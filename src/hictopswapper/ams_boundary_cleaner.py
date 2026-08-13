"""F6 — ams_boundary_cleaner: disable redundant AMS unload/reload at seams.

The site (V12.5) *intends* to comment out an intermediate ``M620 S255``
unload and the matching ``M620 S<n>`` reload when the same filament slot
continues across a plate boundary — but its ``disable_gcode_line2()`` is a
no-op (``return e``), so plates always do a full unload/reload cycle.

This module ports the site's detection logic verbatim and implements the
disabling for real: the ``M620`` line is commented out by inserting ``;``
at the start of the line.
"""

from __future__ import annotations

M620_S_MARKER = "\nM620 S"


def scan_m620_s(text: str) -> list[tuple[int, str]]:
    """All ``\\nM620 S`` events as ``(offset_of_M, slot_string)``.

    Slot-string parsing mirrors the site: take up to 3 chars after
    ``M620 S``; if the 3rd char is a newline or space, keep only 2.
    """
    events = []
    start = 0
    while True:
        idx = text.find(M620_S_MARKER, start)
        if idx == -1:
            break
        slot = text[idx + 7: idx + 10]
        if len(slot) == 3 and slot[2] in ("\n", " "):
            slot = slot[:2]
        events.append((idx + 1, slot))
        start = idx + 1
    return events


def comment_line_at(text: str, offset: int) -> str:
    """Comment out the line whose first char is at ``offset``."""
    if offset > len(text) - 1:
        return text
    return text[:offset] + ";" + text[offset:]


def clean_ams_boundaries(items: list[str]) -> tuple[list[str], int]:
    """Disable intermediate unload/reload when filament continues.

    ``items`` are the *individual* plate gcode strings before final join
    (same granularity the site scans at).  Returns the (possibly modified)
    items and the number of disabled ``M620 S`` lines.

    Detection rule (verbatim port): scanning the global event list across
    all items, when event ``i`` is slot ``255`` (unload) and the previous
    and next events name the same slot, the filament continues across the
    boundary — so the unload line (event ``i``) and the reload line
    (event ``i+1``) are commented out.
    """
    offsets: list[int] = []
    item_idx: list[int] = []
    slots: list[str] = []
    for i, item in enumerate(items):
        for off, slot in scan_m620_s(item):
            offsets.append(off)
            item_idx.append(i)
            slots.append(slot)

    # edits per item: {item_index: [offsets_to_comment]}
    edits: dict[int, list[int]] = {}
    disabled = 0
    for i in range(1, len(slots) - 1):
        if slots[i] == "255" and slots[i - 1] == slots[i + 1]:
            edits.setdefault(item_idx[i], []).append(offsets[i])
            edits.setdefault(item_idx[i + 1], []).append(offsets[i + 1])
            disabled += 2

    out = list(items)
    for i, offs in edits.items():
        # apply from the end of the string so earlier offsets stay valid
        for off in sorted(set(offs), reverse=True):
            out[i] = comment_line_at(out[i], off)
    return out, disabled
