"""F6: 16:9 -> 9:16 smart reframe. MediaPipe face detection at ~5 fps -> face centre x
-> EMA smoothing per segment -> crop_track [{t (clip timeline), x_center (0-1 of source width)}].
"""

import asyncio
import subprocess
import threading
import urllib.request
from pathlib import Path

import numpy as np

from app.services import media
from app.services.edl import output_time
from app.services.storage import MEDIA_DIR

PLATFORMS = {
    "shorts":   {"aspect": "9:16", "max_dur": 60,   "captions": True,  "caption_style": "bold_center"},
    "reels":    {"aspect": "9:16", "max_dur": 90,   "captions": True,  "caption_style": "bold_center"},
    "tiktok":   {"aspect": "9:16", "max_dur": 180,  "captions": True,  "caption_style": "bold_center"},
    "youtube":  {"aspect": "16:9", "max_dur": None, "captions": False},
    "linkedin": {"aspect": "1:1",  "max_dur": 600,  "captions": True,  "caption_style": "clean_bottom"},
    "x":        {"aspect": "16:9", "max_dur": 140,  "captions": True},
}

SAMPLE_FPS = 5
FRAME_W = 320        # detection runs on downscaled frames
EMA_ALPHA = 0.25     # calibration knob: lower = steadier framing, slower to follow movement
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_detector/"
             "blaze_face_short_range/float16/latest/blaze_face_short_range.tflite")
MODEL_PATH = MEDIA_DIR / "models" / "blaze_face_short_range.tflite"

_detector = None
_lock = threading.Lock()


def _get_detector():
    global _detector
    with _lock:
        if _detector is None:
            import mediapipe as mp  # heavy import, only when reframing
            from mediapipe.tasks.python import BaseOptions, vision

            if not MODEL_PATH.exists():
                MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
                urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
            _detector = (vision.FaceDetector.create_from_options(vision.FaceDetectorOptions(
                base_options=BaseOptions(model_asset_buffer=MODEL_PATH.read_bytes()),  # buffer: path-with-spaces safe
                min_detection_confidence=0.5,
            )), mp)
    return _detector


def face_xs(src: Path, start: float, dur: float, src_w: int, src_h: int) -> list[float | None]:
    """Normalized face-centre x for each sampled frame (largest face), None where no face.

    BlazeFace short-range squeezes its input to 128x128, so a mid-shot face in a wide frame is ~20px and
    gets missed. Detect on overlapping square tiles (left / centre / right) instead and map back.
    """
    w, h = FRAME_W, max(2, round(FRAME_W * src_h / src_w / 2) * 2)
    raw = subprocess.run(media.frames_args(src, start, dur, SAMPLE_FPS, w, h), capture_output=True, check=True).stdout
    detector, mp = _get_detector()
    side = min(w, h)
    tiles = sorted({0, (w - side) // 2, w - side})
    xs: list[float | None] = []
    for frame in np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3):
        best = None  # (area, centre_x in frame px)
        for x0 in tiles:
            tile = np.ascontiguousarray(frame[:side, x0:x0 + side])
            for d in detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=tile)).detections:
                b = d.bounding_box
                if best is None or b.width * b.height > best[0]:
                    best = (b.width * b.height, x0 + b.origin_x + b.width / 2)
        xs.append(best[1] / w if best else None)
    return xs


def smooth(xs: list[float | None]) -> list[float]:
    """EMA over detections. Misses hold the last position; before the first face, use the first face;
    no face at all -> 0.5 (centre crop)."""
    first = next((x for x in xs if x is not None), 0.5)
    ema, out = first, []
    for x in xs:
        if x is not None:
            ema += EMA_ALPHA * (x - ema)
        out.append(round(ema, 4))
    return out


def _track(src: Path, segments: list[dict], src_w: int, src_h: int) -> list[dict]:
    track = []
    for seg in segments:  # smoothing restarts per segment: a jump cut is a hard cut, not a pan
        xs = smooth(face_xs(src, seg["start"], seg["end"] - seg["start"], src_w, src_h))
        track += [{"t": output_time(min(seg["start"] + k / SAMPLE_FPS, seg["end"]), segments), "x_center": x}
                  for k, x in enumerate(xs)]
    return track


async def crop_track(src: Path, segments: list[dict], src_w: int, src_h: int) -> list[dict]:
    return await asyncio.to_thread(_track, src, segments, src_w, src_h)
