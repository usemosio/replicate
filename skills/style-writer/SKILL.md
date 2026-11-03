---
name: style-writer
description: Turn one or more reference videos into a reusable style, written either as a STYLE.md file or as an installable agent skill that makes new videos in that style. Use when asked to capture, extract, document or package a video's style, make a recipe, template or skill from a video, or "make more videos like these".
---

# Write a style

A style is technique that survives a change of content: rhythm, camera language, look, type treatment, motion
grammar, sound design. The output is either a `STYLE.md` (for a project or a recipe library) or a skill folder
(`SKILL.md` + `references/`) any agent can install. The helper `replicate-video` measures the references and writes
the numbers; you write what only looking can say.

**Style, not content.** Every sentence you write should still hold when the next video has a different topic,
brand and characters. A sentence that names the reference's story, product or character is content: rewrite it as
the rule behind it.

## 1. Gather references

Two to five videos of the same style give a style; one video gives one video's habits. Ask for more when you have
one and the person has them. Done when every reference is a local file (`replicate-video doctor` passes; a link is
downloaded first). Keep references out of anything you share ([rights](../replicate/references/rights.md)).

## 2. Measure every reference

```bash
replicate-video analyze <video> -o .replicate/<name>       # one folder per reference
```

Then read the evidence the way the `replicate` skill's step 3 describes
([measure.md](../replicate/references/measure.md)): strips, shot frames, caption crops. Done when you have looked at
every strip and every shot's frames of every reference, and noted per reference what you see.

## 3. Write the draft

```bash
replicate-video write .replicate/a .replicate/b --as md    --title "<Style name>" -o <folder>   # STYLE.md
replicate-video write .replicate/a .replicate/b --as skill --title "<Style name>" -o <skills>   # <skills>/<name>/
```

`--engine hyperframes|remotion|any` sets the build step of a skill (default HyperFrames). The draft holds every
measured number (format, rhythm, camera table, palette, captions, loudness) and FILL slots (HTML comments that name what goes there).

## 4. Fill every slot

Fill each slot from what you saw across the references, following [references/slots.md](references/slots.md). Keep
the measured numbers; correct one only when the frames show the measurement is wrong (say so in the text). Camera
moves marked low confidence are already left out of the table; a set-piece move the table misses (a fly-through, a
reveal) goes in the camera slot from its strip. Done
when no slot is left and every claim is something you saw in at least two references, or is marked as seen in one.

## 5. Prove it

Make a 5–10 second test video with content none of the references has (another topic, another brand), using only
the style file or the new skill, the way a stranger would. Render it and put its frames next to reference frames of
the same shot type (close-up with close-up, wide with wide).
Where the test does not read as the same style, the file is missing something: fix the file, not the test. Done when
one test reads as the style and the file names what it took.

## 6. Check and hand over

```bash
replicate-video check <STYLE.md or skill folder>
```

Pass the names that must not leak with `--forbid` (the reference's creator, title, brand, characters). Done when it
prints `ok`. Then tell the person where the file is and, for a skill, how to install it: copy the
folder to `~/.claude/skills/` (Claude Code), `~/.agents/skills/` (Codex, Cursor, Gemini CLI, OpenCode), or commit
it under `skills/<name>/` in a repository and install with `npx skills add <owner>/<repo>`.
