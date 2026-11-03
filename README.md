# replicate

Agent skills and a small CLI for replicating any video, or its style.

- **`replicate`** skill: measure a reference video, rebuild it as an editable project (HyperFrames by default,
  Remotion or any editor work too), and check the render against the reference frame by frame.
- **`style-writer`** skill: turn one or more references into a reusable style, written as a `STYLE.md` or as a new
  installable skill that makes more videos in that style.
- **`replicate-video`** CLI: the measuring and checking both skills run. Cuts (three detectors, with candidates and
  flashes kept apart), shots, palette, camera moves with their eases, burned-in captions timed from pixels, sound,
  and a frame diff with side-by-side sheets.

Works with Claude Code, Codex, Cursor, Gemini CLI, OpenCode and any agent that reads `SKILL.md` folders. Runs on
macOS, Linux and Windows. Nothing is uploaded anywhere: everything runs on your machine.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/usemosio/replicate/main/install.sh | bash
```

Windows (PowerShell): `irm https://raw.githubusercontent.com/usemosio/replicate/main/install.ps1 | iex`

That installs the CLI with `uv` (or `pipx`) and copies both skills to `~/.claude/skills` and `~/.agents/skills`.
You also need [FFmpeg](https://ffmpeg.org/download.html) (`brew install ffmpeg`, `sudo apt install ffmpeg`,
`winget install Gyan.FFmpeg`). Check with `replicate-video doctor`.

Other ways:

| What | How |
|---|---|
| CLI only | `uv tool install git+https://github.com/usemosio/replicate` or `pipx install git+https://github.com/usemosio/replicate` |
| CLI with word transcripts / caption OCR | `uv tool install "replicate-video[transcribe,ocr] @ git+https://github.com/usemosio/replicate"` |
| Skills only, any agent | `npx skills add usemosio/replicate` |
| Claude Code plugin | `/plugin marketplace add usemosio/replicate`, then `/plugin install replicate@replicate` |
| By hand | copy `skills/replicate` and `skills/style-writer` into your agent's skills folder |

## Use

Ask your agent:

> Replicate this video: ~/Downloads/reference.mp4

> Make a 15-second promo for my bakery in the style of these two videos.

> Turn these three videos into a skill I can reuse.

Or run the CLI yourself:

```bash
replicate-video analyze reference.mp4 -o .replicate/ref     # facts.json, SUMMARY.md, contact sheet, strips, caption crops
replicate-video strip reference.mp4 --range 4.6,5.4          # consecutive frames, labelled
replicate-video diff reference.mp4 render.mp4                # SSIM per frame, cuts, duration, sound offset, worst moments
replicate-video write .replicate/ref --as skill --title "Narrated puppet story" -o skills
replicate-video check skills/narrated-puppet-story           # unfilled slots, frontmatter, local paths, media files
```

`replicate-video <command> --help` lists every option.

## What the measurements are good for

Tested on a 20-second narrated animation (6 shots, one-word karaoke captions, firelit sets):

- every hard cut found on its frame, including two that FFmpeg's scene score misses; the light flash that looks like
  a cut is labelled as one;
- caption groups and lit-word changes timed to the frame from the pixels, whatever colour state the words are in
  (24 groups in 20 s against 22 by eye), which speech recognition gets 0.03–0.5 s early; a second caption band and a
  poll card later in the video are found on their own;
- camera pushes, pulls and pans with their start, end, amount and ease, with captions and still overlays masked
  out of the tracking; a "push" that is really fire flicker is marked low confidence.

An agent following the `replicate` skill rebuilt that clip in about 25 minutes, matching every cut, and scored
highest against four other replication methods on the same clip (SSIM 0.837 against 0.805–0.817).

Measurements say where to look; the skills make the agent confirm each one on the frames before building on it.

## Develop

```bash
uv venv && uv pip install -e '.[dev]'
.venv/bin/pytest
```

Tests generate their own clips with FFmpeg. Keep reference videos out of the repository.

## License

Apache-2.0. The skills adapt rules from Open Design and HyperFrames (Apache-2.0) and ideas from ReelMimic (MIT); see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Replicate only videos you have the right to use; the skills learn
technique and rebuild it, and keep a reference's footage, characters, music and words out of the result.
