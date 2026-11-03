# Third-party notices

The skills in this repository adapt ideas and rules from the projects below. No code from them is included; the
`replicate-video` helper is written from scratch.

## Open Design (Apache-2.0)

- Source: https://github.com/nexu-io/open-design, commit 5a0c47777975ddb91d09c1c16b423a3ef74bf572
- Adapted: `skills/motion-design/references/replicate.md` ("Replicating a reference film"): measure-don't-estimate,
  the precedence of measurements over taste, fidelity that follows the request, editable source with one clock
  configuration, the rules for keeping and fitting the reference soundtrack, and the compare-then-fix-once loop.
- Where: `skills/replicate/SKILL.md` (steps 4–7), `skills/replicate/references/sound.md`,
  `skills/replicate/references/rights.md`.
- Changes by Mosio: rewritten for any engine and the `replicate-video` CLI; Open Design host commands, `data-od-id`
  handles and font chains removed; a beat map, a boundary-classification step and caption timing from pixels added.
- Copyright: Open Design contributors. License: Apache License 2.0 (see LICENSE).

## HyperFrames (Apache-2.0)

- Source: https://github.com/heygen-com/hyperframes, commit 3baf81f9a92615507f76fe8de33e489034ee77ec
- Adapted: `skills/reverse-any-video/SKILL.md` and `references/match.md`: the original decides the frame (size,
  rate, duration in frames), times written as frame ÷ fps rounded down, consecutive frames at every change, sizing
  text from its ink, rebuilding transitions over their measured frames, motion blur on fast moves, checking once at
  the end, working as one agent.
- Where: `skills/replicate/SKILL.md` (steps 6–7), `skills/replicate/references/match.md`,
  `skills/replicate/references/hyperframes.md`.
- Changes by Mosio: no HeyGen account, paid plan, avatar re-shoots or cut-outs from the original; measurements from
  `replicate-video`; light, fire and character guidance added from a four-method comparison.
- Copyright: HeyGen, Inc. and contributors. License: Apache License 2.0 (see LICENSE).

## ReelMimic (MIT)

- Source: https://github.com/edenfunf/reelmimic, commit 1be183e593fbdb52734ce49a75d65c924f3b925a
- Adapted: the idea of separating a reference's breakdown (rhythm, shot lengths, camera, palette) from the plan and
  the build, styles written as plain Markdown, and per-shot review with before/after evidence.
- Where: `skills/style-writer/`.
- License: MIT, reproduced in full:

```text
MIT License

Copyright (c) 2026 ReelMimic contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Runtime dependencies

`numpy` (BSD-3-Clause), `pillow` (MIT-CMU), `opencv-python-headless` (Apache-2.0; bundles FFmpeg under LGPL),
optional `faster-whisper` (MIT) and `rapidocr-onnxruntime` (Apache-2.0). FFmpeg itself is installed separately.
