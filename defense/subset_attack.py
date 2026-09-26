#!/usr/bin/env python3
"""Adaptive attacker vs E1a: subset enumeration.

The attacker knows a decoy grid may be interleaved and tries every subset of
stripes of size k, looking for clean arithmetic progressions (uniform pitch
within 2 dbu). Question: is the reconstruction unique?
Run on E1a met4/VDD (19 stripes: 10 true + 9 decoy), k in {9, 10}.
"""
import itertools, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

DEF = os.path.expanduser("~/pgrev/defense")
shapes = lib.load_shapes(os.path.join(DEF, "E1", "data", "e1a_sky130hd_gcd", "pg_shapes.csv"))
TOL = 2

def centers(layer, net):
    cs, _ = lib.stripe_centers(shapes, layer, net)
    return cs

def is_ap(sub):
    diffs = [b - a for a, b in zip(sub, sub[1:])]
    return max(abs(d - diffs[0]) for d in diffs) <= TOL

out = {}
for net in ("VDD", "VSS"):
    cs = centers("met4", net)
    out[net] = {"n_stripes": len(cs)}
    for k in (9, 10):
        if k > len(cs):
            out[net][f"k={k}"] = "n/a (fewer stripes)"
            continue
        valid = 0
        examples = []
        for sub in itertools.combinations(range(len(cs)), k):
            pts = [cs[i] for i in sub]
            if is_ap(pts):
                valid += 1
                if len(examples) < 2:
                    examples.append([round((p - cs[0]) / 1000, 3) for p in pts[:4]])
        out[net][f"k={k}"] = {"n_valid_AP_subsets": valid, "example_first4_um": examples}
        print(f"{net} k={k}: {valid} valid AP subsets", flush=True)

json.dump(out, open(os.path.join(DEF, "E1", "subset_attack.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
