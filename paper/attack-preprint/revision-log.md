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

## Build (2026-09-27)
- Compiled with `~/bin/tectonic -X compile paper.tex --outdir build`:
  exit 0, warnings only (2 pre-existing cosmetic overfull hboxes in the
  §5.2 variant-experiments paragraph and the §7.5 summary table — not
  introduced by this edit). Output: `build/paper.pdf` (104.45 KiB);
  user-facing copy refreshed at
  `~/workspace/your_files/pgrev-attack-preprint.pdf`.
