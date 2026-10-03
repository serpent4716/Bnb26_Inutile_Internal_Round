"""AudioAgent: per-scene TTS through the free provider chain; measured audio duration drives timing;
word timestamps from faster-whisper (fallback: proportional estimate)."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from ..cache import DiskCache, stable_hash
from ..config import settings
from ..logging_setup import log
from ..media import probe_duration
from ..providers import captions, tts
from ..ratelimit import ProviderUnavailable, RateLimited, TransientError
from ..schemas import AudioOutput, SceneAudio, ScriptOutput
from ..tracking import tracker

logger = logging.getLogger("t2s.audio")
_cache = DiskCache("tts")


async def _synth_one(text: str, scene_id: str, out_dir: Path) -> tuple[Path, str, bool]:
    t = tracker()
    chain = tts.chain()
    key = stable_hash({"text": text, "chain": [p.name for p in chain], "voice": settings.edge_voice,
                       "rate": settings.edge_rate, "piper": settings.piper_model, "kokoro": settings.kokoro_voice})
    hit = _cache.get(key)
    if hit:
        dest = out_dir / f"{scene_id}{Path(hit['path']).suffix}"
        shutil.copy(hit["path"], dest)
        return dest, hit["provider"], True
    errors = []
    for prov in chain:
        ok, why = prov.configured()
        if not ok:
            t.fell_back(f"tts {prov.name}: skipped ({why})")
            continue
        try:
            raw = await prov.synth(text, _cache.path_for(key, ""))
            _cache.set(key, {"path": str(raw), "provider": prov.name}, files=[str(raw)])
            t.add("tts_chars", len(text))
            dest = out_dir / f"{scene_id}{raw.suffix}"
            shutil.copy(raw, dest)
            return dest, prov.name, False
        except (ProviderUnavailable, TransientError, RateLimited, RuntimeError, OSError) as e:
            t.fell_back(f"tts {prov.name}: {str(e)[:120]}")
            errors.append(f"{prov.name}: {e}")
            log(logger, "tts provider failed", logging.WARNING, provider=prov.name, error=str(e)[:200])
    raise RuntimeError("All TTS providers failed: " + " | ".join(errors) +
                       " (install edge-tts, or configure PIPER_BIN/PIPER_MODEL, or set MOCK_MODE=true)")


async def run(run_id: str, script: ScriptOutput) -> AudioOutput:
    t = tracker()
    out_dir = settings.runs_dir / run_id / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    use_whisper, why = captions.whisper_available()
    if settings.mock_mode:
        use_whisper, why = False, "MOCK_MODE"
    if not use_whisper:
        t.fell_back(f"captions whisper: skipped ({why}); using estimated word timings")

    scenes: list[SceneAudio] = []
    for s in script.scenes:                       # sequential on purpose: free tiers, no parallel bursts
        path, prov, cached = await _synth_one(s.narration, s.id, out_dir)
        t.used(f"tts.{s.id}", prov, cached)
        dur = probe_duration(path)
        cap_provider = "estimate"
        words = captions.estimate_words(s.narration, dur)
        if use_whisper:
            try:
                heard = await captions.whisper_words(str(path))
                if heard:
                    words = captions.align_to_script(s.narration, heard)
                    cap_provider = f"faster-whisper:{settings.whisper_model}"
            except Exception as e:  # noqa: BLE001
                t.fell_back(f"captions whisper failed on {s.id}: {str(e)[:100]}")
        t.used(f"captions.{s.id}", cap_provider, cached)
        scenes.append(SceneAudio(scene_id=s.id, path=str(path), duration_sec=dur, words=words,
                                 tts_provider=prov, caption_provider=cap_provider))
    return AudioOutput(scenes=scenes, total_duration=round(sum(a.duration_sec for a in scenes), 3))
