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


def find_band(path: str | Path, info: Probe, *, sample_fps: float = 4.0, width: int = 160) -> dict | None:
    """The horizontal band where text comes and goes most. None when nothing looks like captions."""
    # at most ~240 samples, so long videos cost the same memory as short ones
    sample_fps = min(sample_fps, 240 / max(info.duration, 1e-3))
    frames = decode(path, width=width, fps=sample_fps, info=info).astype(np.float32) / 255.0
    if len(frames) < 4:
        return None
    gray = frames @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    grad = np.abs(np.diff(gray, axis=2))[:, :, :]
    ink = _text_mask(frames)[:, :, 1:]
    strong = (grad > 0.25) & ink  # ink next to a strong edge: letters with an outline or on a dark ground
    rows = strong.mean(axis=2)  # (T, H)
    # Caption rows have dense ink that changes over time; static titles and UI have dense ink that does not.
    score = rows.mean(axis=0) * rows.std(axis=0)
    score = np.convolve(score, np.ones(3) / 3, mode="same")
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
    lo, hi = max(0, lo - pad), min(h - 1, hi + pad)
    present = (rows[:, lo : hi + 1].mean(axis=1) > 0.01).mean()
    return {
        "y0": round(lo / h, 4),
        "y1": round((hi + 1) / h, 4),
        "present_share": round(float(present), 3),
        "confidence": "high" if present > 0.3 and (hi - lo) / h < 0.2 else "low",
    }


def _signature(mask: np.ndarray, cols: int = 48, rows: int = 6) -> np.ndarray:
    h, w = mask.shape
    m = mask[: h - h % rows, : w - w % cols]
    return m.reshape(rows, m.shape[0] // rows, cols, m.shape[1] // cols).mean(axis=(1, 3))


def track(path: str | Path, info: Probe, band: dict, *, width: int = 360, crops: Path | None = None) -> dict:
    """Frame-accurate caption events inside the band."""
    height = max(2, int(round(info.height * width / info.width / 2)) * 2)
    y0, y1 = int(band["y0"] * height), max(int(band["y0"] * height) + 2, int(band["y1"] * height))
    fps = info.fps
    groups: list[dict] = []
    prev_sig = None
    prev_lit = None
    current: dict | None = None
    for i, frame in iter_frames(path, width=width, info=info):
        f = frame[y0:y1].astype(np.float32) / 255.0
        mask = _text_mask(f)
        area = float(mask.mean())
        hue, sat, val = _hsv(f)
        lit = (val > 0.55) & (sat > 0.45)
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
            colour = f[lit].mean(axis=0) * 255
            hexc = "#%02x%02x%02x" % tuple(int(c) for c in colour)
            if prev_lit is None or abs(span[0] - prev_lit[0]) > 0.04 or abs(span[1] - prev_lit[1]) > 0.04:
                current["highlights"].append({"time": round(t, 6), "frame": i, "x0": span[0], "x1": span[1], "colour": hexc})
            prev_lit = span
        elif prev_lit is not None:
            current["highlights"].append({"time": round(t, 6), "frame": i, "x0": None, "x1": None, "colour": None})
            prev_lit = None
        prev_sig = sig if new_group or prev_sig is None else 0.8 * prev_sig + 0.2 * sig
    if current is not None and current["end"] is None:
        current["end"] = round(info.duration, 6)
    # Drop flicker: groups shorter than 3 frames are usually a transition or a pop-in overshoot.
    groups = [g for g in groups if (g["end"] - g["start"]) * fps >= 3]
    if crops is not None:
        crops.mkdir(parents=True, exist_ok=True)
        # one crop per group, from its middle frame
        mids = {int(((g["start"] + g["end"]) / 2) * fps): n for n, g in enumerate(groups, 1)}
        for i, frame in iter_frames(path, width=width, info=info):
            if i in mids:
                n = mids[i]
                name = f"{n:03d}_{groups[n - 1]['start']:07.3f}.png"
                Image.fromarray(frame[y0:y1]).save(crops / name)
                groups[n - 1]["crop"] = f"captions/{name}"
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
