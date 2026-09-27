# C++ PDN Forward Model — Source Study (OpenROAD master, Sept 2026)

Source studied: sparse checkout at `/tmp/or-pdn/src/pdn/` (HEAD `80c6be9`,
2026-09-26). All line numbers below are `file:line` in that tree
(`src/pdn/src/...` unless noted). Spot-checked against upstream
`The-OpenROAD-Project/OpenROAD` master (`straps.cpp`, `pdn.tcl`) — the
checkout matches upstream for every construct cited. Nothing was built or
modified; all conclusions come from reading code and the checked-in
`test/*.defok` artifacts.

Headline finding: the C++ rewrite keeps the legacy *observable* stripe
geometry (including the "second net at pitch/2" interleaving) but implements
it through a different, explicit mechanism — a **group model** in which the
`-spacing` parameter, when omitted, *defaults* to `pitch / net_count − width`
(`src/straps.cpp:49-56`). There is no separate pitch/2 code path.

---

## 1. Stripe placement

### 1.1 Where the sweep starts (origin)

The sweep origin is the **near edge of the voltage-domain (core) area** along
the sweep axis — not the legacy `stdcell_yMin − max_rail_width/2` reference:

- `VoltageDomain::getDomainArea()` returns `block_->getCoreArea()` for a core
  domain (`src/domain.cpp:117-123`).
- `Straps::makeShapes` passes `core.yMin()` (horizontal stripes) /
  `core.xMin()` (vertical stripes) as `pos_origin` (`src/straps.cpp:245-273`).
- On a flipped instance grid the sweep is mirrored: origin becomes
  `core.yMax()`/`core.xMax()` and runs toward the opposite edge
  (`src/straps.cpp:239-243, 251-252, 265-266`).

Verified against `test/core_grid_offset_strap.defok` (sky130hd `gcd`):
met5 horizontal stripes, `-width 1.6 -pitch 22.44 -offset 11.44`. Core area is
`y 10880..100640`. First VDD stripe center is at `y = 22320 = 10880 + 11440`
(= core.yMin + offset), then `44760, 67200, 89640` — exact `pitch` steps from
the core near edge.

### 1.2 Position formulas (non-mirrored)

Definitions (`src/straps.cpp:303-305, 338-349, 370-379`):

- `group_pitch = spacing_ + width_` — the **within-group** step between
  consecutive nets (`src/straps.cpp:305`).
- Outer sweep: `pos_k = pos_origin + offset + k · pitch_`, `k = 0, 1, 2, …`
  (`src/straps.cpp:338-339`).
- Inside group `k`, net `j` (in `getNets()` order) is centered at
  `c_{k,j} = pos_k + j · group_pitch` (`src/straps.cpp:340-347, 378`); its
  edges are `strap_start = c − ⌊width/2⌋`, `strap_end = strap_start + width`
  (`src/straps.cpp:348-349`). Mirrored sweeps negate all increments.

**The critical detail — default `-spacing`.** In the `Straps` constructor, when
`-spacing` is omitted (`spacing_ == 0`) and pitch is non-zero:

```cpp
spacing_ = pitch_ / getNetCount() - width_;   // then rounded DOWN to mfg grid
```

(`src/straps.cpp:49-56`). Hence `group_pitch = spacing_ + width_ =
pitch / net_count` (up to rounding): with 2 nets the second net lands exactly
at `pitch/2` from the first — the legacy interleave reproduced as *derived*
behavior, not a special case. Verified: in `core_grid_offset_strap.defok`,
VDD at `22320`, VSS at `33540 = 22320 + 11220 = 22320 + 22440/2`; and in
`core_grid_strap_count.defok` (nangate45, W=1.0, P=5.0, O=2.5), VSS at
`25140 = 20140 + 5000` and VDD at `30140 = 25140 + 5000`.

Two caveats found in source:

- The constructor runs **before** `PdnGen::makeStrap` calls `setNets()`
  (`src/PdnGen.cc:682-690`), so the derived spacing uses the *grid* net count,
  not a stripe-level `-nets` list of different length.
- When `-spacing` *is* given explicitly, the second-net phase is
  `width + spacing` — fully user-controlled.

### 1.3 `-extend_to_boundary` and the sweep origin

`-extend_to_boundary` sets `extend_mode_ = kBoundary`, so the strap *length*
spans `getGridBoundary()` (= die area, `src/grid.cpp:521-524` via
`getGridArea()`) and is clipped to the die polygon region
(`src/straps.cpp:192-209`). It does **not** move the sweep origin or the
termination limit: those stay at the core near/far edges unless
`-allow_out_of_core` is also given.

### 1.4 Termination

The sweep stops at the first of (`src/straps.cpp:338-368`):

1. `pos` passes the far limit → outer loop ends (`!beyond_limit(pos)`,
   `src/straps.cpp:338`);
2. a strap's *near* edge reaches/passes the far limit →
   `at_or_beyond_limit(...)` returns immediately — "no portion of the strap is
   inside the limit" (`src/straps.cpp:361-364`);
3. a strap's *center* passes the far limit → `beyond_limit(group_pos)`
   returns (`src/straps.cpp:365-368`).

Consequence: a final strap whose near edge is still inside the limit but whose
far edge overhangs is **kept** — only its *length* is clipped to the extent
(`clipToExtent` clips length, never width or position;
`src/straps.cpp:411-460`, comment at 490-498). Seen in the defok: met5 VSS
last stripe at `y = 100640 = core.yMax`, overhanging by half its width.

### 1.5 `-number_of_straps`

Counts **sweep positions (groups)**, not individual metal stripes. `strap_count`
is incremented once per outer-loop iteration, after all nets of the group are
processed (`src/straps.cpp:403-407`). Verified:
`core_grid_strap_count.defok` with `-number_of_straps 2` produces 2 VSS + 2 VDD
stripes (4 total).

### 1.6 `-snap_to_grid`

- The track grid for the layer/direction is loaded once
  (`src/straps.cpp:211-214`).
- Each net's center is snapped to the nearest track that stays clear of the
  previous net's claimed track (`next_track`), ties favor the lower track
  (`src/techlayer.cpp:62-90`, called at `src/straps.cpp:344-347`); missing
  routing grid → hard error PDN 215 (`src/straps.cpp:86-93`).

### 1.7 `-allow_out_of_core`

- Origin stays at the **core** near edge; only the sweep *limit* moves out to
  the die far edge, and the die-bounds rejection uses the die area
  (`src/straps.cpp:245-273`, `386-394`).
- The offset sanity check (`checkLayerOffsetSpecification`, PDN 185) likewise
  measures against the die far edge when set
  (`src/straps.cpp:113-147`).

### 1.8 `-starts_with` on a stripe

`add_pdn_stripe -starts_with` maps POWER→1 / GROUND→0 (else PDN 1035;
`src/pdn.tcl`, `proc get_starts_with`). `PdnGen::makeStrap` calls
`setStartWithPower()` only when the stripe specifies it
(`src/PdnGen.cc:687-689`); otherwise the component keeps the grid-level order
it inherited at construction (`src/grid_component.cpp:29-31`). With
`-followpins`, `-starts_with` is explicitly ignored with warning PDN 211
(`src/pdn.tcl:520-528`).

Tcl requirements: `-width` and `-pitch` are mandatory for non-followpin
stripes (PDN 1008/1009); `-spacing`/`-offset` default to 0
(`src/pdn.tcl:392-442`).

### 1.9 Followpins

- `PdnGen::makeFollowpin` builds a `FollowPins` object; pitch/offset are
  **not user-settable** — the constructor derives them
  (`src/PdnGen.cc:658-667`, `src/straps.cpp:515-529`).
- `determinePitch()`: skips rows whose site has a row pattern (hybrid rows);
  takes the smallest site height as the standard row height; sets rail pitch =
  `2 × row_height`; errors PDN 190 if no rows (`src/straps.cpp:531-560`).
- Per row: if the site height is an integer multiple of the row height, rails
  are placed at every internal row boundary plus both edges; otherwise a
  single rail pitch = site height is used
  (`src/straps.cpp:606-632`).
- Net assignment: only MX ("FS") and R180 ("S") orientations invert the
  master Y axis; R0/MY do not. Rows of even standard-row multiple always start
  with ground; odd-height rows start with power iff flipped
  (`src/straps.cpp:633-651`). Rails then alternate
  (`src/straps.cpp:684-694`).
- Width, if not given, is the minimum `DY` over core-cell supply-pin routing
  geometry (`src/straps.cpp:695-756`); still subject to the min-width check
  (`src/straps.cpp:758-762`).

---

## 2. Grid-level `-starts_with` (define_pdn_grid)

Not dead. It sets `Grid::starts_with_power_`
(`src/grid.cpp:39-46`; Tcl default when omitted is **ground**, `set
start_with_power 0`, `src/pdn.tcl:887-889`). Every `GridComponent` copies the
grid's value at construction (`src/grid_component.cpp:29-31`) and, absent a
per-component override, `getNets()` returns the domain nets in that order
(`src/grid_component.cpp:565-571`): power-first =
`[power, (switched), ground]`, ground-first = `[ground, power, (switched)]`
(`src/domain.cpp:74-95`).

Effect at stripe level: the net order decides **which net's stripe sits at
`pos_k = origin + offset + k·pitch`** and which is offset by `group_pitch`
(§1.2) — i.e. it swaps the VDD/VSS phases. It likewise orders ring nesting
(innermost = first net, §6) and repair channels. A stripe-level `-starts_with`
overrides it for that stripe only (`src/PdnGen.cc:687-689`); `-nets` bypasses
ordering entirely (`src/grid_component.cpp:567-570`).

Confirmed by artifact: `core_grid_strap_count` defines the grid with no
`-starts_with` → VSS stripes sit at the offset positions (`25140, 35140`),
VDD at `+pitch/2` — ground-first default.

---

## 3. Via insertion (incl. non-adjacent layers)

The C++ rewrite **does support stacked vias across non-adjacent layers**.
There is no adjacency requirement anywhere in the via path.

- `Connect` requires the two endpoint layers to differ, both be routing
  layers, and both be on the same side of the frontside/backside boundary
  (PDN 3/4/5, PDN 1200; `src/connect.cpp:32-72`). Endpoints are ordered
  lower/upper by routing level; every layer in between is collected
  (`src/connect.cpp:74-91`).
- Via *candidates* are generated per connect rule in
  `Grid::getIntersections` (`src/grid.cpp:730-809`): both endpoint layers must
  have shapes; only same-net pairs are considered; the rects must **overlap
  with positive area** (`overlaps()`, not mere touching —
  `src/grid.cpp:787-790`); the candidate area is the endpoint-shape
  intersection (`src/grid.cpp:792-798`). No stripe is required on intermediate
  routing layers for a candidate to exist.
- `Connect::makeVia` (`src/connect.cpp:531-720`): snaps the intersection to
  the manufacturing grid (off-grid center → dummy via,
  `src/connect.cpp:543-584`); then builds the stack over **all** routing
  layers between the endpoints (`getAllRoutingLayers()`,
  `src/connect.cpp:629`), calling `makeSingleLayerVia` once per adjacent
  pair (`src/connect.cpp:648-696`), with an iterative rebuild that widens
  shared-layer pads until width tiers stabilize
  (`src/connect.cpp:641-710`). The finished stack is written by
  `DbGenerateStackedVia`, which may add patch metal (`DRCFILL`) on
  intermediate layers (`src/via.cpp:931-1079`, patch at `1057-1069`).
- So `add_pdn_connect -layers {met1 met5}` with met1/met5 endpoint shapes
  attempts a full met1→met2→met3→met4→met5 stack; whether met4 has its own
  stripes is irrelevant to candidate formation.
- If the endpoints do not overlap, no candidate exists at all — there is no
  "non-adjacent" warning. If any level of the stack has no legal via, a dummy
  via is built and warning **PDN 110** is emitted: `"No via inserted between
  {} and {} at {} on {}{}"` (`src/via.cpp:1122-1130`), recorded as
  `FailedViaReason::kBuild` (`src/via.cpp:1132`). This replaces the legacy
  PDN-0042 adjacency warning; PDN-0042 does not exist in this source.
- Enclosure/fit: an endpoint that is not modifiable (or has ITerm connections)
  must fit the via in x *and* y; a modifiable stripe must fit only across its
  width and may be patched along its length
  (`src/connect.cpp:654-681`).
- Obstructions on any intermediate layer delete the candidate
  (`FailedViaReason::kObstructed`, `src/grid.cpp:1071-1111`).
- `Via::writeToDb`: if bottom/middle/top shape sets are all empty, the via is
  marked `FailedViaReason::kBuild` (`src/via.cpp:3044-3061`).

---

## 4. Dead-parameter audit

Method: every option in the Tcl `parse_key_args` lists was traced to its C++
consumer. Result — almost everything is live; the genuinely dead ones are:

| Parameter | Verdict |
|---|---|
| `add_pdn_stripe -starts_with` | Live (per-stripe override, `src/PdnGen.cc:687-689`); ignored only with `-followpins` (PDN 211) |
| `define_pdn_grid -starts_with` | Live — default net order for the whole grid (§2) |
| `define_pdn_grid -pins` | Live: validated at check time (PDN 111 if the layer carries no shapes, `src/grid.cpp:923-932`), reported (`src/grid.cpp:705-714`), and passed to `writeToDb` to create real pins (`src/grid.cpp:1291-1295`) |
| `define_pdn_grid -obstructions` | Live: stored (`src/grid.cpp:39-46`), consumed by `Grid::makeRoutingObstructions`, which turns the grid's own shapes on those layers into routing obstructions (`src/grid.cpp:283-300`) |
| `define_pdn_grid -macro -halo` | Live (macro grids only): Tcl parses it (`src/pdn.tcl:1034-1042`), passes it through (`src/pdn.tcl:1120`), C++ stores via `addHalo` (`src/PdnGen.cc:587-589`) and reads it for the grid region, obstruction expansion and reporting (`src/grid.cpp:1813, 1838, 2049, 2159-2162`). Not accepted for stdcell core grids at all (core parser has no `-halo` key, `src/pdn.tcl:865-868`) |
| `add_pdn_stripe` rail pitch/offset (legacy followpin opts) | Do not exist in the Tcl API — followpin geometry is fully derived (§1.9). Not "parsed but dead"; removed |
| `rails_start_with` (legacy) | Not parsed anywhere in `src/pdn.tcl`. Removed |
| `define_pdn_grid -macro -pin_direction` | **Dead**: parsed, warns PDN 1024 "has been deprecated", return value discarded (`src/pdn.tcl:987`, `proc deprecated` at `src/pdn.tcl:855`) |
| `add_pdn_ring -power_pads` / `-ground_pads` | Deprecated but **aliased**: presence sets `-connect_to_pads` (`src/pdn.tcl:410-414`) |
| `pdngen -verbose` | Deprecated, discarded (`src/pdn.tcl:25`) |

Minor bug noticed while auditing (report-only): `Grid::report()` prints
"Routing obstruction layers:" but iterates `pin_layers_` instead of
`obstruction_layers_` (`src/grid.cpp:715-724`).

---

## 5. Zero-width degeneration

**No user-reachable zero-width stripe exists** in the C++ implementation:

- Regular stripes: Tcl requires `-width` (PDN 1008, `src/pdn.tcl:392-410`);
  `checkLayerSpecifications` → `checkLayerWidth` errors PDN 106 when
  `width < min_width` (`src/grid_component.cpp:411-427`, called from
  `src/straps.cpp:78` and `src/grid.cpp:188`). `min_width > 0` for every
  routing layer, so width 0 is rejected before any shape is built.
- Followpins without `-width` derive width from pin geometry (never zero;
  §1.9), and are checked the same way (`src/straps.cpp:758-762`).
- `Shape::writeToDb` writes each rect verbatim via `odb::dbSBox::create` —
  there is no zero-width special case in the C++ writer
  (`src/shape.cpp:394-420`). The legacy `write_def` degeneration path is gone.

What *does* still appear in DEF output are lines like
`NEW M2 0 + SHAPE FOLLOWPIN ( 14600 14850 ) VIA23`
(`test/asap7_M1_M3_followpins.defok`). These are **not zero-width stripes**:
they are the DEF rendering of via-placement SBoxes created by
`odb::dbSBox::create(wire, via, x, y, type)` (`src/via.cpp:704`, also
`src/via.cpp:387, 766, 857`). The wire shape type comes from the via
endpoints — `FOLLOWPIN` when both endpoints are followpin shapes
(`src/via.cpp:3048-3053`) — and the SBox carries the via at a single point,
which the DEF writer emits as a zero-width point path. Dummy vias write
nothing at all (`DbGenerateDummyVia::generate` returns `{} `,
`src/via.cpp:1109-1135`).

---

## 6. Rings (summary)

The inner ring outline is the domain region bloated outward by the per-side
`-core_offsets` (`Rings::getInnerRingOutline`, `src/rings.cpp:242-247`;
`-pad_offsets` is the mutually exclusive alternative, resolved against the
placed pad ring into the same offset form, `src/rings.cpp:200-226`,
`src/pdn.tcl:443-454`). Net `i` (in `getNets()` order) gets the outline
bloated by `i` pitches — one `(width+spacing)` step along each layer's own
axis — so rings nest strictly outward with net 0 innermost
(`src/rings.cpp:303-330`). Edges are then emitted per side (bottom/top on the
horizontal layer, left/right on the vertical) as `RING` shapes; ring width on
a side is centered on the bloated edge and a single-layer ring reuses one
layer for both orientations (`src/rings.cpp:282-330`ff).

---

## 7. Comparison table (legacy Tcl pdngen → current C++)

"Legacy" = the pre-rewrite Tcl implementation as established in PG-rev
Phases 1–5 (geometric round-trip ground truth); "C++" = this source.

| Aspect | Legacy (Tcl) | Current C++ | Verdict |
|---|---|---|---|
| Stripe origin reference | `(stdcell_xMin, stdcell_yMin − max_rail_width/2)` | Near edge of voltage-domain (core) area: `core.yMin()` / `core.xMin` (`domain.cpp:117-123`, `straps.cpp:245-273`) | **Changed** |
| Base-net placement | `origin + offset + k·pitch` | Identical formula (`straps.cpp:338-339`) | Same |
| Second-net phasing | Implicit `pitch/2` interleave (separate code path) | **Group model**: `group_pitch = spacing + width` (`straps.cpp:305`); `-spacing` omitted → defaults to `pitch/net_count − width`, rounded down (`straps.cpp:49-56`), reproducing `pitch/2` as derived behavior | Same observable default; explicit override now possible |
| Termination | Stop at far edge | Stop when strap near-edge reaches far limit, center passes it, or sweep pos passes it; far-overhanging last strap kept, length-clipped (`straps.cpp:361-368`, `411-460`) | Same in practice; C++ documents the overhang rule |
| `-number_of_straps` | (per-stripe counting in legacy impl) | Counts sweep **positions/groups**, incremented after each group's nets (`straps.cpp:403-407`) | Semantics pinned: groups, not stripes |
| Via adjacency | PDN-0042 warned/skipped non-adjacent `{met1 met5}` pairs | No adjacency concept: any two routing layers form a stack over **all** intermediate routing layers (`connect.cpp:629, 648-696`); failure → PDN 110 + `kBuild` (`via.cpp:1122-1132`) | **Changed** (capability added) |
| Via candidate rule | Overlap of endpoint shapes | Same-net, positive-area overlap of endpoint shapes; intermediate stripes not required (`grid.cpp:774-798`) | Same, made explicit |
| Grid `-starts_with` | Default power-first (legacy behavior) | Live; **default is ground-first** when omitted (`pdn.tcl:886-890`); inherited by all components (`grid_component.cpp:29-31`) | Changed default |
| Stripe `-starts_with` | Override | Same (`PdnGen.cc:687-689`); ignored for followpins (PDN 211) | Same |
| Dead params | `rails_start_with` parsed-but-never-read | `rails_start_with` removed from API; only true dead param is `-pin_direction` (deprecated, discarded, `pdn.tcl:987`); `-halo` live for macro grids only; followpin pitch/offset not user-settable | Mostly cleaned up |
| Zero-width degeneration | `write_def` emitted zero-width point shapes as a stripe path degenerate case | No zero-width stripe path exists (PDN 106 rejects); surviving `metalN 0` DEF lines are via-placement SBoxes (`via.cpp:704`), not stripes | Degenerate stripe path **removed**; via-point rendering remains |

### Open / uncertain items (not determinable from source alone)

- Whether the ground-first default for omitted `-starts_with` was an
  intentional behavior change or an accident of the rewrite: the Tcl
  (`set start_with_power 0`) and the defok artifacts agree with each other,
  but no comment or changelog in the tree explains the choice.
- Exact DEF rendering of via SBoxes as `0`-width point paths is OpenDB
  (`dbSBox`/defout) behavior, outside `src/pdn/`; the PDN side only
  determines the wire shape type and the point (`src/via.cpp:704`,
  `src/via.cpp:3048-3053`).
