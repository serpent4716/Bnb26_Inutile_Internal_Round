import os
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "test-secret-at-least-32-bytes-long!!")

from app.models.clip import EDL  # noqa: E402
from app.services.edl import edl_duration, platform_variant, trim, with_hook  # noqa: E402
from app.services.reframe import PLATFORMS, smooth  # noqa: E402
from app.services.renderer import build_ass, build_ffmpeg_args, crop_box, crop_commands, crop_x  # noqa: E402

EDL_DOC = EDL.model_validate({
    "aspect_ratio": "9:16",
    "segments": [{"start": 10.0, "end": 14.0}, {"start": 20.0, "end": 26.0}],
    "captions": [{"start": 0.0, "end": 1.0, "text": "I lost {big}", "style": "emphasis"},
                 {"start": 8.0, "end": 9.5, "text": "the end", "style": "bold"}],
    "zooms": [{"start": 2.0, "end": 3.0, "scale": 1.2}],
    "crop_track": [{"t": 0.0, "x_center": 0.3}, {"t": 0.2, "x_center": 0.3}, {"t": 5.0, "x_center": 0.7}],
}).model_dump()
WORDS = [{"w": f"w{i}", "start": 20.0 + i * 0.5, "end": 20.4 + i * 0.5} for i in range(12)]


def test_crop_geometry():
    assert crop_box(1280, 720, "9:16") == (404, 720)
    assert crop_box(1280, 720, "1:1") == (720, 720)
    assert crop_box(1280, 720, "16:9") == (1280, 720)
    assert crop_x(0.0, 1280, 404) == 0 and crop_x(1.0, 1280, 404) == 876    # clamped inside the frame
    assert crop_commands(EDL_DOC["crop_track"], 1280, 404) == "0.000 crop@cr x 182;\n5.000 crop@cr x 694;\n"


def test_ass_captions_hook_and_escaping():
    ass = build_ass(with_hook(EDL_DOC, "Stop {cutting} coffee"), 1080, 1920)
    assert "PlayResY: 1920" in ass
    assert "Dialogue: 0,0:00:00.00,0:00:01.00,Cap,,0,0,0,,{\\c&H16A5F9&}I lost big" in ass   # emphasis colour, braces stripped
    assert "Dialogue: 1,0:00:00.00,0:00:02.00,Hook,,0,0,0,,Stop cutting coffee" in ass


def test_ffmpeg_graph():
    args = build_ffmpeg_args(EDL_DOC, Path("src.mp4"), "out.mp4", 1280, 720, 30, True, "out.ass", "out.cmd")
    graph = args[args.index("-filter_complex") + 1]
    assert "[0:v]trim=start=10.000:end=14.000,setpts=PTS-STARTPTS[v0]" in graph
    assert "[v0][a0][v1][a1]concat=n=2:v=1:a=1[vc][ac]" in graph
    assert "sendcmd=f=out.cmd,crop@cr=w=404:h=720:x=182:y=0" in graph
    assert "zoompan=z='1+between(in_time\\,2.000\\,3.000)*0.200'" in graph and "s=1080x1920" in graph
    assert graph.endswith("subtitles=out.ass[vout]")
    silent = build_ffmpeg_args(EDL_DOC, Path("src.mp4"), "out.mp4", 1280, 720, 30, False, None, None)
    assert "atrim" not in silent[silent.index("-filter_complex") + 1] and "[ac]" not in silent


def test_smooth_holds_and_centres():
    assert smooth([None, 0.4, None, 0.8]) == [0.4, 0.4, 0.4, 0.5]   # back-fill, hold, EMA (alpha 0.25)
    assert smooth([None, None]) == [0.5, 0.5]                        # no face -> centre crop


def test_trim_cuts_on_word_boundary():
    short = trim(EDL_DOC, 7.0, WORDS)                 # 4s + 3s of the second segment
    assert short["segments"][-1] == {"start": 20.0, "end": 22.9}   # last word ending <= 23.0
    assert edl_duration(short) <= 7.0
    assert [c["text"] for c in short["captions"]] == ["I lost {big}"]   # caption at 8s dropped
    assert all(p["t"] <= edl_duration(short) for p in short["crop_track"])


def test_platform_variants():
    yt = platform_variant(EDL_DOC, PLATFORMS["youtube"], WORDS)
    assert yt["aspect_ratio"] == "16:9" and yt["captions"] == []
    li = platform_variant(EDL_DOC, PLATFORMS["linkedin"], WORDS)
    assert li["aspect_ratio"] == "1:1" and li["caption_style"] == "clean_bottom" and li["captions"]
    hooked = with_hook(with_hook(EDL_DOC, "first"), "second")
    assert [o["text"] for o in hooked["overlays"]] == ["second"] and hooked["overlays"][0]["end"] == 2.0
