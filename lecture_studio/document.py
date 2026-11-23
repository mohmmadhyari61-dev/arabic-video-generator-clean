import csv
import io
import re
import subprocess
import unicodedata
from dataclasses import dataclass

import pymupdf

HEADING = re.compile(r"^(?:الفصل|الوحدة|الباب|المبحث|المطلب|Chapter|Unit)\s+.{1,85}$", re.I)


@dataclass(frozen=True)
class Passage:
    page: int
    box: list
    text: str
    method: str
    id: str


def ocr_lines(pix, mode):
    result = subprocess.run(
        ["tesseract", "stdin", "stdout", "-l", "ara+eng", "--psm", mode, "-c", "tessedit_create_tsv=1"],
        input=pix.tobytes("png"), capture_output=True, timeout=180, check=True,
    )
    groups = {}
    for row in csv.DictReader(io.StringIO(result.stdout.decode()), delimiter="\t",
                              quoting=csv.QUOTE_NONE):
        if row.get("text", "").strip():
            key = tuple(row[k] for k in ("block_num", "par_num", "line_num"))
            x, y, w, h = (int(row[k]) for k in ("left", "top", "width", "height"))
            groups.setdefault(key, []).append((row["text"], x, y, x+w, y+h))
    return groups.values()


def ocr(page):
    pix = page.get_pixmap(dpi=250, colorspace=pymupdf.csGRAY, alpha=False)
    lines = ocr_lines(pix, "3")
    if len(lines) <= 1:
        lines = max(lines, ocr_lines(pix, "11"), key=len)
    for words in lines:
        coords = [min(w[1] for w in words), min(w[2] for w in words),
                  max(w[3] for w in words), max(w[4] for w in words)]
        box = pymupdf.Rect(*(v * 72 / 250 for v in coords)) * page.derotation_matrix
        yield list(box), " ".join(w[0] for w in words), "ocr"


def extract(path):
    passages, failures, warnings, headings = [], [], [], []
    with pymupdf.open(path) as doc:
        if not doc.is_pdf or doc.needs_pass or not len(doc):
            raise ValueError("يلزم ملف PDF صالح وغير محمي بكلمة مرور.")
        for _, title, page in doc.get_toc():
            if 1 <= page <= len(doc):
                headings.append({"title": title, "page": page})
        for page in doc:
            number = page.number + 1
            try:
                blocks = [(list(b[:4]), unicodedata.normalize("NFKC", b[4]).strip(), "text")
                          for b in page.get_text("blocks", sort=True)
                          if b[6] == 0 and b[4].strip()]
                chars = "".join(b[1] for b in blocks)
                letters = sum(c.isalnum() for c in chars)
                large_image = any(
                    pymupdf.Rect(i["bbox"]).get_area() > page.rect.get_area() * .30
                    for i in page.get_image_info()
                )
                broken = (chars.count("�") > max(2, letters // 10) or
                          bool(re.search(r"[\u0600-\u06ff][\u0180-\u024f]\s*[\u0600-\u06ff]", chars)))
                if not letters or broken or (large_image and letters < 120):
                    try:
                        scanned = list(ocr(page))
                        if scanned:
                            blocks = scanned
                        elif letters:
                            warnings.append({"page": number, "reason": "لم يستخرج OCR نص الصورة"})
                    except (OSError, subprocess.SubprocessError, ValueError) as exc:
                        warnings.append({"page": number, "reason": f"تعذر OCR ({type(exc).__name__})"})
                    if not letters and not any(b[2] == "ocr" for b in blocks):
                        blocks = []
                    if broken and not any(b[2] == "ocr" for b in blocks):
                        blocks = []
                elif len(chars) < 25000:
                    try:
                        for table in page.find_tables().tables:
                            rows = [" | ".join(unicodedata.normalize("NFKC", cell or "") for cell in row) for row in table.extract()]
                            if rows:
                                blocks.append((list(table.bbox), "\n".join(rows), "table"))
                    except (RuntimeError, ValueError):
                        warnings.append({"page": number, "reason": "تعذر تحديد بنية جدول"})
            except (RuntimeError, ValueError) as exc:
                failures.append({"page": number, "reason": type(exc).__name__})
                continue
            if not blocks:
                failures.append({"page": number, "reason": "لا يوجد نص قابل للاستخراج"})
            for i, (box, content, method) in enumerate(blocks, 1):
                if not re.search(r"\w", content):
                    continue
                for j, part in enumerate(split_text(content, 1000), 1):
                    passages.append(Passage(number, box, part, method, f"p{number}-{i}-{j}"))
            if blocks and (not passages or passages[-1].page != number):
                failures.append({"page": number, "reason": "لا يوجد نص قابل للقراءة"})
        if not headings:
            headings = [{"title": line.strip(), "page": p.page}
                        for p in passages for line in p.text.splitlines()
                        if HEADING.fullmatch(line.strip())]
        return passages, failures, warnings, headings, len(doc)


def split_text(text, limit):
    while len(text) > limit:
        split = max(text.rfind(mark, 0, limit) + len(mark)
                    if mark in text[:limit] else 0 for mark in ("\n", "؟ ", ". ", "؛ "))
        if split < limit // 2:
            split = text.rfind(" ", 0, limit)
        if split <= 0:
            split = limit
        yield text[:split].strip()
        text = text[split:].strip()
    if text.strip():
        yield text.strip()
