#!/usr/bin/env python3
"""rev5 任务 C：E1 意图歧义深挖（回应审稿人"前向模型完备性检验"）。

检验 1 — 候选子集完备性：对 subset_attack.py 找出的每个候选子集
(VDD k=9 x3, VDD k=10 x1, VSS k=9 x2)，用 pdngen strap 前向模型
（src/pg_infer.py::fwd_stripe_centers 的 per-net 循环语义，忠实复刻
PdnGen.tcl@f12e2f47 generate_upper_metal_mesh_stripes + leading-dropout
trim；grid area 取可见的 stdcell area）做参数拟合：是否存在一组
(offset, pitch, width) 使前向输出精确等于该子集几何。
verdict: LEGAL（存在）/ ILLEGAL（不存在）。

检验 2 — via 不对称性：对 e1a met4 x met5 同网交叉点，按
(true/decoy met4) x (true/decoy met5) 四类统计 via 存在率。

纯 Python（stdlib），不跑 OpenROAD；前向复刻已用真值网格验证。
"""
import itertools, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.expanduser("~/pgrev/src"))
import lib
from pg_infer import fwd_stripe_centers  # faithful forward replica (rev4)

REPO = os.path.expanduser("~/pgrev")
E1A = os.path.join(REPO, "defense", "E1", "data", "e1a_sky130hd_gcd", "pg_shapes.csv")
BASE = os.path.join(REPO, "defense", "baseline", "data", "sky130hd_gcd", "pg_shapes.csv")
TOL = 2  # dbu, same as subset_attack.py

e1a = lib.load_shapes(E1A)
base = lib.load_shapes(BASE)

# met4 grid area (visible stdcell area, x axis)
REF4, NEAR4, FAR4 = 10120, 10120, 269560
W4 = 1600

def centers(shapes, layer, net):
    cs, _ = lib.stripe_centers(shapes, layer, net)
    return cs

def is_ap(sub):
    diffs = [b - a for a, b in zip(sub, sub[1:])]
    return max(abs(d - diffs[0]) for d in diffs) <= TOL

def fwd_base_only(o, p, w):
    """Per-net forward stripe centers (base grid only)."""
    b, _ = fwd_stripe_centers(REF4, NEAR4, FAR4, o, p, w, shift=p // 2)
    return b

# ---------------- 检验 1 ----------------
print("=" * 70)
print("CHECK 1: candidate-subset completeness (forward-model fit, met4)")
print("=" * 70)

# sanity: forward replica reproduces the TRUE grids exactly
for net in ("VDD", "VSS"):
    true_cs = centers(base, "met4", net)
    o_true = true_cs[0] - REF4
    p_true = round((true_cs[-1] - true_cs[0]) / (len(true_cs) - 1))
    fwd = fwd_base_only(o_true, p_true, W4)
    assert fwd == true_cs, f"forward replica mismatch on true {net} grid!"
    print(f"[sanity] forward(true params) == true met4/{net} grid "
          f"({len(true_cs)} stripes, o={o_true}, p={p_true})  OK")

true4 = {net: centers(base, "met4", net) for net in ("VDD", "VSS")}

def label_subset(net, sub):
    t = true4[net]
    if list(sub) == t:
        return "true grid (ground truth)"
    if set(sub) <= set(t):
        missing = sorted(set(t) - set(sub))
        dropped = [t.index(m) for m in missing]
        return f"truncated true-grid subset (dropped true idx {dropped})"
    # decoy grid? all members are non-true centers forming full decoy set
    e = centers(e1a, "met4", net)
    decoys = sorted(set(e) - set(t))
    if list(sub) == decoys:
        return "decoy grid (full)"
    return "OTHER (unexpected)"

def fit_params(sub):
    """Try offset hypotheses; return (verdict, detail)."""
    k = len(sub)
    p = round((sub[-1] - sub[0]) / (k - 1))
    if abs((sub[-1] - sub[0]) - p * (k - 1)) > TOL:
        return "ILLEGAL", "not an exact AP; no pitch fits"
    # pitch must match the layer pitch measured on true grid
    p_true = round((true4["VDD"][-1] - true4["VDD"][0]) / (len(true4["VDD"]) - 1))
    if abs(p - p_true) > TOL:
        return "ILLEGAL", f"pitch {p} != layer pitch {p_true}"
    o0 = sub[0] - REF4
    hits = []
    # hypotheses: o0 + m*p for m in {-1, 0, +1} (leading-dropout can hide
    # an earlier stripe only if it falls in the trim zone)
    for m in (-1, 0, 1):
        o = o0 + m * p
        if o < -100000:
            continue
        fwd = fwd_base_only(o, p, W4)
        if fwd == list(sub):
            hits.append((o, m))
    if hits:
        return "LEGAL", "reproduced by offset=%s (m=%s)" % (
            ", ".join(str(o) for o, _ in hits), ",".join(str(m) for _, m in hits))
    return "ILLEGAL", (f"no offset reproduces exactly "
                       f"(direct o={o0} gives {len(fwd_base_only(o0, p, W4))} stripes)")

results1 = []
specs = [("VDD", 9), ("VDD", 10), ("VSS", 9)]
n_total = 0
for net, k in specs:
    cs = centers(e1a, "met4", net)
    cands = []
    for idxs in itertools.combinations(range(len(cs)), k):
        sub = [cs[i] for i in idxs]
        if is_ap(sub):
            cands.append(sub)
    print(f"\n{net} k={k}: {len(cands)} AP candidates")
    for sub in cands:
        n_total += 1
        label = label_subset(net, sub)
        verdict, detail = fit_params(sub)
        results1.append({"net": net, "k": k, "n_stripes": len(sub),
                         "label": label, "verdict": verdict, "detail": detail})
        print(f"  [{verdict:7s}] {label}\n          fit: {detail}")

n_legal = sum(1 for r in results1 if r["verdict"] == "LEGAL")
n_illegal = n_total - n_legal
print(f"\nCHECK 1 summary: {n_total} candidates -> {n_legal} LEGAL, "
      f"{n_illegal} ILLEGAL (ambiguity {n_total} -> {n_legal})")

# ---- 检验 1b：双网配对一致性（设计层面） ----
# 真实 config 用 starts_with=POWER 生成 VDD/VSS 两网（VSS = VDD + P/2）。
# 对每对 (VDD-cand, VSS-cand)（仅 LEGAL 的），检验是否存在 (o, shift=P/2)
# 使前向 base 网 == VDD-cand 且 other 网 == VSS-cand 精确成立。
print()
print("-" * 70)
print("CHECK 1b: two-net pairing consistency (design level)")
print("-" * 70)
P2 = 13570  # VSS phase = P/2
legal = [r for r in results1 if r["verdict"] == "LEGAL"]
# recover actual center lists
def get_sub(net, label):
    cs = centers(e1a, "met4", net)
    t = true4[net]
    if label.startswith("true grid"):
        return t
    if label.startswith("decoy"):
        return sorted(set(cs) - set(t))
    # truncated: find which true idx dropped
    dropped = int(label.split("[")[1].rstrip("])"))
    return [c for i, c in enumerate(t) if i != dropped]

def fwd_other(o, p, w, shift):
    _, other = fwd_stripe_centers(REF4, NEAR4, FAR4, o, p, w, shift)
    return other

pair_ok = []
for rv in [r for r in legal if r["net"] == "VDD"]:
    D = get_sub("VDD", rv["label"])
    o = D[0] - REF4
    p = 27140
    for rs in [r for r in legal if r["net"] == "VSS"]:
        S = get_sub("VSS", rs["label"])
        # design-level criterion: the other-net forward loop (same o, shift=P/2)
        # emits exactly S. This encodes phase alignment AND the top loop bound
        # (a 10-stripe VDD grid legitimately pairs with a 9-stripe VSS grid:
        # c_9+P/2 exceeds far-width and is never emitted).
        cnt_ok = (fwd_other(o, p, W4, P2) == S)
        phase1_ok = (S[0] == D[0] + P2)  # first-stripe phase alignment
        ok = cnt_ok and phase1_ok
        pair_ok.append((rv["label"], rs["label"], ok))
        print(f"  [{'OK ' if ok else 'xx '}] VDD:{rv['label'][:34]:34s} x "
              f"VSS:{rs['label'][:30]:30s} fwd-other==S:{cnt_ok} phase1:{phase1_ok}")
n_pair_ok = sum(1 for _, _, ok in pair_ok if ok)
print(f"CHECK 1b summary: {n_pair_ok} consistent full-design hypotheses")

# ---------------- 检验 2 ----------------
print()
print("=" * 70)
print("CHECK 2: via asymmetry at met4 x met5 crossings (e1a, same-net)")
print("=" * 70)

def stripe_rects(shapes, layer, net):
    return [s for s in shapes if s["kind"] == "wire" and s["shape"] == "STRIPE"
            and s["layer"] == layer and s["net"] == net]

def classify(layer, net):
    """Return dict center -> 'true'/'decoy' for e1a stripes."""
    ec = centers(e1a, layer, net)
    tc = set(centers(base, layer, net))
    cls = {}
    for c in ec:
        if any(abs(c - t) <= TOL for t in tc):
            cls[c] = "true"
        else:
            cls[c] = "decoy"
    return cls

vias = [v for v in e1a if v["kind"] == "via" and v["layer"] == "met4-met5"]
via_pts = [(v["cx"], v["cy"], v["net"]) for v in vias]

def has_via(s4, s5, net):
    # via centered (within TOL) on the crossing of stripe centers
    return any(n == net and abs(x - s4["cx"]) <= TOL and abs(y - s5["cy"]) <= TOL
               for x, y, n in via_pts)

# baseline reference: true x true via rate in the UN-decoyed design
base_vias = [(v["cx"], v["cy"], v["net"]) for v in base
             if v["kind"] == "via" and v["layer"] == "met4-met5"]
def base_has_via(s4, s5, net):
    return any(n == net and abs(x - s4["cx"]) <= TOL and abs(y - s5["cy"]) <= TOL
               for x, y, n in base_vias)

grand = {}
for net in ("VDD", "VSS"):
    cls4 = classify("met4", net)
    cls5 = classify("met5", net)
    s4s = stripe_rects(e1a, "met4", net)
    s5s = stripe_rects(e1a, "met5", net)
    # sanity: every stripe classified
    assert all(any(abs(s["cx"] - c) <= TOL for c in cls4) for s in s4s)
    stat = {}
    for c4 in ("true", "decoy"):
        for c5 in ("true", "decoy"):
            n_cross = n_via = 0
            for s4 in s4s:
                k4 = cls4[min(cls4, key=lambda c: abs(c - s4["cx"]))]
                if k4 != c4:
                    continue
                for s5 in s5s:
                    k5 = cls5[min(cls5, key=lambda c: abs(c - s5["cy"]))]
                    if k5 != c5:
                        continue
                    # geometric crossing?
                    if not (s4["x1"] < s5["x2"] and s5["x1"] < s4["x2"]
                            and s4["y1"] < s5["y2"] and s5["y1"] < s4["y2"]):
                        continue
                    n_cross += 1
                    if has_via(s4, s5, net):
                        n_via += 1
            stat[(c4, c5)] = (n_cross, n_via)
    # baseline true x true
    b4 = stripe_rects(base, "met4", net)
    b5 = stripe_rects(base, "met5", net)
    bn = bv = 0
    for s4 in b4:
        for s5 in b5:
            bn += 1
            if base_has_via(s4, s5, net):
                bv += 1
    print(f"\nnet {net}: met4 stripes true/decoy = "
          f"{sum(1 for v in cls4.values() if v=='true')}/"
          f"{sum(1 for v in cls4.values() if v=='decoy')}, met5 "
          f"{sum(1 for v in cls5.values() if v=='true')}/"
          f"{sum(1 for v in cls5.values() if v=='decoy')}")
    print(f"  baseline (no decoy) true4 x true5: {bv}/{bn} via'd")
    for key in [("true", "true"), ("true", "decoy"), ("decoy", "true"), ("decoy", "decoy")]:
        n_cross, n_via = stat[key]
        rate = n_via / n_cross if n_cross else float("nan")
        print(f"  {key[0]:5s}4 x {key[1]:5s}5 : {n_via:4d}/{n_cross:4d} = {rate:.4f}")
        g = grand.setdefault(key, [0, 0])
        g[0] += n_cross; g[1] += n_via

print("\npooled over nets:")
sym = True
rates = {}
for key in [("true", "true"), ("true", "decoy"), ("decoy", "true"), ("decoy", "decoy")]:
    n_cross, n_via = grand[key]
    rate = n_via / n_cross if n_cross else float("nan")
    rates[key] = rate
    print(f"  {key[0]:5s}4 x {key[1]:5s}5 : {n_via:4d}/{n_cross:4d} = {rate:.4f}")
r = list(rates.values())
print(f"  max |rate_i - rate_j| = {max(r) - min(r):.4f} "
      f"({'SYMMETRIC' if max(r) - min(r) < 1e-9 else 'ASYMMETRIC'})")

json.dump({"check1": results1,
           "check1_summary": {"n_total": n_total, "n_legal": n_legal,
                              "n_illegal": n_illegal},
           "check1b_pairs": [{"vdd": a, "vss": b, "consistent": ok}
                             for a, b, ok in pair_ok],
           "check1b_n_consistent": n_pair_ok,
           "check2_pooled": {f"{a}4x{b}5": {"cross": grand[(a, b)][0],
                                             "via": grand[(a, b)][1]}
                             for a, b in grand}},
          open(os.path.join(REPO, "defense", "E1", "rev5_expC_results.json"), "w"),
          indent=1)
print("\nwrote defense/E1/rev5_expC_results.json")
