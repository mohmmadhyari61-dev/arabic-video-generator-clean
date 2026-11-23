"""Prepare narration while keeping the original text for captions and export."""
import re
import unicodedata

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
TERMS = {
    "الطعن": "الطَّعْن", "التقادم": "التَّقادُم", "الإخطار": "الإِخْطار",
    "البطلان": "البُطْلان", "الإثبات": "الإِثْبات", "الدعوى": "الدَّعْوَى",
    "الاختصاص": "الاخْتِصاص", "السقوط": "السُّقُوط", "النفاذ": "النَّفاذ",
    "بشرط": "بِشَرْط", "ما لم": "مَا لَمْ", "استثناء": "اسْتِثْنَاء",
}
TERM = re.compile(r"(?<![\w\u064b-\u0652])(?:" + "|".join(TERMS)
                  + r")(?![\w\u064b-\u0652])")
ARTICLE = re.compile(
    r"(?<!\w)(المادة|البند|الفقرة)(?:\s+رقم)?\s+"
    r"(?:\(([1-9][0-9]{0,2})\)|([1-9][0-9]{0,2}))(?![\w/–—:%٪−-]|[.,٫٬]\d)"
)


def spoken_text(text):
    from num2words import num2words

    text = unicodedata.normalize("NFC", text).translate(ARABIC_DIGITS)
    text = " ".join(text.split())

    def article(match):
        label, bracketed, plain = match.groups()
        number = num2words(int(bracketed or plain), lang="ar").replace(" و ", " و")
        return f"{label} رقم {number}"

    return TERM.sub(lambda m: TERMS[m[0]], ARTICLE.sub(article, text))


def chunks(text, limit, measure=len):
    """Return original text units, splitting at the strongest nearby boundary."""
    words = re.findall(r"\S+", text)
    start = 0
    while start < len(words):
        end, strong, weak = start, start, start
        while end < len(words):
            word = words[end]
            if end > start and measure(" ".join(words[start:end+1])) > limit:
                break
            end += 1
            if word.endswith((".", "؟", "!", "؛", "?")):
                strong = end
            elif word.endswith(("،", ",", ":")):
                weak = end
        if end < len(words):
            halfway = start + max(1, (end-start)//2)
            end = strong if strong >= halfway else weak if weak >= halfway else end
        yield " ".join(words[start:end])
        start = end


def pause_after(text, final):
    if final:
        return .25
    if text.endswith((".", "؟", "!", "?", "؛")):
        return .18
    if text.endswith(("،", ",", ":")):
        return .09
    return .04
