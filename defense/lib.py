#!/usr/bin/env python3
"""Shared helpers for defense experiments E1-E3 (Phase 6).

All geometry manipulation is at the extracted-geometry level
(pg_shapes.csv), which is exactly the attacker's input to pg_infer.py.
Defender-side checks: connectivity graph, same-layer stripe spacing vs LEF,
lumped resistive mesh (comparative IR metric, NOT a signoff).
"""
import csv, json, math, os, re, subprocess, sys
from collections import defaultdict

DEF = os.path.expanduser("~/pgrev/defense")
INFER = os.path.join(DEF, "pg_infer_def.py")
PY = "/usr/bin/python3"

# sky130hd tech LEF values (verified by grep of sky130_fd_sc_hd.tlef)
RPERSQ = {"met1": 0.125, "met4": 0.047, "met5": 0.0285}  # ohm/square
MIN_SPACING_UM = {"met4": 0.3, "met5": 1.6}  # from SPACINGTABLE
LAYER_ORDER = ["met1", "met2", "met3", "met4", "met5"]
R_VIA_OHM = 5.0  # nominal per-via resistance (assumption; results are comparative)
DBU_PER_UM = 1000

INT_COLS = ("x1", "y1", "x2", "y2", "width")

def load_shapes(path):
    rows = list(csv.DictReader(open(path)))
    for r in rows:
        for k in INT_COLS:
            r[k] = int(r[k])
        r["cx"] = (r["x1"] + r["x2"]) / 2
        r["cy"] = (r["y1"] + r["y2"]) / 2
    return rows

def save_shapes(rows, path):
    cols = ["net", "layer", "shape", "kind", "x1", "y1", "x2", "y2", "width", "via_name"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in cols})

def stripe_centers(shapes, layer, net):
    """Sorted centers along the stripe axis for (layer, net) STRIPE wires."""
    cs = []
    axis = None
    for s in shapes:
        if s["kind"] == "wire" and s["shape"] == "STRIPE" and s["layer"] == layer and s["net"] == net:
            horiz = (s["x2"] - s["x1"]) >= (s["y2"] - s["y1"])
            axis = "x" if not horiz else "y"
            cs.append(s["cx"] if not horiz else s["cy"])
    return sorted(cs), axis

def wire_list(shapes):
    return [s for s in shapes if s["kind"] == "wire"]

def via_list(shapes):
    return [s for s in shapes if s["kind"] == "via"]

# ----------------------------------------------------------------------------
# inference runner
# ----------------------------------------------------------------------------
def run_infer(root, tag, timeout=300):
    """Run pg_infer_def.py with PGREV_ROOT=root on data/<tag>. Returns dict."""
    env = dict(os.environ, PGREV_ROOT=root)
    p = subprocess.run([PY, INFER, "--tag", tag], capture_output=True, text=True,
                       timeout=timeout, env=env)
    out = p.stdout + p.stderr
    params = {}
    m = re.search(r"met4 \{width ([\d.]+) pitch ([\d.]+) offset ([\d.]+)( spacing ([\d.]+))?\}", p.stdout)
    if m:
        params["met4"] = {"width": float(m.group(1)), "pitch": float(m.group(2)),
                          "offset": float(m.group(3)),
                          "spacing": float(m.group(5)) if m.group(5) else None}
    m = re.search(r"met5 \{width ([\d.]+) pitch ([\d.]+) offset ([\d.]+)( spacing ([\d.]+))?\}", p.stdout)
    if m:
        params["met5"] = {"width": float(m.group(1)), "pitch": float(m.group(2)),
                          "offset": float(m.group(3)),
                          "spacing": float(m.group(5)) if m.group(5) else None}
    m = re.search(r"connect \{(.*)\}", p.stdout)
    if m:
        params["connect"] = m.group(1).strip()
    m = re.search(r'stripes_start_with "(\w+)"', p.stdout)
    if m:
        params["starts_with"] = m.group(1)
    # crash mode: last line of traceback
    err_tail = ""
    if p.returncode != 0:
        lines = (p.stderr or p.stdout).strip().splitlines()
        err_tail = lines[-1] if lines else ""
    return {"exit": p.returncode, "params": params, "err_tail": err_tail,
            "stdout": p.stdout, "stderr": p.stderr}

def setup_tag(root, tag, shapes, meta_src, def_src):
    """Create root/data/<tag>/ with given shapes + copied meta/def."""
    import shutil
    d = os.path.join(root, "data", tag)
    os.makedirs(d, exist_ok=True)
    save_shapes(shapes, os.path.join(d, "pg_shapes.csv"))
    for src in (meta_src, def_src):
        shutil.copy(src, d)
    return d

# ----------------------------------------------------------------------------
# connectivity (wire-level graph, via edges) -- analog of PSM-0040
# ----------------------------------------------------------------------------
def via_stacks(shapes):
    """Group via rows by rounded center -> stacks (dict)."""
    stacks = defaultdict(list)
    for v in via_list(shapes):
        stacks[(round(v["cx"]), round(v["cy"]))].append(v)
    return stacks

def _wire_at(shapes_by_layer, layer, cx, cy, tol=2):
    for w in shapes_by_layer.get(layer, []):
        if w["x1"] - tol <= cx <= w["x2"] + tol and w["y1"] - tol <= cy <= w["y2"] + tol:
            return w
    return None

def _stack_chains(vs):
    """Maximal contiguous span chains within a via stack.

    Returns list of (bottom_layer, top_layer, n_vias). A chain is contiguous
    iff spans link bottom->top with no missing intermediate span. Only a
    contiguous chain can carry current between existing wires (intermediate
    layers may have no wire to terminate on).
    """
    spans = set()
    for v in vs:
        b, t = v["layer"].split("-", 1)
        spans.add((b, t))
    order = [l for l in LAYER_ORDER if any(l in s for s in spans)]
    idx = {l: i for i, l in enumerate(LAYER_ORDER)}
    # adjacency: bottom -> top
    nxt = {}
    for b, t in spans:
        nxt.setdefault(b, t)
    chains = []
    # start layers: bottoms that are not a top of another span
    tops = set(t for _, t in spans)
    for b, t in spans:
        if b not in tops:
            cur, n = b, 0
            while cur in nxt:
                n += sum(1 for v in vs if v["layer"] == f"{cur}-{nxt[cur]}")
                cur = nxt[cur]
            chains.append((b, cur, n))
    return chains

def wire_graph(shapes):
    """Nodes = wire indices; edges = via connections between wires.
    Returns (adj dict, dangling count)."""
    wires = wire_list(shapes)
    by_layer = defaultdict(list)
    for i, w in enumerate(wires):
        w["_i"] = i
        by_layer[w["layer"]].append(w)
    adj = defaultdict(set)
    dangling = 0
    for (cx, cy), vs in via_stacks(shapes).items():
        for b_layer, t_layer, _ in _stack_chains(vs):
            wa = _wire_at(by_layer, b_layer, cx, cy)
            wb = _wire_at(by_layer, t_layer, cx, cy)
            if wa is None or wb is None or wa["_i"] == wb["_i"]:
                dangling += 1
                continue
            a, b = wa["_i"], wb["_i"]
            adj[a].add(b); adj[b].add(a)
    return adj, dangling

def connectivity(shapes):
    """Per-net connected components over wires. Returns {net: n_components}."""
    wires = wire_list(shapes)
    adj, dangling = wire_graph(shapes)
    seen = {}
    comp_of = {}
    for i, w in enumerate(wires):
        if i in comp_of:
            continue
        # BFS limited to same net
        stack = [i]; comp = []
        comp_of[i] = i
        while stack:
            u = stack.pop(); comp.append(u)
            for v in adj[u]:
                if v not in comp_of and wires[v]["net"] == wires[u]["net"]:
                    comp_of[v] = i; stack.append(v)
        seen.setdefault(w["net"], []).append(comp)
    return ({n: len(c) for n, c in seen.items()}, dangling)

# ----------------------------------------------------------------------------
# spacing check (same-layer stripe edge-to-edge)
# ----------------------------------------------------------------------------
def min_stripe_spacing_um(shapes, layer):
    stripes = [s for s in wire_list(shapes)
               if s["shape"] == "STRIPE" and s["layer"] == layer]
    if len(stripes) < 2:
        return None
    horiz = (stripes[0]["x2"] - stripes[0]["x1"]) >= (stripes[0]["y2"] - stripes[0]["y1"])
    key = (lambda s: s["cy"]) if horiz else (lambda s: s["cx"])
    ss = sorted(stripes, key=key)
    best = 1e18
    for a, b in zip(ss, ss[1:]):
        if horiz:
            ea = a["cy"] + a["width"] / 2; eb = b["cy"] - b["width"] / 2
        else:
            ea = a["cx"] + a["width"] / 2; eb = b["cx"] - b["width"] / 2
        best = min(best, eb - ea)
    return best / DBU_PER_UM

# ----------------------------------------------------------------------------
# lumped resistive mesh (comparative IR metric, NOT a signoff)
# Model: ground all top-strap-layer (met5) nodes (ideal feed);
#        inject 1 A total, distributed over rail wires proportional to length,
#        spread evenly over each rail wire's nodes.
#        worst_drop = max node voltage (volts per amp).
# ----------------------------------------------------------------------------
def build_mesh(shapes, ground_layer="met5", itot=1.0):
    import numpy as np
    from scipy.sparse import lil_matrix
    from scipy.sparse.linalg import spsolve
    wires = wire_list(shapes)
    by_layer = defaultdict(list)
    for i, w in enumerate(wires):
        w["_i"] = i
        by_layer[w["layer"]].append(w)
        w["_horiz"] = (w["x2"] - w["x1"]) >= (w["y2"] - w["y1"])

    # contact positions per wire: endpoints + via-stack contact points
    contacts = defaultdict(set)  # wire_i -> set of axis positions
    for i, w in enumerate(wires):
        if w["_horiz"]:
            contacts[i].add(w["x1"]); contacts[i].add(w["x2"])
        else:
            contacts[i].add(w["y1"]); contacts[i].add(w["y2"])

    stack_edges = []  # (wireA, posA, wireB, posB, R)
    for (cx, cy), vs in via_stacks(shapes).items():
        for b_layer, t_layer, n_v in _stack_chains(vs):
            wa = _wire_at(by_layer, b_layer, cx, cy)
            wb = _wire_at(by_layer, t_layer, cx, cy)
            if wa is None or wb is None or wa["_i"] == wb["_i"]:
                continue
            pa = cx if wa["_horiz"] else cy
            pb = cx if wb["_horiz"] else cy
            contacts[wa["_i"]].add(pa); contacts[wb["_i"]].add(pb)
            stack_edges.append((wa["_i"], pa, wb["_i"], pb, n_v * R_VIA_OHM))

    # node index per (wire_i, pos)
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
        rs = RPERSQ.get(w["layer"])
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

    # injection at rail wires, proportional to length
    rails = [w for i, w in enumerate(wires) if w["shape"] == "FOLLOWPIN"]
    tot_len = sum((w["x2"] - w["x1"]) if w["_horiz"] else (w["y2"] - w["y1"]) for w in rails)
    I = defaultdict(float)
    for w in rails:
        ln = (w["x2"] - w["x1"]) if w["_horiz"] else (w["y2"] - w["y1"])
        share = itot * ln / tot_len
        poss = sorted(contacts[w["_i"]])
        for p in poss:
            I[node_id[(w["_i"], p)]] += share / len(poss)

    # restrict to ground-connected free nodes (BFS on conductance graph)
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
    import numpy as np
    V = spsolve(Gm.tocsr(), np.array(Im))
    if iso_inject > 0:
        # part of the load is disconnected from the feed: no meaningful drop
        return {"solvable": True, "n_nodes": n, "n_ground": len(ground_nodes),
                "worst_drop_V": None, "mean_drop_V": None,
                "disconnected_inject_nodes": iso_inject}
    return {"solvable": True, "n_nodes": n, "n_ground": len(ground_nodes),
            "worst_drop_V": float(np.max(V)), "mean_drop_V": float(np.mean(V)),
            "disconnected_inject_nodes": iso_inject}
