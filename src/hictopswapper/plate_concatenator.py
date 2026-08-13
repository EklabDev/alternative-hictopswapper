"""F5 — plate_concatenator: sequential join of prepared plate gcodes.

Faithful port of the site's ``export_3mf`` assembly:
every plate item gets ``PLATE_SUFFIX`` appended, the whole sequence is
repeated ``loops`` times, and ``INI_GCODE`` is prepended to the first item.
"""

from __future__ import annotations

# Site constants (res/test.js): 自动换盘_gcode and ini_gcode.
PLATE_SUFFIX = ";\n\n\n"
INI_GCODE = ";\n"


def expand_items(items: list[str], loops: int = 1) -> list[str]:
    """Per-item assembly: suffix each item, repeat the sequence ``loops``
    times, prepend ``INI_GCODE`` to the very first item.

    The returned list matches the site's post-expansion array ``c`` — the
    granularity at which the AMS boundary scan runs.
    """
    if loops < 1:
        raise ValueError("loops must be >= 1")
    sequence = [item + PLATE_SUFFIX for item in items] * loops
    if sequence:
        sequence[0] = INI_GCODE + sequence[0]
    return sequence


def concatenate(items: list[str], loops: int = 1) -> str:
    """Join plate gcode items into one continuous-print blob."""
    return "".join(expand_items(items, loops))
