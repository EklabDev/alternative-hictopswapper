"""F10 — diff_harness: structured A/B package comparison."""

from __future__ import annotations

import pytest

from hictopswapper.cli import LEGACY_MODEL_SETTINGS_TEMPLATE
from hictopswapper.ams_map_preserver import build_slice_info
from hictopswapper.diff_harness import diff_packages, format_report

from conftest import (
    REAL_INPUT_3MF,
    REAL_OUTPUT_3MF,
    TINY_GCODE,
    TINY_MODEL_SETTINGS,
    TINY_PROJECT_SETTINGS,
    TINY_SLICE_INFO,
    build_tiny_3mf,
    read_fixture,
)


def test_diff_package_with_itself(tiny_3mf):
    report = diff_packages(tiny_3mf, tiny_3mf)
    assert report.ok
    assert all(e.status == "same" for e in report.entries)
    assert report.metadata_diffs == []
    assert report.gcode_diffs == []
    text = format_report(report)
    assert "0 differing/missing" in text
    assert "metadata diffs: 0" in text
    assert "gcode diffs: 0" in text


def test_diff_detects_different_gcode(tmp_path):
    a = build_tiny_3mf(tmp_path / "a.3mf")
    b = build_tiny_3mf(tmp_path / "b.3mf", gcode=TINY_GCODE + "G1 X99\n")
    report = diff_packages(a, b)
    status = {e.name: e.status for e in report.entries}
    assert status["Metadata/plate_1.gcode"] == "different"
    assert status["Metadata/model_settings.config"] == "same"
    assert not report.ok
    assert any("gcode size" in d for d in report.gcode_diffs)
    text = format_report(report)
    assert "[different] Metadata/plate_1.gcode" in text


def test_diff_detects_missing_entries(tmp_path):
    a = build_tiny_3mf(tmp_path / "a.3mf")
    b = build_tiny_3mf(tmp_path / "b.3mf",
                       extra_entries={"Metadata/plate_2.gcode": b"p2"})
    report = diff_packages(a, b)
    status = {e.name: e.status for e in report.entries}
    assert status["Metadata/plate_2.gcode"] == "only_b"


def test_diff_detects_degraded_ams_metadata(tmp_path):
    """Preserved vs site-style (legacy) metadata -> metadata_diffs."""
    a = build_tiny_3mf(tmp_path / "a.3mf")
    bare_slice = build_slice_info(TINY_SLICE_INFO, {1: (1.5, 4.5)},
                                  preserve=False)
    degraded_model = LEGACY_MODEL_SETTINGS_TEMPLATE
    b = build_tiny_3mf(tmp_path / "b.3mf",
                       model_settings=degraded_model,
                       slice_info=bare_slice)
    report = diff_packages(a, b)
    assert any("filament_map_mode" in d for d in report.metadata_diffs)
    assert any("filament_maps" in d for d in report.metadata_diffs)
    assert any("filament 1.color" in d for d in report.metadata_diffs)
    assert any("filament 1.tray_info_idx" in d for d in report.metadata_diffs)


@pytest.mark.skipif(not (REAL_INPUT_3MF.exists() and REAL_OUTPUT_3MF.exists()),
                    reason="real 3MFs not present")
def test_diff_real_input_vs_site_output():
    """Regression catcher: the live-site output dropped the AMS maps and
    filament colors, so the diff must report them."""
    report = diff_packages(REAL_INPUT_3MF, REAL_OUTPUT_3MF)
    status = {e.name: e.status for e in report.entries}
    assert status["Metadata/model_settings.config"] == "different"
    assert status["Metadata/slice_info.config"] == "different"
    assert status["Metadata/plate_1.gcode"] == "different"
    assert any("filament_map_mode" in d for d in report.metadata_diffs)
    assert any("filament_maps" in d for d in report.metadata_diffs)
    assert any("filament 1.color" in d for d in report.metadata_diffs)
    assert any("filament 3.color" in d for d in report.metadata_diffs)
    # gcode: output is two plates concatenated -> bigger, has swap blocks
    assert any("gcode size" in d for d in report.gcode_diffs)
    assert any("swap blocks" in d for d in report.gcode_diffs)
