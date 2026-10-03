"""TTS providers: edge-tts (default, free, no key) -> Piper (local) -> Kokoro-82M (local) -> mock."""
from __future__ import annotations

import asyncio
import logging
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from ..config import settings
from ..media import ffmpeg, run_cmd
from ..ratelimit import ProviderUnavailable, TransientError, limiter, with_backoff

logger = logging.getLogger("t2s.tts")


class TTSProvider(ABC):
    name: str

    @abstractmethod
    def configured(self) -> tuple[bool, str]: ...

    @abstractmethod
    async def synth(self, text: str, out_path: Path) -> Path:
        """Write speech for `text` to out_path (.mp3 or .wav). Return the actual path written."""


class EdgeTTS(TTSProvider):
    name = "edge"

    def configured(self) -> tuple[bool, str]:
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            return False, "edge-tts not installed (pip install edge-tts)"
        return True, ""

    async def synth(self, text: str, out_path: Path) -> Path:
        import edge_tts
        out = out_path.with_suffix(".mp3")

        async def call():
            try:
                await edge_tts.Communicate(text, settings.edge_voice, rate=settings.edge_rate).save(str(out))
            except Exception as e:  # network/service hiccups are transient
                raise TransientError(f"edge-tts: {e}") from e
            if not out.exists() or out.stat().st_size < 1000:
                raise TransientError("edge-tts returned empty audio")
            return out

        return await with_backoff(lambda: limiter("edge").run(call), attempts=3)


class PiperTTS(TTSProvider):
    name = "piper"

    def configured(self) -> tuple[bool, str]:
        if not shutil.which(settings.piper_bin):
            return False, f"piper binary not found ({settings.piper_bin}); set PIPER_BIN"
        if not settings.piper_model or not Path(settings.piper_model).exists():
            return False, "set PIPER_MODEL to a downloaded voice .onnx file"
        return True, ""

    async def synth(self, text: str, out_path: Path) -> Path:
        out = out_path.with_suffix(".wav")
        try:
            await run_cmd([settings.piper_bin, "--model", settings.piper_model, "--output_file", str(out)],
                          timeout=300, stdin=text.encode())
        except RuntimeError as e:
            raise ProviderUnavailable(f"piper failed: {str(e)[-300:]}")
        return out


class KokoroTTS(TTSProvider):
    name = "kokoro"
    _pipe = None

    def configured(self) -> tuple[bool, str]:
        try:
            import kokoro  # noqa: F401
            import soundfile  # noqa: F401
        except ImportError:
            return False, "kokoro/soundfile not installed (pip install kokoro soundfile)"
        return True, ""

    async def synth(self, text: str, out_path: Path) -> Path:
        out = out_path.with_suffix(".wav")

        def work():
            import numpy as np
            import soundfile as sf
            from kokoro import KPipeline
            if KokoroTTS._pipe is None:
                KokoroTTS._pipe = KPipeline(lang_code="a")
            chunks = [audio for _, _, audio in KokoroTTS._pipe(text, voice=settings.kokoro_voice)]
            sf.write(str(out), np.concatenate(chunks), 24000)
            return out

        return await asyncio.to_thread(work)


class MockTTS(TTSProvider):
    """Uses demo_assets/audio/<hash>.mp3 if present, else synthesizes a quiet placeholder whose length
    matches the text at ~2.5 words/sec, so timing/captions behave like real speech."""
    name = "mock"

    def configured(self) -> tuple[bool, str]:
        return True, ""

    async def synth(self, text: str, out_path: Path) -> Path:
        out = out_path.with_suffix(".m4a")
        secs = round(len(text.split()) / 2.5 + 0.35, 2)
        # soft two-tone "voice placeholder" so the mix isn't silent; obviously not speech
        await ffmpeg("-f", "lavfi", "-i", f"sine=frequency=220:duration={secs}",
                     "-f", "lavfi", "-i", f"sine=frequency=330:duration={secs}",
                     "-filter_complex", "[0][1]amix=inputs=2,volume=0.08,afade=t=in:d=0.05,"
                     f"afade=t=out:st={max(secs-0.1, 0)}:d=0.1[a]",
                     "-map", "[a]", "-c:a", "aac", "-b:a", "96k", str(out))
        return out


_ALL = {p.name: p for p in (EdgeTTS(), PiperTTS(), KokoroTTS(), MockTTS())}


def chain() -> list[TTSProvider]:
    if settings.mock_mode:
        return [_ALL["mock"]]
    return [_ALL[n.strip()] for n in settings.tts_order.split(",") if n.strip() in _ALL]


def all_providers() -> list[TTSProvider]:
    return list(_ALL.values())
