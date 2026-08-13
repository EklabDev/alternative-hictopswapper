# AMS mapping in Bambu `.gcode.3mf` packages

Field dictionary for the metadata files inside a BambuStudio-sliced
`.gcode.3mf`, focused on everything that ties a filament **slot** to an
**AMS unit**. Every claim below is grounded in the real fixture pair under
`tests/fixtures/` (extracted from `hictop input/…plate_1.gcode.3mf` and the
corresponding live-site output `hictop output/…swap.gcode.3mf`) and in the
vendored site source `vendor/hictopswapper/res/test.js` (V12.5).

## Slot identity, across files

The same filament slot appears in several Number forms:

| File | Field | Base | Example |
|---|---|---|---|
| `slice_info.config` | `<filament id="…">` | 1-based | `1, 3, 6` |
| `plate_N.gcode` header | `; filament: …` | 1-based | `; filament: 1,3,6` |
| `filament_sequence.json` | `sequence` | 1-based | `[6,1,6,1,6,1,3,1,3,1,3,1]` |
| `plate_N.json` | `filament_ids` | **0-based** | `[0,2,5]` (= slots 1,3,6) |
| `plate_N.json` | `first_extruder` | **0-based** | `5` (= slot 6, the first slot in `sequence`) |
| gcode AMS commands | `M620 S<n>` | 0-based in syntax, slot index | `S255` = unload |

AMS-unit assignment (which physical AMS unit feeds a slot) is carried by the
`filament_maps` / `filament_map` fields below — one value per slot, 1 meaning
"AMS unit 1" in the fixture (single-AMS A1: all eight values are `1`).

## `Metadata/model_settings.config`

XML `<config>` with one `<plate>` per build plate; plate properties are
`<metadata key="…" value="…"/>` pairs. Observed keys (input fixture):

- `plater_id`, `plater_name`, `locked`
- `gcode_file` — e.g. `Metadata/plate_1.gcode`; empty string means the plate
  was not sliced (plates 2 and 3 in the fixture). **Only plates with a
  non-empty `gcode_file` are sliced.**
- `thumbnail_file`, `thumbnail_no_light_file`, `top_file`, `pick_file`,
  `pattern_bbox_file` (→ `Metadata/plate_N.json`)
- **`filament_map_mode`** — `"Auto For Flush"` in the fixture
- **`filament_maps`** — space-separated AMS unit per slot:
  `"1 1 1 1 1 1 1 1"`
- **`filament_volume_maps`** — `"0 0 0 0 0 0 0 0"`

**Live site (V12.5):** discards the source file entirely and substitutes the
hardcoded `model_settings_template` (`test.js` line 7): a single plate named
`自动换盘` with `plater_id/gcode_file/thumbnail_file/top_file/pick_file/
pattern_bbox_file` only. This **drops `filament_map_mode`, `filament_maps`,
`filament_volume_maps` and `thumbnail_no_light_file`** — confirmed by
`tests/fixtures/output/model_settings.config`, which has none of them.

**This tool:** `ams_map_preserver.build_model_settings()` keeps the first
sliced plate, renumbers `plater_id=1`, renames it `自动换盘`, repoints the
file references at `plate_1` names, and **preserves the three AMS fields and
`thumbnail_no_light_file` verbatim**.

## `Metadata/slice_info.config`

XML `<config>`:

- `<header><header_item key="X-BBL-Client-Type" value="slicer"/>` and
  `X-BBL-Client-Version` (`02.07.01.57` in the fixture).
- One `<plate>` per plate, `<metadata>` keys including `index` (1-based),
  `printer_model_id` (`N2S`), `prediction` (seconds, `"54580"`), `weight`
  (grams, `"72.31"`), `filament_maps` / `limit_filament_maps`
  (space-separated per-slot), plus slicing details
  (`nozzle_diameters`, `first_layer_time`, …).
- `<object identify_id="…" name="…" skipped="…"/>` per printed object.
- **`<filament>`** — one per *used* slot. Fixture attributes:
  `id="1" tray_info_idx="GFL99" type="PLA" color="#FFFFFF" used_m="23.31"
  used_g="69.54" group_id="0" nozzle_diameter="0.20" volume_type="Standard"
  used_for_object="true" used_for_support="false"`. `tray_info_idx` is the
  Bambu filament preset id (`GFL99`/`GFA00`); `used_m`/`used_g` are the
  per-plate consumption.
- `<warning>`, `<nozzle>`, `<layer_filament_lists>` blocks.

**Live site:** keeps only the first plate, sets its `index` to `1`, leaves
all other plate metadata (including `filament_maps`) untouched, then
**removes every `<filament>` node and appends bare
`<filament id="N" used_m="0" used_g="0"/>` nodes** for each slot shown in
the page's filament-total list (`test.js` lines 283–293). `color`, `type`,
`tray_info_idx`, `group_id` and the real usage numbers are lost — see
`tests/fixtures/output/slice_info.config` line 39. The site computes the
real totals (`update_filament_usage`, lines 406–425: per-slot
`used_m × repeats × loops`) but only displays them in the page; they never
reach the XML.

**This tool:** `build_slice_info(preserve=True)` clones the full attribute
set per slot (first-seen across all input files via
`collect_filament_sources`) and writes the true totals formatted `%.2f`.
`preserve=False` (and `--legacy` on the CLI) reproduces the site's bare-node
output exactly.

## `Metadata/project_settings.config`

Flat JSON object (569 keys in the fixture; values are strings or lists of
strings). AMS-relevant keys:

- `filament_map` — list form of the per-slot AMS unit: `["1",…,"1"]` (8)
- `filament_map_mode` — `"Auto For Flush"`
- `filament_colour` — 8 hex colors, one per slot
- `filament_ids` — 8 tray preset ids: `["GFL99","GFL99","GFA00",…]`
- `filament_type` — 8 types (`"PLA"`, …)
- `extruder_ams_count` — list with one entry per extruder:
  `["1#0|4#0", "1#0|4#0"]`. The same value appears in the gcode config
  block as `; extruder_ams_count = 1#0|4#0;1#0|4#0` (per-extruder entries
  separated by `;`). Neither the site nor this tool interprets the
  `A#B|C#D` sub-structure; it is copied verbatim.

**Live site:** does not rewrite this file's content — it copies
`project_settings.config` **from the input file that uses the highest AMS
slot** (`ams_max_file_id`, computed in `update_filament_usage` line 416 as
the file whose plate contains the highest slot with `repeats > 0`;
applied at lines 280–282).

**This tool:** same rule, ported as
`select_project_settings_source(items)` over `(file_index, slot_ids,
repeats)`.

## `Metadata/plate_N.json`

Per-plate JSON bounding-box/filament summary (`pattern_bbox_file`).
Fixture keys: `bbox_all`, `bbox_objects` (per-object `area`, `bbox`, `id`,
`layer_height`, `name`, plus the `wipe_tower` entry), `bed_type`
(`"textured_plate"`), **`filament_colors`** (hex, used slots only, in slot
order: `["#FFFFFF","#000000","#A4DAE6"]`), **`filament_ids`** (0-based:
`[0,2,5]`), **`first_extruder`** (0-based: `5`), `first_layer_time`,
`is_seq_print`, `nozzle_diameter`, `version` (2).

Neither the site nor this tool rewrites it; the exported package keeps the
base file's `plate_1.json`.

## `Metadata/filament_sequence.json`

JSON, one entry per plate: `{"plate_1": {"nozzle_sequence": […],
"optimal_assignment": […], "sequence": [6,1,6,1,6,1,3,1,3,1,3,1]}}`.
`sequence` is the 1-based slot ids in print order (fixture: starts with
slot 6, matching `first_extruder = 5` 0-based in `plate_1.json`). Plates
that were not sliced have empty arrays. Untouched by the site and by this
tool.

## `Metadata/plate_N.gcode` (+ `.md5`)

The sliced toolpath. AMS-relevant content:

- Header block (between `; HEADER_BLOCK_START` / `; HEADER_BLOCK_END`):
  `; total estimated time: 15h 9m 40s`,
  `; total filament length [mm] : 23314.10,293.75,621.81`,
  `; total filament weight [g] : 69.54,0.89,1.88`,
  `; filament: 1,3,6` (1-based used slots, matching `slice_info` filament
  ids).
- Config block: `; filament_map = 1,1,1,1,1,1,1,1`,
  `; filament_map_mode = Auto For Flush`,
  `; filament_colour = #FFFFFF;#C52C18;#000000;#EEAECD;#18C241;#A4DAE6;#F6DA5A;#AC95D5`
  (`;`-separated, all 8 slots),
  `; filament_ids = GFL99;GFL99;GFA00;…`,
  `; extruder_ams_count = 1#0|4#0;1#0|4#0`. These mirror
  `project_settings.config` and are informational — the printer reads the
  XML/JSON metadata, the site never edits the config block.
- Executable AMS commands: lines **starting with** `M620 S<n>` (load slot)
  / `M620 S255` (unload) / `M621 S<n>`. The `M620 …` strings inside the
  `; change_filament_gcode = …` / `; machine_end_gcode = …` comment
  templates are *not* commands.
- `M1002 set_gcode_claim_speed_level : 0` markers.

`plate_N.gcode.md5` is the 32-char hex MD5 of the gcode bytes. The
slicer-written sidecar in the input fixture is uppercase
(`D7A31EC0…`); the site's SparkMD5 (`chunked_md5`, 2 MiB chunks — chunk
size does not affect MD5) writes lowercase (`28cb97c4…` in the output
fixture). This tool writes `hashlib.md5(...).hexdigest()` (lowercase) and
the test suite proves byte-for-byte agreement with the slicer sidecar.

**Live site (`export_3mf`, `test.js` lines 257–334):**

1. For each playlist item with `repeats > 0`, reads the plate gcode and
   runs `update_gcode()`: insert the printer's swap snippet after the
   **last** `set_gcode_claim_speed_level : 0`, separated by `"\r\n"`
   (lines 336–357). The A1 snippet starts with the banner
   `;========开始换盘 =================`.
2. Appends `自动换盘_gcode` (`";\n\n\n"`) to every item, replicates the
   sequence `loops` times, prepends `ini_gcode` (`";\n"`) to the first
   item (lines 294–297).
3. Scans each item for `\nM620 S` events (3-char slot window, trimmed to
   2 chars when the 3rd char is `\n` or space; lines 298–309). When event
   `i` is `S255` (unload) and events `i-1` and `i+1` name the same slot,
   it *intends* to comment out the unload and the following reload via
   `disable_gcode_line2()` — **but that function is a no-op
   (`return e`, lines 358–360)**, so the site always prints a full
   unload/reload cycle at every plate boundary.
4. Repacks the zip from the **first** input file: removes all
   `Metadata/plate_N.gcode` and `Metadata/custom_gcode_per_layer.xml`,
   replaces the three configs, writes the concatenated blob as
   `Metadata/plate_1.gcode` plus its MD5 sidecar, DEFLATE level 3
   (lines 275–321).

**This tool:** `gcode_analyzer` collects the same events with byte offsets
(lines starting with `M620`/`M621` only); `plate_swap_injector` ports the
injection verbatim; `plate_concatenator` ports the suffix/loops/ini
assembly; and `ams_boundary_cleaner` implements the intended disabling for
real by inserting `;` at the start of the two `M620` lines (F6). Use
`--legacy` to skip F6/F7 and reproduce site output byte-semantics.

## Thumbnails and other entries

`Metadata/plate_N.png`, `plate_N_small.png`, `plate_no_light_N.png`,
`top_N.png`, `pick_N.png`, `3D/3dmodel.model`, `[Content_Types].xml`,
`_rels/`, `cut_information.xml` are copied through unchanged by both the
site (JSZip repack) and this tool (`ThreeMFPackage.write` streams every
entry that is neither removed nor replaced, so unread entries round-trip
byte-identically).

## Summary: what degrades on the live site vs. this tool

| Field | Live site V12.5 | This tool |
|---|---|---|
| `model_settings` `filament_map_mode` / `filament_maps` / `filament_volume_maps` | dropped (hardcoded template) | preserved (F7) |
| `model_settings` `thumbnail_no_light_file` | dropped | preserved |
| `slice_info` filament `color` / `type` / `tray_info_idx` / `group_id` | dropped (bare nodes) | preserved (F7) |
| `slice_info` filament `used_m` / `used_g` | always `"0"` | real totals × repeats × loops, `%.2f` |
| boundary `M620 S255` + reload when slot continues | intended but no-op (`disable_gcode_line2`) | actually commented out (F6) |
| `project_settings.config` source | file with highest used slot | same (ported) |
| `plate_1.gcode.md5` | SparkMD5 of final blob | `hashlib.md5`, verified equal |
| swap injection after last `set_gcode_claim_speed_level : 0` | yes | yes (verbatim port) |

`ams_map_preserver.verify_ams_metadata()` checks an exported package for
the left column's failure modes and returns a problem list; the CLI export
command prints them as warnings and exits non-zero.
