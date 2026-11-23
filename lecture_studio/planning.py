from itertools import groupby


def plan(passages, headings, first, last, minutes, analytic):
    titles = {}
    for heading in headings:
        titles.setdefault(heading["page"], heading["title"])
    starts = sorted(titles, reverse=True)
    budget = max(80, minutes * (65 if analytic else 125))
    selected = (p for p in passages if first <= p.page <= last)
    for chapter, items in groupby(selected, lambda p: next((n for n in starts if n <= p.page), 0)):
        batch, words = [], 0
        title = titles.get(chapter, "محتوى الكتاب")
        for passage in items:
            size = len(passage.text.split())
            if batch and words + size > budget:
                yield title, batch
                batch, words = [], 0
            batch.append(passage)
            words += size
        if batch:
            yield title, batch


def batches(items, max_chars=3400):
    batch, size = [], 0
    for item in items:
        if batch and size + len(item.text) > max_chars:
            yield batch
            batch, size = [], 0
        batch.append(item)
        size += len(item.text)
    if batch:
        yield batch
