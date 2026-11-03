"""ffmpeg and ffprobe access: finding the binaries, probing, decoding frames into numpy."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np


class MediaError(RuntimeError):
    pass


def _find(name: str) -> str:
    env = os.environ.get(name.upper())
    if env:
        if Path(env).is_file():
            return env
        raise MediaError(f"{name.upper()}={env} does not exist")
    found = shutil.which(name)
    if found:
        return found
    raise MediaError(
        f"{name} not found. Install FFmpeg (https://ffmpeg.org/download.html) or set {name.upper()} to the binary."
    )


def ffmpeg() -> str:
    return _find("ffmpeg")


def ffprobe() -> str:
    return _find("ffprobe")


def run(args: list[str], *, capture: bool = True, cwd: str | Path | None = None) -> subprocess.CompletedProcess:
    proc = subprocess.run(args, capture_output=capture, text=True, cwd=cwd)
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-5:]
        raise MediaError(f"{Path(args[0]).name} failed: " + " | ".join(tail))
    return proc


@dataclass
class Probe:
    path: str
    duration: float
    width: int
    height: int
    fps: float
    fps_text: str
    frames: int
    has_audio: bool
    rotation: int

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "duration": round(self.duration, 6),
            "width": self.width,
            "height": self.height,
            "fps": round(self.fps, 6),
            "fps_text": self.fps_text,
            "frames": self.frames,
            "has_audio": self.has_audio,
            "rotation": self.rotation,
        }


def probe(path: str | Path) -> Probe:
    path = str(path)
    if not Path(path).is_file():
        raise MediaError(f"no such file: {path}")
    out = run(
        [ffprobe(), "-v", "error", "-show_streams", "-show_format", "-of", "json", path]
    ).stdout
    data = json.loads(out)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise MediaError(f"{path} has no video stream")
    rate = video.get("avg_frame_rate") or video.get("r_frame_rate") or "30/1"
    if rate in ("0/0", "0"):
        rate = video.get("r_frame_rate", "30/1")
    fps = float(Fraction(rate))
    duration = float(video.get("duration") or data.get("format", {}).get("duration") or 0)
    rotation = 0
    for side in video.get("side_data_list", []) or []:
        if "rotation" in side:
            rotation = int(side["rotation"])
    if "rotate" in (video.get("tags") or {}):
        rotation = int(video["tags"]["rotate"])
    width, height = int(video["width"]), int(video["height"])
    if abs(rotation) in (90, 270):
        width, height = height, width
    frames = int(video.get("nb_frames") or 0) or int(round(duration * fps))
    has_audio = any(s.get("codec_type") == "audio" for s in data.get("streams", []))
    fps_text = rate if Fraction(rate).denominator != 1 else str(Fraction(rate).numerator)
    return Probe(path, duration, width, height, fps, fps_text, frames, has_audio, rotation)


def decode(
    path: str | Path,
    *,
    width: int,
    height: int | None = None,
    fps: float | None = None,
    start: float | None = None,
    end: float | None = None,
    gray: bool = False,
    info: Probe | None = None,
) -> np.ndarray:
    """Decode a video into an array of frames (N, H, W[, 3]) at a small size.

    Frames come out at the source rate unless `fps` is given. Height keeps the aspect ratio when omitted.
    """
    info = info or probe(path)
    if height is None:
        height = max(2, int(round(info.height * width / info.width / 2)) * 2)
    filters = []
    if fps:
        filters.append(f"fps={fps}")
    filters.append(f"scale={width}:{height}:flags=area")
    args = [ffmpeg(), "-v", "error"]
    if start:
        args += ["-ss", f"{start:.6f}"]
    args += ["-i", str(path)]
    if end is not None:
        args += ["-t", f"{max(0.0, end - (start or 0)):.6f}"]
    pix = "gray" if gray else "rgb24"
    args += ["-vf", ",".join(filters), "-an", "-f", "rawvideo", "-pix_fmt", pix, "-"]
    proc = subprocess.run(args, capture_output=True)
    if proc.returncode != 0:
        raise MediaError("ffmpeg decode failed: " + proc.stderr.decode(errors="replace")[-400:])
    channels = 1 if gray else 3
    frame_size = width * height * channels
    count = len(proc.stdout) // frame_size
    arr = np.frombuffer(proc.stdout[: count * frame_size], dtype=np.uint8)
    shape = (count, height, width) if gray else (count, height, width, 3)
    return arr.reshape(shape)


def iter_frames(path: str | Path, *, width: int, info: Probe | None = None, gray: bool = False):
    """Stream frames at the source rate as (index, array), without holding the whole video in memory."""
    info = info or probe(path)
    height = max(2, int(round(info.height * width / info.width / 2)) * 2)
    pix = "gray" if gray else "rgb24"
    channels = 1 if gray else 3
    size = width * height * channels
    proc = subprocess.Popen(
        [ffmpeg(), "-v", "error", "-i", str(path), "-vf", f"scale={width}:{height}:flags=area", "-an",
         "-f", "rawvideo", "-pix_fmt", pix, "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    assert proc.stdout is not None
    index = 0
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            arr = np.frombuffer(buf, dtype=np.uint8)
            yield index, arr.reshape((height, width) if gray else (height, width, 3))
            index += 1
    finally:
        proc.stdout.close()
        proc.wait()


def frame_at(path: str | Path, t: float, out: str | Path, *, width: int | None = None) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    vf = ["-vf", f"scale={width}:-2"] if width else []
    run([ffmpeg(), "-v", "error", "-y", "-ss", f"{max(0.0, t):.6f}", "-i", str(path), "-frames:v", "1", *vf, str(out)])
    return out


def extract_audio(path: str | Path, out: str | Path, *, rate: int = 44100, mono: bool = False) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    channels = ["-ac", "1"] if mono else ["-ac", "2"]
    run([ffmpeg(), "-v", "error", "-y", "-i", str(path), "-vn", *channels, "-ar", str(rate), str(out)])
    return out


def audio_samples(path: str | Path, *, rate: int = 16000) -> np.ndarray:
    proc = subprocess.run(
        [ffmpeg(), "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(rate), "-f", "f32le", "-"],
        capture_output=True,
    )
    if proc.returncode != 0:
        return np.zeros(0, dtype=np.float32)
    return np.frombuffer(proc.stdout, dtype=np.float32)
