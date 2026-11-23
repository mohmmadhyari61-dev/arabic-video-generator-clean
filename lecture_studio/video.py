import math
import os
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, features

from .document import split_text
from .speech import duration
from .pronunciation import pause_after

NAVY = "#112638"
TEAL = "#12726b"
INK = "#173344"
MUTED = "#466172"
BG = "#f1f5f3"
FONT = "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"


def wrap(text, draw, font, width):
    result = []
    for paragraph in text.splitlines():
        line = ""
        for word in paragraph.split():
            proposed = f"{line} {word}".strip()
            if line and draw.textlength(proposed, font=font, direction="rtl") > width:
                result.append(line)
                line = word
            else:
                line = proposed
        result.append(line)
    return result


def slide(path, scene, pages, size):
    if not features.check_feature("raqm"):
        raise RuntimeError("يلزم Pillow مع دعم RAQM لتشكيل العربية.")
    width, height = size
    image = Image.new("RGB", size, BG)
    draw = ImageDraw.Draw(image)
    scale = min(width, height) / 720
    pad = int(55 * scale)

    def font(px):
        return ImageFont.truetype(os.getenv("LECTURE_FONT", FONT), max(12, round(px * scale)))

    def rtl(text, x, y, f, color=INK):
        draw.text((x, y), text, font=f, fill=color, direction="rtl", anchor="rt")

    def block(value, x, y, available, max_lines, px, color=INK):
        for n in range(px, 12, -2):
            selected = font(n)
            lines = wrap(value, draw, selected, available)
            if len(lines) <= max_lines and all(
                draw.textlength(line, font=selected, direction="rtl") <= available for line in lines
            ):
                break
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] += "…"
        for line in lines:
            while line and draw.textlength(line, font=selected, direction="rtl") > available:
                line = line[:-2].rstrip() + "…" if len(line) > 2 else ""
            rtl(line, x, y, selected, color)
            y += int(n * scale * 1.38)

    draw.rectangle((0, 0, width, int(height * .30)), fill=NAVY)
    rtl("استوديو المحاضرات العربية", width-pad, pad//2, font(21), "#9ee3d5")
    block(scene.title, width-pad, pad + int(18*scale), width-2*pad, 2, 45, "#ffffff")
    points = scene.points or list(split_text(scene.narration, 205))[:3]
    if scene.visual == "table" and not scene.points:
        points = scene.narration.splitlines()[:4]
    top, bottom = int(height * .35), int(height * .87)
    gap = max(10, int(13 * scale))
    rows = points[:4]
    row_h = (bottom-top-gap*(len(rows)-1)) // len(rows)
    if scene.visual == "map" and len(rows) > 1:
        draw_map(draw, block, rows, width, pad, top, bottom, gap, scale)
        rows = []
    if len(rows) == 1:
        row_h = min(row_h, round(195 * scale))
        top = (top + bottom - row_h) // 2
    for i, point in enumerate(rows):
        y = top+i*(row_h+gap)
        draw.rounded_rectangle((pad, y, width-pad, y+row_h), radius=int(12*scale),
                               fill="#d4ebe6" if scene.visual == "highlight" else "#ffffff")
        if scene.visual == "table" and "|" in point:
            cells = [cell.strip() for cell in point.split("|")][:4]
            cell_w = (width-2*pad)//len(cells)
            for j, value in enumerate(cells):
                right = width-pad-j*cell_w
                if j:
                    draw.line((right, y+5, right, y+row_h-5), fill="#b9d2cd", width=2)
                block(value, right-gap, y+gap, cell_w-2*gap, 2, 26)
        else:
            inset = 2*gap
            if scene.visual in ("steps", "flow"):
                rtl(str(i+1), width-pad-gap, y+gap, font(24), TEAL)
                inset += 2*gap
                if scene.visual == "flow" and i+1 < len(rows):
                    x = width//2
                    draw.polygon([(x-6, y+row_h+2), (x+6, y+row_h+2), (x, y+row_h+gap-1)], fill=TEAL)
            px = 36 if len(rows) == 1 else 29
            text_top = y + (max(gap, row_h//5) if len(rows) == 1 else gap)
            block(point, width-pad-inset, text_top, width-2*pad-inset-gap,
                  max(1, int((y+row_h-text_top) / (px*scale*1.38))), px)
    draw.line((pad, int(height*.90), width-pad, int(height*.90)), fill="#c8d9d5", width=2)
    label = "الصفحات " + "، ".join(map(str, pages))
    block(label, width-pad, int(height*.925), width-2*pad, 1, 22, MUTED)
    image.save(path)


def draw_map(draw, block, rows, width, pad, top, bottom, gap, scale):
    center = width // 2
    count = len(rows) - 1
    usable = width - 2 * pad
    node_width = (usable - gap * (count - 1)) // count
    root_width = min(usable, max(node_width, usable // 2))
    root_height = round(96 * scale)
    branch_height = round(144 * scale)
    branch_top = bottom - branch_height
    joint = (top + root_height + branch_top) // 2

    def node(label, left, right, y, height, fill):
        draw.rounded_rectangle((left, y, right, y+height), radius=gap, fill=fill)
        block(label, right-gap, y+gap, right-left-2*gap, 2, 26)

    line_width = max(2, round(3 * scale))
    draw.line((center, top+root_height, center, joint), fill=TEAL, width=line_width)
    for i, label in enumerate(rows[1:]):
        right = width-pad-i*(node_width+gap)
        left = right-node_width
        x = (left+right)//2
        draw.line((center, joint, x, joint, x, branch_top), fill=TEAL, width=line_width)
        node(label, left, right, branch_top, branch_height, "#ffffff")
    node(rows[0], center-root_width//2, center+root_width//2, top, root_height, "#d4ebe6")


def run(*args):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *map(str, args)],
                   check=True)


def timestamp(seconds):
    ms = round(seconds * 1000)
    return f"{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d}.{ms%1000:03d}"


def render(directory, scenes, sources, speaker, size, captions):
    work = directory / ".render"
    work.mkdir(exist_ok=True)
    clips, cues = [], []
    elapsed = 0.
    for i, scene in enumerate(scenes, 1):
        frame = work / f"frame-{i}.png"
        pages = sorted({sources[ref].page for ref in scene.refs})
        slide(frame, scene, pages, size)
        narration = list(speaker.chunks(scene.narration))
        for j, chunk in enumerate(narration, 1):
            name = f"speech-v2-{i}-{j}"
            audio = work / (name + speaker.suffix)
            if not audio.exists():
                speaker.speak(chunk, audio)
            frames = math.ceil((duration(audio) + pause_after(chunk, j == len(narration))) * 24)
            span = frames / 24
            clip = work / (name + ".mp4")
            tmp = work / "pending.mp4"
            if not clip.exists():
                run("-loop", "1", "-framerate", "24", "-i", frame, "-i", audio,
                    "-af", "apad", "-t", f"{span:.7f}", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "22", "-pix_fmt", "yuv420p", "-threads", "2", "-c:a", "aac",
                    "-ar", "48000", "-ac", "1", tmp)
                tmp.replace(clip)
            clips.append(f"file '{clip.name}'\nduration {span:.7f}")
            if captions:
                text = " ".join(chunk.replace("-->", "→").replace("<", "‹").split())
                cues.append(f"{timestamp(elapsed)} --> {timestamp(elapsed + span)}\n{text}")
            elapsed += span
    listing = work / "concat.txt"
    listing.write_text("\n".join(clips) + "\n", encoding="utf-8")
    args = ["-f", "concat", "-safe", "1", "-i", listing]
    if captions:
        vtt = directory / "captions.vtt"
        vtt.write_text("WEBVTT\n\n" + "\n\n".join(cues) + "\n", encoding="utf-8")
        args.extend(["-i", vtt, "-map", "0:v:0", "-map", "0:a:0", "-map", "1:s:0",
                     "-c:s", "mov_text", "-metadata:s:s:0", "language=ara", "-disposition:s:0", "0"])
    pending = work / "final.mp4"
    run(*args, "-c:v", "copy", "-c:a", "copy", "-metadata:s:a:0", "language=ara",
        "-metadata:s:a:0", f"handler_name={speaker.backend} Arabic narration",
        "-movflags", "+faststart", pending)
    video = directory / "lecture.mp4"
    pending.replace(video)
    return duration(video)
