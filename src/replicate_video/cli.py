"""Command line: replicate-video <command> ..."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

from . import __version__


def _pair(text: str) -> tuple[float, float]:
    a, b = text.split(",")
    return float(a), float(b)


def _quad(text: str) -> tuple[float, float, float, float]:
    parts = [float(x) for x in text.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("expected x,y,w,h as fractions of the frame")
    return tuple(parts)  # type: ignore[return-value]


def cmd_doctor(args) -> int:
    from .media import MediaError, ffmpeg, ffprobe, run

    ok = True
    print(f"replicate-video {__version__}, Python {platform.python_version()} on {platform.system()} {platform.machine()}")
    for name, fn in (("ffmpeg", ffmpeg), ("ffprobe", ffprobe)):
        try:
            path = fn()
            first = run([path, "-version"]).stdout.splitlines()[0]
            print(f"  ok   {name}: {path} ({first})")
        except MediaError as e:
            ok = False
            print(f"  FAIL {name}: {e}")
    for mod, extra, what in (
        ("cv2", None, "camera estimate"),
        ("faster_whisper", "transcribe", "word transcript (optional)"),
        ("rapidocr_onnxruntime", "ocr", "caption text by OCR (optional)"),
    ):
        try:
            __import__(mod)
            print(f"  ok   {mod}: {what}")
        except Exception:
            hint = f"pip install 'replicate-video[{extra}]'" if extra else "pip install opencv-python-headless"
            print(f"  --   {mod}: {what} unavailable ({hint})")
            if extra is None:
                ok = False
    return 0 if ok else 1


def cmd_analyze(args) -> int:
    from .analyze import analyze

    out = args.out or str(Path(".replicate") / Path(args.video).stem[:60])
    analyze(
        args.video,
        out,
        transcribe=args.transcribe,
        language=args.language,
        whisper_model=args.whisper_model,
        band=args.band,
        sensitivity=args.sensitivity,
    )
    return 0


def cmd_strip(args) -> int:
    from .media import probe
    from .sheets import strip

    info = probe(args.video)
    a, b = args.range
    out = Path(args.out or f"strip_{a:.2f}-{b:.2f}.jpg")
    strip(args.video, info, a, b, out, width=args.width, roi=args.roi, every=args.every, max_frames=args.max)
    print(out)
    return 0


def cmd_frame(args) -> int:
    from .media import frame_at

    times = [float(x) for item in args.times for x in item.split(",") if x]
    for t in times:
        out = Path(args.out_dir) / f"frame_{t:07.3f}.png"
        frame_at(args.video, t, out)
        print(out)
    return 0


def cmd_diff(args) -> int:
    from .diff import compare

    out = args.out or str(Path(".replicate") / "diff" / Path(args.rebuild).stem[:60])
    r = compare(args.reference, args.rebuild, out)
    if args.json:
        print(json.dumps(r, indent=2))
        return 0
    s = r["ssim"]
    print(f"SSIM mean {s['mean']}  p05 {s['p05']}  min {s['min']}  worst-region p05 {r['worst_cell_p05']}")
    print(f"size {'ok' if r['size_matches'] else 'DIFFERENT'}, fps {'ok' if r['fps_matches'] else 'DIFFERENT'}, "
          f"duration delta {r['duration_delta']:+.3f} s, sound offset {r['sound_offset_s']}")
    c = r["cuts"]
    print(f"cuts: {len(c['matched'])} matched, missing {c['missing']}, extra {c['extra']}")
    off = [m for m in c["matched"] if m["offset_frames"]]
    if off:
        print("  off by frames: " + ", ".join(f"{m['reference']:.3f} ({m['offset_frames']:+d})" for m in off))
    if r["low_stretches"]:
        print("low stretches: " + ", ".join(f"{x['start']:.2f}-{x['end']:.2f}" for x in r["low_stretches"]))
    print("worst moments: " + ", ".join(f"{w['time']:.2f} ({w['ssim']:.3f})" for w in r["worst_moments"]))
    print(f"images: {out}/worst.jpg, {out}/shots.jpg; numbers: {out}/diff.json")
    return 0


def cmd_write(args) -> int:
    from .write import write

    out = write(args.analysis, args.out, as_=args.as_, title=args.title, name=args.name, engine=args.engine)
    print(out)
    print("Fill every <!-- FILL: ... --> slot from the frames, then run: replicate-video check", out)
    return 0


def cmd_check(args) -> int:
    from .write import check

    problems = check(args.path, forbid=args.forbid)
    for p in problems:
        print(p)
    if not problems:
        print("ok")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="replicate-video", description=__doc__)
    p.add_argument("--version", action="version", version=f"replicate-video {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="check ffmpeg, ffprobe and optional extras")
    d.set_defaults(fn=cmd_doctor)

    a = sub.add_parser("analyze", help="measure a reference video into a folder (facts.json, SUMMARY.md, images)")
    a.add_argument("video")
    a.add_argument("-o", "--out", help="output folder (default .replicate/<video name>)")
    a.add_argument("--transcribe", action="store_true", help="word transcript with faster-whisper (extra)")
    a.add_argument("--language", help="transcript language, e.g. en, id (default: detect)")
    a.add_argument("--whisper-model", default="small")
    a.add_argument("--band", type=_pair, help="caption band y0,y1 as fractions of the height, if detection misses it")
    a.add_argument("--sensitivity", type=float, default=1.0, help="cut detection; >1 finds more, <1 fewer")
    a.set_defaults(fn=cmd_analyze)

    s = sub.add_parser("strip", help="consecutive frames in a time range, labelled with time and frame")
    s.add_argument("video")
    s.add_argument("--range", type=_pair, required=True, help="start,end in seconds")
    s.add_argument("--roi", type=_quad, help="x,y,w,h as fractions of the frame")
    s.add_argument("--every", type=int, default=1, help="keep every n-th frame")
    s.add_argument("--width", type=int, default=200)
    s.add_argument("--max", type=int, default=48, help="at most this many frames; a longer range skips frames evenly")
    s.add_argument("-o", "--out")
    s.set_defaults(fn=cmd_strip)

    f = sub.add_parser("frame", help="full-size frames at given times")
    f.add_argument("video")
    f.add_argument("times", nargs="+", help="seconds, space- or comma-separated (1.5 3,4.2)")
    f.add_argument("-o", "--out-dir", default=".")
    f.set_defaults(fn=cmd_frame)

    df = sub.add_parser("diff", help="compare a rebuild with its reference")
    df.add_argument("reference")
    df.add_argument("rebuild")
    df.add_argument("-o", "--out")
    df.add_argument("--json", action="store_true")
    df.set_defaults(fn=cmd_diff)

    w = sub.add_parser("write", help="write a style file (md) or a skill folder from one or more analyses")
    w.add_argument("analysis", nargs="+", help="analysis folders from `analyze`")
    w.add_argument("--as", dest="as_", choices=["md", "skill"], default="md")
    w.add_argument("--title", required=True, help="style name, e.g. 'Narrated puppet story'")
    w.add_argument("--name", help="skill name (default: from title)")
    w.add_argument("--engine", choices=["hyperframes", "remotion", "any"], default="hyperframes")
    w.add_argument("-o", "--out", default=".")
    w.set_defaults(fn=cmd_write)

    c = sub.add_parser("check", help="check a style file or skill folder is complete and shareable")
    c.add_argument("path")
    c.add_argument("--forbid", action="append", default=[], help="a word or name that must not appear (repeatable): "
                   "the reference's creator, title, brand or characters")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except Exception as e:  # show a short message, not a traceback, for expected failures
        from .media import MediaError

        if isinstance(e, MediaError):
            print(f"error: {e}", file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    sys.exit(main())
