"""Word-level timestamps: faster-whisper locally (CPU, base/small) -> proportional estimate fallback."""
from __future__ import annotations

import asyncio
import logging
import re

from ..config import settings
from ..schemas import WordStamp

logger = logging.getLogger("t2s.captions")
_model = None


def whisper_available() -> tuple[bool, str]:
    if not settings.whisper_enabled:
        return False, "WHISPER_ENABLED=false"
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False, "faster-whisper not installed"
    return True, ""


def _load():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8",
                              download_root=str(settings.data_dir / "models"))
    return _model


def _decode_16k_mono(path: str):
    """Decode with our FFmpeg instead of faster-whisper's PyAV path (PyAV 19 broke its open() call)."""
    import subprocess

    import numpy as np

    from ..config import require_ffmpeg
    raw = subprocess.run([require_ffmpeg(), "-nostdin", "-v", "error", "-i", str(path), "-f", "s16le",
                          "-ac", "1", "-ar", "16000", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0


async def whisper_words(path: str) -> list[WordStamp]:
    def work():
        segments, _ = _load().transcribe(_decode_16k_mono(path), word_timestamps=True, language="en",
                                         vad_filter=False)
        out = []
        for seg in segments:
            for w in seg.words or []:
                word = w.word.strip()
                if word:
                    out.append(WordStamp(word=word, start=round(w.start, 3), end=round(w.end, 3)))
        return out
    return await asyncio.to_thread(work)


def estimate_words(text: str, duration: float, lead: float = 0.05, tail: float = 0.15) -> list[WordStamp]:
    """Distribute words across the clip proportional to character length (+ a pause weight on punctuation)."""
    words = text.split()
    if not words:
        return []
    weights = [len(re.sub(r"\W", "", w)) + 2 + (3 if re.search(r"[.,!?;:]$", w) else 0) for w in words]
    span = max(duration - lead - tail, 0.1)
    total = sum(weights)
    t, out = lead, []
    for w, wt in zip(words, weights):
        d = span * wt / total
        out.append(WordStamp(word=w, start=round(t, 3), end=round(t + d * 0.92, 3)))
        t += d
    return out


def align_to_script(script_text: str, heard: list[WordStamp]) -> list[WordStamp]:
    """Use whisper timings but the script's spelling (keeps brand names/punctuation right).
    Falls back to whisper text if counts diverge too much."""
    words = script_text.split()
    if heard and abs(len(words) - len(heard)) <= max(2, len(words) // 6):
        n = min(len(words), len(heard))
        out = [WordStamp(word=words[i], start=heard[i].start, end=heard[i].end) for i in range(n)]
        if len(words) > n and out:   # tack leftovers onto the last timing
            last = out[-1]
            for w in words[n:]:
                out.append(WordStamp(word=w, start=last.end, end=last.end + 0.2))
        return out
    return heard
