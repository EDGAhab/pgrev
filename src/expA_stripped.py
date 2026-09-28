#!/usr/bin/env python3
"""rev6 expA: WS1 unlabeled pipeline on GDSII with ALL cell names stripped.

Same pipeline as src/expB_unlabeled.py (rev5 expB), except the GDSII front end:
instead of gdspy, it uses src/gds_name_strip_reader.py -- a pure-stdlib parser
that provably discards every name-bearing record (LIBNAME/STRNAME/SNAME/
STRING/PROPVALUE) and returns only integer (layer, datatype, bbox) tuples.
An adversarial name-mutation check (STRNAME/LIBNAME rewritten to via-cell-like
decoys) must yield byte-identical rects before the pipeline proceeds.

via_name recovery is purely geometric:
  - cut layer from the attacker's (gds layer, datatype) -> cut table
    (legitimate input: a foundry GDS always carries layer attribution);
  - via size (w x h) measured from the cut-layer rectangle;
  - combined as "{cut}_{w}x{h}". The {cut} prefix is the cut-layer identifier
    from the attacker's own layer table (process-stack knowledge, same class
    as the SPAN table) -- formatted here only as an internal identifier, and
    NEVER read from any GDS cell name.

Usage:
  python3 src/expA_stripped.py
Outputs (new tag dir, expB artifacts untouched):
  data/sky130hd_gcd_gds_strict/pg_shapes.csv
  data/sky130hd_gcd_gds_strict/expA_verdicts.json
"""
import csv, json, os, re, sys
from collections import defaultdict, Counter

REPO = os.path.expanduser("~/pgrev")
TAGDIR = f"{REPO}/data/sky130hd_gcd_gds_strict"
GDS_SRC = f"{REPO}/data/sky130hd_gcd_gds/gcd_top.gds"
TRUTH = f"{REPO}/data/sky130hd_gcd/pg_shapes.csv"

sys.path.insert(0, f"{REPO}/src")
from gds_name_strip_reader import read_flat_gds, mutated_copy

# attacker's (gds layer, datatype) -> (ODB layer label, kind) table.
# authoritative GDS numbers from platforms/sky130hd/sky130hd.lyt (.drawing).
GDS2ODB = {
    (68, 20): ("met1", "wire"),
    (68, 44): ("met1-met2", "via"),   # ODB cut layer "via"
    (69, 20): ("met2", "wire"),
    (69, 44): ("met2-met3", "via"),   # ODB cut layer "via2"
    (70, 20): ("met3", "wire"),
    (70, 44): ("met3-met4", "via"),   # ODB cut layer "via3"
    (71, 20): ("met4", "wire"),
    (71, 44): ("met4-met5", "via"),   # ODB cut layer "via4"
    (72, 20): ("met5", "wire"),
}
# cut-layer identifier used ONLY as the internal via_name prefix.
# These are the ODB cut-layer names (process-stack knowledge, keyed by
# (layer, datatype) -- no GDS cell name is consulted).
CUTID = {"met1-met2": "via", "met2-met3": "via2",
         "met3-met4": "via3", "met4-met5": "via4"}
SPAN = {"met1-met2": ("met1", "met2"), "met2-met3": ("met2", "met3"),
        "met3-met4": ("met3", "met4"), "met4-met5": ("met4", "met5")}


def load_gds_polys(gds_path):
    raw, audit = read_flat_gds(gds_path)
    rects = []
    for r in raw:
        key = (r["gds_layer"], r["gds_datatype"])
        if key not in GDS2ODB:
            continue  # non-metal/cut layers out of scope for PDN recovery
        layer, kind = GDS2ODB[key]
        rects.append({"layer": layer, "kind": kind,
                      "x1": r["x1"], "y1": r["y1"],
                      "x2": r["x2"], "y2": r["y2"]})
    return rects, audit


class UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        p = self.p
        while p[a] != a:
            p[a] = p[p[a]]
            a = p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def overlap_or_touch(a, b):
    return not (a["x2"] < b["x1"] or b["x2"] < a["x1"] or
                a["y2"] < b["y1"] or b["y2"] < a["y1"])


def build_components(rects):
    n = len(rects)
    uf = UF(n)
    CELL = 20000  # 20 um buckets
    grid = defaultdict(list)
    for i, r in enumerate(rects):
        for gx in range((r["x1"] // CELL) - 1, (r["x2"] // CELL) + 2):
            for gy in range((r["y1"] // CELL) - 1, (r["y2"] // CELL) + 2):
                grid[(gx, gy)].append(i)
    wires = [i for i, r in enumerate(rects) if r["kind"] == "wire"]
    vias = [i for i, r in enumerate(rects) if r["kind"] == "via"]
    wire_by_layer = defaultdict(list)
    for i in wires:
        wire_by_layer[rects[i]["layer"]].append(i)
    via_by_cut = defaultdict(list)
    for i in vias:
        via_by_cut[rects[i]["layer"]].append(i)

    def candidates(i):
        r = rects[i]
        seen = set()
        for gx in range((r["x1"] // CELL) - 1, (r["x2"] // CELL) + 2):
            for gy in range((r["y1"] // CELL) - 1, (r["y2"] // CELL) + 2):
                for j in grid[(gx, gy)]:
                    # no j>i restriction (union-find is idempotent)
                    if j != i and j not in seen:
                        seen.add(j)
                        yield j

    for lay, idxs in wire_by_layer.items():
        s = set(idxs)
        for i in idxs:
            for j in candidates(i):
                if j in s and overlap_or_touch(rects[i], rects[j]):
                    uf.union(i, j)
    for cut, idxs in via_by_cut.items():
        lo, hi = SPAN[cut]
        targets = set(wire_by_layer.get(lo, []) + wire_by_layer.get(hi, []))
        for i in idxs:
            for j in candidates(i):
                if j in targets and overlap_or_touch(rects[i], rects[j]):
                    uf.union(i, j)
    cuts = sorted(via_by_cut, key=lambda c: SPAN[c][0])
    for c1, c2 in zip(cuts, cuts[1:]):
        if SPAN[c1][1] != SPAN[c2][0]:
            continue
        s2 = set(via_by_cut[c2])
        for i in via_by_cut[c1]:
            for j in candidates(i):
                if j in s2 and overlap_or_touch(rects[i], rects[j]):
                    uf.union(i, j)
    comps = defaultdict(list)
    for i in range(n):
        comps[uf.find(i)].append(i)
    return comps


def main():
    os.makedirs(TAGDIR, exist_ok=True)
    verdicts = {}

    # [1] name-stripped GDS read + adversarial name-mutation proof
    rects, audit = load_gds_polys(GDS_SRC)
    verdicts["gds_structures_seen"] = audit["n_structures"]
    verdicts["gds_boundary_records"] = audit["n_boundary"]
    verdicts["gds_text_records"] = audit["n_text"]
    verdicts["gds_path_records"] = audit["n_path"]
    verdicts["names_discarded"] = [
        {"record": rec, "value": val} for rec, val in audit["discarded_names"]]
    verdicts["attack_input_all_int"] = True  # asserted inside the reader
    mut_blob, mut_replaced = mutated_copy(
        GDS_SRC, {"STRNAME": "via_340x340_LEAK",
                  "LIBNAME": "via_via2_560x560_LEAKLIB"})
    with open("/tmp/expA_mut.gds", "wb") as f:
        f.write(mut_blob)
    rects_mut, _ = load_gds_polys("/tmp/expA_mut.gds")
    name_indep = (rects == rects_mut)
    verdicts["name_mutation_records_replaced"] = mut_replaced
    verdicts["name_mutation_rects_identical"] = name_indep
    assert name_indep, "extraction depends on GDS names -- aborting"
    verdicts["n_polys"] = len(rects)
    verdicts["polys_per_layer"] = {
        f"{l}": sum(1 for r in rects if r["layer"] == l)
        for l in sorted(set(r["layer"] for r in rects))}
    print(f"[1] name-stripped GDS read: {len(rects)} polygons; "
          f"structures={audit['n_structures']}, "
          f"names discarded={len(audit['discarded_names'])} "
          f"(TEXT={audit['n_text']}); "
          f"name-mutation proof: rects identical = {name_indep}")

    # truth oracle (verdicts only)
    truth = list(csv.DictReader(open(TRUTH)))
    tmap = {(r["layer"], int(r["x1"]), int(r["y1"]), int(r["x2"]), int(r["y2"])): r
            for r in truth}
    missing = [r for r in rects
               if (r["layer"], r["x1"], r["y1"], r["x2"], r["y2"]) not in tmap]
    verdicts["gds_vs_truth_missing"] = len(missing)
    verdicts["gds_vs_truth_extra"] = len(truth) - (len(rects) - len(missing))
    print(f"[1] polygons vs ODB truth: missing={len(missing)}, "
          f"extra={verdicts['gds_vs_truth_extra']}")

    # [2] union-find
    comps = build_components(rects)
    comp_list = sorted(comps.values(), key=len, reverse=True)
    verdicts["n_components"] = len(comp_list)
    verdicts["component_sizes"] = sorted([len(c) for c in comp_list], reverse=True)
    pure = 0
    for c in comp_list:
        nets = set(tmap[(rects[i]["layer"], rects[i]["x1"], rects[i]["y1"],
                         rects[i]["x2"], rects[i]["y2"])]["net"] for i in c)
        if len(nets) == 1:
            pure += 1
    verdicts["component_purity"] = f"{pure}/{len(comp_list)}"
    print(f"[2] union-find: {len(comp_list)} components, "
          f"sizes={verdicts['component_sizes']}, purity={verdicts['component_purity']}")

    # [3] PG identification
    def score(c):
        ws = [rects[i] for i in c if rects[i]["kind"] == "wire"] or [rects[i] for i in c]
        x1 = min(r["x1"] for r in ws); y1 = min(r["y1"] for r in ws)
        x2 = max(r["x2"] for r in ws); y2 = max(r["y2"] for r in ws)
        return (len(ws), (x2 - x1) * (y2 - y1))
    ranked = sorted(comp_list, key=score, reverse=True)
    pg = ranked[:2]
    pg_ok = all(
        len(set(tmap[(rects[i]["layer"], rects[i]["x1"], rects[i]["y1"],
                      rects[i]["x2"], rects[i]["y2"])]["net"] for i in c)) == 1
        for c in pg) and len({tmap[(rects[pg[0][0]]["layer"], rects[pg[0][0]]["x1"],
                                    rects[pg[0][0]]["y1"], rects[pg[0][0]]["x2"],
                                    rects[pg[0][0]]["y2"])]["net"],
                              tmap[(rects[pg[1][0]]["layer"], rects[pg[1][0]]["x1"],
                                    rects[pg[1][0]]["y1"], rects[pg[1][0]]["x2"],
                                    rects[pg[1][0]]["y2"])]["net"]}) == 2
    verdicts["pg_identification_top2_correct"] = bool(pg_ok)
    print(f"[3] PG identification: top-2 heuristic correct = {pg_ok}")

    # [4] polarity
    meta = json.load(open(f"{REPO}/data/sky130hd_gcd/design_meta.json"))
    rows = meta["rows"]; rh = meta["row_height"]
    rails = [i for c in pg for i in c
             if rects[i]["kind"] == "wire" and rects[i]["layer"] == "met1"
             and (rects[i]["x2"] - rects[i]["x1"]) >= (rects[i]["y2"] - rects[i]["y1"])
             and (rects[i]["y2"] - rects[i]["y1"]) < 1000]
    verdicts["n_rails_found"] = len(rails)
    votes = []
    for i in rails:
        r = rects[i]; cy = (r["y1"] + r["y2"]) / 2
        v = None
        for row in rows:
            if abs(cy - row["y"]) <= 241:
                v = "VSS" if row["orient"] == "N" else "VDD"
                break
            if abs(cy - (row["y"] + rh)) <= 241:
                v = "VDD" if row["orient"] == "N" else "VSS"
                break
        assert v, f"rail at cy={cy} matches no row edge"
        votes.append((i, v))
    comp_vote = {}
    for i, v in votes:
        c = next(k for k, cc in enumerate(pg) if i in cc)
        comp_vote.setdefault(c, []).append(v)
    agree = 0
    comp_net = {}
    for k, cc in enumerate(pg):
        vs = comp_vote[k]
        assert len(set(vs)) == 1, f"component {k} rails disagree: {set(vs)}"
        agree += len(vs)
        truth_net = tmap[(rects[cc[0]]["layer"], rects[cc[0]]["x1"],
                          rects[cc[0]]["y1"], rects[cc[0]]["x2"],
                          rects[cc[0]]["y2"])]["net"]
        assert vs[0] == truth_net, f"polarity {vs[0]} != truth {truth_net}"
        comp_net[k] = vs[0]
    verdicts["polarity_rails_unanimous"] = f"{agree}/{len(rails)}"
    verdicts["polarity_matches_truth"] = True
    verdicts["stripes_start_with_net"] = comp_net[0]
    print(f"[4] polarity: {agree}/{len(rails)} rails unanimous, "
          f"matches truth; comp nets = {comp_net}")

    # [5] rail/stripe classification
    mis = 0; ncls = 0
    cls_of = {}
    for k, cc in enumerate(pg):
        for i in cc:
            r = rects[i]
            if r["kind"] != "wire":
                continue
            ncls += 1
            horiz = (r["x2"] - r["x1"]) >= (r["y2"] - r["y1"])
            thin = min(r["x2"] - r["x1"], r["y2"] - r["y1"]) < 1000
            pred = "FOLLOWPIN" if (r["layer"] == "met1" and horiz and thin) else "STRIPE"
            cls_of[i] = pred
            t = tmap[(r["layer"], r["x1"], r["y1"], r["x2"], r["y2"])]["shape"]
            if pred != t:
                mis += 1
    verdicts["classification"] = f"{ncls - mis}/{ncls} correct, {mis} misclassified"
    print(f"[5] rail/stripe classification: {verdicts['classification']}")

    # [6] via span recovery
    wire_idx = defaultdict(list)
    for k, cc in enumerate(pg):
        for i in cc:
            if rects[i]["kind"] == "wire":
                wire_idx[rects[i]["layer"]].append(i)
    span_stats = {}
    for cut, (lo, hi) in SPAN.items():
        vs = [i for k, cc in enumerate(pg) for i in cc
              if rects[i]["kind"] == "via" and rects[i]["layer"] == cut]
        lo_hit = sum(1 for i in vs if any(
            overlap_or_touch(rects[i], rects[j]) for j in wire_idx.get(lo, [])))
        hi_hit = sum(1 for i in vs if any(
            overlap_or_touch(rects[i], rects[j]) for j in wire_idx.get(hi, [])))
        span_stats[cut] = {"n": len(vs), f"overlap_{lo}": lo_hit,
                           f"overlap_{hi}": hi_hit}
    verdicts["via_spans"] = span_stats
    for cut, st in span_stats.items():
        print(f"[6] via span {cut} {SPAN[cut]}: n={st['n']}, "
              f"overlap_lo={st['overlap_' + SPAN[cut][0]]}, "
              f"overlap_hi={st['overlap_' + SPAN[cut][1]]}")

    # [7] via_name recovery -- PURELY GEOMETRIC:
    #   cut id from attacker's (layer, datatype) table + w x h from the
    #   cut-layer rectangle. The "{cut}_" prefix is the cut-layer identifier
    #   (CUTID), never a GDS cell name.
    def geom_via_name(r):
        return f"{CUTID[r['layer']]}_{r['x2'] - r['x1']}x{r['y2'] - r['y1']}"
    via_name_ok = 0; via_name_tot = 0
    for k, cc in enumerate(pg):
        for i in cc:
            r = rects[i]
            if r["kind"] != "via":
                continue
            via_name_tot += 1
            pred = geom_via_name(r)
            t = tmap[(r["layer"], r["x1"], r["y1"], r["x2"], r["y2"])]["via_name"]
            if pred == t:
                via_name_ok += 1
    verdicts["via_name_recovery"] = f"{via_name_ok}/{via_name_tot}"
    verdicts["via_name_method"] = ("cut id from (gds layer,datatype) table + "
                                   "w x h from cut-rectangle geometry; "
                                   "no GDS cell name consulted")
    print(f"[7] via_name recovery (geometric): {verdicts['via_name_recovery']}")

    # [8] reconstruct labeled pg_shapes.csv (net names from DEF SPECIALNETS USE
    # -- same B3 label-leak as WS1/expB; geometry recovery does not use it)
    use = {}
    with open(f"{REPO}/data/sky130hd_gcd/floorplan.def") as f:
        for line in f:
            m = re.match(r"\s*-\s+(\S+).*USE\s+(POWER|GROUND)", line)
            if m:
                use[m.group(1)] = m.group(2)
    netname = {}
    for k, v in comp_net.items():
        want = "POWER" if v == "VDD" else "GROUND"
        netname[k] = next(n for n, u in use.items() if u == want)
    out_rows = []
    for k, cc in enumerate(pg):
        for i in cc:
            r = rects[i]
            if r["kind"] == "wire":
                w = min(r["x2"] - r["x1"], r["y2"] - r["y1"])
                out_rows.append({"net": netname[k], "layer": r["layer"],
                                 "shape": cls_of[i], "kind": "wire",
                                 "x1": r["x1"], "y1": r["y1"],
                                 "x2": r["x2"], "y2": r["y2"],
                                 "width": w, "via_name": ""})
            else:
                w = r["x2"] - r["x1"]
                out_rows.append({"net": netname[k], "layer": r["layer"],
                                 "shape": "STRIPE", "kind": "via",
                                 "x1": r["x1"], "y1": r["y1"],
                                 "x2": r["x2"], "y2": r["y2"], "width": w,
                                 "via_name": geom_via_name(r)})
    key = lambda d: (d["net"], d["layer"], d["shape"], d["kind"], d["x1"],
                     d["y1"], d["x2"], d["y2"], d["width"], d["via_name"])
    a = Counter(key(d) for d in out_rows)
    b = Counter(key({k: (int(v) if k in ("x1", "y1", "x2", "y2", "width") else v)
                         for k, v in d.items()}) for d in truth)
    only_a = sum((a - b).values()); only_b = sum((b - a).values())
    verdicts["reconstructed_vs_truth"] = \
        f"{len(out_rows)} rows; only_in_recon={only_a}, only_in_truth={only_b}"
    print(f"[8] reconstructed pg_shapes.csv vs truth: "
          f"{verdicts['reconstructed_vs_truth']}")

    if only_a == 0 and only_b == 0:
        with open(f"{TAGDIR}/pg_shapes.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["net", "layer", "shape", "kind",
                                              "x1", "y1", "x2", "y2",
                                              "width", "via_name"])
            w.writeheader()
            w.writerows(sorted(out_rows,
                              key=lambda d: (d["net"], d["layer"], d["kind"],
                                             d["x1"], d["y1"])))
        print(f"[8] wrote {TAGDIR}/pg_shapes.csv")
    with open(f"{TAGDIR}/expA_verdicts.json", "w") as f:
        json.dump(verdicts, f, indent=1)
    print("verdicts:", json.dumps(verdicts, indent=1))
    ok = (verdicts["n_components"] == 2 and only_a == 0 and only_b == 0
          and mis == 0 and agree == len(rails) == 96
          and via_name_ok == via_name_tot and audit["n_text"] > 0
          and name_indep)
    print("PIPELINE", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
