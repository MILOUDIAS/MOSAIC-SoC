#!/bin/bash
# MOSAIC all-TITAN 4-core SMP full-SoC simulation (Verilator).
#
# Builds the COMPLETE SoC for the all-TITAN config (2x cv32e20 + 2x cv32e40x,
# every role titan -> all four cores boot free-running at the shared
# BOOT_ADDR) and runs ONE program (prog_titan/titan_smp.S) that branches on
# mhartid: hart 0 queues 3 task descriptors in the TDU FIFO, harts 1-3
# poll-pop them (atomic dequeue), compute, and report per-slot sentinels;
# hart 0 verifies each slot's exact value and signals EXIT SUCCESS.
#
# Defaults to the bus:log fabric; run the same demo over the FlooNoC with:
#   MOSAIC_CFG=configs/mosaic_titan_floonoc.yaml tb/mosaic_soc/run_titan.sh
#
# Needs: Verilator + a RISC-V GCC (compile-only; ld-linked, no multilib).
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
MOSAIC_CFG="${MOSAIC_CFG:-configs/mosaic_titan_log.yaml}"
OBJ="$HERE/obj_dir_titan"

echo "### [1/4] generating RTL ($MOSAIC_CFG: 2x cv32e20 + 2x cv32e40x, all TITAN) ..."
TPLS=$(find . \( -path './hw/vendor/*' ! -path './hw/vendor/xheep' ! -path './hw/vendor/xheep/*' \
    -o -path './util/*' ! -path './util/profile' ! -path './util/profile/*' \
    -o -path './test/*' -o -path './refs/*' \) -prune -o -name '*.tpl' -print)
python3 util/xheep_gen/mcu_gen.py --mosaic_config "$MOSAIC_CFG" --base_config configs/general.hjson \
    --pads_cfg configs/pad_cfg.py --outtpl "$TPLS" --externaltpl "" >/dev/null 2>&1 || { echo "RTL gen failed"; exit 1; }
echo "###       running FuseSoC setup (register generators + filelist) ..."
RISCV_XHEEP="${RISCV_XHEEP:-$(dirname "$(dirname "$TC")")}" \
COMPILER_PREFIX="${COMPILER_PREFIX:-$(basename "$TC" | sed 's/elf$//')}" \
    scripts/fusesoc-setup.sh > "$HERE/fusesoc-setup.log" 2>&1 \
    || { echo "FuseSoC setup failed — see $HERE/fusesoc-setup.log"; exit 1; }

echo "### [2/4] assembling the SMP program (one .S, mhartid-branched, rv32i) ..."
# rv32i_zicsr: the program reads mhartid (csrr); modern binutils requires the
# Zicsr extension to be named explicitly. Encodings remain plain rv32i + CSR.
( cd "$HERE/prog_titan"
  $TC-gcc -march=rv32i_zicsr -mabi=ilp32 -nostdlib -ffreestanding -c titan_smp.S -o titan_smp.o || exit 1
  $TC-ld -T link.ld titan_smp.o -o titan_smp.elf || exit 1
  $TC-objcopy -O verilog titan_smp.elf titan_smp.hex || exit 1 ) || { echo "program build failed"; exit 1; }
echo "    firmware: $HERE/prog_titan/titan_smp.hex"

echo "### [3/4] building the full-SoC Verilator model (this takes a few minutes) ..."
rm -rf "$OBJ"
python3 "$HERE/gen_filelist.py" "$REPO" > "$HERE/soc.f" || { echo "filelist gen failed"; exit 1; }
verilator --binary -j 0 --top-module tb_top \
    --Mdir "$OBJ" -o Vtb_top --timescale 1ns/1ps \
    -GUSE_EXTERNAL_DEVICE_EXAMPLE=1 -GJTAG_DPI=0 \
    -f "$HERE/soc.f" > "$HERE/build-titan.log" 2>&1
[ -x "$OBJ/Vtb_top" ] || { echo "### BUILD FAILED (no Vtb_top) — see $HERE/build-titan.log"; grep -iE "%Error|error:|undefined" "$HERE/build-titan.log" | head; exit 1; }

echo "### [4/4] running the simulation ..."
"$OBJ/Vtb_top" +firmware="$HERE/prog_titan/titan_smp.hex" +boot_sel=0 +maxcycles=300000 +verbose 2>&1 | tee "$HERE/sim-titan.log" | tail -30
echo ""
if grep -q "EXIT SUCCESS" "$HERE/sim-titan.log"; then
  echo "### RESULT: EXIT SUCCESS — 4 TITAN cores cooperated over the TDU ($MOSAIC_CFG) ✓"
else
  echo "### RESULT: no EXIT SUCCESS (see $HERE/sim-titan.log)"
fi
