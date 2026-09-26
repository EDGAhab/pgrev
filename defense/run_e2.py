#!/usr/bin/env python3
"""E2: jittered-pitch sensitivity curve on sky130hd/gcd met4.

j in {0, 2%, 5%, 10%, 15%} of pitch x 3 seeds (j=0: 1 run).
Each met4 stripe (+ its via stack, incl. met4-met5 via x-coords) shifted by
delta ~ Uniform(-j, +j). Attacker: naive pg_infer (expect crash for j>0) +
robust LS pitch estimator -> error-vs-jitter curve.
Defender: connectivity, min spacing vs LEF, mesh delta vs baseline.
"""
import json, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib
from robust_pitch import robust_estimate

DEF = os.path.expanduser("~/pgrev/defense")
ROOT = os.path.join(DEF, "E2")
BASE = os.path.join(DEF, "baseline", "data", "sky130hd_gcd")
TAG = "sky130hd_gcd"
os.makedirs(ROOT, exist_ok=True)

base_shapes = lib.load_shapes(os.path.join(BASE, "pg_shapes.csv"))
P4 = 27140  # dbu, verified
base_mesh = lib.build_mesh(base_shapes)
base_worst = base_mesh["worst_drop_V"]
print(f"baseline worst drop: {base_worst*1000:.2f} mV/A", flush=True)

def stripes_of(shapes, layer):
    return [s for s in shapes if s["kind"] == "wire" and s["shape"] == "STRIPE"
            and s["layer"] == layer]

def jitter(shapes, frac, seed):
    rng = random.Random(1000 + int(frac * 10000) + seed)
    j = frac * P4
    m4 = stripes_of(shapes, "met4")
    # via boxes are 1600 dbu; keep stripe centers (hence via stacks) fully
    # supported by rails/met5 stripes (x in [10120, 269560])
    lo, hi = 10120 + 800, 269560 - 800
    delta_of, redraws = {}, 0
    for s in m4:
        for _ in range(1000):
            d = int(round(rng.uniform(-j, j)))
            if lo <= s["cx"] + d <= hi:
                break
            redraws += 1
        delta_of[id(s)] = d
    out = []
    for r in shapes:
        nr = dict(r)
        if r["kind"] == "wire" and r["shape"] == "STRIPE" and r["layer"] == "met4":
            d = delta_of[id(r)]
            nr["x1"] += d; nr["x2"] += d; nr["cx"] += d
        elif r["kind"] == "via":
            b, t = r["layer"].split("-", 1)
            if b in ("met1", "met2", "met3") or r["layer"] == "met4-met5":
                # via stack belongs to nearest met4 stripe; move with it
                st = min(m4, key=lambda s: abs(s["cx"] - r["cx"]))
                d = delta_of[id(st)]
                nr["x1"] += d; nr["x2"] += d; nr["cx"] += d
        out.append(nr)
    min_sp = lib.min_stripe_spacing_um(out, "met4")
    return out, delta_of, min_sp, redraws

results = {"levels": []}
BASE_META = os.path.join(BASE, "design_meta.json")
BASE_DEF = os.path.join(BASE, "floorplan.def")
for frac in (0.0, 0.02, 0.05, 0.10, 0.15):
    seeds = (0,) if frac == 0.0 else (1, 2, 3)
    for seed in seeds:
        tag = f"e2_j{int(frac*100)}_s{seed}_{TAG}"
        mshapes, deltas, min_sp, redraws = jitter(base_shapes, frac, seed)
        resamples = 0
        while min_sp is not None and min_sp < lib.MIN_SPACING_UM["met4"] - 1e-9:
            resamples += 1
            seed += 100
            mshapes, deltas, min_sp, redraws = jitter(base_shapes, frac, seed)
            tag = f"e2_j{int(frac*100)}_s{seed}_{TAG}"
        lib.setup_tag(ROOT, tag, mshapes, BASE_META, BASE_DEF)
        r = lib.run_infer(ROOT, tag)
        robust = robust_estimate(mshapes, base_shapes, "met4")
        conn, dang = lib.connectivity(mshapes)
        mesh = lib.build_mesh(mshapes)
        wv = mesh.get("worst_drop_V")
        entry = {
            "jitter_frac": frac, "seed": seed, "resamples": resamples,
            "stripe_redraws": redraws,
            "min_spacing_met4_um": min_sp,
            "attacker_naive": {"exit": r["exit"], "err_tail": r["err_tail"]},
            "attacker_robust_met4": robust,
            "defender": {
                "connectivity": conn, "dangling": dang,
                "mesh_solvable": mesh["solvable"],
                "mesh_worst_drop_V": wv,
                "mesh_worst_delta_pct_vs_base":
                    (100 * (wv - base_worst) / base_worst
                     if (mesh["solvable"] and wv is not None) else None),
            },
        }
        results["levels"].append(entry)
        re_ = robust["VDD"]["pitch_rel_err"]
        print(f"j={frac*100:4.0f}% s={seed}: naive_exit={r['exit']} "
              f"robust_pitch_relerr={re_:.4f} min_sp={min_sp:.2f}um "
              f"meshΔ={entry['defender']['mesh_worst_delta_pct_vs_base']}", flush=True)

json.dump(results, open(os.path.join(ROOT, "defense_E2_results.json"), "w"), indent=1)
print("E2 done.", flush=True)
