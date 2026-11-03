"""Per-shot measurements: palette, brightness, motion energy and camera (zoom, pan, rotation, ease)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .cuts import Signals
from .media import Probe, decode

try:  # OpenCV is a dependency, but keep the rest usable if a platform wheel is missing.
    import cv2
except Exception:  # pragma: no cover
    cv2 = None


def _hex(rgb: np.ndarray) -> str:
    r, g, b = (int(round(float(c))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def palette(pixels: np.ndarray, k: int = 5, iters: int = 12, seed: int = 0) -> list[dict]:
    """k-means over RGB pixels (N, 3). Returns colours sorted by share."""
    px = pixels.reshape(-1, 3).astype(np.float32)
    if len(px) > 20000:
        px = px[np.random.default_rng(seed).choice(len(px), 20000, replace=False)]
    k = min(k, len(np.unique(px, axis=0)))
    if k == 0:
        return []
    rng = np.random.default_rng(seed)
    centres = px[rng.choice(len(px), k, replace=False)]
    for _ in range(iters):
        d = ((px[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2)
        label = d.argmin(axis=1)
        for j in range(k):
            sel = px[label == j]
            if len(sel):
                centres[j] = sel.mean(axis=0)
    counts = np.bincount(label, minlength=k)
    order = np.argsort(-counts)
    return [{"hex": _hex(centres[j]), "share": round(float(counts[j] / len(px)), 3)} for j in order if counts[j]]


def _ease(progress: np.ndarray) -> str:
    """Name the shape of a 0..1 progress curve sampled evenly in time: the closest of linear, ease-in,
    ease-out and ease-in-out (quadratic and cubic), or 'unknown' when nothing fits."""
    if len(progress) < 4 or not np.isfinite(progress).all():
        return "unknown"
    p = np.clip(progress, 0, 1)
    t = np.linspace(0, 1, len(p))
    shapes = {
        "linear": t,
        "ease-in": t**2,
        "ease-in (strong)": t**3,
        "ease-out": 1 - (1 - t) ** 2,
        "ease-out (strong)": 1 - (1 - t) ** 3,
        "ease-in-out": t * t * (3 - 2 * t),
    }
    errs = {k: float(np.sqrt(np.mean((p - v) ** 2))) for k, v in shapes.items()}
    best = min(errs, key=errs.get)
    return best if errs[best] < 0.12 else "unknown"


def _pair_transform(a: np.ndarray, b: np.ndarray, mask: np.ndarray | None):
    """Similarity transform from frame a to b: (scale, dx, dy, rotation_deg), dx/dy in pixels.

    Corners are tracked with pyramidal Lucas-Kanade (fast and sub-pixel for the small steps between consecutive
    frames), then a RANSAC similarity fit keeps the dominant motion.
    """
    pts = cv2.goodFeaturesToTrack(a, maxCorners=400, qualityLevel=0.01, minDistance=6, mask=mask)
    if pts is None or len(pts) < 12:
        return None
    nxt, status, _ = cv2.calcOpticalFlowPyrLK(a, b, pts, None, winSize=(21, 21), maxLevel=3)
    back, status_b, _ = cv2.calcOpticalFlowPyrLK(b, a, nxt, None, winSize=(21, 21), maxLevel=3)
    good = (status.ravel() == 1) & (status_b.ravel() == 1) & (np.linalg.norm(back - pts, axis=2).ravel() < 1.0)
    if good.sum() < 12:
        return None
    m, inliers = cv2.estimateAffinePartial2D(pts[good], nxt[good], method=cv2.RANSAC, ransacReprojThreshold=1.5)
    if m is None or inliers is None or inliers.sum() < 10:
        return None
    scale = float(np.hypot(m[0, 0], m[1, 0]))
    rot = float(np.degrees(np.arctan2(m[1, 0], m[0, 0])))
    h, w = a.shape
    moved = m @ np.array([w / 2, h / 2, 1.0])
    agree = float(inliers.sum() / max(1, good.sum()))  # share of tracked points that follow the same move
    return scale, float(moved[0] - w / 2), float(moved[1] - h / 2), rot, agree


def _overlay_mask(frames: np.ndarray, bands: list[dict] | None) -> np.ndarray:
    """255 where features may be tracked: not the caption band, not overlays that stay still while the
    picture under them moves (badges, logos, UI)."""
    h, w = frames.shape[1:]
    mask = np.full((h, w), 255, np.uint8)
    for band in bands or []:
        mask[max(0, int(band["y0"] * h) - 2) : min(h, int(band["y1"] * h) + 2)] = 0
    if len(frames) >= 4:
        std = frames[:: max(1, len(frames) // 40)].astype(np.float32).std(axis=0)
        if float(np.median(std)) > 3.0:
            still = (std < 1.0).astype(np.uint8)
            still = cv2.dilate(still, np.ones((9, 9), np.uint8))
            mask[still > 0] = 0
    return mask


def _segments(t: np.ndarray, v: np.ndarray, *, thresh: float, min_pairs: int = 3) -> list[tuple[int, int]]:
    """Runs where |v| (smoothed) stays above thresh with one sign."""
    if len(v) < min_pairs:
        return []
    k = np.convolve(v, np.ones(3) / 3, mode="same")
    out, start, sign = [], None, 0
    for i, x in enumerate(k):
        s = 1 if x > thresh else -1 if x < -thresh else 0
        if s and start is None:
            start, sign = i, s
        elif start is not None and s != sign:
            if i - start >= min_pairs:
                out.append((start, i))
            start, sign = (i, s) if s else (None, 0)
    if start is not None and len(k) - start >= min_pairs:
        out.append((start, len(k)))
    # Grow each run while the move continues at a slower speed, so the ease includes its slow start and landing.
    grown = []
    for s, e in out:
        sign = np.sign(k[s:e].sum())
        peak = float(np.abs(k[s:e]).max())
        while s > 0 and np.sign(k[s - 1]) == sign and abs(k[s - 1]) > 0.12 * peak:
            s -= 1
        while e < len(k) and np.sign(k[e]) == sign and abs(k[e]) > 0.12 * peak:
            e += 1
        if grown and s <= grown[-1][1]:
            grown[-1] = (grown[-1][0], max(e, grown[-1][1]))
        else:
            grown.append((s, e))
    return grown


def camera(path: str | Path, info: Probe, shots: list[dict], *, bands: list[dict] | None = None,
           sample_fps: float | None = None, width: int = 320) -> list[dict]:
    """Estimate a 2D camera per shot from feature matches between consecutive frames.

    Returns the total move per shot and a list of `moves`: stretches where the picture zooms or slides, with
    their start, end, amount and ease. The numbers describe how the picture moves on screen (a push-in = zoom > 1).
    They cannot tell a camera move from the whole scene moving, and flicker (fire, particles) adds noise: check the
    frames.
    """
    if cv2 is None:
        return [{"available": False} for _ in shots]
    rate = sample_fps or min(info.fps, 30.0)
    out = []
    for shot in shots:
        # one shot at a time keeps memory flat on long videos; skip the first and last frame (cut blur)
        sel = decode(path, width=width, fps=rate, gray=True, info=info,
                     start=shot["start"] + 1 / info.fps, end=max(shot["start"] + 1 / info.fps, shot["end"] - 1 / info.fps))
        live = [b for b in bands or [] if b.get("from") is None or (b["from"] < shot["end"] and b["to"] > shot["start"])]
        mask = _overlay_mask(sel, live)
        steps, misses = [], 0
        for fa, fb in zip(sel, sel[1:]):
            t = _pair_transform(fa, fb, mask)
            if t is None:
                misses += 1
                t = (1.0, 0.0, 0.0, 0.0, 0.0)
            steps.append(t)
        st = np.array(steps) if steps else np.zeros((0, 5))
        logz = np.log(np.maximum(st[:, 0], 1e-3)) if len(st) else np.zeros(0)
        dx = st[:, 1] / width if len(st) else np.zeros(0)
        dy = st[:, 2] / sel.shape[1] if len(st) else np.zeros(0)
        total_zoom = float(np.exp(logz.sum())) if len(st) else 1.0
        entry = {
            "zoom": round(total_zoom, 3),
            "pan_x": round(float(dx.sum()), 3),
            "pan_y": round(float(dy.sum()), 3),
            "rotation_deg": round(float(st[:, 3].sum()), 2) if len(st) else 0.0,
            "pairs": len(steps),
            "unmatched_pairs": misses,
            "moves": [],
        }
        times = shot["start"] + np.arange(len(steps)) / rate
        per_pair = 30.0 / rate  # thresholds are per 1/30 s
        for kind, v, thresh in (("zoom", logz, 0.0012), ("pan_x", dx, 0.0015), ("pan_y", dy, 0.0015)):
            for s, e in _segments(times, v, thresh=thresh * per_pair):
                amount = float(v[s:e].sum())
                if kind == "zoom" and abs(amount) < 0.02 or kind != "zoom" and abs(amount) < 0.02:
                    continue
                cum = np.concatenate([[0], np.cumsum(v[s:e])])
                progress = cum / cum[-1] if abs(cum[-1]) > 1e-9 else cum
                move = {
                    "zoom": "push-in" if amount > 0 else "pull-out",
                    "pan_x": "pan right" if amount < 0 else "pan left",
                    "pan_y": "tilt down" if amount < 0 else "tilt up",
                }[kind]
                agree = float(st[s:e, 4].mean())
                mv = {
                    "move": move,
                    "start": round(float(times[s]), 3),
                    "end": round(float(times[min(e, len(times)) - 1] + 1 / rate), 3),
                    "amount": round(float(np.exp(amount)), 3) if kind == "zoom" else round(abs(amount), 3),
                    "ease": _ease(progress),
                    "agreement": round(agree, 2),
                }
                # Few points agreeing = part of the picture moves on its own (flicker, a character walking at the
                # lens); a huge zoom in a short time is more often that than a camera move.
                if agree < 0.6 or (kind == "zoom" and abs(amount) > np.log(1.8) and mv["end"] - mv["start"] < 3):
                    mv["confidence"] = "low"
                entry["moves"].append(mv)
        entry["moves"].sort(key=lambda m: m["start"])
        entry["move"] = "static" if not entry["moves"] else max(
            entry["moves"], key=lambda m: abs(np.log(m["amount"])) * 2 if m["move"] in ("push-in", "pull-out") else m["amount"]
        )["move"]
        if steps and misses / len(steps) > 0.5:
            entry["confidence"] = "low"
        out.append(entry)
    return out


def describe(path: str | Path, info: Probe, sig: Signals, shots: list[dict], *, bands: list[dict] | None = None) -> list[dict]:
    thumbs = decode(path, width=64, fps=4, info=info)
    cams = camera(path, info, shots, bands=bands)
    out = []
    for shot, cam in zip(shots, cams):
        a, b = shot["start_frame"], shot["end_frame"]
        sel = thumbs[int(shot["start"] * 4) : max(int(shot["start"] * 4) + 1, int(shot["end"] * 4))]
        luma = sig.luma[a:b]
        out.append(
            {
                **shot,
                "luma": {
                    "mean": round(float(luma.mean()), 3) if len(luma) else None,
                    "min": round(float(luma.min()), 3) if len(luma) else None,
                    "max": round(float(luma.max()), 3) if len(luma) else None,
                },
                "saturation": round(float(sig.saturation[a:b].mean()), 3) if b > a else None,
                "motion": round(float(sig.pixels[a + 1 : b].mean()), 4) if b - a > 1 else 0.0,
                "palette": palette(sel) if len(sel) else [],
                "camera": cam,
            }
        )
    return out
