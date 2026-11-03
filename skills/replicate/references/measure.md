# Reading the measurements

`replicate-video analyze <video> -o <dir>` writes:

| File | What it is |
|---|---|
| `facts.json` | everything below as data: `source` (size, fps, frames, audio), `boundaries`, `shots`, `captions`, `audio` |
| `SUMMARY.md` | the same as tables, with the image to open for each row |
| `contact.jpg` | the whole video at a glance, up to 48 labelled frames |
| `strips/<kind>_<time>.jpg` | the 8 consecutive frames around each boundary, labelled with time and frame number |
| `frames/shotNN_{first,middle,last}.jpg` | three frames per shot |
| `captions/NNN_<time>.png` | the caption band of each caption group, from its middle frame |
| `captions.jpg` | every caption crop stacked with its times: read all the words here |
| `audio.wav` | the soundtrack, untouched |
| `transcript.json` | words with timestamps (`--transcribe`, needs the `transcribe` extra) |
| `signals.json` | per-frame brightness and change signals, for your own plots |

## Boundaries

Three detectors vote on every frame (pixel change, colour histogram, edge layout).

- `cut`: two or more agree. Almost always a real cut; check the strip for the one-frame flash or blur that belongs
  to it, and rebuild that over its frames.
- `candidate`: one detector. Often a cut hidden under a fast move, sometimes a fast push-in or a big element arriving.
- `transition`: three or more boundaries within 0.35 s of each other, kept as one window (`frame` to
  `end_frame`): a dissolve, a fade through black, a glitch or a whip. Rebuild it over the whole window.
- `flash`: brightness jumps and returns within 0.3 s with the same picture after. A light flash, an explosion, a
  camera flash; not a shot change, though editors often hide a cut inside one, so check the strip.
- Missing: dissolves and slow wipes spread their change over many frames and can slip under every detector. Scan
  `contact.jpg` for a shot that changes without a boundary, and run `--sensitivity 1.5` or a `strip` there.

## Camera

Moves come from feature tracking between consecutive frames, with the caption band and still overlays (badges,
logos, UI) masked out. Each shot lists `moves`: `push-in`/`pull-out` with a zoom factor, `pan`/`tilt` as a share of
the frame, with start, end, the closest ease and `agreement` (the share of tracked points that follow the move). A
move with low agreement, or a zoom beyond ×1.8 in under 3 s, is marked `confidence: low` ("check" in the summary).

- Reads the picture, not the camera: a whole set sliding is a pan, a character walking at the lens is a push-in.
- Flicker (fire, particles, rain, noise) adds false motion; a shot full of it can show a big push that is not there.
  `confidence: low` means more than half the frame pairs could not be matched.
- Flat vector art with few textures tracks well on edges but poorly on flat fills; a near-empty frame reads static.
- Confirm every move on `frames/` (first vs last) before you build it.

## Captions

Bands are strips of the frame where text comes and goes; a video can have several (captions that move higher for
an ending, a band per speaker), each with its own time span. Text that mostly holds still (a title, a poll card) is
listed as a title band, not tracked. Groups are timed from the band's pixels, whatever colour the words are:
`start`/`end` are when the group is on screen, `highlights` are when the lit word moves and its colour, and `off`
means no word is lit at that moment.

- This is on-screen timing. Speech timing (`transcript.json`) runs 0.03–0.5 s earlier: editors light a word after
  it is said and group words their own way. Build captions from the pixel times.
- The lit colour is the median of bright saturated pixels inside the letters' outline. When the background behind
  the band is bright and saturated (fire, sunset, a coloured set) the colour is marked uncertain (`?` in the
  summary) and left out of style summaries: read it from the crop.
- A white face or object with a dark outline crossing the band can read as a short group with no lit word; the
  sheet shows it.
- A caption that moves around the frame, sits in two bands, or is very thin may be missed: pass
  `--band y0,y1` (fractions of the height) from what you see.
- Text: the `ocr` extra fills `text` per group; otherwise read the crops. OCR misreads stylised type, check it.

## Shots and sound

Per shot: `luma` (0–1), `saturation`, `motion` (mean frame change), `palette` (k-means, sorted by share).
Sound: EBU R128 loudness, silences, onsets, and a tempo when the beat is clear (`null` when it is not, which is
normal for speech).
