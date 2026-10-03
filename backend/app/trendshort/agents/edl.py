"""EDL builder (pure, deterministic, unit-tested) + ASS karaoke captions + SRT export."""
from __future__ import annotations

from pathlib import Path

from ..schemas import (EDL, AudioOutput, EDLAudioSegment, EDLCaptionStyle, EDLMusic, EDLOverlay, EDLSource,
                       EDLVideoSegment, ScriptOutput, VisualOutput, WordStamp)


def build_edl(run_id: str, script: ScriptOutput, audio: AudioOutput, visuals: VisualOutput,
              music_path: str | None = None, caption_style: EDLCaptionStyle | None = None) -> EDL:
    """Audio duration is the clock: every video segment is exactly as long as its voice segment."""
    a_by = {a.scene_id: a for a in audio.scenes}
    v_by = {v.scene_id: v for v in visuals.scenes}
    t = 0.0
    video, voice, words, overlays = [], [], [], []
    for s in script.scenes:
        a, v = a_by[s.id], v_by[s.id]
        dur = round(a.duration_sec, 3)
        c = v.chosen
        video.append(EDLVideoSegment(
            scene_id=s.id, start=round(t, 3), duration=dur,
            source=EDLSource(kind=c.kind, path=c.local_path or c.url, in_point=0.0, ken_burns=c.kind == "image"),
            attribution=c.attribution))
        voice.append(EDLAudioSegment(scene_id=s.id, start=round(t, 3), duration=dur, path=a.path))
        words += [WordStamp(word=w.word, start=round(t + w.start, 3), end=round(t + min(w.end, dur), 3))
                  for w in a.words]
        if s.id == script.scenes[0].id:
            overlays.append(EDLOverlay(text=s.on_screen_text or script.hook, start=round(t, 3),
                                       end=round(t + dur, 3), position="top", kind="hook"))
        elif s.on_screen_text:
            overlays.append(EDLOverlay(text=s.on_screen_text, start=round(t, 3), end=round(t + dur, 3),
                                       position="top", kind="scene_text"))
        t += dur
    music = EDLMusic(path=music_path) if music_path else None
    return EDL(run_id=run_id, total_duration=round(t, 3), video=video, voice=voice, music=music,
               caption_style=caption_style or EDLCaptionStyle(), words=words, overlays=overlays)


# ------------------------------------------------------------------ captions

def _ts_ass(t: float) -> str:
    cs = int(round(max(t, 0) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ts_srt(t: float) -> str:
    ms = int(round(max(t, 0) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def caption_lines(words: list[WordStamp], per_line: int) -> list[list[WordStamp]]:
    """Group words into short lines, breaking early after sentence punctuation."""
    lines, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= per_line or w.word.endswith((".", "!", "?")):
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    return lines


def build_ass(edl: EDL) -> str:
    st = edl.caption_style
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {edl.width}
PlayResY: {edl.height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{st.font},{st.size},{st.primary_color},{st.secondary_color},{st.outline_color},&H80000000,1,0,0,0,100,100,0,0,1,6,2,2,80,80,{st.margin_v},1
Style: Hook,{st.font},96,&H00FFFFFF,&H00FFFFFF,&H007F3DFF,&H00000000,1,0,0,0,100,100,0,0,3,18,0,8,90,90,260,1
Style: SceneText,{st.font},64,&H00FFFFFF,&H00FFFFFF,&H40000000,&H00000000,1,0,0,0,100,100,0,0,3,14,0,8,90,90,300,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    for o in edl.overlays:
        style = "Hook" if o.kind == "hook" else "SceneText"
        fx = r"{\fad(120,120)\t(0,180,\fscx104\fscy104)\t(180,320,\fscx100\fscy100)}" if o.kind == "hook" else r"{\fad(120,120)}"
        ev.append(f"Dialogue: 1,{_ts_ass(o.start)},{_ts_ass(o.end)},{style},,0,0,0,,{fx}{_esc(o.text)}")
    lines = caption_lines(edl.words, st.words_per_line)
    for i, line in enumerate(lines):
        start = line[0].start
        nxt = lines[i + 1][0].start if i + 1 < len(lines) else edl.total_duration
        end = min(max(line[-1].end + 0.25, line[-1].end), nxt)
        parts = []
        for j, w in enumerate(line):
            # \k duration = from this word's start to the next word's start (karaoke fill)
            w_end = line[j + 1].start if j + 1 < len(line) else w.end
            gap_before = (w.start - start) if j == 0 else 0
            if gap_before > 0.01:
                parts.append(f"{{\\k{int(round(gap_before * 100))}}}")
            parts.append(f"{{\\k{max(1, int(round((w_end - w.start) * 100)))}}}{_esc(w.word.upper())} ")
        ev.append(f"Dialogue: 0,{_ts_ass(start)},{_ts_ass(end)},Caption,,0,0,0,,{''.join(parts).rstrip()}")
    return head + "\n".join(ev) + "\n"


def build_srt(edl: EDL, per_line: int = 6) -> str:
    out = []
    for i, line in enumerate(caption_lines(edl.words, per_line), 1):
        out.append(f"{i}\n{_ts_srt(line[0].start)} --> {_ts_srt(line[-1].end)}\n{' '.join(w.word for w in line)}\n")
    return "\n".join(out)


def write_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)
