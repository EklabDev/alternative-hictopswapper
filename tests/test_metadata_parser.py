"""F2 — metadata_parser: typed views over the fixture metadata files."""

from __future__ import annotations

import pytest

from hictopswapper.metadata_parser import (
    parse_filament_sequence,
    parse_model_settings,
    parse_plate_json,
    parse_project_settings,
    parse_slice_info,
)

from conftest import read_fixture


# ---------------------------------------------------------- model_settings
def test_parse_model_settings_three_plates():
    ms = parse_model_settings(read_fixture("model_settings.config"))
    assert len(ms.plates) == 3
    assert [p.plater_id for p in ms.plates] == [1, 2, 3]


def test_parse_model_settings_plate1_fields():
    ms = parse_model_settings(read_fixture("model_settings.config"))
    p1 = ms.plates[0]
    assert p1.gcode_file == "Metadata/plate_1.gcode"
    assert p1.thumbnail_file == "Metadata/plate_1.png"
    assert p1.filament_map_mode == "Auto For Flush"
    assert p1.filament_maps == [1] * 8
    assert p1.filament_volume_maps == [0] * 8


def test_parse_model_settings_sliced_plates():
    ms = parse_model_settings(read_fixture("model_settings.config"))
    sliced = ms.sliced_plates()
    assert len(sliced) == 1
    assert sliced[0].plater_id == 1
    # plates 2 and 3 have empty gcode_file
    assert ms.plates[1].gcode_file == ""
    assert ms.plates[2].gcode_file == ""
    # plate 2 has no filament_maps metadata at all
    assert ms.plates[1].filament_maps == []


# -------------------------------------------------------------- slice_info
def test_parse_slice_info_header():
    si = parse_slice_info(read_fixture("slice_info.config"))
    assert si.client_type == "slicer"
    assert si.client_version == "02.07.01.57"


def test_parse_slice_info_plate_metadata():
    si = parse_slice_info(read_fixture("slice_info.config"))
    assert len(si.plates) == 1
    plate = si.plates[0]
    assert plate.index == 1
    assert plate.printer_model_id == "N2S"
    assert plate.prediction == "54580"
    assert plate.weight == "72.31"
    assert plate.filament_maps == [1] * 8


def test_parse_slice_info_filaments():
    si = parse_slice_info(read_fixture("slice_info.config"))
    fils = {f.id: f for f in si.plates[0].filaments}
    assert sorted(fils) == [1, 3, 6]

    f1 = fils[1]
    assert f1.color == "#FFFFFF"
    assert f1.type == "PLA"
    assert f1.tray_info_idx == "GFL99"
    assert f1.used_m == pytest.approx(23.31)
    assert f1.used_g == pytest.approx(69.54)
    assert f1.group_id == "0"

    f3 = fils[3]
    assert f3.color == "#000000"
    assert f3.tray_info_idx == "GFA00"
    assert f3.used_m == pytest.approx(0.29)
    assert f3.used_g == pytest.approx(0.89)

    f6 = fils[6]
    assert f6.color == "#A4DAE6"
    assert f6.used_m == pytest.approx(0.62)
    assert f6.used_g == pytest.approx(1.88)

    # full attribute dict retained (extra attrs survive)
    assert f1.attrs["nozzle_diameter"] == "0.20"
    assert f1.attrs["used_for_object"] == "true"


# -------------------------------------------------------- project_settings
def test_parse_project_settings():
    ps = parse_project_settings(read_fixture("project_settings.config"))
    assert isinstance(ps, dict)
    assert ps["filament_map"] == ["1"] * 8
    assert ps["filament_map_mode"] == "Auto For Flush"
    assert ps["filament_colour"] == [
        "#FFFFFF", "#C52C18", "#000000", "#EEAECD",
        "#18C241", "#A4DAE6", "#F6DA5A", "#AC95D5",
    ]
    assert ps["filament_ids"] == [
        "GFL99", "GFL99", "GFA00", "GFL99", "GFL99", "GFA00", "GFL99", "GFL99"]
    assert ps["extruder_ams_count"] == ["1#0|4#0", "1#0|4#0"]


# ------------------------------------------------------------- plate_N.json
def test_parse_plate_json():
    pj = parse_plate_json(read_fixture("plate_1.json"))
    assert pj["filament_colors"] == ["#FFFFFF", "#000000", "#A4DAE6"]
    assert pj["filament_ids"] == [0, 2, 5]
    assert pj["first_extruder"] == 5
    assert pj["bed_type"] == "textured_plate"
    assert pj["version"] == 2


# ------------------------------------------------------- filament_sequence
def test_parse_filament_sequence():
    fs = parse_filament_sequence(read_fixture("filament_sequence.json"))
    assert fs["plate_1"]["sequence"] == [6, 1, 6, 1, 6, 1, 3, 1, 3, 1, 3, 1]
    assert fs["plate_1"]["optimal_assignment"] == [0] * 8
    assert fs["plate_2"]["sequence"] == []
    assert fs["plate_3"]["sequence"] == []
