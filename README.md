# hictopswapper

AMS-safe Bambu plate-swap 3MF concatenator.

Takes one or more sliced BambuStudio `.gcode.3mf` plates and writes a single continuous-print `.3mf` with plate-change gcode injected between them. It is a reimplementation of [hictopswapper.com](http://www.hictopswapper.com/) (V12.5) that keeps AMS filament maps, colors, and tray ids intact — the live site drops those fields, which breaks multi-AMS setups on printers like the A1.

Python 3.10+, stdlib only.

## What it does

1. Reads each input `.gcode.3mf` and picks a sliced plate.
2. Injects printer-specific plate-swap gcode after the last `set_gcode_claim_speed_level : 0` marker.
3. Concatenates plates × per-file repeats × loops into one `Metadata/plate_1.gcode`.
4. Comments out redundant AMS unload/reload cycles at plate boundaries when the same slot continues.
5. Rewrites `model_settings.config` / `slice_info.config` while preserving AMS maps, filament color/type/tray, and real usage totals.
6. Copies `project_settings.config` from the input that uses the highest AMS slot.

`--legacy` skips the AMS fixes and reproduces the live site's metadata behavior.

Field-level details: [docs/ams-mapping.md](docs/ams-mapping.md).

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Web UI

```bash
hictopswapper serve
```

Then open http://127.0.0.1:8080. Drop sliced `.gcode.3mf` files, set repeats / loops / printer, and export.

Bind elsewhere with `--host 0.0.0.0 --port 8080`.

## CLI

```bash
# concatenate one or more plates into a continuous-print 3MF
hictopswapper export in.gcode.3mf -o out.gcode.3mf
hictopswapper export a.3mf b.3mf --repeats 2,1 --loops 3 --printer A1 -o out.3mf

# gcode / filament stats for a plate
hictopswapper analyze in.gcode.3mf

# structured A/B report between two packages
hictopswapper diff a.3mf b.3mf
```

| Flag | Default | Meaning |
|---|---|---|
| `-o` / `--output` | required | output `.3mf` path |
| `--repeats` | `1` per input | comma-separated per-file repeat counts |
| `--loops` | `1` | repeat the whole sequence N times |
| `--printer` | `A1` | plate-swap profile (`A1`, or `none` to skip injection) |
| `--plate` | `0` | sliced-plate index in each input |
| `--legacy` | off | match the live site (drops AMS maps/colors) |

`export` prints AMS metadata warnings and exits non-zero if verification fails.

## Docker

```bash
docker compose up
```

Web UI at http://localhost:8080. Override the host port with `HICTOP_PORT`.

CLI (files in the current directory are mounted at `/data`):

```bash
docker compose run --rm hictopswapper export in.3mf --repeats 2 -o out.3mf
docker compose run --rm hictopswapper analyze in.3mf
docker compose run --rm hictopswapper diff a.3mf b.3mf
```

Point the mount at another folder with `HICTOP_DATA=/path/to/files`.

Plain `docker build` / `docker run` also works; the image entrypoint is the CLI:

```bash
docker build -t hictopswapper .
docker run --rm -v "$PWD:/data" hictopswapper \
  export /data/in.3mf --repeats 2 -o /data/out.3mf
```

## Tests

```bash
pip install pytest
python -m pytest tests
```

## Requirements

- Input files must be **sliced** Bambu `.gcode.3mf` packages (they contain `Metadata/plate_N.gcode`). Un-sliced project 3MFs will fail.
- Currently ships an **A1** plate-swap profile. Pass `--printer none` to concatenate without injecting swap gcode.
