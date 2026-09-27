#!/usr/bin/env python3
"""rev3 WS2: random config-space scan for pdngen identifiability.
Worker: for one config -> pdngen, extract, infer, compare (dbu-exact),
round-trip non-exact cases, dual-config equivalence test.
"""
import csv, hashlib, json, math, os, random, re, shutil, subprocess, sys, time
from concurrent.futures import ProcessPoolExecutor

REPO = os.path.expanduser("~/pgrev")
RS = "/tmp/rs"
# rev5: truth configs are archived in-repo (never /tmp) for reviewer audit.
TRUTH_DIR = f"{REPO}/reports/rev5-scan-truth"
OPENROAD = os.path.expanduser("~/pgrev/tools/eda/bin/openroad")
BASE_ODB = f"{REPO}/tools/OpenROAD-flow-scripts/flow/results/sky130hd/gcd/base/2_5_floorplan_tapcell.odb"
BASE_SDC = f"{REPO}/tools/OpenROAD-flow-scripts/flow/results/sky130hd/gcd/base/1_synth.sdc"
DBU = 1000

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
        met1 {width %(railw).3f offset 0}
    }
    straps {
        met4 {width %(w4).3f pitch %(p4).3f offset %(o4).3f%(sp4)s}
        met5 {width %(w5).3f pitch %(p5).3f offset %(o5).3f%(sp5)s}
    }
    connect {{met1 met4} {met4 met5}}
}
"""

def um(d): return d / DBU

def write_cfg(cfg, path):
    def sp(v): return "" if v is None else f" spacing {um(v):.3f}"
    # fractional support: values may be float dbu
    with open(path, "w") as f:
        f.write(CFG_HEAD % dict(
            sw=cfg["sw"], railw=um(cfg["railw"]),
            w4=um(cfg["m4"]["w"]), p4=um(cfg["m4"]["p"]), o4=um(cfg["m4"]["o"]),
            sp4=sp(cfg["m4"]["s"]),
            w5=um(cfg["m5"]["w"]), p5=um(cfg["m5"]["p"]), o5=um(cfg["m5"]["o"]),
            sp5=sp(cfg["m5"]["s"])))

def run(cmd, env_extra=None, timeout=300):
    env = dict(os.environ); env.update(env_extra or {})
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout)
    return r

def pdngen_run(pdn_cfg, out_odb, workdir):
    os.makedirs(workdir, exist_ok=True)
    r = run([OPENROAD, "-exit", f"{RS}/run_pdn.tcl"],
            {"ODB_IN": BASE_ODB, "SDC_IN": BASE_SDC,
             "PDN_CFG": pdn_cfg, "ODB_OUT": out_odb})
    if not os.path.exists(out_odb):
        raise RuntimeError(f"pdngen produced no odb: {r.stdout[-1500:]}\n{r.stderr[-1500:]}")
    return r

def extract(odb, tag):
    """export DEF, dump, pg_extract -> pg_shapes.csv (tolerates matplotlib crash)."""
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
        raise RuntimeError(f"pg_extract failed: {r.stdout[-1500:]}\n{r.stderr[-1500:]}")
    # pg_infer needs core bounds; floorplan is identical for all scan configs
    shutil.copy(f"{REPO}/data/sky130hd_gcd/floorplan.def",
                os.path.join(d, "floorplan.def"))
    return csv_p

def parse_inferred(path):
    t = open(path).read()
    m = re.search(r'set ::stripes_start_with "(\w+)"', t)
    sw = m.group(1) if m else None
    notes = re.findall(r"# NOTE: (.*)", t)
    def grab(layer):
        m = re.search(layer + r" \{([^}]*)\}", t)
        if not m:
            return None
        body = m.group(1)
        d = {}
        for k in ("width", "pitch", "offset", "spacing"):
            mm = re.search(k + r" ([\d.]+)", body)
            d[k] = int(round(float(mm.group(1)) * DBU)) if mm else None
        return d
    rail = grab("met1") or {"width": None}
    g4, g5 = grab("met4"), grab("met5")
    def pack(g):
        return None if g is None else {"w": g["width"], "p": g["pitch"],
                                       "o": g["offset"], "s": g["spacing"]}
    return {"sw": sw, "railw": rail["width"], "m4": pack(g4), "m5": pack(g5),
            "notes": notes}

def truth_dbu(cfg):
    return {"sw": cfg["sw"], "railw": int(round(cfg["railw"])),
            "m4": {k: (None if v is None else int(round(v)))
                   for k, v in cfg["m4"].items()},
            "m5": {k: (None if v is None else int(round(v)))
                   for k, v in cfg["m5"].items()}}

def compare(truth, inf):
    """dbu-exact compare; returns list of diff descriptions (empty = exact)."""
    diffs = []
    if truth["sw"] != inf["sw"]: diffs.append(f"sw {truth['sw']}->{inf['sw']}")
    if truth["railw"] != inf["railw"]:
        diffs.append(f"railw {truth['railw']}->{inf['railw']}")
    for lay in ("m4", "m5"):
        a, b = truth[lay], inf[lay]
        if b is None:
            diffs.append(f"{lay} OMITTED (unidentifiable)")
            continue
        for k, kn in (("w", "width"), ("p", "pitch"), ("o", "offset"), ("s", "spacing")):
            if a[k] != b[k]: diffs.append(f"{lay}.{kn} {a[k]}->{b[k]}")
    return diffs

def pd_diff(a_csv, b_csv):
    r = run([sys.executable, f"{REPO}/src/pd_diff.py", a_csv, b_csv])
    return "ROUNDTRIP PASS" in r.stdout, r.stdout.strip().splitlines()[:4]

def dual_cfg(cfg):
    """reviewer's dual: flip starts_with, offset += shift."""
    d = json.loads(json.dumps(cfg))
    d["sw"] = "GROUND" if cfg["sw"] == "POWER" else "POWER"
    for lay in ("m4", "m5"):
        p = cfg[lay]["p"]; w = cfg[lay]["w"]; s = cfg[lay]["s"]
        shift = p / 2 if s is None else s + w
        d[lay]["o"] = cfg[lay]["o"] + shift
    return d

def worker(i, cfg):
    t0 = time.time()
    res = {"i": i, "kind": cfg.get("kind", "primary")}
    wd = f"{RS}/work/{i}"
    os.makedirs(wd, exist_ok=True)
    try:
        truth = truth_dbu(cfg)
        res["truth"] = truth
        pcfg = os.path.join(wd, "pdn.cfg")
        write_cfg(cfg, pcfg)
        odb = os.path.join(wd, "pdn.odb")
        pdngen_run(pcfg, odb, wd)
        tag = f"_rs{i}"
        shapes = extract(odb, tag)
        res["n_shapes"] = sum(1 for _ in open(shapes)) - 1
        # rev5: fingerprint the truth-generated geometry for the seed-fidelity
        # cross-check against the retained original-scan dirs data/ws2_*.
        with open(shapes, "rb") as f:
            res["shapes_md5"] = hashlib.md5(f.read()).hexdigest()
        r = run([sys.executable, f"{REPO}/src/pg_infer.py", "--tag", tag],
                timeout=300)
        icfg_p = f"{REPO}/data/{tag}/pdn_inferred.cfg"
        if not os.path.exists(icfg_p):
            res["status"] = "infer_fail"
            res["infer_log"] = (r.stdout[-1200:] + r.stderr[-1200:])
            res["wall_s"] = round(time.time() - t0, 1)
            with open(f"{RS}/results/{i}.json", "w") as f:
                json.dump(res, f)
            for t in (f"_rs{i}", f"_rs{i}rt", f"_rs{i}d"):
                shutil.rmtree(f"{REPO}/data/{t}", ignore_errors=True)
            shutil.rmtree(wd, ignore_errors=True)
            return res
        inf = parse_inferred(icfg_p)
        res["inferred"] = inf
        diffs = compare(truth, inf)
        res["diffs"] = diffs
        # rev5: round-trip is MEASURED for every inferable config, including
        # dbu-exact ones (no determinism argument). Status taxonomy:
        #   exact          = params dbu-identical AND round-trip bit-exact
        #   equiv          = params differ but round-trip bit-exact
        #   unidentifiable = inferrer declined (single-stripe, noted OMITTED)
        #   fail           = round-trip mismatch
        #   infer_fail     = no config produced / error
        rtcfg = os.path.join(wd, "rt.cfg")
        shutil.copy(icfg_p, rtcfg)
        rt_odb = os.path.join(wd, "rt.odb")
        pdngen_run(rtcfg, rt_odb, wd)
        rt_shapes = extract(rt_odb, f"_rs{i}rt")
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
        # dual-config equivalence test (reviewer's example)
        dc = dual_cfg(cfg)
        dcfg_p = os.path.join(wd, "dual.cfg")
        write_cfg(dc, dcfg_p)
        d_odb = os.path.join(wd, "dual.odb")
        pdngen_run(dcfg_p, d_odb, wd)
        d_shapes = extract(d_odb, f"_rs{i}d")
        ok, _ = pd_diff(shapes, d_shapes)
        res["dual_equiv"] = ok
        res["dual_truth"] = truth_dbu(dc)
    except Exception as e:
        res["status"] = "error"
        res["error"] = f"{type(e).__name__}: {str(e)[:400]}"
    finally:
        for t in (f"_rs{i}", f"_rs{i}rt", f"_rs{i}d"):
            shutil.rmtree(f"{REPO}/data/{t}", ignore_errors=True)
        # /tmp is a small tmpfs: drop per-config ODB/DEF/CSV after result saved
        shutil.rmtree(wd, ignore_errors=True)
    res["wall_s"] = round(time.time() - t0, 1)
    with open(f"{RS}/results/{i}.json", "w") as f:
        json.dump(res, f)
    return res

def sample_layer(rng, min_w, min_s):
    # Validated sky130hd constraints (this OpenROAD build):
    #   width >= layer min width (else PDN-0077); spacing None or >= min width
    #   (else cryptic TypeError in dbu_to_microns). Keep stripes non-overlapping.
    p = rng.randrange(8000, 50001, 2)
    wmax = min(3000, p // 4)
    w = rng.randrange(min_w, wmax + 1, 2)
    omax = int(p * 1.2)
    o = rng.randrange(0, omax + 1); o -= o % 2
    s = None
    if rng.random() < 0.5:
        smax = p - 3 * w
        if smax > min_s + 200:
            s = rng.randrange(min_s, smax, 2)
    return {"w": w, "p": p, "o": o, "s": s}

def sample_cfg(rng, i, kind="primary", directed_spacing=False,
               high_pitch=False):
    if high_pitch:
        # identifiability boundary: pitch >> core width -> 1 stripe/net
        def hp_layer(min_w, min_s):
            p = rng.randrange(150000, 300001, 2)
            w = rng.randrange(min_w, min(3001, p // 4), 2)
            o = rng.randrange(0, 100001); o -= o % 2
            return {"w": w, "p": p, "o": o, "s": None}
        m4 = hp_layer(400, 300); m5 = hp_layer(1600, 1600)
        return {"i": i, "kind": kind,
                "railw": rng.choice([240, 480, 720, 960]),
                "sw": rng.choice(["POWER", "GROUND"]), "m4": m4, "m5": m5}
    m4 = sample_layer(rng, 400, 300); m5 = sample_layer(rng, 1600, 1600)
    if directed_spacing:
        for m in (m4, m5):
            # force spacing+width == pitch/2 exactly
            m["s"] = m["p"] // 2 - m["w"]
    return {"i": i, "kind": kind,
            "railw": rng.choice([240, 480, 720, 960]),
            "sw": rng.choice(["POWER", "GROUND"]),
            "m4": m4, "m5": m5}

def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    n_pri = int(sys.argv[2]) if len(sys.argv) > 2 else 600
    n_dir = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    n_hp = int(sys.argv[4]) if len(sys.argv) > 4 else 10
    rng = random.Random(seed)
    cfgs = [sample_cfg(rng, i) for i in range(n_pri)]
    cfgs += [sample_cfg(rng, n_pri + j, kind="directed_spacing",
                        directed_spacing=True) for j in range(n_dir)]
    cfgs += [sample_cfg(rng, n_pri + n_dir + k, kind="high_pitch",
                        high_pitch=True) for k in range(n_hp)]
    os.makedirs(f"{RS}/results", exist_ok=True)
    with open(f"{RS}/configs.json", "w") as f:
        json.dump(cfgs, f)
    # rev5: archive every sampled truth config in-repo (small JSON: sampled
    # params only). This is the reviewer-audit trail the rev4 rescan lacked.
    os.makedirs(TRUTH_DIR, exist_ok=True)
    manifest = {"seed": seed, "n_primary": n_pri, "n_directed_spacing": n_dir,
                "n_high_pitch": n_hp, "total": len(cfgs),
                "sampler": "src/randscan.py::sample_cfg (python random.Random)",
                "units": "dbu integers (may be fractional); truth_dbu = rounded",
                "git_commit": subprocess.run(
                    ["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
                    capture_output=True, text=True).stdout.strip()}
    for c in cfgs:
        entry = {"i": c["i"], "kind": c.get("kind", "primary"),
                 "sampled": {k: v for k, v in c.items()
                             if k not in ("i", "kind")},
                 "truth_dbu": truth_dbu(c)}
        with open(f"{TRUTH_DIR}/cfg_{c['i']:04d}.json", "w") as f:
            json.dump(entry, f)
    manifest["truth_files"] = [f"cfg_{c['i']:04d}.json" for c in cfgs]
    with open(f"{TRUTH_DIR}/MANIFEST.json", "w") as f:
        json.dump(manifest, f, indent=1)
    print(f"total {len(cfgs)} configs, 2 workers", flush=True)
    done = 0
    with ProcessPoolExecutor(max_workers=2) as ex:
        futs = {ex.submit(worker, c["i"], c): c["i"] for c in cfgs}
        for fu in futs:
            try:
                r = fu.result(timeout=900)
                done += 1
                if done % 50 == 0:
                    print(f"  {done}/{len(cfgs)} ...", flush=True)
            except Exception as e:
                print(f"  worker exception: {e}", flush=True)
    print("SCAN_DONE", flush=True)

if __name__ == "__main__":
    main()
