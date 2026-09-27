# Phase 7 — Quirk Re-test on Current C++ pdngen

Source: `~/pgrev/phase7/openroad-src` (OpenROAD master, HEAD recorded at build time).
Each test: exact commands run + observed output. Verdicts must cite evidence.

## Q1. Non-adjacent-layer via insertion (`{met1 met5}`-style span)

Legacy (Tcl pdngen): `connect {{met1 met5}}` produced ZERO vias (PDN-0042
skipped every insertion) — a falsified hypothesis in Phase 5.

C++ source says (`src/connect.cpp`, `src/grid.cpp:730-809`): no adjacency
requirement; any two routing layers form a stack over all intermediate
routing layers; failure -> PDN 110 + `kBuild`.

Test: add `add_pdn_connect -grid grid -layers "met1 met5"` to the
sky130hd/gcd config (which has met1 followpins + met4/met5 stripes; met5
overlaps met1 rails where they cross), run pdngen, count vias with
span met1-met5 (or met1-*-met5 stack components) in the extraction.

- [ ] RESULT PENDING

## Q2. Dead-parameter audit (C++ `src/pdn` + `pdn.tcl`)

Method: for each Tcl option in `parse_key_args` lists, trace to a C++
consumer. Legacy dead param `rails_start_with` is gone from the API.

Expected per source study (`cpp-pdn-model.md` §4):
- `define_pdn_grid -macro -pin_direction`: DEAD (deprecated, discarded, `pdn.tcl:987`)
- `add_pdn_ring -power_pads`/`-ground_pads`: deprecated but aliased to `-connect_to_pads`
- `pdngen -verbose`: deprecated, discarded
- everything else live; `-halo` live for macro grids only.

Test: grep the built source tree to confirm each verdict; record the exact
grep hits.

- [ ] RESULT PENDING

## Q3. Zero-width stripe degeneration

Legacy: `write_def` emitted zero-width point paths as a stripe-path
degenerate case.

C++ source says (`src/shape.cpp:394-420`, `src/grid_component.cpp:411-427`):
no zero-width stripe path exists — PDN 106 rejects width < min_width before
any shape is built; surviving `metalN 0` DEF lines are via-placement SBoxes
(`src/via.cpp:704`), not stripes.

Test: (a) attempt `add_pdn_stripe -width 0` -> expect PDN 106 error;
(b) in the generated DEF/ODB, check whether any STRIPE wire has zero width;
(c) confirm `metN 0` lines (if any) carry via names, not stripe geometry.

- [ ] RESULT PENDING
