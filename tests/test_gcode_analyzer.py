"""F3 — gcode_analyzer: streaming gcode scanner."""

from __future__ import annotations

import io

import pytest

from hictopswapper.gcode_analyzer import analyze, analyze_path

from conftest import INPUT_DIR


@pytest.fixture(scope="module")
def head_analysis():
    return analyze_path(INPUT_DIR / "plate_1.head.gcode")


# ------------------------------------------------------- real gcode header
def test_head_header_stats(head_analysis):
    assert head_analysis.total_estimated_time == "15h 9m 40s"
    assert head_analysis.filaments == [1, 3, 6]
    assert head_analysis.total_filament_length_mm == pytest.approx(
        [23314.10, 293.75, 621.81])
    assert head_analysis.total_filament_weight_g == pytest.approx(
        [69.54, 0.89, 1.88])


def test_head_size_and_lines(head_analysis):
    path = INPUT_DIR / "plate_1.head.gcode"
    assert head_analysis.size_bytes == path.stat().st_size
    assert head_analysis.line_count == 300


def test_head_block_markers(head_analysis):
    assert head_analysis.markers["HEADER_BLOCK_START"] == [1]
    assert head_analysis.markers["HEADER_BLOCK_END"] == [14]
    assert head_analysis.markers["CONFIG_BLOCK_START"] == [16]


def test_head_no_ams_events(head_analysis):
    """The config-block M620/M621 comment templates are NOT events: only
    lines *starting with* M620/M621 count, and the 300-line head has none."""
    assert head_analysis.m620_events == []
    assert head_analysis.m620_s255_count == 0


def test_head_claim_speed_offset(head_analysis):
    """claim_speed matching is a plain substring scan, so the head's single
    hit is the template occurrence inside the ``; machine_end_gcode = ...``
    comment line (line 287), not an executable marker."""
    assert head_analysis.claim_speed_offsets == [25024]
    path = INPUT_DIR / "plate_1.head.gcode"
    blob = path.read_bytes()
    assert blob[25024:].startswith(b"set_gcode_claim_speed_level : 0")
    line_start = blob.rfind(b"\n", 0, 25024) + 1
    assert blob[line_start:].startswith(b"; machine_end_gcode = ")


# ------------------------------------------------------------ synthetic
SYNTHETIC = (
    "; HEADER_BLOCK_START\n"
    "; total estimated time: 0h 2m 3s\n"
    "; filament: 2,5\n"
    "; total filament length [mm] : 10.5,20.25\n"
    "; total filament weight [g] : 1.5,2.25\n"
    "; CONFIG_BLOCK_START\n"
    "; change_filament_gcode = ...M620 S[next_extruder]A...\n"  # not an event
    "M1002 set_gcode_claim_speed_level : 1\n"
    "M620 S2\n"
    "G1 X10\n"
    "M620 S255\n"
    "M621 S2\n"
    "M1002 set_gcode_claim_speed_level : 0\n"
    "; M620 S9 commented out\n"
    "M620\n"
)


def test_synthetic_events():
    res = analyze(io.BytesIO(SYNTHETIC.encode()))
    events = res.m620_events
    assert [(e.command, e.slot) for e in events] == [
        ("M620", 2), ("M620", 255), ("M621", 2), ("M620", None)]
    assert res.m620_s255_count == 1
    # the config template and the commented line are excluded
    assert all(not e.text.startswith(";") for e in events)
    assert all(e.slot != 9 for e in events)


def test_synthetic_event_positions():
    blob = SYNTHETIC.encode()
    res = analyze(io.BytesIO(blob))
    first = res.m620_events[0]
    assert first.line_no == 9
    assert blob[first.byte_offset:].startswith(b"M620 S2\n")
    assert first.text == "M620 S2"
    # byte offsets point at the line's first byte for every event
    for e in res.m620_events:
        line = blob[e.byte_offset:].split(b"\n", 1)[0].decode()
        assert line == e.text


def test_synthetic_claim_speed_offsets():
    blob = SYNTHETIC.encode()
    res = analyze(io.BytesIO(blob))
    # only the exact "... : 0" marker matches (the ": 1" line does not)
    marker = b"set_gcode_claim_speed_level : 0"
    assert len(res.claim_speed_offsets) == 1
    assert blob[res.claim_speed_offsets[0]:].startswith(marker)
    assert res.claim_speed_offsets == [blob.find(marker)]


def test_synthetic_header_stats():
    res = analyze(io.BytesIO(SYNTHETIC.encode()))
    assert res.total_estimated_time == "0h 2m 3s"
    assert res.filaments == [2, 5]
    assert res.total_filament_length_mm == pytest.approx([10.5, 20.25])
    assert res.total_filament_weight_g == pytest.approx([1.5, 2.25])
    assert res.size_bytes == len(SYNTHETIC.encode())
    assert res.line_count == len(SYNTHETIC.splitlines())
    assert res.markers["HEADER_BLOCK_START"] == [1]
    assert res.markers["CONFIG_BLOCK_START"] == [6]


def test_empty_stream():
    res = analyze(io.BytesIO(b""))
    assert res.size_bytes == 0
    assert res.line_count == 0
    assert res.m620_events == []
    assert res.total_estimated_time is None
