import subprocess

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from replicate_video.media import ffmpeg

W, H, FPS = 180, 320, 30


def encode(frames, path, fps=FPS, audio=False):
    """Write an iterable of HxWx3 uint8 frames to an H.264 MP4 (optionally with a 440 Hz beep track)."""
    frames = list(frames)
    h, w = frames[0].shape[:2]
    args = [ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={len(frames) / fps}"]
    args += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "12", "-pix_fmt", "yuv420p", "-g", "1"]
    if audio:
        args += ["-c:a", "aac", "-shortest"]
    args.append(str(path))
    subprocess.run(args, input=b"".join(f.tobytes() for f in frames), check=True)
    return path


def scene(seed, w=W, h=H):
    """A textured still: blocks of colour with edges, so trackers and detectors have something to hold."""
    rng = np.random.default_rng(seed)
    img = Image.new("RGB", (w, h), tuple(int(x) for x in rng.integers(0, 255, 3)))
    d = ImageDraw.Draw(img)
    for _ in range(40):
        x, y = rng.integers(0, w), rng.integers(0, h)
        s = rng.integers(6, 40)
        d.rectangle((x, y, x + s, y + s), fill=tuple(int(c) for c in rng.integers(0, 255, 3)))
    return np.array(img)


def zoomed(img, z):
    h, w = img.shape[:2]
    big = Image.fromarray(img).resize((int(w * z), int(h * z)), Image.BILINEAR)
    x, y = (big.width - w) // 2, (big.height - h) // 2
    return np.array(big.crop((x, y, x + w, y + h)))


def font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


@pytest.fixture(scope="session")
def clips(tmp_path_factory):
    root = tmp_path_factory.mktemp("clips")
    out = {}
    # three shots of 1.5 s each, then a flash inside the third
    a, b, c = scene(1), scene(2), scene(3)
    frames = [a] * 45 + [b] * 45 + [c] * 20 + [np.full_like(c, 250)] * 3 + [c] * 22
    out["cuts"] = encode(frames, root / "cuts.mp4", audio=True)
    # a 1.2 s push-in on one picture, eased in-out, with still holds either side
    base = scene(7)
    push = []
    for i in range(60):
        t = min(1.0, max(0.0, (i - 12) / 36))
        e = t * t * (3 - 2 * t)
        push.append(zoomed(base, 1 + 0.4 * e))
    out["push"] = encode(push, root / "push.mp4")
    # captions: dark scene, white words in a band, one word lit green, new group every 0.5 s
    groups = [["ONE", "TWO"], ["THREE", "FOUR"], ["FIVE", "SIX"], ["SEVEN", "EIGHT"]]
    f = font(26)
    cap = []
    for g, words in enumerate(groups):
        for k in range(15):
            img = Image.fromarray((scene(11) * 0.25).astype(np.uint8))
            d = ImageDraw.Draw(img)
            x = 14
            lit = 0 if k < 8 else 1
            for n, word in enumerate(words):
                colour = (200, 230, 60) if n == lit else (255, 255, 255)
                d.text((x, 190), word, font=f, fill=colour, stroke_width=2, stroke_fill=(0, 0, 0))
                x += int(d.textlength(word, font=f)) + 12
            cap.append(np.array(img))
    out["captions"] = encode(cap, root / "captions.mp4")
    out["root"] = root
    return out
