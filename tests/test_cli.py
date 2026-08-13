"""F9 — cli: run_export pipeline and argparse shell."""

from __future__ import annotations

import hashlib
import zipfile

import pytest

from hictopswapper.cli import main, run_export
from hictopswapper.metadata_parser import parse_model_settings, parse_slice_info

from conftest import (
    REAL_INPUT_3MF,
    TINY_SLICE_INFO,
    build_tiny_3mf,
)


# ------------------------------------------------------- fast synthetic path
def test_run_export_tiny(tmp_path):
    a = build_tiny_3mf(tmp_path / "a.3mf")
    b = build_tiny_3mf(
        tmp_path / "b.3mf",
        project_settings='{"source": "b"}',
    )
    out = tmp_path / "out.3mf"
    report = run_export([str(a), str(b)], str(out), repeats=[1, 1])
    assert report["out_path"] == str(out)
    assert report["plates"] == ["Metadata/plate_1.gcode"] * 2
    assert report["legacy"] is False
    assert report["gcode_md5"]
    # both files use slots up to 2 -> tie broken by first-seen (file a);
    # project_settings comes from the selected file
    with zipfile.ZipFile(out) as z:
        assert "Metadata/plate_2.gcode" not in z.namelist()
        assert "Metadata/custom_gcode_per_layer.xml" not in z.namelist()
        assert z.read("Metadata/plate_1.gcode.md5").decode() \
            == hashlib.md5(z.read("Metadata/plate_1.gcode")).hexdigest()
        # swap block injected once per playlist item
        gcode = z.read("Metadata/plate_1.gcode")
        assert gcode.count("开始换盘".encode("utf-8")) == 2


def test_run_export_selects_project_settings_from_highest_slot(tmp_path):
    a = build_tiny_3mf(tmp_path / "a.3mf",
                       project_settings='{"source": "a"}')
    # file b uses slot 9 -> highest slot -> its project_settings wins
    si_b = TINY_SLICE_INFO.replace('<filament id="2" ', '<filament id="9" ')
    b = build_tiny_3mf(tmp_path / "b.3mf", slice_info=si_b,
                       project_settings='{"source": "b"}')
    out = tmp_path / "out.3mf"
    report = run_export([str(a), str(b)], str(out))
    assert report["project_settings_source"] == str(b)
    with zipfile.ZipFile(out) as z:
        assert z.read("Metadata/project_settings.config") == b'{"source": "b"}'


def test_run_export_repeats_and_loops_scale_usage(tmp_path):
    a = build_tiny_3mf(tmp_path / "a.3mf")
    out = tmp_path / "out.3mf"
    report = run_export([str(a)], str(out), repeats=[2], loops=3)
    # tiny slice_info: slot 1 = 1.50m/4.50g, slot 2 = 0.50m/1.50g; x2 x3
    assert report["filaments_used"][1]["used_m"] == pytest.approx(9.0)
    assert report["filaments_used"][1]["used_g"] == pytest.approx(27.0)
    assert report["filaments_used"][2]["used_m"] == pytest.approx(3.0)


def test_run_export_validation_errors(tmp_path):
    a = build_tiny_3mf(tmp_path / "a.3mf")
    with pytest.raises(ValueError, match="no input files"):
        run_export([], str(tmp_path / "o.3mf"))
    with pytest.raises(ValueError, match="repeats count"):
        run_export([str(a)], str(tmp_path / "o.3mf"), repeats=[1, 2])
    with pytest.raises(ValueError, match="repeats must be"):
        run_export([str(a)], str(tmp_path / "o.3mf"), repeats=[0])
    with pytest.raises(ValueError, match="loops must be"):
        run_export([str(a)], str(tmp_path / "o.3mf"), loops=0)
    with pytest.raises(ValueError, match="plate index"):
        run_export([str(a)], str(tmp_path / "o.3mf"), plate_index=5)
    with pytest.raises(ValueError, match="unknown printer profile"):
        run_export([str(a)], str(tmp_path / "o.3mf"), printer="NOPE")


def test_run_export_no_swap_with_printer_none(tmp_path):
    a = build_tiny_3mf(tmp_path / "a.3mf")
    out = tmp_path / "out.3mf"
    report = run_export([str(a)], str(out), printer="none")
    with zipfile.ZipFile(out) as z:
        gcode = z.read("Metadata/plate_1.gcode")
    assert "开始换盘".encode("utf-8") not in gcode
    assert report["gcode_bytes"] == len(gcode)


# ------------------------------------------------------------- argparse CLI
def test_main_analyze(tiny_3mf, capsys):
    assert main(["analyze", str(tiny_3mf)]) == 0
    out = capsys.readouterr().out
    assert "total estimated time: 0h 1m 0s" in out
    assert "filaments: [1, 2]" in out
    assert "M620/M621 events: 3" in out
    assert "S255 unloads: 1" in out


def test_main_diff_self(tiny_3mf, capsys):
    assert main(["diff", str(tiny_3mf), str(tiny_3mf)]) == 0
    out = capsys.readouterr().out
    assert "0 differing/missing" in out


def test_main_export_tiny(tmp_path, capsys):
    a = build_tiny_3mf(tmp_path / "a.3mf")
    out = tmp_path / "out.3mf"
    rc = main(["export", str(a), "-o", str(out), "--repeats", "2",
               "--printer", "A1"])
    assert rc == 0  # no AMS metadata problems in preserve mode
    assert out.exists()
    printed = capsys.readouterr().out
    assert "exported:" in printed
    assert "AMS boundaries cleaned:" in printed


# ------------------------------------------- real end-to-end (slow, 53MB)
needs_real = pytest.mark.skipif(
    not REAL_INPUT_3MF.exists(), reason="real 3MF not present")


@pytest.fixture(scope="module")
def real_export(tmp_path_factory):
    out = tmp_path_factory.mktemp("export") / "out.3mf"
    report = run_export([str(REAL_INPUT_3MF)], str(out), repeats=[2])
    return report, out


@pytest.fixture(scope="module")
def real_export_legacy(tmp_path_factory):
    out = tmp_path_factory.mktemp("export_legacy") / "out.3mf"
    report = run_export([str(REAL_INPUT_3MF)], str(out), repeats=[2],
                        legacy=True)
    return report, out


@needs_real
class TestRealExport:
    def test_zip_structure(self, real_export):
        _, out = real_export
        with zipfile.ZipFile(out) as z:
            names = z.namelist()
            assert "Metadata/plate_1.gcode" in names
            assert "Metadata/plate_1.gcode.md5" in names
            assert "Metadata/plate_2.gcode" not in names
            assert "Metadata/plate_3.gcode" not in names
            assert "Metadata/custom_gcode_per_layer.xml" not in names
            assert z.testzip() is None

    def test_md5_sidecar_matches_gcode(self, real_export):
        report, out = real_export
        with zipfile.ZipFile(out) as z:
            gcode = z.read("Metadata/plate_1.gcode")
            sidecar = z.read("Metadata/plate_1.gcode.md5").decode()
        assert sidecar == hashlib.md5(gcode).hexdigest() == report["gcode_md5"]
        # swap block injected once per repeat
        assert gcode.count("开始换盘".encode("utf-8")) == 2

    def test_preserve_mode_keeps_ams_metadata(self, real_export):
        report, out = real_export
        assert report["legacy"] is False
        assert report["ams_metadata_problems"] == []
        with zipfile.ZipFile(out) as z:
            ms = parse_model_settings(
                z.read("Metadata/model_settings.config").decode("utf-8"))
            si = parse_slice_info(
                z.read("Metadata/slice_info.config").decode("utf-8"))
        plate = ms.sliced_plates()[0]
        assert plate.filament_map_mode == "Auto For Flush"
        assert plate.filament_maps == [1] * 8
        assert plate.filament_volume_maps == [0] * 8
        assert plate.plater_name == "自动换盘"
        fils = {f.id: f for f in si.plates[0].filaments}
        assert sorted(fils) == [1, 3, 6]
        assert fils[1].color == "#FFFFFF"
        assert fils[1].type == "PLA"
        assert fils[1].tray_info_idx == "GFL99"
        # usage totals doubled by repeats=2
        assert fils[1].used_m == pytest.approx(23.31 * 2)
        assert fils[1].used_g == pytest.approx(69.54 * 2)
        assert fils[3].used_m == pytest.approx(0.29 * 2)
        assert fils[6].used_g == pytest.approx(1.88 * 2)

    def test_legacy_mode_reproduces_site_behavior(self, real_export_legacy):
        report, out = real_export_legacy
        assert report["legacy"] is True
        with zipfile.ZipFile(out) as z:
            names = z.namelist()
            assert "Metadata/plate_2.gcode" not in names
            assert "Metadata/custom_gcode_per_layer.xml" not in names
            gcode = z.read("Metadata/plate_1.gcode")
            sidecar = z.read("Metadata/plate_1.gcode.md5").decode()
            assert sidecar == hashlib.md5(gcode).hexdigest()
            ms = parse_model_settings(
                z.read("Metadata/model_settings.config").decode("utf-8"))
            si = parse_slice_info(
                z.read("Metadata/slice_info.config").decode("utf-8"))
        # hardcoded template: AMS map fields dropped
        plate = ms.sliced_plates()[0]
        assert plate.plater_name == "自动换盘"
        assert plate.filament_map_mode is None
        assert plate.filament_maps == []
        # bare filament nodes, colors/type/tray gone, usage zeroed
        fils = {f.id: f for f in si.plates[0].filaments}
        assert sorted(fils) == [1, 3, 6]
        for f in fils.values():
            assert f.color is None
            assert f.type is None
            assert f.tray_info_idx is None
            assert f.used_m == 0.0
            assert f.used_g == 0.0
