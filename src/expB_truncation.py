#!/usr/bin/env python3
"""rev6 expB: truncation-modeling correction for the pdngen float-crack fails.

Reviewer (round 6): the 3 rev5 fails come from pdngen evaluating integer-dbu
truth params in um float, which can land 1-2 dbu off the integer model the
inferrer uses. Since the forward model is known, the inferrer can *simulate*
this truncation: after the frozen pg_infer.py initial inference, generate
candidates in a +/-2 dbu neighbourhood of the inferred params (offset /
spacing-shift / width / pitch per strap layer, rail widths), re-run the
forward model (pdngen) for each, and pick the candidate whose geometry is
bit-identical to the observed geometry (strict wire/via full-set compare,
0 dbu -- stricter than pd_diff.py's 1-dbu slack).

Selection uses ONLY the observed geometry; truth JSONs are used solely for
the final statistics. The correction triggers only when the initial
inference is not bit-exact (strict diff > 0), so all previously passing
configs are untouched by construction.

Usage:
  source ~/pgrev/env.sh && python3 src/expB_truncation.py pilot
  source ~/pgrev/env.sh && python3 src/expB_truncation.py run   # all 1600, 2 workers
  source ~/pgrev/env.sh && python3 src/expB_truncation.py aggregate
"""
import csv, hashlib, json, os, re, shutil, subprocess, sys, time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

REPO = os.path.expanduser("~/pgrev")
# Scratch + results. MUST be persistent storage: /tmp is wiped on VM
# restart (lost a 771-case run on 2026-09-28). Workdirs are transient
# (removed in worker finally); results/*.json are the durable output and
# double as the resume watermark (cmd_run skips cases with a result file).
RS = os.path.join(REPO, "work", "expB")
OPENROAD = os.path.expanduser("~/pgrev/tools/eda/bin/openroad")
FLOWRES = f"{REPO}/tools/OpenROAD-flow-scripts/flow/results"

DESIGNS = {
    "sky130hd_gcd": dict(dbu=1000, kind="expA",
        base_odb=f"{FLOWRES}/sky130hd/gcd/base/2_5_floorplan_tapcell.odb",
        sdc=f"{FLOWRES}/sky130hd/gcd/base/1_synth.sdc"),
    "nangate45_gcd": dict(dbu=2000, kind="breadth",
        base_odb=f"{FLOWRES}/nangate45/gcd/base/2_5_floorplan_tapcell.odb",
        sdc=f"{FLOWRES}/nangate45/gcd/base/1_synth.sdc"),
    "asap7_gcd": dict(dbu=1000, kind="breadth",
        base_odb=f"{FLOWRES}/asap7/gcd/base/2_5_floorplan_tapcell.odb",
        sdc=f"{FLOWRES}/asap7/gcd/base/1_synth.sdc"),
    "sky130hd_aes": dict(dbu=1000, kind="breadth",
        base_odb=f"{FLOWRES}/sky130hd/aes/base/2_5_floorplan_tapcell.odb",
        sdc=f"{FLOWRES}/sky130hd/aes/base/1_synth.sdc"),
}
TRUTH = {
    "sky130hd_gcd": f"{REPO}/reports/rev5-scan-truth/cfg_%04d.json",
    "nangate45_gcd": f"{REPO}/reports/rev5-breadth-truth/nangate45_gcd/cfg_%04d.json",
    "asap7_gcd": f"{REPO}/reports/rev5-breadth-truth/asap7_gcd/cfg_%04d.json",
    "sky130hd_aes": f"{REPO}/reports/rev5-breadth-truth/sky130hd_aes/cfg_%04d.json",
}
NS = {"sky130hd_gcd": 800, "nangate45_gcd": 300, "asap7_gcd": 300,
      "sky130hd_aes": 200}

# --------------------------------------------------------------------------
# cfg templates (verbatim from src/randscan.py and src/randscan_breadth.py)
# --------------------------------------------------------------------------
CFG_HEAD_A = """set ::halo 2
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

CFG_HEAD_B = """set ::halo 2
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

def write_cfg(G, D, path):
    """G: generic {sw, rails:{l:w}, straps:{l:{w,p,o,s}|None}, connect:[[b,t]]}."""
    if D["kind"] == "expA":
        def sp(v): return "" if v is None else f" spacing {um(v, D):.3f}"
        m4, m5 = G["straps"]["met4"], G["straps"]["met5"]
        txt = CFG_HEAD_A % dict(
            sw=G["sw"], railw=um(G["rails"]["met1"], D),
            w4=um(m4["w"], D), p4=um(m4["p"], D), o4=um(m4["o"], D), sp4=sp(m4["s"]),
            w5=um(m5["w"], D), p5=um(m5["p"], D), o5=um(m5["o"], D), sp5=sp(m5["s"]))
    else:
        def sp(v): return "" if v is None else f" spacing {um(v, D):.3f}"
        rails = "\n".join(f"        {l} {{width {um(w, D):.3f}}}"
                          for l, w in G["rails"].items())
        straps = "\n".join(
            f"        {l} {{width {um(s['w'], D):.3f} pitch {um(s['p'], D):.3f}"
            f" offset {um(s['o'], D):.3f}{sp(s['s'])}}}"
            for l, s in G["straps"].items() if s is not None)
        conn = " ".join(f"{{{b} {t}}}" for b, t in G["connect"])
        txt = CFG_HEAD_B % dict(sw=G["sw"], rails=rails, straps=straps,
                                connect=conn)
    with open(path, "w") as f:
        f.write(txt)

def from_truth(design, t):
    if DESIGNS[design]["kind"] == "expA":
        return {"sw": t["sw"], "rails": {"met1": t["railw"]},
                "straps": {"met4": dict(t["m4"]), "met5": dict(t["m5"])},
                "connect": [["met1", "met4"], ["met4", "met5"]]}
    return {"sw": t["sw"], "rails": dict(t["rails"]),
            "straps": {l: (None if s is None else dict(s))
                       for l, s in t["straps"].items()},
            "connect": [list(p) for p in t["connect"]]}

def to_orig_shape(design, G):
    """generic -> the per-design compare() input shape."""
    if DESIGNS[design]["kind"] == "expA":
        return {"sw": G["sw"], "railw": G["rails"]["met1"],
                "m4": G["straps"]["met4"], "m5": G["straps"]["met5"]}
    return {"sw": G["sw"], "rails": dict(G["rails"]),
            "straps": {l: (None if s is None else dict(s))
                       for l, s in G["straps"].items()},
            "connect": [list(p) for p in G["connect"]]}

# --------------------------------------------------------------------------
# parse_inferred (verbatim logic from randscan.py / randscan_breadth.py)
# --------------------------------------------------------------------------
def parse_inferred(design, path):
    D = DESIGNS[design]
    dbu = D["dbu"]
    t = open(path).read()
    m = re.search(r'set ::stripes_start_with "(\w+)"', t)
    sw = m.group(1) if m else None
    notes = re.findall(r"# NOTE: (.*)", t)
    if D["kind"] == "expA":
        def grab(layer):
            m = re.search(layer + r" \{([^}]*)\}", t)
            if not m: return None
            body = m.group(1)
            d = {}
            for k in ("width", "pitch", "offset", "spacing"):
                mm = re.search(k + r" ([\d.]+)", body)
                d[k] = int(round(float(mm.group(1)) * dbu)) if mm else None
            return d
        rail = grab("met1") or {"width": None}
        def pack(g):
            return None if g is None else {"w": g["width"], "p": g["pitch"],
                                           "o": g["offset"], "s": g["spacing"]}
        G = {"sw": sw, "rails": {"met1": rail["width"]},
             "straps": {"met4": pack(grab("met4")), "met5": pack(grab("met5"))},
             "connect": [["met1", "met4"], ["met4", "met5"]]}
    else:
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
        G = {"sw": sw, "rails": rails, "straps": straps, "connect": conn}
    G["notes"] = notes
    return G

# --------------------------------------------------------------------------
# compare (verbatim from randscan.py / randscan_breadth.py)
# --------------------------------------------------------------------------
def compare(design, truth, inf):
    diffs = []
    if DESIGNS[design]["kind"] == "expA":
        if truth["sw"] != inf["sw"]: diffs.append(f"sw {truth['sw']}->{inf['sw']}")
        if truth["railw"] != inf["railw"]:
            diffs.append(f"railw {truth['railw']}->{inf['railw']}")
        for lay in ("m4", "m5"):
            a, b = truth[lay], inf[lay]
            if b is None:
                diffs.append(f"{lay} OMITTED (unidentifiable)")
                continue
            for k, kn in (("w", "width"), ("p", "pitch"), ("o", "offset"),
                          ("s", "spacing")):
                if a[k] != b[k]: diffs.append(f"{lay}.{kn} {a[k]}->{b[k]}")
    else:
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

# --------------------------------------------------------------------------
# shell helpers
# --------------------------------------------------------------------------
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

def full_extract(odb, tag):
    """export DEF + dump + pg_extract (verbatim worker path); returns shapes."""
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
    shutil.copy(def_p, os.path.join(d, "floorplan.def"))
    return load_shapes_csv(csv_p), csv_p

def dump_raw(odb, raw_csv):
    r = run([OPENROAD, "-exit", f"{REPO}/src/dump_pg.tcl"],
            {"ODB_IN": odb, "CSV_OUT": raw_csv})
    if not os.path.exists(raw_csv):
        raise RuntimeError(f"dump_pg.tcl failed: {r.stdout[-1500:]}\n"
                           f"{r.stderr[-1500:]}")

def raw_to_shapes(raw_csv):
    """Verbatim port of pg_extract.py's raw.csv -> pg_shapes.csv mapping
    (no DEF/meta/matplotlib needed for pure geometry comparison)."""
    shapes = []
    for r in csv.DictReader(open(raw_csv)):
        x1, y1, x2, y2 = int(r["x1"]), int(r["y1"]), int(r["x2"]), int(r["y2"])
        if r["via_name"]:
            shapes.append({"net": r["net"],
                           "layer": f"{r['via_bot']}-{r['via_top']}",
                           "shape": r["shape"], "kind": "via",
                           "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                           "width": x2 - x1, "via_name": r["via_name"]})
        else:
            shapes.append({"net": r["net"], "layer": r["layer"],
                           "shape": r["shape"], "kind": "wire",
                           "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                           "width": min(x2 - x1, y2 - y1), "via_name": ""})
    return shapes

def write_shapes_csv(shapes, path):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["net", "layer", "shape", "kind",
                                          "x1", "y1", "x2", "y2", "width",
                                          "via_name"])
        w.writeheader(); w.writerows(shapes)

def load_shapes_csv(path):
    rows = list(csv.DictReader(open(path)))
    for r in rows:
        for k in ("x1", "y1", "x2", "y2", "width"): r[k] = int(r[k])
    return rows

def light_shapes(odb, tag):
    """pdngen odb -> shape list via dump only (no DEF export, no matplotlib)."""
    d = f"{REPO}/data/{tag}"
    if os.path.exists(d): shutil.rmtree(d)
    os.makedirs(d)
    raw = os.path.join(d, "pg_raw.csv")
    dump_raw(odb, raw)
    shapes = raw_to_shapes(raw)
    write_shapes_csv(shapes, os.path.join(d, "pg_shapes.csv"))
    return shapes

# --------------------------------------------------------------------------
# strict (0-dbu) geometry comparison
# --------------------------------------------------------------------------
def _wire_key(s):
    return (s["net"], s["layer"], s["shape"],
            s["x1"], s["y1"], s["x2"], s["y2"])

def _via_key(s):
    return (s["net"], s["layer"], s["via_name"],
            s["x1"], s["y1"], s["x2"], s["y2"])

def strict_diff(a, b):
    """Count of wire boxes + via entries differing at exact integer dbu."""
    wa = Counter(_wire_key(s) for s in a if s["kind"] == "wire")
    wb = Counter(_wire_key(s) for s in b if s["kind"] == "wire")
    va = Counter(_via_key(s) for s in a if s["kind"] == "via")
    vb = Counter(_via_key(s) for s in b if s["kind"] == "via")
    return (sum((wa - wb).values()) + sum((wb - wa).values())
            + sum((va - vb).values()) + sum((vb - va).values()))

def pd_diff_csv(a_csv, b_csv):
    r = run([sys.executable, f"{REPO}/src/pd_diff.py", a_csv, b_csv])
    return "ROUNDTRIP PASS" in r.stdout, r.stdout.strip().splitlines()[:4]

# --------------------------------------------------------------------------
# truncation-modeling correction: +/-2 dbu candidate search
# --------------------------------------------------------------------------
JDELTAS = (-2, -1, 1, 2)

def ser_val(v, dbu):
    """The dbu value pdngen actually sees for integer param v.

    Configs are written as %.3f um text (write_cfg / pg_infer.py). At
    DBU=2000 an odd dbu value (x.xxx5 um) does not survive the round-trip:
    e.g. 14263 -> "7.131" -> 14262. The forward model therefore only
    realizes the serialized lattice (even dbu at DBU=2000); candidates must
    live on it, and hypotheses are normalized to it before search.
    """
    if v is None:
        return None
    return int(round(float(f"{v / dbu:.3f}") * dbu))

def _clone(G):
    return {"sw": G["sw"], "rails": dict(G["rails"]),
            "straps": {l: (None if s is None else dict(s))
                       for l, s in G["straps"].items()},
            "connect": [list(p) for p in G["connect"]]}

def norm_hyp(h, dbu):
    """--hyps-out entry -> internal G, params normalized to the serialized
    (pdngen-realizable) lattice."""
    G = {"sw": h["sw"],
         "rails": {l: ser_val(w, dbu) for l, w in h["rails"].items()},
         "straps": {}, "connect": [list(p) for p in h["connect"]],
         "source": h.get("source", "?")}
    for l, s in h["straps"].items():
        G["straps"][l] = {k: ser_val(v, dbu) for k, v in s.items()}
    return G

def gen_candidates(G0, dbu):
    """Yield (label, Gcand, delta) in deterministic priority order.

    Single-param +/-{1,2} dbu jitter of every numeric param, restricted to
    the serialized lattice (ser_val(v) == v):
      per strap layer: offset, shift (spacing/shift, None-aware), width, pitch
      rails: all rail widths jointly
    Ordered by (total |delta|, param rank, layer, delta).
    """
    cands = []
    def add(label, G, delta, rank):
        cands.append((label, G, delta, rank))
    for L in sorted(G0["straps"]):
        s = G0["straps"][L]
        if s is None:
            continue
        w, p, o, sp = s["w"], s["p"], s["o"], s["s"]
        sh = p // 2 if sp is None else sp + w
        for d in JDELTAS:
            v = o + d
            if v >= 0 and ser_val(v, dbu) == v:
                G = _clone(G0); G["straps"][L]["o"] = v
                add(f"{L}.offset{d:+d}", G, abs(d), (abs(d), 0, L, d))
        for d in JDELTAS:
            sh2 = sh + d
            if sh2 == p // 2:
                sp2 = None
            else:
                sp2 = sh2 - w
                if sp2 is None or sp2 <= 0 or ser_val(sp2, dbu) != sp2:
                    continue
            G = _clone(G0); G["straps"][L]["s"] = sp2
            add(f"{L}.shift{d:+d}", G, abs(d), (abs(d), 1, L, d))
        for d in JDELTAS:
            v = w + d
            if ser_val(v, dbu) == v:
                G = _clone(G0); G["straps"][L]["w"] = v
                add(f"{L}.width{d:+d}", G, abs(d), (abs(d), 2, L, d))
            v = p + d
            if ser_val(v, dbu) == v:
                G = _clone(G0); G["straps"][L]["p"] = v
                add(f"{L}.pitch{d:+d}", G, abs(d), (abs(d), 3, L, d))
    for d in JDELTAS:
        vs = {l: w + d for l, w in G0["rails"].items()}
        if any(w <= 0 or ser_val(w, dbu) != w for w in vs.values()):
            continue
        G = _clone(G0); G["rails"] = vs
        add(f"rails.width{d:+d}", G, abs(d), (abs(d), 4, "", d))
    cands.sort(key=lambda c: c[3])
    return [(label, G, delta) for label, G, delta, _k in cands]

def gen_candidates_joint(G0, dbu):
    """Escalation: joint (offset x shift) 16 combos per strap layer,
    restricted to the serialized lattice."""
    cands = []
    for L in sorted(G0["straps"]):
        s = G0["straps"][L]
        if s is None:
            continue
        w, p, o, sp = s["w"], s["p"], s["o"], s["s"]
        sh = p // 2 if sp is None else sp + w
        for do in JDELTAS:
            vo = o + do
            if vo < 0 or ser_val(vo, dbu) != vo:
                continue
            for ds in JDELTAS:
                sh2 = sh + ds
                sp2 = None if sh2 == p // 2 else sh2 - w
                if sp2 is not None and (sp2 <= 0 or
                                        ser_val(sp2, dbu) != sp2):
                    continue
                G = _clone(G0)
                G["straps"][L]["o"] = vo
                G["straps"][L]["s"] = sp2
                cands.append((f"{L}.o{do:+d}s{ds:+d}", G, abs(do) + abs(ds)))
    cands.sort(key=lambda c: (c[2], c[0]))
    return [(label, G, delta) for label, G, delta in cands]

# --------------------------------------------------------------------------
# worker
# --------------------------------------------------------------------------
def worker(design, i):
    t0 = time.time()
    D = DESIGNS[design]
    res = {"design": design, "i": i}
    wd = f"{RS}/work/{design}_{i}"
    tag = f"_eB{design[:2]}{i}"
    tags = [tag]
    os.makedirs(wd, exist_ok=True)
    try:
        entry = json.load(open(TRUTH[design] % i))
        truth_orig = entry["truth_dbu"]
        Gtruth = from_truth(design, truth_orig)
        res["truth"] = truth_orig

        # observed geometry: forward(truth)
        pcfg = os.path.join(wd, "pdn.cfg")
        write_cfg(Gtruth, D, pcfg)
        odb = os.path.join(wd, "pdn.odb")
        pdngen_run(D, pcfg, odb, wd)
        obs_shapes, obs_csv = full_extract(odb, tag)
        res["n_shapes"] = len(obs_shapes)
        with open(obs_csv, "rb") as f:
            res["shapes_md5"] = hashlib.md5(f.read()).hexdigest()

        # frozen initial inference (+ diagnostic hypotheses sidecar;
        # --hyps-out is additive-only, byte-identical stdout/cfg verified)
        hyps_p = os.path.join(wd, "hyps.json")
        r = run([sys.executable, f"{REPO}/src/pg_infer.py", "--tag", tag,
                 "--hyps-out", hyps_p], timeout=600)
        icfg_p = f"{REPO}/data/{tag}/pdn_inferred.cfg"
        if not os.path.exists(icfg_p) or not os.path.exists(hyps_p):
            res["status"] = "infer_fail"
            res["infer_log"] = (r.stdout[-1200:] + r.stderr[-1200:])
            raise _Done()

        Hyps = [norm_hyp(h, D["dbu"]) for h in json.load(open(hyps_p))]
        res["n_hyps"] = len(Hyps)
        res["hyp_sources"] = [h.get("source", "?")
                              for h in json.load(open(hyps_p))]
        G0 = Hyps[0]
        # consistency: hypotheses[0] (serialized) must equal the emitted
        # winner config text parsed back
        G0_text = parse_inferred(design, icfg_p)
        if to_orig_shape(design, G0) != to_orig_shape(design, G0_text):
            res["hyp_winner_mismatch"] = {
                "hyp0": to_orig_shape(design, G0),
                "text": to_orig_shape(design, G0_text)}
        res["inferred_initial"] = to_orig_shape(design, G0_text)
        res["ambiguous_initial"] = any("AMBIGUOUS" in n
                                       for n in G0_text.get("notes", []))

        # strict round-trip of the initial inference (the trigger)
        rtcfg = os.path.join(wd, "rt0.cfg")
        write_cfg(G0, D, rtcfg)
        rt_odb = os.path.join(wd, "rt0.odb")
        pdngen_run(D, rtcfg, rt_odb, wd)
        rt0_tag = f"{tag}rt0"; tags.append(rt0_tag)
        rt0_shapes = light_shapes(rt_odb, rt0_tag)
        rt0_csv = f"{REPO}/data/{rt0_tag}/pg_shapes.csv"
        s0 = strict_diff(obs_shapes, rt0_shapes)
        res["initial_strict_diff"] = s0

        finalG, final_shapes, final_csv = G0, rt0_shapes, rt0_csv
        corrected, win_label, win_delta, win_hyp, ncand = (
            False, None, None, None, 0)
        if s0 > 0:
            # Truncation-modeling correction. Search space: every
            # globally-consistent hypothesis from the inferrer (the
            # tie-broken winner AND its AMBIGUOUS alternates -- needed
            # because a float-crack can push the tie-break onto the wrong
            # branch, whose +/-2 dbu neighbourhood contains no bit-exact
            # geometry) crossed with +/-2 dbu single-param jitter on the
            # serialized (pdngen-realizable) lattice, then joint
            # (offset x shift) escalation. Each candidate is verified with
            # the real forward model (pdngen); selection uses ONLY the
            # observed geometry: min strict diff, tie-broken by smallest
            # jitter, then hypothesis rank, then label (deterministic).
            INF = float("inf")
            scored = []
            c_tag = f"{tag}c"
            for phase, gen in (("single", gen_candidates),
                               ("joint", gen_candidates_joint)):
                for hi, H in enumerate(Hyps):
                    hcands = [(f"hyp{hi}/as-inferred", H, 0)]
                    hcands += [(f"hyp{hi}/{label}", Gc, delta)
                               for label, Gc, delta in gen(H, D["dbu"])]
                    for label, Gc, delta in hcands:
                        ccfg = os.path.join(wd, "cand.cfg")
                        write_cfg(Gc, D, ccfg)
                        c_odb = os.path.join(wd, "cand.odb")
                        d, c_shapes, added = None, None, False
                        try:
                            pdngen_run(D, ccfg, c_odb, wd)
                            tags.append(c_tag); added = True
                            c_shapes = light_shapes(c_odb, c_tag)
                            d = strict_diff(obs_shapes, c_shapes)
                        except Exception as e:
                            res.setdefault("cand_errors", []).append(
                                f"{label}: {type(e).__name__}")
                        finally:
                            shutil.rmtree(f"{REPO}/data/{c_tag}",
                                          ignore_errors=True)
                            if added:
                                tags.remove(c_tag)
                        ncand += 1
                        scored.append((d if d is not None else INF, delta,
                                       hi, label, Gc, c_shapes))
                res[f"phase_{phase}_evals"] = ncand
                if min(s[0] for s in scored) == 0:
                    break  # bit-exact found; joint escalation unnecessary
            res["candidates_evaluated"] = ncand
            scored.sort(key=lambda s: (s[0], s[1], s[2], s[3]))
            best = scored[0]
            if best[0] == 0:
                corrected = True
                win_hyp, win_label, win_delta = best[2], best[3], best[1]
                finalG, final_shapes = best[4], best[5]
                win_tag = f"{tag}win"; tags.append(win_tag)
                wd2 = f"{REPO}/data/{win_tag}"
                os.makedirs(wd2, exist_ok=True)
                final_csv = os.path.join(wd2, "pg_shapes.csv")
                write_shapes_csv(final_shapes, final_csv)
        res["corrected"] = corrected
        res["winning_hypothesis"] = win_hyp
        res["winning_candidate"] = win_label
        res["winning_delta"] = win_delta
        res["final_strict_diff"] = strict_diff(obs_shapes, final_shapes)

        # final metrics (rev5 taxonomy; rt criterion = pd_diff.py)
        ok, det = pd_diff_csv(obs_csv, final_csv)
        res["rt_pass"] = ok
        res["rt_detail"] = det
        inf_final = to_orig_shape(design, finalG)
        res["inferred_final"] = inf_final
        diffs = compare(design, truth_orig, inf_final)
        res["diffs"] = diffs
        if not diffs:
            res["status"] = "exact" if ok else "fail_exact_rt"
        elif all("OMITTED (unidentifiable)" in d for d in diffs):
            res["status"] = "unidentifiable"
        else:
            res["status"] = "equiv" if ok else "fail"
    except _Done:
        pass
    except Exception as e:
        res["status"] = "error"
        res["error"] = f"{type(e).__name__}: {str(e)[:400]}"
    finally:
        for t in tags:
            shutil.rmtree(f"{REPO}/data/{t}", ignore_errors=True)
        shutil.rmtree(wd, ignore_errors=True)
    res["wall_s"] = round(time.time() - t0, 1)
    os.makedirs(f"{RS}/results", exist_ok=True)
    with open(f"{RS}/results/{design}_{i}.json", "w") as f:
        json.dump(res, f)
    return res

class _Done(Exception):
    pass

# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------
def workload():
    wl = []
    for design in ("sky130hd_gcd", "nangate45_gcd", "asap7_gcd",
                   "sky130hd_aes"):
        wl += [(design, i) for i in range(NS[design])]
    return wl

def ensure_tcl():
    p = f"{RS}/run_pdn.tcl"
    if not os.path.exists(p):
        os.makedirs(RS, exist_ok=True)
        # reconstructed ORFS pdn.tcl semantics (rev5-expA report §2):
        # read_db -> pdngen $PDN_CFG -verbose -> write_db
        with open(p, "w") as f:
            f.write("read_db $::env(ODB_IN)\n"
                    "pdngen $::env(PDN_CFG) -verbose\n"
                    "write_db $::env(ODB_OUT)\n"
                    'puts "PDN_RUN_DONE"\n')

def cmd_pilot():
    ensure_tcl()
    # step 0: light_shapes transform self-check (must be identical to the
    # full pg_extract path on the same ODB)
    design, i = "nangate45_gcd", 46
    D = DESIGNS[design]
    entry = json.load(open(TRUTH[design] % i))
    Gtruth = from_truth(design, entry["truth_dbu"])
    wd = f"{RS}/work/pilot_xform"
    os.makedirs(wd, exist_ok=True)
    pcfg = os.path.join(wd, "pdn.cfg")
    write_cfg(Gtruth, D, pcfg)
    odb = os.path.join(wd, "pdn.odb")
    pdngen_run(D, pcfg, odb, wd)
    full_shapes, _csv = full_extract(odb, "_eBxf")
    light = light_shapes(odb, "_eBxl")
    sd = strict_diff(full_shapes, light)
    print(f"xform self-check strict_diff(full, light) = {sd} "
          f"(must be 0)", flush=True)
    assert sd == 0, "light transform diverges from pg_extract!"
    for t in ("_eBxf", "_eBxl"):
        shutil.rmtree(f"{REPO}/data/{t}", ignore_errors=True)
    shutil.rmtree(wd, ignore_errors=True)
    # step 1: the 3 known fails + 1 known exact + 1 known equiv
    cases = [("nangate45_gcd", 46), ("asap7_gcd", 4), ("asap7_gcd", 160),
             ("sky130hd_gcd", 0), ("sky130hd_gcd", 462)]
    for design, i in cases:
        print(f"=== pilot {design} cfg {i:04d} ===", flush=True)
        r = worker(design, i)
        print(f"  status={r.get('status')} rt_pass={r.get('rt_pass')} "
              f"init_strict={r.get('initial_strict_diff')} "
              f"corrected={r.get('corrected')} hyp={r.get('winning_hypothesis')} "
              f"win={r.get('winning_candidate')} "
              f"diffs={r.get('diffs')} wall={r.get('wall_s')}s", flush=True)
        if r.get("status") in ("error", "fail", "fail_exact_rt"):
            print(f"  detail: {r.get('error', r.get('rt_detail'))}", flush=True)

def cmd_run():
    ensure_tcl()
    wl = workload()
    # resume: skip cases whose result JSON already exists (VM restarts)
    todo = [(d, i) for d, i in wl
            if not os.path.exists(f"{RS}/results/{d}_{i}.json")]
    print(f"total {len(wl)} configs, {len(todo)} todo, 2 workers", flush=True)
    done = 0
    with ProcessPoolExecutor(max_workers=2) as ex:
        futs = {ex.submit(worker, d, i): (d, i) for d, i in todo}
        for fu in futs:
            try:
                r = fu.result(timeout=1800)
                done += 1
                if done % 50 == 0 or done == len(todo):
                    print(f"  {done}/{len(todo)} ...", flush=True)
            except Exception as e:
                print(f"  worker exception {futs[fu]}: {e}", flush=True)
    print("SCAN_DONE", flush=True)

def cmd_aggregate():
    import glob
    files = sorted(glob.glob(f"{RS}/results/*.json"))
    tot = {"exact": 0, "equiv": 0, "unidentifiable": 0, "fail": 0,
           "fail_exact_rt": 0, "infer_fail": 0, "error": 0}
    per = {}
    corrected, triggered = [], []
    strict_nz = []
    for fp in files:
        r = json.load(open(fp))
        dsg = r["design"]
        per.setdefault(dsg, {"exact": 0, "equiv": 0, "unidentifiable": 0,
                             "fail": 0, "fail_exact_rt": 0, "infer_fail": 0,
                             "error": 0})
        st = r.get("status", "?")
        tot[st] = tot.get(st, 0) + 1
        per[dsg][st] = per[dsg].get(st, 0) + 1
        if r.get("initial_strict_diff", 0) > 0:
            strict_nz.append((dsg, r["i"], r["initial_strict_diff"], st))
        if r.get("corrected"):
            corrected.append((dsg, r["i"], r.get("winning_hypothesis"),
                              r.get("winning_candidate"),
                              r.get("winning_delta"), st, r.get("diffs")))
    n = len(files)
    rt = sum(1 for fp in files if json.load(open(fp)).get("rt_pass"))
    # inference success (rev5 taxonomy): the inferrer produced a
    # geometry-faithful config -> exact / equiv / unidentifiable only.
    # A "fail" (round-trip mismatch) or "fail_exact_rt" counts against
    # success; "infer_fail"/"error" are hard failures.
    succ = (tot.get("exact", 0) + tot.get("equiv", 0)
            + tot.get("unidentifiable", 0))
    hard_fail = (tot.get("fail", 0) + tot.get("fail_exact_rt", 0)
                 + tot.get("infer_fail", 0) + tot.get("error", 0))
    print(f"results: {n}/1600")
    print(f"inference success: {succ}/{n}  (exact+equiv+unidentifiable)")
    print(f"round-trip pass:   {rt}/{n}")
    print(f"exact:             {tot.get('exact',0)}/{n}")
    print(f"hard failures (fail/fail_exact_rt/infer_fail/error): {hard_fail}")
    print(f"status histogram:  {tot}")
    for dsg in ("sky130hd_gcd", "nangate45_gcd", "asap7_gcd", "sky130hd_aes"):
        p = per.get(dsg, {})
        print(f"  {dsg}: {p}")
    print(f"correction triggered (initial strict>0): {len(strict_nz)}")
    for s in strict_nz:
        print(f"  trigger {s}")
    print(f"corrected to bit-exact: {len(corrected)}")
    for c in corrected:
        print(f"  fixed {c}")
    non_exact = [(r["design"], r["i"], r.get("status"), r.get("diffs"))
                 for fp in files
                 for r in [json.load(open(fp))]
                 if r.get("status") not in ("exact",)]
    print(f"non-exact ({len(non_exact)}):")
    for ne in non_exact:
        print(f"  {ne[0]} cfg_{ne[1]:04d} {ne[2]}: {ne[3]}")
    # audit: winner-consistency, candidate errors, missing cases
    mismatch = [(r["design"], r["i"]) for fp in files
                for r in [json.load(open(fp))]
                if r.get("hyp_winner_mismatch")]
    print(f"hyp_winner_mismatch ({len(mismatch)}): {mismatch}")
    cand_err = [(r["design"], r["i"], r.get("cand_errors")) for fp in files
                for r in [json.load(open(fp))] if r.get("cand_errors")]
    print(f"cases with candidate errors ({len(cand_err)}):")
    for ce in cand_err:
        print(f"  {ce[0]} cfg_{ce[1]:04d}: {ce[2]}")
    seen = {(r["design"], r["i"]) for fp in files
            for r in [json.load(open(fp))]}
    want = {(d, i) for d in ("sky130hd_gcd", "nangate45_gcd", "asap7_gcd",
                             "sky130hd_aes") for i in range(NS[d])}
    print(f"missing cases ({len(want - seen)}): {sorted(want - seen)[:10]}")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "pilot"
    {"pilot": cmd_pilot, "run": cmd_run, "aggregate": cmd_aggregate}[cmd]()
