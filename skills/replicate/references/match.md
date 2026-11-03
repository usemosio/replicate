# Matching what is drawn

Look at every large element through its whole life (enter, hold, exit) in a `strip` before you build it.

## Type and captions

- Size text from its ink: crop a line in a reference frame and the same line in a snapshot of yours, compare the
  ink boxes' height and width, then adjust size, then letter-spacing, until both agree within a few pixels.
- Match the family by its traits (geometry, contrast, x-height, terminals, weight). Try two or three redistributable
  candidates (Google Fonts) at the measured size and keep the closest; say which one you substituted.
- Compare the ink's darkness for weight, and look for an outline, a stroke or a shadow.
- Captions switch on the frames the caption table gives. Rebuild the pop-in (scale, overshoot, fade) from the strip
  of one group's first 4 frames; rebuild each state of a word (upcoming, lit, said) with its own colour from the crops.

## Layout and palette

- Positions come from measured boxes in source pixels. The canvas is the source's size, so they go in as measured.
- Use the shot palettes for roles: background, mid-tones, accent, text. The largest share is usually the backdrop:
  sample it at several moments and match its gradient and brightness over time.

## Light and shading

Flat fills are the most common reason a rebuild looks "same show, different animator". Before calling the look
done, compare light:

- the direction of the key light and where shadows fall (cast shadows on walls and floors, contact shadows);
- rim or back light around characters (often a coloured glow from a fire, a screen or a sky);
- soft gradients across large planes, ambient occlusion in corners, vignetting;
- light that changes over time (flicker, a colour shift when the story turns) and what it spills onto.

Layer it: base fill, a gradient per plane, soft shadows (blurred shapes with multiply), rim light (an offset stroke
or blurred copy with screen/add), then a light overlay that moves. A soft 3D look in 2D needs every layer.

## Fire, water, particles

A fire is a white-hot core blown out to near white, with yellow then orange then red falling off, and a glow that
lights everything near it; flames are tall soft shapes that boil at 8–12 drawings per second, not thin spikes.
Water carries texture (streaks, ripples) and reflects the light around it. Match the boil rate and density from a
strip, not from one frame.

## Characters and objects

- Measure proportions from a frame: head height ÷ body height, limb thickness, outline width, eye size and spacing.
- Note the acting: blinks, mouth flaps on speech, idle sway, how a walk is drawn (bob only, or real steps).
- Characters and objects are original unless the person brings their own designs. Rebuild the *drawing system*
  (shapes, proportions, outline, shading), not the reference's character.

## Motion

- Times, amounts and eases come from the camera table and from strips. Rebuild a move over its measured frames.
- Fast moves in the original are motion-blurred; sharp shapes at speed read as wrong. Blur along the move while it
  is fast (a directional blur filter or a few faded copies along the path).
- A transition (flash, blur, wipe, whip) at a cut is part of the cut: rebuild it over its measured frames.
