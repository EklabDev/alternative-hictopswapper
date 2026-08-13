"""F7 — ams_map_preserver: build AMS-safe output metadata (the core fix).

The site replaces ``model_settings.config`` with a hardcoded template that
drops ``filament_map_mode`` / ``filament_maps`` / ``filament_volume_maps``,
and rebuilds ``slice_info.config`` filaments as bare ``id/used_m/used_g``
nodes, losing ``color`` / ``type`` / ``tray_info_idx`` / ``group_id``.
On multi-AMS printers the exported job then re-binds every filament to
AMS unit 1 and colors come out wrong.

The builders here keep the source plate's AMS fields and full filament
attributes, only collapsing the plate list to a single plate and updating
usage totals.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .metadata_parser import Filament, parse_model_settings, parse_slice_info

AMS_MODEL_KEYS = ("filament_map_mode", "filament_maps", "filament_volume_maps")

DEFAULT_PLATER_NAME = "自动换盘"

# metadata keys repointed at the collapsed single plate
_PLATE1_FILES = {
    "gcode_file": "Metadata/plate_1.gcode",
    "thumbnail_file": "Metadata/plate_1.png",
    "thumbnail_no_light_file": "Metadata/plate_no_light_1.png",
    "top_file": "Metadata/top_1.png",
    "pick_file": "Metadata/pick_1.png",
    "pattern_bbox_file": "Metadata/plate_1.json",
}


def _serialize(root: ET.Element) -> str:
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode")


def build_model_settings(source_text: str,
                         plater_name: str = DEFAULT_PLATER_NAME) -> str:
    """Single-plate ``model_settings`` that PRESERVES the AMS map fields."""
    root = ET.fromstring(source_text)
    plates = root.findall("plate")
    if not plates:
        raise ValueError("model_settings has no <plate>")

    keep = None
    for el in plates:
        md = {m.get("key"): m.get("value") for m in el.findall("metadata")}
        if md.get("gcode_file"):
            keep = el
            break
    if keep is None:
        keep = plates[0]
    for el in plates:
        if el is not keep:
            root.remove(el)

    for md in keep.findall("metadata"):
        key = md.get("key")
        if key == "plater_id":
            md.set("value", "1")
        elif key == "plater_name":
            md.set("value", plater_name)
        elif key in _PLATE1_FILES:
            md.set("value", _PLATE1_FILES[key])
        # filament_map_mode / filament_maps / filament_volume_maps untouched
    return _serialize(root)


def _fmt_usage(value: float) -> str:
    return f"{value:.2f}"


def build_slice_info(
    source_text: str,
    used: dict[int, tuple[float, float]],
    filament_sources: dict[int, Filament] | None = None,
    preserve: bool = True,
) -> str:
    """Single-plate ``slice_info`` with full filament attributes.

    ``used`` maps 1-based filament slot -> (total used_m, total used_g)
    across all plates × repeats × loops.  With ``preserve`` the filament
    nodes are cloned from ``filament_sources`` (color/type/tray_info_idx
    kept) and only ``used_m``/``used_g`` are updated; otherwise bare
    ``id/used_m=0/used_g=0`` nodes are emitted, exactly like the site.
    """
    root = ET.fromstring(source_text)
    plates = root.findall("plate")
    if not plates:
        raise ValueError("slice_info has no <plate>")
    keep = plates[0]
    for el in plates[1:]:
        root.remove(el)
    for md in keep.findall("metadata"):
        if md.get("key") == "index":
            md.set("value", "1")
        # filament_maps metadata untouched (site kept them too)

    for f_el in keep.findall("filament"):
        keep.remove(f_el)
    filament_sources = filament_sources or {}
    for slot in sorted(used):
        used_m, used_g = used[slot]
        src = filament_sources.get(slot)
        if preserve and src is not None:
            attrs = dict(src.attrs)
            attrs["id"] = str(slot)
            attrs["used_m"] = _fmt_usage(used_m)
            attrs["used_g"] = _fmt_usage(used_g)
        else:
            attrs = {"id": str(slot), "used_m": "0", "used_g": "0"}
        ET.SubElement(keep, "filament", attrs)
    return _serialize(root)


def collect_filament_sources(
    per_file_slice_info: list[str],
) -> dict[int, Filament]:
    """First-seen filament attribute record per slot, across source files."""
    out: dict[int, Filament] = {}
    for text in per_file_slice_info:
        si = parse_slice_info(text)
        for plate in si.plates:
            for fil in plate.filaments:
                out.setdefault(fil.id, fil)
    return out


def select_project_settings_source(
    items: list[tuple[int, list[int], int]],
) -> int:
    """Port of the site's ``ams_max_file_id`` selection.

    ``items``: ``(file_index, used_slot_ids, repeats)`` in playlist order.
    Returns the index of the file containing the highest used filament slot
    among items with repeats > 0.
    """
    best_slot = -1
    best_file = 0
    for file_index, slot_ids, repeats in items:
        for slot in slot_ids:
            s0 = slot - 1
            if best_slot < s0 and repeats > 0:
                best_slot = s0
                best_file = file_index
    return best_file


def merged_filament_maps(
    per_file_model_settings: list[str],
    slot_ids: list[int],
) -> list[int]:
    """AMS unit assignment per slot, preferring explicit source maps.

    Returns a 1-based-slot list where entry ``i`` is the AMS unit for
    filament slot ``i+1``.  Unlike the site (whose output effectively maps
    everything to AMS 1), each slot keeps the map value from the first
    source file that defines it.
    """
    if not slot_ids:
        return []
    size = max(slot_ids)
    result = [1] * size
    defined = [False] * size
    for text in per_file_model_settings:
        ms = parse_model_settings(text)
        for plate in ms.plates:
            if not plate.gcode_file:
                continue
            for i, unit in enumerate(plate.filament_maps[:size]):
                if unit and not defined[i]:
                    result[i] = unit
                    defined[i] = True
            break
    return result


def verify_ams_metadata(
    model_settings_text: str,
    slice_info_text: str,
) -> list[str]:
    """Structural AMS checks on exported metadata; returns problem strings."""
    problems: list[str] = []
    ms = parse_model_settings(model_settings_text)
    sliced = ms.sliced_plates()
    if not sliced:
        problems.append("model_settings: no plate with gcode_file")
    else:
        plate = sliced[0]
        if plate.filament_map_mode is None:
            problems.append("model_settings: filament_map_mode missing")
        if not plate.filament_maps:
            problems.append("model_settings: filament_maps missing")
    si = parse_slice_info(slice_info_text)
    if not si.plates:
        problems.append("slice_info: no plates")
    else:
        for fil in si.plates[0].filaments:
            if not fil.color:
                problems.append(f"slice_info: filament {fil.id} lost color")
            if not fil.type:
                problems.append(f"slice_info: filament {fil.id} lost type")
            if not fil.tray_info_idx:
                problems.append(
                    f"slice_info: filament {fil.id} lost tray_info_idx")
    return problems
