#!/bin/bash
# Build + run the iDMA cocotb tests (cocotb + Verilator), both levels:
#   per-block : iDMA + dual-port memory          (TOPLEVEL=idma_tb_top)
#   SoC-level : iDMA + shared, arbitrated memory  (TOPLEVEL=idma_soc_tb_top)
# Requires cocotb + verilator. No RTL generation needed (iDMA is static RTL).
# Usage: tb/idma/cocotb/run.sh

set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

rc=0
for top in idma_tb_top idma_soc_tb_top; do
  echo "### ===== iDMA cocotb: TOPLEVEL=$top ====="
  rm -rf sim_build results.xml __pycache__
  make SIM=verilator TOPLEVEL="$top" || rc=1
done
exit $rc
