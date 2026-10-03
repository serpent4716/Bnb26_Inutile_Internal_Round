"""Small FFmpeg/ffprobe helpers shared by agents."""
from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

from .config import ffprobe_bin, require_ffmpeg


async def run_cmd(args: list[str], timeout: float = 600, stdin: bytes | None = None) -> str:
    """Runs in a worker thread rather than asyncio.create_subprocess_exec, which raises
    NotImplementedError on Windows under uvicorn's SelectorEventLoop (e.g. with --reload)."""
    try:
        proc = await asyncio.to_thread(subprocess.run, args, input=stdin, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Command timed out: {' '.join(args[:4])}...")
    if proc.returncode != 0:
        raise RuntimeError(f"{args[0]} failed ({proc.returncode}): {proc.stderr.decode(errors='ignore')[-1500:]}")
    return proc.stdout.decode(errors="ignore")


async def ffmpeg(*args: str, timeout: float = 900) -> None:
    await run_cmd([require_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", *args], timeout=timeout)


def probe_duration(path: str | Path) -> float:
    out = subprocess.run(
        [ffprobe_bin(), "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True).stdout
    return round(float(json.loads(out)["format"]["duration"]), 3)


def probe_has_audio(path: str | Path) -> bool:
    out = subprocess.run(
        [ffprobe_bin(), "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True).stdout
    return bool(out.strip())
