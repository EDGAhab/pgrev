#!/bin/bash
# Phase 7: build current OpenROAD master. Run AFTER the clone completes.
# Logs to phase7/logs/build.log
set -u
PH7=~/pgrev/phase7
LOG=$PH7/logs/build.log
SRC=$PH7/openroad-src

[ -f "$SRC/CMakeLists.txt" ] || { echo "clone not complete"; exit 1; }

cd $SRC
git submodule status 2>&1 | head -30 >> $LOG

mkdir -p build && cd build
echo "[$(date)] cmake configure" | tee -a $LOG
ORTOOLS=$HOME/pgrev/phase7/third-party/ortools
CUDD=$HOME/pgrev/phase7/third-party/cudd/cudd-3.0.0
DEPS=$HOME/pgrev/phase7/deps
cmake .. -DCMAKE_BUILD_TYPE=RELEASE -DSWIG_EXECUTABLE=$DEPS/bin/swig \
  -Dortools_ROOT=$ORTOOLS -Dabsl_ROOT=$ORTOOLS -DCUDD_DIR=$CUDD \
  -Dspdlog_ROOT=$DEPS -DBUILD_PYTHON=OFF -DLINK_TIME_OPTIMIZATION=OFF \
  -DCMAKE_CXX_FLAGS="-I$DEPS/include" >> $LOG 2>&1
[ $? -ne 0 ] && { echo "CMAKE FAILED"; exit 2; }
echo "[$(date)] make -j2" | tee -a $LOG
make -j2 >> $LOG 2>&1
echo "[$(date)] make exit: $?" | tee -a $LOG
ls -la src/openroad 2>/dev/null | tee -a $LOG
