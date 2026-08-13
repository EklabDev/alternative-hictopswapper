"""F1 — threemf_io: lazy 3MF zip reader / rewriting writer."""

from __future__ import annotations

import zipfile

import pytest

from hictopswapper.threemf_io import ThreeMFPackage

from conftest import build_tiny_3mf


def test_open_names_read(tiny_3mf):
    with ThreeMFPackage.open(tiny_3mf) as pkg:
        names = pkg.names()
        assert "Metadata/plate_1.gcode" in names
        assert "Metadata/model_settings.config" in names
        assert pkg.read("Metadata/plate_1.gcode.md5") == b"0" * 32
        text = pkg.read_text("Metadata/model_settings.config")
        assert "<config>" in text


def test_open_entry_streams(tiny_3mf):
    with ThreeMFPackage.open(tiny_3mf) as pkg:
        with pkg.open_entry("Metadata/plate_1.gcode") as f:
            data = f.read()
        assert data == pkg.read("Metadata/plate_1.gcode")


def test_context_manager_closes(tiny_3mf):
    pkg = ThreeMFPackage.open(tiny_3mf)
    with pkg:
        pass
    with pytest.raises(ValueError):
        pkg.read("Metadata/plate_1.gcode")


def test_plate_gcode_names_sorted_numerically(tmp_path):
    path = build_tiny_3mf(
        tmp_path / "multi.3mf",
        extra_entries={
            "Metadata/plate_10.gcode": b"p10",
            "Metadata/plate_2.gcode": b"p2",
        },
    )
    with ThreeMFPackage.open(path) as pkg:
        assert pkg.plate_gcode_names() == [
            "Metadata/plate_1.gcode",
            "Metadata/plate_2.gcode",
            "Metadata/plate_10.gcode",
        ]


def test_write_roundtrip_byte_identical(tiny_3mf, tmp_path):
    out = tmp_path / "copy.3mf"
    with ThreeMFPackage.open(tiny_3mf) as pkg:
        original = {n: pkg.read(n) for n in pkg.names()}
        pkg.write(out)
    with ThreeMFPackage.open(out) as pkg:
        assert set(pkg.names()) == set(original)
        for name, data in original.items():
            assert pkg.read(name) == data, name


def test_write_replacements_and_removals(tiny_3mf, tmp_path):
    out = tmp_path / "edited.3mf"
    with ThreeMFPackage.open(tiny_3mf) as pkg:
        original_names = pkg.names()
        pkg.write(
            out,
            replacements={
                "Metadata/plate_1.gcode": b"G1 X1\n",          # bytes
                "Metadata/plate_1.gcode.md5": "a" * 32,        # str
                "Metadata/new_entry.txt": "brand new",         # appended
            },
            removals={"Metadata/plate_2.gcode", "Metadata/custom_gcode_per_layer.xml"},
        )
    with ThreeMFPackage.open(out) as pkg:
        names = pkg.names()
        assert "Metadata/plate_2.gcode" not in names  # never existed, no crash
        assert "Metadata/custom_gcode_per_layer.xml" not in names
        assert "Metadata/new_entry.txt" in names
        assert pkg.read("Metadata/plate_1.gcode") == b"G1 X1\n"
        assert pkg.read("Metadata/plate_1.gcode.md5") == b"a" * 32
        assert pkg.read_text("Metadata/new_entry.txt") == "brand new"
        # untouched entries still identical
        for name in ("Metadata/model_settings.config", "Metadata/plate_1.png",
                     "3D/3dmodel.model"):
            assert name in names
    with ThreeMFPackage.open(tiny_3mf) as orig, ThreeMFPackage.open(out) as new:
        for name in ("Metadata/model_settings.config", "Metadata/plate_1.png"):
            assert orig.read(name) == new.read(name)
        # entry order preserved for carried-over entries
        carried = [n for n in original_names if n in set(new.names())]
        assert carried == [n for n in original_names
                           if n != "Metadata/custom_gcode_per_layer.xml"]


def test_write_output_is_valid_zip(tiny_3mf, tmp_path):
    out = tmp_path / "valid.3mf"
    with ThreeMFPackage.open(tiny_3mf) as pkg:
        pkg.write(out)
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
