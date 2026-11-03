"""Shot boundaries from per-frame signals.

Three independent detectors vote on every frame:

- `pixels`: mean absolute difference between consecutive frames (catches cuts between similar palettes),
- `histogram`: colour-histogram distance (catches cuts that keep the layout but change the picture),
- `edges`: change in where the edges are (catches cuts between scenes of the same colour).

A frame two or more detectors agree on is a `cut`. A frame only one detector flags is a `candidate`: often a cut
hidden under a fast move, sometimes a fast push-in or a big element arriving. A brightness spike that comes back
within a few frames is a `flash`. Candidates and flashes are evidence to look at, not facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .media import Probe, iter_frames, probe


@dataclass
class Signals:
    fps: float
    luma: np.ndarray  # mean luma per frame, 0..1
    pixels: np.ndarray  # diff to previous frame
    histogram: np.ndarray
    edges: np.ndarray
    saturation: np.ndarray

    def to_dict(self) -> dict:
        r = lambda a: [round(float(x), 4) for x in a]  # noqa: E731
        return {
            "fps": self.fps,
            "luma": r(self.luma),
            "pixels": r(self.pixels),
            "histogram": r(self.histogram),
            "edges": r(self.edges),
            "saturation": r(self.saturation),
        }


def _hist(frame: np.ndarray) -> np.ndarray:
    q = (frame // 32).astype(np.int32)  # 8 levels per channel
    idx = q[..., 0] * 64 + q[..., 1] * 8 + q[..., 2]
    h = np.bincount(idx.ravel(), minlength=512).astype(np.float32)
    return h / max(1.0, h.sum())


def _edges(gray: np.ndarray) -> np.ndarray:
    gx = np.abs(np.diff(gray, axis=1))[:-1, :]
    gy = np.abs(np.diff(gray, axis=0))[:, :-1]
    return (gx + gy) > 0.12


def measure_signals(path: str | Path, *, info: Probe | None = None, width: int = 96) -> Signals:
    info = info or probe(path)
    luma, pixels, hist_d, edge_d, sat = [], [], [], [], []
    prev = prev_h = prev_e = None
    for _, frame in iter_frames(path, width=width, info=info):
        f = frame.astype(np.float32) / 255.0
        gray = f @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
        h = _hist(frame)
        e = _edges(gray)
        mx, mn = f.max(axis=2), f.min(axis=2)
        sat.append(float(np.mean((mx - mn) / np.maximum(mx, 1e-3))))
        luma.append(float(gray.mean()))
        if prev is None:
            pixels.append(0.0)
            hist_d.append(0.0)
            edge_d.append(0.0)
        else:
            pixels.append(float(np.mean(np.abs(gray - prev))))
            hist_d.append(float(0.5 * np.abs(h - prev_h).sum()))
            union = np.logical_or(e, prev_e).sum()
            edge_d.append(float(np.logical_xor(e, prev_e).sum() / union) if union else 0.0)
        prev, prev_h, prev_e = gray, h, e
    return Signals(
        info.fps,
        np.array(luma),
        np.array(pixels),
        np.array(hist_d),
        np.array(edge_d),
        np.array(sat),
    )


def _peaks(x: np.ndarray, *, floor: float, k: float, window: int) -> np.ndarray:
    """Frames where x stands out from its neighbourhood: above floor, above median + k * MAD, a local maximum."""
    n = len(x)
    hits = np.zeros(n, dtype=bool)
    for i in range(2, n):  # frame 1 differs from frame 0 in many encodes (fade-in, keyframe): skip it
        lo, hi = max(0, i - window), min(n, i + window + 1)
        neigh = np.concatenate([x[lo:i], x[i + 1 : hi]])
        if neigh.size == 0:
            continue
        med = float(np.median(neigh))
        mad = float(np.median(np.abs(neigh - med))) + 1e-4
        local_max = x[i] >= x[max(0, i - 2) : min(n, i + 3)].max()
        hits[i] = x[i] > floor and x[i] > med + k * mad * 1.4826 and x[i] > 2.5 * med and local_max
    return hits


@dataclass
class Boundary:
    frame: int
    time: float
    kind: str  # cut | candidate | flash | transition
    detectors: list[str] = field(default_factory=list)
    scores: dict = field(default_factory=dict)
    end_frame: int | None = None  # transitions only: last frame of the window

    def to_dict(self) -> dict:
        d = {
            "frame": self.frame,
            "time": round(self.time, 6),
            "kind": self.kind,
            "detectors": self.detectors,
            "scores": {k: round(v, 4) for k, v in self.scores.items()},
        }
        if self.end_frame is not None:
            d["end_frame"] = self.end_frame
        return d


DETECTORS = {
    # name: (floor, k)
    "pixels": (0.035, 6.0),
    "histogram": (0.18, 6.0),
    "edges": (0.45, 5.0),
}


def find_boundaries(sig: Signals, *, sensitivity: float = 1.0) -> list[Boundary]:
    window = max(5, int(round(sig.fps)))
    votes: dict[int, list[str]] = {}
    for name, (floor, k) in DETECTORS.items():
        x = getattr(sig, name)
        hits = _peaks(x, floor=floor / sensitivity, k=k / sensitivity, window=window)
        for i in np.flatnonzero(hits):
            # merge votes within one frame of each other
            key = next((j for j in (i - 1, i, i + 1) if j in votes), int(i))
            votes.setdefault(key, []).append(name)
    out: list[Boundary] = []
    for i in sorted(votes):
        names = sorted(set(votes[i]))
        scores = {n: float(getattr(sig, n)[i]) for n in DETECTORS}
        kind = "cut" if len(names) >= 2 else "candidate"
        # A flash: brightness jumps and comes back to where it was within ~0.3 s, and the picture before
        # and after the spike is the same.
        span = max(2, int(round(sig.fps * 0.3)))
        before = sig.luma[max(0, i - 2)]
        peak = float(np.max(sig.luma[i : i + span])) if i < len(sig.luma) else before
        after = sig.luma[min(len(sig.luma) - 1, i + span)]
        if peak - before > 0.12 and abs(after - before) < 0.05:
            kind = "flash"
        # The frame where a flash ends is not a new shot when the picture came back.
        if out and out[-1].kind == "flash" and i - out[-1].frame <= span and abs(sig.luma[i] - sig.luma[max(0, out[-1].frame - 2)]) < 0.05:
            continue
        out.append(Boundary(int(i), i / sig.fps, kind, names, scores))
    return _merge_transitions(out, sig.fps)


def _merge_transitions(found: list[Boundary], fps: float, gap: float = 0.35, min_count: int = 3) -> list[Boundary]:
    """Three or more boundaries close together are one transition (a dissolve, a fade through black, a glitch, a
    whip), not several cuts. Keep it as one window to look at."""
    out: list[Boundary] = []
    run: list[Boundary] = []

    def flush():
        if len(run) >= min_count:
            names = sorted({n for b in run for n in b.detectors})
            out.append(Boundary(run[0].frame, run[0].time, "transition", names, run[0].scores, end_frame=run[-1].frame))
        else:
            out.extend(run)

    for b in found:
        if run and (b.frame - run[-1].frame) / fps > gap:
            flush()
            run = []
        run.append(b)
    if run:
        flush()
    return out


def shots_from(boundaries: list[Boundary], *, frames: int, fps: float, include_candidates: bool = False) -> list[dict]:
    kinds = {"cut", "transition", "candidate"} if include_candidates else {"cut", "transition"}
    starts = [0] + [b.frame for b in boundaries if b.kind in kinds and b.frame > 0]
    starts = sorted(set(starts))
    shots = []
    for n, s in enumerate(starts):
        e = starts[n + 1] if n + 1 < len(starts) else frames
        shots.append(
            {
                "index": n + 1,
                "start_frame": s,
                "end_frame": e,
                "start": round(s / fps, 6),
                "end": round(e / fps, 6),
                "duration": round((e - s) / fps, 6),
            }
        )
    return shots
