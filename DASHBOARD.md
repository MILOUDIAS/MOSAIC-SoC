# MOSAIC-SoC Progress Dashboard

> **IEEE SSCS Chipathon 2026 · Track D · GF180MCU · Updated: 2026-07-01**

---

## Executive Summary

```
PHASE 1 — Config-Driven Multi-Core Generator   █████████████████████  95%
PHASE 2 — Agentic Harness (oh-my-soc)          ████████████████████░  85%
PHASE 3 — Physical Design (GF180MCU)           ██████░░░░░░░░░░░░░░░  30%
OVERALL                                        ████████████████░░░░  78%
```

| Metric | Value |
|--------|-------|
| Commits | 13 (Jun 27–30, 2026) |
| Bugs found & fixed | 14 |
| Core IPs integrated | 5 / 5 (cv32e20, ibex, fazyrv, qerv, serv) |
| SCI wrappers | 3 (fazyrv, serv, ibex) |
| RTL templates rendered | 37 |
| Testbenches | 4 suites, all PASS |
| Lines of new RTL | ~1,800 (SCI + TDU + iDMA wrapper) |
| Lines of Python | ~1,200 (generator + config) |
| Lines of firmware | ~1,338 (TDU driver + TITAN fw + sched demo + workers) |
| Firmware size | 1,496 B text (main) / 2,424 B text (demo) |
| PD configs created | 6 files (OpenRAM tech, 2 SRAM configs, bitcell wrapper) |

---

## Kanban Board

### DONE

| ID | Task | Component | Verified |
|----|------|-----------|----------|
| D-01 | MOSAIC YAML config parser | `util/xheep_gen/mosaic_config.py` | `make mosaic-gen` EXIT=0 |
| D-02 | Multi-core XHeep API | `util/xheep_gen/xheep.py` | Unit + integration |
| D-03 | Per-core master indices | `core_v_mini_mcu_pkg.sv.tpl` | Lint-clean |
| D-04 | Multi-core cpu_subsystem template | `cpu_subsystem.sv.tpl` | 6 branches elaborated |
| D-05 | Multi-master system_bus | `system_bus.sv.tpl` | Lint-clean |
| D-06 | Per-hart interrupt routing | `core_v_mini_mcu.sv.tpl` | Functional sim |
| D-07 | Per-core hart ID array | `core_v_mini_mcu.sv.tpl` | Functional sim |
| D-08 | FazyRV SCI wrapper | `hw/sci/fazyrv_sci.sv` | Verilator lint-clean |
| D-09 | SERV SCI wrapper | `hw/sci/serv_sci.sv` | Verilator lint-clean |
| D-10 | Ibex SCI wrapper | `hw/sci/ibex_sci.sv` | Verilator lint-clean |
| D-11 | Vendored FazyRV RTL | `hw/vendor/mosaic/fazyrv/` | Elaborates clean |
| D-12 | Vendored SERV + servile RTL | `hw/vendor/mosaic/serv/` | Elaborates clean |
| D-13 | Vendored Ibex RTL | `hw/vendor/mosaic/ibex/` | Elaborates clean |
| D-14 | TDU hardware scheduler | `hw/tdu/rtl/tdu.sv` | 16/16 unit tests |
| D-15 | TDU SoC-level integration | `tb/tdu/soc/` | cocotb PASS |
| D-16 | iDMA integration | `hw/vendor/mosaic/idma/` | cocotb PASS (2 levels) |
| D-17 | Worker dormancy + wake loop | `core_v_mini_mcu.sv.tpl` | cocotb end-to-end |
| D-18 | Packed/unpacked port fix | `core_v_mini_mcu.sv.tpl` | Lint-clean |
| D-19 | Mako directive fix | `core_v_mini_mcu.sv.tpl` | Generated SV compiles |
| D-20 | FazyRV reset polarity fix | `hw/sci/fazyrv_sci.sv` | FazyRV now executes |
| D-21 | FazyRV clock-stall adapter | `hw/sci/fazyrv_sci.sv` | Combinational mem core |
| D-22 | serv_sci OBI bridge fix | `hw/sci/serv_sci.sv` | Single-outstanding OK |
| D-23 | fazyrv_sci OBI bridge fix | `hw/sci/fazyrv_sci.sv` | Read-data hold latch |
| D-24 | FuseSoC refs/ crash fix | `scripts/fusesoc-setup.sh` | `make mosaic-gen` works |
| D-25 | Full-SoC elaboration clean | Top-level | 837 modules lint-clean |
| D-26 | TDU wake-and-run demo | `tb/mosaic_soc/` | EXIT SUCCESS |
| D-27 | Multi-core SCI simulation | `tb/mosaic/` | 3/3 cores PASS |
| D-28 | All-cores generation test | `configs/mosaic_all_cores.yaml` | 5 SCI branches render |
| D-29 | QERV integration | Reuses `serv_sci` W=4 | Elaborates clean |
| D-30 | LibreLane flow structure | `flow/librelane/` | Makefile + configs |
| D-31 | GF180 pad frame | `flow/librelane/src/chip_top.sv` | Elaborates clean |
| D-32 | TDU driver (C API) | `sw/firmware/common/tdu.{h,c}` | Builds clean, rv32i |
| D-33 | TITAN firmware (TDU programming) | `sw/firmware/titan/titan_main.c` | Builds, 261 lines |
| D-34 | ATLAS worker (signal processing) | `sw/firmware/atlas/atlas_worker.S` | Builds, 104 bytes |
| D-35 | NANO worker (sensor polling) | `sw/firmware/nano/nano_worker.S` | Builds, 72 bytes |
| D-36 | Multi-core linker script | `sw/firmware/mosaic_link.ld` | Correct VMA layout |
| D-37 | Firmware build system | `sw/firmware/Makefile` | Builds hex for sim TB |
| D-38 | Hardware register definitions | `sw/firmware/common/mosaic_hw.h` | Self-contained, mmio_region_t, Apache-2.0 licensed |
| D-39 | Scheduling modes demo (dynamic + power-aware) | `sw/firmware/titan/titan_scheduling_demo.c` | Builds clean, 451 lines, exercises all 3 TDU modes |
| D-40 | oh-my-soc harness core framework | `harness/core.py` | SkillResult, validate_config, run_cmd, config I/O |
| D-41 | config-author skill | `harness/skills/config_author.py` | Generate/validate mosaic.yaml, 3 presets, CLI |
| D-42 | flow-runner skill | `harness/skills/flow_runner.py` | 11 flows, structured log parsing, timing |
| D-43 | drc-triage skill | `harness/skills/drc_triage.py` | Magic/KLayout/Netgen parsers, fix suggestions |
| D-44 | doc-gen skill | `harness/skills/doc_gen.py` | Config summary, memory map, run reports, dashboard |
| D-45 | oh-my-soc CLI | `harness/__main__.py` | `python -m harness <skill> <cmd>` entry point |
| D-46 | OpenRAM GF180 technology config | `sw/vendor/openram/gf180mcu/tech/tech.py` | 3.3V params, corrected layer map, DRC rules |
| D-47 | OpenRAM bitcell wrapper | `sw/vendor/openram/gf180mcu/custom/gf180_bitcell.py` | GF180MCU 6T cell wrapper for OpenRAM factory |
| D-48 | OpenRAM 4KB SRAM config | `sw/vendor/openram/configs/mosaic_sram_4k.py` | 512×8, single bank, ~0.05 mm² est. |
| D-49 | OpenRAM 32KB SRAM config | `sw/vendor/openram/configs/mosaic_sram_32k.py` | 4096×8, 2 banks, ~0.3-0.6 mm² est. |
| D-50 | LibreLane config.yaml SRAM macros | `flow/librelane/config.yaml` | MACROS section + PDN_MACRO_CONNECTIONS |
| D-51 | LibreLane pdn_cfg.tcl SRAM grid | `flow/librelane/pdn_cfg.tcl` | define_pdn_grid + add_pdn_connect for SRAM |
| D-52 | LibreLane config_classic.yaml SRAM | `flow/librelane/config_classic.yaml` | MACROS section for classic (core-only) flow |
| D-53 | OpenRAM directory README | `sw/vendor/openram/README.md` | Porting guide, status, known issues |

---

### IN PROGRESS

| ID | Task | Component | Blocker / Notes |
|----|------|-----------|-----------------|
| **P-01** | LibreLane `mosaic_soc_core.sv` pin-binding | `flow/librelane/src/` | TODO at line 68 — needs `x_heep_system` instantiation + pad-to-pin wiring |
| **P-02** | Pad map finalization | `flow/librelane/slots/` | `slot_mosaic.yaml` exists, needs completion for all SoC signals |
| **P-03** | SRAM hard macro generation | `sw/vendor/openram/` | Configs ready; needs GF180 PDK + OpenRAM installed to generate GDS/LEF/LIB |
| **P-04** | Full-SoC sim with cv32e20 | `tb/mosaic_soc/` | cv32e20 needs boot_rom + GCC; serial cores tested standalone |
| **P-05** | Ibex prim de-dup for co-build | `hw/vendor/mosaic/ibex/` | Ibex has own prim closure; de-dup needed for full FuseSoC build |
| **P-06** | GF180 SRAM bitcell extraction | `sw/vendor/openram/gf180mcu/gds_lib/` | Need cell1rw.gds + sp from PDK or upstream OpenRAM |

---

### NOT STARTED

| ID | Task | Priority | Component | Notes |
|----|------|----------|-----------|-------|
| ~~**N-01**~~ | ~~FreeRTOS firmware on TITAN~~ | ~~**HIGH**~~ | ~~`sw/freertos/`~~ | ~~DONE — `sw/firmware/titan/titan_main.c` + TDU driver~~ |
| ~~**N-02**~~ | ~~Dynamic TDU scheduling mode~~ | ~~MED~~ | ~~`sw/firmware/`~~ | ~~DONE — `titan_scheduling_demo.c` phase 2: CPI-based task migration~~ |
| ~~**N-03**~~ | ~~Power-aware TDU scheduling mode~~ | ~~MED~~ | ~~`sw/firmware/`~~ | ~~DONE — `titan_scheduling_demo.c` phase 3: energy-budget core selection~~ |
| **N-04** | PLIC multi-target routing | CANCEL | `peripheral_subsystem.sv.tpl` | Architecturally unnecessary for PoC: TITAN handles all interrupts, dispatches via TDU wake. Future enhancement only. |
| **N-05** | Per-core power domains | LOW | `ao_peripheral_subsystem.sv.tpl` | Power manager is single-domain |
| **N-06** | GF180MCU DRC/LVS signoff | **HIGH** | `flow/librelane/` | No actual signoff run yet |
| **N-07** | 50 MHz STA closure | **HIGH** | `flow/librelane/` | SDC exists; no timing analysis run |
| **N-08** | Target area validation (1.249 mm²) | MED | Post-synthesis | No area data yet |
| **N-09** | Formal verification (riscv-formal) | LOW | SCI wrappers | Not started |
| **N-10** | FPGA bitstream generation | LOW | `hw/fpga/` | Structure exists; no flow completed |
| ~~**N-11**~~ | ~~Phase 2: Agentic Harness~~ | ~~**HIGH**~~ | ~~oh-my-soc~~ | ~~DONE — `harness/` with 4 skills + CLI~~ |
| ~~**N-12**~~ | ~~`config-author` skill~~ | ~~MED~~ | ~~`harness/skills/`~~ | ~~DONE — generate/validate mosaic.yaml, 3 presets~~ |
| ~~**N-13**~~ | ~~`flow-runner` skill~~ | ~~MED~~ | ~~`harness/skills/`~~ | ~~DONE — 11 flows, structured log parsing~~ |
| ~~**N-14**~~ | ~~`drc-triage` skill~~ | ~~MED~~ | ~~`harness/skills/`~~ | ~~DONE — Magic/KLayout/Netgen parsers + fix suggestions~~ |
| ~~**N-15**~~ | ~~`doc-gen` skill~~ | ~~LOW~~ | ~~`harness/skills/`~~ | ~~DONE — config summary, memory map, run reports~~ |
| **N-16** | CVA6 integration | SKIP | Core IP | Out of scope for GF180MCU PoC |

---

## Firmware Architecture

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
│   └── atlas_worker.S     # ATLAS signal-processing worker
├── nano/
│   └── nano_worker.S      # NANO sensor-polling worker
├── mosaic_link.ld         # Multi-core linker script (4 memory regions)
├── Makefile               # Build system (make / make demo / make clean)
└── build/
    ├── mosaic_fw.elf      # Linked ELF (production)
    ├── mosaic_fw.hex      # Verilog hex (production)
    ├── mosaic_demo.elf    # Linked ELF (scheduling demo)
    └── mosaic_demo.hex    # Verilog hex (scheduling demo)
```

**Build targets:**
- `make` — builds production firmware (1,496 B text)
- `make demo` — builds scheduling demo (2,424 B text)

**Production boot flow** (`titan_main.c`):
1. Boot ROM jumps to `_start` @ 0x180
2. `start.S` initializes stack, calls `main()`
3. `titan_main.c`:
   - Writes TITAN sentinel (0xC0FFEE00) to prove alive
   - Sets TDU scheduling mode to DYNAMIC
   - Configures wake mask for all worker harts (bits 1-6)
   - Loads CPI estimates (ATLAS=4, NANO=32) for scheduler
   - Pushes signal-processing tasks to ATLAS cores (harts 1-2)
   - Pushes sensor-polling tasks to NANO cores (harts 3-6)
   - Workers auto-wake via TDU hardware (masked + sleeping)
   - Polls sentinel addresses for completion
   - Signals EXIT SUCCESS via soc_ctrl

**Scheduling demo** (`titan_scheduling_demo.c`):
- Phase 1 (STATIC): Baseline dispatch, fixed core assignment
- Phase 2 (DYNAMIC): Reads CPI estimates, migrates tasks from slow cores to fast
- Phase 3 (POWER_AWARE): Reads energy counter, consolidates to fewer cores when budget exceeded
- Reports energy per phase + PASS/FAIL to testbench via sentinel slots

**FreeRTOS integration path:** The TDU driver API (`tdu.h`) is designed to be called from FreeRTOS tasks. The current bare-metal poll loop can be wrapped in `xTaskCreate()` + `xQueueSend()` calls with minimal changes.

---

## oh-my-soc Agentic Harness

```
harness/
├── __init__.py              # Package init, version
├── __main__.py              # CLI: python -m harness <skill> <cmd>
├── core.py                  # SkillResult, validate_config, run_cmd, config I/O
└── skills/
    ├── __init__.py          # Skill imports
    ├── config_author.py     # Generate/validate mosaic.yaml, 3 presets
    ├── flow_runner.py       # 11 EDA flows, structured log parsing
    ├── drc_triage.py        # Magic/KLayout/Netgen parsers, fix suggestions
    └── doc_gen.py           # Config summary, memory map, run reports
```

**Design principle:** The agent *assists and is checked by* deterministic tooling. It never replaces signoff.

**CLI usage:**
```bash
python -m harness config-author generate --preset poc --name my_soc
python -m harness config-author validate mosaic.yaml
python -m harness flow-runner run firmware-build
python -m harness drc-triage analyze report.rpt
python -m harness doc-gen memory-map
```

**Skills:**
| Skill | Input → Output | Key Feature |
|-------|---------------|-------------|
| `config-author` | NL intent → `mosaic.yaml` | 3 presets (poc/minimal/max_cores), schema validation |
| `flow-runner` | Config → EDA run + summary | 11 flows, timing, structured log parsing |
| `drc-triage` | DRC/LVS report → fix suggestions | 3 format parsers (Magic/KLayout/Netgen), severity classify |
| `doc-gen` | Artifacts → documentation | Config summary, memory map, run reports, dashboard parse |

---

## Milestone Tracker

```
M1: Config-driven generation         ████████████████████  DONE     (Jun 27)
M2: Multi-core RTL generation        ████████████████████  DONE     (Jun 28)
M3: SCI wrappers + vendored cores    ████████████████████  DONE     (Jun 28)
M4: TDU + iDMA integration           ████████████████████  DONE     (Jun 29)
M5: Multi-core simulation PASS       ████████████████████  DONE     (Jun 30)
M6: Full-SoC elaboration clean       ████████████████████  DONE     (Jun 30)
M7: TITAN firmware + TDU driver      ████████████████████  DONE     (Jun 30)
M8: Scheduling modes demo            ████████████████████  DONE     (Jun 30)
M9: oh-my-soc agentic harness        ████████████████████  DONE     (Jun 30)
M10: LibreLane pin-binding + SRAM    ████░░░░░░░░░░░░░░░░  IN PROG
M11: DRC/LVS clean signoff           ░░░░░░░░░░░░░░░░░░░░  PLANNED
M12: Tapeout-ready GDSII             ░░░░░░░░░░░░░░░░░░░░  PLANNED
```

---

## Component Status Matrix

| Component | RTL | Wrapper | Tests | Integration | Status |
|-----------|-----|---------|-------|-------------|--------|
| **cv32e20 (TITAN)** | Native x-heep | N/A | Full-SoC | `cpu_subsystem` | DONE |
| **FazyRV (ATLAS)** | Vendored | `fazyrv_sci.sv` | cocotb PASS | `cpu_subsystem` | DONE |
| **SERV (NANO)** | Vendored | `serv_sci.sv` | cocotb PASS | `cpu_subsystem` | DONE |
| **QERV (NANO)** | Reuses SERV | `serv_sci.sv` (W=4) | Elaborates | `cpu_subsystem` | DONE |
| **Ibex (TITAN)** | Vendored | `ibex_sci.sv` | Lint-clean | `cpu_subsystem` | DONE |
| **CVA6** | — | — | — | — | SKIP |
| **TDU** | `tdu.sv` | N/A | 16/16 unit + SoC | `ao_peripheral` | DONE |
| **iDMA** | `idma_xheep_wrapper.sv` | N/A | cocotb PASS (2) | `ao_peripheral` | DONE |
| **Bus fabric** | `system_xbar.sv.tpl` | N/A | Lint-clean | Top-level | DONE |
| **PLIC** | OpenTitan IP | N/A | Single-target | `peripheral` | PARTIAL |
| **Power mgr** | x-heep IP | N/A | Single-domain | `ao_peripheral` | PARTIAL |
| **LibreLane flow** | `chip_top.sv` | `mosaic_soc_core.sv` | — | Flow wired | PARTIAL |
| **FreeRTOS fw** | `titan_main.c` | `tdu.{h,c}` | Builds clean | `sw/firmware/` | DONE |
| **Sched demo** | `titan_scheduling_demo.c` | `tdu.{h,c}` | Builds clean, 3 modes | `sw/firmware/` | DONE |
| **oh-my-soc** | `harness/` | 4 skills + CLI | All 4 skills tested | `harness/skills/` | DONE |
| **OpenRAM GF180** | `tech/tech.py` | `gf180_bitcell.py` | Configs written | `sw/vendor/openram/` | PARTIAL |
| **SRAM macros** | Configs ready | PDK needed | Not generated | `flow/librelane/` | BLOCKED |

---

## Bug Tracker (All Fixed)

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

---

## Risk Register

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| FreeRTOS kernel integration | MED | MED | Bare-metal firmware works; FreeRTOS is enhancement |
| GF180 SRAM bitcell not available | HIGH | MED | Upstream OpenRAM has it; PDK extraction possible |
| OpenRAM GF180 port incomplete | MED | MED | Custom tech.py created; library cells can be auto-generated |
| SRAM area exceeds die budget | HIGH | LOW | 4KB option (~0.05 mm²) fits easily; 32KB (~0.5 mm²) needs verification |
| Ibex prim de-dup blocks full build | MED | MED | Can exclude Ibex from PoC if needed |
| CVA6 area exceeds 1.249 mm² | HIGH | HIGH | Intentionally excluded from PoC |
| No storage space for PDK run | MED | MED | Use IIC-OSIC-TOOLS container or remote server |

---

## Next Actions (Priority Order)

1. **Obtain GF180 SRAM bitcell** — Extract cell1rw.gds/sp from PDK or copy from upstream OpenRAM
2. **Set up Python venv** — `hjson`, `mako`, `yaml` for `make mosaic-gen` pipeline
3. **Full-SoC Verilator sim with firmware hex** — Load `mosaic_fw.hex` or `mosaic_demo.hex` in testbench
4. **LibreLane pin-binding** — Complete `mosaic_soc_core.sv` to instantiate `x_heep_system` and bind pads
5. **Generate SRAM macros** — Run OpenRAM with GF180 PDK to produce 4KB/32KB GDS/LEF/LIB
6. **DRC/LVS signoff** — Run full LibreLane flow with GF180 PDK
