# MOSAIC-SoC Progress Dashboard

> **IEEE SSCS Chipathon 2026 · Track D · GF180MCU · Updated: 2026-07-10**

---

## 1. At a Glance

```
PHASE 1 — Config-Driven Multi-Core Generator   █████████████████████  98%
PHASE 2 — Agentic Harness (oh-my-soc)          ████████████████████░  85%
PHASE 3 — Physical Design (GF180MCU)           ██████░░░░░░░░░░░░░░░  30%
OVERALL                                        ████████████████░░░░  80%
```

**Headline:** the production C firmware runs end-to-end on the full 7-hart PoC SoC —
`tb/mosaic_soc/run_fw.sh` → **EXIT SUCCESS** (TITAN dispatches 6 TDU tasks, all workers
pop unique descriptors, compute, and report). The TDU wake-and-run demo passes on **all
three bus fabrics** (`obi`, `log`, `floonoc`).

| Metric | Value |
|--------|-------|
| Bugs found & fixed | 21 (see [Bug Tracker](#7-bug-tracker-all-fixed)) |
| Core IPs integrated | 9 / 9 (cv32e20, cv32e40x, cva6†, ibex, fazyrv, picorv32, qerv, serv, snitch) — †sim-only |
| SCI wrappers | 6 (fazyrv, serv, ibex, picorv32, snitch, cva6 — qerv reuses serv) |
| Bus fabrics | 3 (OBI crossbar · logarithmic interconnect · FlooNoC) |
| Test suites | 11, all green (see below) |
| Firmware size | 1,592 B text (production) · 2,440 B text (sched demo) |
| Commits | 19 on `main` history (+ `dev-mld` in flight) |

### What passes today

Last full sweep: **2026-07-11** (18-step, after the picorv32/snitch/cva6 additions) — all green.

| Suite | Command | Proves | Result |
|-------|---------|--------|--------|
| TDU unit TB | Verilator on `hw/tdu/tb/tdu_tb.sv` | reg map, FIFO order, **targeted** auto-wake, CPI array, energy counter | 22/22 |
| TDU SoC-level | `tb/tdu/soc/cocotb/run.sh` | reg-bus tap decode inside the AO subsystem | PASS |
| Multi-core SCI wake-loop | `tb/mosaic/run.sh` + `tb/mosaic/cocotb/run.sh` | dormancy → selective wake → execution, 3 core types | 3/3 |
| iDMA | `tb/idma/cocotb/run.sh` | mem-to-mem DMA at block + SoC (arbitrated) level | PASS ×2 |
| LIC fabric unit | `tb/log_xbar/run.sh` | parallel banks, same-bank RR, periph tier, ERROR decode | 5/5 |
| OBI↔AXI bridges + NoC smoke | `tb/floonoc/cocotb/run.sh [stage2]` | bridge loopback, then through the generated FlooNoC | PASS ×2 |
| Full-SoC wake demo ×3 fabrics | `[MOSAIC_CFG=…] tb/mosaic_soc/run.sh` | TITAN → TDU → worker wake → execute, on `obi`/`log`/`floonoc` | EXIT SUCCESS ×3 |
| **Production firmware** | `tb/mosaic_soc/run_fw.sh` | C firmware on the 7-hart PoC: TDU driver, task-pop protocol, completion poll | EXIT SUCCESS |
| All-TITAN SMP ×3 fabrics | `MOSAIC_CFG=… tb/mosaic_soc/run_titan.sh` | 2×cv32e20 + 2×cv32e40x free-running SMP, atomic TDU dequeue | EXIT SUCCESS ×3 |
| New-core wake demos | `MOSAIC_CFG=configs/mosaic_{picorv32,snitch,cva6,new_cores}.yaml tb/mosaic_soc/run.sh` | picorv32, snitch, cva6 (sim-only) each boot/wake/execute; combined config runs all three together | EXIT SUCCESS ×4 |
| Generator pytests | `pytest test/test_x_heep_gen` | config seam, bus-type mapping/validation, topo-viz | 15+ pass |

---

## 2. Milestones

```
M1:  Config-driven generation          ████████████████████  DONE     (Jun 27)
M2:  Multi-core RTL generation         ████████████████████  DONE     (Jun 28)
M3:  SCI wrappers + vendored cores     ████████████████████  DONE     (Jun 28)
M4:  TDU + iDMA integration            ████████████████████  DONE     (Jun 29)
M5:  Multi-core simulation PASS        ████████████████████  DONE     (Jun 30)
M6:  Full-SoC elaboration clean        ████████████████████  DONE     (Jun 30)
M7:  TITAN firmware + TDU driver       ████████████████████  DONE     (Jun 30)
M8:  Scheduling modes demo             ████████████████████  DONE     (Jun 30)
M9:  oh-my-soc agentic harness         ████████████████████  DONE     (Jun 30)
M10: Multi-fabric bus (log + FlooNoC)  ████████████████████  DONE     (Jul 09)
M11: Production firmware full-SoC sim  ████████████████████  DONE     (Jul 09)
M12: LibreLane pin-binding + SRAM      ████░░░░░░░░░░░░░░░░  IN PROG
M13: DRC/LVS clean signoff             ░░░░░░░░░░░░░░░░░░░░  PLANNED
M14: Tapeout-ready GDSII               ░░░░░░░░░░░░░░░░░░░░  PLANNED
```

---

## 3. Work Board

### In progress

| ID | Task | Component | Blocker / Notes |
|----|------|-----------|-----------------|
| **P-01** | LibreLane `mosaic_soc_core.sv` pin-binding | `flow/librelane/src/` | TODO at line 68 — needs `x_heep_system` instantiation + pad-to-pin wiring |
| **P-02** | Pad map finalization | `flow/librelane/slots/` | `slot_mosaic.yaml` exists, needs completion for all SoC signals |
| **P-03** | SRAM hard macro generation | `sw/vendor/openram/` | Configs ready; needs GF180 PDK + OpenRAM installed to generate GDS/LEF/LIB |
| **P-05** | Ibex prim de-dup for co-build | `hw/vendor/mosaic/ibex/` | Ibex has own prim closure; de-dup needed for full FuseSoC build |
| **P-06** | GF180 SRAM bitcell extraction | `sw/vendor/openram/gf180mcu/gds_lib/` | Need cell1rw.gds + sp from PDK or upstream OpenRAM |

### Backlog

| ID | Task | Priority | Component | Notes |
|----|------|----------|-----------|-------|
| **N-06** | GF180MCU DRC/LVS signoff | **HIGH** | `flow/librelane/` | No actual signoff run yet |
| **N-07** | 50 MHz STA closure | **HIGH** | `flow/librelane/` | SDC exists; no timing analysis run |
| **N-08** | Target area validation (1.249 mm²) | MED | Post-synthesis | No area data yet |
| **N-05** | Per-core power domains | LOW | `ao_peripheral_subsystem.sv.tpl` | Power manager is single-domain |
| **N-09** | Formal verification (riscv-formal) | LOW | SCI wrappers | Not started |
| **N-10** | FPGA bitstream generation | LOW | `hw/fpga/` | Structure exists; no flow completed |

**Cancelled / out of scope:** N-04 PLIC multi-target routing (TITAN handles all interrupts,
dispatches via TDU wake — future enhancement only) · N-16 CVA6 tapeout integration (area
budget — **sim-only** CVA6 support landed as D-65/D-66 on 2026-07-11).
Completed backlog items (N-01..03 firmware, N-11..15 harness, P-04 full-SoC sim) live in
the Done log below as D-32..45 and D-60.

### Done — by area

Sixty deliverables, grouped by area. IDs are stable (referenced elsewhere in the repo).

**Config system & RTL generation**

| ID | Task | Component | Verified |
|----|------|-----------|----------|
| D-01 | MOSAIC YAML config parser | `util/xheep_gen/mosaic_config.py` | `make mosaic-gen` EXIT=0 |
| D-02 | Multi-core XHeep API | `util/xheep_gen/xheep.py` | Unit + integration |
| D-03 | Per-core master indices | `core_v_mini_mcu_pkg.sv.tpl` | Lint-clean |
| D-04 | Multi-core cpu_subsystem template | `cpu_subsystem.sv.tpl` | 6 branches elaborated |
| D-05 | Multi-master system_bus | `system_bus.sv.tpl` | Lint-clean |
| D-06 | Per-hart interrupt routing | `core_v_mini_mcu.sv.tpl` | Functional sim |
| D-07 | Per-core hart ID array | `core_v_mini_mcu.sv.tpl` | Functional sim |
| D-18 | Packed/unpacked port fix | `core_v_mini_mcu.sv.tpl` | Lint-clean |
| D-19 | Mako directive fix | `core_v_mini_mcu.sv.tpl` | Generated SV compiles |
| D-28 | All-cores generation test | `configs/mosaic_all_cores.yaml` | 5 SCI branches render |
| D-54 | Multi-fabric bus config seam (`bus: obi\|log\|floonoc` + `bus_opts`) | `util/xheep_gen/{bus_type,mosaic_config,xheep}.py` | 10 pytests pass |

**Cores & SCI wrappers**

| ID | Task | Component | Verified |
|----|------|-----------|----------|
| D-08 | FazyRV SCI wrapper | `hw/sci/fazyrv_sci.sv` | Verilator lint-clean |
| D-09 | SERV SCI wrapper | `hw/sci/serv_sci.sv` | Verilator lint-clean |
| D-10 | Ibex SCI wrapper | `hw/sci/ibex_sci.sv` | Verilator lint-clean |
| D-11 | Vendored FazyRV RTL | `hw/vendor/mosaic/fazyrv/` | Elaborates clean |
| D-12 | Vendored SERV + servile RTL | `hw/vendor/mosaic/serv/` | Elaborates clean |
| D-13 | Vendored Ibex RTL | `hw/vendor/mosaic/ibex/` | Elaborates clean |
| D-20 | FazyRV reset polarity fix | `hw/sci/fazyrv_sci.sv` | FazyRV now executes |
| D-21 | FazyRV clock-stall adapter | `hw/sci/fazyrv_sci.sv` | Combinational mem core |
| D-22 | serv_sci OBI bridge fix | `hw/sci/serv_sci.sv` | Single-outstanding OK |
| D-23 | fazyrv_sci OBI bridge fix | `hw/sci/fazyrv_sci.sv` | Read-data hold latch |
| D-29 | QERV integration | Reuses `serv_sci` W=4 | Elaborates clean |

**TDU & iDMA**

| ID | Task | Component | Verified |
|----|------|-----------|----------|
| D-14 | TDU hardware scheduler (targeted auto-wake) | `hw/tdu/rtl/tdu.sv` | 22/22 unit checks |
| D-15 | TDU SoC-level integration | `tb/tdu/soc/` | cocotb PASS |
| D-16 | iDMA integration | `hw/vendor/mosaic/idma/` | cocotb PASS (2 levels) |
| D-17 | Worker dormancy + wake loop | `core_v_mini_mcu.sv.tpl` | cocotb end-to-end |

**Bus fabrics**

| ID | Task | Component | Verified |
|----|------|-----------|----------|
| D-55 | `bus: log` two-tier logarithmic interconnect (LIC + varlat tiers) | `system_xbar.sv.tpl`, `xheep_cluster_interconnect.core` | tb/log_xbar 5/5 + wake demo EXIT SUCCESS |
| D-56 | OBI↔AXI bridges (x-heep-struct type params, no pulp obi_pkg) | `hw/vendor/mosaic/axi_obi/` | cocotb loopback PASS |
| D-57 | FlooNoC vendoring + floogen integration + `bus: floonoc` fabric | `hw/vendor/mosaic/floonoc/`, `util/xheep_gen/floonoc_gen.py`, `hw/ip/floonoc_fabric/` | NoC smoke PASS + wake demo EXIT SUCCESS |

**Simulation & verification infrastructure**

| ID | Task | Component | Verified |
|----|------|-----------|----------|
| D-24 | FuseSoC refs/ crash fix | `scripts/fusesoc-setup.sh` | `make mosaic-gen` works |
| D-25 | Full-SoC elaboration clean | Top-level | 837 modules lint-clean |
| D-26 | TDU wake-and-run demo | `tb/mosaic_soc/` | EXIT SUCCESS |
| D-27 | Multi-core SCI simulation | `tb/mosaic/` | 3/3 cores PASS |
| D-59 | Full-SoC sim flow hardening (fusesoc-setup in run.sh, live-file remaps, generated tb_util) | `tb/mosaic_soc/{run.sh,gen_filelist.py,tb_util.svh.tpl}` | all 3 fabrics' wake demos green |
| D-60 | Production C firmware full-SoC sim (7-hart PoC, TDU task-pop worker protocol) | `sw/firmware/`, `tb/mosaic_soc/run_fw.sh` | EXIT SUCCESS @ ~300k cycles: 6 workers pop unique descriptors, per-slot sentinels + results verified |
| D-61 | cv32e40x TITAN integration (vendor bump 0.9.0 → post-0.10 `d952cd6`, XIF iface rename + `if_xif_compat.sv` shim, XIF patch 0003 reapplied) | `hw/vendor/openhwgroup/cv32e40x/`, `cpu_subsystem.sv.tpl` | Boots + executes in full-SoC SMP sim (D-62) |
| D-62 | All-TITAN 4-core SMP demo (2× cv32e20 + 2× cv32e40x free-running, atomic TDU TASK_POP dequeue, per-slot sentinels) on all 3 fabrics | `configs/mosaic_titan_{obi,log,floonoc}.yaml`, `tb/mosaic_soc/run_titan.sh`, `prog_titan/titan_smp.S` | EXIT SUCCESS ×3: OBI @17µs, LOG @8µs, FlooNoC @58µs (pinned Verilator 5.050) |
| D-63 | PicoRV32 integration (YosysHQ picorv32.v @ `f00a88c`, native mem→OBI SCI wrapper) | `hw/vendor/mosaic/picorv32/`, `hw/sci/picorv32_sci.sv` | `mosaic_picorv32.yaml` wake demo EXIT SUCCESS (2 picorv32 workers) |
| D-64 | Snitch bare-core integration (mempool flavor; instr refill + TCDM reqrsp → split OBI; X-poison + fork-fpnew divergences patched) | `hw/vendor/mosaic/snitch/`, `hw/sci/snitch_sci.sv` | `mosaic_snitch.yaml` wake demo EXIT SUCCESS (2 snitch workers) |
| D-65 | CVA6 32-bit **sim-only** integration (cv32a65x-derived MOSAIC config: uncached D-side, NonIdempotent periph PMA, WT cache, CVXIF off; burst-capable 64→32 AXI→OBI bridge) | `hw/vendor/mosaic/cva6/`, `hw/vendor/mosaic/axi_obi/xheep_axi_burst_to_obi.sv`, `hw/sci/cva6_sci.sv` | `mosaic_cva6.yaml` wake demo EXIT SUCCESS (cva6 TITAN orchestrates TDU); tapeout exclusion stands |
| D-66 | Combined new-cores demo: cva6 TITAN + snitch ATLAS + picorv32 NANO in one SoC | `configs/mosaic_new_cores.yaml` | EXIT SUCCESS — CVA6 wakes both workers via the TDU, per-slot sentinels verified (Verilator 5.050) |

**Firmware**

| ID | Task | Component | Verified |
|----|------|-----------|----------|
| D-32 | TDU driver (C API) | `sw/firmware/common/tdu.{h,c}` | Builds clean, rv32i |
| D-33 | TITAN firmware (TDU programming) | `sw/firmware/titan/titan_main.c` | Full-SoC sim EXIT SUCCESS (D-60) |
| D-34 | ATLAS worker (signal processing) | `sw/firmware/atlas/atlas_worker.S` | Full-SoC sim EXIT SUCCESS (D-60) |
| D-35 | NANO worker (sensor polling) | `sw/firmware/nano/nano_worker.S` | Full-SoC sim EXIT SUCCESS (D-60) |
| D-36 | Multi-core linker script | `sw/firmware/mosaic_link.ld` | Correct VMA layout; sentinel window reserved |
| D-37 | Firmware build system | `sw/firmware/Makefile` | Builds hex for sim TB |
| D-38 | Hardware register definitions | `sw/firmware/common/mosaic_hw.h` | Self-contained, mmio_region_t, Apache-2.0 licensed |
| D-39 | Scheduling modes demo (dynamic + power-aware) | `sw/firmware/titan/titan_scheduling_demo.c` | Builds clean, exercises all 3 TDU modes |

**oh-my-soc harness**

| ID | Task | Component | Verified |
|----|------|-----------|----------|
| D-40 | Harness core framework | `harness/core.py` | SkillResult, validate_config, run_cmd, config I/O |
| D-41 | config-author skill | `harness/skills/config_author.py` | Generate/validate mosaic.yaml, 3 presets, CLI |
| D-42 | flow-runner skill | `harness/skills/flow_runner.py` | 11 flows, structured log parsing, timing |
| D-43 | drc-triage skill | `harness/skills/drc_triage.py` | Magic/KLayout/Netgen parsers, fix suggestions |
| D-44 | doc-gen skill | `harness/skills/doc_gen.py` | Config summary, memory map, run reports, dashboard |
| D-45 | oh-my-soc CLI | `harness/__main__.py` | `python -m harness <skill> <cmd>` entry point |
| D-58 | topo-viz skill (checks + interactive topology HTML) | `harness/skills/topo_viz.py` | 5 pytests pass, all 3 fabrics render |

**Physical design prep**

| ID | Task | Component | Verified |
|----|------|-----------|----------|
| D-30 | LibreLane flow structure | `flow/librelane/` | Makefile + configs |
| D-31 | GF180 pad frame | `flow/librelane/src/chip_top.sv` | Elaborates clean |
| D-46 | OpenRAM GF180 technology config | `sw/vendor/openram/gf180mcu/tech/tech.py` | 3.3V params, corrected layer map, DRC rules |
| D-47 | OpenRAM bitcell wrapper | `sw/vendor/openram/gf180mcu/custom/gf180_bitcell.py` | GF180MCU 6T cell wrapper for OpenRAM factory |
| D-48 | OpenRAM 4KB SRAM config | `sw/vendor/openram/configs/mosaic_sram_4k.py` | 512×8, single bank, ~0.05 mm² est. |
| D-49 | OpenRAM 32KB SRAM config | `sw/vendor/openram/configs/mosaic_sram_32k.py` | 4096×8, 2 banks, ~0.3-0.6 mm² est. |
| D-50 | LibreLane config.yaml SRAM macros | `flow/librelane/config.yaml` | MACROS section + PDN_MACRO_CONNECTIONS |
| D-51 | LibreLane pdn_cfg.tcl SRAM grid | `flow/librelane/pdn_cfg.tcl` | define_pdn_grid + add_pdn_connect for SRAM |
| D-52 | LibreLane config_classic.yaml SRAM | `flow/librelane/config_classic.yaml` | MACROS section for classic (core-only) flow |
| D-53 | OpenRAM directory README | `sw/vendor/openram/README.md` | Porting guide, status, known issues |

---

## 4. Component Status Matrix

| Component | RTL | Wrapper | Tests | Integration | Status |
|-----------|-----|---------|-------|-------------|--------|
| **cv32e20 (TITAN)** | Native x-heep | N/A | Full-SoC fw sim | `cpu_subsystem` | DONE |
| **cv32e40x (TITAN)** | Vendored `d952cd6` | N/A (native OBI) | Full-SoC SMP ×3 fabrics | `cpu_subsystem` | DONE |
| **CVA6 (TITAN, sim-only)** | Vendored 32-bit WT subset | `cva6_sci.sv` (AXI→OBI burst bridge) | Full-SoC wake demo ×2 configs | `cpu_subsystem` | DONE (sim) — excluded from tapeout |
| **PicoRV32 (ATLAS/NANO)** | Vendored `f00a88c` | `picorv32_sci.sv` | Full-SoC wake demo | `cpu_subsystem` | DONE |
| **Snitch (ATLAS/NANO)** | Vendored (mempool) | `snitch_sci.sv` | Full-SoC wake demo | `cpu_subsystem` | DONE |
| **FazyRV (ATLAS)** | Vendored | `fazyrv_sci.sv` | cocotb + fw sim | `cpu_subsystem` | DONE |
| **SERV (NANO)** | Vendored | `serv_sci.sv` | cocotb + fw sim | `cpu_subsystem` | DONE |
| **QERV (NANO)** | Reuses SERV | `serv_sci.sv` (W=4) | Elaborates | `cpu_subsystem` | DONE |
| **Ibex (TITAN)** | Vendored | `ibex_sci.sv` | Lint-clean | `cpu_subsystem` | DONE |
| **TDU** | `tdu.sv` | N/A | 22/22 unit + SoC | `ao_peripheral` | DONE |
| **iDMA** | `idma_xheep_wrapper.sv` | N/A | cocotb PASS (2) | `ao_peripheral` | DONE |
| **Bus fabric — obi** | `system_xbar.sv.tpl` | N/A | wake demo + fw sim | Top-level | DONE |
| **Bus fabric — log** | `system_xbar.sv.tpl` + LIC | N/A | tb/log_xbar 5/5 + wake demo | Top-level | DONE |
| **Bus fabric — floonoc** | floogen + `axi_obi` bridges | N/A | bridge/NoC cocotb + wake demo | Top-level | DONE |
| **TITAN firmware** | `titan_main.c` | `tdu.{h,c}` | Full-SoC EXIT SUCCESS | `sw/firmware/` | DONE |
| **Sched demo** | `titan_scheduling_demo.c` | `tdu.{h,c}` | Builds clean, 3 modes | `sw/firmware/` | DONE |
| **oh-my-soc** | `harness/` | 5 skills + CLI | pytest + CLI smoke | `harness/skills/` | DONE |
| **PLIC** | OpenTitan IP | N/A | Single-target | `peripheral` | PARTIAL |
| **Power mgr** | x-heep IP | N/A | Single-domain | `ao_peripheral` | PARTIAL |
| **LibreLane flow** | `chip_top.sv` | `mosaic_soc_core.sv` | — | Flow wired | PARTIAL |
| **OpenRAM GF180** | `tech/tech.py` | `gf180_bitcell.py` | Configs written | `sw/vendor/openram/` | PARTIAL |
| **SRAM macros** | Configs ready | PDK needed | Not generated | `flow/librelane/` | BLOCKED |

---

## 5. Firmware Architecture

```
sw/firmware/
├── common/
│   ├── mosaic_hw.h        # Self-contained HW register definitions
│   ├── tdu.h              # TDU driver API (header)
│   └── tdu.c              # TDU driver implementation
├── titan/
│   ├── start.S            # Entry point at 0x180 (stack init + jump to main)
│   ├── titan_main.c       # TITAN orchestrator firmware (production)
│   └── titan_scheduling_demo.c  # Scheduling modes demo (3 phases)
├── atlas/
│   └── atlas_worker.S     # ATLAS signal-processing worker (TDU task pop)
├── nano/
│   └── nano_worker.S      # NANO sensor-polling worker (TDU task pop)
├── mosaic_link.ld         # Multi-core linker script (sentinel window reserved)
├── Makefile               # Build system (make / make demo / make clean)
└── build/
    ├── mosaic_fw.{elf,hex}    # Production (1,592 B text)
    └── mosaic_demo.{elf,hex}  # Scheduling demo (2,440 B text)
```

**Memory layout contract** (`mosaic_link.ld`): TITAN code @ 0x180, ATLAS @ 0x1000,
NANO @ 0x2000. The window **0x3000–0x31FF is reserved for worker↔TITAN signalling**
(sentinels at `0x3000 + slot*4`, results at `0x3100 + slot*4`) and is excluded from every
linker MEMORY region; TITAN data + stack live at 0x3200+ (bug 19).

**Production boot flow** (`titan_main.c`, verified end-to-end in `run_fw.sh`):
1. Boot ROM jumps to `_start` @ 0x180; `start.S` sets the stack, calls `main()`
2. TITAN writes its sentinel, sets TDU mode DYNAMIC, loads CPI estimates (ATLAS=4, NANO=32)
3. **Push-all-then-wake:** queues all 6 task descriptors (2× signal-proc → ATLAS,
   4× sensor-poll → NANO), then arms the wake mask and releases every worker with one
   WAKE_REQ (HW auto-wake is targeted by `core_hint` since bug 20)
4. Each worker pops a **unique** descriptor from TDU `TASK_POP` (hardware-atomic dequeue),
   computes, stores its result, then writes its sentinel — slot = the descriptor's
   `core_hint`, so reporting is correct no matter which worker pops which task
5. TITAN polls the 6 sentinel slots → `soc_ctrl` **EXIT SUCCESS**

**Scheduling demo** (`titan_scheduling_demo.c`): phase 1 STATIC (fixed assignment) →
phase 2 DYNAMIC (CPI-based migration) → phase 3 POWER_AWARE (energy-budget consolidation);
reports energy per phase + PASS/FAIL via sentinel slots.

**FreeRTOS integration path:** the TDU driver API (`tdu.h`) is designed to be called from
FreeRTOS tasks; the bare-metal poll loop can be wrapped in `xTaskCreate()` +
`xQueueSend()` with minimal changes.

---

## 6. oh-my-soc Agentic Harness

```
harness/
├── __main__.py              # CLI: python -m harness <skill> <cmd>
├── core.py                  # SkillResult, validate_config, run_cmd, config I/O
└── skills/
    ├── config_author.py     # Generate/validate mosaic.yaml, 3 presets
    ├── flow_runner.py       # 11 EDA flows, structured log parsing
    ├── drc_triage.py        # Magic/KLayout/Netgen parsers, fix suggestions
    ├── doc_gen.py           # Config summary, memory map, run reports
    └── topo_viz.py          # Config checks + interactive bus-topology HTML
```

**Design principle:** the agent *assists and is checked by* deterministic tooling. It
never replaces signoff.

| Skill | Input → Output | Key feature |
|-------|---------------|-------------|
| `config-author` | NL intent → `mosaic.yaml` | 3 presets (poc/minimal/max_cores), schema validation |
| `flow-runner` | Config → EDA run + summary | 11 flows, timing, structured log parsing |
| `drc-triage` | DRC/LVS report → fix suggestions | 3 format parsers, severity classification |
| `doc-gen` | Artifacts → documentation | Config summary, memory map, run reports |
| `topo-viz` | Config → semantic checks + topology HTML | Per-fabric rendering (obi/log/floonoc), self-contained SVG+JS |

```bash
python -m harness config-author generate --preset poc --name my_soc
python -m harness flow-runner run firmware-build
python -m harness drc-triage analyze report.rpt
python -m harness doc-gen memory-map
python -m harness topo-viz render mosaic.yaml -o topology.html
```

---

## 7. Bug Tracker (All Fixed)

| # | Bug | Severity | Found Via | Fixed In |
|---|-----|----------|-----------|----------|
| 1 | FazyRV reset polarity inverted | CRITICAL | Functional sim | `fazyrv_sci.sv` |
| 2 | CpuType enum overflow (SCI core as first) | HIGH | Generation | `core_v_mini_mcu_pkg.sv.tpl` |
| 3 | FazyRV CSR+LOGIC invalid combo | HIGH | Elaboration | `cpu_subsystem.sv.tpl` |
| 4 | FuseSoC crashes on `refs/` empty `.core` | HIGH | `make mosaic-gen` | `fusesoc-setup.sh` |
| 5 | Generated top `.sv` not in `.gitignore` | LOW | Code review | `.gitignore` |
| 6 | `core_wake_i` packed/unpacked mismatch | CRITICAL | Verilator lint | `core_v_mini_mcu.sv.tpl` |
| 7 | Per-hart array range direction reversed | HIGH | Verilator lint | `core_v_mini_mcu.sv.tpl` |
| 8 | `serv_sci` OBI ack never fires | CRITICAL | Functional sim | `serv_sci.sv` |
| 9 | `fazyrv_sci` OBI ack never fires | CRITICAL | Functional sim | `fazyrv_sci.sv` |
| 10 | FazyRV clock stalls during fetch | HIGH | Functional sim | `fazyrv_sci.sv` |
| 11 | Inline Mako `% if` syntax error | CRITICAL | Verilator lint | `core_v_mini_mcu.sv.tpl` |
| 12 | TDU address decode missing base subtract | HIGH | SoC-level cocotb | `ao_peripheral_subsystem.sv.tpl` |
| 13 | iDMA wrapper version skew | CRITICAL | Elaboration | `idma_xheep_wrapper.sv` |
| 14 | `obi_fifo` output-port readback | MEDIUM | Verilator lint | `obi_fifo` |
| 15 | floogen router ID-table omits mgr endpoints → responses misrouted to port 0 | CRITICAL | FlooNoC wake demo | `floonoc_gen.py::_patch_router_map` |
| 16 | tb SoC flow skipped register-gen → stale power manager gates extra RAM banks (reads 0) | CRITICAL | LOG wake demo | `tb/mosaic_soc/run.sh` |
| 17 | Static `tb_util.svh` shadow hardcoded 2×32KB banks (breaks il/other layouts) | HIGH | LOG wake demo | `tb/mosaic_soc/tb_util.svh.tpl` |
| 18 | common_cells 1.38 vs FlooNoC-1.39 skew (addr_decode NoIndices, 5-arg ASSERT) | HIGH | Elaboration | vendored floo patches |
| 19 | Linker placed `.sbss`/stack at 0x3000 — TITAN's globals collide with the worker sentinel window (TDU region ptr clobbered by own sentinel write → wild store) | CRITICAL | Production-fw sim | `sw/firmware/mosaic_link.ld` |
| 20 | TDU auto-wake fired for ALL masked sleeping cores on ANY push (no core_hint decode) → workers popped the FIFO before their descriptors were queued; spurious wakes also inflate the energy counter | HIGH | Production-fw sim | `tdu.sv` (targeted `1<<core_hint` decode) + `titan_main.c` push-all-then-wake + worker park-on-empty-pop |
| 21 | **Simulator, not RTL:** oss-cad-suite Verilator nightly (5.047 devel, v5.046-70 "(mod)") DFG optimizer miscompiles cv32e40x's load-use-hazard halt — one of two *identical* e40x instances executed the boot-ROM `bnez` with the load's address-phase ALU result (`halt_id=0` while `load_stall=1`, combinationally impossible per the RTL) → hart 2 branched to `_copy_from_flash` and spun on the SPI controller forever. `-fno-dfg` alone fixes it; `-O0` fixes it; stable releases are clean. RTL exonerated only after a 7-probe chain (bus → WB → regfile → decode → branch-operand → hazard → FSM) | CRITICAL | All-TITAN SMP demo | Pinned Verilator 5.050 (`/mnt/.../tools/verilator-5.050`, `VERILATOR_PIN` env override) in all `tb/mosaic_soc/run*.sh` |

---

## 8. Risk Register

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| GF180 SRAM bitcell not available | HIGH | MED | Upstream OpenRAM has it; PDK extraction possible |
| OpenRAM GF180 port incomplete | MED | MED | Custom tech.py created; library cells can be auto-generated |
| SRAM area exceeds die budget | HIGH | LOW | 4KB option (~0.05 mm²) fits easily; 32KB (~0.5 mm²) needs verification |
| Ibex prim de-dup blocks full build | MED | MED | Can exclude Ibex from PoC if needed |
| No storage space for PDK run | MED | MED | Use IIC-OSIC-TOOLS container or remote server |
| FreeRTOS kernel integration | MED | MED | Bare-metal firmware works end-to-end; FreeRTOS is enhancement |
| CVA6 area exceeds 1.249 mm² | HIGH | HIGH | Sim-only integration (D-65); excluded from tapeout configs |

---

## 9. Next Actions (Priority Order)

1. **Obtain GF180 SRAM bitcell** (P-06) — extract cell1rw.gds/sp from PDK or copy from upstream OpenRAM
2. **LibreLane pin-binding** (P-01/P-02) — complete `mosaic_soc_core.sv` (`x_heep_system` instantiation) and the pad map
3. **Generate SRAM macros** (P-03) — run OpenRAM with the GF180 PDK to produce 4KB/32KB GDS/LEF/LIB
4. **DRC/LVS signoff + STA** (N-06/N-07) — full LibreLane flow with the GF180 PDK, 50 MHz closure
5. **Scheduling demo in full-SoC sim** — run `mosaic_demo.hex` through the `run_fw.sh` flow (currently build-verified only)
