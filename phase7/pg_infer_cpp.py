#!/usr/bin/env python3
"""Phase 7: infer current-C++-pdn (define_pdn_grid/add_pdn_stripe) parameters
from extracted PG geometry.

Port of src/pg_infer.py. Core geometry-inversion logic carries over; the
forward-model constants below come from the C++ source study
(phase7/cpp-pdn-model.md).

Usage: python3 pg_infer_cpp.py --tag <tag>
Reads phase7/data/<tag>/pg_shapes.csv, design_meta.json
Writes phase7/data/<tag>/pdn_inferred.tcl (new-API Tcl) and prints a report.
"""
import argparse, csv, json, os, re, sys
from collections import Counter, defaultdict

PH7 = os.path.expanduser("~/pgrev/phase7")
TOL_DBU = 2  # tolerance for pitch/offset arithmetic in dbu

# ---- forward-model constants (from C++ source study: cpp-pdn-model.md) ----
# ORIGIN: voltage-domain (core) area near edge along sweep axis
#   (domain.cpp:117-123, straps.cpp:245-273). getCoreArea() is the merged-row
#   bbox (domain.cpp:133-135), i.e. the row-derived "core" in design_meta.json.
#   CHANGED vs legacy (stdcell_yMin - max_rail_width/2).
ORIGIN_MODE = "core_area"
# SECOND_NET_PHASE: group model. Net j (in starts_with order) sits at
#   pos_k + j*(width+spacing); -spacing omitted -> pitch/net_count - width,
#   so 2-net default phasing = pitch/2 (straps.cpp:49-56, 305, 338-347).
SECOND_NET_PHASE = "group_model"

def um(dbu, per): return dbu / per

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    a = ap.parse_args()
    d = f"{PH7}/data/{a.tag}"
    shapes = list(csv.DictReader(open(f"{d}/pg_shapes.csv")))
    meta = json.load(open(f"{d}/design_meta.json"))
    dbu_per_um = meta["dbu"]
    wires = [s for s in shapes if s["kind"] == "wire"]
    for s in wires:
        s.update({k: int(s[k]) for k in ("x1", "y1", "x2", "y2", "width")})
        s["cx"] = (s["x1"] + s["x2"]) / 2
        s["cy"] = (s["y1"] + s["y2"]) / 2
        s["dir"] = "H" if (s["x2"] - s["x1"]) >= (s["y2"] - s["y1"]) else "V"

    notes = []
    out = []
    out.append("# Inferred by pg_infer_cpp.py -- new-API (define_pdn_grid/add_pdn_stripe).")
    out.append("# Model: " + f"ORIGIN_MODE={ORIGIN_MODE}, SECOND_NET_PHASE={SECOND_NET_PHASE}")

    # ---- power/ground nets: from DEF SPECIALNETS USE ----
    use = {}
    # floorplan.def path: reuse legacy data dir def
    def_path = os.path.expanduser(f"~/pgrev/data/{a.tag}/floorplan.def")
    if not os.path.exists(def_path):
        def_path = f"{d}/floorplan.def"
    with open(def_path) as f:
        for line in f:
            m = re.match(r"\s*-\s+(\S+).*USE\s+(POWER|GROUND)", line)
            if m: use[m.group(1)] = m.group(2)
    power = {n for n, u in use.items() if u == "POWER"}
    ground = {n for n, u in use.items() if u == "GROUND"}

    def layer_dir(layer):
        dd = [s["dir"] for s in wires if s["layer"] == layer]
        return Counter(dd).most_common(1)[0][0] if dd else None

    def layer_min(layer):
        order = {"li1": 0, "met1": 1, "m1": 1, "met2": 2, "m2": 2, "met3": 3,
                 "m3": 3, "met4": 4, "m4": 4, "met5": 5, "m5": 5, "met6": 6}
        ml = re.match(r"([a-zA-Z]+)(\d+)", layer)
        if ml: return order.get(layer.lower(), 99)
        return 99

    # ---- origin reference: db core area (== row-derived core) ----
    if ORIGIN_MODE == "core_area":
        core = meta.get("db_core_area") or meta.get("core")
        assert core, "no core area in design_meta.json"
        ref_x, ref_y = core[0], core[1]
        if meta.get("db_core_vs_rowcore_dbu"):
            assert max(meta["db_core_vs_rowcore_dbu"]) <= TOL_DBU, \
                f"db core area != row core: {meta['db_core_vs_rowcore_dbu']}"
    else:
        raise ValueError(f"unknown ORIGIN_MODE {ORIGIN_MODE}")
    notes.append(f"origin ref=({ref_x},{ref_y}) dbu mode={ORIGIN_MODE} "
                 f"(core area, no legacy rail-width adjustment)")

    stripes = [s for s in wires if s["shape"] == "STRIPE"]
    rails = [s for s in wires if s["shape"] == "FOLLOWPIN"]
    rail_layers = sorted(set(s["layer"] for s in rails), key=layer_min)
    strap_layers = sorted(set(s["layer"] for s in stripes),
                          key=lambda l: (0 if layer_dir(l) == "V" else 1, layer_min(l)))

    # ---- rails ----
    rail_block = []
    for lay in rail_layers:
        w = Counter(s["width"] for s in rails if s["layer"] == lay).most_common(1)[0][0]
        rail_block.append((lay, w))
        notes.append(f"rail {lay}: width {um(w, dbu_per_um):.3f} um (followpins)")

    # ---- straps ----
    stripe_cmds = []
    grid_starts_with = None
    for lay in strap_layers:
        by_net = defaultdict(list)
        for s in stripes:
            if s["layer"] == lay:
                c = s["cx"] if s["dir"] == "V" else s["cy"]
                by_net[s["net"]].append(c)
        nets = sorted(by_net)
        assert len(nets) >= 1
        width = Counter(s["width"] for s in stripes if s["layer"] == lay).most_common(1)[0][0]
        pitches, firsts = {}, {}
        for n in nets:
            cs = sorted(by_net[n])
            firsts[n] = cs[0]
            if len(cs) > 1:
                diffs = [b - a for a, b in zip(cs, cs[1:])]
                p = Counter(round(x) for x in diffs).most_common(1)[0][0]
                assert max(abs(x - p) for x in diffs) <= TOL_DBU, f"non-uniform pitch {lay} {n}"
                pitches[n] = p
        pitch = Counter(pitches.values()).most_common(1)[0][0] if pitches else None
        if pitch is None:
            notes.append(f"{lay}: single strap per net -> pitch NOT identifiable")
            continue
        base_net = min(nets, key=lambda n: firsts[n])
        other_net = [n for n in nets if n != base_net]
        base_is_power = base_net in power
        sw = "POWER" if base_is_power else "GROUND"
        grid_starts_with = sw if grid_starts_with in (None, sw) else "MIXED!"
        lay_dir = layer_dir(lay)
        r = ref_x if lay_dir == "V" else ref_y
        offset_dbu = firsts[base_net] - r
        assert offset_dbu >= -TOL_DBU, f"negative offset {lay}"
        cmd = (f"add_pdn_stripe -grid grid -layer {lay} "
               f"-width {um(width, dbu_per_um):.3f} "
               f"-pitch {um(pitch, dbu_per_um):.3f} "
               f"-offset {um(offset_dbu, dbu_per_um):.3f} "
               f"-starts_with {sw}")
        if other_net:
            o = other_net[0]
            shift = firsts[o] - firsts[base_net]
            if abs(shift - pitch / 2) <= TOL_DBU:
                notes.append(f"{lay}: second net at pitch/2 (default phasing)")
            else:
                spacing_dbu = shift - width
                assert spacing_dbu > 0, f"bad spacing {lay}"
                cmd += f" -spacing {um(spacing_dbu, dbu_per_um):.3f}"
                notes.append(f"{lay}: second net shifted by spacing+width "
                             f"({um(spacing_dbu, dbu_per_um):.3f} um)")
            for n in other_net:
                assert abs((firsts[n] - firsts[base_net]) - shift) <= TOL_DBU
                if n in pitches: assert abs(pitches[n] - pitch) <= TOL_DBU
        stripe_cmds.append(cmd)

    assert grid_starts_with not in (None, "MIXED!"), "inconsistent starts_with"

    # ---- connect: collapse via-span chains (same as legacy) ----
    spans = set()
    for s in shapes:
        if s["kind"] == "via" and "-" in s["layer"]:
            b, t = s["layer"].split("-", 1)
            spans.add((b, t))
    parent = {}
    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(x, y): parent[find(x)] = find(y)
    for b, t in spans: union(b, t)
    chains = defaultdict(set)
    for b, t in spans: chains[find(b)].add((b, t))
    rail_set, strap_set = set(rail_layers), set(strap_layers)
    pairs = []
    for ch in chains.values():
        nxt = {b: t for b, t in ch}
        bs = set(nxt); ts = set(nxt.values())
        bottom = (bs - ts)
        assert len(bottom) == 1, f"non-linear chain {ch}"
        ordered, cur = [], bottom.pop()
        while True:
            ordered.append(cur)
            if cur not in nxt: break
            cur = nxt[cur]
        rails_in = [l for l in ordered if l in rail_set]
        straps_in = [l for l in ordered if l in strap_set]
        if rails_in and straps_in:
            first_strap = next(l for l in ordered
                               if l in strap_set and ordered.index(l) > ordered.index(rails_in[0]))
            pairs.append((rails_in[0], first_strap))
        for s1, s2 in zip(straps_in, straps_in[1:]):
            pairs.append((s1, s2))
    seen, upairs = set(), []
    for p in pairs:
        if p not in seen: seen.add(p); upairs.append(p)
    pairs = upairs
    def pair_key(p):
        b, t = p
        return (0 if b in rail_set else 1, strap_layers.index(t) if t in strap_set else 99)
    pairs.sort(key=pair_key)
    notes.append(f"via-span chains collapsed: {sorted(spans)} -> {pairs}")

    # ---- emit new-API Tcl ----
    out.append("")
    pwr = sorted(power); gnd = sorted(ground)
    out.append(f"set_voltage_domain -power {' '.join(pwr)} -ground {' '.join(gnd)}")
    out.append("")
    pin_layers = " ".join(strap_layers)
    out.append(f'define_pdn_grid -name grid -starts_with {grid_starts_with} '
               f'-voltage_domains {{CORE}} -pins "{pin_layers}"')
    out.append("")
    for c in stripe_cmds:
        out.append(c)
    for b, t in pairs:
        if b not in rail_set:
            out.append(f'add_pdn_connect -grid grid -layers "{b} {t}"')
    for lay, w in rail_block:
        out.append(f"add_pdn_stripe -grid grid -layer {lay} "
                   f"-width {um(w, dbu_per_um):.3f} -followpins")
    for b, t in pairs:
        if b in rail_set:
            out.append(f'add_pdn_connect -grid grid -layers "{b} {t}"')
    out.append("")
    out.append("pdngen")

    with open(f"{d}/pdn_inferred.tcl", "w") as f:
        f.write("\n".join(out) + "\n")
    print("\n".join(notes))
    print(f"\nwrote {d}/pdn_inferred.tcl")

if __name__ == "__main__":
    main()
