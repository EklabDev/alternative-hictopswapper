"""F10 — diff_harness: structured A/B comparison of two 3MF packages.

Used by the test-suite and the ``diff`` CLI command to catch regressions
like dropped ``filament_maps`` or stripped filament colors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

from .gcode_analyzer import analyze
from .metadata_parser import parse_model_settings, parse_slice_info
from .threemf_io import ThreeMFPackage

SWAP_MARKER = "开始换盘"  # site swap block banner (A1 profile)


@dataclass
class EntryDiff:
    name: str
    status: str            # "same" | "different" | "only_a" | "only_b"
    detail: str = ""


@dataclass
class DiffReport:
    entries: list[EntryDiff] = field(default_factory=list)
    metadata_diffs: list[str] = field(default_factory=list)
    gcode_diffs: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(e.status != "same" for e in self.entries)


def _count_substring_stream(stream, needle: bytes, chunk: int = 1 << 20) -> int:
    count = 0
    tail = b""
    while True:
        buf = stream.read(chunk)
        if not buf:
            break
        data = tail + buf
        count += data.count(needle)
        tail = data[-(len(needle) - 1):] if len(needle) > 1 else b""
    return count


def _diff_model_settings(a_text: str, b_text: str, out: list[str]) -> None:
    a = parse_model_settings(a_text)
    b = parse_model_settings(b_text)
    pa = a.sliced_plates()[0] if a.sliced_plates() else None
    pb = b.sliced_plates()[0] if b.sliced_plates() else None
    if pa is None or pb is None:
        out.append("model_settings: sliced plate missing on one side")
        return
    for key in ("filament_map_mode", "filament_maps", "filament_volume_maps"):
        va, vb = pa.metadata.get(key), pb.metadata.get(key)
        if va != vb:
            out.append(f"model_settings.{key}: {va!r} != {vb!r}")


def _diff_slice_info(a_text: str, b_text: str, out: list[str]) -> None:
    a = parse_slice_info(a_text)
    b = parse_slice_info(b_text)
    if not a.plates or not b.plates:
        out.append("slice_info: plate missing on one side")
        return
    fa = {f.id: f for f in a.plates[0].filaments}
    fb = {f.id: f for f in b.plates[0].filaments}
    for slot in sorted(set(fa) | set(fb)):
        if slot not in fa:
            out.append(f"slice_info filament {slot}: only in B")
            continue
        if slot not in fb:
            out.append(f"slice_info filament {slot}: only in A")
            continue
        for key in ("color", "type", "tray_info_idx"):
            va, vb = getattr(fa[slot], key), getattr(fb[slot], key)
            if va != vb:
                out.append(
                    f"slice_info filament {slot}.{key}: {va!r} != {vb!r}")


def diff_packages(
    a_path: Union[str, Path],
    b_path: Union[str, Path],
) -> DiffReport:
    report = DiffReport()
    with ThreeMFPackage.open(a_path) as za, ThreeMFPackage.open(b_path) as zb:
        names_a, names_b = set(za.names()), set(zb.names())
        for name in sorted(names_a | names_b):
            if name not in names_a:
                report.entries.append(EntryDiff(name, "only_b"))
            elif name not in names_b:
                report.entries.append(EntryDiff(name, "only_a"))
            else:
                same = za.read(name) == zb.read(name)
                report.entries.append(EntryDiff(
                    name, "same" if same else "different"))

        for cfg, fn in (("Metadata/model_settings.config", _diff_model_settings),
                        ("Metadata/slice_info.config", _diff_slice_info)):
            if cfg in names_a and cfg in names_b:
                fn(za.read_text(cfg), zb.read_text(cfg), report.metadata_diffs)

        ga = za.plate_gcode_names()
        gb = zb.plate_gcode_names()
        if ga and gb:
            with za.open_entry(ga[0]) as fa:
                aa = analyze(fa)
            with zb.open_entry(gb[0]) as fb:
                ab = analyze(fb)
            if aa.size_bytes != ab.size_bytes:
                report.gcode_diffs.append(
                    f"gcode size: {aa.size_bytes} != {ab.size_bytes}")
            if aa.m620_s255_count != ab.m620_s255_count:
                report.gcode_diffs.append(
                    f"M620 S255 count: {aa.m620_s255_count} != "
                    f"{ab.m620_s255_count}")
            if len(aa.claim_speed_offsets) != len(ab.claim_speed_offsets):
                report.gcode_diffs.append(
                    f"claim_speed markers: {len(aa.claim_speed_offsets)} != "
                    f"{len(ab.claim_speed_offsets)}")
            with za.open_entry(ga[0]) as fa:
                sa = _count_substring_stream(fa, SWAP_MARKER.encode("utf-8"))
            with zb.open_entry(gb[0]) as fb:
                sb = _count_substring_stream(fb, SWAP_MARKER.encode("utf-8"))
            if sa != sb:
                report.gcode_diffs.append(f"swap blocks: {sa} != {sb}")
    return report


def format_report(report: DiffReport) -> str:
    lines = []
    bad = [e for e in report.entries if e.status != "same"]
    lines.append(f"entries: {len(report.entries)} compared, "
                 f"{len(bad)} differing/missing")
    for e in bad:
        lines.append(f"  [{e.status}] {e.name} {e.detail}".rstrip())
    lines.append(f"metadata diffs: {len(report.metadata_diffs)}")
    for d in report.metadata_diffs:
        lines.append(f"  {d}")
    lines.append(f"gcode diffs: {len(report.gcode_diffs)}")
    for d in report.gcode_diffs:
        lines.append(f"  {d}")
    return "\n".join(lines)
