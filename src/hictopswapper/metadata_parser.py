"""F2 — metadata_parser: typed views over Bambu 3MF metadata files.

Parses ``model_settings.config`` / ``slice_info.config`` (XML),
``project_settings.config`` (JSON), ``plate_N.json`` and
``filament_sequence.json`` into plain dataclasses/dicts.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field


# ------------------------------------------------------------- model_settings
@dataclass
class PlateMeta:
    plater_id: int
    plater_name: str
    gcode_file: str
    thumbnail_file: str
    filament_map_mode: str | None
    filament_maps: list[int]
    filament_volume_maps: list[int]
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class ModelSettings:
    plates: list[PlateMeta]

    def sliced_plates(self) -> list[PlateMeta]:
        """Plates that actually carry a gcode file."""
        return [p for p in self.plates if p.gcode_file]


def _parse_int_list(value: str | None) -> list[int]:
    if not value:
        return []
    return [int(v) for v in value.replace(",", " ").split()]


def _plate_metadata(plate_el: ET.Element) -> dict[str, str]:
    out = {}
    for md in plate_el.findall("metadata"):
        out[md.get("key", "")] = md.get("value", "")
    return out


def parse_model_settings(text: str) -> ModelSettings:
    root = ET.fromstring(text)
    plates = []
    for plate_el in root.findall("plate"):
        md = _plate_metadata(plate_el)
        plates.append(PlateMeta(
            plater_id=int(md.get("plater_id", "0") or 0),
            plater_name=md.get("plater_name", ""),
            gcode_file=md.get("gcode_file", ""),
            thumbnail_file=md.get("thumbnail_file", ""),
            filament_map_mode=md.get("filament_map_mode"),
            filament_maps=_parse_int_list(md.get("filament_maps")),
            filament_volume_maps=_parse_int_list(md.get("filament_volume_maps")),
            metadata=md,
        ))
    return ModelSettings(plates=plates)


# ---------------------------------------------------------------- slice_info
@dataclass
class Filament:
    id: int
    color: str | None
    type: str | None
    tray_info_idx: str | None
    used_m: float
    used_g: float
    group_id: str | None
    attrs: dict[str, str] = field(default_factory=dict)


@dataclass
class SlicePlate:
    index: int
    printer_model_id: str | None
    prediction: str | None
    weight: str | None
    filament_maps: list[int]
    filaments: list[Filament]
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class SliceInfo:
    client_type: str | None
    client_version: str | None
    plates: list[SlicePlate]


def parse_filament_el(el: ET.Element) -> Filament:
    attrs = dict(el.attrib)
    def _f(key: str) -> float:
        try:
            return float(attrs.get(key, "0") or 0)
        except ValueError:
            return 0.0
    return Filament(
        id=int(attrs.get("id", "0") or 0),
        color=attrs.get("color"),
        type=attrs.get("type"),
        tray_info_idx=attrs.get("tray_info_idx"),
        used_m=_f("used_m"),
        used_g=_f("used_g"),
        group_id=attrs.get("group_id"),
        attrs=attrs,
    )


def parse_slice_info(text: str) -> SliceInfo:
    root = ET.fromstring(text)
    header = root.find("header")
    client_type = client_version = None
    if header is not None:
        for item in header.findall("header_item"):
            if item.get("key") == "X-BBL-Client-Type":
                client_type = item.get("value")
            elif item.get("key") == "X-BBL-Client-Version":
                client_version = item.get("value")
    plates = []
    for plate_el in root.findall("plate"):
        md = _plate_metadata(plate_el)
        plates.append(SlicePlate(
            index=int(md.get("index", "0") or 0),
            printer_model_id=md.get("printer_model_id"),
            prediction=md.get("prediction"),
            weight=md.get("weight"),
            filament_maps=_parse_int_list(md.get("filament_maps")),
            filaments=[parse_filament_el(f) for f in plate_el.findall("filament")],
            metadata=md,
        ))
    return SliceInfo(client_type=client_type, client_version=client_version, plates=plates)


# ---------------------------------------------------------- project_settings
def parse_project_settings(text: str) -> dict:
    """``project_settings.config`` is a flat JSON object (values str or list)."""
    return json.loads(text)


# ------------------------------------------------------------- plate_N.json
def parse_plate_json(text: str) -> dict:
    return json.loads(text)


# ------------------------------------------------------ filament_sequence
def parse_filament_sequence(text: str) -> dict:
    return json.loads(text)
