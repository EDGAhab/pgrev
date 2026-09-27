#!/usr/bin/env python3
"""WS3: infer macro-grid parameters from labeled PDN geometry + floorplan meta.

Recoverable (given macro bbox from DEF placement + LEF size, or derived from
macro-confined straps):
  - straps over macro: per layer {width, pitch, offset from macro edge, net order}
  - blockages: stdcell strap layers interrupted over the macro bbox
  - connect: via stacks over the macro bbox; pin-width via fingerprint
             (via rect x-extent == macro pin width) => {pinlayer_PIN_<dir> strap}
Not recoverable from PDN geometry alone:
  - power_pins/ground_pins NAMES (need LEF pin names)
  - orient selector (known from DEF instance orient)
  - blockage layers with no observable effect (e.g. metal1 rails are NOT cut
    by legacy blockages -- quirk; metal2/3 have no stdcell straps here)
"""
import argparse, csv, json
from collections import defaultdict, Counter

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shapes", required=True)
    ap.add_argument("--meta", required=True)
    ap.add_argument("--macro-size-um", required=True, help="W,H in um from LEF")
    a = ap.parse_args()
    meta = json.load(open(a.meta))
    dbu = meta["dbu"]
    mw, mh = [float(x) * dbu for x in a.macro_size_um.split(",")]
    macros = meta["macros"]
    assert len(macros) == 1, f"expected 1 macro, got {len(macros)}"
    mi = macros[0]
    mb = (mi["x"], mi["y"], mi["x"] + mw, mi["y"] + mh)  # macro bbox dbu
    print(f"macro {mi['inst']} {mi['cell']} orient={mi['orient']} bbox_dbu={tuple(int(v) for v in mb)}")

    rows = list(csv.DictReader(open(a.shapes)))
    wires = [r for r in rows if r["kind"] == "wire"]
    vias = [r for r in rows if r["kind"] == "via"]
    for r in wires + vias:
        for k in ("x1", "y1", "x2", "y2"):
            r[k] = int(r[k])

    def inside_macro(r, pad=0):
        return r["x1"] >= mb[0]-pad and r["x2"] <= mb[2]+pad and r["y1"] >= mb[1]-pad and r["y2"] <= mb[3]+pad

    # 1) macro-confined strap layers: layers whose wires are ALL inside macro bbox
    by_layer = defaultdict(list)
    for r in wires:
        by_layer[r["layer"]].append(r)
    macro_layers = [l for l, rs in by_layer.items()
                    if all(inside_macro(r) for r in rs) and len(rs) >= 2]
    print(f"\nmacro-confined strap layers: {macro_layers}")

    strap_specs = {}
    for layer in macro_layers:
        rs = sorted(by_layer[layer], key=lambda r: (r["y1"], r["x1"]))
        # orientation from first wire
        r0 = rs[0]
        hor = (r0["x2"] - r0["x1"]) > (r0["y2"] - r0["y1"])
        widths = Counter(min(r["x2"]-r["x1"], r["y2"]-r["y1"]) for r in rs)
        width = widths.most_common(1)[0][0]
        centers = sorted(set(((r["x1"]+r["x2"])/2 if not hor else (r["y1"]+r["y2"])/2) for r in rs))
        # per-net centers to get pitch & offset & order
        net_centers = defaultdict(list)
        for r in rs:
            c = (r["x1"]+r["x2"])/2 if not hor else (r["y1"]+r["y2"])/2
            net_centers[r["net"]].append(c)
        allc = sorted(centers)
        # pitch: same-net center spacing (nets interleave, so use per-net)
        per_net_pitch = []
        for n, cs in net_centers.items():
            sc = sorted(cs)
            if len(sc) > 1:
                per_net_pitch += [b - a for a, b in zip(sc, sc[1:])]
        pitch = per_net_pitch[0] if per_net_pitch else None
        assert all(p == pitch for p in per_net_pitch), f"nonuniform pitch {Counter(per_net_pitch)}"
        edge = mb[1] if hor else mb[0]
        offset = allc[0] - edge - width/2 + width/2  # center - edge... see below
        # offset def: distance from macro edge to first strap CENTERLINE
        offset = allc[0] - edge
        order = [n for n, _ in sorted(net_centers.items(), key=lambda kv: min(kv[1]))]
        strap_specs[layer] = {"width_dbu": width, "pitch_dbu": pitch,
                              "offset_dbu": offset, "direction": "hor" if hor else "ver",
                              "net_order": order, "n": len(rs)}
        print(f"  {layer}: {'hor' if hor else 'ver'} width={width/dbu:.3f}um "
              f"pitch={pitch/dbu if pitch else None}um offset={offset/dbu:.3f}um order={order} n={len(rs)}")

    # 2) blockages: stdcell strap layers interrupted over the macro bbox.
    #    Group long bars by (net, long-axis centerline); a group whose centerline
    #    passes through the macro is interrupted iff it has segments strictly
    #    outside the macro but none passing through its interior.
    cx1, cy1, cx2, cy2 = meta["core"]
    blocked = []
    for layer, rs in by_layer.items():
        if layer in macro_layers:
            continue
        segs = defaultdict(list)
        for r in rs:
            if max(r["x2"]-r["x1"], r["y2"]-r["y1"]) <= 20000:
                continue  # via-stack landing artifact, not a strap
            vert = (r["y2"]-r["y1"]) > (r["x2"]-r["x1"])
            axis_c = (r["x1"]+r["x2"])/2 if vert else (r["y1"]+r["y2"])/2
            in_range = (mb[0] < axis_c < mb[2]) if vert else (mb[1] < axis_c < mb[3])
            if in_range:
                segs[(r["net"], axis_c)].append(r)
        if not segs:
            continue
        interrupted = False
        for key, srs in segs.items():
            vert = (srs[0]["y2"]-srs[0]["y1"]) > (srs[0]["x2"]-srs[0]["x1"])
            if vert:
                outside = [r for r in srs if r["y2"] <= mb[1] + 2*dbu or r["y1"] >= mb[3] - 2*dbu]
                through = [r for r in srs if r["y1"] < mb[3] and r["y2"] > mb[1] and r not in outside]
            else:
                outside = [r for r in srs if r["x2"] <= mb[0] + 2*dbu or r["x1"] >= mb[2] - 2*dbu]
                through = [r for r in srs if r["x1"] < mb[2] and r["x2"] > mb[0] and r not in outside]
            if outside and not through:
                interrupted = True
        print(f"  stdcell layer {layer}: colinear groups through macro: {len(segs)}, interrupted={interrupted}")
        if interrupted:
            blocked.append(layer)
    print(f"\nobserved blocked layers: {blocked}")

    # 3) connect pairs from via stacks over macro bbox
    print("\nvia stacks over macro bbox:")
    vcnt = Counter()
    pinvias = defaultdict(list)
    for r in vias:
        if r["x1"] >= mb[0] and r["x2"] <= mb[2] and r["y1"] >= mb[1] and r["y2"] <= mb[3]:
            vcnt[(r["layer"], r["via_name"])] += 1
            # pin-width fingerprint: via x-extent == 560 dbu (0.28um pin width)
            if r["layer"] == "metal4-metal5" and (r["x2"]-r["x1"]) == 560:
                pinvias[r["net"]].append((r["x1"], r["y1"]))
    for k, v in sorted(vcnt.items()):
        print(f"  {k}: {v}")
    print(f"pin-width (560dbu) metal4-metal5 vias: VDD={len(pinvias['VDD'])} VSS={len(pinvias['VSS'])}")
    if pinvias:
        xs = sorted(set(x for net in pinvias.values() for x, y in net))
        dx = [b-a for a, b in zip(xs, xs[1:])]
        print(f"  pin via x-positions: n={len(xs)} pitch_dbu={Counter(dx).most_common(3)}")
        print(f"  first x rel macro: {(xs[0]-mb[0])/dbu:.3f}um")

if __name__ == "__main__":
    main()
