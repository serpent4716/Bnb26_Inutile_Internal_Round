"""FFmpeg / ffprobe helpers. Builders are pure and return arg lists; run() executes one."""

import asyncio
import json
import subprocess
from fractions import Fraction
from pathlib import Path


def probe_args(src: Path) -> list[str]:
    return ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(src)]


def extract_audio_args(src: Path, out: Path) -> list[str]:
    """16kHz mono 16-bit WAV, what Whisper wants."""
    return ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out)]


KEYFRAME_EVERY_S = 3  # kf_0001.jpg is t=0, kf_0002.jpg is t=3, ...


def keyframes_args(src: Path, out_dir: Path, every_s: float = KEYFRAME_EVERY_S) -> list[str]:
    return ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", f"fps=1/{every_s},scale=640:-2", "-q:v", "4",
            str(out_dir / "kf_%04d.jpg")]


def thumbnail_args(src: Path, out: Path, at: float = 1.0) -> list[str]:
    return ["ffmpeg", "-y", "-v", "error", "-ss", f"{at:.3f}", "-i", str(src), "-frames:v", "1", "-vf", "scale=480:-2",
            "-q:v", "4", str(out)]


def frames_args(src: Path, start: float, dur: float, fps: float, w: int, h: int) -> list[str]:
    """Raw RGB frames on stdout (for face detection)."""
    return ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(src),
            "-vf", f"fps={fps},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]


def parse_probe(data: dict) -> dict:
    """ffprobe JSON -> assets.metadata {duration, width, height, fps}."""
    fmt = data.get("format", {})
    meta = {"duration": float(fmt["duration"]) if "duration" in fmt else None}
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if video:
        try:
            fps = round(float(Fraction(video.get("avg_frame_rate", "0/0"))), 3)
        except ZeroDivisionError:  # still images report 0/0
            fps = None
        meta |= {"width": video.get("width"), "height": video.get("height"), "fps": fps}
    return meta


FFMPEG_TIMEOUT_S = 900


def resolve(args: list[str]) -> list[str]:
    """Swap a bare "ffmpeg"/"ffprobe" for its full path (FFMPEG_DIR, PATH, saved Windows PATH, winget dirs),
    so a fresh install works without restarting the terminal. Unknown binaries pass through unchanged."""
    from app.trendshort.config import find_tool

    return [find_tool(args[0]) or args[0], *args[1:]] if args and args[0] in ("ffmpeg", "ffprobe") else args


async def run(args: list[str], cwd: Path | None = None) -> str:
    """Run a command in a thread (asyncio subprocesses are unreliable on Windows loops). Returns stdout.
    `cwd` lets filtergraphs reference helper files by bare name (no Windows path escaping)."""
    proc = await asyncio.to_thread(subprocess.run, resolve(args), capture_output=True, encoding="utf-8", errors="replace", cwd=cwd,
                                 timeout=FFMPEG_TIMEOUT_S)
    if proc.returncode != 0:
        raise RuntimeError(f"{args[0]} failed: {proc.stderr.strip()[-500:]}")
    return proc.stdout


async def probe(src: Path) -> dict:
    return parse_probe(json.loads(await run(probe_args(src))))
