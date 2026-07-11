#!/usr/bin/env python3
"""Assemble a Verilator build filelist for the MOSAIC full-SoC functional sim.

Starts from the FuseSoC sim-verilator .vc (the complete sim filelist: SoC RTL +
testharness + tb_top.cpp + uartdpi + flash model, top = testharness) and applies
the same live-source remaps / fixes that make the full SoC elaborate clean:
  - core-v-mini-mcu/hw/* and the tb/* build-copies -> live hw/* and tb/* sources
  - drop the stale idma build copies + pulp obi_pkg.sv (duplicate-package fix)
  - add -y for sci / serv / fazyrv / live-idma / cv32e40x (if_xif) / ams, plus
    idma_reg_top.sv (module name != filename) and the obi/idma include roots
Emits a verilator command file on stdout (incdirs, CFLAGS, waivers, .sv/.v, .cpp).
"""
import os, sys

REPO = sys.argv[1]
SIMV = os.path.join(REPO, "build/openhwgroup.org_systems_core-v-mini-mcu_1.0.5/sim-verilator")
VC = os.path.join(SIMV, "openhwgroup.org_systems_core-v-mini-mcu_1.0.5.vc")
CMM = "openhwgroup.org_systems_core-v-mini-mcu_1.0.5/hw/"
CMM_TB = "openhwgroup.org_systems_core-v-mini-mcu_1.0.5/tb/"
TBUTILS = "x-heep__tb-utils_0/"

def res(p):
    return os.path.normpath(os.path.join(SIMV, p))

incs, cflags, waivers, vfiles, cppfiles = [], [], [], [], []
for ln in open(VC):
    s = ln.strip()
    if not s or s.startswith("--") or s.startswith("-G") or s.startswith("-D"):
        continue
    if s.startswith("-CFLAGS"):
        # Resolve relative '-I../...' include dirs to absolute (they are relative
        # to the sim-verilator dir in the .vc, but the C++ compiler runs from
        # obj_dir, where '../src' would not exist) so DPI C models find their
        # cross-directory headers (e.g. sim_jtag.c -> remote_bitbang.h).
        toks = s.split()
        fixed = []
        for t in toks:
            if t.startswith("-I") and not os.path.isabs(t[2:]):
                fixed.append("-I" + res(t[2:]))
            else:
                fixed.append(t)
        cflags.append(" ".join(fixed))
        continue
    if s.startswith("+incdir+"):
        incs.append(res(s[len("+incdir+"):]))
        continue
    ap = res(s)
    # obi_fifo lives under its own VLNV (x-heep_ip_obi_fifo_0), so the CMM remap
    # misses it -> point at the live (fixed) source explicitly.
    if os.path.basename(ap) == "obi_fifo.sv":
        ap = os.path.join(REPO, "hw/ip/obi_fifo/obi_fifo.sv")
    # core_v_mini_mcu_pkg.sv is a CONFIG-DEPENDENT generated package (NUM_HARTS,
    # CORE*_IDX) shipped under a separate VLNV (x-heep__packages_0) as a STALE
    # build-copy. The CMM remap misses it, so the build would use the old
    # NUM_HARTS while the live hw/ files use the regenerated value -> array-size
    # mismatch. Point at the freshly-generated live package.
    elif os.path.basename(ap) == "core_v_mini_mcu_pkg.sv":
        ap = os.path.join(REPO, "hw/core-v-mini-mcu/include/core_v_mini_mcu_pkg.sv")
    # The FlooNoC fabric top + pkg are CONFIG-DEPENDENT generated files
    # (floogen via floonoc_gen.py, incl. the router-map patch) — same staleness
    # hazard as core_v_mini_mcu_pkg.sv: point at the live generated sources.
    elif os.path.basename(ap) in ("floo_mosaic_noc.sv", "floo_mosaic_noc_pkg.sv"):
        ap = os.path.join(REPO, "hw/ip/floonoc_fabric", os.path.basename(ap))
    # remap build-copies -> live
    elif CMM in ap:
        ap = os.path.normpath(os.path.join(REPO, "hw", ap.split(CMM, 1)[1]))
    elif CMM_TB in ap:
        ap = os.path.normpath(os.path.join(REPO, "tb", ap.split(CMM_TB, 1)[1]))
    elif TBUTILS in ap:                       # x-heep__tb-utils_0/* -> live tb/*
        ap = os.path.normpath(os.path.join(REPO, "tb", ap.split(TBUTILS, 1)[1]))
    # drop stale idma copies + pulp obi_pkg (collision)
    if "mosaic_ip_idma_0" in ap:
        continue
    if ap.replace("\\", "/").endswith("__obi_0.1.2/src/obi_pkg.sv"):
        continue
    # drop the vendored latch-based cve2 clock gate — replaced by the always-on
    # functional-sim override below (the latch gate keeps TITAN asleep at POR).
    if ap.replace("\\", "/").endswith("cve2_clock_gate.sv"):
        continue
    if not os.path.exists(ap):
        continue
    if ap.endswith(".vlt"):
        waivers.append(ap)
    elif ap.endswith((".cpp", ".cc", ".c")):
        # Keep the DPI-import C models (uartdpi + the JTAG DPI, whose `jtag_tick`
        # is imported by testharness unconditionally). Drop ONLY the C++ main
        # (tb_top.cpp / XHEEP_CmdLineOptions.cpp) — we drive the sim from the
        # pure-SV tb_top.sv with --binary (Verilator generates its own main).
        if os.path.basename(ap) not in ("tb_top.cpp", "XHEEP_CmdLineOptions.cpp"):
            cppfiles.append(ap)
    elif ap.endswith((".sv", ".v")):
        vfiles.append(ap)

def dd(xs):
    return list(dict.fromkeys(xs))

incs = [i for i in dd(incs) if "mosaic_ip_idma_0" not in i]
waivers, vfiles, cppfiles = dd(waivers), dd(vfiles), dd(cppfiles)

out = []
# warnings (match the proven clean-elaboration set; UNOPTFLAT for FazyRV carry chains)
for w in ["-Wno-fatal", "-Wno-WIDTH", "-Wno-UNUSEDSIGNAL", "-Wno-UNDRIVEN", "-Wno-UNUSEDPARAM",
          "-Wno-DECLFILENAME", "-Wno-TIMESCALEMOD", "-Wno-PINMISSING", "-Wno-CASEINCOMPLETE",
          "-Wno-SYMRSVDWORD", "-Wno-GENUNNAMED", "-Wno-WIDTHEXPAND", "-Wno-WIDTHTRUNC",
          "-Wno-UNOPTFLAT", "-Wno-MULTIDRIVEN", "-Wno-LATCH", "-Wno-BLKANDNBLK",
          "-Wno-IMPLICIT", "-Wno-REALCVT", "-Wno-COMBDLY", "-Wno-STMTDLY",
          "-Wno-INITIALDLY", "-Wno-MISINDENT"]:
    out.append(w)
# -y search dirs for modules the stale .vc omits / that we remapped to live
for y in ["hw/sci", "hw/vendor/mosaic/serv/rtl", "hw/vendor/mosaic/serv/servile",
          "hw/vendor/mosaic/fazyrv/rtl", "hw/vendor/mosaic/picorv32",
          "hw/vendor/mosaic/snitch/rtl",
          "hw/vendor/mosaic/idma/rtl",
          "hw/vendor/mosaic/idma/rtl/backend", "hw/vendor/mosaic/idma/rtl/midend",
          "hw/vendor/mosaic/idma/rtl/frontend", "hw/vendor/mosaic/idma",
          "hw/ip_examples/ams/rtl", "hw/vendor/openhwgroup/cv32e40x/rtl",
          # classic fixed-latency logarithmic interconnect (bus: log configs)
          "hw/vendor/xheep/cluster_interconnect/rtl/tcdm_interconnect"]:
    out.append("-y " + os.path.join(REPO, y))
out.append("-I" + os.path.join(REPO, "hw/vendor/pulp_platform/obi/include"))
out.append("-I" + os.path.join(REPO, "hw/vendor/mosaic/idma/rtl/include"))
# tb/mosaic_soc FIRST so testharness's `include "tb_util.svh"` resolves to the
# DPI-export-free shadow (dodges the Verilator tb_loadHEX codegen bug), then tb/.
out.append("-I" + os.path.join(REPO, "tb/mosaic_soc"))
out.append("-I" + os.path.join(REPO, "tb"))
for i in incs:
    out.append("-I" + i)
out += cflags
for w in waivers:
    out.append(w)
# module idma_reg32_3d lives in idma_reg_top.sv (filename != module) -> add explicitly
out.append(os.path.join(REPO, "hw/vendor/mosaic/idma/rtl/idma_reg_top.sv"))
# tcdm_interconnect_pkg: packages are not resolved via -y -> add explicitly
out.append(os.path.join(
    REPO, "hw/vendor/xheep/cluster_interconnect/rtl/tcdm_interconnect/tcdm_interconnect_pkg.sv"))
# snitch: packages (riscv_instr, snitch_pkg) + module snitch_regfile lives in
# snitch_regfile_ff.sv (filename != module) -> add explicitly
out.append(os.path.join(REPO, "hw/vendor/mosaic/snitch/rtl/riscv_instr.sv"))
out.append(os.path.join(REPO, "hw/vendor/mosaic/snitch/rtl/snitch_pkg.sv"))
out.append(os.path.join(REPO, "hw/vendor/mosaic/snitch/rtl/snitch_regfile_ff.sv"))
# cva6 (mosaic:ip:cva6): package-heavy — explicit ordered fragment, appended
# ONLY when the generated cpu_subsystem actually instantiates cva6_sci (keeps
# ~80 files out of non-cva6 builds; sim-only core, excluded from tapeout)
_cpu_ss = os.path.join(REPO, "hw/core-v-mini-mcu/cpu_subsystem.sv")
if os.path.exists(_cpu_ss) and "cva6_sci" in open(_cpu_ss).read():
    out.append("-I" + os.path.join(REPO, "hw/vendor/mosaic/cva6/core/include"))
    with open(os.path.join(REPO, "hw/vendor/mosaic/cva6/cva6.f")) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#"):
                out.append(os.path.join(REPO, _line))
# functional-sim cve2 clock-gate override (replaces the dropped vendored latch gate)
out.append(os.path.join(REPO, "tb/mosaic_soc/cve2_clock_gate.sv"))
# the pure-SV testbench top (the .vc uses tb_top.cpp instead, so add it explicitly)
out.append(os.path.join(REPO, "tb/tb_top.sv"))
for f in vfiles:
    out.append(f)
for c in cppfiles:
    out.append(c)

sys.stdout.write("\n".join(out) + "\n")
sys.stderr.write(
    f"[gen_filelist] verilog={len(vfiles)} cpp={len(cppfiles)} waivers={len(waivers)} "
    f"incs={len(incs)} cflags={len(cflags)}\n")
