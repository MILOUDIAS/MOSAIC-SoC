#!/bin/bash
# tb/tl_obi/run.sh — self-checking unit TB for the TileLink->OBI bridge
# (xheep_tilelink_to_obi, used by the Rocket/BOOM SCI wrappers).
#
# Pass criterion: "ALL TESTS PASSED" on stdout.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)

# Pinned stable Verilator (bug 21: nightly DFG miscompiles cv32e40x).
# VERILATOR_PIN=/path overrides; VERILATOR_PIN= (empty) uses PATH's verilator.
VPIN="${VERILATOR_PIN-/mnt/fda14e36-49c8-4508-a4b0-f37189565cd9/tools/verilator-5.050}"
if [ -n "$VPIN" ] && [ -x "$VPIN/usr/bin/verilator" ]; then
  export PATH="$VPIN/usr/bin:$PATH" VERILATOR_ROOT="$VPIN/usr/share/verilator"
fi
echo "verilator: $(command -v verilator) [$(verilator --version)]"

cd "$REPO"
rm -rf build/tl_obi_tb_obj
verilator --binary -j 0 --timescale 1ns/1ps --top-module tl_obi_tb \
  --Mdir build/tl_obi_tb_obj -o Vtl_obi_tb \
  hw/core-v-mini-mcu/include/obi_pkg.sv \
  hw/vendor/mosaic/tl_obi/xheep_tilelink_to_obi.sv \
  tb/tl_obi/tl_obi_tb.sv

build/tl_obi_tb_obj/Vtl_obi_tb
