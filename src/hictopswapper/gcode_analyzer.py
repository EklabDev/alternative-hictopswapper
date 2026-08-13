"""F3 — gcode_analyzer: streaming scanner for Bambu plate gcode.

Files are 50–100MB+, so analysis is a single pass over a binary stream
with byte offsets tracked.  Collects header stats, all ``M620``/``M621``
AMS events, ``set_gcode_claim_speed_level`` offsets and structural block
markers (HEADER_BLOCK / CONFIG_BLOCK / EXECUTABLE_BLOCK / MACHINE_*).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Union

CLAIM_SPEED_MARKER = "set_gcode_claim_speed_level : 0"

BLOCK_MARKERS = (
    "HEADER_BLOCK_START",
    "HEADER_BLOCK_END",
    "CONFIG_BLOCK_START",
    "CONFIG_BLOCK_END",
    "EXECUTABLE_BLOCK_START",
    "EXECUTABLE_BLOCK_END",
    "MACHINE_START_GCODE_END",
    "MACHINE_END_GCODE_START",
)

_M620_RE = re.compile(r"^M62[01](?:\s|$)")
_M620_S_RE = re.compile(r"^M62[01]\s+S(\d+)")
_TIME_RE = re.compile(r"total estimated time:\s*(.+?)\s*$")
_FILAMENT_RE = re.compile(r"^; filament:\s*([0-9,]+)")
_LEN_RE = re.compile(r"^; total filament length \[mm\] :\s*(.+?)\s*$")
_WEIGHT_RE = re.compile(r"^; total filament weight \[g\] :\s*(.+?)\s*$")


@dataclass
class M620Event:
    command: str           # "M620" or "M621"
    slot: int | None       # S parameter when present (255 = unload)
    line_no: int           # 1-based
    byte_offset: int       # offset of the line's first byte
    text: str              # full line, stripped


@dataclass
class GcodeAnalysis:
    size_bytes: int = 0
    line_count: int = 0
    total_estimated_time: str | None = None
    filaments: list[int] = field(default_factory=list)
    total_filament_length_mm: list[float] = field(default_factory=list)
    total_filament_weight_g: list[float] = field(default_factory=list)
    m620_events: list[M620Event] = field(default_factory=list)
    claim_speed_offsets: list[int] = field(default_factory=list)
    markers: dict[str, list[int]] = field(default_factory=dict)

    @property
    def m620_s255_count(self) -> int:
        return sum(1 for e in self.m620_events if e.command == "M620" and e.slot == 255)


def analyze(stream: BinaryIO) -> GcodeAnalysis:
    result = GcodeAnalysis()
    offset = 0
    line_no = 0
    while True:
        raw = stream.readline()
        if not raw:
            break
        line_no += 1
        line_offset = offset
        offset += len(raw)
        line = raw.decode("utf-8", errors="surrogateescape").rstrip("\r\n").rstrip()

        if line_no < 2000:  # header stats live in the header/config blocks
            m = _TIME_RE.search(line)
            if m and result.total_estimated_time is None:
                result.total_estimated_time = m.group(1)
            m = _FILAMENT_RE.match(line)
            if m:
                result.filaments = [int(v) for v in m.group(1).split(",") if v]
            m = _LEN_RE.match(line)
            if m:
                result.total_filament_length_mm = [
                    float(v) for v in m.group(1).split(",") if v]
            m = _WEIGHT_RE.match(line)
            if m:
                result.total_filament_weight_g = [
                    float(v) for v in m.group(1).split(",") if v]

        if CLAIM_SPEED_MARKER in line:
            result.claim_speed_offsets.append(
                line_offset + line.index(CLAIM_SPEED_MARKER))

        for marker in BLOCK_MARKERS:
            if marker in line:
                result.markers.setdefault(marker, []).append(line_no)
                break

        if _M620_RE.match(line):
            command = line[:4]
            s = _M620_S_RE.match(line)
            result.m620_events.append(M620Event(
                command=command,
                slot=int(s.group(1)) if s else None,
                line_no=line_no,
                byte_offset=line_offset,
                text=line,
            ))

    result.size_bytes = offset
    result.line_count = line_no
    return result


def analyze_path(path: Union[str, Path]) -> GcodeAnalysis:
    with open(path, "rb") as f:
        return analyze(f)
