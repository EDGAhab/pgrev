# Phase 7 Report: Current C++ pdngen Reproduction

**Date:** 2026-09-27 UTC
**Generator:** OpenROAD HEAD `80c6be93c28244f9f72840852a667daef764a4ff` (2026-09-26)
**Input data:** 2022 ORFS sky130hd LEF (not current PDK)
**Author:** Feilian Huang <fffeilian@gmail.com>, Independent Researcher

## Summary

Built the current OpenROAD from source (HEAD 80c6be9) and reproduced the
Phase 1–5 round-trip experiment using the **new C++ pdngen API**
(`define_pdn_grid` / `add_pdn_stripe` / `add_pdn_connect`).

**Result: PASS.** The inferred configuration regenerates geometry that is
**exactly identical** to the truth: 3,051 shapes (134 wires + 2,917 vias),
zero symmetric difference.

## Build Notes

The build required significant dependency work (documented in
`~/pgrev/phase7/build_openroad.sh`):

- SWIG 4.3.0 built from source → `~/pgrev/phase7/deps/bin/swig`
- OR-Tools 9.14.6206 prebuilt → `~/pgrev/phase7/third-party/ortools/`
- CUDD 3.0.0 built → `~/pgrev/phase7/third-party/cudd/cudd-3.0.0/`
- spdlog 1.15.0 built from source → `~/pgrev/phase7/deps/` (system 1.12.0
  incompatible with GCC 13 + C++20: `fmt::basic_format_string` parse error)
- LEMON headers patched in `~/pgrev/phase7/deps/include/lemon/` for C++20
  (`std::allocator::construct/destroy` removed; use `allocator_traits`)
- CMake flags: `-DBUILD_PYTHON=OFF -DLINK_TIME_OPTIMIZATION=OFF`
  (Python wrapper hit the spdlog bug; LTO link OOM-killed at 8GB RAM)
- VM rebooted 4× during build (rootfs wipe); `/home` and
  `/var/cache/apt/archives` persist. Recovery: `~/pgrev/phase7/recover.sh`
- Binary: `~/pgrev/phase7/openroad-src/build/bin/openroad` (123MB, no LTO)

## Experiment: sky130hd/gcd

### Truth configuration (new API)
```tcl
define_pdn_grid -name grid -starts_with POWER -voltage_domains {CORE} -pins "met4 met5"
add_pdn_stripe -grid grid -layer met4 -width 1.6 -pitch 27.14 -offset 13.57 -starts_with POWER
add_pdn_stripe -grid grid -layer met5 -width 1.6 -pitch 27.2 -offset 13.6 -starts_with POWER
add_pdn_connect -grid grid -layers "met4 met5"
add_pdn_stripe -grid grid -layer met1 -width 0.48 -followpins
add_pdn_connect -grid grid -layers "met1 met4"
```

### Results
| Metric | Truth | Regen | Match |
|--------|-------|-------|-------|
| Wires | 134 | 134 | ✓ |
| Vias | 2,917 | 2,917 | ✓ |
| Total shapes | 3,051 | 3,051 | ✓ |
| Symmetric difference | — | — | **0** |

**Note:** Counts differ from legacy (133 wires, 2,907 vias). This is expected:
different generator. The C++ version also emits 1,824 DRCFILL shapes (filtered
from extraction as non-spec geometry).

### Via stack structure (new finding)
The `{met1 met4}` connect produces a **complete via stack**:
- met1-met2: 912 vias
- met2-met3: 912 vias
- met3-met4: 912 vias
- met4-met5: 181 vias (from `{met4 met5}` connect)

Total: 2,917 vias. The C++ pdngen **does** form complete intermediate via
stacks for non-adjacent layer connects (when they succeed).

### Inference accuracy
`pg_infer_cpp.py` recovered all parameters exactly:
- met4: width 1.600, pitch 27.140, offset 13.570 ✓
- met5: width 1.600, pitch 27.200, offset 13.600 ✓
- met1: width 0.480, followpins ✓
- connects: {met4 met5}, {met1 met4} ✓
- starts_with: POWER ✓
- origin: core_area (10120, 10880) dbu ✓

## Quirk Retests

### Q1: Non-adjacent {met1 met5} connect
**Result:** FAILS with `[ERROR PDN-0179] Unable to repair all channels.`

In the legacy Tcl pdngen, `{met1 met5}` produced 0 vias with PDN-0042 warnings.
In the current C++ version, it is a **hard error** (PDN-0179), not a silent
skip. The channel repair step cannot handle the tall via stack interfering
with intermediate stripes.

**Implication:** The C++ pdngen is stricter about non-adjacent connects.
The `{met1 met4}` case works (complete stack), but `{met1 met5}` does not.

### Q2: Dead parameters
**Result:** CONFIRMED DEPRECATED (not dead, but explicitly deprecated).

From `src/pdn/src/pdn.tcl`:
- Line 25: `pdn::deprecated flags -verbose` (for `pdngen -verbose`)
- Line 987: `pdn::deprecated keys -pin_direction` (for `define_pdn_grid`)

Both are accepted by the parser but have no geometric effect. They are
marked deprecated, not silently ignored.

### Q3: Zero-width stripe degeneration
**Result:** STILL GUARDED.

`add_pdn_stripe -width 0` triggers:
```
[ERROR PDN-0106] Width (0.0000 um) specified for layer met4 is less than
minimum width (0.3000 um).
```

The minimum-width check (PDN-0106) is present in the C++ version. Zero-width
stripes do not degenerate into points/lines; they are rejected.

## nangate45/gcd (attempted, incomplete)

Attempted with metal1/metal4/metal7 config. Blocked by:
1. DEF parse error (missing TAPCELL_X1 in LEF)
2. After LEF fix: PDN-0179 channel repair failure

The issue appears to be data/config related, not a generator bug. The
sky130hd/gcd result stands as the primary Phase 7 outcome.

## Files
- Truth ODB: `~/pgrev/phase7/truth.odb`
- Regen ODB: `~/pgrev/phase7/regen.odb`
- Extraction: `~/pgrev/phase7/data/sky130hd_gcd_cpp/`
- Inferred Tcl: `~/pgrev/phase7/data/sky130hd_gcd_cpp/pdn_inferred.tcl`
- Build script: `~/pgrev/phase7/build_openroad.sh`
- Recovery script: `~/pgrev/phase7/recover.sh`

## Conclusion

The current C++ pdngen (HEAD 80c6be9) **passes** the round-trip reproduction:
geometry → inferred config → regenerated geometry is exactly identical
(3,051/3,051 shapes). The forward model (core_area origin, pitch/2 phasing,
complete via stacks) is confirmed. Three quirks retested: non-adjacent
{met1 met5} now hard-errors (PDN-0179), deprecated params are explicitly
marked, zero-width is still guarded (PDN-0106).
