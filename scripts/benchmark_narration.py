"""Render one controlled fictional legal example for pronunciation comparison."""
import argparse
import json
import os
import re
import resource
import subprocess
import time
from pathlib import Path

from lecture_studio.document import Passage
from lecture_studio.pronunciation import spoken_text
from lecture_studio.speech import Speaker, duration
from lecture_studio.teaching import Scene
from lecture_studio.video import render, run

PARAGRAPH = [
    ("شروط الطعن", "نَفْتَرِضُ، لِغَرَضِ التَّدْرِيسِ، نَصًّا قانونيًّا افتراضيًّا. "
     "تشترط المادة (١٢) لقبول الطعن أن يقدِّم المدَّعي طلبًا مكتوبًا خلال خمسة عشر يومًا من تاريخ الإخطار."),
    ("الاستثناء", "ويُستثنى من هذا الشرط مَن أثبت وجود قوَّة قاهرة منعت الإيداع في الموعد، "
     "بِشَرْطِ أن يزول المانع قبل قيد الطلب."),
    ("عبء الإثبات", "وتحمِّل المادة ٢٧ المدَّعي عبء الإثبات، ما لم يُقرَّ الخصم بواقعة الإخطار. "
     "ولا يترتَّب على بُطلان الإخطار سقوط الحقِّ في الطعن."),
    ("بداية الميعاد", "أمَّا التقادم، فيُحسَب من تاريخ الاستحقاق، ما لم ينصَّ التشريع على خلاف ذلك. "
     "وفي التطبيق، نميِّز بين تاريخ صدور القرار وتاريخ تبليغه، ثم نتحقَّق من الشرط والاستثناء."),
]


def ffprobe(path):
    return json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)], text=True
    ))["streams"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("engine", choices=("silma", "audar", "edge"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    profile = PARAGRAPH
    (out / "script.txt").write_text("\n\n".join(text for _, text in profile), encoding="utf-8")
    (out / "pronunciation.txt").write_text(
        "\n\n".join(spoken_text(text) for _, text in profile), encoding="utf-8")
    passage = Passage(1, [0, 0, 1, 1], "", "text", "fixture")
    scenes = [Scene(title, text, [], ["fixture"]) for title, text in profile]
    speaker = Speaker(args.engine, "ar-JO-TaimNeural", "-10%")
    started = time.perf_counter()
    seconds = render(out, scenes, {"fixture": passage}, speaker, (1280, 720), True)
    render_seconds = time.perf_counter() - started
    video = out / "lecture.mp4"
    streams = {s["codec_type"]: s for s in ffprobe(video)}
    tracks = [float(streams[k]["duration"]) for k in ("video", "audio", "subtitle")]
    if max(tracks) - min(tracks) > .16:
        raise ValueError(f"Audio, video and caption durations differ: {tracks}")
    assert streams["audio"]["tags"]["handler_name"] == f"{args.engine} Arabic narration"
    assert streams["audio"]["codec_name"] == "aac"
    assert streams["video"]["codec_name"] == "h264"
    run("-i", video, "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-")

    # Keep the lecture at its native pace. Match the requested comparison window
    # with a pitch-preserving tempo adjustment only where necessary.
    tempo = seconds / 57 if seconds > 59 else seconds / 47 if seconds < 46 else 1
    mp3 = out / f"{args.engine}.mp3"
    run("-i", video, "-map", "0:a:0", "-af", f"atempo={tempo:.6f}", "-c:a", "libmp3lame",
        "-b:a", "128k", mp3)
    length = duration(mp3)
    if not 45 <= length <= 60:
        raise ValueError(f"Unexpected MP3 length: {length:.2f}s")
    analysis = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(mp3), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, check=True,
    )
    peak = float(re.search(r"max_volume: (-?[\d.]+) dB", analysis.stderr)[1])
    if peak < -35:
        raise ValueError(f"Silent or very quiet MP3: peak {peak} dBFS")
    usage = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    stats = {
        "engine": args.engine, "mp3_seconds": round(length, 2),
        "video_seconds": round(seconds, 2), "benchmark_mp3_tempo": round(tempo, 3),
        "render_wall_seconds": round(render_seconds, 2), "runner_cores": os.cpu_count(),
        "cpu_seconds": round(sum(u.ru_utime + u.ru_stime for u in (usage, children)), 2),
        "peak_process_rss_mib": round(usage.ru_maxrss / 1024, 1),
        "peak_child_rss_mib": round(children.ru_maxrss / 1024, 1),
        "stream_end_seconds": dict(zip(("video", "audio", "subtitle"), tracks)),
        "peak_dbfs": peak,
    }
    (out / "metrics.json").write_text(json.dumps(stats, indent=2) + "\n")
    print(json.dumps(stats, indent=2), flush=True)


if __name__ == "__main__":
    main()
