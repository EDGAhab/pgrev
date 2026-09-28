#!/usr/bin/env python3
"""rev6 expC: random config-space scan on CURRENT C++ pdngen (OpenROAD HEAD).

Answers the round-6 reviewer's timeliness question: does the identifiability
result hold on the new C++ pdngen API (define_pdn_grid/add_pdn_stripe/
add_pdn_connect), which does NOT accept the legacy Tcl-dict `pdngen $PDN_CFG`
format (verified: task-1 finding, see reports/rev6-expC-head-rescan.md)?

Pipeline per config: sample cfg (same sampler as legacy randscan.py) ->
generate with HEAD openroad -> extract (phase7/extract_cpp.py) ->
infer (phase7/pg_infer_cpp.py) -> dbu-exact compare -> round-trip regen +
geometry compare.

SERIAL single worker (shared VM has two other light tasks).
Truth configs archived: reports/rev6-head-truth/cfg_*.json + MANIFEST.json.
"""
import csv, hashlib, json, os, random, re, shutil, subprocess, sys, time

REPO = os.path.expanduser("~/pgrev")
PH7 = f"{REPO}/phase7"
OPENROAD = f"{PH7}/openroad-src/build/bin/openroad"
TRUTH_DIR = f"{REPO}/reports/rev6-head-truth"
RS = "/tmp/headscan"
DBU = 1000
PDK = f"{REPO}/tools/OpenROAD-flow-scripts/flow/platforms/sky130hd/lef"
TLEF = f"{PDK}/sky130_fd_sc_hd.tlef"
TECH_LEF = f"{PDK}/sky130_fd_sc_hd_merged.lef"
DEF_IN = f"{PH7}/data/sky130hd_gcd_clean/floorplan.def"
HEAD_SHA = "80c6be93c28244f9f72840852a667daef764a4ff"

# ---- sampler: legacy src/randscan.py ranges, adapted to HEAD admissibility --
# HEAD (C++) pdngen admissibility constraints found empirically 2026-09-28
# (see reports/rev6-expC-head-rescan.md):
#   PDN-0191: width/pitch/offset/spacing must fit mfg grid 0.005 um = 5 dbu
#             (legacy Tcl accepted 1 dbu) -> quantize to multiples of 5 dbu.
#   PDN-0175: with explicit -spacing, pitch >= 2*(width+spacing) (hard error)
#             -> smax = p//2 - w (legacy used p - 3w, too permissive).
#   via4 rule M4M5_PR: cut 0.8 + met4 enclosure 2*0.19 -> met4 width < 1.18 um
#             inserts ZERO met4-met5 vias; all met5 stripes then removed as
#             floating (PDN-0200). -> met4 min width 1180 dbu.
#   via1 rule M1M2_PR: cut 0.15 + met1 enclosure 2*0.055 -> rail width < 0.26 um
#             inserts ZERO met1-met2 vias; cascade removes met4 AND met5
#             stripes (PDN-0200). -> railw choices >= 300 dbu.
def sample_layer(rng, min_w, min_s):
    p = rng.randrange(8000, 50001, 10)
    wmax = min(3000, p // 4)
    w = rng.randrange(min_w, wmax + 1, 10)
    omax = int(p * 1.2)
    o = rng.randrange(0, omax + 1, 10)
    s = None
    if rng.random() < 0.5:
        smax = p // 2 - w
        if smax > min_s + 200:
            s = rng.randrange(min_s, smax, 10)
    return {"w": w, "p": p, "o": o, "s": s}

def sample_cfg(rng, i, kind="primary"):
    m4 = sample_layer(rng, 1180, 300)   # 1180 dbu = via4 1.18 um min (PDN-0200)
    m5 = sample_layer(rng, 1600, 1600)
    return {"i": i, "kind": kind,
            "railw": rng.choice([300, 480, 720, 960]),  # >= via1 0.26 um min
            "sw": rng.choice(["POWER", "GROUND"]),
            "m4": m4, "m5": m5}

# ---- new-API Tcl generation ------------------------------------------------
def um(dbu):
    return dbu / DBU

def stripe_line(lay, w, p, o, s, sw):
    cmd = (f"add_pdn_stripe -grid grid -layer {lay} "
           f"-width {um(w):.3f} -pitch {um(p):.3f} -offset {um(o):.3f} "
           f"-starts_with {sw}")
    if s is not None:
        cmd += f" -spacing {um(s):.3f}"
    return cmd

def write_gen_tcl(cfg, path):
    L = [
        "read_lef $::env(TLEF)",
        "read_lef $::env(TECH_LEF)",
        "read_def $::env(DEF_IN)",
        "add_global_connection -net VDD -pin_pattern VPWR -power",
        "add_global_connection -net VDD -pin_pattern VPB -power",
        "add_global_connection -net VSS -pin_pattern VGND -ground",
        "add_global_connection -net VSS -pin_pattern VNB -ground",
        "set_voltage_domain -power VDD -ground VSS",
        f"define_pdn_grid -name grid -starts_with {cfg['sw']} "
        '-voltage_domains {CORE} -pins "met4 met5"',
        "",
        stripe_line("met4", cfg["m4"]["w"], cfg["m4"]["p"], cfg["m4"]["o"],
                    cfg["m4"]["s"], cfg["sw"]),
        stripe_line("met5", cfg["m5"]["w"], cfg["m5"]["p"], cfg["m5"]["o"],
                    cfg["m5"]["s"], cfg["sw"]),
        'add_pdn_connect -grid grid -layers "met4 met5"',
        f"add_pdn_stripe -grid grid -layer met1 -width {um(cfg['railw']):.3f} -followpins",
        'add_pdn_connect -grid grid -layers "met1 met4"',
        "",
        "pdngen",
        "write_db $::env(ODB_OUT)",
        'puts "GEN DONE"',
    ]
    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")

def run(cmd, env_extra=None, timeout=300):
    env = dict(os.environ)
    env.update(env_extra or {})
    return subprocess.run(cmd, capture_output=True, text=True, env=env,
                          timeout=timeout)

def pdngen_run(gen_tcl, out_odb):
    r = run([OPENROAD, "-exit", gen_tcl],
            {"TLEF": TLEF, "TECH_LEF": TECH_LEF,
             "DEF_IN": DEF_IN, "ODB_OUT": out_odb}, timeout=600)
    if not os.path.exists(out_odb):
        raise RuntimeError(f"pdngen produced no odb: {(r.stdout+r.stderr)[-1500:]}")
    return r

def extract(odb, tag):
    d = f"{PH7}/data/{tag}"
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(d)
    env = dict(os.environ, OPENROAD_EXE=OPENROAD)
    r = subprocess.run([sys.executable, f"{PH7}/extract_cpp.py", "--odb", odb,
                        "--def", DEF_IN, "--outdir", d, "--tag", tag],
                       capture_output=True, text=True, env=env, timeout=900)
    csv_p = os.path.join(d, "pg_shapes.csv")
    if not os.path.exists(csv_p):
        raise RuntimeError(f"extract failed: {(r.stdout+r.stderr)[-1500:]}")
    shutil.copy(DEF_IN, os.path.join(d, "floorplan.def"))
    return csv_p

# ---- inference -------------------------------------------------------------
def run_infer(tag):
    r = run([sys.executable, f"{PH7}/pg_infer_cpp.py", "--tag", tag],
            timeout=300)
    return r

def parse_inferred(path):
    """Parse new-API pdn_inferred.tcl -> {sw, grid_sw, railw, m4, m5, pairs}."""
    t = open(path).read()
    out = {"sw": None, "grid_sw": None, "railw": None, "m4": None,
           "m5": None, "pairs": [], "notes": []}
    m = re.search(r'define_pdn_grid -name grid -starts_with (\w+)', t)
    if m:
        out["grid_sw"] = m.group(1)
    for line in t.splitlines():
        if "add_pdn_stripe" not in line:
            continue
        lm = re.search(r"-layer (\S+)", line)
        if not lm:
            continue
        lay = lm.group(1)
        # map met4->m4, met5->m5 to match truth keys
        key = re.sub(r"^met", "m", lay)
        def grab(flag):
            mm = re.search(flag + r" ([\d.]+)", line)
            return int(round(float(mm.group(1)) * DBU)) if mm else None
        if "-followpins" in line:
            out["railw"] = grab("-width")
            continue
        if key not in ("m4", "m5"):
            continue
        swm = re.search(r"-starts_with (\w+)", line)
        rec = {"w": grab("-width"), "p": grab("-pitch"), "o": grab("-offset"),
               "s": grab("-spacing"), "sw": swm.group(1) if swm else None}
        out[key] = rec
        if out["sw"] is None:
            out["sw"] = rec["sw"]
        elif out["sw"] != rec["sw"]:
            out["sw"] = "MIXED!"
    out["pairs"] = re.findall(r'add_pdn_connect -grid grid -layers "([^"]+)"', t)
    return out

def truth_dbu(cfg):
    return {"sw": cfg["sw"], "railw": int(round(cfg["railw"])),
            "m4": {k: (None if v is None else int(round(v)))
                   for k, v in cfg["m4"].items() if k != "sw"},
            "m5": {k: (None if v is None else int(round(v)))
                   for k, v in cfg["m5"].items() if k != "sw"}}

def compare(truth, inf):
    diffs = []
    if truth["sw"] != inf["sw"]:
        diffs.append(f"sw {truth['sw']}->{inf['sw']}")
    if inf["grid_sw"] and truth["sw"] != inf["grid_sw"]:
        diffs.append(f"grid_sw {truth['sw']}->{inf['grid_sw']}")
    if truth["railw"] != inf["railw"]:
        diffs.append(f"railw {truth['railw']}->{inf['railw']}")
    for lay in ("m4", "m5"):
        a, b = truth[lay], inf[lay]
        if b is None:
            diffs.append(f"{lay} OMITTED (unidentifiable)")
            continue
        for k, kn in (("w", "width"), ("p", "pitch"), ("o", "offset"),
                      ("s", "spacing")):
            if a[k] != b[k]:
                diffs.append(f"{lay}.{kn} {a[k]}->{b[k]}")
        if a.get("sw") is None and b["sw"] != truth["sw"]:
            diffs.append(f"{lay}.starts_with {truth['sw']}->{b['sw']}")
    return diffs

# ---- round-trip -------------------------------------------------------------
def shapes_key(csv_p):
    rows = list(csv.DictReader(open(csv_p)))
    ws = sorted((r["net"], r["layer"], r["shape"], int(r["x1"]), int(r["y1"]),
                 int(r["x2"]), int(r["y2"])) for r in rows if r["kind"] == "wire")
    vs = sorted((r["net"], r["layer"], r["shape"], int(r["x1"]), int(r["y1"]),
                 int(r["x2"]), int(r["y2"]), r["via_name"])
                for r in rows if r["kind"] == "via")
    return ws, vs

def roundtrip_pass(truth_csv, inf_tcl, wd):
    """Regenerate from inferred tcl; return (pass, detail)."""
    rt_tcl = os.path.join(wd, "regen.tcl")
    with open(rt_tcl, "w") as f:
        f.write(f"""read_lef {TLEF}
read_lef {TECH_LEF}
read_def {DEF_IN}
add_global_connection -net VDD -pin_pattern VPWR -power
add_global_connection -net VDD -pin_pattern VPB -power
add_global_connection -net VSS -pin_pattern VGND -ground
add_global_connection -net VSS -pin_pattern VNB -ground
source {inf_tcl}
write_db $::env(ODB_OUT)
""")
    rt_odb = os.path.join(wd, "rt.odb")
    r = run([OPENROAD, "-exit", rt_tcl], {"ODB_OUT": rt_odb}, timeout=600)
    if not os.path.exists(rt_odb):
        return False, [f"regen produced no odb: {(r.stdout+r.stderr)[-500:]}"]
    rt_csv = extract(rt_odb, f"head_rt_tmp")
    a = shapes_key(truth_csv)
    b = shapes_key(rt_csv)
    shutil.rmtree(f"{PH7}/data/head_rt_tmp", ignore_errors=True)
    dw = [x for x in a[0] if x not in b[0]] + [x for x in b[0] if x not in a[0]]
    dv = [x for x in a[1] if x not in b[1]] + [x for x in b[1] if x not in a[1]]
    det = [f"wires t={len(a[0])} r={len(b[0])} diff={len(dw)}",
           f"vias t={len(a[1])} r={len(b[1])} diff={len(dv)}"]
    return (not dw and not dv), det

# ---- worker -----------------------------------------------------------------
def worker(i, cfg):
    t0 = time.time()
    res = {"i": i, "kind": cfg.get("kind", "primary")}
    wd = f"{RS}/work/{i}"
    os.makedirs(wd, exist_ok=True)
    tag = f"head_{i}"
    try:
        truth = truth_dbu(cfg)
        res["truth"] = truth
        gen_tcl = os.path.join(wd, "gen.tcl")
        write_gen_tcl(cfg, gen_tcl)
        odb = os.path.join(wd, "pdn.odb")
        try:
            pdngen_run(gen_tcl, odb)
        except RuntimeError as e:
            res["status"] = "gen_fail"
            errs = [l for l in str(e).splitlines() if "ERROR" in l]
            res["error"] = "; ".join(errs[:4])[:500] or str(e)[:500]
            res["wall_s"] = round(time.time() - t0, 1)
            return res
        shapes = extract(odb, tag)
        res["n_shapes"] = sum(1 for _ in open(shapes)) - 1
        with open(shapes, "rb") as f:
            res["shapes_md5"] = hashlib.md5(f.read()).hexdigest()
        r = run_infer(tag)
        icfg_p = f"{PH7}/data/{tag}/pdn_inferred.tcl"
        if not os.path.exists(icfg_p):
            res["status"] = "infer_fail"
            res["infer_log"] = (r.stdout[-1200:] + r.stderr[-1200:])
            res["wall_s"] = round(time.time() - t0, 1)
            return res
        inf = parse_inferred(icfg_p)
        res["inferred"] = inf
        diffs = compare(truth, inf)
        res["diffs"] = diffs
        ok, det = roundtrip_pass(shapes, icfg_p, wd)
        res["rt_pass"] = ok
        res["rt_detail"] = det
        if not diffs:
            res["status"] = "exact" if ok else "fail_exact_rt"
        elif all("OMITTED (unidentifiable)" in d for d in diffs):
            res["status"] = "unidentifiable"
        else:
            res["status"] = "equiv" if ok else "fail"
    except Exception as e:
        res["status"] = "error"
        res["error"] = f"{type(e).__name__}: {str(e)[:400]}"
    finally:
        shutil.rmtree(f"{PH7}/data/{tag}", ignore_errors=True)
        shutil.rmtree(wd, ignore_errors=True)
    res["wall_s"] = round(time.time() - t0, 1)
    return res

def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 20260930
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    rng = random.Random(seed)
    cfgs = [sample_cfg(rng, i) for i in range(n)]
    # archive truth upfront (reviewer audit trail)
    os.makedirs(TRUTH_DIR, exist_ok=True)
    os.makedirs(f"{RS}/results", exist_ok=True)
    truth_files = []
    for c in cfgs:
        fn = f"cfg_{c['i']:04d}.json"
        truth_files.append(fn)
        with open(f"{TRUTH_DIR}/{fn}", "w") as f:
            json.dump({"i": c["i"], "kind": c["kind"], "sampled": c,
                       "truth_dbu": truth_dbu(c)}, f, indent=1)
    manifest = {"seed": seed, "n_primary": n, "n_directed_spacing": 0,
                "n_high_pitch": 0, "total": n,
                "sampler": "phase7/randscan_head.py::sample_cfg (python random.Random); "
                           "ranges match legacy src/randscan.py except HEAD "
                           "admissibility restrictions (see below)",
                "units": "dbu integers, multiples of 5 (mfg grid); "
                         "truth_dbu = sampled (no rounding needed)",
                "api": "OpenROAD C++ pdngen: define_pdn_grid/add_pdn_stripe/add_pdn_connect + pdngen",
                "openroad_head": HEAD_SHA,
                "design": "sky130hd/gcd (phase7/data/sky130hd_gcd_clean/floorplan.def)",
                "connect": "fixed {{met1 met4} {met4 met5}}",
                "admissibility": {
                    "mfg_grid_5dbu": "PDN-0191 hard error otherwise",
                    "pitch_ge_2x_w_plus_s": "PDN-0175 hard error otherwise",
                    "met4_width_min_um": 1.18,
                    "met4_width_min_why": "via4 rule M4M5_PR: 0.8 + 2*0.19; below -> 0 vias -> met5 stripes removed as floating (PDN-0200)",
                    "rail_width_min_um": 0.30,
                    "rail_width_min_why": "via1 rule M1M2_PR: 0.15 + 2*0.055 = 0.26; below -> 0 vias -> cascade removes met4+met5 stripes (PDN-0200)",
                },
                "truth_files": truth_files}
    with open(f"{TRUTH_DIR}/MANIFEST.json", "w") as f:
        json.dump(manifest, f, indent=1)
    print(f"truth archived: {n} cfgs -> {TRUTH_DIR} (seed {seed})", flush=True)

    results = []
    t_all = time.time()
    for idx, c in enumerate(cfgs):
        res = worker(c["i"], c)
        results.append(res)
        with open(f"{RS}/results/{c['i']}.json", "w") as f:
            json.dump(res, f)
        if (idx + 1) % 10 == 0 or idx == 0:
            el = time.time() - t_all
            eta = el / (idx + 1) * (n - idx - 1)
            sts = {}
            for r2 in results:
                sts[r2["status"]] = sts.get(r2["status"], 0) + 1
            print(f"[{idx+1}/{n}] {res['status']} wall={res['wall_s']}s "
                  f"elapsed={el/60:.1f}m eta={eta/60:.1f}m {sts}", flush=True)
    el = time.time() - t_all
    sts = {}
    for r2 in results:
        sts[r2["status"]] = sts.get(r2["status"], 0) + 1
    summary = {"seed": seed, "n": n, "status_counts": sts,
               "wall_min": round(el / 60, 1), "serial": True}
    with open(f"{TRUTH_DIR}/scan_results.json", "w") as f:
        json.dump(summary, f, indent=1)
    print(f"DONE {n} configs in {el/60:.1f} min: {sts}", flush=True)

if __name__ == "__main__":
    main()
