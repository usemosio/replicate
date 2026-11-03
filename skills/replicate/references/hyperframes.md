# Building with HyperFrames

[HyperFrames](https://github.com/heygen-com/hyperframes) renders HTML, CSS and GSAP to video. Its own skills hold
the composition contract; install or update them with `npx hyperframes skills update` and read `/hyperframes`
before writing the first file. This page only maps the measurements onto that contract.

## From facts.json to the composition

| Measurement | Where it goes |
|---|---|
| `source.width`, `source.height` | root `data-width`, `data-height` (replace the `init` default canvas) |
| `source.fps_text` | root `data-fps`; a fractional rate stays a fraction (`30000/1001`) |
| `source.frames` ÷ fps | root `data-duration` (the video's frames, not the audio's length) |
| each shot `start`, `duration` | one scene or sub-composition per shot: `data-start`, `data-duration` |
| camera `moves` | a GSAP tween on the scene's camera wrapper: `scale` (zoom), `x`/`y` (pan, tilt) with the measured start, length and ease |
| caption groups | a data array (`[{start, end, words, lit: [{t, word, colour}]}]`) that one captions component renders |
| `audio.file` | one `<audio>` over the whole film for a replica |

## Work loop

```bash
npx hyperframes init <project>                          # then set the canvas, fps and duration from facts.json
npx hyperframes snapshot -o .replicate/snapshots --against <reference> --at 1.2,5.3,9.0   # side-by-side, no render
npx hyperframes check                                   # lint the composition
npx hyperframes render -o out.mp4                       # local render
replicate-video diff <reference> out.mp4                # final comparison
```

- Keep every scene deterministic: no unseeded `Math.random`, no clock reads; animate from the timeline.
- Assets are local files in the project (fonts in `assets/fonts/`), so the render needs no network.
- CPU rendering of WebGL is slow; prefer SVG and CSS for 2D looks, and say so if a look really needs 3D.
- HyperFrames' own `measure cuts` and `diff` are good second opinions when installed.
- Reference pixels stay out of the project: `init --video <reference>` copies the reference into the project and
  `snapshot --against` saves reference frames next to yours by default. Use `init` without `--video`, write
  snapshots to a folder outside the project (`-o`), and put the soundtrack in as `assets/audio.wav` from the
  analysis only when the sound is kept.
- HyperFrames prefers one file per scene. Keep the configuration (clock, copy, colours) in one script, e.g.
  `config.js`, that the root and every scene load.
