# Sound

For a replica the reference's soundtrack is part of the reference: keep `audio.wav` as one track from 0 for the
film's length. Do not compose, replace or remix it, and add no effects on top, unless the person asks for different
sound (their own track, new music, a voiceover, silence).

When the new video is a different length than the reference:

- Cut the soundtrack at scene boundaries, moving each cut to the nearest quiet point (`audio.silences`) so no word
  or note is split.
- Change each piece's tempo to fit its new scene with ffmpeg `atempo`: within 0.8–1.25× for music, within
  0.95–1.05× when a voice is heard.
- Join pieces with 20–50 ms crossfades, fade in over 0.15 s and out over the last second, and write a new WAV.
- A piece that needs more than its range keeps its own tempo and is trimmed (or padded with its own faded tail).
  Say which scenes the sound no longer lines up with.

When the person changes what a voice would say (a new brand, new claims) and keeps the soundtrack, say in the report
that the voice still says the original words.

For an adapted or style-only video, match the measured sound design instead: loudness (`integrated_lufs`), how dense
the onsets are, whether cuts land on beats or on words.
