#!/usr/bin/env python3
"""E3: via-dropout targeting connect inference on sky130hd/gcd.

  E3a: delete p% of rail->strap via STACKS (spans met1-met2/met2-met3/met3-met4
       grouped by (x,y)), p in {10, 30, 50} (seed 42). Span TYPES remain ->
       connect inference expected UNCHANGED (type-level collapse).
  E3b: delete ALL met2-met3 vias (full span-type removal) -> chain breaks,
       connect mis-recovered; PDN itself disconnects (stripes float off rails).

Attacker: naive pg_infer (connect line). Defender: connectivity, mesh curve.
E3b roundtrip consequence computed analytically (no pdngen re-run): the
mis-inferred connect {{met4 met5}} re-run through pdngen yields stripes with
zero rail->strap via stacks (same mechanism as phase-5 v_conn).
"""
import json, os, random, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

DEF = os.path.expanduser("~/pgrev/defense")
ROOT = os.path.join(DEF, "E3")
BASE = os.path.join(DEF, "baseline", "data", "sky130hd_gcd")
TAG = "sky130hd_gcd"
os.makedirs(ROOT, exist_ok=True)

base_shapes = lib.load_shapes(os.path.join(BASE, "pg_shapes.csv"))
BASE_META = os.path.join(BASE, "design_meta.json")
BASE_DEF = os.path.join(BASE, "floorplan.def")
base_mesh = lib.build_mesh(base_shapes)
base_worst = base_mesh["worst_drop_V"]

RAIL_STRAP_SPANS = {"met1-met2", "met2-met3", "met3-met4"}

def rail_strap_stacks(shapes):
    stacks = defaultdict(list)
    for v in shapes:
        if v["kind"] == "via" and v["layer"] in RAIL_STRAP_SPANS:
            stacks[(round(v["cx"]), round(v["cy"]))].append(v)
    return stacks

stacks = rail_strap_stacks(base_shapes)
nv = sum(len(v) for v in stacks.values())
print(f"rail->strap stacks: {len(stacks)}, vias: {nv}", flush=True)
assert all(len(v) == 3 for v in stacks.values()), "each stack should be 3 vias"

def defender_report(shapes):
    conn, dang = lib.connectivity(shapes)
    mesh = lib.build_mesh(shapes)
    wv = mesh.get("worst_drop_V")
    return {
        "connectivity": conn, "dangling": dang,
        "mesh_solvable": mesh["solvable"],
        "mesh_worst_drop_V": wv,
        "mesh_worst_delta_pct_vs_base":
            (100 * (wv - base_worst) / base_worst
             if (mesh["solvable"] and wv is not None) else None),
        "disconnected_inject_nodes": mesh["disconnected_inject_nodes"],
    }

results = {"E3a": [], "n_stacks": len(stacks)}
rng = random.Random(42)
stack_keys = sorted(stacks.keys())

for p in (0.10, 0.30, 0.50):
    drop = set(rng.sample(stack_keys, int(round(p * len(stack_keys)))))
    keep_ids = set()
    for k, vs in stacks.items():
        if k not in drop:
            keep_ids.update(id(v) for v in vs)
    mshapes = [r for r in base_shapes
               if not (r["kind"] == "via" and r["layer"] in RAIL_STRAP_SPANS
                       and id(r) not in keep_ids)]
    n_via_del = sum(1 for r in base_shapes if r["kind"] == "via") - \
                sum(1 for r in mshapes if r["kind"] == "via")
    tag = f"e3a_p{int(p*100)}_{TAG}"
    lib.setup_tag(ROOT, tag, mshapes, BASE_META, BASE_DEF)
    r = lib.run_infer(ROOT, tag)
    drep = defender_report(mshapes)
    results["E3a"].append({
        "p": p, "n_stacks_dropped": len(drop), "n_vias_deleted": n_via_del,
        "attacker": {"exit": r["exit"], "connect": r["params"].get("connect"),
                     "err_tail": r["err_tail"]},
        "defender": drep,
    })
    print(f"E3a p={p*100:.0f}%: dropped {len(drop)} stacks / {n_via_del} vias | "
          f"infer exit={r['exit']} connect={r['params'].get('connect')} | "
          f"conn={drep['connectivity']} meshΔ={drep['mesh_worst_delta_pct_vs_base']}",
          flush=True)

# ---- E3b: full met2-met3 span removal ----
mshapes_b = [r for r in base_shapes
             if not (r["kind"] == "via" and r["layer"] == "met2-met3")]
n_via_del_b = sum(1 for r in base_shapes if r["kind"] == "via") - \
              sum(1 for r in mshapes_b if r["kind"] == "via")
tag = f"e3b_nomet2met3_{TAG}"
lib.setup_tag(ROOT, tag, mshapes_b, BASE_META, BASE_DEF)
r = lib.run_infer(ROOT, tag)
drep = defender_report(mshapes_b)
# analytic roundtrip projection: mis-inferred connect re-run => zero rail-strap vias
n_rail_strap_vias_orig = sum(1 for v in base_shapes
                             if v["kind"] == "via" and v["layer"] in RAIL_STRAP_SPANS)
results["E3b"] = {
    "n_vias_deleted": n_via_del_b,
    "attacker": {"exit": r["exit"], "connect": r["params"].get("connect"),
                 "err_tail": r["err_tail"]},
    "defender": drep,
    "roundtrip_projection": (
        "mis-inferred connect {{met4 met5}} re-run through pdngen yields "
        f"stripes with ZERO rail->strap via stacks ({n_rail_strap_vias_orig} vias "
        "missing vs truth geometry); strap->strap (met4-met5) vias retained. "
        "Analytic projection (same via-placement mechanism as phase-5 v_conn); "
        "no pdngen re-run performed."),
}
print(f"E3b: deleted {n_via_del_b} met2-met3 vias | infer exit={r['exit']} "
      f"connect={r['params'].get('connect')} | conn={drep['connectivity']} "
      f"mesh_solvable={drep['mesh_solvable']}", flush=True)

json.dump(results, open(os.path.join(ROOT, "defense_E3_results.json"), "w"), indent=1)
print("E3 done.", flush=True)
