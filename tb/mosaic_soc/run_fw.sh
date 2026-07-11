#!/bin/bash
# MOSAIC full-SoC PRODUCTION-FIRMWARE simulation (Verilator).
#
# Builds the COMPLETE PoC SoC from the default config (mosaic.yaml: 1 cv32e20
# TITAN + 2 fazyrv ATLAS + 4 serv NANO + TDU + system_bus + peripherals +
# debug) and runs the production C firmware (sw/firmware -> mosaic_fw.hex):
#   - TITAN boots from the boot ROM into titan_main.c: configures the TDU
#     (DYNAMIC mode, CPI estimates), queues all 6 task descriptors in the TDU
#     FIFO, then arms the wake mask and releases every worker with one
#     WAKE_REQ pulse (push-all-then-wake: a woken worker reaches TASK_POP in
#     a few instructions, so descriptors must be queued first).
#   - Each worker (atlas_worker.S / nano_worker.S) pops a UNIQUE descriptor
#     from TDU TASK_POP (hardware-atomic dequeue), runs its workload (MAC /
#     CRC loop), stores its result at 0x3100+slot*4 and its sentinel at
#     0x3000+slot*4 — slot = the popped descriptor's core_hint, so completion
#     reporting is correct no matter which worker pops which task.
#   - TITAN polls the 6 sentinel slots and signals soc_ctrl exit 0.
# So "EXIT SUCCESS" proves the full production stack: C runtime + TDU driver +
# task dispatch + 6 heterogeneous workers + completion protocol, in the real SoC.
#
# Needs: Verilator + a RISC-V GCC (rv32i, ld-linked, no multilib).
# Usage: tb/mosaic_soc/run_fw.sh   (MOSAIC_CFG / RISCV_TC override)
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
cd "$REPO"
TC="${RISCV_TC:-/opt/riscv32-gnu-toolchain-elf-bin/bin/riscv32-unknown-elf}"
# Pin a stable Verilator release: the oss-cad-suite nightly (5.047 devel "(mod)")
# DFG optimizer miscompiles cv32e40x's load-use-hazard halt (bug 21) — a branch
# consumes the load's address-phase ALU result. VERILATOR_PIN=/path overrides;
# VERILATOR_PIN= (empty) falls back to PATH's verilator.
VPIN="${VERILATOR_PIN-/mnt/fda14e36-49c8-4508-a4b0-f37189565cd9/tools/verilator-5.050}"
if [ -n "$VPIN" ] && [ -x "$VPIN/usr/bin/verilator" ]; then
  export PATH="$VPIN/usr/bin:$PATH" VERILATOR_ROOT="$VPIN/usr/share/verilator"
fi
MOSAIC_CFG="${MOSAIC_CFG:-mosaic.yaml}"
OBJ="$HERE/obj_dir_fw"

echo "### [1/4] generating RTL ($MOSAIC_CFG: 1 TITAN + 2 ATLAS + 4 NANO) ..."
TPLS=$(find . \( -path './hw/vendor/*' ! -path './hw/vendor/xheep' ! -path './hw/vendor/xheep/*' \
    -o -path './util/*' ! -path './util/profile' ! -path './util/profile/*' \
    -o -path './test/*' -o -path './refs/*' \) -prune -o -name '*.tpl' -print)
python3 util/xheep_gen/mcu_gen.py --mosaic_config "$MOSAIC_CFG" --base_config configs/general.hjson \
    --pads_cfg configs/pad_cfg.py --outtpl "$TPLS" --externaltpl "" >/dev/null 2>&1 || { echo "RTL gen failed"; exit 1; }
# FuseSoC setup regenerates the config-dependent regtool outputs (power
# manager banks etc.) — skipping it leaves stale per-bank RTL behind.
echo "###       running FuseSoC setup (register generators + filelist) ..."
RISCV_XHEEP="${RISCV_XHEEP:-$(dirname "$(dirname "$TC")")}" \
COMPILER_PREFIX="${COMPILER_PREFIX:-$(basename "$TC" | sed 's/elf$//')}" \
    scripts/fusesoc-setup.sh > "$HERE/fusesoc-setup.log" 2>&1 \
    || { echo "FuseSoC setup failed — see $HERE/fusesoc-setup.log"; exit 1; }

echo "### [2/4] building the production firmware (sw/firmware, rv32i) ..."
make -C sw/firmware clean >/dev/null
make -C sw/firmware RISCV_TC="$TC" > "$HERE/fw-build.log" 2>&1 \
    || { echo "firmware build failed — see $HERE/fw-build.log"; exit 1; }
echo "    firmware: sw/firmware/build/mosaic_fw.hex"

echo "### [3/4] building the full-SoC Verilator model (this takes a few minutes) ..."
rm -rf "$OBJ"
python3 "$HERE/gen_filelist.py" "$REPO" > "$HERE/soc.f" || { echo "filelist gen failed"; exit 1; }
verilator --binary -j 0 --top-module tb_top \
    --Mdir "$OBJ" -o Vtb_top --timescale 1ns/1ps \
    -GUSE_EXTERNAL_DEVICE_EXAMPLE=1 -GJTAG_DPI=0 \
    -f "$HERE/soc.f" > "$HERE/build-fw.log" 2>&1
[ -x "$OBJ/Vtb_top" ] || { echo "### BUILD FAILED (no Vtb_top) — see $HERE/build-fw.log"; grep -iE "%Error|error:|undefined" "$HERE/build-fw.log" | head; exit 1; }

echo "### [4/4] running the simulation (production firmware) ..."
# 2M-cycle cap: the serv (bit-serial) CRC loops dominate; the run exits at
# ~300k cycles when TITAN's completion poll sees all six sentinels.
"$OBJ/Vtb_top" +firmware="$REPO/sw/firmware/build/mosaic_fw.hex" +boot_sel=0 \
    +maxcycles=2000000 +verbose 2>&1 | tee "$HERE/sim-fw.log" | tail -20
echo ""
if grep -q "EXIT SUCCESS" "$HERE/sim-fw.log"; then
  echo "### RESULT: EXIT SUCCESS — production firmware ran on the full 7-hart SoC ✓"
else
  echo "### RESULT: no EXIT SUCCESS (see $HERE/sim-fw.log)"
fi
