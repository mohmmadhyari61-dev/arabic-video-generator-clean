import argparse
import hashlib
import json
import shutil
from dataclasses import asdict
from pathlib import Path

from . import document, planning, teaching, video
from .speech import Speaker


def write(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def dataset(path, out):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    index = out / "source.json"
    if index.exists():
        result = json.loads(index.read_text(encoding="utf-8"))
        if result["sha256"] != digest:
            raise ValueError("مجلد النتائج يخص ملفاً آخر.")
        return result
    print("استخراج النص والفهرس وقراءة الصفحات المصورة", flush=True)
    source, failed, warnings, headings, pages = document.extract(path)
    result = {"sha256": digest, "filename": path.name, "pages": pages, "headings": headings,
              "failures": failed, "warnings": warnings, "passages": [asdict(p) for p in source]}
    write(index, result)
    return result


def prepare(args, source, title, headings, folder):
    if args.provider == "reading":
        return teaching.reading(source), [], {}, {
            k: "الأسئلة التحليلية تتطلب مزوداً للنموذج" for k in teaching.QUESTION_KINDS
        }
    scenes, questions, omitted, skipped_questions = [], [], {}, {}
    for number, batch in enumerate(planning.batches(source), 1):
        checkpoint = folder / f"batch-{number:03d}.json"
        if checkpoint.exists():
            result = json.loads(checkpoint.read_text(encoding="utf-8"))
            group = [teaching.Scene(**s) for s in result["scenes"]]
            missing = result["missing"]
        else:
            print(f"شرح مجموعة المقاطع {number}", flush=True)
            chapter = [h for h in headings if abs(h["page"] - batch[0].page) <= 15][:15]
            group, missing = teaching.explain(args.provider, args.level, title, batch, chapter)
            result = {"scenes": [asdict(s) for s in group], "missing": missing, "exam": {}}
            write(checkpoint, result)
        scenes.extend(group)
        omitted.update(missing)
        for i in range(0, len(group), 4):
            key = str(i)
            if key not in result["exam"]:
                result["exam"][key] = teaching.questions(args.provider, args.level, group[i:i+4], batch)
                write(checkpoint, result)
            rows, skipped = result["exam"][key]
            questions.extend(rows)
            skipped_questions.update(skipped)
    present = {row["kind"] for row in questions}
    return scenes, questions, omitted, {k: v for k, v in skipped_questions.items() if k not in present}


def pages(refs, sources):
    return "، ".join(map(str, sorted({sources[r].page for r in refs})))


def main():
    cli = argparse.ArgumentParser(description="استوديو المحاضرات العربية")
    cli.add_argument("pdf", type=Path)
    cli.add_argument("--out", type=Path, default=Path("output"))
    cli.add_argument("--analyze", action="store_true")
    cli.add_argument("--provider", choices=("reading", "local", "custom"), default="reading")
    cli.add_argument("--level", choices=("simple", "university", "exam"), default="university")
    cli.add_argument("--first", type=int, default=1)
    cli.add_argument("--last", type=int, default=0)
    cli.add_argument("--chapter", type=int, default=0, help="رقم المدخل في الفهرس")
    cli.add_argument("--minutes", type=int, default=25)
    cli.add_argument("--voice", help="معرّف صوت Edge الاحتياطي")
    cli.add_argument("--tts", choices=("edge", "piper", "espeak", "silma", "audar", "heygen"))
    cli.add_argument("--rate", choices=("-20%", "-10%", "0%", "+10%"), default="-10%")
    cli.add_argument("--aspect", choices=("16:9", "9:16"), default="16:9")
    cli.add_argument("--resolution", type=int, choices=(720, 1080), default=1080)
    cli.add_argument("--no-captions", action="store_true")
    args = cli.parse_args()
    if not args.analyze and args.tts is None:
        cli.error("اختر محرك التعليق الصوتي عبر --tts قبل التوليد.")
    if args.tts == "edge":
        args.voice = args.voice or "ar-JO-TaimNeural"
    elif args.tts == "heygen":
        args.voice = "Fouad"
    else:
        args.voice = "ar" if args.tts == "espeak" else args.tts
    args.out.mkdir(parents=True, exist_ok=True)
    data = dataset(args.pdf, args.out)
    outline = [f"{i}. صفحة {h['page']} — {h['title']}" for i, h in enumerate(data["headings"], 1)]
    report = [f"# {data['filename']}", f"عدد الصفحات: {data['pages']}", "## الفهرس",
              *(outline or ["لم يعثر النظام على عناوين للفهرس."]), "## مشكلات الاستخراج",
              *[f"- صفحة {r['page']} — {r['reason']}" for r in data["failures"] + data["warnings"]]]
    (args.out / "analysis.md").write_text("\n\n".join(report), encoding="utf-8")
    if args.analyze:
        return
    last = args.last or data["pages"]
    if args.chapter:
        if not 1 <= args.chapter <= len(outline):
            cli.error("رقم الفصل خارج الفهرس.")
        start = data["headings"][args.chapter-1]["page"]
        end = min((h["page"]-1 for h in data["headings"] if h["page"] > start), default=data["pages"])
        args.first, last = max(args.first, start), min(last, end)
    if not 1 <= args.first <= last <= data["pages"] or not 1 <= args.minutes <= 60:
        cli.error("نطاق الصفحات أو مدة المحاضرة غير صالحين.")
    options = {k: v for k, v in vars(args).items() if k not in {"out", "pdf"}}
    if args.provider != "reading":
        options["model"] = teaching.settings(args.provider)[:2]
    identity = json.loads(json.dumps(options))
    config = args.out / "config.json"
    if config.exists() and json.loads(config.read_text()) != identity:
        cli.error("الاستئناف يتطلب الإعدادات نفسها ومجلد نتائج الملف الأصلي.")
    write(config, identity)
    sources = {p["id"]: document.Passage(**p) for p in data["passages"]}
    lectures = list(planning.plan(sources.values(), data["headings"], args.first, last,
                                  args.minutes, args.provider != "reading"))
    mode = "استخراج وقراءة منظمة" if args.provider == "reading" else "شرح تحليلي"
    coverage = {"mode": mode, "provider": args.provider, "tts": args.tts, "voice": args.voice,
                "selected": [args.first, last], "unreadable": data["failures"],
                "warnings": data["warnings"], "lectures": []}
    for i, (title, items) in enumerate(lectures, 1):
        coverage["lectures"].append({"lecture": i, "chapter": title, "status": "pending",
                                     "pages": sorted({p.page for p in items}),
                                     "planned_refs": [p.id for p in items]})
    write(args.out / "coverage.json", coverage)
    if not lectures:
        cli.error("لا يوجد نص قابل للاستخراج ضمن النطاق المحدد. راجع analysis.md.")
    size = (args.resolution * 16 // 9 // 2 * 2, args.resolution)
    if args.aspect == "9:16":
        size = size[::-1]
    speaker = Speaker(args.tts, args.voice, args.rate)
    for i, (title, items) in enumerate(lectures, 1):
        print(f"{mode} — المحاضرة {i} من {len(lectures)}", flush=True)
        folder = args.out / f"lecture-{i:03d}"
        folder.mkdir(exist_ok=True)
        script = folder / "script.json"
        if script.exists():
            content = json.loads(script.read_text())
            scenes = [teaching.Scene(**r) for r in content["scenes"]]
            rows, omitted, skipped = (content[k] for k in ("questions", "omitted", "skipped"))
        else:
            scenes, rows, omitted, skipped = prepare(args, items, title, data["headings"], folder)
            write(script, {"scenes": [asdict(s) for s in scenes], "questions": rows,
                           "omitted": omitted, "skipped": skipped})
        transcript = [f"# {title}", mode] + [
            f"## {s.title}\n\n{s.narration}\n\nالصفحات: {pages(s.refs, sources)}"
            for s in scenes]
        exam = ["# أسئلة المحاضرة"] + [
            f"## {q['kind']}\n\n{q['question']}\n\n**الإجابة**: {q['answer']}\n\n"
            f"الصفحات: {pages(q['refs'], sources)}" for q in rows]
        if rows:
            transcript.extend(["## تدريب الامتحان", *exam[1:]])
        exam.extend(f"- {kind} — {reason}" for kind, reason in skipped.items())
        for name, lines in (("transcript", transcript), ("questions", exam)):
            (folder / f"{name}.md").write_text("\n\n".join(lines), encoding="utf-8")
        render_scenes = list(scenes)
        for q in rows:
            render_scenes.append(teaching.Scene(q["kind"], q["question"], [], q["refs"], "highlight"))
            render_scenes.append(teaching.Scene("الإجابة النموذجية", q["answer"], [], q["refs"], "highlight"))
        entry = coverage["lectures"][i-1]
        entry.update(status="rendering", topics=[{"title": s.title, "refs": s.refs} for s in scenes],
                     unaddressed=omitted, missing_question_types=skipped)
        write(args.out / "coverage.json", coverage)
        mp4 = folder / "lecture.mp4"
        seconds = video.duration(mp4) if mp4.exists() else video.render(
            folder, render_scenes, sources, speaker, size, not args.no_captions,
        )
        entry.update(status="complete", seconds=seconds)
        write(args.out / "coverage.json", coverage)
        shutil.rmtree(folder / ".render", ignore_errors=True)
        for checkpoint in folder.glob("batch-*.json"):
            checkpoint.unlink()


if __name__ == "__main__":
    main()
