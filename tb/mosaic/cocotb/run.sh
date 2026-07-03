#!/bin/bash
# Build + run the MOSAIC multi-core cocotb harness (cocotb + Verilator).
#
#   1. Generate the multi-core SoC RTL for configs/mosaic_sim.yaml (RTL step only).
#   2. Run the cocotb testbench (test_mosaic.py) against the generated cpu_subsystem.
#   3. Regenerate the default PoC config so the working tree is left as found.
#
# Requires: cocotb + verilator (both in oss-cad-suite). No RISC-V GCC needed.
# Usage: tb/mosaic/cocotb/run.sh

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
cd "$REPO"
PY="${PYTHON:-python3}"

TPLS=$(find . \( -path './hw/vendor/*' ! -path './hw/vendor/xheep' ! -path './hw/vendor/xheep/*' \
    -o -path './util/*' ! -path './util/profile' ! -path './util/profile/*' \
    -o -path './test/*' -o -path './refs/*' \) -prune -o -name '*.tpl' -print)

gen () {  # $1 = mosaic config
  $PY util/xheep_gen/mcu_gen.py --mosaic_config "$1" \
      --base_config configs/general.hjson --pads_cfg configs/pad_cfg.py \
      --outtpl "$TPLS" --externaltpl "" >/dev/null
}

echo "### [1/3] generating RTL for configs/mosaic_sim.yaml ..."
gen configs/mosaic_sim.yaml

echo "### [2/3] running cocotb (SIM=verilator) ..."
set +e
make -C "$HERE" SIM=verilator
RC=$?
set -e

echo "### [3/3] restoring default PoC config (mosaic.yaml) ..."
gen mosaic.yaml

exit $RC
