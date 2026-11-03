"""Sound: loudness (EBU R128), silences, onsets and tempo, and an optional word transcript."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from .media import audio_samples, ffmpeg, run


def loudness(path: str | Path) -> dict:
    proc = run([ffmpeg(), "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"])
    text = proc.stderr
    summary = text[text.rfind("Summary:") :] if "Summary:" in text else text
    def num(label: str):
        m = re.search(label + r":\s+(-?[\d.]+|-inf)", summary)
        return None if not m or m.group(1) == "-inf" else float(m.group(1))
    return {"integrated_lufs": num("I"), "range_lu": num("LRA"), "true_peak_dbfs": num("Peak")}


def silences(path: str | Path, *, noise_db: float = -35, min_len: float = 0.3) -> list[dict]:
    proc = run([ffmpeg(), "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af",
                f"silencedetect=noise={noise_db}dB:d={min_len}", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", proc.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: (-?[\d.]+)", proc.stderr)]
    out = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else None
        out.append({"start": round(max(0.0, s), 3), "end": round(e, 3) if e is not None else None})
    return out


def onsets(samples: np.ndarray, rate: int = 16000, hop: int = 320) -> tuple[np.ndarray, np.ndarray]:
    """Spectral-flux onset strength (one value per hop) and the times of its peaks."""
    if len(samples) < rate // 2:
        return np.zeros(0), np.zeros(0)
    win = 1024
    n = 1 + (len(samples) - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    frames = samples[idx] * np.hanning(win)[None, :]
    mag = np.log1p(np.abs(np.fft.rfft(frames, axis=1)))
    flux = np.maximum(0, np.diff(mag, axis=0)).sum(axis=1)
    flux = np.concatenate([[0], flux])
    flux = flux / (flux.max() + 1e-9)
    w = int(0.25 * rate / hop)
    peaks = []
    for i in range(1, len(flux) - 1):
        lo, hi = max(0, i - w), min(len(flux), i + w + 1)
        if flux[i] == flux[lo:hi].max() and flux[i] > np.median(flux[lo:hi]) + 0.1:
            peaks.append(i * hop / rate)
    return flux, np.array(peaks)


def tempo(flux: np.ndarray, rate: int = 16000, hop: int = 320) -> float | None:
    """Beats per minute from the autocorrelation of onset strength (60-200 BPM), or None if unclear."""
    if len(flux) < 200:
        return None
    x = flux - flux.mean()
    ac = np.correlate(x, x, mode="full")[len(x) - 1 :]
    fps = rate / hop
    lo, hi = int(fps * 60 / 200), int(fps * 60 / 60)
    if hi >= len(ac):
        return None
    lag = lo + int(np.argmax(ac[lo:hi]))
    strength = ac[lag] / (ac[0] + 1e-9)
    return round(60 * fps / lag, 1) if strength > 0.15 else None


def describe(path: str | Path, has_audio: bool) -> dict:
    if not has_audio:
        return {"present": False}
    samples = audio_samples(path)
    flux, peaks = onsets(samples)
    rms = float(np.sqrt(np.mean(samples**2))) if len(samples) else 0.0
    return {
        "present": True,
        "loudness": loudness(path),
        "silences": silences(path),
        "onsets": [round(float(t), 3) for t in peaks],
        "tempo_bpm": tempo(flux),
        "rms": round(rms, 4),
    }


def transcribe(path: str | Path, *, model: str = "small", language: str | None = None) -> dict | None:
    """Word timestamps with faster-whisper when installed (`pip install replicate-video[transcribe]`)."""
    try:
        from faster_whisper import WhisperModel
    except Exception:
        return None
    m = WhisperModel(model, device="cpu", compute_type="int8")
    segments, info = m.transcribe(str(path), word_timestamps=True, language=language, vad_filter=True)
    words = []
    for seg in segments:
        for w in seg.words or []:
            words.append({"text": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3), "p": round(w.probability, 3)})
    return {"language": info.language, "model": model, "words": words}
