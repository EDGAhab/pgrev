#!/usr/bin/env python3
"""Robust attacker for E2: least-squares pitch/offset recovery under jitter.

Method: sort stripe centers per (layer, net); least-squares fit
c_i = c0 + i * p (indices assumed consecutive -- valid while jitter < P/2).
Reports estimated pitch/offset and errors vs truth taken from the
un-jittered CSV.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

def ls_fit(cs):
    n = len(cs)
    sx = sum(range(n)); sxx = sum(i * i for i in range(n))
    sy = sum(cs); sxy = sum(i * c for i, c in enumerate(cs))
    den = n * sxx - sx * sx
    p = (n * sxy - sx * sy) / den
    c0 = (sy - p * sx) / n
    resid = max(abs(c - (c0 + i * p)) for i, c in enumerate(cs))
    return p, c0, resid

def truth_params(orig_shapes, layer):
    out = {}
    for net in ("VDD", "VSS"):
        cs, _ = lib.stripe_centers(orig_shapes, layer, net)
        diffs = sorted(b - a for a, b in zip(cs, cs[1:]))
        p = diffs[len(diffs) // 2]
        out[net] = {"pitch_dbu": p, "c0_dbu": cs[0], "n": len(cs)}
    return out

def robust_estimate(mod_shapes, orig_shapes, layer):
    truth = truth_params(orig_shapes, layer)
    rep = {}
    for net in ("VDD", "VSS"):
        cs, _ = lib.stripe_centers(mod_shapes, layer, net)
        p_est, c0_est, resid = ls_fit(cs)
        t = truth[net]
        rep[net] = {
            "n": len(cs),
            "pitch_est_um": p_est / 1000,
            "pitch_rel_err": abs(p_est - t["pitch_dbu"]) / t["pitch_dbu"],
            "offset_err_um": abs(c0_est - t["c0_dbu"]) / 1000,
            "max_resid_dbu": resid,
        }
    return rep

if __name__ == "__main__":
    # usage: robust_pitch.py <orig_csv> <mod_csv> <layer>
    orig = lib.load_shapes(sys.argv[1])
    mod = lib.load_shapes(sys.argv[2])
    print(json.dumps(robust_estimate(mod, orig, sys.argv[3]), indent=1))
