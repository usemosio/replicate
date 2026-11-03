# {title}

{summary_slot}

Measured from {ref_count} reference video(s), {total_seconds:.1f} s in total. Numbers in this file are
measurements; prose marked as direction is a reading of the frames. When you build with this style, the numbers
win over taste.

## Format

- Canvas: {canvas}. Frame rate: {fps}.
- Typical length: {length}.

## Rhythm

- Shots: {shot_count} in {total_seconds:.1f} s, {cuts_per_minute} cuts per minute.
- Shot length: median {shot_median:.2f} s, shortest {shot_min:.2f} s, longest {shot_max:.2f} s.
- Boundaries that are not hard cuts: {soft_boundaries}.

{rhythm_slot}

## Camera

{camera_table}

{camera_slot}

## Look

Palette (share of screen across all shots):

{palette_list}

Brightness: mean luma {luma_mean}, darkest shot {luma_min}, brightest shot {luma_max}. Saturation {saturation}.

{look_slot}

## Characters and objects

{characters_slot}

## Type and captions

{captions_measured}

{type_slot}

## Motion grammar

{motion_slot}

## Transitions

{transitions_slot}

## Sound

{sound_measured}

{sound_slot}

## Make it yours

{slots_slot}

## Keep / never copy

{keep_slot}
