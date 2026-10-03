import io
import math
import os
import wave
from array import array

os.environ.setdefault("JWT_SECRET", "test-secret-at-least-32-bytes-long!!")

from app.services.media import parse_probe  # noqa: E402
from app.services.transcription import assign_words, finalize, is_filler_segment, wav_chunks  # noqa: E402


def test_wav_chunks_cut_in_silence(tmp_path):
    rate = 16000
    # 5s of tone with silent gaps at 1.5-1.7s and 3.3-3.5s
    samples = [0 if 1.5 <= i / rate < 1.7 or 3.3 <= i / rate < 3.5 else int(8000 * math.sin(i / 5)) for i in range(5 * rate)]
    path = tmp_path / "a.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(array("h", samples).tobytes())

    chunks = list(wav_chunks(path, max_bytes=1024 + 2 * rate * 2))  # 2s limit per chunk
    starts = [s for s, _, _, _ in chunks]
    assert len(chunks) == 3
    assert 1.5 < starts[1] < 1.7 and 3.3 < starts[2] < 3.5  # cuts landed in the gaps
    assert all(a[1] == b[0] for a, b in zip(chunks, chunks[1:]))  # contiguous
    assert chunks[-1][1] == 5.0 and chunks[-1][3] == 1.0
    frames = 0
    for _, _, data, _ in chunks:
        with wave.open(io.BytesIO(data)) as w:
            frames += w.getnframes()
    assert frames == 5 * rate  # nothing lost or duplicated


def test_assign_and_finalize():
    segs = [{"start": 0.0, "end": 2.0, "text": " Hello there.", "words": []},
            {"start": 2.0, "end": 3.0, "text": " Um, uh.", "words": []},
            {"start": 3.0, "end": 5.0, "text": " Okay.", "words": []}]
    words = [{"w": " Hello", "start": 0.1, "end": 0.5}, {"w": " there.", "start": 0.6, "end": 1.2},
             {"w": " Um,", "start": 2.1, "end": 2.3}, {"w": " uh.", "start": 2.5, "end": 2.7},
             {"w": " Okay.", "start": 3.9, "end": 4.4}]
    assign_words(segs, words)
    out = finalize(segs, duration=6.0)
    assert [len(s["words"]) for s in out] == [2, 2, 1]
    assert [s["is_filler"] for s in out] == [False, True, False]
    assert [s["silence_after"] for s in out] == [0.9, 1.2, 1.6]  # gaps between words, last runs to duration
    assert out[0]["text"] == "Hello there." and out[0]["words"][0]["w"] == "Hello"


def test_filler_segment():
    assert is_filler_segment(["You", "know,", "like,", "ummm"])
    assert not is_filler_segment(["You", "knowledge", "is", "power"])
    assert not is_filler_segment([])


def test_parse_probe():
    meta = parse_probe({"format": {"duration": "12.5"},
                        "streams": [{"codec_type": "audio"},
                                    {"codec_type": "video", "width": 1920, "height": 1080, "avg_frame_rate": "30000/1001"}]})
    assert meta == {"duration": 12.5, "width": 1920, "height": 1080, "fps": 29.97}
    assert parse_probe({"format": {}, "streams": [{"codec_type": "video", "avg_frame_rate": "0/0"}]})["fps"] is None
