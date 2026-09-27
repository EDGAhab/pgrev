# rev4 Task C — Innovus `addStripe` parameter-semantics mapping

**Date:** 2026-09-27
**Purpose:** respond to round-4 reviewer "no commercial tool coverage" at the
parameter-semantics level (document analysis only; no Innovus license, no measured runs).

**Conclusion口径:** *transferability analyzed at parameter-semantics level;
tool measurement listed as future work (no license).*

---

## 1. Sources

| # | Source | What it documents | URL |
|---|--------|-------------------|-----|
| S1 | qfliuyang/hipilot `skills/power-planning.md` (community EDA skill, Innovus-targeted) | Full `addStripe` usage examples: `-nets -layer -direction -width -spacing -set_to_set_distance -start_from -start_offset`; sky130 example; separate `sroute` rail step | https://github.com/qfliuyang/hipilot/blob/HEAD/skills/power-planning.md |
| S2 | T. Manikas, SMU, "Tutorial for Innovus 16.2" (2019-02-26), §4.3 Power Stripes | Add Stripes GUI: Basic tab = Net(s), Layer, Direction, Width, Spacing; Set Pattern = Set-to-set distance; First/Last Stripe = "Relative from core or selected area", start offset; Advanced tab = Snap wire center to routing grid | https://s2.smu.edu/~manikas/CAD_Tools/CPR/lib/Innovus_PR_Tutorial2019Feb.pdf |
| S3 | WSU EECE579 "Advanced MOS Digital IC Design" tutorial-innovus.pdf | Stripes alternate VDD/VSS across the core; vias added by a separate "Route → Special Route…" step ("The X squares are vias connecting the M1 and M2 wires") | https://eecs.wsu.edu/~ee434/Labs2/tutorial-innovus.pdf |
| S4 | Cadence Community forum (Digital Implementation), "Why use addstripe command run so long?" | Real-world full `addStripe` invocation exposing advanced options: `-number_of_sets`, `-set_to_set_distance`, `-start_from`, `-start_offset`, `-skip_via_on_wire_shape`, `-switch_layer_over_obs`, `-use_wire_group`, `-snap_wire_center_to_grid`, `-max_same_layer_jog_length`, `-padcore_ring_top_layer_limit`, `-block_ring_top_layer_limit` | https://community.cadence.com/cadence_technology_forums/f/digital-implementation/56939/why-use-addstripe-command-run-so-long |
| S5 | Auburn Univ. ELEC 5250/6250 slides, "ASIC Layout 2 — Digital Innovus" | Identifies "Tcl command: addStripe" as the power-stripe primitive | https://www.eng.auburn.edu/~nelson/courses/elec5250_6250/slides/ASIC%20Layout_2%20%20Digital%20Innovus.pdf |
| S6 | sharjeelimtiaz27/riscv-microarchitecture-lab, week05 P&R notes | `addStripe -nets {VDD VSS} -layer ... -direction vertical -width 1.0 -spacing 0.5 -set_to_set_distance 20.0` | https://github.com/sharjeelimtiaz27/riscv-microarchitecture-lab/blob/HEAD/docs/weekly_notebooks/week05_pnr.md |
| S7 | sohan2311 priority-encoder README (module 4.3–4.4) | addStripe then "**Step 4: Special Route (Add Vias)**: `sroute -connect {corePin} ...` — This connects power mesh from highest metal to METAL1" — confirms vias are a separate step | https://github.com/sohan2311/scalable-high-performance-priority-encoder-using-1d-array-to-2d-array-conversion/blob/HEAD/README.md |

No official Cadence Text Command Reference was accessible (requires support login);
all semantics below are triangulated from S1–S7 and labeled accordingly.

---

## 2. What `addStripe` generates (documented behavior)

`addStripe` places a **periodic set of equal-width parallel stripes** over a
rectangular placement area (the core by default, or `-area {x1 y1 x2 y2}`).
One *set* = one stripe per listed net in `-nets` order; the set repeats across
the area. Within a set, adjacent stripes are separated by `-spacing`; sets are
separated by `-set_to_set_distance`. The first stripe's position is anchored by
`-start_from {left|right|top|bottom}` (which boundary of the area the pattern
grows from) plus `-start_offset` (distance from that boundary, cf. S2 GUI:
"Relative from core or selected area"). Stripes alternate nets across the area:
S3 shows the resulting grid "alternating between VDD and VSS".

**Key structural fact:** with the standard two-net invocation
`-nets {VDD VSS}`, each set contains exactly 2 stripes, so the geometry is a
uniform two-interleaved-stripe grating with one period — the same class of
object our forward model describes.

---

## 3. Parameter对照表 (addStripe ↔ our forward-model bundle)

Our attack target (post-rev3) is the geometry-sufficient bundle
`{width, pitch, offset, spacing, nets, direction, layer, area}` per layer —
deliberately decoupled from `pdngen::specify_grid` key names.

| addStripe option | Our bundle param | Semantic mapping | Status |
|---|---|---|---|
| `-width` | `width` | Stripe width. Exact. | direct |
| `-spacing` | `spacing` | Edge-to-edge gap between adjacent stripes *within* a set (S1/S2 place Spacing next to Width in "Set Configuration", separate from the set pattern). Maps to our `spacing = shift − width` for the second net's stripe. | direct |
| `-set_to_set_distance` | `pitch` | Repeat period of the stripe-set pattern (S2 GUI "Set Pattern → Set-to-set distance"). For a 2-net set, `pitch` = set-to-set distance. | direct, with caveat C1 |
| `-start_offset` | `offset` | Distance from the area boundary to the first stripe (S2: "Relative from core or selected area"). | direct, with caveats C1, C2 |
| `-start_from` | (implicit) | Which boundary/orientation the pattern grows from; folds into the sign of `offset` and the `direction` axis in our model. | direct |
| `-nets {VDD VSS}` order | `nets` (net ordering / polarity) | One stripe per net per set in listed order → stripe↔net assignment repeats with the period; exactly our polarity model. | direct, with caveat C3 |
| `-direction {vertical\|horizontal}` | `direction` | Stripe orientation. Exact. | direct |
| `-layer` | `layer` | Single metal layer for the stripes. Exact. | direct |
| `-area {x1 y1 x2 y2}` | `area` | Rectangular placement domain (default = core). Our clipping domain. | direct, with caveat C4 |
| `-number_of_sets` | — | Count-based alternative to area fill (S4). Our model assumes area-fill; a count-limited pattern is a truncated subset, still covered geometrically. | out of scope (covered by geometry) |
| `-snap_wire_center_to_grid` | — | Quantization of stripe centers to the routing grid. Analogous to our dbu-rounding step. | unmeasured quirk (C5) |

Caveats:
- **C1 — datum convention unverified:** public docs do not pin down whether
  `-set_to_set_distance` / `-start_offset` are measured edge-to-edge,
  center-to-center, or edge-to-center. Our mapping treats them as a period and
  an anchor offset; the exact datum must be established by measurement.
- **C2 — offset reference unverified:** whether `-start_offset` measures to the
  stripe's leading edge or centerline is not documented publicly.
- **C3 — multi-net sets:** with 3+ nets per set our two-net polarity model does
  not apply; this is outside the current attack's coverage by design.
- **C4 — boundary truncation:** how stripes are clipped at `-area`/core edges
  (partial stripe kept vs dropped) is not documented publicly.
- **C5 — snapping:** `-snap_wire_center_to_grid {Grid|None}` exists (S2, S4);
  its quantization semantics are unmeasured.

---

## 4. Transferability argument (geometry → parameter bundle)

rev3 reframed the attack target as *the smallest parameter bundle sufficient to
reconstruct the geometry*, decoupled from the generating tool. The attack then
has two separable stages:

1. **Geometry → bundle (tool-agnostic):** detect the regular stripe grating per
   layer (least-squares pitch/offset, per §6 of the paper), measure widths, and
   assign nets per stripe position. This stage consumes only rectangles + net
   labels, not generator identity.
2. **Bundle → generator config (tool-specific table lookup):** translate the
   recovered bundle into the target generator's key names.

The mapping in §3 shows stage 2 is a near-mechanical translation for
Innovus `addStripe`: `width→-width`, `pitch→-set_to_set_distance`,
`offset→-start_offset`, `spacing→-spacing`, net order→`-nets` order,
`direction→-direction`, `layer→-layer`, domain→`-area`. Stage 1 does not depend
on whether the grating was made by `pdngen::specify_grid` or `addStripe`,
because both tools produce the same geometric class — an equal-period
repeating stripe set over a rectangular area with per-net assignment — as
documented in S1–S4. Therefore the inference method transfers **in principle**;
what is missing is only the measured confirmation (caveats C1–C5).

---

## 5. Honest boundaries — what CANNOT be claimed

1. **Via/connect inference does NOT transfer.** In Innovus, `addStripe` creates
   stripes only; vias are generated by a **separate** `sroute` (special route)
   step with its own parameters (`-layerChangeRange`, `-crossoverViaLayerRange`,
   `-nets`, per S3/S7). There is no Innovus-side analog of pdngen's `connect`
   pairs computed in the same configuration. Our connect/via-stack recovery
   (§5.4-equivalent) is pdngen-specific and cannot be carried over; any via
   analysis for Innovus would require a separate `sroute` parameter-semantics
   study, also unmeasured.
2. **No measured geometry.** All mappings above are document-level. dbu
   rounding, grid snapping (`-snap_wire_center_to_grid`), and boundary
   truncation behavior are unmeasured and are **not** claimed as verified.
3. **Datum conventions unknown** (C1, C2): edge vs centerline references for
   `-set_to_set_distance`/`-start_offset` cannot be asserted from public docs.
4. **Advanced options out of scope:** `-skip_via_on_wire_shape`,
   `-switch_layer_over_obs`, `-use_wire_group`, `-max_same_layer_jog_length`,
   `-padcore_ring_top_layer_limit`/`-block_ring_top_layer_limit`,
   `-number_of_sets`, `-master_stripe`-style variants are not covered by our
   model and were not analyzed.
5. **Hard constraint:** no Innovus license is available to us; tool measurement
   is listed as future work.

---

## 6. Conclusion

*Transferability analyzed at parameter-semantics level; tool measurement listed
as future work (no license).*

`addStripe` generates the same geometric object class (equal-period repeating
per-net stripe sets over a rectangular area) that our geometry→parameter-bundle
inference consumes, and its parameters map onto our bundle almost 1:1
(§3 table). The stripe-geometry half of the attack is therefore transferable in
principle. The via/connect half is **not** — Innovus separates stripe creation
from via generation (`sroute`), so that part of the pipeline stays
pdngen-specific until a separate `sroute` study is done.
