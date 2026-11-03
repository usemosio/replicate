import json
import re

from replicate_video.analyze import analyze
from replicate_video.cli import main
from replicate_video.diff import compare
from replicate_video.write import SLOT_RE, check, write


def test_diff_identical(clips, tmp_path):
    r = compare(str(clips["cuts"]), str(clips["cuts"]), tmp_path)
    assert r["ssim"]["mean"] > 0.99
    assert r["cuts"]["missing"] == [] and r["cuts"]["extra"] == []
    assert r["duration_delta"] == 0
    assert r["sound_offset_s"] == 0
    assert (tmp_path / "worst.jpg").exists() and (tmp_path / "diff.json").exists()


def test_diff_finds_missing_cut(clips, tmp_path):
    r = compare(str(clips["cuts"]), str(clips["push"]), tmp_path)
    assert len(r["cuts"]["missing"]) == 2
    assert r["ssim"]["mean"] < 0.9


def test_analyze_write_check(clips, tmp_path):
    out = tmp_path / "ref"
    facts = analyze(str(clips["captions"]), out, log=lambda *_: None)
    assert (out / "SUMMARY.md").exists() and (out / "contact.jpg").exists()
    assert json.loads((out / "facts.json").read_text())["captions"]["groups"]

    skill = write([out], tmp_path / "skills", as_="skill", title="Test Style")
    assert skill.name == "test-style"
    problems = check(skill)
    assert any("description" in p for p in problems)
    assert any("unfilled slot" in p for p in problems)

    # an agent fills every slot: then the skill passes
    for f in [skill / "SKILL.md", skill / "references" / "style.md"]:
        text = f.read_text()
        text = re.sub(r"<!--\s*FILL:[^>]*-->", "Filled from the frames.", text)
        f.write_text(text)
    assert check(skill) == []
    assert main(["check", str(skill)]) == 0

    md = write([out], tmp_path / "md", as_="md", title="Test Style")
    assert md.name == "STYLE.md" and SLOT_RE.search(md.read_text())
    assert (md.parent / "measurements.json").exists()
    assert facts["source"]["frames"] == 60


def test_check_flags_paths_and_media(tmp_path):
    d = tmp_path / "bad-skill"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: Bad Skill\ndescription: x\n---\nSee /home/me/ref.mp4\n")
    (d / "ref.mp4").write_bytes(b"0")
    problems = check(d)
    assert any("name" in p for p in problems)
    assert any("absolute local path" in p for p in problems)
    assert any("media file" in p for p in problems)
