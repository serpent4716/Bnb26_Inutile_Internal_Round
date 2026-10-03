"""Speech-to-text with word timestamps. Groq Whisper first, local faster-whisper as fallback."""

import asyncio
import io
from array import array
import logging
import re
import threading
import wave
from pathlib import Path
from typing import Awaitable, Callable, Iterator

from app.config import settings

log = logging.getLogger("uvicorn.error")

GROQ_MODEL = "whisper-large-v3-turbo"
GROQ_MAX_BYTES = 24 * 1024 * 1024  # Groq free tier caps uploads at 25MB (~13 min of 16kHz mono WAV)
# Whisper drops disfluencies unless the prompt contains some; we need them for filler cuts.
FILLER_PROMPT = "Umm, so, uh, I was like, you know, basically thinking. Hmm, okay."

FILLER_RE = re.compile(r"^(u+m+|u+h+|e+r+m*|h+m+|a+h+|m+h*m+)$")
# Real words that are only filler when Whisper sets them off with a comma ("like," vs "I like it").
SOFT_FILLERS = {"like", "basically"}
SENTENCE_END = re.compile(r"[.!?][\"')\]]*$")
MAX_SENTENCE_WORDS = 40
SENTENCE_GAP_S = 1.0

Progress = Callable[[float], Awaitable[None]]


def _norm(word: str) -> str:
    return re.sub(r"[^\w']", "", word.lower())


def is_filler_word(word: str) -> bool:
    """`word` is raw Whisper text, punctuation included."""
    t = _norm(word)
    return bool(FILLER_RE.match(t)) or (t in SOFT_FILLERS and word.rstrip().endswith(","))


def filler_mask(words: list[str]) -> list[bool]:
    """Per raw word: is it filler? Includes a comma-delimited "you know,"."""
    mask = [is_filler_word(w) for w in words]
    for i in range(len(words) - 1):
        if _norm(words[i]) == "you" and _norm(words[i + 1]) == "know" and words[i + 1].rstrip().endswith(","):
            mask[i] = mask[i + 1] = True
    return mask


def is_filler_segment(words: list[str]) -> bool:
    """True when every word in the segment is filler ("um", "uh", "like,", "you know,", ...)."""
    return bool(words) and all(filler_mask(words))


def sentences(words: list[dict]) -> list[dict]:
    """Sentence units from word timestamps (Whisper segments can span many sentences).
    Split on . ! ?, on pauses > SENTENCE_GAP_S, or every MAX_SENTENCE_WORDS words.
    Returns [{start, end, text, w0, w1}] with w0..w1 inclusive word indexes.
    """
    out, first = [], 0
    for i, w in enumerate(words):
        last = i == len(words) - 1
        if last or SENTENCE_END.search(w["w"]) or i - first + 1 >= MAX_SENTENCE_WORDS \
                or words[i + 1]["start"] - w["end"] > SENTENCE_GAP_S:
            out.append({"start": words[first]["start"], "end": w["end"], "w0": first, "w1": i,
                        "text": " ".join(x["w"] for x in words[first:i + 1])})
            first = i + 1
    return out


def assign_words(segments: list[dict], words: list[dict]) -> None:
    """Groq returns words flat; attach each to the segment containing its midpoint (else nearest)."""
    i = 0
    for w in words:
        mid = (w["start"] + w["end"]) / 2
        while i < len(segments) - 1 and mid >= segments[i]["end"]:
            i += 1
        if segments:
            segments[i]["words"].append(w)


def finalize(segments: list[dict], duration: float | None) -> list[dict]:
    """Raw segments -> DATABASE_SCHEMA transcripts.segments (idx, is_filler, silence_after)."""
    out = []
    for s in segments:
        text = s["text"].strip()
        if not text:
            continue
        words = [{"w": w["w"].strip(), "start": round(w["start"], 3), "end": round(w["end"], 3), "conf": w.get("conf")}
                 for w in s["words"] if w["w"].strip()]
        out.append({
            "idx": len(out),
            "start": round(s["start"], 3),
            "end": round(s["end"], 3),
            "text": text,
            "words": words,
            "is_filler": is_filler_segment([w["w"] for w in words]),
            "silence_after": 0.0,
        })

    def first_start(s):
        return s["words"][0]["start"] if s["words"] else s["start"]

    def last_end(s):
        return s["words"][-1]["end"] if s["words"] else s["end"]

    for cur, nxt in zip(out, out[1:]):
        cur["silence_after"] = round(max(0.0, first_start(nxt) - last_end(cur)), 3)
    if out and duration:
        out[-1]["silence_after"] = round(max(0.0, duration - last_end(out[-1])), 3)
    return out


CUT_SEARCH_S = 10  # look this far back from the size limit for a quiet place to cut
CUT_WINDOW_S = 0.2


def _quietest(samples: array, rate: int) -> int:
    """Sample index at the centre of the lowest-energy CUT_WINDOW_S window."""
    win = max(1, int(rate * CUT_WINDOW_S))
    best, best_i = None, len(samples) // 2
    for i in range(0, max(1, len(samples) - win), max(1, win // 2)):
        energy = sum(x * x for x in samples[i:i + win])
        if best is None or energy < best:
            best, best_i = energy, i + win // 2
    return best_i


def _wav_bytes(frames: bytes, rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(frames)
    return buf.getvalue()


def wav_chunks(path: Path, max_bytes: int = GROQ_MAX_BYTES) -> Iterator[tuple[float, float, bytes, float]]:
    """Split a 16-bit mono WAV into standalone WAVs under max_bytes, cutting at the quietest
    point near each limit so words aren't split. Yields (start_s, end_s, wav_bytes, fraction_done).
    """
    with wave.open(str(path)) as src:
        assert src.getsampwidth() == 2 and src.getnchannels() == 1, "expects 16-bit mono (media.extract_audio_args)"
        rate, total = src.getframerate(), src.getnframes() or 1
        per_chunk = (max_bytes - 1024) // 2
        carry, offset = b"", 0
        while buf := carry + src.readframes(per_chunk - len(carry) // 2):
            n = len(buf) // 2
            if offset + n >= total:
                cut = n
            else:
                search = min(rate * CUT_SEARCH_S, n // 2)
                cut = n - search + _quietest(array("h", buf[-search * 2:]), rate)
            carry = buf[cut * 2:]
            yield offset / rate, (offset + cut) / rate, _wav_bytes(buf[:cut * 2], rate), (offset + cut) / total
            offset += cut


async def _groq(audio: Path, on_progress: Progress) -> dict:
    from groq import AsyncGroq

    client = AsyncGroq(api_key=settings.GROQ_API_KEY)
    language, segments, words = None, [], []
    for offset, end, data, done in wav_chunks(audio):
        resp = await client.audio.transcriptions.create(
            file=("audio.wav", data),
            model=GROQ_MODEL,
            response_format="verbose_json",
            timestamp_granularities=["word", "segment"],
            prompt=FILLER_PROMPT,
        )
        d = resp.model_dump()
        language = language or d.get("language")
        # Whisper sometimes "finishes the sentence" past the end of a chunk; drop anything starting after it.
        segments += [{"start": s["start"] + offset, "end": min(s["end"] + offset, end), "text": s["text"], "words": []}
                     for s in d.get("segments") or [] if s["start"] + offset < end]
        words += [{"w": w["word"], "start": w["start"] + offset, "end": min(w["end"] + offset, end), "conf": None}
                  for w in d.get("words") or [] if w["start"] + offset < end]
        await on_progress(done)
    assign_words(segments, words)
    return {"language": language, "segments": segments}


_model = None
_model_lock = threading.Lock()


def _local(audio: Path, report: Callable[[float], None]) -> dict:
    global _model
    with _model_lock:
        if _model is None:
            from faster_whisper import WhisperModel
            _model = WhisperModel(settings.WHISPER_LOCAL_MODEL, device="cpu", compute_type="int8")
    segs, info = _model.transcribe(str(audio), word_timestamps=True, initial_prompt=FILLER_PROMPT)
    segments = []
    for s in segs:  # generator: transcription happens while iterating
        segments.append({
            "start": s.start, "end": s.end, "text": s.text,
            "words": [{"w": w.word, "start": w.start, "end": w.end, "conf": round(w.probability, 3)} for w in s.words or []],
        })
        if info.duration:
            report(min(1.0, s.end / info.duration))
    return {"language": info.language, "segments": segments}


async def transcribe(audio_path: Path, duration: float | None = None, on_progress: Progress | None = None) -> dict:
    """Returns {language, full_text, segments} shaped like the `transcripts` collection."""
    async def noop(_):
        pass

    on_progress = on_progress or noop
    raw = None
    if settings.GROQ_API_KEY:
        try:
            raw = await _groq(audio_path, on_progress)
        except Exception:
            log.warning("Groq transcription failed, falling back to local faster-whisper", exc_info=True)
    if raw is None:
        loop = asyncio.get_running_loop()
        raw = await asyncio.to_thread(
            _local, audio_path, lambda f: asyncio.run_coroutine_threadsafe(on_progress(f), loop)
        )
    segments = finalize(raw["segments"], duration)
    return {"language": raw["language"], "full_text": " ".join(s["text"] for s in segments), "segments": segments}
