#!/bin/bash
# Phase 5: round-trip -- re-run PDN step with inferred cfg, compare geometry.
# Usage: src/roundtrip.sh <tag> <design_config> <plat> <design>
# Outputs: /tmp/rt/<tag>/2_6_floorplan_pdn.odb (fresh pdngen run)
set -e
TAG=$1; CFG=$2; PLAT=$3; DESIGN=$4
source ~/pgrev/env.sh
FLOW=~/pgrev/tools/OpenROAD-flow-scripts/flow
ORIG=$FLOW/results/$PLAT/$DESIGN/base
RT=/tmp/rt/$TAG
mkdir -p $RT
ln -sf $ORIG/2_5_floorplan_tapcell.odb $RT/
ln -sf $ORIG/1_synth.sdc $RT/
cd $FLOW
python3 ~/pgrev/src/run_with_mem.py ~/pgrev/logs/${TAG}_roundtrip.log \
  make SHELL=/bin/bash DESIGN_CONFIG=$CFG \
    RESULTS_DIR=$RT LOG_DIR=$RT \
    PDN_CFG=~/pgrev/data/$TAG/pdn_inferred.cfg \
    $RT/2_6_floorplan_pdn.odb
echo "ROUNDTRIP_DONE $TAG"
