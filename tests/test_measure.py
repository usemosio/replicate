from replicate_video.captions import find_band, track
from replicate_video.cuts import find_boundaries, measure_signals, shots_from
from replicate_video.media import probe
from replicate_video.shots import camera


def test_probe(clips):
    info = probe(clips["cuts"])
    assert (info.width, info.height, info.fps) == (180, 320, 30)
    assert info.frames == 135
    assert info.has_audio


def test_cuts_and_flash(clips):
    sig = measure_signals(clips["cuts"])
    found = find_boundaries(sig)
    cuts = [b.frame for b in found if b.kind == "cut"]
    flashes = [b.frame for b in found if b.kind == "flash"]
    assert cuts == [45, 90]
    assert flashes and abs(flashes[0] - 110) <= 1
    shots = shots_from(found, frames=len(sig.luma), fps=sig.fps)
    assert [s["start_frame"] for s in shots] == [0, 45, 90]


def test_push_in(clips):
    info = probe(clips["push"])
    shot = {"start": 0.0, "end": info.duration, "start_frame": 0, "end_frame": info.frames}
    cam = camera(clips["push"], info, [shot], width=180)[0]
    pushes = [m for m in cam["moves"] if m["move"] == "push-in"]
    assert pushes, cam
    p = pushes[0]
    assert 1.25 < p["amount"] < 1.55
    assert abs(p["start"] - 0.4) < 0.25 and abs(p["end"] - 1.6) < 0.25
    assert p["ease"].startswith("ease-in-out") or p["ease"].startswith("ease")


def test_captions(clips, tmp_path):
    info = probe(clips["captions"])
    band = find_band(clips["captions"], info)
    assert band and band["confidence"] == "high"
    assert band["y0"] < 203 / 320 < band["y1"]  # middle of the caption line
    result = track(clips["captions"], info, band, crops=tmp_path / "captions")
    starts = [round(g["start"] * 30) for g in result["groups"]]
    assert starts == [0, 15, 30, 45]
    # the lit word moves once per group, at frame 8 of the group
    moves = [round(h["time"] * 30) for g in result["groups"] for h in g["highlights"] if h["colour"]]
    assert all(any(abs(m - (s + 8)) <= 1 for m in moves) for s in starts)
    assert all((tmp_path / g["crop"]).exists() for g in result["groups"])
