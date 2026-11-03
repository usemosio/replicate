---
name: replicate
description: Rebuild any video, or its style, as an editable video project. Measure the reference (cuts, shots, camera, captions, sound), write a beat map, build it (HyperFrames by default), then check the render against the reference frame by frame. Use when asked to replicate, recreate, copy, clone or match a video, or to make one "like this".
---

# Replicate a video

The result is an editable project whose render matches the reference in timing, framing, type, palette and
motion, and a report of what is exact and what is approximate. The helper CLI `replicate-video` does the
measuring and checking; you do the looking and the building.

**Measure, never estimate.** A timeline guessed from a contact sheet is off by a second in a 15-second film. Every
time in the build comes from a measured frame. The frames are the evidence; the numbers say where to look.

## 1. Set up

Run `replicate-video doctor`. Done when ffmpeg, ffprobe and cv2 say `ok`. If the command is missing, install it
(`uv tool install git+https://github.com/usemosio/replicate` or `pipx install git+https://github.com/usemosio/replicate`)
and FFmpeg. A link is a page, not a file: download it first (`yt-dlp`, or ask the person for the file) and keep only
what they have the right to use ([references/rights.md](references/rights.md)).

## 2. Measure

```bash
replicate-video analyze <video> -o .replicate/<name>            # add --transcribe when speech matters
```

Done when `.replicate/<name>/facts.json` and `SUMMARY.md` exist. What each output means and how it misleads:
[references/measure.md](references/measure.md).

## 3. Read the evidence

Open `contact.jpg`, then `SUMMARY.md`, then every image it names:

- each **boundary strip** (`strips/`): confirm or reject every `cut`, `candidate` and `flash`. A cut hides under a
  fast move; a flash or a fast push-in looks like a cut;
- each **shot's frames** (`frames/`), against the camera moves in the table;
- each **caption crop** (`captions/`): write down its exact words;
- for every entrance, exit and transition, consecutive frames:
  `replicate-video strip <video> --range a,b [--roi x,y,w,h]`.

Done when every boundary is classified by eye, every caption group has its words, and every move in the table is
confirmed or corrected.

## 4. Decide the fidelity

| The person asks | Keep | Swap |
|---|---|---|
| "replicate / make the same video" | beats, timing, copy, composition, palette, motion, sound | nothing |
| "like this, for my brand / change X" | beat structure, rhythm, motion grammar, composition, palette roles | the content they name; words, logos, people and places of the reference |
| "this style, reusable" | — | hand over to the `style-writer` skill |

When the request is unclear, ask once with these three options.

## 5. Write the beat map

Write `BEATS.md` before any code. For each beat: start and end frame, what fills the frame, the exact on-screen
words, palette, type, the camera move (amount, ease, start and end), how things enter, the motion mechanism (what
turns into what), and how it exits. Done when every frame of the reference belongs to a beat.

## 6. Build

- The canvas is the reference's size and frame rate; the duration is its frames ÷ fps. Write times as frame ÷ fps,
  rounded down (frame 83 at 30 fps is `2.766666`).
- One configuration holds the clock (scenes, cues) and everything a person might swap (copy, colours, fonts, image
  paths), so a later change is a one-place edit.
- Every scene keeps some motion written as a function of time, so a stretched scene never freezes.
- Match each layer by the rules in [references/match.md](references/match.md): type from its ink, captions from the
  pixels, light, fire and particles, characters, motion blur.
- HyperFrames: [references/hyperframes.md](references/hyperframes.md). Any other tool:
  [references/other-engines.md](references/other-engines.md). Sound: [references/sound.md](references/sound.md).

Work alone: one agent holding the whole film beats several that each re-watch it.

## 7. Check once, at the end

```bash
replicate-video diff <reference> <render> -o .replicate/diff
```

Open `worst.jpg` and `shots.jpg` (reference left, render right). Judge by eye in this order: beat timing,
composition, palette, type, motion. The score only says where to look first; it cannot see a wrong word and it
punishes changes that were asked for. Fix the single largest real difference, render and diff once more, then stop.
Done when the diff lists no missing cuts, the duration delta is 0 and one fix round is behind you. Small score
differences are not worth another round.

## 8. Report

Write `REPLICATE.md` in the project: what is rebuilt exactly, what is approximate and why (substituted fonts, a
simplified drawing), what was asked to change, and the last diff numbers.
