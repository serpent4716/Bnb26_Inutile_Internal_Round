"""AssemblyAgent: EDL first, then a deterministic FFmpeg render derived from it.
Editing the EDL re-renders without calling any LLM/TTS/footage API."""
from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path

from ..cache import stable_hash
from ..config import settings
from ..media import ffmpeg, probe_has_audio
from ..schemas import EDL, AssemblyOutput, AudioOutput, ScriptOutput, VisualOutput
from ..tracking import tracker
from .edl import build_ass, build_edl, write_text

NORM = "scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps},setsar=1,format=yuv420p"
X264 = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p"]


def _file_sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def render_key(edl: EDL) -> str:
    """Content key: same timeline + same audio bytes -> same video, across runs (instant demo re-runs)."""
    d = edl.model_dump()
    d.pop("run_id")
    for v in d["voice"]:
        v["path"] = _file_sha(v["path"]) if Path(v["path"]).exists() else v["path"]
    return stable_hash(d)


def _filter_path(p: Path) -> str:
    s = str(p.resolve()).replace("\\", "/")
    return s.replace(":", r"\:").replace("'", r"\'")


async def _segment(seg, i: int, edl: EDL, work: Path) -> Path:
    out = work / f"seg_{i:02d}.mp4"
    w, h, fps = edl.width, edl.height, edl.fps
    d = f"{seg.duration:.3f}"
    if seg.source.kind == "video":
        await ffmpeg("-ss", f"{seg.source.in_point:.3f}", "-stream_loop", "-1", "-i", seg.source.path,
                     "-t", d, "-vf", NORM.format(w=w, h=h, fps=fps), "-an", *X264, str(out))
    else:  # Ken Burns: one still -> slow zoom toward center
        frames = max(1, int(round(seg.duration * fps)))
        bw, bh = int(w * 1.5), int(h * 1.5)
        zoom = (f"scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
                f"zoompan=z='min(zoom+{0.18 / frames:.5f},1.18)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                f":d={frames}:s={w}x{h}:fps={fps},setsar=1,format=yuv420p")
        await ffmpeg("-i", seg.source.path, "-vf", zoom, "-frames:v", str(frames), "-an", *X264, str(out))
    return out


async def render(edl: EDL) -> AssemblyOutput:
    t0 = time.monotonic()
    run_dir = settings.runs_dir / edl.run_id
    key = render_key(edl)
    final = run_dir / f"short_{key[:10]}.mp4"
    shared = settings.cache_dir / "renders" / f"{key}.mp4"
    shared.parent.mkdir(parents=True, exist_ok=True)
    ass_path = run_dir / "captions.ass"
    write_text(ass_path, build_ass(edl))
    write_text(run_dir / "edl.json", edl.model_dump_json(indent=2))
    if not final.exists() and shared.exists():
        shutil.copy(shared, final)
    if final.exists():                         # same EDL -> same video, instant
        tracker().used("render", "ffmpeg", cached=True)
        return AssemblyOutput(edl=edl, video_path=str(final), ass_path=str(ass_path), render_seconds=0)

    work = run_dir / "render_tmp"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    segs = [await _segment(s, i, edl, work) for i, s in enumerate(edl.video)]
    concat_list = work / "list.txt"
    concat_list.write_text("".join(f"file '{p.name}'\n" for p in segs))
    video_only = work / "video.mp4"
    await ffmpeg("-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(video_only))

    voice = work / "voice.m4a"
    ins = []
    for a in edl.voice:
        ins += ["-i", a.path]
    pads = "".join(f"[{i}:a]aresample=48000,apad=whole_dur={a.duration:.3f},atrim=0:{a.duration:.3f}[a{i}];"
                   for i, a in enumerate(edl.voice))
    cat = "".join(f"[a{i}]" for i in range(len(edl.voice)))
    await ffmpeg(*ins, "-filter_complex", f"{pads}{cat}concat=n={len(edl.voice)}:v=0:a=1[v]",
                 "-map", "[v]", "-c:a", "aac", "-b:a", "160k", str(voice))

    args = ["-i", str(video_only), "-i", str(voice)]
    vf = f"[0:v]ass='{_filter_path(ass_path)}'[vout]"
    if edl.music and Path(edl.music.path).exists() and probe_has_audio(edl.music.path):
        args += ["-stream_loop", "-1", "-i", edl.music.path]
        m = f"[2:a]volume={edl.music.volume},aresample=48000[m];"
        if edl.music.duck:
            af = (f"{m}[1:a]asplit=2[vk][vs];[m][vs]sidechaincompress=threshold=0.03:ratio=10:attack=15:release=350[md];"
                  "[vk][md]amix=inputs=2:duration=first:normalize=0[aout]")
        else:
            af = f"{m}[1:a][m]amix=inputs=2:duration=first:normalize=0[aout]"
    else:
        af = "[1:a]anull[aout]"
    await ffmpeg(*args, "-filter_complex", f"{vf};{af}", "-map", "[vout]", "-map", "[aout]",
                 "-t", f"{edl.total_duration:.3f}", *X264, "-c:a", "aac", "-b:a", "160k",
                 "-movflags", "+faststart", str(final))
    shutil.rmtree(work, ignore_errors=True)
    shutil.copy(final, shared)
    tracker().used("render", "ffmpeg")
    return AssemblyOutput(edl=edl, video_path=str(final), ass_path=str(ass_path),
                          render_seconds=round(time.monotonic() - t0, 2))


async def run(run_id: str, script: ScriptOutput, audio: AudioOutput, visuals: VisualOutput,
              edl_override: EDL | None = None) -> AssemblyOutput:
    music = settings.music_path or None
    if not music:
        demo_music = settings.demo_assets / "music" / "bed.m4a"
        music = str(demo_music) if demo_music.exists() else None
    edl = edl_override or build_edl(run_id, script, audio, visuals, music_path=music)
    return await render(edl)
