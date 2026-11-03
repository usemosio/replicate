# Building with another tool

The measuring (`analyze`) and checking (`diff`) work for any renderer: they only read video files.

## Remotion

- `fps` and the composition size from `source`; `durationInFrames` = `source.frames`.
- Times are frames: use the boundary `frame` numbers directly; a shot is a `<Sequence from={start_frame}
  durationInFrames={end_frame - start_frame}>`.
- Camera moves: `interpolate(frame, [startFrame, endFrame], [1, zoom], {easing: Easing.inOut(Easing.quad)})` on a
  wrapper's `scale`, matching the measured ease name (`ease-in` = `Easing.in`, `ease-out` = `Easing.out`,
  `ease-in-out` = `Easing.inOut`; "strong" = cubic).
- Render to PNG frames with `--image-format=png` and `--color-space=bt709` before diffing, or the diff measures the
  encoder.

## Editors and motion tools (After Effects, Premiere, DaVinci, CapCut, Motion)

- Use `SUMMARY.md` as the edit decision list: shot starts and lengths, camera moves as keyframes, caption groups as
  text layers with in and out points.
- Export at the reference's size and frame rate, then run `replicate-video diff`.

## Anything else

Whatever the tool, keep the canvas, frame rate and duration of the reference, build every time from a measured
frame, and finish with `replicate-video diff`.
