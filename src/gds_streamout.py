#!/usr/bin/env python3
"""expB (rev5): stream out flat ODB swire boxes as a genuine GDSII file.

Reads the box CSV from src/dump_all_geo.tcl and writes standard GDSII
(BOUNDARY records on (layer, datatype), integer dbu coordinates).
Deliberately emits NO net names and NO kind tags -- the GDSII contains
only (layer, datatype) polygons, which is exactly the untrusted-foundry
threat model assumption set (cf. rev3-ws1-unlabeled.md B1).

With --with-text, also emits TEXT records carrying net names on the
label datatypes, mimicking what ORFS's klayout stream-out would produce
(sky130hd.lyt sets <produce-net-names>true</produce-net-names>). The
attack-side reader (expB_unlabeled.py) strips ALL TEXT records before
extraction, so the attack input is the post-strip polygon set either way.

Layer map: authoritative from
  tools/OpenROAD-flow-scripts/flow/platforms/sky130hd/sky130hd.lyt
  met1 68/20, via 68/44, met2 69/20, via2 69/44, met3 70/20,
  via3 70/44, met4 71/20, via4 71/44, met5 72/20.
ODB tech layer "via" is the cut between met1/met2 (ORFS tech LEF naming).

UNITS: user unit 1 um (=1e-6 m), 1 dbu = 0.001 um = 1 nm, matching the
ODB's 1000 dbu/um, so integer coordinates are preserved exactly.

Usage:
  python3 src/gds_streamout.py --csv <boxes.csv> --gds <out.gds> [--with-text]
"""
import argparse, csv, math, struct, time

# ODB tech-layer name -> (gds layer, datatype), drawing purpose
LAYER_MAP = {
    "met1": (68, 20), "via":  (68, 44),
    "met2": (69, 20), "via2": (69, 44),
    "met3": (70, 20), "via3": (70, 44),
    "met4": (71, 20), "via4": (71, 44),
    "met5": (72, 20),
}
# label datatypes for the --with-text mimicry (metN.label from the .lyt)
LABEL_DT = {"met1": 5, "met2": 5, "met3": 5, "met4": 5, "met5": 5}

def gds_real(x):
    """Encode a float as an 8-byte GDSII real."""
    if x == 0.0:
        return b"\x00" * 8
    sign = 0
    if x < 0:
        sign = 0x80
        x = -x
    exp = math.floor(math.log(x, 16)) + 1
    m = x / (16.0 ** exp)
    while m >= 1.0:
        m /= 16.0; exp += 1
    while m < 1.0 / 16.0:
        m *= 16.0; exp -= 1
    mant = int(round(m * 16 ** 14))
    if mant >= 16 ** 14:
        mant >>= 4; exp += 1
    return bytes([sign | (exp + 64)]) + mant.to_bytes(7, "big")

def rec(rtype, dtype, data):
    return struct.pack(">HBB", 4 + len(data), rtype, dtype) + data

def ascii_str(s):
    b = s.encode("ascii")
    if len(b) % 2:
        b += b"\x00"
    return b

def timestamps():
    t = time.localtime()
    v = [t.tm_year % 100, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec] * 2
    return struct.pack(">12h", *v)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--gds", required=True)
    ap.add_argument("--with-text", action="store_true",
                    help="mimic klayout net-name TEXT labels (stripped by reader)")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(a.csv)))
    boxes = []
    for r in rows:
        x1, y1, x2, y2 = int(r["x1"]), int(r["y1"]), int(r["x2"]), int(r["y2"])
        if r["via_name"]:
            # via: cut layer derived from bottom metal (via->met1, via2->met2, ...)
            lay = {"met1": "via", "met2": "via2", "met3": "via3",
                   "met4": "via4"}[r["via_bot"]]
        else:
            lay = r["layer"]
        if lay not in LAYER_MAP:
            raise RuntimeError(f"no GDS mapping for ODB layer {lay!r}")
        boxes.append((lay, x1, y1, x2, y2, r["net"]))

    out = bytearray()
    out += rec(0x00, 0x01, struct.pack(">h", 600))          # HEADER
    out += rec(0x01, 0x01, timestamps())                    # BGNLIB
    out += rec(0x02, 0x06, ascii_str("pgrev"))              # LIBNAME
    out += rec(0x03, 0x05, gds_real(0.001) + gds_real(1e-6))  # UNITS
    out += rec(0x05, 0x01, timestamps())                    # BGNSTR
    out += rec(0x06, 0x06, ascii_str("gcd_top"))            # STRNAME

    n_text = 0
    seen_text = set()
    for lay, x1, y1, x2, y2, net in boxes:
        gl, dt = LAYER_MAP[lay]
        out += rec(0x08, 0x00, b"")                         # BOUNDARY
        out += rec(0x0D, 0x02, struct.pack(">h", gl))       # LAYER
        out += rec(0x0E, 0x02, struct.pack(">h", dt))       # DATATYPE
        out += rec(0x10, 0x03, struct.pack(">10i",
            x1, y1, x1, y2, x2, y2, x2, y1, x1, y1))         # XY (closed rect)
        out += rec(0x11, 0x00, b"")                         # ENDEL
        if a.with_text and lay in LABEL_DT and (net, lay) not in seen_text:
            seen_text.add((net, lay))
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            out += rec(0x0C, 0x00, b"")                     # TEXT
            out += rec(0x0D, 0x02, struct.pack(">h", gl))   # LAYER
            out += rec(0x16, 0x02, struct.pack(">h", 0))    # TEXTTYPE
            out += rec(0x17, 0x01, struct.pack(">h", 0))    # PRESENTATION
            out += rec(0x10, 0x03, struct.pack(">2i", cx, cy))  # XY
            out += rec(0x19, 0x06, ascii_str(net))          # STRING (net name!)
            out += rec(0x11, 0x00, b"")                     # ENDEL
            n_text += 1

    out += rec(0x07, 0x00, b"")                             # ENDSTR
    out += rec(0x04, 0x00, b"")                             # ENDLIB

    with open(a.gds, "wb") as f:
        f.write(out)
    print(f"wrote {a.gds}: {len(boxes)} BOUNDARY, {n_text} TEXT, "
          f"{len(out)} bytes")

if __name__ == "__main__":
    main()
