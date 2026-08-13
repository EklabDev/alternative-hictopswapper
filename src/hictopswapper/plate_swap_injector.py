"""F4 — plate_swap_injector: printer-specific plate-swap gcode injection.

Faithful port of the site's ``update_gcode()``: the swap block is inserted
immediately after the *last* ``set_gcode_claim_speed_level : 0`` marker,
separated by CRLF.  Swap snippets live in ``profiles/<id>_swap.gcode`` and
were extracted verbatim from the site's HTML radio options.
"""

from __future__ import annotations

from importlib import resources

CLAIM_SPEED_MARKER = "set_gcode_claim_speed_level : 0"


def available_printers() -> list[str]:
    out = []
    for entry in resources.files("hictopswapper.profiles").iterdir():
        if entry.name.endswith("_swap.gcode"):
            out.append(entry.name[: -len("_swap.gcode")].upper())
    return sorted(out)


def load_swap_gcode(printer_id: str) -> str:
    name = f"{printer_id.lower()}_swap.gcode"
    try:
        ref = resources.files("hictopswapper.profiles").joinpath(name)
        return ref.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ValueError(
            f"unknown printer profile {printer_id!r}; "
            f"available: {', '.join(available_printers())}"
        ) from None


def inject_swap_gcode(gcode: str, swap_gcode: str) -> str:
    """Insert ``swap_gcode`` after the last claim-speed-level marker.

    Exact port of the site's ``update_gcode`` — including the quirk that the
    swap text lands before the remainder of the matched line (the marker is
    normally the end of an ``M1002`` line, so the remainder is just EOL).
    """
    if not swap_gcode:
        return gcode
    idx = gcode.rfind(CLAIM_SPEED_MARKER)
    if idx == -1:
        return gcode
    return (
        gcode[:idx]
        + CLAIM_SPEED_MARKER
        + "\r\n"
        + swap_gcode
        + gcode[idx + len(CLAIM_SPEED_MARKER):]
    )
