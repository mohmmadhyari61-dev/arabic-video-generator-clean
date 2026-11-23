import io
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"


def sample(path: Path, blank=False):
    with pymupdf.open() as pdf:
        first = pdf.new_page()
        first.insert_htmlbox(pymupdf.Rect(50, 50, 535, 235), """
        <div dir="rtl" lang="ar">
        <h2>الفصل عن الماء</h2>
        <p>عندما يسخن الماء يتحول إلى بخار. يسمى هذا التحول التبخر.</p>
        </div>""", css="""@font-face {font-family: Arabic; src: url(NotoNaskhArabic-Regular.ttf);}
        * {font-family: Arabic; font-size: 19px}""",
        archive=pymupdf.Archive("/usr/share/fonts/truetype/noto"))
        image = Image.new("RGB", (1050, 420), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(FONT, 52)
        draw.text((980, 100), "عندما يبرد البخار يتحول إلى ماء.", anchor="rt",
                  direction="rtl", font=font, fill="black")
        draw.text((980, 230), "يسمى هذا التحول التكاثف.", anchor="rt",
                  direction="rtl", font=font, fill="black")
        content = io.BytesIO()
        image.save(content, "PNG")
        second = pdf.new_page()
        second.insert_image(pymupdf.Rect(40, 100, 555, 306), stream=content.getvalue())
        if blank:
            pdf.new_page()
        pdf.set_toc([[1, "حالات الماء", 1]])
        pdf.save(path)


if __name__ == "__main__":
    sample(Path(sys.argv[1]))
