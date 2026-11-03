"""`replicate-video write`: turn one or more analyses into a style file (STYLE.md) or an installable skill.

The writer fills every number it measured and leaves `<!-- FILL: ... -->` slots for what only a reading of the
frames can say (the look, the characters, the motion grammar). The agent fills the slots from the frames; `check`
refuses a file that still has one.
"""

from __future__ import annotations

import json
import re
import shutil
from importlib import resources
from pathlib import Path

import numpy as np

from .shots import palette as kmeans

SLOT = "<!-- FILL: {} -->"
SLOT_RE = re.compile(r"<!--\s*FILL:")


def _template(name: str) -> str:
    return resources.files("replicate_video").joinpath("templates", name).read_text()


def load(analysis: str | Path) -> dict:
    p = Path(analysis)
    facts = json.loads((p / "facts.json" if p.is_dir() else p).read_text())
    facts["_dir"] = str(p if p.is_dir() else p.parent)
    return facts


def aggregate(analyses: list[dict]) -> dict:
    shots, bounds, groups, highlights, sounds = [], [], [], [], []
    total = 0.0
    canvases, rates = set(), set()
    for f in analyses:
        s = f["source"]
        total += s["duration"]
        canvases.add(f"{s['width']}×{s['height']}")
        rates.add(s["fps_text"])
        shots += f["shots"]
        bounds += f["boundaries"]
        if f.get("captions"):
            for g in f["captions"]["groups"]:
                groups.append(g)
                highlights += [h for h in g["highlights"] if h.get("colour") and not h.get("colour_uncertain")]
        if f["audio"].get("present"):
            sounds.append(f["audio"])
    lengths = np.array([s["duration"] for s in shots]) if shots else np.zeros(1)
    cams = [s["camera"] for s in shots if s["camera"].get("available") is not False]
    moves: dict[str, list] = {}
    for c in cams:
        if not c.get("moves"):
            moves.setdefault("static", []).append({"move": None, "amount": 1.0, "start": 0, "end": 0, "ease": None})
        for mv in c.get("moves", []):
            if mv.get("confidence") != "low":  # flicker and characters moving on their own stay out of the style
                moves.setdefault(mv["move"], []).append(mv)
    # palette across shots, weighted by shot length
    swatches = []
    for s in shots:
        for p in s["palette"]:
            rgb = [int(p["hex"][i : i + 2], 16) for i in (1, 3, 5)]
            swatches += [rgb] * max(1, int(round(p["share"] * s["duration"] * 20)))
    pal = kmeans(np.array(swatches, dtype=np.float32), k=8) if swatches else []
    cap = None
    if groups:
        g_len = np.array([g["end"] - g["start"] for g in groups])
        hl_cols = [h["colour"] for h in highlights]
        hl_pal = kmeans(np.array([[int(c[i : i + 2], 16) for i in (1, 3, 5)] for c in hl_cols], dtype=np.float32), k=3) if hl_cols else []
        by_band: dict[tuple, int] = {}
        for g in groups:
            key = (g["band"]["y0"], g["band"]["y1"])
            by_band[key] = by_band.get(key, 0) + 1
        per_min = len(groups) / total * 60 if total else 0
        cap = {
            "groups": len(groups),
            "groups_per_minute": round(per_min, 1),
            "group_seconds_median": round(float(np.median(g_len)), 3),
            "group_seconds_min": round(float(g_len.min()), 3),
            "bands": [{"y0": k[0], "y1": k[1], "share": round(v / len(groups), 3)}
                      for k, v in sorted(by_band.items(), key=lambda kv: -kv[1])],
            "lit_colours": hl_pal,
            "groups_with_lit_word": round(sum(1 for g in groups if any(h.get("colour") for h in g["highlights"])) / len(groups), 3),
        }
    snd = None
    if sounds:
        lu = [s["loudness"]["integrated_lufs"] for s in sounds if s["loudness"]["integrated_lufs"] is not None]
        tempos = [s["tempo_bpm"] for s in sounds if s.get("tempo_bpm")]
        snd = {
            "integrated_lufs": round(float(np.mean(lu)), 1) if lu else None,
            "tempo_bpm": round(float(np.median(tempos)), 1) if tempos else None,
            "onsets_per_second": round(sum(len(s["onsets"]) for s in sounds) / total, 2) if total else None,
            "has_transcript": any(s.get("transcript") for s in sounds),
        }
    return {
        "references": len(analyses),
        "total_seconds": round(total, 3),
        "canvas": sorted(canvases),
        "fps": sorted(rates),
        "lengths": [round(f["source"]["duration"], 2) for f in analyses],
        "shots": {
            "count": len(shots),
            "cuts_per_minute": round(sum(1 for b in bounds if b["kind"] == "cut") / total * 60, 1) if total else 0,
            "median": round(float(np.median(lengths)), 3),
            "min": round(float(lengths.min()), 3),
            "max": round(float(lengths.max()), 3),
            "lengths": [round(float(x), 3) for x in lengths],
        },
        "soft_boundaries": {k: sum(1 for b in bounds if b["kind"] == k) for k in ("candidate", "flash")},
        "camera": {
            k: _move_stats(v)
            for k, v in moves.items()
        },
        "shots_static": sum(1 for c in cams if not c.get("moves")),
        "palette": pal,
        "luma": {
            "mean": round(float(np.mean([s["luma"]["mean"] for s in shots if s["luma"]["mean"] is not None])), 3) if shots else None,
            "min": round(float(min(s["luma"]["mean"] for s in shots if s["luma"]["mean"] is not None)), 3) if shots else None,
            "max": round(float(max(s["luma"]["mean"] for s in shots if s["luma"]["mean"] is not None)), 3) if shots else None,
        },
        "saturation": round(float(np.mean([s["saturation"] for s in shots if s["saturation"] is not None])), 3) if shots else None,
        "captions": cap,
        "sound": snd,
    }


def _move_stats(v: list[dict]) -> dict:
    """Short blips (a character shifting, a nudge) and sustained moves are different tools: keep them apart, and
    keep the largest move of each kind, which a median hides."""
    def size(mv: dict) -> float:
        return abs(float(np.log(mv["amount"]))) if mv.get("move") in ("push-in", "pull-out") else mv["amount"]

    long = [mv for mv in v if mv["end"] - mv["start"] >= 1.0]
    big = max(v, key=size) if v and v[0].get("move") else None
    return {
        "count": len(v),
        "sustained": len(long),
        "amount_median": round(float(np.median([mv["amount"] for mv in (long or v)])), 3),
        "seconds_median": round(float(np.median([mv["end"] - mv["start"] for mv in (long or v)])), 3),
        "eases": sorted({mv["ease"] for mv in v if mv.get("ease")}),
        "largest": {k: big[k] for k in ("amount", "start", "end", "ease")} if big else None,
    }


def _camera_table(m: dict) -> str:
    if not m["camera"]:
        return "No camera measurement."
    rows = ["| move | times (≥ 1 s) | median amount | median length | eases | largest |", "|---|---|---|---|---|---|"]
    for k, v in sorted(m["camera"].items(), key=lambda kv: -kv[1]["count"]):
        if k == "static":
            rows.append(f"| static shot | {v['count']} | — | — | — | — |")
            continue
        zoom = k in ("push-in", "pull-out")
        fmt = (lambda a: f"×{a}") if zoom else (lambda a: f"{a:.0%} of the frame")  # noqa: E731
        big = v.get("largest")
        largest = f"{fmt(big['amount'])} over {big['end'] - big['start']:.1f} s ({big['ease']})" if big else "—"
        rows.append(f"| {k} | {v['count']} ({v['sustained']}) | {fmt(v['amount_median'])} | {v['seconds_median']:.2f} s | "
                    f"{', '.join(v['eases']) or '—'} | {largest} |")
    rows.append("")
    rows.append("Camera numbers come from feature tracking between frames: a whole scene sliding reads as a pan, "
                "and flicker (fire, particles) reads as noise. The frames decide.")
    return "\n".join(rows)


def _captions(m: dict) -> str:
    c = m["captions"]
    if not c:
        return "No burned-in captions were measured."
    cols = ", ".join(f"{p['hex']} ({p['share']:.0%})" for p in c["lit_colours"]) or "none"
    return (
        "- Band: " + "; ".join(f"y {b['y0']:.3f}–{b['y1']:.3f} of the frame height ({b['share']:.0%} of groups)"
                               for b in c["bands"]) + ".\n"
        f"- {c['groups_per_minute']} caption groups per minute; a group stays median {c['group_seconds_median']:.2f} s "
        f"(shortest {c['group_seconds_min']:.2f} s).\n"
        f"- {c['groups_with_lit_word']:.0%} of groups light one word; lit colours: {cols}.\n"
        "- Timing is on-screen timing measured from pixels, not speech timing."
    )


def _sound(m: dict) -> str:
    s = m["sound"]
    if not s:
        return "The references are silent."
    return (
        f"- Loudness {s['integrated_lufs']} LUFS integrated; {s['onsets_per_second']} onsets per second; "
        f"tempo {s['tempo_bpm'] or 'not clear'} BPM."
    )


def fill(template: str, m: dict, *, title: str, name: str = "", engine: str = "hyperframes") -> str:
    pal = "\n".join(f"- `{p['hex']}` {p['share']:.0%}" for p in m["palette"]) or "- (none)"
    soft = ", ".join(f"{v} {k}{'s' if v != 1 else ''}" for k, v in m["soft_boundaries"].items() if v) or "none"
    engines = {
        "hyperframes": "Write a HyperFrames composition (HTML + GSAP; `npx hyperframes init`, `check`, `render`) at "
        "the style's canvas and frame rate. Put copy, colours and fonts in one place so a change is one edit.",
        "remotion": "Write a Remotion composition at the style's canvas and frame rate; times in frames.",
        "any": "Build it in the tool you use (HyperFrames, Remotion, After Effects, an editor) at the style's canvas "
        "and frame rate.",
    }
    values = {
        "title": title,
        "name": name,
        "ref_count": m["references"],
        "total_seconds": m["total_seconds"],
        "canvas": ", ".join(m["canvas"]),
        "fps": ", ".join(m["fps"]),
        "length": ", ".join(f"{x:.1f} s" for x in m["lengths"]),
        "shot_count": m["shots"]["count"],
        "cuts_per_minute": m["shots"]["cuts_per_minute"],
        "shot_median": m["shots"]["median"],
        "shot_min": m["shots"]["min"],
        "shot_max": m["shots"]["max"],
        "soft_boundaries": soft,
        "camera_table": _camera_table(m),
        "palette_list": pal,
        "luma_mean": m["luma"]["mean"],
        "luma_min": m["luma"]["min"],
        "luma_max": m["luma"]["max"],
        "saturation": m["saturation"],
        "captions_measured": _captions(m),
        "sound_measured": _sound(m),
        "engine_line": engines.get(engine, engines["any"]),
        "summary_slot": SLOT.format("one paragraph: what this style is, what it is good for, the feeling it leaves"),
        "description_slot": SLOT.format(
            "one line, max 1024 characters, what videos this skill makes and when to use it, "
            "for example 'Make narrated story shorts in this look, ... Use when ...'"
        ),
        "rhythm_slot": SLOT.format("how the rhythm is built: what drives cuts (voice, beat, action), holds, accelerations"),
        "camera_slot": SLOT.format("camera language in words: moves per shot type, how they start and land"),
        "look_slot": SLOT.format("rendering style, light, shading, textures, depth, colour roles (background, accent, text)"),
        "characters_slot": SLOT.format("how characters/objects are drawn and act (proportions, outline, faces, poses); "
                                       "write 'none' if the style has none"),
        "type_slot": SLOT.format("type traits (weight, case, outline, size relative to frame), a redistributable family "
                                 "that matches, how captions pop in and change"),
        "motion_slot": SLOT.format("how things move: entrances, exits, eases, overshoot, secondary motion, loops"),
        "transitions_slot": SLOT.format("each transition used and how it is built (cut, flash, push, wipe...)"),
        "sound_slot": SLOT.format("sound design: voice, music, effects and how they sit with the picture"),
        "slots_slot": SLOT.format("what a new video swaps in: copy, characters, colours, logo, footage; and what stays"),
        "keep_slot": SLOT.format("what must stay for it to read as this style, and what must never be copied from the references"),
        "extra_rules_slot": SLOT.format("any rule specific to this style, or delete this line"),
    }
    return template.format(**values)


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:64] or "style"


def write(analyses: list[str | Path], out: str | Path, *, as_: str, title: str, name: str | None = None,
          engine: str = "hyperframes") -> Path:
    facts = [load(a) for a in analyses]
    m = aggregate(facts)
    out = Path(out)
    if as_ == "md":
        target = out if out.suffix == ".md" else out / "STYLE.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(fill(_template("STYLE.md"), m, title=title, engine=engine))
        (target.parent / "measurements.json").write_text(json.dumps(m, indent=2))
        return target
    name = slugify(name or title)
    root = out / name if out.name != name else out
    (root / "references").mkdir(parents=True, exist_ok=True)
    (root / "SKILL.md").write_text(fill(_template("SKILL.md"), m, title=title, name=name, engine=engine))
    (root / "references" / "style.md").write_text(fill(_template("STYLE.md"), m, title=title, engine=engine))
    (root / "references" / "measurements.json").write_text(json.dumps(m, indent=2))
    return root


NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


LEAK_PATTERNS = [
    (re.compile(r"(?<![\w.])@[A-Za-z0-9_.]{3,30}\b"), "a social handle"),
    (re.compile(r"https?://(www\.)?(tiktok|instagram|youtube|youtu\.be|x\.com|twitter|facebook)\S*", re.I), "a link to a social post"),
    (re.compile(r"\b[\w-]+\.(mp4|mov|webm|mkv|m4v)\b", re.I), "a video file name"),
]


def check(path: str | Path, *, forbid: list[str] | None = None) -> list[str]:
    """Problems that keep a style file or skill from being shared. Empty list = ready."""
    p = Path(path).resolve()
    problems: list[str] = []
    files = [p] if p.is_file() else sorted(x for x in p.rglob("*") if x.is_file())
    if p.is_dir():
        skill = p / "SKILL.md"
        if not skill.exists() and not (p / "STYLE.md").exists():
            problems.append("no SKILL.md or STYLE.md in the folder")
        if skill.exists():
            text = skill.read_text()
            m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
            if not m:
                problems.append("SKILL.md: missing YAML frontmatter")
            else:
                front = dict(
                    (k.strip(), v.strip()) for k, v in (line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)
                )
                name = front.get("name", "")
                if not NAME_RE.match(name) or len(name) > 64:
                    problems.append(f"SKILL.md: name '{name}' must be lowercase words joined by '-', max 64 characters")
                if name and name != p.name:
                    problems.append(f"SKILL.md: name '{name}' should match the folder name '{p.name}'")
                desc = front.get("description", "")
                if not desc or SLOT_RE.search(desc):
                    problems.append("SKILL.md: description is empty or still a FILL slot")
                elif len(desc) > 1024:
                    problems.append("SKILL.md: description is longer than 1024 characters")
            for link in re.findall(r"\]\(([^)#]+)\)", text):
                if not link.startswith(("http://", "https://")) and not (p / link).exists():
                    problems.append(f"SKILL.md: link to missing file {link}")
    for f in files:
        if f.suffix not in (".md", ".json", ".txt", ".yaml", ".yml"):
            if f.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv", ".wav", ".mp3", ".m4a"):
                problems.append(f"{f.relative_to(p) if p.is_dir() else f.name}: media file; a shareable style carries no reference footage or sound")
            continue
        text = f.read_text(errors="replace")
        rel = f.relative_to(p) if p.is_dir() else f.name
        fenced = False
        for n, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("```"):
                fenced = not fenced
            if SLOT_RE.search(line):
                problems.append(f"{rel}:{n}: unfilled slot")
            if re.search(r"(^|[\s\"'(])(/home/|/Users/|[A-Za-z]:\\\\)", line):
                problems.append(f"{rel}:{n}: absolute local path")
            if f.suffix == ".md" and not fenced:  # commands in code blocks name their own files
                for rx, what in LEAK_PATTERNS:
                    m = rx.search(line)
                    if m:
                        problems.append(f"{rel}:{n}: {what} ({m.group(0)}): the style should not point back at its references")
            for word in forbid or []:
                if word and word.lower() in line.lower():
                    problems.append(f"{rel}:{n}: contains '{word}'")
    return problems


def copy_examples(analysis: str | Path, root: Path, picks: list[str]) -> None:
    """Copy chosen analysis images into the skill (only when the user has the right to share them)."""
    src = Path(analysis)
    dest = root / "references" / "examples"
    dest.mkdir(parents=True, exist_ok=True)
    for rel in picks:
        shutil.copy2(src / rel, dest / Path(rel).name)
