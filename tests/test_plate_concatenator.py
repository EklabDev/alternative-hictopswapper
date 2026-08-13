"""F5 — plate_concatenator: item expansion and final join."""

from __future__ import annotations

import pytest

from hictopswapper.plate_concatenator import (
    INI_GCODE,
    PLATE_SUFFIX,
    concatenate,
    expand_items,
)


def test_site_constants():
    # res/test.js: 自动换盘_gcode = ";\n\n\n", ini_gcode = ";\n"
    assert PLATE_SUFFIX == ";\n\n\n"
    assert INI_GCODE == ";\n"


def test_expand_single_loop():
    assert expand_items(["AAA", "BBB"], 1) == [
        INI_GCODE + "AAA" + PLATE_SUFFIX,
        "BBB" + PLATE_SUFFIX,
    ]


def test_expand_loops_repeat_sequence():
    assert expand_items(["A"], 3) == [
        INI_GCODE + "A" + PLATE_SUFFIX,
        "A" + PLATE_SUFFIX,
        "A" + PLATE_SUFFIX,
    ]
    out = expand_items(["A", "B"], 2)
    assert out == [
        INI_GCODE + "A" + PLATE_SUFFIX,
        "B" + PLATE_SUFFIX,
        "A" + PLATE_SUFFIX,
        "B" + PLATE_SUFFIX,
    ]
    # INI_GCODE only ever on the very first item
    assert sum(1 for it in out if it.startswith(INI_GCODE)) == 1


def test_expand_rejects_bad_loops():
    with pytest.raises(ValueError):
        expand_items(["A"], 0)


def test_concatenate_size():
    items = ["x" * 100, "y" * 250, "z"]
    loops = 2
    out = concatenate(items, loops)
    expected = (
        sum(len(i) for i in items) * loops
        + len(items) * loops * len(PLATE_SUFFIX)
        + len(INI_GCODE)
    )
    assert len(out) == expected


def test_concatenate_seam_structure():
    out = concatenate(["AAA", "BBB"], 2)
    assert out == (
        INI_GCODE
        + "AAA" + PLATE_SUFFIX
        + "BBB" + PLATE_SUFFIX
        + "AAA" + PLATE_SUFFIX
        + "BBB" + PLATE_SUFFIX
    )
    assert out.startswith(INI_GCODE)
    assert out.endswith(PLATE_SUFFIX)


def test_concatenate_empty():
    assert concatenate([], 1) == ""
    assert expand_items([], 1) == []
