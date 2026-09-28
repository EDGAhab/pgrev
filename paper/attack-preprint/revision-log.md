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

## rev4 writing revision (2026-09-27)

### Experiments now reflected in text
- **Dropout-aware sweep (reports/rev4-exp1-dropout-rescan.md):** N=800 —
  inference 800/800, geometric round-trip 800/800, parameter-exact
  796/800 = 99.5%, 0 failures. 64/66 former failures resolved via the
  uniqueness argument (honestly caveated: truth records lost with
  ephemeral scratch, so these rely on uniqueness + round-trip rather
  than item-by-item truth comparison); 2 genuine duals
  (ws2_0082, ws2_0507) flagged AMBIGUOUS. met5 dropout threshold
  corrected to offset < width/2 (transcription error fixed; §2 now
  states the dropout rule as part of the forward model). 1-dbu spacing
  lesson documented (exact integer comparison shift == pitch//2).
- **End-to-end demo (reports/rev4-exp2-e2e-demo.md):** new §5.7 —
  recovered spec replayed on a floorplan with an inserted 50×50µm macro:
  141 wires / 2785 vias, 0 errors, 8 stripes cut at halo, 163/163 via4
  intact, 0 wires/vias inside macro; naive copy leaves 8 stripes
  shorting + 122 vias inside. Thesis: spec = executable intent,
  geometry = one-time instance. Boundaries stated (same generator,
  macro-grid declaration designer-standard, met1 rails unaffected).
- **Innovus addStripe mapping (reports/rev4-exp3-innovus-mapping.md):**
  new transfer-analysis paragraph in §8 (limitations) — parameter
  semantics map 1:1, but via/connect inference does NOT transfer
  (sroute separation); datum/snap/truncation unmeasured; no license,
  document-level analysis only. No claim of official Cadence manual use.

### Writing/structural changes
- **Reframe:** title kept; abstract/intro/conclusion shifted from
  "large exact-recovery attack" to identifiability characterization +
  negative defense results. Abstract rewritten (~190 words; see word
  count below): drops "from unlabeled polygons alone", uses "de-labeled
  ODB", distinguishes label gap (closed) from imaging gap (future work),
  drops "closing the harder gap" contradiction.
- **Contributions:** 8 → 5 (merged into: verified model + inference;
  identifiability evidence; label-free + e2e demo; rings/macro + Innovus
  transfer; defenses).
- **Threat model:** FOLLOWPIN/STRIPE/via-span labels now explicitly
  called out as generator leakage; §5.5's 0-misclassification result
  cited to show the kind-label step is trivial.
- **Terminology:** R0/MX → N/FS unified; "provably dead" → "dead by
  exhaustive source inspection".
- **§6 rewritten:** primary N=800 with 800/800, 796/800 = 99.5%, 4
  equiv, 0 failures; (¬start, o+shift) duality recast as analytic
  argument (0/553 empirical check kept as confirmation); equivalence
  catalog now 4 classes (+dropout-induced naming duality).
- **§5.6:** "Reviewers noted…" sentence removed.
- **E1:** IR tables/paragraphs labeled qualitative (uniform-current,
  ideal-feed, comparative only); "defender can invert the majority"
  downgraded to untested hypothesis.
- **E2:** 15 attempts → 13 legal runs (2 resampled at j=15%); j=0%
  errors now listed (pitch 0, offset 0).
- **Generalization §8:** rewritten honestly — 3 hand-picked configs +
  800 sweep + rings/macro covered; outdated "rings/macro uncovered"
  sentence fixed.
- **Related work:** added layout-regularity/template paragraph (Degate
  template matching, ML gate recognition recover instances not rules;
  ICC2 create_pg_mesh_pattern + Innovus addStripe as industrial PDN
  template practice) — all verifiable, no fabricated citations.
- **Table 1:** column widths retuned (2.4/5.8/4.6cm).

### Build (2026-09-27, rev4)
- Compiled with `~/bin/tectonic paper.tex --outdir build`: zero errors,
  zero LaTeX warnings; no overfull hbox >= 10pt (fixed three: Innovus
  mapping line, e2e `(pdn_inferred.cfg:` line, E1 residual line; all via
  rewording, no `\sloppy`). Output: `build/paper.pdf` (16 pages).
- Abstract: 194 words (target <200).
- User-facing copy refreshed at
  `~/workspace/goals/pdn-reverse-engineering-experiment/files/pgrev-attack-preprint.pdf`.
- `paper.docx` untouched; nothing pushed (per task constraints).

## rev5 writing revision (2026-09-27)

Source: five new experiment reports (rev5-expA/B/C/D/E). Writing only;
no experimental numbers altered. `paper.docx` untouched; nothing pushed.

- **Abstract:** rewritten to 199 words (target 150-200): fresh-seed
  99.75% / breadth 99.25% / real GDSII / e2e demo / cost model / defenses;
  Innovus kept at document-level; no "directly actionable".
- **New §2 (moved from Results tail):** "End-to-end motivation: the spec
  as executable intent" now fronts the paper as core motivation, followed
  by the manual-recovery cost model (three-layer argument: single grid
  hand-feasible; aes-scale 140-280 h; campaign = 8-16 human-years and
  statistics/negatives unobtainable by hand). All hardcoded § numbers
  after the insertion shifted +1 and were fixed.
- **Contributions:** item 2 now cites fresh-seed 99.75% with archived
  truth + breadth 99.25% + real GDSII; item 3 adds GDSII foundry input.
- **Threat model:** de-labeled regime validated on real GDSII stream-out
  (actual untrusted-foundry input).
- **§5.5 (label-free):** new GDSII paragraph — 3040 polygons, 6 TEXT
  stripped, 2 components, 96/96 polarity, 133/133 rail/stripe, 2907/2907
  vias, round-trip all exact; fixed union-find j>i ordering bug exposed
  by layer-grouped GDS order; foundry vs silicon-delayering split stated.
- **§6 sweep rewritten:** strict metric table (inference/round-trip/exact
  800/800, 798/800=99.75%, 2 equiv, 0 failures); fresh seed 20260929,
  truth archived, all round-trips measured; breadth paragraph (794/800 =
  99.25%, 3 fails = pdngen float/dbu 1-2 dbu cracks, ~5/1600 duals).
  Dropout naming duality given analytic condition
  o in [w/2-shift, w/2); (¬start,o+shift) rejection now states its exact
  boundary (holds for o >= w/2; the dropout window is the exception),
  0/553 + 0/800 confirmation.
- **E1:** 6 subsets -> 5 legal, design-level exactly 2 hypotheses
  (all-true vs all-decoy); via 4-class symmetry 100% (171/171 x2,
  162/162 x2, max diff 0), flagged as carrier-measured not theorem.
- **E2:** "degrades precision" -> "coarsens recovery"; offset error
  stated honestly as 2.97 µm ≈ 11% of pitch.
- **Dead parameters:** search scope expanded — full OpenROAD tree zero
  hits; ORFS only 7 inert .cfg settings; legacy Tcl removed, finding now
  archival not actionable ("directly actionable" removed from conclusion).
- **Review residue removed:** "earlier draft's transcription error",
  "design-doc numbering", "we therefore withdraw ... framing".
- **5Ω via resistance:** now "assumed nominal value; comparative only".
- **Conclusion/limitations:** 99.75%+99.25%, GDSII, E1 two-hypothesis;
  deflim notes 1600 configs across 3 PDKs.

### Build (2026-09-27, rev5)
- Compiled with `~/bin/tectonic paper.tex`: zero errors, zero warnings
  (also cleared all pre-existing rev4 warnings; added `array` package
  for raggedright table columns; no `\sloppy`). Output: `paper.pdf`
  (18 pages).
- Abstract: 199 words (target 150-200).
- User-facing copy refreshed at
  `~/workspace/goals/pdn-reverse-engineering-experiment/files/pgrev-attack-preprint.pdf`.
- `paper.docx` untouched; nothing pushed (per task constraints).

## rev6 writing revision (2026-09-28)

Source: sixth-round review (Weak Reject / Major Revision, significance
framing) + three new experiment reports (rev6-expA/B/C). Writing only;
no experimental numbers altered. `paper.docx` untouched; nothing pushed.

- **Abstract:** compressed to ~150 words: analytic identifiability
  theorem, exact recovery on 4 designs x 3 PDKs, label-free GDSII after
  constructive name-strip, 1600-config sweeps (1600/1600 inference and
  round-trip, 1595/1600 exact, zero failures), defenses one-liners, HEAD
  C++ N=200 all exact, legacy-Tcl results archival.
- **Threat model rewritten (reviewer point 2):** trojan narrative
  removed (a fab doing mask edits would not re-run pdngen). Honest
  scenarios: (a) spec as executable intent for re-spin / derivative
  floorplan (macro-insertion demo of §2); (b) compact, editable,
  replayable representation that polygon copying cannot provide under
  floorplan change. IP value stated candidly: most spec values are
  process-derived; the value is exact replayable reconstruction.
  Defensive "we state the label situation plainly" reworded.
- **Cost model → one paragraph (reviewer point 3):** pattern-based
  counting (identify the via-stack pattern once, propagate) replaces
  the per-via independent-judgment arithmetic; honest conclusion is
  expert-hours vs pipeline-seconds, scaling to hundreds of
  configurations. The "8-16 human-years" circular argument removed.
- **§7 → analytic identifiability theorem (reviewer point 1):**
  sufficient conditions (C1)-(C6) (≥2 stripes per (layer,net),
  o ≥ w/2, no S+W=pitch/2, ≥1 via per connect pair, dbu resolution,
  via-stack chain integrity), geometry taken modulo Z2 naming symmetry
  and blockage-superset equivalence; degenerate catalog with analytic
  conditions: dropout naming duality (o ∈ [w/2−shift, w/2)), the
  (¬start, o+shift) duality's exact boundary (fails for o ≥ w/2,
  dropout window is the exception), phasing coincidence, single-stripe
  layers, zero-yield connect pairs, float-truncation near-duals (expB
  source-level conclusion: %.3f serialization + microns_to_dbu
  round-half-up, forward map deterministic in dbu integers), dbu
  rounding classes.
- **Sweeps repositioned as implementation-correctness checks:** the
  theorem is analytic; sweeps certify the implementation realizes it.
  Evidence: exact-integer spacing comparison bug (1 dbu is not noise),
  union-find GDS layer-order bug, HEAD validity-domain pits.
  Numbers updated to rev6-expB final: 1600/1600 inference, 1600/1600
  round-trip, 1595/1600 exact (99.69%), 5 genuine duals, zero failures.
  7.5% vs 8.25% explained (different seeds; dropout trigger rate is
  seed-dependent).
- **1 dbu tolerance explained:** geometric comparison tolerance vs
  dbu-exact parameter check are two independent checks; tolerance
  cannot mask parameter-level errors.
- **Inverse procedural modeling related work:** added Stava et al.
  (2014) and Bokeloh/Wand/Seidel (2010) with verified bibliographic
  details (browser-verified; the assumed "Bokeloh et al. Inverse
  Procedural Modeling of Facade Layouts" attribution was incorrect and
  was not used).
- **HEAD results in main text:** C++ N=200 sweep (200/200 inference,
  200/200 round-trip, 200/200 exact = 100%), E2 reproduced on HEAD
  (naive crashes at j≥2%, robust pitch error ≤1.64% at 15%), validity
  domain pits (PDN-0191 5dbu grid, PDN-0175 pitch≥2(w+s), via-enclosure
  floors met4 w≥1.18µm / rail w≥0.26µm, legacy dict API STA-0562).
  Legacy-Tcl results marked archival; E1/E3 validated on 2022 version
  only.
- **GDS name-strip in §5.5 (expA):** pure-stdlib reader discards all
  name records (STRNAME/SNAME/STRING/LIBNAME/PROPVALUE, audit trail);
  adversarial rename leaves 3,040 rectangles byte-identical; via_name
  recovered purely geometrically 2907/2907; 16/16 verdicts match;
  round-trip PASS. Hierarchical GDS (SREF/AREF) listed as uncovered
  (fail closed).
- **Table 1:** column layout tidied (narrower tabcolsep, two-line
  straps/connect cells via \newline).
- **Defensive phrasing removed:** "Boundaries:", "we state plainly",
  "we claim absence from this retrieval, not a proof of non-existence",
  "make no precise claim", "unmeasured and not claimed", "Verdict:".

### Build (2026-09-28, rev6)
- Compiled with `~/bin/tectonic paper.tex`: zero errors, zero warnings
  (fixed two overfull hboxes introduced by rewording).
- Abstract ~150 words.
- User-facing copy refreshed at
  `~/workspace/goals/pdn-reverse-engineering-experiment/files/pgrev-attack-preprint.pdf`.
- `paper.docx` untouched; nothing pushed (per task constraints).
