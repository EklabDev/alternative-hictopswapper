"""Shared fixtures: fixture paths and a tiny synthetic 3MF builder."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
INPUT_DIR = FIXTURES / "input"
OUTPUT_DIR = FIXTURES / "output"

PROJECT_ROOT = Path(__file__).parent.parent
REAL_INPUT_3MF = PROJECT_ROOT / "hictop input" / "CAD Coin Hong Kong Version_plate_1.gcode.3mf"
REAL_OUTPUT_3MF = PROJECT_ROOT / "hictop output" / "CAD Coin Hong Kong Version.swap.gcode.3mf"


def read_fixture(name: str, side: str = "input") -> str:
    return (FIXTURES / side / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------- tiny 3MF
TINY_MODEL_SETTINGS = """<?xml version="1.0" encoding="UTF-8"?>
<config>
  <plate>
    <metadata key="plater_id" value="1"/>
    <metadata key="plater_name" value=""/>
    <metadata key="locked" value="false"/>
    <metadata key="filament_map_mode" value="Auto For Flush"/>
    <metadata key="filament_maps" value="1 1 1 1 1 1 1 1"/>
    <metadata key="filament_volume_maps" value="0 0 0 0 0 0 0 0"/>
    <metadata key="gcode_file" value="Metadata/plate_1.gcode"/>
    <metadata key="thumbnail_file" value="Metadata/plate_1.png"/>
    <metadata key="thumbnail_no_light_file" value="Metadata/plate_no_light_1.png"/>
    <metadata key="top_file" value="Metadata/top_1.png"/>
    <metadata key="pick_file" value="Metadata/pick_1.png"/>
    <metadata key="pattern_bbox_file" value="Metadata/plate_1.json"/>
  </plate>
</config>
"""

TINY_SLICE_INFO = """<?xml version="1.0" encoding="UTF-8"?>
<config>
  <header>
    <header_item key="X-BBL-Client-Type" value="slicer"/>
    <header_item key="X-BBL-Client-Version" value="02.07.01.57"/>
  </header>
  <plate>
    <metadata key="index" value="1"/>
    <metadata key="printer_model_id" value="N2S"/>
    <metadata key="prediction" value="60"/>
    <metadata key="weight" value="5.00"/>
    <metadata key="filament_maps" value="1 1 1 1 1 1 1 1"/>
    <filament id="1" tray_info_idx="GFL99" type="PLA" color="#FFFFFF" used_m="1.50" used_g="4.50" group_id="0"/>
    <filament id="2" tray_info_idx="GFA00" type="PLA" color="#000000" used_m="0.50" used_g="1.50" group_id="0"/>
  </plate>
</config>
"""

TINY_PROJECT_SETTINGS = '{"filament_map": ["1", "1"], "filament_map_mode": "Auto For Flush"}'

# one load of slot 1, one unload at the end, two claim-speed markers
TINY_GCODE = (
    "; HEADER_BLOCK_START\n"
    "; total estimated time: 0h 1m 0s\n"
    "; filament: 1,2\n"
    "; HEADER_BLOCK_END\n"
    "M1002 set_gcode_claim_speed_level : 1\n"
    "M620 S1\n"
    "G1 X10 F1000\n"
    "M1002 set_gcode_claim_speed_level : 0\n"
    "G1 X20\n"
    "M620 S255\n"
    "M621 S255\n"
)


def build_tiny_3mf(
    path: Path,
    *,
    model_settings: str = TINY_MODEL_SETTINGS,
    slice_info: str = TINY_SLICE_INFO,
    project_settings: str = TINY_PROJECT_SETTINGS,
    gcode: str = TINY_GCODE,
    extra_entries: dict[str, bytes | str] | None = None,
) -> Path:
    """Write a minimal but structurally valid .gcode.3mf zip."""
    entries: dict[str, bytes | str] = {
        "[Content_Types].xml": b"<Types/>",
        "3D/3dmodel.model": b"<model/>",
        "Metadata/model_settings.config": model_settings,
        "Metadata/slice_info.config": slice_info,
        "Metadata/project_settings.config": project_settings,
        "Metadata/plate_1.gcode": gcode,
        "Metadata/plate_1.gcode.md5": "0" * 32,
        "Metadata/plate_1.json": "{}",
        "Metadata/plate_1.png": b"\x89PNG-tiny",
        "Metadata/custom_gcode_per_layer.xml": b"<custom/>",
    }
    if extra_entries:
        entries.update(extra_entries)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items():
            if isinstance(data, str):
                data = data.encode("utf-8")
            z.writestr(name, data)
    return path


@pytest.fixture
def tiny_3mf(tmp_path: Path) -> Path:
    return build_tiny_3mf(tmp_path / "tiny.3mf")
