"""Tests for the web UI server (F9 web shell)."""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pytest

from conftest import build_tiny_3mf
from hictopswapper.webui import serve_in_thread


@pytest.fixture
def server():
    srv, workspace, thread = serve_in_thread()
    base = f"http://127.0.0.1:{srv.server_port}"
    yield base, workspace
    srv.shutdown()
    srv.server_close()
    workspace.cleanup()


def _post(base: str, path: str, body: bytes,
          content_type: str = "application/octet-stream") -> dict:
    req = urllib.request.Request(
        base + path, data=body,
        headers={"Content-Type": content_type}, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def _get(base: str, path: str) -> bytes:
    with urllib.request.urlopen(base + path) as resp:
        return resp.read()


def test_index_served(server):
    base, _ = server
    html = _get(base, "/").decode()
    assert "HICTOP Swapper" in html
    assert "/api/files" in html


def test_printers(server):
    base, _ = server
    data = json.loads(_get(base, "/api/printers"))
    assert "A1" in data["printers"]


def test_upload_describes_plates(server, tmp_path: Path):
    base, _ = server
    tiny = build_tiny_3mf(tmp_path / "tiny.3mf")
    data = _post(base, "/api/files?name=tiny.3mf", tiny.read_bytes())
    assert data["file_id"]
    assert data["name"] == "tiny.3mf"
    assert len(data["plates"]) == 1
    plate = data["plates"][0]
    assert plate["time"] == "0h 1m 0s"
    assert [(f["id"], f["color"]) for f in plate["filaments"]] == [
        (1, "#FFFFFF"), (2, "#000000")]


def test_export_roundtrip(server, tmp_path: Path):
    base, _ = server
    tiny = build_tiny_3mf(tmp_path / "tiny.3mf")
    up = _post(base, "/api/files?name=tiny.3mf", tiny.read_bytes())
    out = _post(base, "/api/export", json.dumps({
        "items": [{"file_id": up["file_id"], "plate_index": 0, "repeats": 2}],
        "loops": 1, "printer": "A1", "filename": "job",
    }).encode(), content_type="application/json")
    assert out["filename"] == "job.3mf"
    assert out["report"]["ams_metadata_problems"] == []
    blob = _get(base, out["download"])
    with zipfile.ZipFile(__import__("io").BytesIO(blob)) as z:
        gcode = z.read("Metadata/plate_1.gcode")
        assert z.read("Metadata/plate_1.gcode.md5").decode() == \
            hashlib.md5(gcode).hexdigest()
        assert "开始换盘" in gcode.decode()  # swap block injected twice
        assert gcode.decode().count("开始换盘") == 2
        ms = z.read("Metadata/model_settings.config").decode()
        assert "filament_maps" in ms          # AMS maps preserved
        si = z.read("Metadata/slice_info.config").decode()
        assert 'color="#FFFFFF"' in si        # colors preserved
        assert "Metadata/custom_gcode_per_layer.xml" not in z.namelist()


def test_export_rejects_unknown_file(server):
    base, _ = server
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, "/api/export", json.dumps({
            "items": [{"file_id": "nope", "plate_index": 0, "repeats": 1}],
        }).encode(), content_type="application/json")
    assert exc.value.code == 400


def test_export_rejects_empty_playlist(server):
    base, _ = server
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, "/api/export", json.dumps({"items": []}).encode(),
              content_type="application/json")
    assert exc.value.code == 400
