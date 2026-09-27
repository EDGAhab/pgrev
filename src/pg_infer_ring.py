#!/usr/bin/env python3
"""WS3: infer core_ring parameters from labeled PDN geometry.

Forward model (legacy PdnGen.tcl generate_core_rings, core_offset semantics):
  for net i in [primary_power, primary_ground, ...] (pg_nets order):
    offset_i = core_offset + i*(width+spacing)   # per layer
    horizontal layer: bars at y = core_yMin - offset_i (bottom),
                      y = core_yMax + offset_i (top), each
                      rect (lx-w/2, y-w/2)-(ux+w/2, y+w/2)
    vertical layer:   bars at x = core_xMin - offset_i (left),
                      x = core_xMax + offset_i (right)

Inference: ring bars are the only wire rects whose center lies OUTSIDE the
core on the bar's short axis. (Stdcell straps are extended to the outer ring
edge, but their centers stay inside the core on the short axis.)
Outputs a core_ring spec fragment; compares against truth if given.
"""
import argparse, csv, json, sys
from collections import defaultdict

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shapes", required=True)
    ap.add_argument("--meta", required=True)
    ap.add_argument("--truth", default=None, help="json {layer:{width,spacing,core_offset}}")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    meta = json.load(open(a.meta))
    cx1, cy1, cx2, cy2 = meta["core"]
    rows = list(csv.DictReader(open(a.shapes)))

    # ring candidates: horizontal bars w/ center-y outside core; vertical bars w/ center-x outside
    cand = defaultdict(list)  # (net, layer, orient) -> rects
    for r in rows:
        if r["kind"] != "wire":
            continue
        x1, y1, x2, y2 = map(int, (r["x1"], r["y1"], r["x2"], r["y2"]))
        w, h = x2 - x1, y2 - y1
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        if w > h and (cy < cy1 or cy > cy2):
            cand[(r["net"], r["layer"], "hor")].append((x1, y1, x2, y2))
        elif h > w and (cx < cx1 or cx > cx2):
            cand[(r["net"], r["layer"], "ver")].append((x1, y1, x2, y2))

    layers = {}
    for (net, layer, orient), rects in cand.items():
        layers.setdefault(layer, orient)
        assert layers[layer] == orient, f"mixed orient on {layer}"

    if len(layers) != 2:
        print(f"AMBIGUITY: found {len(layers)} ring layers: {layers} (expected 2)", file=sys.stderr)

    # per net: collect offset measurements from all 4 sides
    net_offsets = defaultdict(list)   # net -> [offsets]
    net_widths = defaultdict(list)
    for (net, layer, orient), rects in cand.items():
        if len(rects) != 2:
            print(f"NOTE: {(net,layer)} has {len(rects)} ring rects (expected 2)", file=sys.stderr)
        for (x1, y1, x2, y2) in rects:
            w = min(x2 - x1, y2 - y1)
            net_widths[net].append(w)
            if orient == "hor":
                o = (cy1 - y1 - w / 2) if (y1 + y2) / 2 < cy1 else (y2 - cy2 - w / 2)
            else:
                o = (cx1 - x1 - w / 2) if (x1 + x2) / 2 < cx1 else (x2 - cx2 - w / 2)
            net_offsets[net].append(o)

    dbu = meta.get("dbu", 1000)
    result = {"layers": {}, "nets": {}}
    for net in sorted(net_offsets):
        offs = net_offsets[net]
        ws = net_widths[net]
        w_med = sorted(ws)[len(ws) // 2]
        o_med = sorted(offs)[len(offs) // 2]
        result["nets"][net] = {
            "width_dbu": w_med,
            "offset_dbu": o_med,
            "n_side_measurements": len(offs),
            "offset_spread_dbu": max(offs) - min(offs),
            "width_spread_dbu": max(ws) - min(ws),
        }

    nets_sorted = sorted(result["nets"], key=lambda n: result["nets"][n]["offset_dbu"])
    specs = {}
    for layer, orient in layers.items():
        # width uniform across nets on a layer (spec-level); take median
        w = sorted(net_widths[n][0] for n in nets_sorted)
        width = w[len(w) // 2]
        o0 = result["nets"][nets_sorted[0]]["offset_dbu"]
        if len(nets_sorted) > 1:
            o1 = result["nets"][nets_sorted[1]]["offset_dbu"]
            spacing = o1 - o0 - width
        else:
            spacing = None
        specs[layer] = {"width_um": width / dbu, "spacing_um": (spacing / dbu if spacing is not None else None),
                        "core_offset_um": o0 / dbu, "direction": orient,
                        "inner_net": nets_sorted[0],
                        "outer_net": nets_sorted[1] if len(nets_sorted) > 1 else None}
    result["layers"] = layers
    result["spec"] = specs

    lines = ["core_ring {"]
    for layer, s in specs.items():
        lines.append(f"    {layer} {{width {s['width_um']:.3f} spacing {s['spacing_um']:.3f} "
                     f"core_offset {s['core_offset_um']:.3f}}}  # {s['direction']}, inner={s['inner_net']}, outer={s['outer_net']}")
    lines.append("}")
    frag = "\n".join(lines)
    print(frag)
    print("\nper-net measurements (dbu):")
    for net, d in result["nets"].items():
        print(f"  {net}: width={d['width_dbu']} offset={d['offset_dbu']} "
              f"spread_o={d['offset_spread_dbu']} spread_w={d['width_spread_dbu']} n={d['n_side_measurements']}")

    if a.truth:
        truth = json.load(open(a.truth))
        print("\ntruth comparison:")
        ok = True
        for layer, t in truth.items():
            s = specs.get(layer)
            if s is None:
                print(f"  {layer}: MISSING in inference"); ok = False; continue
            for k in ("width_um", "spacing_um", "core_offset_um"):
                match = abs(s[k] - t[k]) < 1e-9
                ok &= match
                print(f"  {layer}.{k}: inferred={s[k]:.4f} truth={t[k]:.4f} {'EXACT' if match else 'DIFF'}")
        print("RING_INFER", "PASS" if ok else "FAIL")

    if a.out:
        open(a.out, "w").write(frag + "\n")

if __name__ == "__main__":
    main()
