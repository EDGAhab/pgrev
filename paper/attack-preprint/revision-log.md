# Revision log — reviewer-driven writing revision (2026-09-26)

Source: external peer-review critique (Major Revision verdict) + earlier
`review-report.md` minor fixes. Writing fixes only; no experimental
numbers, data claims, or results were altered.

## Fix 1 — Threat model honesty (§1 + §4)
- Threat-model paragraph rewritten: attacker is now explicitly assumed to
  hold the post-extraction layout database (ODB/DEF-level net labels,
  `FOLLOWPIN`/`STRIPE` kinds, via bottom/top spans, die/core/row
  metadata); "decapsulated and imaged die" example removed.
- Added: imaging-only attacker needs connectivity tracing + power/ground
  net identification, NOT evaluated; unlabeled-polygon ablation listed as
  explicit future work.
- Softened all "geometry alone" phrasings → "extracted layout database"
  (abstract ×2, §1 intro, conclusion).
- §4 (Inference Algorithm) input description now notes it consumes the
  labeled ODB/DEF view, not unlabeled polygons.

## Fix 2 — Motivation (§1, after threat model)
- Two new paragraphs answering "why recover the spec if geometry can be
  cloned": (i) partial observation — image a sample region, predict the
  whole die; static cloning cannot extrapolate; (ii) regeneration under
  modification — Trojan insertion / re-spin / derivative porting needs
  generation rules, not a frozen shape snapshot.

## Fix 3 — Equivalence-class formalization + terminology (§6, §7.1, abstract, conclusion)
- §6 (`sec:ident`) rewritten: injectivity stated formally on the
  live-parameter quotient space (dead params quotiented out), with three
  explicitly listed degenerate regimes: (i) spacing+width == pitch/2
  phasing coincidence; (ii) single-stripe layer → pitch unidentifiable;
  (iii) zero-yield connect pair ({met1 met5} / PDN-0042) ≡ omitting the
  pair (noted as possibly version-specific).
- §7.1 terminology clash fixed: defense-side concept renamed to "intent
  ambiguity" with an explicit parenthetical distinguishing it from §6's
  configuration-level equivalence classes; removed the claim that it is
  "the same" equivalence class §6 hunted for. Honest boundary sentence kept.
- Abstract + conclusion reworded to match ("genuine two-way intent
  ambiguity"; "injective on the live-parameter quotient space").

## Fix 4 — Earlier minor fixes (from review-report.md)
- (a) "degrades up to $4.3\times$" → "degrades by up to $+426\%$" (abstract;
  §7 E3 already used unambiguous "+425.7%").
- (b) `quadir2016`: pages → 13(1), Article 6, pp. 6:1–6:34 (thebibliography
  env in paper.tex is the active bibliography; refs.bib is not \input).
- (c) `perez2020`: → IEEE Access, vol. 8, pp. 184013–184035, 2020.
- (d) "the exact-recovery attack of Section~5" → "Sections~3--5".
- (e) Added one sentence distinguishing anti-probing/tamper-evidence
  metal-mesh prior art (different threat model) next to the "no prior
  work" claim.

## Fix 5 — D1–D4/E1–E3 mapping (§7 defense-goal paragraph)
- Compact naming sentence added at first §7 use: D1 = no-via/floating
  decoys, D2 = pitch jitter, D3 = interleaved decoy grids, D4 = via
  dropout; E1↔D3, E2↔D2, E3↔D4.

## Fix 6 — E3 compression (§7.3)
- Via-dropout subsection cut to ~55% of prior length; kept: 912 stacks /
  2,736 vias, connect unchanged, up to +426% IR degradation, full-span
  deletion → {met4 met5} mis-inference, 49 components/net, 192 nodes
  disconnected, analytic projection of zero rail→strap stacks, falsified
  verdict tied to §6 via-chain integrity. Dropped: intermediate
  +42.4%/+108.1% values, "exit 0", "floating stripe island" detail, mesh
  refusal phrasing.

## Fix 7 — Table 1 connect column
- Tabular changed to `{lp{2.0cm}p{6.0cm}p{4.4cm}}` with `\small`; asap7
  merged to a single row; all connect pairs now fully visible (no
  truncation). Overfull-hbox warnings on the old table are gone.

## Fix 8 — "0.001 µm" de-emphasis
- Reframed as exact recovery "down to the layout database's unit grid"
  (abstract, §1 contributions, §5.1). No longer presented as a highlight.

## Fix 9 — §2 rail rule PDK annotation
- "R0 rows: VDD on top; MX rows: flipped" now annotated as observed on
  the sky130hd test designs, following the PDK's standard-cell
  definitions. Also narrowed "appears zero times in the pdngen source" →
  "in PdnGen.tcl" (the grep only covered that file).

## Fix 10 — Limitations strengthening (§7.5)
- Names the current C++ pdngen (`define_pdn_grid` / `add_pdn_stripe`);
  states {met1 met5} zero-via behavior and `write_def` stripe degeneration
  were observed only on the 2022 legacy Tcl implementation and may be
  version-specific bugs; lists porting to the current C++ pdngen as
  explicit future work.

## Build
- Compiled with `~/bin/tectonic -X compile paper.tex --outdir build`:
  **zero errors** (only cosmetic underfull-hbox warnings in the new §6
  enumerate). Output: `build/paper.pdf` (102.73 KiB); user-facing copy
  refreshed at `~/workspace/your_files/pgrev-attack-preprint.pdf`.

## Leftovers (not in scope / need experiments or user call)
- Reviewer's +P/2-decoy conditional qualification ("(in the no-spacing
  phasing used here)") not applied — small honesty improvement, needs a
  user nod.
- Equal-metal baseline for E1 IR claim, aes reproduction of E1, DRC/route
  evaluation, current-version port, and the unlabeled-polygon ablation are
  experiments — explicitly NOT done in this revision (some are now listed
  as future work in the paper).

## Fix 11 — Phase 7 current-C++ pdngen evidence (2026-09-27)

Source: `~/pgrev/reports/phase-7.md`. Replaced the "not re-verified"
limitation paragraph (§7.5): full round-trip on current OpenROAD
(HEAD `80c6be93c28244f9f72840852a667daef764a4ff`, Sept 2026, built from
source) with the new C++ API (`define_pdn_grid` / `add_pdn_stripe` /
`add_pdn_connect`) on `sky130hd/gcd`: exact PASS — 3,051/3,051 shapes
(134 wires + 2,917 vias), symmetric difference 0; parameters recovered
to unit grid (met4 1.600/27.140/13.570; met5 1.600/27.200/13.600);
complete intermediate via stack confirmed (912×3 met1–met4 steps +
181 met4–met5). Quirks differ from 2022 legacy: `{met1 met5}` is now a
hard error (PDN-0179), not a silent zero-via skip (PDN-0042);
`-verbose` / `-pin_direction` are explicitly marked deprecated in
`src/pdn/src/pdn.tcl` (parsed, no geometric effect); `-width 0` still
rejected (PDN-0106, min 0.3000 µm). Input caveat stated: 2022 ORFS
sky130hd LEF with current generator code. Defense experiments (E1–E3)
remain legacy-version only. Abstract + Conclusion updated with one
sentence each. All numbers taken verbatim from the Phase 7 report.

## Fix 12 — Second-round review revision (2026-09-27)

Source: `review-report-v2.md` (Major Revision / weak-reject verdict, 6
major + 6 minor issues, 3 author questions). Numbers taken only from
`reports/rev2-exp1-crop.md`, `rev2-exp2-multiseq.md`,
`rev2-exp3-ir-baseline.md`, `rev2-issue3-connect.md`,
`rev2-b3-robust-fit.md`, and verified entries in
`related-work-candidates.md`. Writing revision only; no new numbers
invented.

- **Issue 1 (threat model):** motivation narrowed — regeneration-under-
  modification (Trojan/re-spin/derivative) promoted to first reason;
  partial observation demoted to second, qualified reason. New §5.3
  "Partial-region extrapolation" (labeled ODB crops on sky130hd/gcd):
  20%-width strip and ~10%-area square → all parameters exact, full-die
  regeneration PASS; thin 10% strip → FAIL (1 VDD / 0 VSS met4 in-window,
  information deficit not numerical error). Stated rule: recovery depends
  on crop shape and ≥2–3 period instances per (layer, net); unlabeled
  imaged polygons still future work. Abstract untouched (never claimed
  partial imaging); contribution 3 extended.
- **Issue 2 (injectivity wording):** "injective" → "empirically
  identifiable" everywhere (abstract, §6, conclusion, contributions);
  "provably dead" kept only for `rails_start_with` (zero reads in
  PdnGen.tcl); rail pitch/offset → "dead by code inspection and case
  verification". §6 gains 4th degenerate regime: µm-to-dbu rounding
  collisions; closing paragraph admits non-proof status and untested
  joint offset≥pitch/2 × stripes_start_with transforms.
- **Issue 3 (connect semantics):** §2 vias/connect paragraph rewritten —
  connect pairs may span multiple routing layers; success decided by
  geometric overlap at crossings (orthogonal H×V succeeds; parallel
  narrow-rail vs wide-stripe triggers PDN-0042 skip-all), not "adjacency".
  asap7 {M1 M5} = cross-layer evidence (4×106-via stack); sky130
  {met1 met5} 0-via = parallel-overlap counterexample. §3 connect rule
  made precise: lowest endpoint rail → first strap endpoint above;
  intermediates are not endpoints (M2 in asap7 chain). "Only adjacent
  layers connect" claim removed.
- **Issue 4 (D3 reframe):** E1 attacker-side rewritten — naive now fails
  loudly under LS fit (residual 3571.1 dbu > 2 dbu gate); new paragraph
  "Adaptive attacker: multi-sequence inference" (k=2 recovers all 73
  stripe centers exactly; met4 P=27.140, met5 P=27.200 exact; phases at
  truth and truth+P/4). Honest verdict: D3 protects intent attribution,
  not geometry cloning. Footnote: multi-sequence bundle ≠ single legacy
  pdngen config (2nd specify_grid stdcell silently ignored; sequential
  runs ripup; E1a geometry is geometrically constructed). Subset-
  enumeration paragraph reframed as "What D3 does protect: intent
  attribution". Abstract + conclusion reworded to match.
- **Issue 5 (IR baseline):** "-61.2% negative cost" framing withdrawn.
  New three-way table (same mesh model): baseline 133/2907,
  66.90/38.89 mV/A worst/mean; E1a 169/5994, 25.98/11.63; P/2 equal-metal
  169/5994, 18,918.4 µm stripe length (identical to E1a), 24.51/11.54.
  Verdict: -61.2% fully explained by doubled metal; D3 vs equal-metal
  +6.0% worst / +0.8% mean; real price = 2× blockage, 2.06× vias.
  Absolute mV/A values reported, not only percentages. Summary-table D3
  row updated.
- **Issue 6 (scale):** §7.5 now states 3 distinct configs
  (sky130hd/gcd+aes share), no core ring/macro; commercial-generator
  (Innovus addStripe) port = future work.
- **Minor:** §4 Yosys note (synthesis only; PDN independent of Yosys
  version); 133/2907 vs 134/2917 explained (stripe-offset datum change:
  legacy −max_rail_width/2 → current core-area edge); §3 straps now
  least-squares + 2-dbu residual gate (per rev2-b3-robust-fit; 4/4
  round-trips still PASS, E1a naive still fails loudly); related work
  expanded with 10 verified entries (botero2021, rajarathnam2020,
  chen2015, wang2013, mosavirik2023, rajendran2014, imeson2013,
  rajendran2012, kahng2001, ziener2008); "no PDN-obfuscation prior art"
  phrased as systematic-search finding, not first-claim proof.

## Build (2026-09-27, rev2)
- Compiled with `~/bin/tectonic -X compile paper.tex --outdir build`:
  exit 0, warnings only (2 pre-existing cosmetic overfull hboxes in the
  §5.2 variant-experiments paragraph and the §7.5 summary table — not
  introduced by this edit). Output: `build/paper.pdf` (104.45 KiB);
  user-facing copy refreshed at
  `~/workspace/your_files/pgrev-attack-preprint.pdf`.

## Revision 3 — reviewer round 3 (Path A), 2026-09-27

Scope: respond to the third-round review (which challenged the attack
framing itself) by doing the requested experiments instead of
downgrading the paper. New experiments: WS1 unlabeled-polygon attack
MVP, WS2 randomized sweep (N=800 + N=630), WS3 ring/macro recovery.
Reports: `reports/rev3-ws1-unlabeled.md`, `reports/rev3-ws2-randscan.md`,
`reports/rev3-ws3-ringmacro.md`.

- **New §5.5 "Label-free attack" (Issue 1 core demand):** de-labeled
  polygons → union-find connectivity (exactly 2 components, purity 2/2,
  ~2 s) → PG identification (synthetic 300-signal-wire test: top-2
  still PG) → polarity via row orient + tap-cell library knowledge
  (96/96 rails; truth spot-checks 58/58, 228/228, 106/106 on the other
  three designs) → rail/stripe classification (0 misclassifications) →
  via-span recovery → unmodified `pg_infer.py`: all params exact incl.
  `stripes_start_with`=POWER, byte-identical cfg, round-trip 133/133
  wires, 2907/2907 vias. Honest limits stated: VDD/VSS global-swap +
  `starts_with`-flip Z2 naming symmetry (attacker without PDK knowledge
  recovers only up to the Z2 class); input is de-labeled ODB, not true
  imaging (delayering noise unmodeled); SPECIALNETS names are label
  leakage (naming only).
- **New §6 paragraphs "Randomized sweep" (Issue 2):** N=800 → 732/800 =
  91.5% dbu-exact; independent N=630 (seed 7) → 553/600 = 92.2%;
  width/pitch 100% in every success. Failures = stripe-dropout modeling
  gap (47/47 follow the drop rule; met4 threshold offset<width/2, met5
  offset<railw/2+width/2, 10-dbu bisection). Duality
  (¬starts_with, o+shift) refuted 0/553 (boundary stripe at ref+o always
  placed for o≥0). Catalog: Class P (20/20), Class S (30/30), single-
  stripe boundary; offset-translation class falsified.
- **New §5.6 "Core rings and macro grids" (scale):** ring 6/6 exact,
  141/141 wires, 2989/2989 vias; macro straps 6/6 exact, connect chain
  {metal4_PIN_ver metal5}/{metal5 metal6}/{metal6 metal7}, 84/84 wires,
  350/350 vias. Honest: blockages superset-equivalent (truth metal1–4
  vs observed metal4, geometrically identical); pin names/orient need
  LEF/DEF; pad_offset rings and rotated macros uncovered.
- **Issue 4 (reference frame):** explicit origins — legacy (10120,10640)
  dbu vs current core_area (10120,10880) dbu (240 dbu shift); both truth
  offsets 13.6, recovered 13.600 relative to each frame; 133→134 is the
  datum shift; 3051/3051 is a within-new-version round-trip.
- **Issue 5:** attack goal unified as "parameter bundle sufficient to
  reconstruct geometry" (generator-agnostic) — dissolves the D3/footnote
  contradiction. Intent-attribution value narrowed (matters only when
  the attacker needs the designer's original intent). D2/D3 stated as
  geometry post-processing needing flow integration (limitation). IR
  claims made qualitative (coarse model; no precise ±%/+6.0% claims);
  three-way table numbers kept with weakened wording.
- **Issue 6:** `rails_start_with` "provably dead" now carries the method
  (full-text search of PdnGen.tcl@f12e2f47 — file archived in repo;
  literal key access only; `dict keys` enumerates layer names; parameter
  absent from current C++ src/pdn/).
- **Minor:** abstract compressed 412 → 181 words; all 9 "honest*"
  occurrences removed/rewritten; E1a defined in the naming paragraph;
  1-dbu tolerance explained (absorbs pdngen float→dbu rounding) + via
  comparison key (net, layer-span, via-name, box); Table 1 note on
  asap7 M1/M2 dual rail layers; reproducibility paragraph with repo URL
  https://github.com/EDGAhab/pgrev (pg_infer.py, randscan.py,
  PdnGen.tcl); related work: search-scope statement + PDN
  synthesis/forward-problem discussion.

## Build (2026-09-27, rev3)
- Compiled with `~/bin/tectonic paper.tex --outdir build`: zero errors
  (added `\usepackage{amssymb}` for `\mathbb`); cosmetic overfull/underfull
  hbox warnings only. Output: `build/paper.pdf` (146,597 bytes);
  user-facing copy refreshed at
  `~/workspace/goals/pdn-reverse-engineering-experiment/files/pgrev-attack-preprint.pdf`.
