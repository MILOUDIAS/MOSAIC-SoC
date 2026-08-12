#!/bin/bash
# Gate-level simulation of the Chipathon Block A macro.
#
# Runs the POST-PLACE-AND-ROUTE netlist -- the gates that are in the GDS -- with
# the PDK's own cell models, booting XIP from a behavioural QSPI flash and
# reporting only through the 22 pins the integrator bonds. See gls_tb.sv.
#
# Icarus is used rather than Verilator: these models are UDP-based, which
# Verilator cannot simulate at all.
#
# SDF NOTE: timing-annotated GLS is NOT possible with these models under Icarus.
# Compiling them with -gspecify fails --
#     sorry: ifnone with an edge-sensitive path is not supported
# -- so the models are compiled -DFUNCTIONAL, which drops the specify blocks and
# with them the paths SDF would annotate. Timing-annotated GLS on GF180 needs a
# simulator that supports ifnone edge paths. What runs here is a ZERO-DELAY
# functional check of the routed netlist, which is still the thing that catches
# synthesis/P&R mis-implementation; it is not a timing check. STA already covers
# timing at nine corners.
#
# Usage:
#   ./run_gls.sh                 zero-delay functional GLS on the routed netlist
#   GLS_NETLIST=<nl.v> ./run_gls.sh     post-synthesis netlist instead
#   GLS_FIRMWARE=<hex> ./run_gls.sh     a different flash image
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
cd "$REPO"

RUN="${GLS_RUN:-$REPO/flow/librelane/experimental/runs/blocka_signoff}"
PDK="$REPO/flow/librelane/gf180mcu/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/verilog"
# Post-PnR netlist by default: that is what the GDS contains, fill and antenna
# cells included. NL (post-synthesis) is available via GLS_NETLIST for
# comparison, but it is not what gets manufactured.
NETLIST="${GLS_NETLIST:-$RUN/final/pnl/mosaic_block_a.pnl.v}"
CORNER="${2:-max_ss_125C_4v50}"
MAXCYCLES="${GLS_MAXCYCLES:-2000000}"

SDF_ARG=""
if [ "${1:-}" = "--sdf" ]; then
  echo "ERROR: SDF annotation is not supported with these models under Icarus." >&2
  echo "       The GF180 cell models use ifnone with edge-sensitive paths, which" >&2
  echo "       iverilog rejects (-gspecify), so they are compiled -DFUNCTIONAL and" >&2
  echo "       carry no annotatable timing paths. Refusing rather than running a" >&2
  echo "       zero-delay simulation and calling it timing-annotated." >&2
  exit 2
fi

[ -f "$NETLIST" ] || { echo "ERROR: netlist missing: $NETLIST" >&2; exit 2; }

# Firmware: the topology-generic liveness image. It boots the TITAN from the
# boot ROM, executes XIP from flash, wakes the worker through the TDU and writes
# the exit register -- i.e. it exercises the whole part through the pins.
FW="${GLS_FIRMWARE:-}"
if [ -z "$FW" ]; then
  FW="$(ls -t "$REPO"/build/mosaic/mosaic_tapeout_ultra-*/generated/generic_fw/generic.hex 2>/dev/null | head -1)"
fi
[ -n "$FW" ] && [ -f "$FW" ] || { echo "ERROR: no firmware hex. Run tb/mosaic_soc/run_generic.sh first, or set GLS_FIRMWARE." >&2; exit 2; }

# The flash model comes from the FuseSoC staging tree.
FLASH="$(ls -t "$REPO"/build/mosaic/mosaic_tapeout_ultra-*/runs/fusesoc.*/build/src/x-heep__tb-utils_0/yosys_spiflash.sv 2>/dev/null | head -1)"
[ -n "$FLASH" ] && [ -f "$FLASH" ] || { echo "ERROR: spiflash model not found; run a FuseSoC setup first." >&2; exit 2; }

OBJ="$HERE/obj"
mkdir -p "$OBJ"
echo "### netlist : $(basename "$NETLIST") ($(du -h "$NETLIST" | cut -f1))"
echo "### firmware: $FW"
echo "### models  : $(basename "$PDK")/gf180mcu_fd_sc_mcu7t5v0.v + primitives.v"

# USE_POWER_PINS: the netlist connects .VDD/.VNW/.VPW/.VSS on every instance, so
# the models must expose them or every instantiation is a port mismatch.
iverilog -g2012 -DUSE_POWER_PINS -DFUNCTIONAL -I"$HERE" \
    -o "$OBJ/gls.vvp" \
    -s gls_tb \
    "$HERE/gls_tb.sv" \
    "$NETLIST" \
    "$FLASH" \
    "$PDK/primitives.v" \
    "$PDK/gf180mcu_fd_sc_mcu7t5v0.v" \
    2> "$HERE/compile.log"
RC=$?
if [ $RC -ne 0 ] || [ ! -f "$OBJ/gls.vvp" ]; then
  echo "### COMPILE FAILED — see $HERE/compile.log"
  tail -20 "$HERE/compile.log"
  exit 1
fi
echo "### compiled ($(grep -c . "$HERE/compile.log" 2>/dev/null) warnings)"

# shellcheck disable=SC2086
vvp "$OBJ/gls.vvp" +firmware="$FW" +maxcycles="$MAXCYCLES" $SDF_ARG \
    2>&1 | tee "$HERE/sim-gls.log" | grep -vE "^\[GLS\] [0-9]+ cycles" | tail -25
SIM_RC=${PIPESTATUS[0]}

echo
if [ "$SIM_RC" -eq 0 ] && grep -q "EXIT SUCCESS" "$HERE/sim-gls.log"; then
  echo "### RESULT: gate-level simulation PASSED"
else
  echo "### RESULT: gate-level simulation FAILED (see $HERE/sim-gls.log)"
  exit 1
fi
