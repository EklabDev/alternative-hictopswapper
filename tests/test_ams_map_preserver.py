"""F7 — ams_map_preserver: AMS-safe output metadata builders."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from hictopswapper.ams_map_preserver import (
    build_model_settings,
    build_slice_info,
    collect_filament_sources,
    merged_filament_maps,
    select_project_settings_source,
    verify_ams_metadata,
)
from hictopswapper.metadata_parser import parse_model_settings, parse_slice_info

from conftest import read_fixture

USED = {1: (46.62, 139.08), 3: (0.58, 1.78), 6: (1.24, 3.76)}


# ------------------------------------------------------ build_model_settings
def test_build_model_settings_collapses_to_one_plate():
    out = build_model_settings(read_fixture("model_settings.config"))
    ms = parse_model_settings(out)
    assert len(ms.plates) == 1
    plate = ms.plates[0]
    assert plate.plater_id == 1
    assert plate.plater_name == "自动换盘"
    assert plate.gcode_file == "Metadata/plate_1.gcode"


def test_build_model_settings_preserves_ams_fields():
    out = build_model_settings(read_fixture("model_settings.config"))
    plate = parse_model_settings(out).plates[0]
    assert plate.filament_map_mode == "Auto For Flush"
    assert plate.filament_maps == [1] * 8
    assert plate.filament_volume_maps == [0] * 8


def test_build_model_settings_repoints_plate1_files():
    out = build_model_settings(read_fixture("model_settings.config"))
    md = parse_model_settings(out).plates[0].metadata
    assert md["thumbnail_file"] == "Metadata/plate_1.png"
    assert md["thumbnail_no_light_file"] == "Metadata/plate_no_light_1.png"
    assert md["top_file"] == "Metadata/top_1.png"
    assert md["pick_file"] == "Metadata/pick_1.png"
    assert md["pattern_bbox_file"] == "Metadata/plate_1.json"


def test_build_model_settings_no_plate_raises():
    with pytest.raises(ValueError):
        build_model_settings("<config></config>")


# -------------------------------------------------------- build_slice_info
def _sources():
    return collect_filament_sources([read_fixture("slice_info.config")])


def test_build_slice_info_preserve_keeps_full_attrs():
    out = build_slice_info(read_fixture("slice_info.config"), USED,
                           filament_sources=_sources(), preserve=True)
    si = parse_slice_info(out)
    assert len(si.plates) == 1
    assert si.plates[0].index == 1
    fils = {f.id: f for f in si.plates[0].filaments}
    assert sorted(fils) == [1, 3, 6]  # ascending slot order
    f1 = fils[1]
    assert f1.color == "#FFFFFF"
    assert f1.type == "PLA"
    assert f1.tray_info_idx == "GFL99"
    assert f1.group_id == "0"
    # totals updated, formatted %.2f
    assert 'used_m="46.62"' in out
    assert 'used_g="139.08"' in out
    assert f1.used_m == pytest.approx(46.62)
    # untouched source attrs survive
    assert fils[3].color == "#000000"
    assert fils[6].tray_info_idx == "GFA00"
    assert fils[6].used_m == pytest.approx(1.24)


def test_build_slice_info_bare_matches_site_behavior():
    """preserve=False emits bare id/used_m=0/used_g=0 nodes, exactly like
    the live site (see fixtures/output/slice_info.config)."""
    out = build_slice_info(read_fixture("slice_info.config"), USED,
                           preserve=False)
    si = parse_slice_info(out)
    fils = si.plates[0].filaments
    assert [f.id for f in fils] == [1, 3, 6]
    for f in fils:
        assert f.color is None
        assert f.type is None
        assert f.tray_info_idx is None
        assert f.used_m == 0.0
        assert f.used_g == 0.0
        assert set(f.attrs) == {"id", "used_m", "used_g"}
    # and the actual site output has exactly this shape
    site = parse_slice_info(read_fixture("slice_info.config", side="output"))
    site_fils = site.plates[0].filaments
    assert [f.id for f in site_fils] == [1, 3, 6]
    for f in site_fils:
        assert set(f.attrs) == {"id", "used_m", "used_g"}


def test_build_slice_info_preserve_without_source_falls_back_to_bare():
    out = build_slice_info(read_fixture("slice_info.config"), {9: (1.0, 2.0)},
                           filament_sources={}, preserve=True)
    fils = parse_slice_info(out).plates[0].filaments
    assert [f.id for f in fils] == [9]
    assert fils[0].color is None


# --------------------------------------------------- collect_filament_sources
def test_collect_filament_sources_first_seen_wins():
    si_a = read_fixture("slice_info.config")
    # second file redefines slot 1 with a different color -> ignored
    si_b = si_a.replace('color="#FFFFFF"', 'color="#123456"')
    sources = collect_filament_sources([si_a, si_b])
    assert sorted(sources) == [1, 3, 6]
    assert sources[1].color == "#FFFFFF"


# ---------------------------------------------- select_project_settings_source
def test_select_project_settings_source_single():
    assert select_project_settings_source([(0, [1, 3, 6], 1)]) == 0


def test_select_project_settings_source_highest_slot_wins():
    items = [(0, [1, 2], 1), (1, [3, 6], 1), (2, [4], 1)]
    assert select_project_settings_source(items) == 1  # slot 6 is highest


def test_select_project_settings_source_zero_repeats_excluded():
    items = [(0, [1], 1), (1, [8], 0), (2, [3], 2)]
    assert select_project_settings_source(items) == 2


def test_select_project_settings_source_all_zero_repeats():
    assert select_project_settings_source([(0, [5], 0), (1, [6], 0)]) == 0


# ------------------------------------------------------- merged_filament_maps
def test_merged_filament_maps_from_fixture():
    merged = merged_filament_maps(
        [read_fixture("model_settings.config")], [1, 3, 6])
    assert merged == [1] * 6  # sized by max slot, all AMS unit 1


def test_merged_filament_maps_defaults_to_ams1():
    merged = merged_filament_maps(["<config></config>"], [1, 4])
    assert merged == [1, 1, 1, 1]


def test_merged_filament_maps_empty_slots():
    assert merged_filament_maps(["<config></config>"], []) == []


# ------------------------------------------------------- verify_ams_metadata
def test_verify_flags_site_degraded_metadata():
    problems = verify_ams_metadata(
        read_fixture("model_settings.config", side="output"),
        read_fixture("slice_info.config", side="output"),
    )
    assert "model_settings: filament_map_mode missing" in problems
    assert "model_settings: filament_maps missing" in problems
    for slot in (1, 3, 6):
        assert f"slice_info: filament {slot} lost color" in problems
        assert f"slice_info: filament {slot} lost type" in problems
        assert f"slice_info: filament {slot} lost tray_info_idx" in problems


def test_verify_preserved_metadata_is_clean():
    ms_out = build_model_settings(read_fixture("model_settings.config"))
    si_out = build_slice_info(read_fixture("slice_info.config"), USED,
                              filament_sources=_sources(), preserve=True)
    assert verify_ams_metadata(ms_out, si_out) == []


def test_verify_no_sliced_plate():
    ms = '<config><plate><metadata key="gcode_file" value=""/></plate></config>'
    problems = verify_ams_metadata(ms, read_fixture("slice_info.config"))
    assert "model_settings: no plate with gcode_file" in problems


def test_builders_emit_parseable_xml():
    ms_out = build_model_settings(read_fixture("model_settings.config"))
    si_out = build_slice_info(read_fixture("slice_info.config"), USED,
                              filament_sources=_sources())
    assert ET.fromstring(ms_out).tag == "config"
    assert ET.fromstring(si_out).tag == "config"
