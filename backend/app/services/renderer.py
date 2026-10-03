"""EDL -> MP4 via FFmpeg. Command/file builders are pure; render() runs them.

Graph: per-segment trim/atrim -> concat -> crop to aspect (x follows crop_track via sendcmd)
-> zoompan (zoom punches, scale to output size) -> subtitles (.ass: captions + hook overlay).
Helper files sit next to the output and ffmpeg runs with cwd there, so the filtergraph names them
bare (Windows drive-letter paths need awkward escaping inside filter arguments).
"""

import json
import re
from pathlib import Path

from app.services import media

OUTPUT_SIZE = {"9:16": (1080, 1920), "1:1": (1080, 1080), "16:9": (1920, 1080)}
ASPECT = {"9:16": 9 / 16, "1:1": 1.0, "16:9": 16 / 9}
HOOK_COLOUR = "&H00FFFFFF"
EMPHASIS_TAG = r"{\c&H16A5F9&}"  # inline colour override is &HBBGGRR& (amber)


def _even(x: float) -> int:
    return int(x) // 2 * 2


def crop_box(src_w: int, src_h: int, aspect: str) -> tuple[int, int]:
    """Largest crop of the source with the target aspect ratio."""
    a = ASPECT[aspect]
    return (_even(src_h * a), _even(src_h)) if src_w / src_h > a else (_even(src_w), _even(src_w / a))


def crop_x(x_center: float, src_w: int, crop_w: int) -> int:
    return _even(min(max(x_center * src_w - crop_w / 2, 0), src_w - crop_w))


def crop_commands(track: list[dict], src_w: int, crop_w: int) -> str:
    """sendcmd script moving crop@cr's x along the crop track (only when it changes)."""
    lines, last = [], None
    for p in track:
        x = crop_x(p["x_center"], src_w, crop_w)
        if x != last:
            lines.append(f"{p['t']:.3f} crop@cr x {x};")
            last = x
    return "\n".join(lines) + "\n"


def _ass_time(t: float) -> str:
    cs = round(max(t, 0) * 100)
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _ass_text(s: str) -> str:
    return re.sub(r"[{}\\]", "", s).replace("\n", " ")


def build_ass(edl: dict, out_w: int, out_h: int) -> str:
    """Captions (bottom/centre per caption_style, emphasis chunks coloured) + text overlays (hook, top)."""
    clean = edl.get("caption_style") == "clean_bottom"
    cap_size = round(out_h * (0.032 if clean else 0.045))
    cap_margin = round(out_h * (0.06 if clean else 0.22))
    hook_size = round(min(out_w, out_h) * 0.075)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {out_w}
PlayResY: {out_h}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Arial,{cap_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{3 if clean else 6},{0 if clean else 2},2,60,60,{cap_margin},1
Style: Hook,Arial,{hook_size},{HOOK_COLOUR},{HOOK_COLOUR},&H00000000,&HB4000000,-1,0,0,0,100,100,0,0,3,18,0,8,70,70,{round(out_h * 0.1)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for c in edl.get("captions", []):
        text = _ass_text(c["text"])
        if c.get("style") == "emphasis":
            text = EMPHASIS_TAG + text
        events.append(f"Dialogue: 0,{_ass_time(c['start'])},{_ass_time(c['end'])},Cap,,0,0,0,,{text}")
    for o in edl.get("overlays", []):
        if o.get("text"):
            events.append(f"Dialogue: 1,{_ass_time(o['start'])},{_ass_time(o['end'])},Hook,,0,0,0,,{_ass_text(o['text'])}")
    return head + "\n".join(events) + "\n"


def build_ffmpeg_args(edl: dict, src: Path, out_name: str, src_w: int, src_h: int, fps: float,
                      has_audio: bool, ass_name: str | None, cmd_name: str | None) -> list[str]:
    segs = edl["segments"]
    out_w, out_h = OUTPUT_SIZE[edl["aspect_ratio"]]
    parts = []
    for i, s in enumerate(segs):
        parts.append(f"[0:v]trim=start={s['start']:.3f}:end={s['end']:.3f},setpts=PTS-STARTPTS[v{i}]")
        if has_audio:
            parts.append(f"[0:a]atrim=start={s['start']:.3f}:end={s['end']:.3f},asetpts=PTS-STARTPTS[a{i}]")
    ins = "".join(f"[v{i}]" + (f"[a{i}]" if has_audio else "") for i in range(len(segs)))
    parts.append(f"{ins}concat=n={len(segs)}:v=1:a={int(has_audio)}[vc]" + ("[ac]" if has_audio else ""))

    chain = []
    cw, ch = crop_box(src_w, src_h, edl["aspect_ratio"])
    if (cw, ch) != (_even(src_w), _even(src_h)):
        track = edl.get("crop_track") or []
        x0 = crop_x(track[0]["x_center"] if track else 0.5, src_w, cw)
        if cmd_name:
            chain.append(f"sendcmd=f={cmd_name}")
        chain.append(f"crop@cr=w={cw}:h={ch}:x={x0}:y={(src_h - ch) // 2}")
    zooms = edl.get("zooms") or []
    if zooms:
        z = "+".join(f"between(in_time\\,{zz['start']:.3f}\\,{zz['end']:.3f})*{zz['scale'] - 1:.3f}" for zz in zooms)
        chain.append(f"zoompan=z='1+{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={out_w}x{out_h}:fps={fps:g}")
    else:
        chain.append(f"scale={out_w}:{out_h}:flags=lanczos")
    chain.append("setsar=1")
    if ass_name:
        chain.append(f"subtitles={ass_name}")
    parts.append("[vc]" + ",".join(chain) + "[vout]")

    args = ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-filter_complex", ";".join(parts), "-map", "[vout]"]
    if has_audio:
        args += ["-map", "[ac]", "-c:a", "aac", "-b:a", "160k"]
    return args + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
                   "-movflags", "+faststart", out_name]


async def render(edl: dict, src: Path, out: Path, src_w: int, src_h: int, fps: float) -> Path:
    """Render `edl` from `src` to `out` (helper files written beside it)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    streams = json.loads(await media.run(media.probe_args(src))).get("streams", [])
    has_audio = any(s.get("codec_type") == "audio" for s in streams)

    out_w, out_h = OUTPUT_SIZE[edl["aspect_ratio"]]
    ass_name = cmd_name = None
    if edl.get("captions") or any(o.get("text") for o in edl.get("overlays", [])):
        ass_name = f"{out.stem}.ass"
        (out.parent / ass_name).write_text(build_ass(edl, out_w, out_h), encoding="utf-8")
    cw, _ = crop_box(src_w, src_h, edl["aspect_ratio"])
    if edl.get("crop_track") and cw < src_w:
        cmd_name = f"{out.stem}.cmd"
        (out.parent / cmd_name).write_text(crop_commands(edl["crop_track"], src_w, cw), encoding="utf-8")

    await media.run(build_ffmpeg_args(edl, src, out.name, src_w, src_h, fps or 30, has_audio, ass_name, cmd_name),
                    cwd=out.parent)
    return out
