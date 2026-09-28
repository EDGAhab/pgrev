#!/usr/bin/env python3
"""rev6 expA: pure-stdlib GDSII reader that provably strips ALL cell/name labels.

Reviewer question (round 6): "GDS cell names are labels themselves -- report
the result with cell names stripped, geometry only."

This module parses the raw GDSII byte stream itself (no third-party library),
so the name-stripping point is explicit and auditable:

  STRIPPED (counted + logged in the audit trail, never returned):
    LIBNAME, STRNAME, SNAME (cell reference names), STRING (TEXT payload),
    PROPATTR / PROPVALUE.
  KEPT:
    BOUNDARY elements' LAYER + DATATYPE + XY only.
  FAIL CLOSED:
    SREF / AREF (hierarchical cell references) raise -- the experimental GDS
    is flat, so no reference expansion is needed; silently mishandling a
    hierarchy would be worse than refusing it.

Guarantees:
  - the returned rects contain no GDS-derived strings: every value is int
    (the ODB-layer labels are applied later by the caller from the attacker's
    own (layer, datatype) -> layer table, i.e. process-stack knowledge, not
    from any GDS name);
  - the audit trail lists every discarded name value, proving what was dropped.

Also provides `mutated_copy()`: rewrites the STRNAME/LIBNAME records with
adversarial decoy names (e.g. a via-cell-like "via_340x340_LEAK"). Re-running
extraction on the mutated file must yield byte-identical rects -- the direct
proof that the attack input is name-independent.
"""
import struct

# record types we care about
HEADER, BGNLIB, LIBNAME, UNITS, ENDLIB = 0x00, 0x01, 0x02, 0x03, 0x04
BGNSTR, STRNAME, ENDSTR = 0x05, 0x06, 0x07
BOUNDARY, SREF, AREF, TEXT = 0x08, 0x0A, 0x0B, 0x0C
LAYER, DATATYPE, XY, ENDEL = 0x0D, 0x0E, 0x10, 0x11
SNAME = 0x12
STRING = 0x19
PROPATTR, PROPVALUE = 0x2B, 0x2C

DTYPE_NONE, DTYPE_I2, DTYPE_I4, DTYPE_ASCII = 0x00, 0x02, 0x03, 0x06

# name-bearing records: stripped, counted, logged -- never returned
NAME_RECORDS = {LIBNAME: "LIBNAME", STRNAME: "STRNAME", SNAME: "SNAME",
                STRING: "STRING", PROPVALUE: "PROPVALUE"}


def _ascii(data):
    return data.decode("ascii").rstrip("\x00")


def parse_records(buf):
    """Yield (rtype, dtype, data) for every record in the byte stream."""
    off, n = 0, len(buf)
    while off < n:
        if off + 4 > n:
            raise ValueError(f"truncated record header at offset {off}")
        reclen, rtype, dtype = struct.unpack_from(">HBB", buf, off)
        if reclen < 4 or off + reclen > n:
            raise ValueError(f"bad record length {reclen} at offset {off}")
        yield rtype, dtype, bytes(buf[off + 4: off + reclen])
        off += reclen


def read_flat_gds(path):
    """Extract BOUNDARY rects; strip every name. Returns (rects, audit).

    rects: [{"gds_layer": int, "gds_datatype": int,
             "x1": int, "y1": int, "x2": int, "y2": int}]  (ints only)
    audit: {"n_structures": int, "n_boundary": int, "n_text": int,
            "n_path": int, "discarded_names": [(record, value)], ...}
    """
    with open(path, "rb") as f:
        buf = f.read()
    audit = {"n_structures": 0, "n_boundary": 0, "n_text": 0, "n_path": 0,
             "discarded_names": []}
    rects = []
    in_el = None          # "BOUNDARY" while inside one
    lay = dtyp = xy = None
    for rtype, dtype, data in parse_records(buf):
        if rtype == BGNSTR:
            audit["n_structures"] += 1
            in_el = None
        elif rtype in NAME_RECORDS:
            assert dtype == DTYPE_ASCII, f"{NAME_RECORDS[rtype]} not ascii"
            audit["discarded_names"].append((NAME_RECORDS[rtype], _ascii(data)))
        elif rtype == SREF or rtype == AREF:
            raise RuntimeError(
                f"hierarchical {'SREF' if rtype == SREF else 'AREF'} found: "
                "name-stripping reader refuses hierarchical GDS (fail closed); "
                "reference expansion with name stripping is not implemented")
        elif rtype == TEXT:
            audit["n_text"] += 1
            in_el = None
        elif rtype == 0x09:  # PATH
            audit["n_path"] += 1
            in_el = None
        elif rtype == BOUNDARY:
            in_el, lay, dtyp, xy = "BOUNDARY", None, None, None
        elif rtype == LAYER and in_el == "BOUNDARY":
            (lay,) = struct.unpack(">h", data)
        elif rtype == DATATYPE and in_el == "BOUNDARY":
            (dtyp,) = struct.unpack(">h", data)
        elif rtype == XY and in_el == "BOUNDARY":
            pts = struct.unpack(">" + "i" * (len(data) // 4), data)
            xy = list(zip(pts[0::2], pts[1::2]))
        elif rtype == ENDEL:
            if in_el == "BOUNDARY":
                assert lay is not None and dtyp is not None and xy, \
                    "BOUNDARY without LAYER/DATATYPE/XY"
                xs = [p[0] for p in xy]; ys = [p[1] for p in xy]
                x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
                assert x2 > x1 and y2 > y1, f"degenerate {(lay, dtyp)}"
                rects.append({"gds_layer": lay, "gds_datatype": dtyp,
                              "x1": x1, "y1": y1, "x2": x2, "y2": y2})
                audit["n_boundary"] += 1
            in_el = None
    # HARD GUARANTEE: attack input carries no GDS-derived strings at all
    assert all(isinstance(v, int) for r in rects for v in r.values()), \
        "non-integer leaked into attack input"
    return rects, audit


def mutated_copy(path, new_names):
    """Return GDS bytes with name records replaced by decoys.

    new_names: {"STRNAME": "...", "LIBNAME": "..."} -- adversarial decoy
    names (e.g. via-cell-like strings). Used to prove extraction output is
    name-independent: read_flat_gds(mutated) must equal read_flat_gds(orig).
    """
    with open(path, "rb") as f:
        buf = bytearray(f.read())
    out, off, replaced = bytearray(), 0, []
    n = len(buf)
    while off < n:
        reclen, rtype, dtype = struct.unpack_from(">HBB", buf, off)
        data = bytes(buf[off + 4: off + reclen])
        key = NAME_RECORDS.get(rtype)
        if key in new_names and dtype == DTYPE_ASCII:
            b = new_names[key].encode("ascii")
            if len(b) % 2:
                b += b"\x00"
            data = b
            reclen = 4 + len(data)
            replaced.append(key)
        out += struct.pack(">HBB", reclen, rtype, dtype) + data
        off += (struct.unpack_from(">H", buf, off)[0])
    assert replaced, "no name record found to mutate"
    return bytes(out), replaced


if __name__ == "__main__":
    import sys
    rects, audit = read_flat_gds(sys.argv[1])
    print(f"structures={audit['n_structures']} boundary={audit['n_boundary']} "
          f"text={audit['n_text']} path={audit['n_path']}")
    print("discarded names:")
    for rec, val in audit["discarded_names"]:
        print(f"  {rec}: {val!r}")
    print(f"rects={len(rects)} (all-int check passed)")
