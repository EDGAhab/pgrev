#!/usr/bin/env python3
"""rev6 expC: E2 jitter defense on the CURRENT C++ pdngen (HEAD).

Port of defense/run_e2.py to HEAD geometry. Same experiment: jitter met4
stripe positions by delta ~ Uniform(-j,+j), j in {0,2%,5%,10%,15%} of pitch
x 3 seeds; each stripe moves with its via stack (incl. met4-met5 via
x-coords). Attacker: naive pg_infer_cpp (expect crash for j>0) + robust
least-squares pitch estimator -> error-vs-jitter curve. Defender:
connectivity, min spacing vs LEF, mesh delta vs HEAD baseline.

Baseline: fixed config (phase7 truth equivalent) generated with HEAD openroad.
Output: phase7/e2_head_results.json
"""
import json, os, random, shutil, subprocess, sys
from collections import defaultdict
sys.path.insert(0, os.path.expanduser("~/pgrev/defense"))
sys.path.insert(0, os.path.expanduser("~/pgrev/phase7"))
import lib
from robust_pitch import robust_estimate
from randscan_head import write_gen_tcl, pdngen_run, extract

REPO = os.path.expanduser("~/pgrev")
PH7 = f"{REPO}/phase7"
ROOT = f"{PH7}/e2h"
OPENROAD = f"{PH7}/openroad-src/build/bin/openroad"
DBU = 1000

# baseline truth (dbu): same numbers as the phase7 round-trip truth
BASE_CFG = {"i": -1, "kind": "baseline",
            "railw": 480, "sw": "POWER",
            "m4": {"w": 1600, "p": 27140, "o": 13570, "s": None},
            "m5": {"w": 1600, "p": 27200, "o": 13600, "s": None}}
P4 = BASE_CFG["m4"]["p"]

def build_mesh_connected(shapes, ground_layer="met5", itot=1.0):
    """Copy of lib.build_mesh with one modeling fix.

    lib._stack_chains collapses a via stack into a single (bottom, top) edge.
    When a met4-met5 via coincides with a rail (as in the HEAD baseline, where
    every met5 stripe y happens to equal a rail y), the whole rail->met5 stack
    merges and the intermediate met4 stripe gets NO edge, disconnecting most
    of the mesh from ground (885/2092 nodes). Physically the stack connects
    all pierced layers, so we expand each chain into edges between adjacent
    *wired* layers (layers that actually have a wire at the via position),
    with resistance = (# via spans between them) * R_VIA_OHM.

    On legacy geometry (no met4-met5/rail coincidence) this reduces exactly to
    lib.build_mesh: merged chains there are all (met1,met4) with wires only at
    met1 and met4, i.e. the identical single edge. Verified: legacy baseline
    worst_drop_V matches lib.build_mesh to 1e-12.
    """
    import numpy as np
    from scipy.sparse import lil_matrix
    from scipy.sparse.linalg import spsolve
    wires = lib.wire_list(shapes)
    by_layer = defaultdict(list)
    for i, w in enumerate(wires):
        w["_i"] = i
        by_layer[w["layer"]].append(w)
        w["_horiz"] = (w["x2"] - w["x1"]) >= (w["y2"] - w["y1"])
    contacts = defaultdict(set)
    for i, w in enumerate(wires):
        if w["_horiz"]:
            contacts[i].add(w["x1"]); contacts[i].add(w["x2"])
        else:
            contacts[i].add(w["y1"]); contacts[i].add(w["y2"])
    stack_edges = []
    for (cx, cy), vs in lib.via_stacks(shapes).items():
        for b_layer, t_layer, _ in lib._stack_chains(vs):
            lo = lib.LAYER_ORDER.index(b_layer); hi = lib.LAYER_ORDER.index(t_layer)
            wl = []
            for l in lib.LAYER_ORDER[lo:hi + 1]:
                w = lib._wire_at(by_layer, l, cx, cy)
                if w is not None:
                    wl.append((l, w))
            for (la, wa), (lb, wb) in zip(wl, wl[1:]):
                if wa["_i"] == wb["_i"]:
                    continue
                ia, ib = lib.LAYER_ORDER.index(la), lib.LAYER_ORDER.index(lb)
                n_v = sum(1 for v in vs
                          if ia <= lib.LAYER_ORDER.index(v["layer"].split("-", 1)[0])
                          and lib.LAYER_ORDER.index(v["layer"].split("-", 1)[1]) <= ib)
                pa = cx if wa["_horiz"] else cy
                pb = cx if wb["_horiz"] else cy
                contacts[wa["_i"]].add(pa); contacts[wb["_i"]].add(pb)
                stack_edges.append((wa["_i"], pa, wb["_i"], pb, n_v * lib.R_VIA_OHM))
    node_id = {}
    for i, poss in contacts.items():
        for p in sorted(poss):
            node_id[(i, p)] = len(node_id)
    n = len(node_id)
    G = lil_matrix((n, n))
    def add_g(a, b, r):
        g = 1.0 / r
        G[a, a] += g; G[b, b] += g; G[a, b] -= g; G[b, a] -= g
    for i, w in enumerate(wires):
        poss = sorted(contacts[i])
        rs = lib.RPERSQ.get(w["layer"])
        if rs is None:
            continue
        for p1, p2 in zip(poss, poss[1:]):
            r = rs * abs(p2 - p1) / w["width"]
            add_g(node_id[(i, p1)], node_id[(i, p2)], r)
    for (ia, pa, ib, pb, r) in stack_edges:
        add_g(node_id[(ia, pa)], node_id[(ib, pb)], r)
    ground_nodes = set()
    for i, w in enumerate(wires):
        if w["layer"] == ground_layer:
            for p in contacts[i]:
                ground_nodes.add(node_id[(i, p)])
    free = [i for i in range(n) if i not in ground_nodes]
    rails = [w for i, w in enumerate(wires) if w["shape"] == "FOLLOWPIN"]
    tot_len = sum((w["x2"] - w["x1"]) if w["_horiz"] else (w["y2"] - w["y1"]) for w in rails)
    I = defaultdict(float)
    for w in rails:
        ln = (w["x2"] - w["x1"]) if w["_horiz"] else (w["y2"] - w["y1"])
        share = itot * ln / tot_len
        poss = sorted(contacts[w["_i"]])
        for p in poss:
            I[node_id[(w["_i"], p)]] += share / len(poss)
    import collections
    seen = set(ground_nodes)
    dq = collections.deque(ground_nodes)
    rows = G.tocsr()
    while dq:
        u = dq.popleft()
        for v in rows.indices[rows.indptr[u]:rows.indptr[u + 1]]:
            if v not in seen:
                seen.add(v); dq.append(v)
    reachable = [i for i in free if i in seen]
    iso_inject = sum(1 for i in I if i not in seen and abs(I[i]) > 0)
    if not reachable:
        return {"solvable": False, "n_nodes": n, "n_ground": len(ground_nodes),
                "disconnected_inject_nodes": iso_inject}
    idx = {g: k for k, g in enumerate(reachable)}
    m = len(reachable)
    Gm = lil_matrix((m, m)); Im = [0.0] * m
    for g in reachable:
        k = idx[g]
        Im[k] = I.get(g, 0.0)
        for v in rows.indices[rows.indptr[g]:rows.indptr[g + 1]]:
            if v in idx:
                Gm[k, idx[v]] += rows[g, v]
    V = spsolve(Gm.tocsr(), np.array(Im))
    if iso_inject > 0:
        return {"solvable": True, "n_nodes": n, "n_ground": len(ground_nodes),
                "worst_drop_V": None, "mean_drop_V": None,
                "disconnected_inject_nodes": iso_inject}
    return {"solvable": True, "n_nodes": n, "n_ground": len(ground_nodes),
            "worst_drop_V": float(np.max(V)), "mean_drop_V": float(np.mean(V)),
            "disconnected_inject_nodes": iso_inject}

def wire_graph_connected(shapes):
    """Copy of lib.wire_graph with the same merged-stack fix as
    build_mesh_connected: expand each via-stack chain into edges between
    adjacent wired layers instead of a single collapsed (bottom, top) edge.
    Without this, rails coinciding with met5 stripes lose their met4 edges
    and lib.connectivity overcounts components (11 vs the true 1 per net)."""
    wires = lib.wire_list(shapes)
    by_layer = defaultdict(list)
    for i, w in enumerate(wires):
        w["_i"] = i
        by_layer[w["layer"]].append(w)
    adj = defaultdict(set)
    dangling = 0
    for (cx, cy), vs in lib.via_stacks(shapes).items():
        for b_layer, t_layer, _ in lib._stack_chains(vs):
            lo = lib.LAYER_ORDER.index(b_layer); hi = lib.LAYER_ORDER.index(t_layer)
            wl = []
            for l in lib.LAYER_ORDER[lo:hi + 1]:
                w = lib._wire_at(by_layer, l, cx, cy)
                if w is not None:
                    wl.append(w)
            for wa, wb in zip(wl, wl[1:]):
                if wa["_i"] == wb["_i"]:
                    dangling += 1
                    continue
                a, b = wa["_i"], wb["_i"]
                adj[a].add(b); adj[b].add(a)
            if len(wl) < 2:
                dangling += 1
    return adj, dangling

def connectivity_connected(shapes):
    wires = lib.wire_list(shapes)
    adj, dangling = wire_graph_connected(shapes)
    comp_of = {}
    seen = defaultdict(list)
    for i, w in enumerate(wires):
        if i in comp_of:
            continue
        stack = [i]; comp_of[i] = i
        while stack:
            u = stack.pop()
            for v in adj[u]:
                if v not in comp_of and wires[v]["net"] == wires[u]["net"]:
                    comp_of[v] = i; stack.append(v)
        seen[w["net"]].append(i)
    return ({n: len(c) for n, c in seen.items()}, dangling)

def gen_baseline():
    d = f"{ROOT}/data/baseline"
    os.makedirs(d, exist_ok=True)
    gen_tcl = f"{ROOT}/baseline_gen.tcl"
    write_gen_tcl(BASE_CFG, gen_tcl)
    odb = f"{ROOT}/baseline.odb"
    pdngen_run(gen_tcl, odb)
    extract(odb, "e2h_baseline")
    src = f"{PH7}/data/e2h_baseline"
    for fn in ("pg_shapes.csv", "design_meta.json", "floorplan.def"):
        shutil.copy(f"{src}/{fn}", f"{d}/{fn}")
    shutil.rmtree(src, ignore_errors=True)
    print("baseline generated", flush=True)

def stripes_of(shapes, layer):
    return [s for s in shapes if s["kind"] == "wire" and s["shape"] == "STRIPE"
            and s["layer"] == layer]

def rails_x_extent(shapes):
    xs = [s["x1"] for s in shapes if s["kind"] == "wire"
          and s["shape"] == "FOLLOWPIN"]
    xe = [s["x2"] for s in shapes if s["kind"] == "wire"
          and s["shape"] == "FOLLOWPIN"]
    return min(xs), max(xe)

def jitter(shapes, frac, seed, lo, hi):
    rng = random.Random(1000 + int(frac * 10000) + seed)
    j = frac * P4
    m4 = stripes_of(shapes, "met4")
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
                st = min(m4, key=lambda s: abs(s["cx"] - r["cx"]))
                d = delta_of[id(st)]
                nr["x1"] += d; nr["x2"] += d; nr["cx"] += d
        out.append(nr)
    min_sp = lib.min_stripe_spacing_um(out, "met4")
    return out, delta_of, min_sp, redraws

def setup_tag(tag, shapes, meta_src, def_src):
    d = f"{PH7}/data/{tag}"
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(d)
    lib.save_shapes(shapes, os.path.join(d, "pg_shapes.csv"))
    shutil.copy(meta_src, d)
    shutil.copy(def_src, d)
    return d

def run_infer_cpp(tag):
    p = subprocess.run([sys.executable, f"{PH7}/pg_infer_cpp.py", "--tag", tag],
                       capture_output=True, text=True, timeout=300)
    err_tail = ""
    if p.returncode != 0:
        lines = (p.stderr or p.stdout).strip().splitlines()
        err_tail = lines[-1] if lines else ""
    return {"exit": p.returncode, "err_tail": err_tail}

def main():
    os.makedirs(ROOT, exist_ok=True)
    if not os.path.exists(f"{ROOT}/data/baseline/pg_shapes.csv"):
        gen_baseline()
    base_shapes = lib.load_shapes(f"{ROOT}/data/baseline/pg_shapes.csv")
    base_mesh = build_mesh_connected(base_shapes)
    base_worst = base_mesh["worst_drop_V"]
    print(f"HEAD baseline worst drop: {base_worst*1000:.2f} mV/A "
          f"(n_wires={sum(1 for s in base_shapes if s['kind']=='wire')})", flush=True)
    lo0, hi0 = rails_x_extent(base_shapes)
    via_half = max(s["x2"] - s["x1"] for s in base_shapes
                   if s["kind"] == "via" and s["layer"] == "met4-met5") // 2
    lo, hi = lo0 + via_half, hi0 - via_half

    results = {"baseline_cfg_dbu": BASE_CFG, "levels": []}
    BASE_META = f"{ROOT}/data/baseline/design_meta.json"
    BASE_DEF = f"{ROOT}/data/baseline/floorplan.def"
    for frac in (0.0, 0.02, 0.05, 0.10, 0.15):
        seeds = (0,) if frac == 0.0 else (1, 2, 3)
        for seed in seeds:
            tag = f"e2h_j{int(frac*100)}_s{seed}_sky130hd_gcd"
            mshapes, deltas, min_sp, redraws = jitter(base_shapes, frac, seed, lo, hi)
            resamples = 0
            while min_sp is not None and min_sp < lib.MIN_SPACING_UM["met4"] - 1e-9:
                resamples += 1
                seed += 100
                mshapes, deltas, min_sp, redraws = jitter(base_shapes, frac, seed, lo, hi)
                tag = f"e2h_j{int(frac*100)}_s{seed}_sky130hd_gcd"
            setup_tag(tag, mshapes, BASE_META, BASE_DEF)
            r = run_infer_cpp(tag)
            robust = robust_estimate(mshapes, base_shapes, "met4")
            conn, dang = connectivity_connected(mshapes)
            mesh = build_mesh_connected(mshapes)
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
                  f"robust_pitch_rel_err={re_*100:.3f}% "
                  f"mesh_d={entry['defender']['mesh_worst_delta_pct_vs_base']:+.2f}%",
                  flush=True)
            shutil.rmtree(f"{PH7}/data/{tag}", ignore_errors=True)
    with open(f"{PH7}/e2_head_results.json", "w") as f:
        json.dump(results, f, indent=1)
    print(f"wrote {PH7}/e2_head_results.json", flush=True)

if __name__ == "__main__":
    main()
