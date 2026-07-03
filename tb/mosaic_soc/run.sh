#!/bin/bash
# MOSAIC full-SoC functional simulation (Verilator) — TDU wake-and-run demo.
#
# Builds the COMPLETE multi-core SoC (x-heep testharness wrapping the generated
# core_v_mini_mcu) for the 3-core wake demo (configs/mosaic_wake_demo.yaml:
# 1 cv32e20 TITAN + 1 fazyrv ATLAS + 1 serv NANO + TDU + system_bus + peripherals
# + debug) and runs three programs:
#   - TITAN boots from the boot ROM, writes its sentinel, then WAKES the workers
#     via the TDU (store 0x6 to WAKE_REQ @ 0x200A000C), waits for both worker
#     sentinels, and signals EXIT SUCCESS.
#   - ATLAS (hart 1) and NANO (hart 2) boot DORMANT and run their own programs
#     (at boot addresses 0x1000 / 0x2000) only once woken, each writing a unique
#     sentinel through the shared system bus.
# So "EXIT SUCCESS" proves the full wake-and-run loop: TITAN -> TDU -> core_wake ->
# worker fetch -> execute, all in the real SoC.
#
# Needs: Verilator + a RISC-V GCC (compile-only; ld-linked, no multilib).
# Usage: tb/mosaic_soc/run.sh   (MOSAIC_CFG overrides the config)
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
cd "$REPO"
TC="${RISCV_TC:-/opt/riscv32-gnu-toolchain-elf-bin/bin/riscv32-unknown-elf}"
MOSAIC_CFG="${MOSAIC_CFG:-configs/mosaic_wake_demo.yaml}"
OBJ="$HERE/obj_dir"

echo "### [1/4] generating RTL ($MOSAIC_CFG: 1 TITAN + 1 ATLAS + 1 NANO) ..."
TPLS=$(find . \( -path './hw/vendor/*' ! -path './hw/vendor/xheep' ! -path './hw/vendor/xheep/*' \
    -o -path './util/*' ! -path './util/profile' ! -path './util/profile/*' \
    -o -path './test/*' -o -path './refs/*' \) -prune -o -name '*.tpl' -print)
python3 util/xheep_gen/mcu_gen.py --mosaic_config "$MOSAIC_CFG" --base_config configs/general.hjson \
    --pads_cfg configs/pad_cfg.py --outtpl "$TPLS" --externaltpl "" >/dev/null 2>&1 || { echo "RTL gen failed"; exit 1; }

echo "### [2/4] assembling the 3 programs (TITAN + ATLAS + NANO, rv32i, ld-linked) ..."
# All three assembled as base rv32i (no compressed / no M): the serial cores
# (fazyrv RVC=NONE, serv COMPRESSED=0) can't decode compressed insns, and cve2
# runs rv32i fine. Linked into one ELF (sections at 0x180/0x1000/0x2000).
( cd "$HERE/prog"
  for s in start atlas nano; do
    $TC-gcc -march=rv32i -mabi=ilp32 -nostdlib -ffreestanding -c "$s.S" -o "$s.o" || exit 1
  done
  $TC-ld -T link.ld start.o atlas.o nano.o -o prog.elf || exit 1
  $TC-objcopy -O verilog prog.elf prog.hex || exit 1 ) || { echo "program build failed"; exit 1; }
echo "    firmware: $HERE/prog/prog.hex"

echo "### [3/4] building the full-SoC Verilator model (this takes a few minutes) ..."
rm -rf "$OBJ"
python3 "$HERE/gen_filelist.py" "$REPO" > "$HERE/soc.f" || { echo "filelist gen failed"; exit 1; }
# Pure-SV tb_top top + --binary (Verilator's own main); uartdpi.c is the only
# C model (DPI import). The DPI-export-free tb_util shadow dodges the codegen bug.
verilator --binary -j 0 --top-module tb_top \
    --Mdir "$OBJ" -o Vtb_top --timescale 1ns/1ps \
    -GUSE_EXTERNAL_DEVICE_EXAMPLE=1 -GJTAG_DPI=0 \
    -f "$HERE/soc.f" > "$HERE/build.log" 2>&1
[ -x "$OBJ/Vtb_top" ] || { echo "### BUILD FAILED (no Vtb_top) — see $HERE/build.log"; grep -iE "%Error|error:|undefined" "$HERE/build.log" | head; exit 1; }

echo "### [4/4] running the simulation ..."
"$OBJ/Vtb_top" +firmware="$HERE/prog/prog.hex" +boot_sel=0 +maxcycles=300000 +verbose 2>&1 | tee "$HERE/sim.log" | tail -30
echo ""
if grep -q "EXIT SUCCESS" "$HERE/sim.log"; then
  echo "### RESULT: EXIT SUCCESS — full multi-core SoC executed the program ✓"
else
  echo "### RESULT: no EXIT SUCCESS (see $HERE/sim.log)"
fi
