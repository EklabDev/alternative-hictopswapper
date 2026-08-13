"""F4 — plate_swap_injector: swap-block injection after the last marker."""

from __future__ import annotations

import pytest

from hictopswapper.plate_swap_injector import (
    CLAIM_SPEED_MARKER,
    available_printers,
    inject_swap_gcode,
    load_swap_gcode,
)


def test_available_printers():
    assert "A1" in available_printers()


def test_load_a1_profile():
    swap = load_swap_gcode("A1")
    assert "开始换盘" in swap
    assert "G380" in swap  # A1 bed-probe moves, from the site HTML


def test_load_profile_case_insensitive():
    assert load_swap_gcode("a1") == load_swap_gcode("A1")


def test_load_unknown_profile():
    with pytest.raises(ValueError, match="unknown printer profile"):
        load_swap_gcode("NOPE")


def test_inject_after_last_marker():
    gcode = (
        f"AAA {CLAIM_SPEED_MARKER}\n"
        "middle\n"
        f"BBB {CLAIM_SPEED_MARKER}\n"
        "tail\n"
    )
    swap = ";SWAP\nG1 X0"
    out = inject_swap_gcode(gcode, swap)
    last = gcode.rfind(CLAIM_SPEED_MARKER)
    # swap lands immediately after the LAST marker, separated by CRLF
    assert out.index(swap) == last + len(CLAIM_SPEED_MARKER) + 2
    assert out == (
        gcode[:last]
        + CLAIM_SPEED_MARKER
        + "\r\n"
        + swap
        + "\ntail\n"          # remainder of the matched line is preserved
    )
    # first marker untouched
    assert out.startswith(f"AAA {CLAIM_SPEED_MARKER}\nmiddle\n")


def test_inject_no_marker_returns_input():
    gcode = "G1 X1\nM620 S1\n"
    assert inject_swap_gcode(gcode, ";SWAP") == gcode


def test_inject_empty_swap_returns_input():
    gcode = f"AAA {CLAIM_SPEED_MARKER}\n"
    assert inject_swap_gcode(gcode, "") == gcode


def test_inject_roundtrip_with_real_profile():
    swap = load_swap_gcode("A1")
    gcode = f"start\n{CLAIM_SPEED_MARKER}\nend\n"
    out = inject_swap_gcode(gcode, swap)
    assert "开始换盘" in out
    assert out.endswith("\nend\n")
