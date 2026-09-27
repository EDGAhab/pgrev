#!/usr/bin/env python3
"""Phase 4: infer minimal pdngen::specify_grid config from extracted PG geometry.

Forward model (verified against PdnGen.tcl @ f12e2f47):
- rails: one per row boundary, width from config; net assignment from row orient
  (rails_start_with is NEVER read -> dead parameter, omitted).
- straps: VDD/base grid at ref + offset + k*pitch; other net at
  ref + offset + shift + k*pitch, shift = pitch/2 (no spacing) or
  spacing + width. ref = (stdcell_xMin, stdcell_yMin - max_rail_width/2).
- connect: via spans collapse into chains; each chain -> {bottom top}.

Usage: python3 src/pg_infer.py --tag <tag>
Reads data/<tag>/pg_shapes.csv, design_meta.json, floorplan.def
Writes data/<tag>/pdn_inferred.cfg and prints a comparison/equivalence report.
"""
import argparse, csv, json, os, re, sys
from collections import Counter, defaultdict

REPO = os.path.expanduser("~/pgrev")
TOL_DBU = 2  # tolerance for pitch/offset arithmetic in dbu

def um(dbu, per): return dbu / per

def ls_fit(cs):
    """Least-squares fit of c_i = c0 + i*p (indices assumed consecutive).

    Robust pitch estimator (cf. paper §7.2): the minimum-variance estimator
    for near-arithmetic stripe centers, tolerant to sub-dbu numerical noise
    that can flip a mode-of-rounded-diffs vote. The residual gate below still
    rejects genuinely multi-modal (e.g. decoy-interleaved) grids, so the
    naive attacker keeps its fail-loud behavior on obfuscated inputs.
    """
    n = len(cs)
    sx = sum(range(n)); sxx = sum(i * i for i in range(n))
    sy = sum(cs); sxy = sum(i * c for i, c in enumerate(cs))
    den = n * sxx - sx * sx
    p = (n * sxy - sx * sy) / den
    c0 = (sy - p * sx) / n
    resid = max(abs(c - (c0 + i * p)) for i, c in enumerate(cs))
    return p, c0, resid

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    a = ap.parse_args()
    d = f"{REPO}/data/{a.tag}"
    shapes = list(csv.DictReader(open(f"{d}/pg_shapes.csv")))
    meta = json.load(open(f"{d}/design_meta.json"))
    dbu_per_um = meta["dbu"]
    wires = [s for s in shapes if s["kind"] == "wire"]
    for s in wires:
        s.update({k: int(s[k]) for k in ("x1", "y1", "x2", "y2", "width")})
        s["cx"] = (s["x1"] + s["x2"]) / 2
        s["cy"] = (s["y1"] + s["y2"]) / 2
        s["dir"] = "H" if (s["x2"] - s["x1"]) >= (s["y2"] - s["y1"]) else "V"

    notes = []  # equivalence / non-identifiability notes
    out = []
    out.append("# Inferred by pg_infer.py -- minimal geometry-affecting parameters only.")
    out.append("# Dead/omitted parameters (no geometric effect, verified in PdnGen.tcl):")
    out.append("#   ::halo, ::rails_start_with, rail pitch/offset, specify_grid name.")

    # ---- power/ground nets from DEF SPECIALNETS ----
    use = {}
    with open(f"{d}/floorplan.def") as f:
        for line in f:
            m = re.match(r"\s*-\s+(\S+).*USE\s+(POWER|GROUND)", line)
            if m: use[m.group(1)] = m.group(2)
    power = sorted(n for n, u in use.items() if u == "POWER")
    ground = sorted(n for n, u in use.items() if u == "GROUND")
    sw_idx = len(out)
    out.append('set ::stripes_start_with "POWER" ;  # placeholder, refined below')
    out.append(f'set ::power_nets "{" ".join(power)}"')
    out.append(f'set ::ground_nets "{" ".join(ground)}"')
    out.append("")

    # ---- rails ----
    rails = [s for s in wires if s["shape"] == "FOLLOWPIN"]
    rail_layers = sorted(set(s["layer"] for s in rails))
    max_rail_w = 0
    rail_block = []
    for lay in rail_layers:
        ws = [s for s in rails if s["layer"] == lay]
        w = Counter(s["width"] for s in ws).most_common(1)[0][0]
        max_rail_w = max(max_rail_w, w)
        rail_block.append(f"        {lay} {{width {um(w, dbu_per_um):.3f}}}")
    # reference frame for strap offsets
    core = meta["core"]
    ref_x = core[0]
    ref_y = core[1] - max_rail_w / 2

    # ---- straps ----
    straps = [s for s in wires if s["shape"] == "STRIPE"]
    def layer_dir(lay): return next(s["dir"] for s in straps if s["layer"] == lay)
    def layer_min(lay):
        return min(s["cx"] if layer_dir(lay) == "V" else s["cy"]
                   for s in straps if s["layer"] == lay)
    strap_layers = sorted(set(s["layer"] for s in straps),
                          key=lambda l: (0 if layer_dir(l) == "V" else 1, layer_min(l)))
    strap_block = []
    starts_with = None
    for lay in strap_layers:
        by_net = defaultdict(list)
        for s in straps:
            if s["layer"] == lay:
                c = s["cx"] if s["dir"] == "V" else s["cy"]
                by_net[s["net"]].append(c)
        nets = sorted(by_net)
        assert len(nets) >= 1
        width = Counter(s["width"] for s in straps if s["layer"] == lay).most_common(1)[0][0]
        pitches, firsts = {}, {}
        for n in nets:
            cs = sorted(by_net[n])
            firsts[n] = cs[0]
            if len(cs) > 1:
                p_est, _c0_est, resid = ls_fit(cs)
                p = int(round(p_est))
                assert resid <= TOL_DBU, (
                    f"non-uniform pitch {lay} {n}: LS pitch {p_est:.1f} dbu, "
                    f"max residual {resid:.1f} dbu > {TOL_DBU} dbu")
                pitches[n] = p
        pitch = Counter(pitches.values()).most_common(1)[0][0] if pitches else None
        if pitch is None:
            notes.append(f"{lay}: single strap per net -> pitch NOT identifiable")
            continue
        base_net = min(nets, key=lambda n: firsts[n])
        other_net = [n for n in nets if n != base_net]
        base_is_power = base_net in power
        sw = "POWER" if base_is_power else "GROUND"
        starts_with = sw if starts_with in (None, sw) else "MIXED!"
        lay_dir = layer_dir(lay)
        r = ref_x if lay_dir == "V" else ref_y
        c0 = firsts[base_net]
        offset_dbu = c0 - r
        assert offset_dbu >= -TOL_DBU, f"negative offset {lay}"
        spec = f"{lay} {{width {um(width, dbu_per_um):.3f} pitch {um(pitch, dbu_per_um):.3f} offset {um(offset_dbu, dbu_per_um):.3f}"
        if other_net:
            o = other_net[0]
            shift = firsts[o] - firsts[base_net]
            if abs(shift - pitch / 2) <= TOL_DBU:
                pass  # default half-pitch shift, no spacing key
            else:
                spacing_dbu = shift - width
                assert spacing_dbu > 0, f"bad spacing {lay}"
                spec += f" spacing {um(spacing_dbu, dbu_per_um):.3f}"
                notes.append(f"{lay}: {o} shifted by spacing+width ({um(spacing_dbu, dbu_per_um):.3f}um), not pitch/2")
            # verify other net's grid matches
            for n in other_net:
                assert abs((firsts[n] - firsts[base_net]) - shift) <= TOL_DBU
                if n in pitches: assert abs(pitches[n] - pitch) <= TOL_DBU
        spec += "}"
        strap_block.append("        " + spec)
    assert starts_with not in (None, "MIXED!"), "inconsistent starts_with across layers"
    out[sw_idx] = f'set ::stripes_start_with "{starts_with}" ;'

    # ---- connect: collapse via-span chains ----
    spans = set()
    for s in shapes:
        if s["kind"] == "via" and "-" in s["layer"]:
            b, t = s["layer"].split("-", 1)
            spans.add((b, t))
    # chain spans: bottom = never a top, top = never a bot
    bots = set(b for b, t in spans); tops = set(t for b, t in spans)
    # union-find over layers linked by spans
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
        # order chain bottom-to-top by walking adjacent spans
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
            # rail -> first strap layer above the lowest rail layer
            first_strap = next(l for l in ordered
                               if l in strap_set and ordered.index(l) > ordered.index(rails_in[0]))
            pairs.append((rails_in[0], first_strap))
        # consecutive strap layers within this chain (strap->strap)
        # NOTE: a single tall {rail strapB} vs split {{rail strapA} {strapA strapB}}
        # may yield identical via spans -> equivalence class (see Phase 5)
        for s1, s2 in zip(straps_in, straps_in[1:]):
            pairs.append((s1, s2))
    seen, upairs = set(), []
    for p in pairs:
        if p not in seen: seen.add(p); upairs.append(p)
    pairs = upairs
    # order: rail->strap first, then strap->strap by bottom layer order
    def pair_key(p):
        b, t = p
        return (0 if b in rail_set else 1, strap_layers.index(t) if t in strap_set else 99)
    pairs.sort(key=pair_key)
    conn = " ".join(f"{{{b} {t}}}" for b, t in pairs)
    notes.append(f"via-span chains collapsed: {sorted(spans)} -> {pairs}")

    out.append("pdngen::specify_grid stdcell {")
    out.append("    name grid")
    out.append("    rails {")
    out.extend(rail_block)
    out.append("    }")
    out.append("    straps {")
    out.extend(strap_block)
    out.append("    }")
    out.append(f"    connect {{{conn}}}")
    out.append("}")
    out.append("")
    for n in notes: out.append(f"# NOTE: {n}")

    cfg = "\n".join(out)
    with open(f"{d}/pdn_inferred.cfg", "w") as f:
        f.write(cfg)
    print(cfg)
    print(f"\nwrote {d}/pdn_inferred.cfg", file=sys.stderr)

if __name__ == "__main__":
    main()
