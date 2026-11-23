import json
import shutil
import subprocess
import sys

import pytest

from lecture_studio import document, planning, teaching
from tests.make_sample import sample


def test_extraction_and_plan(tmp_path):
    path = tmp_path / "sample.pdf"
    sample(path, blank=True)
    passages, failed, _, headings, pages = document.extract(path)
    assert pages == 3
    assert failed[0]["page"] == 3
    assert any(p.method == "text" and "عندما يسخن الماء" in p.text for p in passages)
    assert any(p.method == "ocr" and "البخار" in p.text for p in passages)
    assert all(p.box[2] > p.box[0] for p in passages)
    lectures = list(planning.plan(passages, headings, 2, 2, 25, True))
    assert lectures[0][0] == "حالات الماء"
    assert all(p.page == 2 for p in lectures[0][1])


def test_explanation_and_exam_references(monkeypatch):
    item = document.Passage(1, [0, 0, 5, 5], "يتحول الماء إلى بخار.", "text", "p1-1-1")
    narration = {"title": "التبخر", "narration": "التبخر تحول الماء إلى بخار.",
                 "points": ["ماء", "بخار"], "refs": [item.id], "visual": "flow"}
    exam = {"kind": "مقالي", "question": "ما التبخر؟", "answer": item.text, "refs": [item.id]}
    replies = iter([{"scenes": [narration]}, {"questions": [exam]}, {"scenes": [
        dict(narration, refs=["p99-1-1"])]}])
    monkeypatch.setattr(teaching, "ask", lambda *args: next(replies))
    scenes, missing = teaching.explain("custom", "simple", "الماء", [item], [])
    assert missing == {}
    assert scenes[0].visual == "flow"
    questions, skipped = teaching.questions("custom", "simple", scenes, [item])
    assert questions[0]["refs"] == [item.id]
    assert "تطبيقي" in skipped
    with pytest.raises(ValueError, match="مراجع"):
        teaching.explain("custom", "simple", "الماء", [item], [])


def test_mp4_with_arabic_audio_and_resume(tmp_path):
    assert shutil.which("espeak-ng")
    source = tmp_path / "sample.pdf"
    sample(source)
    output = tmp_path / "output"
    command = [sys.executable, "-m", "lecture_studio", str(source), "--out", str(output),
               "--tts", "espeak", "--voice", "ar", "--resolution", "720", "--aspect", "9:16"]
    subprocess.run(command, check=True)
    video = output / "lecture-001" / "lecture.mp4"
    report = subprocess.check_output(["ffprobe", "-v", "error", "-show_streams",
                                      "-of", "json", str(video)], text=True)
    streams = {s["codec_type"]: s for s in json.loads(report)["streams"]}
    assert streams["video"]["codec_name"] == "h264"
    assert streams["video"]["pix_fmt"] == "yuv420p"
    assert streams["video"]["width"] == 720 and streams["video"]["height"] == 1280
    assert streams["audio"]["codec_name"] == "aac"
    assert streams["audio"]["tags"]["language"] == "ara"
    assert streams["subtitle"]["codec_name"] == "mov_text"
    assert video.read_bytes().find(b"moov") < video.read_bytes().find(b"mdat")
    scan = subprocess.run(["ffmpeg", "-v", "info", "-i", str(video), "-vn", "-af", "volumedetect",
                           "-f", "null", "-"], capture_output=True, text=True, check=True)
    peak = float(scan.stderr.split("max_volume: ")[1].split()[0])
    assert peak > -30
    transcript = output / "lecture-001" / "transcript.md"
    assert "التبخر" in transcript.read_text()
    before = video.stat().st_mtime_ns
    subprocess.run(command, check=True)
    assert video.stat().st_mtime_ns == before
    coverage = json.loads((output / "coverage.json").read_text())
    assert coverage["lectures"][0]["status"] == "complete"
    assert coverage["lectures"][0]["pages"] == [1, 2]
