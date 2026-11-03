"""Compare a rebuild with its reference: per-frame SSIM, the worst region per frame, cuts, duration, sound offset,
and side-by-side pairs of the worst moments and of every shot head.

The score tells you where to look first. It cannot see a wrong word or a beat in the wrong order, and it punishes
changes that were asked for; judge the pairs by eye.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import numpy as np

from .cuts import find_boundaries, measure_signals
from .media import audio_samples, decode, ffmpeg, probe, run
from .sheets import side_by_side, stamp, tile
from .audio import onsets


def ssim_per_frame(ref: str, cand: str, w: int, h: int, fps: str) -> np.ndarray:
    with tempfile.TemporaryDirectory() as tmp:
        # A relative stats path: a Windows drive colon inside a filter graph reads as an option separator.
        graph = (
            f"[0:v]fps={fps},scale={w}:{h},format=yuv420p,setsar=1[r];"
            f"[1:v]fps={fps},scale={w}:{h},format=yuv420p,setsar=1[c];"
            "[r][c]ssim=stats_file=ssim.log"
        )
        run([ffmpeg(), "-v", "error", "-i", str(Path(ref).resolve()), "-i", str(Path(cand).resolve()),
             "-lavfi", graph, "-f", "null", "-"], cwd=tmp)
        values = [float(m) for m in re.findall(r"All:([\d.]+)", (Path(tmp) / "ssim.log").read_text(encoding="utf-8"))]
    return np.array(values)


def _block_ssim(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    ma, mb = a.mean(), b.mean()
    va, vb = a.var(), b.var()
    cov = ((a - ma) * (b - mb)).mean()
    return float(((2 * ma * mb + c1) * (2 * cov + c2)) / ((ma**2 + mb**2 + c1) * (va + vb + c2)))


def worst_cells(ra: np.ndarray, ca: np.ndarray, grid=(4, 6)) -> list[dict]:
    """For each sampled frame pair, the grid cell that differs most (x, y, w, h as fractions)."""
    gx, gy = grid
    out = []
    for r, c in zip(ra, ca):
        h, w = r.shape
        worst = (2.0, 0, 0)
        for j in range(gy):
            for i in range(gx):
                ys, ye = j * h // gy, (j + 1) * h // gy
                xs, xe = i * w // gx, (i + 1) * w // gx
                s = _block_ssim(r[ys:ye, xs:xe], c[ys:ye, xs:xe])
                if s < worst[0]:
                    worst = (s, i, j)
        out.append({"ssim": round(worst[0], 4), "cell": [round(worst[1] / gx, 3), round(worst[2] / gy, 3), round(1 / gx, 3), round(1 / gy, 3)]})
    return out


def sound_offset(ref: str, cand: str, rate: int = 16000, hop: int = 320, max_s: float = 1.0) -> float | None:
    a, b = audio_samples(ref, rate=rate), audio_samples(cand, rate=rate)
    if len(a) < rate or len(b) < rate:
        return None
    fa, _ = onsets(a, rate, hop)
    fb, _ = onsets(b, rate, hop)
    n = min(len(fa), len(fb))
    fa, fb = fa[:n] - fa[:n].mean(), fb[:n] - fb[:n].mean()
    lag_max = int(max_s * rate / hop)
    best, best_lag = -1e18, 0
    for lag in range(-lag_max, lag_max + 1):
        if lag >= 0:
            v = float(np.dot(fa[lag:], fb[: n - lag]))
        else:
            v = float(np.dot(fa[: n + lag], fb[-lag:]))
        if v > best:
            best, best_lag = v, lag
    return round(best_lag * hop / rate, 3)  # > 0: the rebuild's sound is early


def match_cuts(ref_cuts: list[float], cand_cuts: list[float], tol: float) -> dict:
    missing, extra, matched = [], list(cand_cuts), []
    for t in ref_cuts:
        near = [c for c in extra if abs(c - t) <= tol]
        if near:
            c = min(near, key=lambda c: abs(c - t))
            matched.append({"reference": t, "rebuild": c, "offset_frames": None})
            extra.remove(c)
        else:
            missing.append(t)
    return {"matched": matched, "missing": missing, "extra": extra}


def compare(reference: str, rebuild: str, out_dir: str | Path, *, sample_fps: float = 2.0, worst_n: int = 8) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ri, ci = probe(reference), probe(rebuild)
    w = min(ri.width, 540)
    h = max(2, int(round(ri.height * w / ri.width / 2)) * 2)
    ssim = ssim_per_frame(reference, rebuild, w, h, ri.fps_text)

    # boundaries on both sides
    rb = [b for b in find_boundaries(measure_signals(reference, info=ri)) if b.kind == "cut"]
    cb = [b for b in find_boundaries(measure_signals(rebuild, info=ci)) if b.kind == "cut"]
    cuts = match_cuts([b.time for b in rb], [b.time for b in cb], tol=2.5 / ri.fps)
    for m in cuts["matched"]:
        m["offset_frames"] = int(round((m["rebuild"] - m["reference"]) * ri.fps))

    # regions, sampled
    small_w = 180
    small_h = max(2, int(round(ri.height * small_w / ri.width / 2)) * 2)
    rs = decode(reference, width=small_w, height=small_h, fps=sample_fps, gray=True, info=ri)
    cs = decode(rebuild, width=small_w, height=small_h, fps=sample_fps, gray=True, info=ci)
    k = min(len(rs), len(cs))
    cells = worst_cells(rs[:k], cs[:k])

    # stretches where the rebuild is far off for a while (missing content, wrong scene)
    low = ssim < (np.median(ssim) - 0.15) if len(ssim) else np.zeros(0, bool)
    stretches, start = [], None
    for i, flag in enumerate(low):
        if flag and start is None:
            start = i
        if (not flag or i == len(low) - 1) and start is not None:
            end = i if not flag else i + 1
            if (end - start) / ri.fps >= 0.5:
                stretches.append({"start": round(start / ri.fps, 3), "end": round(end / ri.fps, 3)})
            start = None

    # worst moments, at least 0.5 s apart
    order = np.argsort(ssim)
    picks: list[int] = []
    for i in order:
        if all(abs(i - j) > ri.fps * 0.5 for j in picks):
            picks.append(int(i))
        if len(picks) >= worst_n:
            break
    picks.sort()
    pair_w = 240
    pair_h = max(2, int(round(ri.height * pair_w / ri.width / 2)) * 2)
    images = []
    for i in picks:
        t = i / ri.fps
        a = decode(reference, width=pair_w, height=pair_h, start=t, end=t + 0.5 / ri.fps, info=ri)
        b = decode(rebuild, width=pair_w, height=pair_h, start=t, end=t + 0.5 / ci.fps, info=ci)
        if len(a) and len(b):
            images.append(side_by_side(a[0], b[0], f"{stamp(t)} ssim {ssim[i]:.3f}"))
    if images:
        tile(images, 4 if ri.width < ri.height else 2, gap=6).save(out_dir / "worst.jpg", quality=88)

    heads = []
    for n, s in enumerate([0.0] + [b.time for b in rb], 1):
        t = s + 0.3
        a = decode(reference, width=pair_w, height=pair_h, start=t, end=t + 0.5 / ri.fps, info=ri)
        b = decode(rebuild, width=pair_w, height=pair_h, start=t, end=t + 0.5 / ci.fps, info=ci)
        if len(a) and len(b):
            heads.append(side_by_side(a[0], b[0], f"shot {n} {stamp(t)}"))
    if heads:
        tile(heads, 4 if ri.width < ri.height else 2, gap=6).save(out_dir / "shots.jpg", quality=88)

    result = {
        "reference": ri.to_dict(),
        "rebuild": ci.to_dict(),
        "size_matches": (ri.width, ri.height) == (ci.width, ci.height),
        "fps_matches": abs(ri.fps - ci.fps) < 0.01,
        "duration_delta": round(ci.duration - ri.duration, 3),
        "ssim": {
            "mean": round(float(ssim.mean()), 4) if len(ssim) else None,
            "p05": round(float(np.percentile(ssim, 5)), 4) if len(ssim) else None,
            "min": round(float(ssim.min()), 4) if len(ssim) else None,
            "per_second": [round(float(ssim[int(i * ri.fps) : int((i + 1) * ri.fps)].mean()), 4)
                           for i in range(int(np.ceil(len(ssim) / ri.fps)))],
        },
        "worst_cell_p05": round(float(np.percentile([c["ssim"] for c in cells], 5)), 4) if cells else None,
        "worst_moments": [{"time": round(i / ri.fps, 3), "ssim": round(float(ssim[i]), 4),
                           "cell": cells[min(len(cells) - 1, int(i / ri.fps * sample_fps))]["cell"] if cells else None}
                          for i in picks],
        "low_stretches": stretches,
        "cuts": cuts,
        "sound_offset_s": sound_offset(reference, rebuild) if ri.has_audio and ci.has_audio else None,
        "images": {"worst": "worst.jpg" if images else None, "shots": "shots.jpg" if heads else None},
    }
    (out_dir / "diff.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
