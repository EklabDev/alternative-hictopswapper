"""F8 — export_packager: MD5 helpers and final zip assembly."""

from __future__ import annotations

import hashlib
import io
import zipfile

import pytest

from hictopswapper.export_packager import (
    ALWAYS_REMOVE,
    build_removals,
    md5_hex_bytes,
    md5_hex_stream,
    package,
)
from hictopswapper.threemf_io import ThreeMFPackage

from conftest import INPUT_DIR, REAL_INPUT_3MF, build_tiny_3mf


# -------------------------------------------------------------------- md5
def test_md5_hex_bytes_matches_hashlib():
    data = b"some gcode blob \x00\x01" * 100
    assert md5_hex_bytes(data) == hashlib.md5(data).hexdigest()


def test_md5_hex_stream_matches_bytes_regardless_of_chunk_size():
    data = bytes(range(256)) * 1000
    for chunk in (1, 7, 4096, 2 * 1024 * 1024):
        assert md5_hex_stream(io.BytesIO(data), chunk_size=chunk) \
            == md5_hex_bytes(data)


@pytest.mark.skipif(not REAL_INPUT_3MF.exists(), reason="real 3MF not present")
def test_md5_stream_matches_bambu_sidecar():
    """SparkMD5 compatibility proof: streaming MD5 of the real 53MB
    plate_1.gcode equals the slicer-written plate_1.gcode.md5 sidecar."""
    expected = (INPUT_DIR / "plate_1.gcode.md5").read_text().strip().lower()
    with ThreeMFPackage.open(REAL_INPUT_3MF) as pkg:
        with pkg.open_entry("Metadata/plate_1.gcode") as f:
            assert md5_hex_stream(f) == expected


# ---------------------------------------------------------------- removals
def test_build_removals(tmp_path):
    path = build_tiny_3mf(
        tmp_path / "multi.3mf",
        extra_entries={"Metadata/plate_2.gcode": b"p2"},
    )
    with ThreeMFPackage.open(path) as pkg:
        removals = build_removals(pkg)
    assert removals == {
        "Metadata/plate_1.gcode",
        "Metadata/plate_2.gcode",
        "Metadata/custom_gcode_per_layer.xml",
    }
    assert "Metadata/custom_gcode_per_layer.xml" in ALWAYS_REMOVE


# ---------------------------------------------------------------- package
def test_package_replaces_and_removes(tmp_path):
    base_path = build_tiny_3mf(
        tmp_path / "base.3mf",
        extra_entries={"Metadata/plate_2.gcode": b"p2"},
    )
    out = tmp_path / "out.3mf"
    new_gcode = b"; concatenated\nG1 X1\n"
    with ThreeMFPackage.open(base_path) as base:
        untouched = {n: base.read(n) for n in (
            "Metadata/plate_1.png", "3D/3dmodel.model", "[Content_Types].xml")}
        digest = package(
            base, out, new_gcode,
            model_settings="<config/>",
            slice_info="<config><plate/></config>",
            project_settings="{}",
        )
    assert digest == hashlib.md5(new_gcode).hexdigest()
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        # removals
        assert "Metadata/plate_2.gcode" not in names
        assert "Metadata/custom_gcode_per_layer.xml" not in names
        # replacements
        assert z.read("Metadata/plate_1.gcode") == new_gcode
        assert z.read("Metadata/plate_1.gcode.md5").decode() == digest
        assert z.read("Metadata/model_settings.config") == b"<config/>"
        assert z.read("Metadata/slice_info.config") == b"<config><plate/></config>"
        assert z.read("Metadata/project_settings.config") == b"{}"
        # untouched entries byte-identical
        for name, data in untouched.items():
            assert z.read(name) == data


def test_package_accepts_bytes_metadata(tmp_path):
    base_path = build_tiny_3mf(tmp_path / "base.3mf")
    out = tmp_path / "out.3mf"
    with ThreeMFPackage.open(base_path) as base:
        package(base, out, b"g", b"<ms/>", b"<si/>", b"{}")
    with zipfile.ZipFile(out) as z:
        assert z.read("Metadata/model_settings.config") == b"<ms/>"
