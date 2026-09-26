#!/usr/bin/env python3
"""Phase 3: extract PG geometry from odb (via OpenROAD Tcl dump) + DEF meta.

Deviation from manual: the 2022 OpenROAD write_def emits stripe wires as
single via-points (width 0), losing wire rectangles. So instead of parsing
DEF SPECIALNETS, we dump exact wire/via boxes via the Tcl API
(src/dump_pg.tcl) -- the manual's own suggested fallback (it names the
Python odb API; this conda build only has the Tcl API).

Usage:
  python3 src/pg_extract.py --odb <2_floorplan.odb> --def <floorplan.def> \\
      --outdir data/<tag> --tag <tag>

Outputs in outdir: pg_shapes.csv, design_meta.json
Report figure: reports/phase-3_<tag>.png
"""
import argparse, csv, json, os, re, subprocess, sys
from collections import Counter

REPO = os.path.expanduser("~/pgrev")

def run_dump(odb, raw_csv):
    env = dict(os.environ)
    env["ODB_IN"] = odb
    env["CSV_OUT"] = raw_csv
    openroad = os.path.expanduser("~/pgrev/tools/eda/bin/openroad")
    r = subprocess.run([openroad, "-exit", f"{REPO}/src/dump_pg.tcl"],
                       capture_output=True, text=True, env=env, timeout=600)
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
    # core bounds + row height from ROWs
    if meta["rows"]:
        xs = [r["x"] for r in meta["rows"]]
        xe = [r["x"] + r["nx"] * r["stepx"] for r in meta["rows"]]
        ys = sorted(set(r["y"] for r in meta["rows"]))
        diffs = [b - a for a, b in zip(ys, ys[1:]) if b > a]
        rh = max(set(diffs), key=diffs.count) if diffs else None
        ye = [r["y"] + (rh or 0) for r in meta["rows"]]
        meta["core"] = [min(xs), min(ys), max(xe), max(ye)]
        meta["row_height"] = rh
    # macros: COMPONENTS with FIXED, excluding tap/fill/decap filler cells
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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--odb", required=True); ap.add_argument("--def", required=True)
    ap.add_argument("--outdir", required=True); ap.add_argument("--tag", required=True)
    ap.add_argument("--lef", default=None, help="tech LEF for direction check")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    raw_csv = os.path.join(a.outdir, "pg_raw.csv")
    if not os.path.exists(raw_csv):
        run_dump(a.odb, raw_csv)

    rows = list(csv.DictReader(open(raw_csv)))
    shapes = []
    for r in rows:
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
    meta["counts"] = {f"{k[0]}/{k[1]}/{k[2]}/{k[3]}": v for k, v in
                      Counter((s["net"], s["layer"], s["shape"], s["kind"]) for s in shapes).items()}
    with open(os.path.join(a.outdir, "design_meta.json"), "w") as f:
        json.dump(meta, f, indent=1)

    # ---- self checks ----
    wires = [s for s in shapes if s["kind"] == "wire"]
    print(f"[{a.tag}] wires={len(wires)} vias={len(shapes)-len(wires)}")
    bad = [s for s in wires if not (s["x2"] > s["x1"] and s["y2"] > s["y1"])]
    assert not bad, f"degenerate boxes: {bad[:3]}"
    # direction from long axis; every wire must be H or V (never diagonal)
    for s in wires:
        s["dir"] = "H" if (s["x2"] - s["x1"]) >= (s["y2"] - s["y1"]) else "V"
    print("check2 (axis-aligned H/V wires): OK")
    # direction vs LEF preferred direction (warn only)
    if a.lef and os.path.exists(a.lef):
        pref = {}
        cur = None
        with open(a.lef, errors="replace") as f:
            for line in f:
                m = re.match(r"\s*LAYER (\S+)", line)
                if m: cur = m.group(1)
                m = re.match(r"\s*DIRECTION (HORIZONTAL|VERTICAL)", line)
                if m and cur: pref[cur] = "H" if m.group(1) == "HORIZONTAL" else "V"
        mism = 0
        for s in wires:
            if s["shape"] == "FOLLOWPIN":
                continue  # rails run along rows by definition, not LEF preferred dir
            d = s["dir"]
            if s["layer"] in pref and pref[s["layer"]] != d:
                mism += 1
        print(f"check3 (LEF direction): {mism} mismatches (0 expected)")
    # ---- plot ----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    layers = sorted(set(s["layer"] for s in wires))
    cmap = plt.cm.get_cmap("tab10", max(len(layers), 1))
    l2c = {l: cmap(i) for i, l in enumerate(layers)}
    fig, ax = plt.subplots(figsize=(8, 8))
    for s in wires:
        ax.add_patch(Rectangle((s["x1"], s["y1"]), s["x2"] - s["x1"], s["y2"] - s["y1"],
                               facecolor=l2c[s["layer"]], edgecolor="none", alpha=0.7))
    for l, c in l2c.items():
        ax.plot([], [], color=c, label=l, linewidth=6)
    ax.set_aspect("equal"); ax.legend(fontsize=8, loc="upper right")
    ax.set_title(f"PG wires: {a.tag} ({len(wires)} wires, vias omitted)")
    fig.tight_layout()
    png = f"{REPO}/reports/phase-3_{a.tag}.png"
    fig.savefig(png, dpi=90)
    print("plot:", png)

if __name__ == "__main__":
    main()
