#!/usr/bin/env python3
"""expB (rev5): WS1 unlabeled pipeline re-run with GDSII as the attack input.

Rewrites the lost /tmp/rev3/ws1/unlabeled.py from reports/rev3-ws1-unlabeled.md,
with one change at the front: the polygon source is a real GDSII file
(data/sky130hd_gcd_gds/gcd_top.gds), read with gdspy (independent reader).

Attack-side assumptions (== WS1 + foundry threat model):
  - per-layer polygon attribution known  -> GDS (layer, datatype)
  - cut layers grouped                    -> datatype 44 layers
  - metal stack order known               -> (68,20)<(68,44)<(69,20)<...
  - NO net names, NO kind tags            -> all TEXT records stripped first
  - die rows / row orients observable     -> design_meta.json (PDK knowledge)
  - cut-layer <-> metal-pair table known  -> process stack knowledge (B5)

Steps: TEXT strip -> extract -> union-find connectivity -> PG identification ->
polarity (row-orient vote) -> rail/stripe classification -> via span recovery ->
via_name recovery -> reconstruct labeled pg_shapes.csv -> verify vs truth.

Usage:
  python3 src/expB_unlabeled.py   # reads data/sky130hd_gcd_gds/gcd_top.gds
Outputs:
  data/sky130hd_gcd_gds/pg_shapes.csv   (reconstructed, labeled)
  data/sky130hd_gcd_gds/expB_verdicts.json
"""
import csv, json, os, sys
from collections import defaultdict

REPO = os.path.expanduser("~/pgrev")
TAGDIR = f"{REPO}/data/sky130hd_gcd_gds"
TRUTH = f"{REPO}/data/sky130hd_gcd/pg_shapes.csv"

# (gds layer, datatype) -> ODB layer / via-span label.
# Authoritative GDS numbers from platforms/sky130hd/sky130hd.lyt (.drawing).
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
CUTBASE = {"met1-met2": "via", "met2-met3": "via2",
           "met3-met4": "via3", "met4-met5": "via4"}
SPAN = {"met1-met2": ("met1", "met2"), "met2-met3": ("met2", "met3"),
        "met3-met4": ("met3", "met4"), "met4-met5": ("met4", "met5")}

def load_gds_polys(gds_path):
    import gdspy
    lib = gdspy.GdsLibrary()
    lib.read_gds(gds_path)
    cell = lib.top_level()[0]
    labels = cell.get_labels()
    n_text = len(labels)
    leaked = sorted(set(l.text for l in labels))
    # STRIP: the attack input must not contain any label information.
    polys = cell.get_polygons(by_spec=True)
    rects = []
    for spec, pl in polys.items():
        key = (int(spec[0]), int(spec[1]))
        if key not in GDS2ODB:
            continue  # non-metal/cut layers are out of scope for PDN recovery
        layer, kind = GDS2ODB[key]
        for p in pl:
            xs = [c[0] for c in p]; ys = [c[1] for c in p]
            # GDS user unit = 1 um, dbu = 0.001 um -> back to integer dbu
            x1, y1, x2, y2 = (int(round(v * 1000))
                              for v in (min(xs), min(ys), max(xs), max(ys)))
            assert x2 > x1 and y2 > y1, f"degenerate {key} {(x1,y1,x2,y2)}"
            rects.append({"layer": layer, "kind": kind,
                          "x1": x1, "y1": y1, "x2": x2, "y2": y2})
    return rects, n_text, leaked

class UF:
    def __init__(self, n):
        self.p = list(range(n))
    def find(self, a):
        p = self.p
        while p[a] != a:
            p[a] = p[p[a]]; a = p[a]
        return a
    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb: self.p[ra] = rb

def overlap_or_touch(a, b):
    return not (a["x2"] < b["x1"] or b["x2"] < a["x1"] or
                a["y2"] < b["y1"] or b["y2"] < a["y1"])

def build_components(rects):
    n = len(rects)
    uf = UF(n)
    # uniform grid bucket index on bbox centers
    CELL = 20000  # 20 um buckets
    grid = defaultdict(list)
    for i, r in enumerate(rects):
        cx, cy = (r["x1"] + r["x2"]) // 2, (r["y1"] + r["y2"]) // 2
        for gx in range((r["x1"] // CELL) - 1, (r["x2"] // CELL) + 2):
            for gy in range((r["y1"] // CELL) - 1, (r["y2"] // CELL) + 2):
                grid[(gx, gy)].append(i)
    wires = [i for i, r in enumerate(rects) if r["kind"] == "wire"]
    vias = [i for i, r in enumerate(rects) if r["kind"] == "via"]
    wire_by_layer = defaultdict(list)
    for i in wires: wire_by_layer[rects[i]["layer"]].append(i)
    via_by_cut = defaultdict(list)
    for i in vias: via_by_cut[rects[i]["layer"]].append(i)

    def candidates(i):
        r = rects[i]
        seen = set()
        for gx in range((r["x1"] // CELL) - 1, (r["x2"] // CELL) + 2):
            for gy in range((r["y1"] // CELL) - 1, (r["y2"] // CELL) + 2):
                for j in grid[(gx, gy)]:
                    # NOTE: no j>i restriction -- pair partners may live in a
                    # layer whose indices sort lower (gdspy groups by spec);
                    # union-find is idempotent so duplicate checks are harmless.
                    if j != i and j not in seen:
                        seen.add(j); yield j
    # 1) same-layer wires touching/overlapping
    for lay, idxs in wire_by_layer.items():
        s = set(idxs)
        for i in idxs:
            for j in candidates(i):
                if j in s and overlap_or_touch(rects[i], rects[j]):
                    uf.union(i, j)
    # 2) via overlaps wire on its lower/upper metal
    for cut, idxs in via_by_cut.items():
        lo, hi = SPAN[cut]
        targets = set(wire_by_layer.get(lo, []) + wire_by_layer.get(hi, []))
        for i in idxs:
            for j in candidates(i):
                if j in targets and overlap_or_touch(rects[i], rects[j]):
                    uf.union(i, j)
    # 3) adjacent cut layers: vias whose XY overlap (the via stack)
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
    verdicts = {}
    rects, n_text, leaked = load_gds_polys(f"{TAGDIR}/gcd_top.gds")
    verdicts["gds_text_records"] = n_text
    verdicts["gds_text_leaked_names"] = leaked
    verdicts["gds_text_stripped"] = True
    verdicts["n_polys"] = len(rects)
    verdicts["polys_per_layer"] = {f"{l}": sum(1 for r in rects if r["layer"] == l)
                                   for l in sorted(set(r["layer"] for r in rects))}
    print(f"[1] GDS read: {len(rects)} polygons; TEXT records found+stripped: "
          f"{n_text} (names were {leaked})")

    # truth oracle (for verdicts only, never fed to the pipeline)
    truth = list(csv.DictReader(open(TRUTH)))
    tmap = {(r["layer"], int(r["x1"]), int(r["y1"]), int(r["x2"]), int(r["y2"])): r
            for r in truth}
    missing = [r for r in rects
               if (r["layer"], r["x1"], r["y1"], r["x2"], r["y2"]) not in tmap]
    verdicts["gds_vs_truth_missing"] = len(missing)
    verdicts["gds_vs_truth_extra"] = len(truth) - (len(rects) - len(missing))
    print(f"[1] GDS polygons vs ODB truth: missing={len(missing)}, "
          f"extra={verdicts['gds_vs_truth_extra']}")

    comps = build_components(rects)
    comp_list = sorted(comps.values(), key=len, reverse=True)
    verdicts["n_components"] = len(comp_list)
    verdicts["component_sizes"] = sorted([len(c) for c in comp_list], reverse=True)
    # purity vs oracle
    pure = 0
    for c in comp_list:
        nets = set(tmap[(rects[i]["layer"], rects[i]["x1"], rects[i]["y1"],
                         rects[i]["x2"], rects[i]["y2"])]["net"] for i in c)
        if len(nets) == 1: pure += 1
    verdicts["component_purity"] = f"{pure}/{len(comp_list)}"
    print(f"[2] union-find: {len(comp_list)} components, "
          f"sizes={verdicts['component_sizes']}, purity={verdicts['component_purity']}")

    # PG identification: sort heuristic (wire count, bbox area), take top-2
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

    # polarity: rail = met1 + horizontal + thin; vote by row edge + orient
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
                v = "VSS" if row["orient"] == "N" else "VDD"  # bottom edge
                break
            if abs(cy - (row["y"] + rh)) <= 241:
                v = "VDD" if row["orient"] == "N" else "VSS"  # top edge
                break
        assert v, f"rail at cy={cy} matches no row edge"
        votes.append((i, v))
    comp_vote = {}
    for i, v in votes:
        c = next(k for k, cc in enumerate(pg) if i in cc)
        comp_vote.setdefault(c, []).append(v)
    # unanimity + cross-check vs truth
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
    verdicts["stripes_start_with_net"] = comp_net[0]  # placeholder, refined by pg_infer
    print(f"[4] polarity: {agree}/{len(rails)} rails unanimous, "
          f"matches truth; comp nets = {comp_net}")

    # rail vs stripe classification vs truth
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

    # via span recovery: cut-layer table + overlap verification
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

    # via_name recovery: pdngen names vias {cutbase}_{w}x{h} (dbu); w,h from geometry
    via_name_ok = 0; via_name_tot = 0
    for k, cc in enumerate(pg):
        for i in cc:
            r = rects[i]
            if r["kind"] != "via":
                continue
            via_name_tot += 1
            pred = f"{CUTBASE[r['layer']]}_{r['x2'] - r['x1']}x{r['y2'] - r['y1']}"
            t = tmap[(r["layer"], r["x1"], r["y1"], r["x2"], r["y2"])]["via_name"]
            if pred == t:
                via_name_ok += 1
    verdicts["via_name_recovery"] = f"{via_name_ok}/{via_name_tot}"
    print(f"[7] via_name recovery: {verdicts['via_name_recovery']}")

    # reconstruct labeled pg_shapes.csv (net names from DEF SPECIALNETS USE --
    # the same B3 label-leak as WS1; geometry recovery does not depend on it)
    use = {}
    with open(f"{REPO}/data/sky130hd_gcd/floorplan.def") as f:
        for line in f:
            import re
            m = re.match(r"\s*-\s+(\S+).*USE\s+(POWER|GROUND)", line)
            if m: use[m.group(1)] = m.group(2)
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
                                 "via_name": f"{CUTBASE[r['layer']]}_{w}x{r['y2'] - r['y1']}"})
    key = lambda d: (d["net"], d["layer"], d["shape"], d["kind"], d["x1"],
                     d["y1"], d["x2"], d["y2"], d["width"], d["via_name"])
    from collections import Counter
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
    with open(f"{TAGDIR}/expB_verdicts.json", "w") as f:
        json.dump(verdicts, f, indent=1)
    print("verdicts:", json.dumps(verdicts, indent=1))
    ok = (verdicts["n_components"] == 2 and only_a == 0 and only_b == 0
          and mis == 0 and agree == len(rails) == 96
          and via_name_ok == via_name_tot and n_text > 0)
    print("PIPELINE", "PASS" if ok else "FAIL")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
