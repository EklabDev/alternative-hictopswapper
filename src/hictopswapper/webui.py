"""Web UI server — stdlib-only HTTP frontend for the export pipeline.

Mirrors the hictopswapper.com workflow: drop sliced ``.gcode.3mf`` files,
set per-plate repeats / loops / printer profile, export one continuous
AMS-safe 3MF, download it from the browser.

API (all JSON unless noted):
  GET  /                      single-page UI (static/index.html)
  GET  /api/printers          available plate-swap profiles
  POST /api/files?name=...    raw request body = one .3mf; returns file_id
                              plus plate/filament/time metadata
  POST /api/export            {items: [{file_id, plate_index, repeats}],
                               loops, printer, filename, legacy}
                              → {download: url, report: {...}}
  GET  /api/download/<token>/<filename>
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .cli import run_export
from .metadata_parser import parse_model_settings, parse_slice_info
from .plate_swap_injector import available_printers
from .threemf_io import ThreeMFPackage

MAX_UPLOAD_BYTES = 512 * 1024 * 1024
_TIME_RE = re.compile(rb"total estimated time: ([^\r\n;]+)")


class Workspace:
    """Per-server-run temp storage for uploads and exports."""

    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="hictopswapper-"))
        (self.root / "exports").mkdir()
        self.uploads: dict[str, Path] = {}
        self.exports: dict[str, Path] = {}

    def add_upload(self, data: bytes) -> Path:
        file_id = uuid.uuid4().hex[:12]
        path = self.root / f"{file_id}.3mf"
        path.write_bytes(data)
        self.uploads[file_id] = path
        return path

    def upload(self, file_id: str) -> Path:
        if file_id not in self.uploads:
            raise KeyError(f"unknown file_id {file_id!r}")
        return self.uploads[file_id]

    def add_export(self, path: Path) -> str:
        token = uuid.uuid4().hex[:12]
        self.exports[token] = path
        return token

    def export(self, token: str) -> Path:
        if token not in self.exports:
            raise KeyError(f"unknown download token {token!r}")
        return self.exports[token]

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


def describe_file(path: Path) -> list[dict]:
    """Plate/filament/time metadata for the playlist UI."""
    with ThreeMFPackage.open(path) as pkg:
        ms = parse_model_settings(pkg.read_text("Metadata/model_settings.config"))
        si = parse_slice_info(pkg.read_text("Metadata/slice_info.config"))
        plates = []
        for plate in ms.sliced_plates():
            plate_pos = ms.plates.index(plate)
            si_plate = next(
                (pl for pl in si.plates if pl.index == plate_pos + 1),
                si.plates[0] if si.plates else None)
            with pkg.open_entry(plate.gcode_file) as f:
                head = f.read(65536)
            m = _TIME_RE.search(head)
            plates.append({
                "index": len(plates),
                "gcode_file": plate.gcode_file,
                "time": m.group(1).decode("utf-8", "replace").strip() if m else None,
                "filaments": [
                    {"id": fil.id, "color": fil.color, "type": fil.type,
                     "used_m": fil.used_m, "used_g": fil.used_g}
                    for fil in si_plate.filaments
                ] if si_plate else [],
            })
        return plates


def make_handler(workspace: Workspace) -> type[BaseHTTPRequestHandler]:

    class Handler(BaseHTTPRequestHandler):
        server_version = "hictopswapper-web/0.1"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # keep container logs terse
            pass

        # --------------------------------------------------------- helpers
        def _send_json(self, obj, status: int = 200) -> None:
            body = json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_error_json(self, status: int, message: str) -> None:
            self._send_json({"error": message}, status)

        # ------------------------------------------------------------- GET
        def do_GET(self) -> None:
            path = urlparse(self.path).path
            try:
                if path == "/":
                    body = resources.files("hictopswapper.static") \
                        .joinpath("index.html").read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif path == "/api/printers":
                    self._send_json({"printers": available_printers()})
                elif path.startswith("/api/download/"):
                    self._download(path)
                else:
                    self._send_error_json(404, "not found")
            except (KeyError, ValueError) as exc:
                self._send_error_json(400, str(exc))
            except Exception as exc:  # noqa: BLE001 - surface to UI
                self._send_error_json(500, f"{type(exc).__name__}: {exc}")

        def _download(self, path: str) -> None:
            parts = path.split("/", 4)
            if len(parts) < 5 or not parts[4]:
                raise ValueError("download URL must include a filename")
            token, filename = parts[3], parts[4]
            export_path = workspace.export(token)
            size = export_path.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition",
                             f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(size))
            self.end_headers()
            with open(export_path, "rb") as f:
                shutil.copyfileobj(f, self.wfile, 1 << 20)

        # ------------------------------------------------------------ POST
        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length <= 0:
                    raise ValueError("empty request body")
                if length > MAX_UPLOAD_BYTES:
                    raise ValueError("upload too large")
                if parsed.path == "/api/files":
                    self._upload(parsed, length)
                elif parsed.path == "/api/export":
                    self._export(length)
                else:
                    self._send_error_json(404, "not found")
            except (KeyError, ValueError) as exc:
                self._send_error_json(400, str(exc))
            except Exception as exc:  # noqa: BLE001 - surface to UI
                self._send_error_json(500, f"{type(exc).__name__}: {exc}")

        def _upload(self, parsed, length: int) -> None:
            name = parse_qs(parsed.query).get("name", ["plate.3mf"])[0]
            chunks, remaining = [], length
            while remaining > 0:
                chunk = self.rfile.read(min(remaining, 1 << 20))
                if not chunk:
                    raise ValueError("truncated upload")
                chunks.append(chunk)
                remaining -= len(chunk)
            path = workspace.add_upload(b"".join(chunks))
            self._send_json({
                "file_id": path.stem,
                "name": name,
                "plates": describe_file(path),
            })

        def _export(self, length: int) -> None:
            body = json.loads(self.rfile.read(length))
            items = body.get("items") or []
            if not items:
                raise ValueError("no playlist items")
            input_paths, repeats, plate_indices = [], [], []
            for item in items:
                input_paths.append(str(workspace.upload(item["file_id"])))
                repeats.append(int(item.get("repeats", 1)))
                plate_indices.append(int(item.get("plate_index", 0)))
            filename = (body.get("filename") or "自动换盘").strip() or "自动换盘"
            if not filename.endswith(".3mf"):
                filename += ".3mf"
            out_path = workspace.root / "exports" / f"{uuid.uuid4().hex[:12]}.3mf"
            report = run_export(
                input_paths=input_paths,
                out_path=str(out_path),
                repeats=repeats,
                loops=int(body.get("loops", 1)),
                printer=body.get("printer") or "A1",
                plate_indices=plate_indices,
                legacy=bool(body.get("legacy", False)),
            )
            token = workspace.add_export(out_path)
            self._send_json({
                "download": f"/api/download/{token}/{filename}",
                "filename": filename,
                "report": report,
            })

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8080) -> None:
    workspace = Workspace()
    server = ThreadingHTTPServer((host, port), make_handler(workspace))
    shown_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    print(f"hictopswapper web UI: http://{shown_host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        workspace.cleanup()


def serve_in_thread(host: str = "127.0.0.1", port: int = 0):
    """Test helper: returns (server, workspace, thread)."""
    workspace = Workspace()
    server = ThreadingHTTPServer((host, port), make_handler(workspace))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, workspace, thread
