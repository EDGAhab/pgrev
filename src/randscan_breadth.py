#!/usr/bin/env python3
"""rev5 task D: breadth scan -- PDK / strap-layer-selection / design-size coverage.

Worker pipeline mirrors rev3 WS2 and rev5 expA (src/randscan.py), but the
config template, layer names, DBU and sampling ranges are parameterized per
design:
  truth cfg -> pdngen -> export DEF + dump PG -> pg_extract -> pg_infer
  (dropout-aware, frozen) -> generic dbu-exact compare vs archived truth
  -> measured round-trip for every inferable config
  -> dual-config equivalence test (small designs only)

Truth JSONs are archived in-repo under reports/rev5-breadth-truth/<design>/
(never /tmp), same schema as rev5 expA (reports/rev5-scan-truth/).

Usage: python3 src/randscan_breadth.py <design> <seed> <n>
  design in {nangate45_gcd, asap7_gcd, sky130hd_aes}
"""
import hashlib, json, os, random, re, shutil, subprocess, sys, time
from concurrent.futures import ProcessPoolExecutor

REPO = os.path.expanduser("~/pgrev")
RS = "/tmp/rsB"   # scratch (separate from /tmp/rs used by expA)
TRUTH_ROOT = f"{REPO}/reports/rev5-breadth-truth"
OPENROAD = os.path.expanduser("~/pgrev/tools/eda/bin/openroad")
FLOWRES = f"{REPO}/tools/OpenROAD-flow-scripts/flow/results"

# min widths validated against the tech LEFs (dbu); rail widths are sampled
# from railw_choices. strap_layers: layer -> (min width dbu, LEF direction).
# Two strap layers are sampled per config under the "legal layer selection"
# constraint: L1 perpendicular to the rail layer(s), L2 perpendicular to L1
# (alternating directions, as in every real PDN grid). A strap layer parallel
# to the rail layer forms no rail->strap vias, making that connect pair a
# dead parameter (verified in the pilot: inferred connect dropped the pair,
# round-trip still bit-exact). connect follows the canonical chain
# rail[0] -> L1 -> L2 (what the inferrer's via-span collapse recovers).
DESIGNS = {
    "nangate45_gcd": dict(
        base_odb=f"{FLOWRES}/nangate45/gcd/base/2_5_floorplan_tapcell.odb",
        sdc=f"{FLOWRES}/nangate45/gcd/base/1_synth.sdc",
        dbu=2000,
        rail_layers=["metal1"],
        strap_layers={"metal2": (140, "V"), "metal3": (140, "H"),
                      "metal4": (280, "V"), "metal5": (280, "H"),
                      "metal6": (280, "V"), "metal7": (800, "H")},
        pitch_range=(8000, 30000), w_cap=6000, step=2,
        railw_choices=[340, 680, 1020, 1360],
        dual=True, tag_prefix="_n45"),
    "asap7_gcd": dict(
        base_odb=f"{FLOWRES}/asap7/gcd/base/2_5_floorplan_tapcell.odb",
        sdc=f"{FLOWRES}/asap7/gcd/base/1_synth.sdc",
        dbu=1000,
        rail_layers=["M1", "M2"],  # dual rail layers (both FOLLOWPIN, horizontal)
        strap_layers={"M3": (18, "V"), "M4": (24, "H"), "M5": (24, "V"),
                      "M6": (32, "H"), "M7": (32, "V")},
        pitch_range=(1200, 3600), w_cap=800, step=2,
        railw_choices=[18, 36, 54, 72],
        dual=True, tag_prefix="_a7"),
    "sky130hd_aes": dict(
        base_odb=f"{FLOWRES}/sky130hd/aes/base/2_5_floorplan_tapcell.odb",
        sdc=f"{FLOWRES}/sky130hd/aes/base/1_synth.sdc",
        dbu=1000,
        rail_layers=["met1"],
        strap_layers={"met4": (400, "V"), "met5": (1600, "H")},
        pitch_range=(8000, 50000), w_cap=3000, step=2,
        railw_choices=[240, 480, 720, 960],
        dual=False, tag_prefix="_aes"),    # dual test skipped: big design
}

CFG_HEAD = """set ::halo 2
set ::rails_start_with "POWER" ;
set ::stripes_start_with "%(sw)s" ;
set ::power_nets "VDD"
set ::ground_nets "VSS"
set pdngen::global_connections {
  VDD {
    {inst_name .* pin_name VPWR}
    {inst_name .* pin_name VPB}
  }
  VSS {
    {inst_name .* pin_name VGND}
    {inst_name .* pin_name VNB}
  }
}
pdngen::specify_grid stdcell {
    name grid
    rails {
%(rails)s
    }
    straps {
%(straps)s
    }
    connect {%(connect)s}
}
"""

def um(d, D): return d / D["dbu"]

def layer_idx(l): return int(re.search(r"\d+", l).group())

def write_cfg(cfg, D, path):
    def sp(v): return "" if v is None else f" spacing {um(v, D):.3f}"
    rails = "\n".join(f"        {l} {{width {um(w, D):.3f}}}"
                      for l, w in cfg["rails"].items())
    straps = "\n".join(
        f"        {l} {{width {um(s['w'], D):.3f} pitch {um(s['p'], D):.3f}"
        f" offset {um(s['o'], D):.3f}{sp(s['s'])}}}"
        for l, s in cfg["straps"].items())
    conn = " ".join(f"{{{b} {t}}}" for b, t in cfg["connect"])
    with open(path, "w") as f:
        f.write(CFG_HEAD % dict(sw=cfg["sw"], rails=rails,
                                straps=straps, connect=conn))

def run(cmd, env_extra=None, timeout=600):
    env = dict(os.environ); env.update(env_extra or {})
    r = subprocess.run(cmd, capture_output=True, text=True, env=env,
                       timeout=timeout)
    return r

def pdngen_run(D, pdn_cfg, out_odb, workdir):
    os.makedirs(workdir, exist_ok=True)
    r = run([OPENROAD, "-exit", f"{RS}/run_pdn.tcl"],
            {"ODB_IN": D["base_odb"], "SDC_IN": D["sdc"],
             "PDN_CFG": pdn_cfg, "ODB_OUT": out_odb})
    if not os.path.exists(out_odb):
        raise RuntimeError(
            f"pdngen produced no odb: {r.stdout[-1500:]}\n{r.stderr[-1500:]}")
    return r

def extract(D, odb, tag):
    d = f"{REPO}/data/{tag}"
    if os.path.exists(d): shutil.rmtree(d)
    os.makedirs(d)
    wd = os.path.dirname(odb)
    def_p = os.path.join(wd, "pdn.def")
    raw_p = os.path.join(wd, "raw.csv")
    run([OPENROAD, "-exit", f"{REPO}/src/export_def.tcl"],
        {"ODB_IN": odb, "DEF_OUT": def_p})
    run([OPENROAD, "-exit", f"{REPO}/src/dump_pg.tcl"],
        {"ODB_IN": odb, "CSV_OUT": raw_p})
    r = run([sys.executable, f"{REPO}/src/pg_extract.py", "--odb", odb,
             "--def", def_p, "--outdir", d, "--tag", tag])
    csv_p = os.path.join(d, "pg_shapes.csv")
    if not os.path.exists(csv_p):
        raise RuntimeError(f"pg_extract failed: {r.stdout[-1500:]}\n"
                           f"{r.stderr[-1500:]}")
    # pg_infer reads SPECIALNETS USE from floorplan.def; the freshly
    # exported DEF of the pdngen result carries the same nets, so reuse it
    # (randscan.py instead copied a cached per-design file).
    shutil.copy(def_p, os.path.join(d, "floorplan.def"))
    return csv_p

def parse_inferred(path, D):
    dbu = D["dbu"]
    t = open(path).read()
    m = re.search(r'set ::stripes_start_with "(\w+)"', t)
    sw = m.group(1) if m else None
    notes = re.findall(r"# NOTE: (.*)", t)
    rails = {}
    m = re.search(r"rails \{(.*?)\n    \}", t, re.S)
    if m:
        for lm in re.finditer(r"(\S+) \{width ([\d.]+)\}", m.group(1)):
            rails[lm.group(1)] = int(round(float(lm.group(2)) * dbu))
    straps = {}
    m = re.search(r"straps \{(.*?)\n    \}", t, re.S)
    if m:
        for lm in re.finditer(
                r"(\S+) \{width ([\d.]+) pitch ([\d.]+) offset ([\d.]+)"
                r"(?: spacing ([\d.]+))?\}", m.group(1)):
            straps[lm.group(1)] = {
                "w": int(round(float(lm.group(2)) * dbu)),
                "p": int(round(float(lm.group(3)) * dbu)),
                "o": int(round(float(lm.group(4)) * dbu)),
                "s": (None if lm.group(5) is None
                      else int(round(float(lm.group(5)) * dbu)))}
    conn = []
    m = re.search(r"connect \{(.*)\}", t)
    if m:
        conn = [list(x) for x in re.findall(r"\{(\S+) (\S+)\}", m.group(1))]
    return {"sw": sw, "rails": rails, "straps": straps,
            "connect": conn, "notes": notes}

def truth_dbu(cfg):
    return {"sw": cfg["sw"],
            "rails": {l: int(round(w)) for l, w in cfg["rails"].items()},
            "straps": {l: {k: (None if v is None else int(round(v)))
                           for k, v in s.items()}
                       for l, s in cfg["straps"].items()},
            "connect": [list(p) for p in cfg["connect"]]}

def compare(truth, inf):
    diffs = []
    if truth["sw"] != inf["sw"]:
        diffs.append(f"sw {truth['sw']}->{inf['sw']}")
    for l, w in truth["rails"].items():
        if inf["rails"].get(l) != w:
            diffs.append(f"rail.{l}.width {w}->{inf['rails'].get(l)}")
    for l, s in truth["straps"].items():
        b = inf["straps"].get(l)
        if b is None:
            diffs.append(f"{l} OMITTED (unidentifiable)")
            continue
        for k, kn in (("w", "width"), ("p", "pitch"), ("o", "offset"),
                      ("s", "spacing")):
            if s[k] != b[k]:
                diffs.append(f"{l}.{kn} {s[k]}->{b[k]}")
    tc = set(map(tuple, truth["connect"]))
    ic = set(map(tuple, inf["connect"]))
    if tc != ic:
        diffs.append(f"connect {sorted(tc)}->{sorted(ic)}")
    return diffs

def pd_diff(a_csv, b_csv):
    r = run([sys.executable, f"{REPO}/src/pd_diff.py", a_csv, b_csv])
    return "ROUNDTRIP PASS" in r.stdout, r.stdout.strip().splitlines()[:4]

def dual_cfg(cfg):
    d = json.loads(json.dumps(cfg))
    d["sw"] = "GROUND" if cfg["sw"] == "POWER" else "POWER"
    for l, s in d["straps"].items():
        shift = s["p"] / 2 if s["s"] is None else s["s"] + s["w"]
        s["o"] = s["o"] + shift
    return d

def worker(i, cfg, D, design):
    t0 = time.time()
    res = {"i": i, "kind": cfg.get("kind", "primary"),
           "strap_layers": sorted(cfg["straps"], key=layer_idx)}
    wd = f"{RS}/work/{design}_{i}"
    os.makedirs(wd, exist_ok=True)
    tag = f"{D['tag_prefix']}{i}"
    try:
        truth = truth_dbu(cfg)
        res["truth"] = truth
        pcfg = os.path.join(wd, "pdn.cfg")
        write_cfg(cfg, D, pcfg)
        odb = os.path.join(wd, "pdn.odb")
        pdngen_run(D, pcfg, odb, wd)
        shapes = extract(D, odb, tag)
        res["n_shapes"] = sum(1 for _ in open(shapes)) - 1
        with open(shapes, "rb") as f:
            res["shapes_md5"] = hashlib.md5(f.read()).hexdigest()
        r = run([sys.executable, f"{REPO}/src/pg_infer.py", "--tag", tag],
                timeout=600)
        icfg_p = f"{REPO}/data/{tag}/pdn_inferred.cfg"
        if not os.path.exists(icfg_p):
            res["status"] = "infer_fail"
            res["infer_log"] = (r.stdout[-1200:] + r.stderr[-1200:])
            res["wall_s"] = round(time.time() - t0, 1)
            with open(f"{RS}/results/{design}_{i}.json", "w") as f:
                json.dump(res, f)
            for t in (tag, f"{tag}rt", f"{tag}d"):
                shutil.rmtree(f"{REPO}/data/{t}", ignore_errors=True)
            shutil.rmtree(wd, ignore_errors=True)
            return res
        inf = parse_inferred(icfg_p, D)
        res["inferred"] = inf
        res["dropout_engaged"] = any("dropout-aware correction" in n
                                     for n in inf["notes"])
        diffs = compare(truth, inf)
        res["diffs"] = diffs
        # measured round-trip for every inferable config (rev5 expA method)
        rtcfg = os.path.join(wd, "rt.cfg")
        shutil.copy(icfg_p, rtcfg)
        rt_odb = os.path.join(wd, "rt.odb")
        pdngen_run(D, rtcfg, rt_odb, wd)
        rt_shapes = extract(D, rt_odb, f"{tag}rt")
        ok, det = pd_diff(shapes, rt_shapes)
        res["rt_pass"] = ok
        res["rt_detail"] = det
        if not diffs:
            res["status"] = "exact" if ok else "fail_exact_rt"
        elif all("OMITTED (unidentifiable)" in d for d in diffs):
            res["status"] = "unidentifiable"
            res["notes"] = inf.get("notes")
        else:
            res["status"] = "equiv" if ok else "fail"
        if D["dual"]:
            dc = dual_cfg(cfg)
            dcfg_p = os.path.join(wd, "dual.cfg")
            write_cfg(dc, D, dcfg_p)
            d_odb = os.path.join(wd, "dual.odb")
            pdngen_run(D, dcfg_p, d_odb, wd)
            d_shapes = extract(D, d_odb, f"{tag}d")
            ok, _ = pd_diff(shapes, d_shapes)
            res["dual_equiv"] = ok
            res["dual_truth"] = truth_dbu(dc)
    except Exception as e:
        res["status"] = "error"
        res["error"] = f"{type(e).__name__}: {str(e)[:400]}"
    finally:
        for t in (tag, f"{tag}rt", f"{tag}d"):
            shutil.rmtree(f"{REPO}/data/{t}", ignore_errors=True)
        shutil.rmtree(wd, ignore_errors=True)
    res["wall_s"] = round(time.time() - t0, 1)
    with open(f"{RS}/results/{design}_{i}.json", "w") as f:
        json.dump(res, f)
    return res

def sample_layer(rng, minw, D):
    # same validated constraints as rev3 WS2 sample_layer: width >= layer min
    # width (else PDN-0077); spacing None or >= min width (else cryptic
    # TypeError in dbu_to_microns); stripes non-overlapping within a layer.
    pmin, pmax = D["pitch_range"]; st = D["step"]
    p = rng.randrange(pmin, pmax + 1, st)
    wmax = min(D["w_cap"], p // 4)
    w = rng.randrange(minw, wmax + 1, st)
    omax = int(p * 1.2)
    o = rng.randrange(0, omax + 1, st)
    s = None
    if rng.random() < 0.5:
        smax = p - 3 * w
        if smax > minw + 200:
            s = rng.randrange(minw, smax, st)
    return {"w": w, "p": p, "o": o, "s": s}

def sample_strap_layers(rng, D):
    """Legal layer selection: L1 vertical (perpendicular to the rails),
    L2 horizontal (perpendicular to L1), both above the top rail layer.

    Rails are FOLLOWPIN along (horizontal) rows in every design, regardless
    of the rail metal's LEF preferred direction (asap7 M1 is LEF-vertical but
    its rails run horizontally -- verified: a horizontal L1=M4 strap layer
    formed zero rail->strap vias in the pilot). A strap layer parallel to
    the rails makes its connect pair a dead parameter, so it is excluded."""
    layers = D["strap_layers"]
    rail_top = max(layer_idx(r) for r in D["rail_layers"])
    c1 = [l for l, (mw, d) in layers.items()
          if d == "V" and layer_idx(l) > rail_top
          and any(d2 == "H" and layer_idx(l2) > layer_idx(l)
                  for l2, (mw2, d2) in layers.items())]
    L1 = rng.choice(sorted(c1, key=layer_idx))
    c2 = [l for l, (mw, d) in layers.items()
          if d == "H" and layer_idx(l) > layer_idx(L1)]
    L2 = rng.choice(sorted(c2, key=layer_idx))
    return L1, L2

def sample_cfg(rng, D, i):
    L1, L2 = sample_strap_layers(rng, D)
    straps = {L: sample_layer(rng, D["strap_layers"][L][0], D)
              for L in (L1, L2)}
    railw = rng.choice(D["railw_choices"])
    r0 = D["rail_layers"][0]
    return {"i": i, "kind": "primary",
            "rails": {r: railw for r in D["rail_layers"]},
            "sw": rng.choice(["POWER", "GROUND"]),
            "straps": straps,
            "connect": [[r0, L1], [L1, L2]]}

def summarize(design, n):
    import glob
    files = sorted(glob.glob(f"{RS}/results/{design}_*.json"))
    stats = {}
    exact = rt = succ = drop = dual = 0
    fails = []
    walls = []
    for fp in files:
        r = json.load(open(fp))
        st = r.get("status")
        stats[st] = stats.get(st, 0) + 1
        if st in ("exact", "equiv", "unidentifiable"): succ += 1
        if st == "exact": exact += 1
        if r.get("rt_pass"): rt += 1
        if r.get("dropout_engaged"): drop += 1
        if r.get("dual_equiv"): dual += 1
        if st in ("fail", "fail_exact_rt", "infer_fail", "error"):
            fails.append((r["i"], st, r.get("diffs"), r.get("error"),
                          r.get("rt_detail")))
        walls.append(r.get("wall_s", 0))
    tot = len(files)
    print(f"--- {design}: {tot}/{n} results")
    print(f"  inference success: {succ}/{tot}")
    print(f"  round-trip pass:   {rt}/{tot}")
    print(f"  exact:             {exact}/{tot}")
    print(f"  status histogram:  {stats}")
    print(f"  dropout engaged:   {drop}/{tot}")
    print(f"  dual_equiv:        {dual}/{tot}")
    print(f"  avg wall:          {sum(walls)/max(len(walls),1):.1f}s")
    for f_ in fails:
        print(f"  FAIL {f_}")

def main():
    design = sys.argv[1]
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 20260930
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    D = DESIGNS[design]
    rng = random.Random(seed)
    cfgs = [sample_cfg(rng, D, i) for i in range(n)]
    os.makedirs(f"{RS}/results", exist_ok=True)
    # archive truth in-repo (reviewer audit trail; never /tmp)
    tdir = f"{TRUTH_ROOT}/{design}"
    os.makedirs(tdir, exist_ok=True)
    manifest = {"seed": seed, "n": n, "design": design,
                "sampler": "src/randscan_breadth.py::sample_cfg "
                           "(python random.Random)",
                "units": "dbu integers; truth_dbu = rounded",
                "design_params": {k: v for k, v in D.items()
                                  if k not in ("base_odb", "sdc")},
                "git_commit": subprocess.run(
                    ["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
                    capture_output=True, text=True).stdout.strip()}
    for c in cfgs:
        entry = {"i": c["i"], "kind": c.get("kind", "primary"),
                 "sampled": {k: v for k, v in c.items()
                             if k not in ("i", "kind")},
                 "truth_dbu": truth_dbu(c)}
        with open(f"{tdir}/cfg_{c['i']:04d}.json", "w") as f:
            json.dump(entry, f)
    manifest["truth_files"] = [f"cfg_{c['i']:04d}.json" for c in cfgs]
    with open(f"{tdir}/MANIFEST.json", "w") as f:
        json.dump(manifest, f, indent=1)
    # run_pdn.tcl lives in /tmp/rs from expA; copy it into our scratch dir
    # (do not depend on /tmp/rs staying around)
    with open(f"{RS}/run_pdn.tcl", "w") as f:
        f.write(open("/tmp/rs/run_pdn.tcl").read()
                if os.path.exists("/tmp/rs/run_pdn.tcl") else
                "read_db $::env(ODB_IN)\npdngen $::env(PDN_CFG) -verbose\n"
                "write_db $::env(ODB_OUT)\nputs \"PDN_RUN_DONE\"\n")
    print(f"{design}: total {len(cfgs)} configs, 2 workers", flush=True)
    done = 0
    with ProcessPoolExecutor(max_workers=2) as ex:
        futs = {ex.submit(worker, c["i"], c, D, design): c["i"] for c in cfgs}
        for fu in futs:
            try:
                r = fu.result(timeout=1800)
                done += 1
                if done % 25 == 0 or done == len(cfgs):
                    print(f"  {done}/{len(cfgs)} ...", flush=True)
            except Exception as e:
                print(f"  worker exception: {e}", flush=True)
    print("SCAN_DONE", flush=True)
    summarize(design, n)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "summarize":
        summarize(sys.argv[2], int(sys.argv[3]))
    else:
        main()
