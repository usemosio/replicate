"""Burned-in captions from pixels: where the caption band is, when each caption group appears and when the
highlighted (lit) word moves.

Speech recognition gives when a word is said; editors light a word on screen 0.03-0.5 s later and group words
their own way. The frames are the truth, so timing comes from the band's pixels. The words themselves come from
OCR when `rapidocr-onnxruntime` is installed, otherwise from reading the saved band crops.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .media import Probe, decode, iter_frames


def _hsv(f: np.ndarray):
    mx, mn = f.max(axis=-1), f.min(axis=-1)
    sat = (mx - mn) / np.maximum(mx, 1e-3)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    d = np.maximum(mx - mn, 1e-6)
    hue = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    return hue, sat, mx


def _text_mask(f: np.ndarray) -> np.ndarray:
    """Pixels that look like caption ink: near-white, or bright and saturated (a lit word)."""
    hue, sat, val = _hsv(f)
    white = (val > 0.82) & (sat < 0.22)
    lit = (val > 0.55) & (sat > 0.45)
    return white | lit


def _dilate(m: np.ndarray, r: int) -> np.ndarray:
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dy or dx:
                out |= np.roll(np.roll(m, dy, axis=0), dx, axis=1)
    return out


def _letters(f: np.ndarray):
    """(shape, lit): `shape` is caption ink whatever its colour state (white, grey for words not yet said, lit),
    found as bright pixels hugging a dark outline, plus plain near-white text; `lit` is the saturated part of it."""
    hue, sat, val = _hsv(f)
    near_outline = _dilate(val < 0.2, 4)
    shape = ((val > 0.42) & near_outline) | ((val > 0.85) & (sat < 0.2))
    lit = (val > 0.55) & (sat > 0.45) & near_outline
    return shape, lit


def _band_at(score: np.ndarray, rows: np.ndarray) -> tuple[int, int] | None:
    h = score.shape[0]
    peak = int(score.argmax())
    if score[peak] < 1e-5:
        return None
    lo = hi = peak
    while lo > 0 and score[lo - 1] > 0.25 * score[peak]:
        lo -= 1
    while hi < h - 1 and score[hi + 1] > 0.25 * score[peak]:
        hi += 1
    pad = max(1, (hi - lo) // 3)
    return max(0, lo - pad), min(h - 1, hi + pad)


def find_bands(path: str | Path, info: Probe, *, sample_fps: float = 4.0, width: int = 160) -> list[dict]:
    """Horizontal bands where caption text comes and goes. Captions that move to another height for part of the
    video (a lower band for the ending, a band per speaker) show up as separate bands with their own time span."""
    sample_fps = min(sample_fps, 240 / max(info.duration, 1e-3))  # memory stays flat on long videos
    frames = decode(path, width=width, fps=sample_fps, info=info).astype(np.float32) / 255.0
    if len(frames) < 4:
        return []
    gray = frames @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    grad = np.abs(np.diff(gray, axis=2))
    ink = _text_mask(frames)[:, :, 1:]
    rows = ((grad > 0.25) & ink).mean(axis=2)  # (T, H): ink next to a strong edge, per row
    h = rows.shape[1]
    # Look in time windows, so a band used only near the end is not drowned by the main one.
    win = max(12, len(rows) // 6)
    found: list[tuple[int, int]] = []
    for start in range(0, len(rows), win // 2):
        part = rows[start : start + win]
        if len(part) < 6:
            continue
        # caption rows have dense ink that changes; titles and UI have dense ink that does not
        score = np.convolve(part.mean(axis=0) * part.std(axis=0), np.ones(3) / 3, mode="same")
        top = float(score.max())
        for _ in range(3):  # a window can hold captions and a title card at once
            band = _band_at(score, part)
            if not band or score[band[0] : band[1] + 1].max() < 0.3 * top:
                break
            if (part[:, band[0] : band[1] + 1].mean(axis=1) > 0.01).mean() > 0.3:
                found.append(band)
            score[band[0] : band[1] + 1] = 0
    merged: list[list[int]] = []
    for lo, hi in sorted(found):
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    bands = []
    for lo, hi in merged:
        if (hi - lo) / h > 0.2:
            continue
        level = rows[:, lo : hi + 1].mean(axis=1)
        present = level > 0.01
        on = np.flatnonzero(present)
        changes = float(np.abs(np.diff(level[on])).mean()) if len(on) > 2 else 0.0
        times = np.flatnonzero(present) / sample_fps
        bands.append({
            "y0": round(lo / h, 4),
            "y1": round((hi + 1) / h, 4),
            "present_share": round(float(present.mean()), 3),
            "from": round(float(times.min()), 2) if len(times) else None,
            "to": round(float(times.max()) + 1 / sample_fps, 2) if len(times) else None,
            "change": round(changes, 4),
            # captions change every half second; a title or a poll card mostly holds still
            "kind": "captions" if changes > 0.004 else "title",
            "confidence": "high" if present.mean() > 0.05 else "low",
        })
    bands.sort(key=lambda b: -b["present_share"])
    return [b for b in bands if b["confidence"] == "high"]


def find_band(path: str | Path, info: Probe, **kw) -> dict | None:
    """The strongest caption band, or None."""
    bands = find_bands(path, info, **kw)
    return bands[0] if bands else None


def _signature(mask: np.ndarray, cols: int = 48, rows: int = 6) -> np.ndarray:
    h, w = mask.shape
    m = mask[: h - h % rows, : w - w % cols]
    return m.reshape(rows, m.shape[0] // rows, cols, m.shape[1] // cols).mean(axis=(1, 3))


def track(path: str | Path, info: Probe, band: dict, *, width: int = 360, crops: Path | None = None,
          start: float = 0.0, end: float | None = None, prefix: str = "") -> dict:
    """Frame-accurate caption events inside the band, between start and end seconds."""
    height = max(2, int(round(info.height * width / info.width / 2)) * 2)
    y0, y1 = int(band["y0"] * height), max(int(band["y0"] * height) + 2, int(band["y1"] * height))
    fps = info.fps
    groups: list[dict] = []
    prev_sig = None
    prev_lit = None
    current: dict | None = None
    for i, frame in iter_frames(path, width=width, info=info, start=start, end=end):
        f = frame[y0:y1].astype(np.float32) / 255.0
        mask, lit = _letters(f)
        area = float(mask.mean())
        t = i / fps
        sig = _signature(mask)
        has_text = area > 0.012
        if not has_text:
            if current is not None:
                current["end"] = round(t, 6)
                current = None
            prev_sig = None
            prev_lit = None
            continue
        new_group = current is None or prev_sig is None or float(np.abs(sig - prev_sig).mean()) > 0.08
        if new_group:
            if current is not None:
                current["end"] = round(t, 6)
            current = {"start": round(t, 6), "start_frame": i, "end": None, "highlights": []}
            groups.append(current)
            prev_lit = None
        # the lit word: its horizontal span and colour
        if lit.sum() > 0.004 * lit.size:
            xs = np.flatnonzero(lit.any(axis=0))
            span = (round(xs.min() / lit.shape[1], 3), round((xs.max() + 1) / lit.shape[1], 3))
            colour = np.median(f[lit], axis=0) * 255
            hexc = "#%02x%02x%02x" % tuple(int(c) for c in colour)
            # a new lit word = its centre moves; a pop-in only grows the span around the same centre
            moved = prev_lit is None or abs((span[0] + span[1]) - (prev_lit[0] + prev_lit[1])) / 2 > 0.06
            if moved:
                h = {"time": round(t, 6), "frame": i, "x0": span[0], "x1": span[1], "colour": hexc}
                # A bright, saturated background (fire, a sunset, a coloured set) behind the band can pass for the lit
                # word: flag the colour so summaries can leave it out.
                _, sat, val = _hsv(f)
                bg = ~_dilate(mask | (val < 0.2), 2) & (val > 0.3)
                if bg.mean() > 0.05 and float(sat[bg].mean()) > 0.35:
                    h["colour_uncertain"] = True
                current["highlights"].append(h)
            prev_lit = span
        elif prev_lit is not None:
            current["highlights"].append({"time": round(t, 6), "frame": i, "x0": None, "x1": None, "colour": None})
            prev_lit = None
        prev_sig = sig  # frame to frame: a pop-in splits into short pieces that are folded back below
    if current is not None and current["end"] is None:
        current["end"] = round(end if end is not None else info.duration, 6)
    # A pop-in's first frames (scale or fade) read as their own group: fold a group shorter than 0.25 s into the
    # group that follows it directly, and drop the rest of the flicker.
    merged: list[dict] = []
    for g in groups:
        if merged and (merged[-1]["end"] - merged[-1]["start"]) < 0.25 and abs(merged[-1]["end"] - g["start"]) < 1.5 / fps:
            g = {**g, "start": merged[-1]["start"], "start_frame": merged[-1]["start_frame"],
                 "highlights": merged[-1]["highlights"] + g["highlights"]}
            merged[-1] = g
        else:
            merged.append(g)
    groups = [g for g in merged if (g["end"] - g["start"]) * fps >= 3]
    if crops is not None:
        crops.mkdir(parents=True, exist_ok=True)
        # one crop per group, from its middle frame
        mids = {int(((g["start"] + g["end"]) / 2) * fps): n for n, g in enumerate(groups, 1)}
        for i, frame in iter_frames(path, width=width, info=info, start=start, end=end):
            if i in mids:
                n = mids[i]
                name = f"{prefix}{n:03d}_{groups[n - 1]['start']:07.3f}.png"
                Image.fromarray(frame[y0:y1]).save(crops / name)
                groups[n - 1]["crop"] = f"captions/{name}"
    for g in groups:
        g["band"] = {"y0": band["y0"], "y1": band["y1"]}
    return {"band": band, "groups": groups}


def ocr(groups: list[dict], root: Path) -> bool:
    """Fill `text` from the crops with RapidOCR when it is installed."""
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception:
        return False
    engine = RapidOCR()
    for g in groups:
        if "crop" not in g:
            continue
        result, _ = engine(str(root / g["crop"]))
        if result:
            g["text"] = " ".join(r[1] for r in sorted(result, key=lambda r: r[0][0][0]))
    return True
