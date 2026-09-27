# Exact Recovery of PDN Grid Specifications from Layout Geometry

A reverse-engineering study on OpenROAD's `pdngen` — attack and defense.

**Author:** Feilian Huang, Independent Researcher (`fffeilian@gmail.com`)
**Preprint:** *Exact Recovery of PDN Grid Specifications from Layout Geometry:
A Reverse-Engineering Study on OpenROAD's pdngen* (`paper/attack-preprint/paper.tex`)

## What this is

**Attack (Phases 1–5).** Given a post-extraction layout database (ODB/DEF) containing
a power-delivery network, recover the *generator configuration* — the
`pdngen::specify_grid` parameters (width, pitch, offset, spacing, connect,
starts-with) — rather than just cloning geometry. A recovered spec lets an
attacker predict the grid across the full die from a local observation, or
regenerate the rules when inserting a Trojan / re-spinning a design.

Result: exact recovery (to the layout database unit grid) on 4 designs × 3 PDKs
(sky130hd/gcd, nangate45/gcd, sky130hd/aes, asap7/gcd); 4/4 round-trips with
wire rectangles and via sets item-wise identical (up to 16,403 vias).
The parameter→geometry map is injective on the quotient space after removing
dead parameters (`rails_start_with` is never read by the generator; `halo` and
rail pitch/offset have no geometric effect).

**Defense (Phase 6).** Three countermeasures evaluated:
- **E1 — interleaved decoy grids (effective):** inserting decoys at +P/4 breaks
  naive inference (133→169 wires, 2,907→5,994 vias), improves comparative IR
  drop by 61.2%, and leaves two fully equivalent 9-stripe VSS candidates —
  true vs. decoy intent is indistinguishable.
- **E2 — pitch jitter (partially effective):** naive inference fails at ≥2%
  jitter, but robust least-squares still recovers pitch within 1.2% at 15% jitter.
- **E3 — via dropout (falsified):** removing 10–50% of vias does not affect
  connect inference, while IR degrades 42–426%.

**Phase 7 — current-version reproduction.** Rebuilt OpenROAD from source
(HEAD `80c6be9`, Sep 2026) and reproduced the round-trip on the **new C++ pdngen
API** (`define_pdn_grid` / `add_pdn_stripe` / `add_pdn_connect`):
**3,051/3,051 shapes exact** (134 wires + 2,917 vias), zero symmetric difference.
Quirk re-tests: `{met1 met5}` non-adjacent connect is now a hard `PDN-0179`
error (legacy silently produced 0 vias); `-verbose`/`-pin_direction` are
explicitly deprecated; `-width 0` still rejected (`PDN-0106`); full via stacks
verified.

## Layout

| Path | Contents |
|---|---|
| `src/pg_infer.py` | The PG inference tool (legacy Tcl pdngen) |
| `phase7/pg_infer_cpp.py` | Inference tool for the current C++ pdngen API |
| `phase7/` | Current-OpenROAD build scripts, extraction, generation Tcl |
| `defense/` | E1/E2/E3 defense experiments |
| `reports/` | Phase reports (`phase-1.md` … `phase-7.md`) |
| `paper/attack-preprint/` | Preprint LaTeX source, review report, revision log |
| `env.sh` | Pinned legacy toolchain environment |

## Reproducibility

Legacy results pin: OpenROAD `f12e2f4`, OpenFlowScripts `96eb3de`,
Yosys `0.69+154` (see `env.sh`). Phase 7 pins OpenROAD HEAD `80c6be9` with
build notes in `phase7/build_openroad.sh` (SWIG 4.3, OR-Tools, CUDD, spdlog,
LEMON patch, `LINK_TIME_OPTIMIZATION=OFF`).

## Limitations (see paper §7.5)

Non-signoff IR/EM analysis, uniform-current / ideal-feed assumptions, no full
detailed route in defense evaluation, defense experiments mainly on gcd, and
2022 ORFS sky130hd LEF as input PDK data for the Phase 7 run.

## License

MIT — see `LICENSE`.
