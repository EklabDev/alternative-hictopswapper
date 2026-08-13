"""F6 — ams_boundary_cleaner: disable redundant AMS unload/reload at seams."""

from __future__ import annotations

from hictopswapper.ams_boundary_cleaner import (
    clean_ams_boundaries,
    comment_line_at,
    scan_m620_s,
)


# --------------------------------------------------------------- scan
def test_scan_offsets_and_slots():
    text = "G1 X0\nM620 S255\nM400\nM620 S2\nG1 X1\n"
    events = scan_m620_s(text)
    assert len(events) == 2
    off255, slot255 = events[0]
    off2, slot2 = events[1]
    assert text[off255:].startswith("M620 S255")
    assert slot255 == "255"
    assert text[off2:].startswith("M620 S2")
    # "M620 S2\n" -> 3rd char after the slot is the char after the newline,
    # not newline/space, so the raw 3-char window is kept (site quirk)
    assert slot2 == "2\nG"


def test_scan_slot_trimming():
    # 3rd char is a space -> trimmed to 2 chars
    assert scan_m620_s("\nM620 S12 A\n") == [(1, "12")]
    # 3rd char is a newline -> trimmed to 2 chars
    assert scan_m620_s("\nM620 S12\n") == [(1, "12")]
    # 3-digit slot kept whole
    assert scan_m620_s("\nM620 S255\n") == [(1, "255")]


def test_scan_requires_leading_newline():
    # "M620 S" at position 0 (no preceding \n) is not found
    assert scan_m620_s("M620 S1\n") == []


def test_comment_line_at():
    assert comment_line_at("ab\ncd", 3) == "ab\n;cd"
    # offset past end -> unchanged
    assert comment_line_at("ab", 5) == "ab"


# ------------------------------------------------------------- cleaning
def _plate(end_slot: str, tail: str = "") -> str:
    return (
        f"; plate\nM620 S{end_slot}\nG1 X0\n" + tail
    )


def test_clean_matching_boundary():
    # global events: S2, S255 | S2  -> unload+reload disabled
    item1 = "; plate A\nM620 S2\nG1 X0\nM620 S255\nM400\n"
    item2 = "; plate B\nM620 S2\nG1 X1\nM620 S255\n"
    items, n = clean_ams_boundaries([item1, item2])
    assert n == 2
    assert "\n;M620 S255\nM400\n" in items[0]   # unload commented
    assert "\n;M620 S2\nG1 X1\n" in items[1]    # reload commented
    # first load of slot 2 in item1 untouched (not at a boundary)
    assert "\nM620 S2\nG1 X0\n" in items[0]
    # trailing S255 of the LAST item untouched (no next event)
    assert items[1].endswith("\nM620 S255\n")


def test_clean_non_matching_slots_untouched():
    # S2, S255, S3 -> different filament after boundary: nothing disabled
    item1 = "; A\nM620 S2\nG1 X0\nM620 S255\n"
    item2 = "; B\nM620 S3\nG1 X1\n"
    items, n = clean_ams_boundaries([item1, item2])
    assert n == 0
    assert items == [item1, item2]


def test_clean_255_at_edges_ignored():
    # first and last events are never candidates (need i-1 and i+1)
    item = "\nM620 S255\nM400\nM620 S255\n"
    items, n = clean_ams_boundaries([item])
    assert n == 0
    assert items == [item]


def test_clean_multiple_boundaries_across_repeats():
    plate = "; p\nM620 S1\nG1 X0\nM620 S255\n"
    items, n = clean_ams_boundaries([plate, plate, plate])
    # boundaries between plate1/plate2 and plate2/plate3:
    # events S1,S255 | S1,S255 | S1,S255  ->  i=1 (255, 1==1) and i=3 (255, 1==1)
    assert n == 4
    assert items[0].count(";M620 S255") == 1
    assert items[1].count(";M620 S1") == 1
    assert items[1].count(";M620 S255") == 1
    assert items[2].count(";M620 S1") == 1
    # the very first load and very last unload survive
    assert "\nM620 S1\n" in items[0]
    assert items[2].endswith("M620 S255\n")


def test_clean_no_events():
    items, n = clean_ams_boundaries(["G1 X0\n", "G1 X1\n"])
    assert n == 0
    assert items == ["G1 X0\n", "G1 X1\n"]
