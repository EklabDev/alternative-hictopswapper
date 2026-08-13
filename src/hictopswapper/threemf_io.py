"""F1 — 3mf_io: read/write Bambu ``.gcode.3mf`` packages (ZIP containers).

The package is kept lazy: entries (including 50MB+ plate gcode) are only
decompressed when read.  ``write`` streams a new zip, copying every entry
that is neither removed nor replaced, so unread entries round-trip
byte-identically.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import BinaryIO, Mapping, Union

_PLATE_GCODE_RE = re.compile(r"^Metadata/plate_(\d+)\.gcode$")


class ThreeMFPackage:
    """Lazy reader / rewriting writer for a Bambu sliced 3MF zip."""

    def __init__(self, source: Union[str, Path, BinaryIO]):
        self._source = source
        self._zip = zipfile.ZipFile(source, "r")

    @classmethod
    def open(cls, path: Union[str, Path]) -> "ThreeMFPackage":
        return cls(path)

    def close(self) -> None:
        self._zip.close()

    def __enter__(self) -> "ThreeMFPackage":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------ read
    def names(self) -> list[str]:
        return self._zip.namelist()

    def read(self, name: str) -> bytes:
        return self._zip.read(name)

    def read_text(self, name: str, encoding: str = "utf-8") -> str:
        # surrogateescape guarantees read_text -> encode round-trips exactly,
        # even if a gcode comment contains non-UTF-8 bytes.
        return self.read(name).decode(encoding, errors="surrogateescape")

    def open_entry(self, name: str) -> BinaryIO:
        """Stream an entry (for chunked processing of huge gcode)."""
        return self._zip.open(name, "r")

    def plate_gcode_names(self) -> list[str]:
        """``Metadata/plate_N.gcode`` entries, sorted by plate number."""
        found = []
        for n in self.names():
            m = _PLATE_GCODE_RE.match(n)
            if m:
                found.append((int(m.group(1)), n))
        return [n for _, n in sorted(found)]

    # ----------------------------------------------------------------- write
    def write(
        self,
        out_path: Union[str, Path],
        replacements: Mapping[str, Union[bytes, str]] | None = None,
        removals: set[str] | frozenset[str] | None = None,
        compresslevel: int = 3,
    ) -> None:
        """Write a new zip to ``out_path``.

        Entries are copied in original order; ``removals`` are skipped and
        ``replacements`` substitute (or append) entry content.  The site's
        exporter uses DEFLATE level 3, mirrored here.
        """
        replacements = dict(replacements or {})
        removals = set(removals or ())
        written: set[str] = set()
        with zipfile.ZipFile(
            out_path, "w", zipfile.ZIP_DEFLATED,
            compresslevel=compresslevel, allowZip64=True,
        ) as zout:
            for info in self._zip.infolist():
                name = info.filename
                if name in removals:
                    continue
                if name in replacements:
                    data = replacements[name]
                    if isinstance(data, str):
                        data = data.encode("utf-8", errors="surrogateescape")
                    zout.writestr(name, data, zipfile.ZIP_DEFLATED, compresslevel)
                else:
                    with self._zip.open(info, "r") as fin:
                        with zout.open(info, "w") as fout:
                            while True:
                                chunk = fin.read(1 << 20)
                                if not chunk:
                                    break
                                fout.write(chunk)
                written.add(name)
            for name, data in replacements.items():
                if name in written:
                    continue
                if isinstance(data, str):
                    data = data.encode("utf-8", errors="surrogateescape")
                zout.writestr(name, data, zipfile.ZIP_DEFLATED, compresslevel)
