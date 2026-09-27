#!/usr/bin/env python3
"""Phase 7: extract PG geometry from an ODB produced by the CURRENT C++ pdngen.

Same pg_shapes.csv format as the legacy pipeline (net,layer,shape,kind,
x1,y1,x2,y2,width,via_name) so pg_infer_cpp.py can consume it.

Differences vs legacy src/pg_extract.py:
- filters out SHAPE DRCFILL filler shapes (new in C++ pdn; not part of the
  grid spec and would pollute stripe geometry)
- OPENROAD_EXE taken from env (points at the phase7 build)
- no matplotlib plot (headless-safe minimal)

Usage:
  python3 extract_cpp.py --odb <file.odb> --def <floorplan.def> \
      --outdir phase7/data/<tag> --tag <tag>
"""
import argparse, csv, json, os, re, subprocess, sys
from collections import Counter

REPO = os.path.expanduser("~/pgrev")
DUMP_TCL = f"{REPO}/src/dump_pg.tcl"
EXCLUDE_SHAPES = {"DRCFILL"}

def run_dump(odb, raw_csv):
    env = dict(os.environ)
    env["ODB_IN"] = odb
    env["CSV_OUT"] = raw_csv
    openroad = os.environ.get("OPENROAD_EXE", os.path.expanduser("~/pgrev/tools/eda/bin/openroad"))
    r = subprocess.run([openroad, "-exit", DUMP_TCL],
                       capture_output=True, text=True, env=env, timeout=900)
    if not os.path.exists(raw_csv):
        print(r.stdout[-2000:]); print(r.stderr[-2000:], file=sys.stderr)
        raise RuntimeError("dump_pg.tcl produced no csv")

def parse_def_meta(def_path):
    meta = {"dbu": None, "die": None, "rows": [], "macros": []}
    with open(def_path) as f:
        for line in f:
            s = line.strip()
            m = re.match(r"UNITS DISTANCE MICRONS (\d+)", s)
            if m: meta["dbu"] = int(m.group(1))
            m = re.match(r"DIEAREA \(\s*(-?\d+)\s+(-?\d+)\s*\)\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)", s)
            if m: meta["die"] = [int(x) for x in m.groups()]
            m = re.match(r"ROW (\S+) (\S+) (-?\d+) (-?\d+) (\S+) DO (\d+) BY (\d+) STEP (-?\d+) (-?\d+)", s)
            if m:
                meta["rows"].append({"name": m.group(1), "site": m.group(2),
                    "x": int(m.group(3)), "y": int(m.group(4)), "orient": m.group(5),
                    "nx": int(m.group(6)), "ny": int(m.group(7)),
                    "stepx": int(m.group(8)), "stepy": int(m.group(9))})
    if meta["rows"]:
        xs = [r["x"] for r in meta["rows"]]
        xe = [r["x"] + r["nx"] * r["stepx"] for r in meta["rows"]]
        ys = sorted(set(r["y"] for r in meta["rows"]))
        diffs = [b - a for a, b in zip(ys, ys[1:]) if b > a]
        rh = max(set(diffs), key=diffs.count) if diffs else None
        ye = [r["y"] + (rh or 0) for r in meta["rows"]]
        meta["core"] = [min(xs), min(ys), max(xe), max(ye)]
        meta["row_height"] = rh
    comp = False
    with open(def_path) as f:
        for line in f:
            s = line.strip()
            if s.startswith("COMPONENTS"): comp = True; continue
            if s.startswith("END COMPONENTS"): break
            if comp and "FIXED" in s:
                m = re.match(r"-\s+(\S+)\s+(\S+).*?FIXED \(\s*(-?\d+)\s+(-?\d+)\s*\) (\S+)", s)
                if m and not re.search(r"tap|fill|decap", m.group(2), re.I):
                    meta["macros"].append({"inst": m.group(1), "cell": m.group(2),
                        "x": int(m.group(3)), "y": int(m.group(4)), "orient": m.group(5)})
    return meta

def query_db_core_area(odb):
    """Best-effort: read dbBlock core area (the C++ pdngen stripe origin)."""
    openroad = os.environ.get("OPENROAD_EXE", os.path.expanduser("~/pgrev/tools/eda/bin/openroad"))
    tcl = r'''
read_db $::env(ODB_IN)
set block [ord::get_db_block]
if {![catch {set ca [$block getCoreArea]}]} {
    if {![catch {puts "DBCOREAREA [$ca xMin] [$ca yMin] [$ca xMax] [$ca yMax]"}]} {}
}
'''
    env = dict(os.environ); env["ODB_IN"] = odb
    r = subprocess.run([openroad, "-exit", "-no_init"], input=tcl,
                       capture_output=True, text=True, env=env, timeout=300)
    m = re.search(r"DBCOREAREA (-?\d+) (-?\d+) (-?\d+) (-?\d+)", r.stdout)
    return [int(x) for x in m.groups()] if m else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--odb", required=True); ap.add_argument("--def", required=True)
    ap.add_argument("--outdir", required=True); ap.add_argument("--tag", required=True)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    raw_csv = os.path.join(a.outdir, "pg_raw.csv")
    if not os.path.exists(raw_csv):
        run_dump(a.odb, raw_csv)

    rows = list(csv.DictReader(open(raw_csv)))
    shapes = []
    n_excluded = 0
    for r in rows:
        if r["shape"] in EXCLUDE_SHAPES or r["via_name"].startswith("DRCFILL"):
            n_excluded += 1
            continue
        x1, y1, x2, y2 = int(r["x1"]), int(r["y1"]), int(r["x2"]), int(r["y2"])
        if r["via_name"]:
            shapes.append({"net": r["net"], "layer": f"{r['via_bot']}-{r['via_top']}",
                           "shape": r["shape"], "kind": "via",
                           "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                           "width": x2 - x1, "via_name": r["via_name"]})
        else:
            w = min(x2 - x1, y2 - y1)
            shapes.append({"net": r["net"], "layer": r["layer"], "shape": r["shape"],
                           "kind": "wire", "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                           "width": w, "via_name": ""})
    with open(os.path.join(a.outdir, "pg_shapes.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["net", "layer", "shape", "kind",
                                          "x1", "y1", "x2", "y2", "width", "via_name"])
        w.writeheader(); w.writerows(shapes)

    meta = parse_def_meta(getattr(a, "def"))
    meta["n_shapes"] = len(shapes)
    meta["n_excluded_drcfill"] = n_excluded
    meta["db_core_area"] = query_db_core_area(a.odb)
    if meta["db_core_area"] and meta.get("core"):
        d = [abs(x - y) for x, y in zip(meta["db_core_area"], meta["core"])]
        meta["db_core_vs_rowcore_dbu"] = d
    meta["counts"] = {f"{k[0]}/{k[1]}/{k[2]}/{k[3]}": v for k, v in
                      Counter((s["net"], s["layer"], s["shape"], s["kind"]) for s in shapes).items()}
    with open(os.path.join(a.outdir, "design_meta.json"), "w") as f:
        json.dump(meta, f, indent=1)

    wires = [s for s in shapes if s["kind"] == "wire"]
    print(f"[{a.tag}] wires={len(wires)} vias={len(shapes)-len(wires)} excluded_drcfill={n_excluded}")
    bad = [s for s in wires if not (s["x2"] > s["x1"] and s["y2"] > s["y1"])]
    assert not bad, f"degenerate boxes: {bad[:3]}"
    print("extract OK")

if __name__ == "__main__":
    main()
