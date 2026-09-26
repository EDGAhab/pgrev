#!/usr/bin/env python3
"""E1: interleaved via'd decoy grid (D3) on sky130hd/gcd + D1 controls.

Variants (all at extracted-geometry level = attacker's exact input):
  E1a : D3 decoys at +P/4 on met4+met5, both nets, full via stacks cloned,
        decoy x decoy met4-met5 vias added (faithful to a 2nd pdngen run)
  E1b : P/2 offset variant -- DOCUMENTED INFEASIBLE (decoy lands exactly on
        the other net's stripes -> VDD/VSS short). Not run; infeasibility shown.
  D1b : on-net via-less decoys at +P/4 (weak control); then adaptive
        via-presence filter defeats it.
  D1a : floating (no-net) decoys -- never reach the extractor
        (dump_pg.tcl:7-9 iterates only POWER/GROUND sigType nets); code-level
        control, no runtime effect possible.

Attacker: naive pg_infer_def.py (zero modification).
Adaptive: subset-enumeration on E1a met4/VDD (sizes 9 and 10).
Defender: connectivity, stripe spacing vs LEF, resistive mesh vs baseline.
"""
import json, os, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

DEF = os.path.expanduser("~/pgrev/defense")
ROOT = os.path.join(DEF, "E1")
BASE = os.path.join(DEF, "baseline", "data", "sky130hd_gcd")
TAG = "sky130hd_gcd"
os.makedirs(ROOT, exist_ok=True)

base_shapes = lib.load_shapes(os.path.join(BASE, "pg_shapes.csv"))
meta = json.load(open(os.path.join(BASE, "design_meta.json")))
core = meta["core"]  # [x1, y1, x2, y2]

def layer_pitch(shapes, layer):
    cs, _ = lib.stripe_centers(shapes, layer, "VDD")
    cs2, _ = lib.stripe_centers(shapes, layer, "VSS")
    allc = sorted(cs + cs2)
    diffs = sorted(b - a for a, b in zip(allc, allc[1:]))
    return 2 * diffs[len(diffs) // 2]  # median diff = P/2

P4 = layer_pitch(base_shapes, "met4")   # 27140
P5 = layer_pitch(base_shapes, "met5")   # 27200
print(f"pitch met4={P4} dbu, met5={P5} dbu", flush=True)

def stripes_of(shapes, layer):
    return [s for s in shapes if s["kind"] == "wire" and s["shape"] == "STRIPE"
            and s["layer"] == layer]

def nearest_stripe(stripes, pos, horiz):
    return min(stripes, key=lambda s: abs((s["cy"] if horiz else s["cx"]) - pos))

def build_decoy(shapes, shift_frac, clone_vias=True):
    """Return new shape list with interleaved decoy grid added."""
    out = [dict(r) for r in shapes]
    m4 = stripes_of(shapes, "met4")
    m5 = stripes_of(shapes, "met5")
    s4 = int(round(shift_frac * P4))
    s5 = int(round(shift_frac * P5))
    bound4 = core[2] - 1600   # pdngen loop bound: center < area_max - width
    bound5 = core[3] - 1600
    d4, d5 = [], []  # (orig_stripe, decoy_center)
    for s in m4:
        c = s["cx"] + s4
        if c < bound4:
            d4.append((s, c))
    for s in m5:
        c = s["cy"] + s5
        if c < bound5:
            d5.append((s, c))
    # clone stripe wires
    for s, c in d4:
        r = dict(s)
        w = r["x2"] - r["x1"]
        r["x1"] = int(round(c - w / 2)); r["x2"] = int(round(c + w / 2))
        r["cx"] = c; r["via_name"] = ""
        out.append(r)
    for s, c in d5:
        r = dict(s)
        h = r["y2"] - r["y1"]
        r["y1"] = int(round(c - h / 2)); r["y2"] = int(round(c + h / 2))
        r["cy"] = c; r["via_name"] = ""
        out.append(r)
    if clone_vias:
        # assign original vias to nearest original stripe, clone shifted
        orig_vias = [v for v in shapes if v["kind"] == "via"]
        for v in orig_vias:
            b, t = v["layer"].split("-", 1)
            r = dict(v)
            if t in ("met2", "met3", "met4") and b in ("met1", "met2", "met3"):
                st = nearest_stripe(m4, v["cx"], horiz=False)
                match = next(((s, c) for s, c in d4 if s is st), None)
                if match is None:
                    continue
                dx = int(round(match[1] - st["cx"]))
                r["x1"] += dx; r["x2"] += dx; r["cx"] += dx
                out.append(r)
            elif v["layer"] == "met4-met5":
                st4 = nearest_stripe(m4, v["cx"], horiz=False)
                st5 = nearest_stripe(m5, v["cy"], horiz=True)
                m4d = next(((s, c) for s, c in d4 if s is st4), None)
                m5d = next(((s, c) for s, c in d5 if s is st5), None)
                if m4d is not None:
                    r2 = dict(v)
                    dx = int(round(m4d[1] - st4["cx"]))
                    r2["x1"] += dx; r2["x2"] += dx; r2["cx"] += dx
                    out.append(r2)
                if m5d is not None:
                    r2 = dict(v)
                    dy = int(round(m5d[1] - st5["cy"]))
                    r2["y1"] += dy; r2["y2"] += dy; r2["cy"] += dy
                    out.append(r2)
        # decoy x decoy met4-met5 vias (same net only -- a real 2nd pdngen
        # run vias same-net crossings only)
        for s4o, c4 in d4:
            for s5o, c5 in d5:
                if s4o["net"] != s5o["net"]:
                    continue
                if not (s4o["y1"] <= c5 <= s4o["y2"] and s5o["x1"] <= c4 <= s5o["x2"]):
                    continue
                out.append({"net": s4o["net"], "layer": "met4-met5", "shape": "STRIPE",
                            "kind": "via", "x1": int(c4 - 800), "y1": int(c5 - 800),
                            "x2": int(c4 + 800), "y2": int(c5 + 800), "width": 1600,
                            "via_name": "via4_1600x1600", "cx": c4, "cy": c5})
    return out, (len(d4), len(d5))

def defender_report(shapes):
    conn, dang = lib.connectivity(shapes)
    return {
        "connectivity_components": conn,
        "dangling_vias": dang,
        "min_spacing_met4_um": lib.min_stripe_spacing_um(shapes, "met4"),
        "min_spacing_met5_um": lib.min_stripe_spacing_um(shapes, "met5"),
        "mesh": lib.build_mesh(shapes),
    }

results = {}
results["pitch_dbu"] = {"met4": P4, "met5": P5}
results["note_E1b"] = ("P/2-offset same-net decoys are physically infeasible: a "
    "+P/2 decoy lands exactly on the opposite net's stripe centers "
    "(VSS grid = VDD grid + P/2), i.e. a VDD/VSS short. Not run.")

# ---- E1a: D3 at +P/4 ----
e1a_shapes, (n_d4, n_d5) = build_decoy(base_shapes, 0.25, clone_vias=True)
results["E1a"] = {"decoy_stripes": {"met4": n_d4, "met5": n_d5}}
lib.setup_tag(ROOT, "e1a_" + TAG, e1a_shapes,
              os.path.join(BASE, "design_meta.json"), os.path.join(BASE, "floorplan.def"))
r = lib.run_infer(ROOT, "e1a_" + TAG)
open(os.path.join(ROOT, "e1a_infer_stdout.txt"), "w").write(r["stdout"])
open(os.path.join(ROOT, "e1a_infer_stderr.txt"), "w").write(r["stderr"])
results["E1a"]["attacker_naive"] = {"exit": r["exit"], "params": r["params"],
                                    "err_tail": r["err_tail"]}
drep = defender_report(e1a_shapes)
results["E1a"]["defender"] = {
    "connectivity_components": drep["connectivity_components"],
    "dangling_vias": drep["dangling_vias"],
    "min_spacing_met4_um": drep["min_spacing_met4_um"],
    "min_spacing_met5_um": drep["min_spacing_met5_um"],
    "lef_min_spacing_um": lib.MIN_SPACING_UM,
    "mesh_worst_drop_V": drep["mesh"]["worst_drop_V"] if drep["mesh"]["solvable"] else None,
    "mesh_mean_drop_V": drep["mesh"]["mean_drop_V"] if drep["mesh"]["solvable"] else None,
    "mesh_solvable": drep["mesh"]["solvable"],
}
print("E1a naive infer exit:", r["exit"], "| err:", r["err_tail"][:100], flush=True)
print("E1a defender:", json.dumps(results["E1a"]["defender"], indent=1)[:600], flush=True)

# ---- D1b: on-net via-less decoys at +P/4 ----
d1b_shapes, _ = build_decoy(base_shapes, 0.25, clone_vias=False)
lib.setup_tag(ROOT, "d1b_" + TAG, d1b_shapes,
              os.path.join(BASE, "design_meta.json"), os.path.join(BASE, "floorplan.def"))
r = lib.run_infer(ROOT, "d1b_" + TAG)
results["D1b"] = {"attacker_naive": {"exit": r["exit"], "params": r["params"],
                                     "err_tail": r["err_tail"]}}
print("D1b naive infer exit:", r["exit"], "| err:", r["err_tail"][:100], flush=True)

# adaptive attacker vs D1b: drop STRIPE wires with no via inside their rect
vias = [v for v in d1b_shapes if v["kind"] == "via"]
def has_via(s):
    return any(s["x1"] <= v["cx"] <= s["x2"] and s["y1"] <= v["cy"] <= s["y2"] for v in vias)
filt = [s for s in d1b_shapes
        if not (s["kind"] == "wire" and s["shape"] == "STRIPE" and not has_via(s))]
results["D1b"]["n_stripes_dropped_by_filter"] = (
    sum(1 for s in d1b_shapes if s["kind"] == "wire" and s["shape"] == "STRIPE")
    - sum(1 for s in filt if s["kind"] == "wire" and s["shape"] == "STRIPE"))
lib.setup_tag(ROOT, "d1b_filt_" + TAG, filt,
              os.path.join(BASE, "design_meta.json"), os.path.join(BASE, "floorplan.def"))
r = lib.run_infer(ROOT, "d1b_filt_" + TAG)
results["D1b"]["attacker_adaptive_viafilter"] = {"exit": r["exit"], "params": r["params"],
                                                "err_tail": r["err_tail"]}
print("D1b adaptive(via-filter) exit:", r["exit"], "| params:", r["params"], flush=True)

json.dump(results, open(os.path.join(ROOT, "defense_E1_results.json"), "w"), indent=1)
print("E1 naive/adaptive part done; subset enumeration runs next (separate script).", flush=True)
