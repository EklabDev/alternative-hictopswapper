"""F8 — export_packager: write the final downloadable ``.gcode.3mf``.

Mirrors the site's export: the first input file is the base zip, all
``Metadata/plate_N.gcode`` entries and ``custom_gcode_per_layer.xml`` are
removed, metadata configs are replaced, and the concatenated gcode lands
in ``Metadata/plate_1.gcode`` with a matching MD5 sidecar.

MD5 is the plain hex digest of the whole gcode blob — identical to the
site's SparkMD5 chunked hash (2MiB chunks are an implementation detail;
MD5 chunk size does not affect the result).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import BinaryIO, Union

from .threemf_io import ThreeMFPackage

CHUNK_SIZE = 2 * 1024 * 1024  # 2 MiB, same as the site's chunked_md5

ALWAYS_REMOVE = frozenset({"Metadata/custom_gcode_per_layer.xml"})


def md5_hex_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def md5_hex_stream(stream: BinaryIO, chunk_size: int = CHUNK_SIZE) -> str:
    h = hashlib.md5()
    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        h.update(chunk)
    return h.hexdigest()


def build_removals(base: ThreeMFPackage) -> set[str]:
    return set(base.plate_gcode_names()) | set(ALWAYS_REMOVE)


def package(
    base: ThreeMFPackage,
    out_path: Union[str, Path],
    plate_gcode: bytes,
    model_settings: Union[str, bytes],
    slice_info: Union[str, bytes],
    project_settings: Union[str, bytes],
) -> str:
    """Write the export zip; returns the plate gcode MD5 hex digest."""
    digest = md5_hex_bytes(plate_gcode)
    replacements = {
        "Metadata/model_settings.config": model_settings,
        "Metadata/slice_info.config": slice_info,
        "Metadata/project_settings.config": project_settings,
        "Metadata/plate_1.gcode": plate_gcode,
        "Metadata/plate_1.gcode.md5": digest,
    }
    base.write(out_path, replacements=replacements,
               removals=build_removals(base))
    return digest
