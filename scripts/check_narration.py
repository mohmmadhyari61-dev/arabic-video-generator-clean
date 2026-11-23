"""Independent, repeatable Arabic pronunciation check on the public test fixture."""
import argparse
import json
import re
import subprocess
import unicodedata
from pathlib import Path

from lecture_studio.pronunciation import ARABIC_DIGITS


def normalized(text):
    text = unicodedata.normalize("NFD", text.translate(ARABIC_DIGITS))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.findall(r"\w+", text))


TERMS = {
    "المادة ١٢": ("12", "اثنا عشر", "اثني عشر", "اثنا عشرة", "اثنتي عشرة", "الثانية عشرة"),
    "المادة ٢٧": ("27", "سبعة وعشرون", "سبعة وعشرين", "سبعة و عشرون", "السابعة والعشرون"),
    "خمسة عشر يومًا": ("خمسة عشر يوما", "15 يوما", "خمسة عشر يوم"),
    "الطعن": ("الطعن",), "الإخطار": ("الاخطار",), "قوة قاهرة": ("قوة قاهرة", "قوه قاهره"),
    "بشرط": ("بشرط",), "عبء الإثبات": ("عبء الاثبات", "عبئ الاثبات"),
    "ما لم": ("ما لم", "مالم"), "بطلان": ("بطلان",),
    "سقوط الحق": ("سقوط الحق",), "التقادم": ("التقادم",),
}


def main():
    import numpy as np
    from faster_whisper import WhisperModel

    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    args = parser.parse_args()
    model = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=2)
    pcm = subprocess.check_output(["ffmpeg", "-nostdin", "-v", "error", "-i", str(args.audio),
                                   "-ar", "16000", "-ac", "1", "-f", "f32le", "pipe:1"])
    segments, _ = model.transcribe(np.frombuffer(pcm, dtype="<f4"), language="ar", beam_size=3)
    transcript = " ".join(segment.text.strip() for segment in segments)
    heard = " " + normalized(transcript) + " "
    checks = {term: any(" " + normalized(value) + " " in heard for value in values)
              for term, values in TERMS.items()}
    report = {"recognizer": "Whisper small, Arabic, CPU int8", "transcript": transcript,
              "detected": checks, "detected_count": sum(checks.values()), "total": len(checks)}
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    args.audio.with_name("pronunciation-check.json").write_text(rendered, encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
