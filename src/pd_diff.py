#!/usr/bin/env python3
"""Compare two pg_shapes.csv files (original vs round-trip).
Pass criterion: identical wire boxes (<=1 dbu) and identical via sets."""
import csv, sys
from collections import defaultdict

def load(p):
    rows = list(csv.DictReader(open(p)))
    for r in rows:
        for k in ("x1", "y1", "x2", "y2", "width"): r[k] = int(r[k])
    return rows

def key_wire(r): return (r["net"], r["layer"], r["shape"])
def key_via(r): return (r["net"], r["layer"], r["via_name"], r["x1"], r["y1"], r["x2"], r["y2"])

a, b = sys.argv[1], sys.argv[2]
ra, rb = load(a), load(b)
wa = [r for r in ra if r["kind"] == "wire"]; wb = [r for r in rb if r["kind"] == "wire"]
va = [r for r in ra if r["kind"] == "via"];  vb = [r for r in rb if r["kind"] == "via"]
ok = True
# wire multiset comparison per key
def boxkey(r): return (r["x1"], r["y1"], r["x2"], r["y2"])
from collections import Counter
ca = Counter((key_wire(r), boxkey(r)) for r in wa)
cb = Counter((key_wire(r), boxkey(r)) for r in wb)
# allow 1 dbu slack: quantize
def q(v): return round(v / 2) * 2
qa = Counter((key_wire(r), q(r["x1"]), q(r["y1"]), q(r["x2"]), q(r["y2"])) for r in wa)
qb = Counter((key_wire(r), q(r["x1"]), q(r["y1"]), q(r["x2"]), q(r["y2"])) for r in wb)
only_a = qa - qb; only_b = qb - qa
print(f"wires: orig={len(wa)} rt={len(wb)} | only_in_orig={sum(only_a.values())} only_in_rt={sum(only_b.values())}")
if only_a or only_b:
    ok = False
    for k, v in list(only_a.items())[:5]: print("  ORIG ONLY:", k, v)
    for k, v in list(only_b.items())[:5]: print("  RT ONLY:", k, v)
ka = Counter(key_via(r) for r in va); kb = Counter(key_via(r) for r in vb)
da = ka - kb; db = kb - ka
print(f"vias: orig={len(va)} rt={len(vb)} | only_in_orig={sum(da.values())} only_in_rt={sum(db.values())}")
if da or db:
    ok = False
    for k, v in list(da.items())[:5]: print("  ORIG ONLY:", k, v)
    for k, v in list(db.items())[:5]: print("  RT ONLY:", k, v)
print("ROUNDTRIP", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
