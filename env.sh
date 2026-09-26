#!/bin/bash
# pgrev environment: OpenROAD (conda, litex-hub 2022 build) + Yosys (oss-cad-suite)
source ~/pgrev/tools/oss-cad-suite/environment
export OPENROAD_EXE=~/pgrev/tools/eda/bin/openroad
export YOSYS_EXE=~/pgrev/tools/oss-cad-suite/bin/yosys
export PATH=~/pgrev/tools/eda/bin:$PATH
