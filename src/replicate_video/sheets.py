"""Images an agent can look at: contact sheet, shot frames, strips of consecutive frames around each boundary."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .media import Probe, decode, frame_at


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def label(img: Image.Image, text: str) -> Image.Image:
    d = ImageDraw.Draw(img)
    f = _font(max(10, img.width // 12))
    box = d.textbbox((0, 0), text, font=f)
    d.rectangle((0, 0, box[2] + 6, box[3] + 6), fill=(0, 0, 0))
    d.text((3, 2), text, fill=(255, 230, 0), font=f)
    return img


def tile(images: list[Image.Image], cols: int, gap: int = 2, bg=(20, 20, 20)) -> Image.Image:
    if not images:
        return Image.new("RGB", (10, 10), bg)
    w, h = images[0].size
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w + (cols - 1) * gap, rows * h + (rows - 1) * gap), bg)
    for i, im in enumerate(images):
        sheet.paste(im, ((i % cols) * (w + gap), (i // cols) * (h + gap)))
    return sheet


def stamp(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:06.3f}"


def contact(path: str | Path, info: Probe, out: Path, *, max_frames: int = 48, width: int = 180) -> Path:
    step = max(0.25, info.duration / max_frames)
    frames = decode(path, width=width, fps=1 / step, info=info)
    imgs = [label(Image.fromarray(f), stamp(i * step)) for i, f in enumerate(frames)]
    cols = 8 if info.width < info.height else 6
    out.parent.mkdir(parents=True, exist_ok=True)
    tile(imgs, cols).save(out, quality=88)
    return out


def strip(
    path: str | Path,
    info: Probe,
    start: float,
    end: float,
    out: Path,
    *,
    width: int = 200,
    roi: tuple[float, float, float, float] | None = None,
    every: int = 1,
) -> Path:
    """Consecutive frames from start to end (seconds), labelled with time and frame number.

    roi = (x, y, w, h) as fractions of the frame, to zoom on one region.
    """
    first = max(0, int(round(start * info.fps)))
    src_w = width if roi is None else int(width / max(roi[2], 0.05))
    frames = decode(path, width=src_w, start=first / info.fps, end=end + 0.5 / info.fps, info=info)
    imgs = []
    for k, f in enumerate(frames[::every]):
        n = first + k * every
        im = Image.fromarray(f)
        if roi:
            x, y, w, h = roi
            im = im.crop((int(x * im.width), int(y * im.height), int((x + w) * im.width), int((y + h) * im.height)))
        imgs.append(label(im, f"{stamp(n / info.fps)} f{n}"))
    cols = min(len(imgs), 8 if (roi or info.width < info.height) else 6) or 1
    out.parent.mkdir(parents=True, exist_ok=True)
    tile(imgs, cols).save(out, quality=88)
    return out


def boundary_strips(path, info: Probe, boundaries: list[dict], folder: Path, *, around: int = 4) -> list[str]:
    paths = []
    for b in boundaries:
        a = (b["frame"] - around) / info.fps
        e = (b.get("end_frame", b["frame"]) + around - 1) / info.fps
        every = max(1, (b.get("end_frame", b["frame"]) - b["frame"] + 2 * around) // 16)
        name = f"{b['kind']}_{b['time']:07.3f}.jpg"
        strip(path, info, max(0.0, a), e, folder / name, every=every)
        paths.append(f"strips/{name}")
    return paths


def shot_frames(path, info: Probe, shots: list[dict], folder: Path, *, width: int = 540) -> list[dict]:
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for s in shots:
        picks = {
            "first": s["start"] + 1 / info.fps,
            "middle": (s["start"] + s["end"]) / 2,
            "last": max(s["start"], s["end"] - 2 / info.fps),
        }
        files = {}
        for k, t in picks.items():
            name = f"shot{s['index']:02d}_{k}.jpg"
            frame_at(path, t, folder / name, width=min(width, info.width))
            files[k] = f"frames/{name}"
        out.append(files)
    return out


def side_by_side(a: np.ndarray, b: np.ndarray, text: str) -> Image.Image:
    ia, ib = Image.fromarray(a), Image.fromarray(b)
    if ib.size != ia.size:
        ib = ib.resize(ia.size)
    pair = tile([ia, ib], 2, gap=4)
    return label(pair, text)
