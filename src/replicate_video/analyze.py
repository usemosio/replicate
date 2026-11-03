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

    log("measuring every frame for cuts...")
    sig = cuts.measure_signals(video, info=info)
    boundaries = cuts.find_boundaries(sig, sensitivity=sensitivity)
    shot_list = cuts.shots_from(boundaries, frames=len(sig.luma), fps=info.fps)
    log(f"cuts: {sum(b.kind == 'cut' for b in boundaries)} cuts, "
        f"{sum(b.kind == 'candidate' for b in boundaries)} candidates, {sum(b.kind == 'flash' for b in boundaries)} flashes")

    log("looking for caption bands, then tracking the camera per shot...")
    if band:
        bands = [{"y0": band[0], "y1": band[1], "present_share": None, "from": 0.0, "to": info.duration,
                  "kind": "captions", "confidence": "given"}]
    else:
        bands = captions.find_bands(video, info)
    caption_bands = [b for b in bands if b["kind"] == "captions"]
    described = shots.describe(video, info, sig, shot_list, bands=bands)
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
    if caption_bands:
        log("timing caption groups from the pixels...")
        groups = []
        for n, b in enumerate(caption_bands):
            r = captions.track(video, info, b, crops=out / "captions", prefix=f"b{n + 1}_" if len(caption_bands) > 1 else "",
                               start=max(0.0, b["from"] - 0.5), end=min(info.duration, b["to"] + 0.5))
            groups += r["groups"]
        groups.sort(key=lambda g: g["start"])
        cap = {"bands": caption_bands, "titles": [b for b in bands if b["kind"] == "title"], "groups": groups}
        cap["ocr"] = captions.ocr(cap["groups"], out)
        cap["sheets"] = sheets.caption_sheet(out, cap["groups"], out / "captions.jpg")
        where = ", ".join(f"y {b['y0']:.3f}-{b['y1']:.3f} ({b['from']}-{b['to']} s)" for b in caption_bands)
        log(f"captions: {len(groups)} groups in {where}; {len(cap['titles'])} title band(s); ocr={cap['ocr']}")
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
                (out / "transcript.json").write_text(json.dumps(tr, indent=2, ensure_ascii=False), encoding="utf-8")
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
    (out / "facts.json").write_text(json.dumps(facts, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "signals.json").write_text(json.dumps(sig.to_dict()), encoding="utf-8")
    (out / "SUMMARY.md").write_text(summary(facts), encoding="utf-8")
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
                          f"{m['start']:.2f}–{m['end']:.2f} {m['ease']}{' (check: low confidence)' if m.get('confidence') == 'low' else ''}"
                          for m in cam["moves"])
        if cam.get("confidence") == "low":
            c += " (low confidence)"
        pal = " ".join(p["hex"] for p in sh["palette"][:5])
        lines.append(
            f"| {sh['index']} | {sh['start']:.3f} | {sh['duration']:.3f} | {sh['luma']['mean']} | {sh['motion']} | {c} | {pal} |"
        )
    cap = f.get("captions")
    if cap:
        where = "; ".join(f"y {b['y0']:.3f}–{b['y1']:.3f} from {b['from']} to {b['to']} s" for b in cap["bands"])
        lines += ["", "## Captions", "", f"{len(cap['groups'])} groups. Bands: {where}. "
                  "Times are when the group appears on screen and when the lit word moves; read the words from "
                  f"{', '.join(cap.get('sheets') or ['the crops'])} (every crop, labelled with its times). "
                  "`off` = no word is lit at that moment (between words, or the group is shown plain). "
                  "A colour marked ? sat on a bright coloured background and may be the background's colour.", ""]
        for t in cap.get("titles", []):
            lines.append(f"Text that mostly holds still (a title or a card) at y {t['y0']:.3f}–{t['y1']:.3f}, "
                         f"{t['from']}–{t['to']} s.")
        lines += ["", "| start | end | band y | lit-word changes | text | crop |", "|---|---|---|---|---|---|"]
        for g in cap["groups"]:
            hl = ", ".join(
                f"{h['time']:.3f} {h['colour'] + ('?' if h.get('colour_uncertain') else '') if h['colour'] else 'off'}"
                for h in g["highlights"][:4]
            )
            lines.append(f"| {g['start']:.3f} | {g['end']:.3f} | {g['band']['y0']:.2f} | {hl} | {g.get('text', '')} | {g.get('crop', '')} |")
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
