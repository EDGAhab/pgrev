#!/usr/bin/env python3
"""Phase 4: infer minimal pdngen::specify_grid config from extracted PG geometry.

Forward model (verified against PdnGen.tcl @ f12e2f47):
- rails: one per row boundary, width from config; net assignment from row orient
  (rails_start_with is NEVER read -> dead parameter, omitted).
- straps: VDD/base grid at ref + offset + k*pitch; other net at
  ref + offset + shift + k*pitch, shift = pitch/2 (no spacing) or
  spacing + width. ref = (stdcell_xMin, stdcell_yMin - max_rail_width/2).
- dropout (rev4): stripes whose lower edge protrudes >= 2 dbu past the grid
  area edge are removed by pdngen's core-boundary blockage trim
  (cut_blocked_areas: blockage outside core minus stdcell_plus_area, then
  shrink/bloat trims shapes narrower than the wire width). Kept iff
  center - width/2 >= area_edge - 1, i.e. in offset terms offset < width/2
  drops the leading base stripe(s). Both layers follow the same rule; the
  met5 area edge already sits railw/2 below core_y1, so railw enters only via
  the reference point, not as an additive threshold term (rev4 bisection:
  kept at o == w/2, dropped below; rev3-ws2 §11.1's "railw/2 + w/2" text was
  wrong, its own 11430/11440 dbu numbers support w/2).
- top bound: stripe k placed while center < area_far - width (tcl loop bound).
- connect: via spans collapse into chains; each chain -> {bottom top}.

Inference (rev4): the naive least-squares fit runs first and its output is kept
verbatim on success. If it raises (e.g. MIXED starts_with from a dropped leading
stripe, or bad-spacing from the same cause), each strap layer is re-inferred by
searching (base_net, dropped_count k) hypotheses and keeping those whose
dropout-inclusive forward model reproduces the observed stripe geometry
(counts and centers within 2 dbu). Cross-layer starts_with is then resolved
from the surviving hypotheses.

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

class DropoutFailed(Exception):
    """No dropout-aware hypothesis reproduces the observed geometry."""

# ---------------------------------------------------------------------------
# rev4: dropout-inclusive forward model (all integer dbu)
# ---------------------------------------------------------------------------
def fwd_stripe_centers(ref, near, far, o, p, w, shift):
    """Predict per-net stripe centers with pdngen placement + dropout.

    ref: stripe origin (grid area near edge); near/far: area edges along the
    stripe-normal axis; o/p/w: offset/pitch/width; shift: other-net grid shift
    (pitch/2 default or spacing+width). Returns (base_centers, other_centers).
    """
    base, other = [], []
    for lst, ph in ((base, 0), (other, shift)):
        j = 0
        while True:
            c = ref + o + ph + j * p
            if c >= far - w:      # tcl loop bound: x < area_far - width
                break
            if 2 * c - w >= 2 * near - 2:  # blockage trim keeps d <= 1 dbu
                lst.append(c)
            j += 1
            assert j < 100000, "runaway stripe loop"
    return base, other

def fwd_validates(ref, near, far, o, p, w, shift, obs_base, obs_other):
    """True iff the forward model reproduces observed centers (2 dbu)."""
    pb, po = fwd_stripe_centers(ref, near, far, o, p, w, shift)
    if len(pb) != len(obs_base) or len(po) != len(obs_other):
        return False
    return (all(abs(a - b) <= TOL_DBU for a, b in zip(pb, obs_base)) and
            all(abs(a - b) <= TOL_DBU for a, b in zip(po, obs_other)))

def infer_layer_dropout(lay, obs, width, ref, near, far, power, ground):
    """Dropout-aware per-layer inference.

    obs: {net: sorted [centers]} (integer dbu). Searches (base_net, k) with
    k = number of dropped leading base-grid stripes; validates each candidate
    with the dropout-inclusive forward model. Returns (hyps, pitch, width)
    with hyps ordered smallest-k first per base net, or None when pitch is
    unidentifiable (single surviving stripe per net). Raises DropoutFailed.
    """
    nets = sorted(obs)
    assert len(nets) >= 1
    # integer centers: observed boxes are integer dbu; LS arithmetic below
    # needs ints for exact comparison with the tcl forward model
    obs = {n: [int(round(c)) for c in cs] for n, cs in obs.items()}
    pitches = {}
    for n in nets:
        cs = obs[n]
        if len(cs) > 1:
            p_est, _c0_est, resid = ls_fit(cs)
            assert resid <= TOL_DBU, (
                f"non-uniform pitch {lay} {n}: LS pitch {p_est:.1f} dbu, "
                f"max residual {resid:.1f} dbu > {TOL_DBU} dbu")
            pitches[n] = int(round(p_est))
    pitch_vals = [pitches[n] for n in nets if n in pitches]
    if not pitch_vals:
        return None  # single stripe per net -> pitch NOT identifiable
    pitch = Counter(pitch_vals).most_common(1)[0][0]
    by_first = sorted(nets, key=lambda n: obs[n][0])
    hyps = []
    for base in by_first:
        others = [n for n in nets if n != base]
        other = others[0] if others else None
        if other is None:
            shift, spacing = 0, None
        else:
            shift = (obs[other][0] - obs[base][0]) % pitch
            # Default-vs-explicit spacing must be decided EXACTLY (integer dbu).
            # The tcl default is integer pitch//2; an observed shift equal to
            # that is indistinguishable from explicit spacing+width == pitch//2,
            # and emitting the default reproduces it exactly.  A tolerance here
            # (e.g. |shift - p/2| <= 2) would collapse a genuine explicit shift
            # like 7469 (vs pitch//2 = 7468) into the default and silently move
            # every other-net stripe by 1 dbu (half-integer truncation).
            if shift == pitch // 2:
                spacing = None  # default half-pitch shift, no spacing key
            else:
                spacing = shift - width
                if spacing <= 0:
                    continue  # not expressible with positive spacing
        kmax = (obs[base][0] - ref + TOL_DBU) // pitch
        for k in range(max(kmax, -1) + 1):
            o_cand = obs[base][0] - k * pitch - ref
            if o_cand < -TOL_DBU:
                continue
            if fwd_validates(ref, near, far, o_cand, pitch, width, shift,
                             obs[base], obs[other] if other else []):
                hyps.append({"k": k, "base": base, "o": o_cand,
                             "spacing": spacing, "shift": shift})
                # NOTE: no `break` here on purpose. A larger k with o-k*p can
                # also validate and be geometrically identical to a smaller k
                # (the (k,o) ≡ (k+1,o-p) wrap duality when o-p in [0,w/2)).
                # Keeping all lets the global enumeration count the genuine
                # ambiguity instead of silently collapsing it.
    if not hyps:
        raise DropoutFailed(
            f"{lay}: no (base_net, dropped_k) hypothesis reproduces "
            f"the observed stripe geometry")
    return hyps, pitch, width

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
    # grid area edges (dropout reference); area = stdcell_plus_area
    area = {"near_x": core[0], "far_x": core[2],
            "near_y": core[1] - max_rail_w / 2,
            "far_y": core[3] + max_rail_w / 2}

    # ---- straps ----
    straps = [s for s in wires if s["shape"] == "STRIPE"]
    def layer_dir(lay): return next(s["dir"] for s in straps if s["layer"] == lay)
    def layer_min(lay):
        return min(s["cx"] if layer_dir(lay) == "V" else s["cy"]
                   for s in straps if s["layer"] == lay)
    strap_layers = sorted(set(s["layer"] for s in straps),
                          key=lambda l: (0 if layer_dir(l) == "V" else 1, layer_min(l)))
    # per-layer observations shared by both inference paths
    layer_obs = {}
    layer_width = {}
    for lay in strap_layers:
        by_net = defaultdict(list)
        for s in straps:
            if s["layer"] == lay:
                c = s["cx"] if s["dir"] == "V" else s["cy"]
                by_net[s["net"]].append(c)
        obs = {n: sorted(cs) for n, cs in by_net.items()}
        layer_obs[lay] = obs
        layer_width[lay] = Counter(
            s["width"] for s in straps if s["layer"] == lay).most_common(1)[0][0]

    def layer_ref(lay):
        # integer dbu: rail widths are even dbu in practice; int() keeps the
        # dropout arithmetic exact (matches tcl integer comparisons)
        if layer_dir(lay) == "V":
            return (int(ref_x), int(area["near_x"]), int(area["far_x"]))
        return (int(round(ref_y)), int(round(area["near_y"])),
                int(round(area["far_y"])))

    def infer_layer_naive(lay):
        """Original (rev2) per-layer inference, verbatim.

        Returns (spec_params, sw): spec_params = dict(width/pitch/offset_dbu/
        spacing_dbu|None), sw = "POWER"/"GROUND". Returns None when pitch is
        unidentifiable. Raises AssertionError on inconsistency.
        """
        obs = layer_obs[lay]
        nets = sorted(obs)
        assert len(nets) >= 1
        width = layer_width[lay]
        pitches, firsts = {}, {}
        for n in nets:
            cs = obs[n]
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
            return None
        base_net = min(nets, key=lambda n: firsts[n])
        other_net = [n for n in nets if n != base_net]
        base_is_power = base_net in power
        sw = "POWER" if base_is_power else "GROUND"
        r = ref_x if layer_dir(lay) == "V" else ref_y
        c0 = firsts[base_net]
        offset_dbu = c0 - r
        assert offset_dbu >= -TOL_DBU, f"negative offset {lay}"
        spacing_dbu = None
        if other_net:
            o = other_net[0]
            shift = firsts[o] - firsts[base_net]
            if abs(shift - pitch / 2) <= TOL_DBU:
                pass  # default half-pitch shift, no spacing key
            else:
                spacing_dbu = shift - width
                assert spacing_dbu > 0, f"bad spacing {lay}"
                notes.append(f"{lay}: {o} shifted by spacing+width ({um(spacing_dbu, dbu_per_um):.3f}um), not pitch/2")
            # verify other net's grid matches
            for n in other_net:
                assert abs((firsts[n] - firsts[base_net]) - shift) <= TOL_DBU
                if n in pitches: assert abs(pitches[n] - pitch) <= TOL_DBU
        return ({"width": width, "pitch": pitch, "offset_dbu": offset_dbu,
                 "spacing_dbu": spacing_dbu}, sw)

    strap_block = []
    starts_with = None
    naive_err = None
    try:
        for lay in strap_layers:
            r = infer_layer_naive(lay)
            if r is None:
                continue
            params, sw = r
            starts_with = sw if starts_with in (None, sw) else "MIXED!"
            spec = f"{lay} {{width {um(params['width'], dbu_per_um):.3f} pitch {um(params['pitch'], dbu_per_um):.3f} offset {um(params['offset_dbu'], dbu_per_um):.3f}"
            if params["spacing_dbu"] is not None:
                spec += f" spacing {um(params['spacing_dbu'], dbu_per_um):.3f}"
            spec += "}"
            strap_block.append("        " + spec)
        assert starts_with not in (None, "MIXED!"), "inconsistent starts_with across layers"
    except AssertionError as e:
        naive_err = e
    except DropoutFailed as e:  # not raised by naive path; defensive
        naive_err = e

    if naive_err is not None:
        # ---- rev4 dropout-aware correction: re-infer every strap layer ----
        notes.append(f"naive inference failed ({naive_err}); "
                     f"dropout-aware correction engaged")
        strap_block = []
        layer_hyps = {}
        for lay in strap_layers:
            ref, near, far = layer_ref(lay)
            try:
                r = infer_layer_dropout(lay, layer_obs[lay], layer_width[lay],
                                        ref, near, far, power, ground)
            except (AssertionError, DropoutFailed) as e:
                print(f"DROPOUT_CORRECTION_FAILED {lay}: {e}", file=sys.stderr)
                sys.exit(1)
            if r is None:
                notes.append(f"{lay}: single strap per net -> pitch NOT identifiable")
                continue
            hyps, pitch, width = r
            layer_hyps[lay] = (hyps, pitch)
        if not layer_hyps:
            print("UNIDENTIFIABLE: no strap layer yielded a pitch",
                  file=sys.stderr)
            sys.exit(1)
        def hyp_sw(h):
            if h["base"] in power: return "POWER"
            if h["base"] in ground: return "GROUND"
            return None
        # global starts_with: prefer values already pinned by unambiguous
        # layers, then POWER, then GROUND (deterministic)
        order = []
        for lay, (hyps, _pitch) in layer_hyps.items():
            sws = {hyp_sw(h) for h in hyps} - {None}
            if len(sws) == 1:
                s = next(iter(sws))
                if s not in order: order.append(s)
        for s in ("POWER", "GROUND"):
            if s not in order: order.append(s)
        # enumerate ALL globally-consistent (starts_with, per-layer choice)
        # combos: more than one means a genuine geometric ambiguity (the
        # chosen config reproduces the geometry exactly but the parameters
        # are not uniquely identifiable)
        all_combos = []
        for gsw in ("POWER", "GROUND"):
            def rec(lays, acc, gsw=gsw):
                if not lays:
                    all_combos.append((gsw, dict(acc)))
                    return
                lay = lays[0]
                hyps, _pitch = layer_hyps[lay]
                for h in hyps:
                    if hyp_sw(h) in (gsw, None):
                        acc[lay] = h
                        rec(lays[1:], acc)
                        del acc[lay]
            rec([l for l in strap_layers if l in layer_hyps], {})
        if not all_combos:
            print("DROPOUT_CORRECTION_FAILED: no consistent starts_with",
                  file=sys.stderr)
            sys.exit(1)
        # deterministic pick: pinned-by-unambiguous first, then POWER
        def combo_rank(c):
            return order.index(c[0]) if c[0] in order else 99
        all_combos.sort(key=combo_rank)
        starts_with, choice = all_combos[0]
        if len(all_combos) > 1:
            notes.append(
                f"AMBIGUOUS: {len(all_combos)} globally-consistent hypotheses "
                f"reproduce the observed geometry exactly; selected "
                f"starts_with={starts_with} (deterministic tie-break). "
                f"Parameters beyond geometry are not uniquely identifiable.")
        for lay in strap_layers:
            if lay not in choice:
                continue
            h = choice[lay]
            _hyps, pitch = layer_hyps[lay]
            width = layer_width[lay]
            spec = f"{lay} {{width {um(width, dbu_per_um):.3f} pitch {um(pitch, dbu_per_um):.3f} offset {um(h['o'], dbu_per_um):.3f}"
            if h["spacing"] is not None:
                spec += f" spacing {um(h['spacing'], dbu_per_um):.3f}"
            spec += "}"
            strap_block.append("        " + spec)
            notes.append(
                f"{lay}: dropout-aware correction (naive: {naive_err}); "
                f"base net {h['base']}, {h['k']} leading stripe(s) dropped, "
                f"forward model reproduces observed geometry within {TOL_DBU} dbu")
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
