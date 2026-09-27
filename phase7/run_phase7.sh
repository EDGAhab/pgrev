#!/bin/bash
# Phase 7 runbook: generate -> extract -> infer -> round-trip, for one tag.
# Usage: ./run_phase7.sh <tag>   (tag dir: phase7/data/<tag>, def at phase7/data/<tag>/floorplan.def)
# Env required: OPENROAD_EXE (built binary)
set -u
TAG=${1:?usage: run_phase7.sh <tag>}
PH7=~/pgrev/phase7
D=$PH7/data/$TAG
PDK=~/pgrev/tools/OpenROAD-flow-scripts/flow/platforms/sky130hd/lef
OPENROAD_EXE=${OPENROAD_EXE:?set OPENROAD_EXE}
mkdir -p $D

echo "=== [1/4] generate (truth tcl)"
TLEF=$PDK/sky130_fd_sc_hd.tlef TECH_LEF=$PDK/sky130_fd_sc_hd_merged.lef \
  DEF_IN=$D/floorplan.def ODB_OUT=$D/truth.odb \
  $OPENROAD_EXE -exit $PH7/gen_pdn.tcl 2>&1 | tail -5

echo "=== [2/4] extract"
OPENROAD_EXE=$OPENROAD_EXE python3 $PH7/extract_cpp.py \
  --odb $D/truth.odb --def $D/floorplan.def --outdir $D --tag $TAG

echo "=== [3/4] infer"
python3 $PH7/pg_infer_cpp.py --tag $TAG
echo "--- inferred tcl ---"; cat $D/pdn_inferred.tcl

echo "=== [4/4] round-trip: regenerate from inferred tcl"
cat > $D/regen.tcl <<EOF
read_lef $PDK/sky130_fd_sc_hd.tlef
read_lef $PDK/sky130_fd_sc_hd_merged.lef
read_def $D/floorplan.def
add_global_connection -net VDD -pin_pattern VPWR -power
add_global_connection -net VDD -pin_pattern VPB -power
add_global_connection -net VSS -pin_pattern VGND -ground
add_global_connection -net VSS -pin_pattern VNB -ground
source $D/pdn_inferred.tcl
write_db $D/regen.odb
EOF
$OPENROAD_EXE -exit $D/regen.tcl 2>&1 | tail -3

echo "=== [5/5] extract regen + compare"
mkdir -p $D/regen && OPENROAD_EXE=$OPENROAD_EXE python3 $PH7/extract_cpp.py \
  --odb $D/regen.odb --def $D/floorplan.def --outdir $D/regen --tag ${TAG}_regen
python3 - "$D/pg_shapes.csv" "$D/regen/pg_shapes.csv" <<'EOF'
import csv, sys
def load(p):
    rows = list(csv.DictReader(open(p)))
    ws = sorted((r['net'],r['layer'],r['shape'],int(r['x1']),int(r['y1']),int(r['x2']),int(r['y2'])) for r in rows if r['kind']=='wire')
    vs = sorted((r['net'],r['layer'],r['shape'],int(r['x1']),int(r['y1']),int(r['x2']),int(r['y2']),r['via_name']) for r in rows if r['kind']=='via')
    return ws, vs
a = load(sys.argv[1]); b = load(sys.argv[2])
print(f"truth: wires={len(a[0])} vias={len(a[1])} | regen: wires={len(b[0])} vias={len(b[1])}")
dw = [x for x in a[0] if x not in b[0]] + [x for x in b[0] if x not in a[0]]
dv = [x for x in a[1] if x not in b[1]] + [x for x in b[1] if x not in a[1]]
print(f"wire diffs: {len(dw)} | via diffs: {len(dv)}")
for x in dw[:5]: print(" WIRE-DIFF", x)
for x in dv[:5]: print(" VIA-DIFF", x)
print("ROUND_TRIP:", "PASS" if not dw and not dv else "FAIL")
EOF
