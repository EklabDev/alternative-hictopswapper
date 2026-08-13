"""F9 — cli: thin shell driving the F1–F8 pipeline.

Subcommands:
  export   concatenate plates into one continuous-print AMS-safe 3MF
  analyze  print gcode/metadata stats for a 3MF
  diff     structured A/B report between two 3MFs (F10)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .ams_boundary_cleaner import clean_ams_boundaries
from .ams_map_preserver import (
    build_model_settings,
    build_slice_info,
    collect_filament_sources,
    select_project_settings_source,
    verify_ams_metadata,
)
from .diff_harness import diff_packages, format_report
from .export_packager import package
from .gcode_analyzer import analyze
from .metadata_parser import parse_model_settings, parse_slice_info
from .plate_concatenator import expand_items
from .plate_swap_injector import available_printers, inject_swap_gcode, load_swap_gcode
from .threemf_io import ThreeMFPackage

# Hardcoded template the live site (V12.5) substitutes for model_settings —
# drops all AMS map fields.  Used only with --legacy to reproduce site output.
LEGACY_MODEL_SETTINGS_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<config>\n'
    '  <plate>\n'
    '    <metadata key="plater_id" value="1"/>\n'
    '    <metadata key="plater_name" value="自动换盘"/>\n'
    '    <metadata key="locked" value="false"/>\n'
    '    <metadata key="gcode_file" value="Metadata/plate_1.gcode"/>\n'
    '    <metadata key="thumbnail_file" value="Metadata/plate_1.png"/>\n'
    '    <metadata key="top_file" value="Metadata/top_1.png"/>\n'
    '    <metadata key="pick_file" value="Metadata/pick_1.png"/>\n'
    '    <metadata key="pattern_bbox_file" value="Metadata/plate_1.json"/>\n'
    '  </plate>\n'
    '</config> '
)


def run_export(
    input_paths: list[str],
    out_path: str,
    repeats: list[int] | None = None,
    loops: int = 1,
    printer: str = "A1",
    plate_index: int = 0,
    legacy: bool = False,
    plate_indices: list[int] | None = None,
) -> dict:
    """Concatenate one plate per input file into a single-plate 3MF.

    Faithful port of the site's ``export_3mf`` with the AMS fixes from
    F6/F7 applied unless ``legacy`` is set.  ``plate_indices`` selects the
    sliced plate per input file; when omitted, ``plate_index`` applies to
    all inputs.
    """
    if not input_paths:
        raise ValueError("no input files")
    if plate_indices is not None and len(plate_indices) != len(input_paths):
        raise ValueError("plate_indices count must match number of input files")
    repeats = repeats or [1] * len(input_paths)
    if len(repeats) != len(input_paths):
        raise ValueError("--repeats count must match number of input files")
    if any(r < 1 for r in repeats):
        raise ValueError("repeats must be >= 1")
    if loops < 1:
        raise ValueError("loops must be >= 1")

    swap_gcode = "" if printer.lower() == "none" else load_swap_gcode(printer)

    packages: list[ThreeMFPackage] = []
    try:
        for p in input_paths:
            packages.append(ThreeMFPackage.open(p))
        ms_texts = [pkg.read_text("Metadata/model_settings.config")
                    for pkg in packages]
        si_texts = [pkg.read_text("Metadata/slice_info.config")
                    for pkg in packages]

        gcode_items: list[str] = []
        slot_items: list[tuple[int, list[int], int]] = []
        used: dict[int, tuple[float, float]] = {}
        plate_names: list[str] = []

        for i, pkg in enumerate(packages):
            ms = parse_model_settings(ms_texts[i])
            sliced = ms.sliced_plates()
            if not sliced:
                raise ValueError(f"{input_paths[i]}: no sliced plate found")
            pidx = plate_indices[i] if plate_indices is not None else plate_index
            if pidx >= len(sliced):
                raise ValueError(
                    f"{input_paths[i]}: plate index {pidx} out of "
                    f"range ({len(sliced)} sliced plate(s))")
            chosen = sliced[pidx]
            plate_names.append(chosen.gcode_file)

            gcode_text = inject_swap_gcode(
                pkg.read_text(chosen.gcode_file), swap_gcode)
            gcode_items.extend([gcode_text] * repeats[i])

            # usage stats from the matching slice_info plate
            si = parse_slice_info(si_texts[i])
            plate_pos = ms.plates.index(chosen)
            si_plate = next(
                (pl for pl in si.plates if pl.index == plate_pos + 1),
                si.plates[0] if si.plates else None)
            slot_ids = [f.id for f in si_plate.filaments] if si_plate else []
            slot_items.append((i, slot_ids, repeats[i]))
            for f in si_plate.filaments if si_plate else []:
                m, g = used.get(f.id, (0.0, 0.0))
                used[f.id] = (m + f.used_m * repeats[i] * loops,
                              g + f.used_g * repeats[i] * loops)

        expanded = expand_items(gcode_items, loops)
        disabled = 0
        if not legacy:
            expanded, disabled = clean_ams_boundaries(expanded)
        final_bytes = "".join(expanded).encode("utf-8", errors="surrogateescape")

        # the site only lists slots with nonzero usage
        used = {s: (m, g) for s, (m, g) in used.items() if m and g}

        if legacy:
            model_settings_out = LEGACY_MODEL_SETTINGS_TEMPLATE
            slice_info_out = build_slice_info(si_texts[0], used, preserve=False)
        else:
            model_settings_out = build_model_settings(ms_texts[0])
            slice_info_out = build_slice_info(
                si_texts[0], used,
                filament_sources=collect_filament_sources(si_texts),
                preserve=True)

        src_idx = select_project_settings_source(slot_items)
        project_settings = packages[src_idx].read(
            "Metadata/project_settings.config")

        digest = package(packages[0], out_path, final_bytes,
                         model_settings_out, slice_info_out, project_settings)

        problems = [] if legacy else verify_ams_metadata(
            model_settings_out, slice_info_out)
        return {
            "out_path": out_path,
            "plates": plate_names,
            "repeats": repeats,
            "loops": loops,
            "printer": printer,
            "legacy": legacy,
            "gcode_bytes": len(final_bytes),
            "gcode_md5": digest,
            "filaments_used": {s: {"used_m": round(m, 2), "used_g": round(g, 2)}
                               for s, (m, g) in sorted(used.items())},
            "project_settings_source": input_paths[src_idx],
            "ams_boundaries_cleaned": disabled,
            "ams_metadata_problems": problems,
        }
    finally:
        for pkg in packages:
            pkg.close()


def _print_report(report: dict) -> None:
    print(f"exported: {report['out_path']}")
    print(f"  plates:   {report['plates']}")
    print(f"  repeats:  {report['repeats']}  loops: {report['loops']}  "
          f"printer: {report['printer']}"
          + ("  [legacy site behavior]" if report["legacy"] else ""))
    print(f"  gcode:    {report['gcode_bytes']} bytes  "
          f"md5: {report['gcode_md5']}")
    for slot, u in report["filaments_used"].items():
        print(f"  filament {slot}: {u['used_m']} m / {u['used_g']} g")
    print(f"  project_settings from: {report['project_settings_source']}")
    print(f"  AMS boundaries cleaned: {report['ams_boundaries_cleaned']}")
    for p in report["ams_metadata_problems"]:
        print(f"  WARNING: {p}")


def cmd_export(args: argparse.Namespace) -> int:
    repeats = ([int(v) for v in args.repeats.split(",")]
               if args.repeats else None)
    report = run_export(
        input_paths=args.inputs,
        out_path=args.output,
        repeats=repeats,
        loops=args.loops,
        printer=args.printer,
        plate_index=args.plate,
        legacy=args.legacy,
    )
    _print_report(report)
    return 1 if report["ams_metadata_problems"] else 0


def cmd_analyze(args: argparse.Namespace) -> int:
    with ThreeMFPackage.open(args.input) as pkg:
        gcode_names = pkg.plate_gcode_names()
        if not gcode_names:
            print("no plate gcode found", file=sys.stderr)
            return 1
        name = gcode_names[min(args.plate, len(gcode_names) - 1)]
        with pkg.open_entry(name) as f:
            stats = analyze(f)
        print(f"{args.input} :: {name}")
        print(f"  size: {stats.size_bytes} bytes, {stats.line_count} lines")
        print(f"  total estimated time: {stats.total_estimated_time}")
        print(f"  filaments: {stats.filaments}")
        print(f"  filament length [mm]: {stats.total_filament_length_mm}")
        print(f"  filament weight [g]:  {stats.total_filament_weight_g}")
        print(f"  M620/M621 events: {len(stats.m620_events)} "
              f"(S255 unloads: {stats.m620_s255_count})")
        print(f"  claim_speed markers: {len(stats.claim_speed_offsets)}")
        for marker, lines in sorted(stats.markers.items()):
            print(f"  {marker}: lines {lines[:4]}"
                  + (" ..." if len(lines) > 4 else ""))
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    print(format_report(diff_packages(args.a, args.b)))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .webui import serve
    serve(host=args.host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hictopswapper",
        description="AMS-safe Bambu plate-swap 3MF concatenator")
    sub = parser.add_subparsers(dest="command", required=True)

    p_exp = sub.add_parser("export", help="concatenate plates into one 3MF")
    p_exp.add_argument("inputs", nargs="+", help="input .gcode.3mf files")
    p_exp.add_argument("-o", "--output", required=True, help="output .3mf path")
    p_exp.add_argument("--repeats",
                       help="comma-separated per-input repeat counts "
                            "(default: all 1)")
    p_exp.add_argument("--loops", type=int, default=1,
                       help="repeat the whole sequence N times")
    p_exp.add_argument("--printer", default="A1",
                       help="plate-swap profile "
                            f"({', '.join(available_printers())}) or 'none'")
    p_exp.add_argument("--plate", type=int, default=0,
                       help="sliced-plate index per input (default 0)")
    p_exp.add_argument("--legacy", action="store_true",
                       help="reproduce the live site's exact metadata "
                            "behavior (drops AMS maps/colors)")
    p_exp.set_defaults(func=cmd_export)

    p_ana = sub.add_parser("analyze", help="stats for a 3MF plate gcode")
    p_ana.add_argument("input")
    p_ana.add_argument("--plate", type=int, default=0)
    p_ana.set_defaults(func=cmd_analyze)

    p_diff = sub.add_parser("diff", help="compare two 3MF packages")
    p_diff.add_argument("a")
    p_diff.add_argument("b")
    p_diff.set_defaults(func=cmd_diff)

    p_srv = sub.add_parser("serve", help="start the web UI")
    p_srv.add_argument("--host", default="127.0.0.1")
    p_srv.add_argument("--port", type=int, default=8080)
    p_srv.set_defaults(func=cmd_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
