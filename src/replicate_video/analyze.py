"""`replicate-video analyze`: measure a reference once and write everything an agent needs into one folder."""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import __version__, audio, captions, cuts, sheets, shots
from .media import extract_audio, probe


def analyze(
    video: str | Path,
    out_dir: str | Path,
    *,
    transcribe: bool = False,
    language: str | None = None,
    whisper_model: str = "small",
    band: tuple[float, float] | None = None,
    sensitivity: float = 1.0,
    log=print,
) -> dict:
    video = str(video)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    info = probe(video)
    log(f"probe: {info.width}x{info.height} {info.fps_text} fps {info.duration:.2f} s, audio={info.has_audio}")

    sig = cuts.measure_signals(video, info=info)
    boundaries = cuts.find_boundaries(sig, sensitivity=sensitivity)
    shot_list = cuts.shots_from(boundaries, frames=len(sig.luma), fps=info.fps)
    log(f"cuts: {sum(b.kind == 'cut' for b in boundaries)} cuts, "
        f"{sum(b.kind == 'candidate' for b in boundaries)} candidates, {sum(b.kind == 'flash' for b in boundaries)} flashes")

    found = {"y0": band[0], "y1": band[1], "present_share": None, "confidence": "given"} if band else captions.find_band(video, info)
    use_band = found if found and (band or found["confidence"] == "high") else None
    described = shots.describe(video, info, sig, shot_list, band=use_band)
    frame_files = sheets.shot_frames(video, info, shot_list, out / "frames")
    for s, f in zip(described, frame_files):
        s["frames"] = f
    bdicts = [b.to_dict() for b in boundaries]
    strips = sheets.boundary_strips(video, info, bdicts, out / "strips")
    for b, p in zip(bdicts, strips):
        b["strip"] = p
    sheets.contact(video, info, out / "contact.jpg")
    log(f"shots: {len(described)} described, contact sheet and strips written")

    cap = None
    if use_band:
        cap = captions.track(video, info, use_band, crops=out / "captions")
        cap["ocr"] = captions.ocr(cap["groups"], out)
        log(f"captions: band y {found['y0']:.3f}-{found['y1']:.3f}, {len(cap['groups'])} groups, ocr={cap['ocr']}")
    else:
        log("captions: no caption band found (pass --band y0,y1 if there is one)")

    snd = audio.describe(video, info.has_audio)
    if info.has_audio:
        extract_audio(video, out / "audio.wav")
        snd["file"] = "audio.wav"
        if transcribe:
            tr = audio.transcribe(video, model=whisper_model, language=language)
            if tr is None:
                log("transcript: faster-whisper is not installed (pip install 'replicate-video[transcribe]')")
            else:
                (out / "transcript.json").write_text(json.dumps(tr, indent=2, ensure_ascii=False))
                snd["transcript"] = "transcript.json"
                log(f"transcript: {len(tr['words'])} words ({tr['language']})")

    facts = {
        "tool": f"replicate-video {__version__}",
        "source": info.to_dict(),
        "boundaries": bdicts,
        "shots": described,
        "captions": cap,
        "audio": snd,
        "images": {"contact": "contact.jpg"},
        "seconds": round(time.time() - started, 1),
    }
    (out / "facts.json").write_text(json.dumps(facts, indent=2, ensure_ascii=False))
    (out / "signals.json").write_text(json.dumps(sig.to_dict()))
    (out / "SUMMARY.md").write_text(summary(facts))
    log(f"done in {facts['seconds']} s -> {out}/facts.json, SUMMARY.md")
    return facts


def summary(f: dict) -> str:
    s = f["source"]
    lines = [
        "# Reference measurements",
        "",
        f"{s['width']}×{s['height']}, {s['fps_text']} fps, {s['duration']:.3f} s ({s['frames']} frames), "
        f"audio: {'yes' if s['has_audio'] else 'no'}.",
        "",
        "Numbers below are measured. Look at the strips before trusting a candidate or a flash, and at the frames "
        "before trusting a camera move: the frames are the evidence, the numbers say where to look.",
        "",
        "## Boundaries",
        "",
        "| time | frame | kind | detectors | strip |",
        "|---|---|---|---|---|",
    ]
    for b in f["boundaries"]:
        kind = b["kind"] if "end_frame" not in b else f"transition to frame {b['end_frame']}"
        lines.append(f"| {b['time']:.3f} | {b['frame']} | {kind} | {', '.join(b['detectors'])} | {b['strip']} |")
    lines += ["", "## Shots", "", "| # | start | length | luma | motion | camera | palette |", "|---|---|---|---|---|---|---|"]
    for sh in f["shots"]:
        cam = sh["camera"]
        if cam.get("available") is False:
            c = "n/a"
        elif not cam.get("moves"):
            c = "static"
        else:
            c = "; ".join(f"{m['move']} {'×' if m['move'] in ('push-in', 'pull-out') else ''}{m['amount']} "
                          f"{m['start']:.2f}–{m['end']:.2f} {m['ease']}" for m in cam["moves"])
        if cam.get("confidence") == "low":
            c += " (low confidence)"
        pal = " ".join(p["hex"] for p in sh["palette"][:5])
        lines.append(
            f"| {sh['index']} | {sh['start']:.3f} | {sh['duration']:.3f} | {sh['luma']['mean']} | {sh['motion']} | {c} | {pal} |"
        )
    cap = f.get("captions")
    if cap:
        b = cap["band"]
        lines += ["", "## Captions", "", f"Band at y {b['y0']:.3f}–{b['y1']:.3f} of the frame, {len(cap['groups'])} groups. "
                  "Times are when the group appears on screen and when the lit word moves; read the words from the crops.",
                  "", "| start | end | lit-word changes | text | crop |", "|---|---|---|---|---|"]
        for g in cap["groups"]:
            hl = ", ".join(f"{h['time']:.3f}{' ' + h['colour'] if h['colour'] else ' off'}" for h in g["highlights"][:4])
            lines.append(f"| {g['start']:.3f} | {g['end']:.3f} | {hl} | {g.get('text', '')} | {g.get('crop', '')} |")
    a = f["audio"]
    if a.get("present"):
        lu = a["loudness"]
        lines += ["", "## Sound", "",
                  f"Integrated {lu['integrated_lufs']} LUFS, range {lu['range_lu']} LU, true peak {lu['true_peak_dbfs']} dBFS. "
                  f"Tempo: {a['tempo_bpm'] or 'no clear beat'}. {len(a['onsets'])} onsets, {len(a['silences'])} silences."]
        if a.get("transcript"):
            lines.append("Word transcript: transcript.json (speech timing; on-screen timing comes from the captions table).")
    lines.append("")
    return "\n".join(lines)
