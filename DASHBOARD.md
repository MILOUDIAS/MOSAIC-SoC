# MOSAIC-SoC Progress Dashboard

> **IEEE SSCS Chipathon 2026 · Track D · GF180MCU · Updated: 2026-08-17**

---

## 1. At a Glance

```
PHASE 1 — Config-Driven Multi-Core Generator   █████████████████████  99%
PHASE 2 — Agentic Harness (oh-my-soc)          █████████████████████  99%
PHASE 3 — Physical Design (GF180MCU)           ████████████████████░  95%
OVERALL                                        ████████████████████░  95%
```

Phase 3 moved 80 → 95 on 2026-08-16: electrical closure is done on all three blocks
(max-slew 0, max-cap 0, antenna 0, DRC/LVS/XOR/routing 0, one accepted max-fanout
waiver), and 25 MHz is measured. It is **not** 100% because the tapeout tag waits on a
clock target only the track lead can set.

**Headline (2026-08-17): re-review returned GO, and the last electrical gap turned out
not to be one.** The reviewer's second must-close item — *"591 max-slew (worst 5.19 ns vs
the library's 4.0 ns) … all at `ss_125C_4v50`, TT and FF clean"* — was measured against
the wrong corner's limit, and the mistake was **ours**: this dashboard and the closure
report both said "the library's 4.0 ns". `max_transition` in GF180 is declared **per input
pin and per corner** — 4.0 ns at `tt_025C_5v00`, **7.0 ns at `ss_125C_4v50`**, 2.6 ns at
`ff_n40C_5v50` — and `MAX_TRANSITION_CONSTRAINT: 4` applied the *typical* corner's number
at all nine because `PNR_SDC_FILE` and `SIGNOFF_SDC_FILE` were both unset. Measured on the
netlist the reviewer verified:

```
CONTROL   shipped SDC, max_ss_125C_4v50        591 violations   (reproduces exactly)
LIBRARY   per-pin limits, all nine corners       0 violations
worst pin spi_flash_sd_io[3]   limit 7.00   slew 5.19   slack +1.81   MET
```

Dropping the constraint entirely was tried and is **wrong** — it is an optimisation
target, not a reporting threshold, and without it the design sheds 3.10% of cell area and
degrades past the library's *own* limits. The fix is to split PnR from signoff: PnR still
targets 4.0 ns, signoff checks each pin's liberty limit. Across all three blocks the
post-PnR netlists are **byte-identical** to the runs they replace — same silicon, honest
reporting — and max-slew goes **56 → 0, 17 → 0, 49 → 0**. Both slew waivers are retired;
**one waiver remains** (Block A max-fanout 1, real: GF180 declares no `max_fanout` at all).

Also closed: Block C's antenna violation, root-caused to LibreLane's post-DRT repair loop
stopping on its iteration cap rather than on convergence (Tcl `&&` short-circuits, so the
final check never ran). Cost of the fix: **one diode, +4.39 µm²**.

**25 MHz is measured and closes** (`runs/blocka_25mhz`): setup +1.663 ns TNS 0, hold
+0.0662 ns, every hard check 0, GLS `EXIT SUCCESS` 12,399 cycles, same die. The clock now
lives in `configs/mosaic_tapeout_ultra.yaml` as `soc.objectives.target_clock_mhz` — design
intent, derived into `CLOCK_PERIOD` — and is a **request, not an agreed target**.

**Previously (2026-08-02):** the Block A macro is **DRC and LVS clean**, and the RTL is
frozen and tagged (`rtl-freeze-blocka-v2`) in answer to the schematic review — see
[`docs/rtl_freeze_blocka.md`](docs/rtl_freeze_blocka.md) and
[`docs/chipathon_review_response.md`](docs/chipathon_review_response.md).
The macro has been **re-hardened** with the bug-31 fix in it and the electrical repair
enabled: **max-cap 27 → 0, max-fanout 411 → 1, max-slew 2 889 → 591** ~~against the
library's own 4.0 ns limit~~ — against a blanket 4.0 ns SDC constraint, which is the
`tt_025C_5v00` number and not the library's limit at the corner all 591 sat in; see the
2026-08-17 headline above. At *lower* utilization (84.4%) and less wire than before.
`mosaic_tapeout_ultra` hardened to exactly **1117.5 × 1117.5 µm = 1.2488 mm²** (a quarter
of the 2235 µm shared MPW die, 22 pins) now passes the full deck set with nothing skipped:
**Magic DRC 0, KLayout DRC 0, Netgen LVS "circuits match uniquely", XOR 0, antenna 0,
routing DRC 0, 0 power-grid violations, IR drop 120 µV on 5 V**, timing closed at all nine
corners (setup +20.72 ns, hold +0.055 ns, TNS 0). LVS matched the 22-pin contract against
extracted layout rather than taking the wrapper's word for it. Getting there cost three
bugs (28–30), one of them a `soc_ctrl` breakage introduced by an earlier fix and hidden by
`ERROR_ON_SYNTH_CHECKS: false`. ~~**Remaining electrical gap: 591 max-slew violations**~~
— **closed 2026-08-16**, and it was never a gap: 0 against per-pin library limits at all
nine corners. Max-cap and max-fanout stand at 0 and 1.
Area came down 3.903 → 1.249 mm² (−68%) through measured cuts, not estimates; see
[`docs/area_study_gf180_min_soc.md`](docs/area_study_gf180_min_soc.md) §8c–§8g. The MPW
block plan is [`docs/padrinrg/padring_proposal.jpg`](docs/padrinrg/padring_proposal.jpg).
The hardening is now reproducible on any machine: the checked-in LibreLane configs carry
**no absolute paths** — `flow/librelane/scripts/gen_filelist.py` resolves the source list
from the FuseSoC manifest at run time — so a fresh clone hardens with `make mosaic-gen
MOSAIC_CFG=configs/mosaic_tapeout_ultra.yaml` then
`flow/librelane/experimental/run_signoff.sh`, no hand-editing (D-90).

**Previously:** the SoC boots the production path **flash-only** — boot ROM → SPI-XIP
TITAN → CRC-checked worker loading → 6-worker TDU dispatch → **EXIT SUCCESS** — on top of
a hardened generator (strict shared core registry, heterogeneous per-hart RTL, topology-
derived firmware/linkers/flash manifests, content-addressed builds, fail-closed `target:
tapeout`). The harness gained a **built-in agent runtime** (bounded model/tool loop with
approval gates + evidence binding), and a beginner `tutorial/` walks the whole stack.

| Metric | Value |
|--------|-------|
| Bugs found & fixed | 35 (see [Bug Tracker](#7-bug-tracker-all-fixed)) — 9 new from the physical flow; one (28) was introduced by the fix for another; **31 was CRITICAL** (SERV could not load from flash); 32–33 were measurement/flow faults, 34–35 are PDK/tooling findings, not RTL |
| Core IPs integrated | 12 / 12 (cv32e20, cv32e40x, cva6†, ibex, fazyrv, hazard3, picorv32, qerv, serv, snitch, rocket†, boom†) — †sim-only |
| SCI wrappers | 9 (fazyrv, serv, ibex, picorv32, snitch, cva6, rocket, boom, hazard3 — qerv reuses serv) |
| Bus fabrics | 3 (OBI crossbar · logarithmic interconnect · FlooNoC) |
| Shipped configs | 33 under `configs/` — incl. `mosaic_tapeout_ultra` (the Block A candidate) |
| Platform knobs | 8 selectable blocks: `dma` `debug` `plic` `spi_mode` `multicore_timer` `gpio_ao` `ao_rv_timer` `ao_fast_intr` |
| Test suites | **33-step sweep green** (`scripts/run_sweep.sh`, 42 min) + tb-matrix coverage; generator pytests **1 233 passed / 1 skipped** across 47 files |
| Harness skills | 10 + built-in agent runtime (`./oh-my-soc` executable, omp-style driver picker, `oh-my-soc agent` dispatch; cards in `.claude/skills/` for Claude Code + omp) |
| Firmware size | 1,592 B text (production) · 2,440 B text (sched demo) |
| Commits | 145 on `mld-rtl-freeze` (74 ahead of `origin/dev-mld`). `mld-rtl-freeze` is the Chipathon branch and was fast-forwarded to `mld-exp` on 2026-08-16 |

### What passes today

Last full sweep: **2026-08-03** — `scripts/run_sweep.sh`, **33/33 green** in 42 min.
The previous one was 2026-07-12, and three weeks of drift cost four failures
(bugs 36-39): CVA6 unbuildable on any bus but floonoc, Hazard3's headers never
staged, and a dormancy test asserting a contract the generator had deliberately
changed. Two were masked by a sibling suite sharing a row in the table below —
the sweep is now a script so the claim and the check cannot drift apart again.

The **2026-07-31 area / physical pass** added the eight platform knobs above, re-verified every shipped
config, and took `mosaic_tapeout_ultra` through LibreLane to a routed GDS in the
Chipathon Block A envelope (0 routing DRC, 0 antenna, timing closed all corners).

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
| TL→OBI bridge unit TB | `tb/tl_obi/run.sh` | TileLink-C Acquire/Release/Get/Put, window translation, denied, bursts | 21/21 |
| Berkeley RV64 wake demos | `MOSAIC_CFG=configs/mosaic_{rocket,boom,berkeley}.yaml tb/mosaic_soc/run.sh` | Rocket + BOOM v3 tiles (sim-only) boot through the DRAM alias, write sentinels through the uncached CLINT window; combined config runs both in ONE build | EXIT SUCCESS ×3 |
| Generic per-hart boot TB | `tb/mosaic_soc/run_generic.sh` | consumes generated boot metadata, builds ABI-correct per-image firmware (mixed RV32E/RV32/RV64), requires **every** configured hart to report | EXIT SUCCESS |
| tb-matrix combination coverage | `./oh-my-soc tb-matrix run --tier {validate,render,sim}` | the integration SPACE: 248-config pairwise covering array (validate), mcu-gen render, all-hart liveness on curated corners | 248/248 validate; 3 sim EXIT SUCCESS incl. 2 never-tested combos (2026-07-19) |
| Flash-only production boot | `tb/mosaic_soc/run_fw.sh` (flash path) | boot ROM → SPI-XIP TITAN → CRC-checked worker loading → 6-worker TDU dispatch, no sim-side memory preload | EXIT SUCCESS |
| **Block A from a prompt** | `./demo/03_blocka_from_prompt.sh` | the frozen tapeout config is reachable from one natural-language prompt — all 16 fields including the 8 platform knobs — and the capability gate refuses the same prompt when a claim is false | 16/16 fields, 2 false claims refused (2026-08-03) |
| **Gate-level simulation (Block A)** | `tb/gls/run_gls.sh` | the POST-P&R netlist -- the gates in the GDS -- boots XIP from a behavioural flash through only the 22 bonded pins, no backdoor loads | EXIT SUCCESS in **12 399 cycles** vs RTL's ~12 400 (2026-08-03) |
| **UART bring-up (Block A)** | `MOSAIC_CFG=configs/mosaic_tapeout_ultra.yaml tb/mosaic_soc/run_uart.sh` | TX FIFO depth is really 4 (the area cut), polled TX byte-for-byte against the UART DPI log, RX via system loopback; reads its message from flash, so it also regresses bug 31 | EXIT SUCCESS (2026-08-02) |
| Generator + harness pytests | `pytest test/test_x_heep_gen -m "not slow"` | config registry, per-hart RTL gen, software gen, build manifests, target capabilities, harness skills, agent runtime, tb-matrix coverage, LibreLane filelist, agent CLI surface | **672 pass** (2026-08-03) |

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
M15: Harness v2 + Hazard3 integration  ████████████████████  DONE     (Jul 12)
M16: Generator hardening + flash boot  ████████████████████  DONE     (Jul 13)
M17: Area reduction 3.903 → 1.249 mm²  ████████████████████  DONE     (Jul 31)
M18: Block A routed GDS (22 pins)      ████████████████████  DONE     (Jul 31)
M12: LibreLane pin-binding + SRAM      ████░░░░░░░░░░░░░░░░  IN PROG  (not needed for the MPW macro path)
M13: DRC/LVS clean signoff             ████████████████████  DONE     (Aug 01, nothing skipped)
M20: RTL freeze + review response      ████████████████████  DONE     (Aug 02, rtl-freeze-blocka-v2)
M21: Gate-level simulation             ████████████████░░░░  DONE*    (Aug 03; functional yes, timing-annotated blocked)
M19: Block A power delivery (PSM)      ████████████████████  DONE     (Aug 01, 0 grid violations)
M22: Re-review GO + slew closed        ████████████████████  DONE     (Aug 16; 591 → 0 vs library limits, both slew waivers retired)
M23: Blocks B and C signed off         ████████████████████  DONE     (Aug 16; all three at 0 on every hard check, C's antenna closed)
M14: Tapeout-ready GDSII               ██████████████████░░  IN PROG  ← blocked ONLY on the track lead locking a clock
```

**M14 is no longer blocked on us.** Electrical closure is done: max-slew 0, max-cap 0,
antenna 0, DRC/LVS/XOR/routing 0, and one accepted max-fanout waiver. 25 MHz is measured
and closes. What remains is a decision by the track lead / integration team, plus the
`ifnone` question for the organizers — see §9.

---

## 3. Work Board

### In progress

| ID | Task | Component | Blocker / Notes |
|----|------|-----------|-----------------|
| **P-07** | ~~DRC + LVS on the Block A GDS~~ **DONE 2026-08-01** | `flow/librelane/experimental/` | All decks clean via `config_blocka_signoff.yaml` (no `--skip`). Succeeded by **P-10** (re-harden after bug 31) and **P-11** (repair 2 889 max-slew / 411 max-fanout / 27 max-cap violations, which no deck checks) |
| **P-08** | ~~Block A power delivery (`PSM-0069`)~~ **RESOLVED 2026-08-01** | `flow/librelane/experimental/` | Ring restored on Metal4/Metal5 by *omitting* `PDN_CORE_{VERTICAL,HORIZONTAL}_LAYER` — `pdn_cfg.tcl` then defaults them to the strap layers and leaves the three `info exists`-guarded `add_pdn_connect` calls dormant, so neither `PDN-0186` nor bug 27 recurs. `config_blocka_signoff.yaml` measures `PSM-0040 all shapes connected` on both nets and **0 power-grid violations** |
| **P-10** | ~~Re-harden Block A with the bug-31 fix~~ **DONE 2026-08-02** | `flow/librelane/experimental/` | Re-ran the full signoff on RTL containing the SERV ext-Wishbone fix. All decks clean again at *lower* utilization (84.4%) than the pre-fix run, and the electrical repair landed with it: max-cap 27 → 0, max-fanout 411 → 1, max-slew 2 889 → 591. Tracked deliverable is `runs/blocka_signoff/final/` (D-84) |
| **P-11** | Repair the remaining 591 max-slew violations | `flow/librelane/experimental/` | **OPEN — the last known gap to a submittable macro.** Worst 5.19 ns against the library's own 4.0 ns. No deck checks these and setup/hold closure does not imply them: at `CLOCK_PERIOD: 100` the resizer has ~21 ns of slack and so no timing pressure to repair transitions. Two global levers were tried and *measured to hurt* — `CTS_MAX_CAP` made capacitance worse, `bufz_8` pads made slew worse (those pads are input-slew limited). Needs per-net work |
| **P-09** | Confirm the Block A pin contract | MPW integrator | 22 pins fixed; `bufz_4` QSPI drive provisional; `status_o[6:0]` must be bonded |
| **P-01** | LibreLane `mosaic_soc_core.sv` pin-binding | `flow/librelane/src/` | TODO at line 68. *Chip-level only — the MPW path ships a macro, so this is no longer on the critical path* |
| **P-02** | Pad map finalization | `flow/librelane/slots/` | `slot_mosaic.yaml` is a 68-pad chip ring. *Not used by Block A (22-pin macro, shared MPW ring)* |
| **P-03** | SRAM hard macro generation | `sw/vendor/openram/` | Configs ready. *Deprioritised: PDK cuts measured area-negative below ~512 B (area study §8f)* |
| **P-05** | Ibex prim de-dup for co-build | `hw/vendor/mosaic/ibex/` | Ibex has own prim closure; de-dup needed for full FuseSoC build |
| **P-06** | GF180 SRAM bitcell extraction | `sw/vendor/openram/gf180mcu/gds_lib/` | Need cell1rw.gds + sp from PDK or upstream OpenRAM |

### Backlog

| ID | Task | Priority | Component | Notes |
|----|------|----------|-----------|-------|
| **N-06** | ~~GF180MCU DRC/LVS signoff~~ | ~~HIGH~~ | `flow/librelane/` | ✅ **DONE 2026-08-01** (re-run 08-02 with the bug-31 fix). Every deck ran with nothing skipped: Magic DRC 0, KLayout DRC 0, Netgen LVS *"circuits match uniquely"*, XOR 0, antenna 0, IR drop 120 µV. Landed as P-07 / D-84. What remains is electrical, not deck: 591 max-slew (P-11) |
| **N-07** | ~~50 MHz~~ STA closure | **HIGH** | `flow/librelane/` | **Re-scoped.** Multi-corner STA now runs and Block A CLOSES at 10 MHz: setup +20.67 ns, hold +0.075 ns, TNS 0 at every corner. 50 MHz was never re-attempted after the clock was relaxed to cut timing-repair buffers (0.326 → 0.114 mm²). **Decide whether 50 MHz is still a requirement** |
| **N-08** | ~~Target area validation (1.249 mm²)~~ | ~~MED~~ | Post-synthesis + P&R | ✅ **DONE 2026-07-31.** Block A hardened to exactly 1117.5 × 1117.5 µm = **1.2488 mm²** — the Chipathon slot. Full measured path 3.903 → 1.249 mm² in area study §8c–§8g. Moved to the Done log as D-81/D-84 |
| **N-05** | Per-core power domains | LOW | `ao_peripheral_subsystem.sv.tpl` | Power manager is single-domain |
| **N-09** | Formal verification (riscv-formal) | LOW | SCI wrappers | Not started |
| **N-10** | FPGA bitstream generation | LOW | `hw/fpga/` | Structure exists; no flow completed |

**Cancelled / out of scope:** N-04 PLIC multi-target routing (TITAN handles all interrupts,
dispatches via TDU wake — future enhancement only) · N-16 CVA6 tapeout integration (area
budget — **sim-only** CVA6 support landed as D-65/D-66 on 2026-07-11).
Completed backlog items (N-01..03 firmware, N-11..15 harness, P-04 full-SoC sim) live in
the Done log below as D-32..45 and D-60.

### Done — by area

Seventy-eight deliverables, grouped by area. IDs are stable (referenced elsewhere in the repo).

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
| D-67 | TileLink-C→OBI window bridge (Acquire/GrantData/GrantAck refills, Release(Data) writebacks, uncached Get/Put; DRAM-alias code window + uncached CLINT→sentinel / PLIC→TDU windows) | `hw/vendor/mosaic/tl_obi/xheep_tilelink_to_obi.sv`, `tb/tl_obi/` | Self-checking unit TB 21/21 (Verilator 5.050) |
| D-68 | Rocket + BOOM v3 (RV64, **sim-only**) tile extraction: one chipyard 1.14.0 hetero elaboration (`MosaicRocketBoomConfig`, JDK17 + firtool 1.75.0), 299-module closure vendored with automated RESET_VECTOR re-parameterization | `hw/vendor/mosaic/berkeley/` (extract_tile_closure.py, MosaicConfigs.scala), `hw/sci/{rocket,boom}_sci.sv` | `mosaic_rocket.yaml` + `mosaic_boom.yaml` wake demos EXIT SUCCESS (2 RV64 workers each); tapeout exclusion stands |
| D-69 | Combined Berkeley demo: cv32e20 TITAN + Rocket ATLAS + BOOM NANO in ONE Verilator build (single-elaboration namespace — no module collisions) | `configs/mosaic_berkeley.yaml` | EXIT SUCCESS — TDU wakes both RV64 tiles; sentinels land at 0x3004/0x3008 through the uncached CLINT window |
| D-70 | oh-my-soc Phase-2 harness completed: 8 skills (config-author/wake-demo, **soc-from-prompt** deterministic NL grammar + gated pipeline, flow-runner ×18 flows with EXIT SUCCESS gates, **wrapper-smith**, **tb-smith**, drc-triage, doc-gen, topo-viz); registries AST-single-sourced; shared `.claude/skills/` cards (Claude Code + omp) + `.omp/tools/` shim; fixed 3 live harness bugs (missing subprocess import, broken config argv, `"no EXIT SUCCESS"` substring false-positive) | `harness/`, `.claude/skills/`, `.omp/tools/oh-my-soc.ts` | `soc-from-prompt run "<prompt>" --run` → wake demo **EXIT SUCCESS** (no LLM); pytest 116 |
| D-71 | wrapper-smith mechanism: port-parse ladder (verible→yosys→regex), 9-family weighted classifier, clone-proven scaffold of all 8 integration touchpoints (idempotent, marker-guarded, dry-run first) | `harness/skills/wrapper_smith.py`, `harness/templates/wrapper/` | Ground-truth corpus: all integrated cores classify correctly (≥0.94 conf); picorv32 regen-diff = provenance banner only |
| D-72 | **Hazard3 (RP2350 core) integrated BY the mechanism**: analyze → ahb_split @ 1.00 (new family, real AHB→OBI template) → scaffold (45 files + 5 edits) → agent-fill (63-port map, irq/boot/tie-offs) → tb-smith TB PASS (229 cycles) → wake demo | `hw/vendor/mosaic/hazard3/` (@ 8af99293, Apache-2.0), `hw/sci/hazard3_sci.sv`, `configs/mosaic_hazard3.yaml`, `tb/sci/hazard3/` | Full-SoC TDU wake demo **EXIT SUCCESS**; tapeout-eligible |
| D-73 | GitHub-core completion + executable UX: `wrapper-smith fetch <url>[@commit]` (pinned clone, license detect w/ GPL gate, provenance → vendored .core header), auto sci.core `depend:` edge (only with a vendor .core — no dangling VLNVs) + post-apply FuseSoC-graph smoke; `./oh-my-soc` launcher + pyproject console script; omp-style driver picker (`setup`: deterministic/claude/omp/api, keys never stored) + `agent` dispatch + optional `--llm` intent translation (anthropic/openai-compatible, grammar fallback) | `harness/` (llm.py, skills/setup_wizard.py), `oh-my-soc`, `pyproject.toml` | pytest **128**; fetch/scaffold/depend/smoke verified live on hazard3; wake demo re-PASS |
| D-74 | **Generator hardening** (2026-07-13): strict shared core registry (topology/ISA/core params/boot layout/sim-only/target capabilities), heterogeneous per-hart RTL gen (OBI masters, boot addrs, reset/wake/park, IRQs, debug masks, PLIC contexts, CLINT state, TDU routing, iDMA ports), topology-derived fw headers + linkers + startup contracts + flash manifests + authenticated cold boot, content-addressed isolated builds (source hashing, drift rejection, snapshot FuseSoC staging), **fail-closed `target: tapeout`** (only the canonical GF180 7-hart PoC, requires real bound RTL + SRAM views); unsupported combos rejected explicitly | `util/xheep_gen/{core_registry,build_manifest,software_gen,pack_flash,plic_gen}.py`, `mcu_gen.py` | 249 pytests; canonical 7-hart **607-file** full-SoC run EXIT SUCCESS; **flash-only production boot** (boot ROM → SPI-XIP → CRC worker load → 6-worker dispatch) EXIT SUCCESS; generated startup compiles under RV32E |
| D-75 | **Built-in agent runtime**: bounded model/tool/replanning loop with typed tools, approval gates, evidence tracking + failure recovery; live terminal events, journals, streaming subprocess output, omp-style incremental tool cards; streaming Anthropic + OpenAI-compatible tool adapters; `tb-soc-generic` flow (generated boot metadata → ABI-correct per-image firmware, every configured hart must report before EXIT SUCCESS); integration completion bound to **fresh** evidence (analysis + apply + FuseSoC smoke + unit TB PASS + generic full-SoC run — stale evidence disqualified) | `harness/{agent,agent_tools,events,llm}.py`, `harness/EVALUATION.md`, `tb/mosaic_soc/{run_generic.sh,prog_generic/}` | `test_agent_runtime.py` suite; before/after documented in EVALUATION.md; mixed RV32E/RV32/RV64 image + TB PASS/watchdog-race fixes |
| D-76 | Beginner tutorial: generator → harness → opencode/go walkthroughs, troubleshooting guide, verified config, executable end-to-end script, build-manifest inspector | `tutorial/` (01-generator, 02-harness, 03-opencode-go, run_all.sh, configs/tutorial_soc.yaml, inspect_manifest.py) | `tutorial/run_all.sh` runs clean; + `mosaic_{rocket,boom}_titan.yaml` configs |
| D-77 | General multicore SoC generator roadmap — proposition for a next-generation generator architecture | `docs/general_multicore_soc_generator_roadmap.md` (+ `docs/source/images/general_multicore_soc_generator.{mmd,svg,png}`) | Doc + diagram committed (Jul 17); team decision pending |
| D-78 | **tb-matrix skill — combination-coverage testing of the SoC integration space** (branch `tb-matrix`): axes derived live from `core_registry.py` (cores × roles × counts × second-worker heterogeneity × ISA/param variants × bus × sched mode × SRAM × peripherals × topology shape); deterministic greedy **pairwise covering array** (248 configs — every legal value pair covered, 68 illegal pairs reported *blocked with reason*); curated 30-config sim boundary set; tiered gates validate → mcu-gen render → `run_generic.sh` all-hart liveness, crash-safe resume in `build/tb_matrix/report.json`; wired into CLI, agent runtime (`tb_matrix_plan`/`tb_matrix_run`), omp shim + skill card | `harness/skills/tb_matrix.py`, `.claude/skills/tb-matrix/`, `test/test_x_heep_gen/test_tb_matrix.py` | validate tier 248/248 pass; 1 render pass; first sim-tier config (cv32e20 TITAN + **BOOM RV64 worker**) **EXIT SUCCESS** in 183 s; pytest **439** (28 new: pair-coverage proof, oracle validity of every synthesized config, registry-growth sync) |

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
| D-48 | OpenRAM 512 B SRAM config | `sw/vendor/openram/configs/mosaic_sram_512b.py` | 512×8 = 512 bytes, single bank, ~0.05 mm² est. (unverified) |
| D-49 | OpenRAM 4 KiB SRAM config | `sw/vendor/openram/configs/mosaic_sram_4k.py` | 4096×8 = 4 KiB, 2 banks, ~0.3-0.6 mm² est. (unverified) |
| D-50 | LibreLane config.yaml SRAM macros | `flow/librelane/config.yaml` | MACROS section + PDN_MACRO_CONNECTIONS |
| D-51 | LibreLane pdn_cfg.tcl SRAM grid | `flow/librelane/pdn_cfg.tcl` | define_pdn_grid + add_pdn_connect for SRAM |
| D-52 | LibreLane config_classic.yaml SRAM | `flow/librelane/config_classic.yaml` | MACROS section for classic (core-only) flow |
| D-53 | OpenRAM directory README | `sw/vendor/openram/README.md` | Porting guide, status, known issues |
| D-92 | Selectable platform blocks (8 knobs) | `util/xheep_gen/core_registry.py`, `mosaic_config.py` | `dma` `debug` `plic` `spi_mode` `multicore_timer` `gpio_ao` `ao_rv_timer` `ao_fast_intr`; defaults preserve behaviour |
| D-79 | Template gates + tie-offs for every optional block | `hw/core-v-mini-mcu/*.tpl`, `hw/vendor/xheep/spi/rtl/spi_subsystem.sv.tpl` | Removed blocks answer error+ready, never left undriven |
| D-80 | GF180 cell bindings | `hw/asic/gf180/{tc_clk,gf180_sram_blackbox,sram_wrapper}.sv` | ICG bind (no latch cell in GF180), attributed blackboxes, cut-by-depth SRAM |
| D-81 | GF180 area study §8c–§8g | `docs/area_study_gf180_min_soc.md` | 3.903 → 1.249 mm², every step measured |
| D-82 | `mosaic_tapeout_ultra` config | `configs/mosaic_tapeout_ultra.yaml` | The Block A candidate: 2× SERV, UART, XIP, 128 B scratchpad |
| D-83 | Chipathon Block A 22-pin macro | `flow/librelane/experimental/mosaic_block_a.sv` | Exposes 22 pins, terminates 251 ports internally |
| D-84 | **Block A signed-off GDS** | `flow/librelane/experimental/runs/blocka_signoff/final/` | 1117.5 µm square. Magic DRC 0, KLayout DRC 0, Netgen LVS "circuits match uniquely", XOR 0, antenna 0, routing DRC 0, IR drop 120 µV. Re-hardened 2026-08-02 with the bug-31 fix and post-GRT electrical repair: max-cap 0, max-fanout 1, max-slew 591. Reproducible from a fresh clone since D-90 — the config that built it no longer names a path from this machine |
| D-86 | **RTL freeze record + review response** | `docs/rtl_freeze_blocka.md`, `docs/chipathon_review_response.md`, tag `rtl-freeze-blocka-v1` | Frozen config, verification trace, 22-pin map, waivers, tool versions; point-by-point answer to the schematic review. Open item 8 (absolute paths in the LibreLane configs) closed 2026-08-03 by D-90 |
| D-89 | **Prompt → tapeout config showcase** | `demo/03_blocka_from_prompt.sh`, `harness/skills/soc_from_prompt.py` | The Block A part generated from one prompt, field-for-field identical to the hand-written config; false `tapeout` claims refused by the capability gate |
| D-88 | **Gate-level simulation** | `tb/gls/` | Functional GLS on the routed netlist passes cycle-for-cycle with RTL. Timing-annotated GLS blocked: PDK models use `ifnone` on edge-sensitive paths (illegal per IEEE 1364-2005 §14.2.6) and CVC segfaults at this scale |
| D-87 | **UART bring-up test** | `tb/mosaic_soc/run_uart.sh`, `prog_uart/uart.S` | TX FIFO depth measured = 4, polled TX verified against the UART DPI log, RX via loopback. EXIT SUCCESS. Doubles as the bug-31 regression |
| D-85 | `test_dma_selection.py` | `test/test_x_heep_gen/` | 71 tests pinning the knob contracts + the documented xbar-master limitation |
| D-91 | **Executable regression sweep** | `scripts/run_sweep.sh` | The 33 suites this document claims, as a script instead of a table to copy commands out of. Exits non-zero on any failure so it can gate a merge, checks a success MARKER as well as the exit status (several suites exit 0 while printing a failure), and reports what `--only` excluded rather than letting a partial run read as a full one. First run found bugs 36-39 |
| D-90 | **Run-time LibreLane filelist** — the hardening configs carry no absolute paths | `flow/librelane/scripts/gen_filelist.py`, `flow/librelane/experimental/run_signoff.sh` | `VERILOG_FILES` + `VERILOG_INCLUDE_DIRS` resolved from the FuseSoC manifest at run time — the D-59 approach, now on the hardening flow. Configs 767 → 241 and 657 → 131 lines, ~526 absolute paths gone. `--verify` reproduced the old list exactly (507/507 files) and a run from the composed config synthesised to 854 954 µm² / 33 852 cells / 0 check errors — identical to the signoff. If the RTL has not been generated the runner stops rather than reaching for whatever bundle is on disk. Guarded by `test_librelane_filelist.py` (8 tests: no config may regain an absolute path or a hand-pasted source list) |

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
| **Hazard3 (ATLAS/NANO)** | Vendored `8af99293` (Apache-2.0) | `hazard3_sci.sv` (AHB-Lite→OBI) | unit TB PASS + full-SoC wake demo | `cpu_subsystem` (integrated BY wrapper-smith) | DONE — tapeout-eligible |
| **Rocket (ATLAS, sim-only)** | Vendored chipyard 1.14 tile closure | `rocket_sci.sv` (TL-C→OBI) | Full-SoC wake demo | `cpu_subsystem` | DONE (sim) — excluded from tapeout |
| **BOOM v3 (NANO, sim-only)** | Vendored chipyard 1.14 tile closure | `boom_sci.sv` (TL-C→OBI) | Full-SoC wake demo | `cpu_subsystem` | DONE (sim) — excluded from tapeout |
| **TDU** | `tdu.sv` | N/A | 22/22 unit + SoC | `ao_peripheral` | DONE |
| **iDMA** | `idma_xheep_wrapper.sv` | N/A | cocotb PASS (2) | `ao_peripheral` | DONE |
| **Bus fabric — obi** | `system_xbar.sv.tpl` | N/A | wake demo + fw sim | Top-level | DONE |
| **Bus fabric — log** | `system_xbar.sv.tpl` + LIC | N/A | tb/log_xbar 5/5 + wake demo | Top-level | DONE |
| **Bus fabric — floonoc** | floogen + `axi_obi` bridges | N/A | bridge/NoC cocotb + wake demo | Top-level | DONE |
| **TITAN firmware** | `titan_main.c` | `tdu.{h,c}` | Full-SoC EXIT SUCCESS | `sw/firmware/` | DONE |
| **Sched demo** | `titan_scheduling_demo.c` | `tdu.{h,c}` | Builds clean, 3 modes | `sw/firmware/` | DONE |
| **oh-my-soc** | `harness/` | 10 skills + agent runtime + `./oh-my-soc` CLI | pytest + live hazard3 fetch→scaffold→TB→wake proof | `harness/` | DONE |
| **PLIC** | OpenTitan IP | N/A | Single-target | `peripheral` | PARTIAL |
| **Power mgr** | x-heep IP | N/A | Single-domain | `ao_peripheral` | PARTIAL |
| **LibreLane flow (chip)** | `chip_top.sv` | `mosaic_soc_core.sv` is a stub | — | Flow wired | PARTIAL — not needed for the MPW macro path |
| **LibreLane flow (Block A)** | `mosaic_block_a.sv` | 22 pins, ties off 251 ports | Signoff GDS: DRC/LVS/XOR/antenna/IR all clean, nothing skipped | `flow/librelane/experimental/` | **SIGNED OFF** — open: 591 max-slew (P-11) |
| **GF180 cell bindings** | `tc_clk.sv` ICG, SRAM blackboxes, `bufz_4` | — | Synthesised clean | `hw/asic/gf180/` | DONE |
| **OpenRAM GF180** | `tech/tech.py` | `gf180_bitcell.py` | Configs written | `sw/vendor/openram/` | PARTIAL |
| **SRAM macros** | Configs ready | PDK cuts bound in `hw/asic/gf180/` | Not generated | `flow/librelane/` | DEPRIORITISED — measured area-negative below ~512 B |

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
├── __main__.py              # CLI: ./oh-my-soc <skill> <cmd> (also python -m harness)
├── core.py                  # SkillResult, registry-synced validation, run_cmd, config I/O
├── agent.py                 # Built-in agent runtime: bounded model/tool/replanning loop,
│                            #   typed tools, approval gates, evidence binding
├── agent_tools.py           # Typed tool registry exposed to the agent loop
├── events.py                # Live terminal events, journals, streaming subprocess output
├── llm.py                   # Streaming Anthropic + OpenAI-compatible tool adapters
├── EVALUATION.md            # Before/after evaluation of the agent runtime
└── skills/
    ├── config_author.py     # Generate/validate mosaic.yaml, presets, wake-demo configs
    ├── soc_from_prompt.py   # Prompt→SoC: NL grammar + gated pipeline (no-LLM fallback)
    ├── flow_runner.py       # 19 EDA/sim flows, EXIT SUCCESS gates, structured log parsing
    ├── wrapper_smith.py     # fetch/analyze/classify/scaffold any open-source core
    ├── tb_smith.py          # Generated self-checking single-hart TBs + wake demo
    ├── tb_matrix.py         # Combination coverage: registry axes → pairwise array → tiered gates
    ├── drc_triage.py        # Magic/KLayout/Netgen parsers, fix suggestions
    ├── doc_gen.py           # Config summary, memory map, run reports
    ├── topo_viz.py          # Config checks + interactive bus-topology HTML
    └── setup_wizard.py      # First-run driver picker (deterministic/claude/omp/api)
```

**Design principle:** the agent *assists and is checked by* deterministic tooling. It
never replaces signoff. The built-in runtime enforces this structurally: integration
completion is bound to **fresh** evidence (current analysis, apply, FuseSoC smoke,
unit-TB PASS, generic full-SoC run) — stale or unrelated evidence never qualifies.

| Skill | Input → Output | Key feature |
|-------|---------------|-------------|
| `soc-from-prompt` | NL request → validated SoC + sim | Gated pipeline: config → topo check → mcu-gen render → wake demo EXIT SUCCESS; deterministic grammar, optional `--llm` |
| `config-author` | Intent → `mosaic.yaml` | Presets + wake-demo configs, registry-synced schema validation |
| `wrapper-smith` | Core RTL (or GitHub URL) → SCI integration | fetch w/ license gate + provenance, 9-family classifier, 8-touchpoint scaffold, FuseSoC smoke |
| `tb-smith` | Wrapped core → verified core | Generated self-checking TB (dormancy/wake/sentinel) + full-SoC wake demo gate |
| `tb-matrix` | Registry axes → tested integration space | Pairwise covering array (blocked pairs reported w/ reason) + curated sim corners; validate/render/sim tiers, resumable report |
| `flow-runner` | Config → EDA run + summary | 19 flows, EXIT SUCCESS gates, timing, structured log parsing |
| `drc-triage` | DRC/LVS report → fix suggestions | 3 format parsers, severity classification |
| `doc-gen` | Artifacts → documentation | Config summary, memory map, run reports |
| `topo-viz` | Config → semantic checks + topology HTML | Per-fabric rendering (obi/log/floonoc), self-contained SVG+JS |
| `setup` | First run → driver config | deterministic/claude/omp/api; API keys never stored (env-var name only) |

```bash
./oh-my-soc setup                                  # first-run driver picker
./oh-my-soc agent "a cv32e20 controller with two picorv32 workers and a uart"
./oh-my-soc soc-from-prompt run "..." --run        # same pipeline, deterministic, no LLM
./oh-my-soc wrapper-smith fetch https://github.com/Wren6991/Hazard3@<commit>
./oh-my-soc wrapper-smith analyze <top.sv> && ./oh-my-soc wrapper-smith scaffold <core> --apply
./oh-my-soc tb-smith generate <core> && ./oh-my-soc tb-smith wake-demo <core>
./oh-my-soc tb-matrix run --tier validate && ./oh-my-soc tb-matrix run --tier sim --limit 5
```

Agent surfaces: shared skill cards in `.claude/skills/` (read by Claude Code **and**
oh-my-pi), the `.omp/tools/oh-my-soc.ts` tool shim with incremental tool cards, and the
built-in `oh-my-soc agent` runtime for API-driven sessions.

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
| 22 | `soc.dma: none` left `ao_peripheral_slv_rsp[DMA_IDX]` and `[DMA_CH0_IDX]` undriven — the DMA still occupies its slots in the AO register demux, so any access to that window would hang the bus forever | CRITICAL | `yosys check` (Checker.YosysSynthChecks) | `ao_peripheral_subsystem.sv.tpl` — answers error+ready |
| 23 | `soc.spi_mode: xip_only` gated the OpenTitan host but left the `w25q128jw_controller` branch live; that controller exists only to drive the host, so its `reg_mux` response came back undriven | CRITICAL | `yosys check` | `spi_subsystem.sv.tpl` — w25q gated off in xip_only, `ot_reg_rsp_o` tied error+ready |
| 24 | **GF180 has no latch cell.** pulp's generic `tc_clk_gating` models gating with a behavioural latch, which survives synthesis as an unmapped `$_DLATCH_N_` — nothing for the placer to place | HIGH | Checker.YosysUnmappedCells | `hw/asic/gf180/tc_clk.sv` — rebound to the library ICG `icgtp_1` |
| 25 | The PDK's SRAM `__blackbox.v` views are empty modules with **no `(* blackbox *)` attribute**, so yosys reports every `Q` bit as "used but has no driver" — 32 errors for a 4-cut bank | HIGH | Checker.YosysSynthChecks | `hw/asic/gf180/gf180_sram_blackbox.sv` |
| 26 | Tristates are not mapped by `dfflibmap`/`abc`: `assign pad = oe ? d : 1'bz` leaves unmapped `$_TBUF_` cells. GF180 *does* have `bufz_*`/`invz_*`, they must be named | HIGH | Checker.YosysUnmappedCells | `mosaic_block_a.sv` — explicit `bufz_4` |
| 27 | **PDN core ring on Metal2/Metal3 sits inside the router's own layer range** (`RT_MIN_LAYER: Metal2`, `RT_MAX_LAYER: Metal5`). Every detailed-routing violation was a signal-net-to-VDD short on Metal3 at x≈1801 µm — the ring itself. DRT thrashed 3+ h without converging (28 → 56) | CRITICAL | Detailed routing non-convergence | Was `PDN_CORE_RING: false`, which cost IR analysis (`PSM-0069`). Real fix: keep the ring but **omit** `PDN_CORE_{VERTICAL,HORIZONTAL}_LAYER` so it defaults to the M4/M5 strap layers, above the router |
| 28 | **A fix for bug 22 silently broke `soc_ctrl`.** The `soc.dma: none` branch also drove `ao_peripheral_slv_rsp[DMA_CH0_IDX]`, but `DMA_CH0_IDX` is not an AO peripheral index — it is an 8-bit index into the DMA's *own* channel map (`DMA_ADDR_RULES`) and its value is `0`, i.e. `SOC_CTRL_IDX`. Every `soc_ctrl` register read therefore returned `error=1, rdata=0`: `boot_select`, `boot_address` and `use_spimemio` read back as zero | CRITICAL | `yosys check` — *only after* `ERROR_ON_SYNTH_CHECKS` was turned back on for the signoff config | `ao_peripheral_subsystem.sv.tpl` — `DMA_IDX` alone covers the window |
| 29 | `soc.ao_rv_timer: false` absorbed `rv_timer_tl_h2d` into an unused signal instead of tying it off. Its only driver (the `reg_to_tlul` bridge) is inside the branch that was removed, leaving 107 bits used-but-undriven — the same signature that exposed 22 and 25 | MEDIUM | `yosys check` | `ao_peripheral_subsystem.sv.tpl` — `assign rv_timer_tl_h2d = '0` |
| 30 | **`flow/librelane/pdn_cfg.tcl` could never generate a PDN.** Its MOSAIC `sram_grid` appendix calls `define_pdn_grid -macro` without `-cells`, `-instances` or `-default`, so OpenROAD aborts with `[PDN-1028]` — for *any* design that sources the file, macros or not. Broken since `6454c80`; unseen because the experimental configs never set `PDN_CFG` | HIGH | Block A signoff run, step 21 | `-cells {mosaic_sram gf180mcu_fd_ip_sram__.*}` (still unexercised — no macro-bearing config has reached PDN) |
| 31 | **SERV's ext Wishbone port was tied off, so every data access at or above `0x4000_0000` stalled the hart forever.** `servile.v` feeds `servile_mux` with the DATA bus only, and the mux splits on the top two address bits (`ext = adr[31:30] != 2'b00`); instruction fetch reaches the mem port through servile's arbiter and bypasses the mux entirely. `serv_sci.sv` wired only the mem port and set `.i_wb_ext_ack(1'b0)` under the comment "Extension bus (unused — tie off)" — the comment was the bug. Executing from flash therefore worked while *loading* from it hung with no bus request ever issued. In MOSAIC's map that dead region is FLASH_MEM (XIP, `0x4000_0000`) **and** EXT_SLAVE (`0xF000_0000`) | CRITICAL | UART bring-up firmware, whose `.rodata` string hung; localised with 4 firmware probes + RTL bus/port tracing | `serv_sci.sv` — both Wishbone ports arbitrated onto the one OBI master, `ext_owns_q` routes the response to the issuing port, ext wins ties so a continuously-fetching core cannot starve its own load |
| 32 | **The flow was measuring against constraints tighter than the PDK's own.** `MAX_TRANSITION_CONSTRAINT` defaulted to 3 ns while every one of the 215 cells declares `max_transition : 4.0`; `MAX_CAPACITANCE_CONSTRAINT` applied a blanket `set_max_capacitance 0.2 pF` to the whole design, **below even the weakest clock buffer's own 0.2394 pF rating**. A `clkbuf_16` driving 0.443 pF was reported as failing while rated for 3.813 pF. Repair then spent buffers, area and wirelength on nets that were never violating | MEDIUM | Chasing 2 889 max-slew / 35 max-cap violations that would not come down | Constrain from the library: `MAX_TRANSITION_CONSTRAINT: 4`, `MAX_CAPACITANCE_CONSTRAINT: null` (per-cell limits). Result: cap 35 → 0, slew 1 815 → 591, utilization 86.2% → 84.4%, wirelength 2.13 m → 1.94 m |
| 33 | **`RUN_POST_GRT_DESIGN_REPAIR` was false**, so `repair_design` only ever ran on global-placement wire estimates. Nothing repaired slew or cap again after CTS and real routing, which is why violations survived a run that closed timing at every corner | MEDIUM | Post-PnR STA vs the repair logs | `RUN_POST_GRT_DESIGN_REPAIR: true` in `config_blocka_signoff.yaml` |
| 34 | **The GF180 cell models are not standard-compliant**: 120 specify paths use `ifnone` on EDGE-SENSITIVE arcs, e.g. `ifnone (posedge A1 => (ZN:A1))`. IEEE 1364-2005 §14.2.6 permits `ifnone` only as the default for state-dependent *simple* paths. Two independent simulators reject it — iverilog `sorry: ifnone with an edge-sensitive path is not supported`, CVC `ERROR [1012] ifnone path illegal`. Consequence: **no open-source simulator can do SDF-annotated GLS on GF180 without patching the PDK** | MEDIUM | Building timing-annotated gate-level simulation | Not fixable by us. `tb/gls/mk_cells_cvc.py` writes a compliant local copy (keeps the paths as SDF targets); worth reporting upstream. Timing coverage stays with STA at 9 corners |
| 35 | **4 081 of 5 587 flip-flops have no reset** (plain `dffq_1`). Harmless in silicon — datapath flops are written before use, and real flops power up to a definite 0/1 — but in gate-level simulation they start X and X-propagation stalls the netlist: the first GLS attempt ran 126 000 cycles with the QSPI pins stuck at `x`. **Verilator hides this by zero-initialising**, which is why no RTL run ever showed it | LOW (sim), open question for silicon | First gate-level simulation | Power-up modelled explicitly: `$deposit` per flop (Icarus) or `+random_2state=<seed>` (CVC). Reset coverage deserves a deliberate review before tapeout |
| 36 | **CVA6 could not build on any bus but `floonoc`.** `cva6_sci.sv` bridges CVA6's native AXI4 to OBI with `xheep_axi_burst_to_obi` — CVA6 has no OBI port, so it needs the bridge *always* — but `mosaic:ip:axi_obi` was only reachable through `core-v-mini-mcu`'s `files_rtl_floonoc` fileset, i.e. only when `bus == floonoc`. `bus: obi` died with `Cannot find file containing module` | HIGH | 2026-08-03 sweep (`wake_cva6`, `wake_new_cores`) | `cva6.core` declares `mosaic:ip:axi_obi` itself, exactly as `berkeley.core` declares `mosaic:ip:tl_obi` — which is why Rocket/BOOM never hit this |
| 37 | **Hazard3's headers were never staged.** `hazard3.core` listed only `rtl/*.v`, so FuseSoC never copied the eight `.vh` files into `build/src` and elaboration died on `hazard3_config.vh`. **The standalone TB hid it** — `tb_smith` adds the include path itself, so `tb/sci/hazard3` passed in the same sweep that `wake_hazard3` failed | HIGH | 2026-08-03 sweep (`wake_hazard3`) | All eight declared `is_include_file: true`, which also puts `rtl/` on `+incdir+` |
| 38 | **The cocotb dormancy test was stale, not the RTL.** `testbench_hart0_bootstrap` releases hart 0 when a config has no TITAN and declares `profile: testbench` — a worker-only topology otherwise has no hart able to issue the first TDU dispatch. The test predated the rule and asserted all three harts stayed parked | LOW (test-only) | 2026-08-03 sweep (`mosaic_sci_cocotb`) | Test asserts the real contract; the selective-wake proof **moved to hart 1**, a hart that really is dormant. Waking hart 0, already running, proved nothing |
| 39 | **`tb-smith wake-demo hazard3` emitted an invalid config.** `wake_demo_config` read a hand-maintained `CORE_DEFAULTS` table with no `hazard3` entry and fell back to `rv32i`, which the core rejects (`valid: ['rv32imc']`). Together with bug 37, *both* documented routes to the "Hazard3 integrated end-to-end" claim were broken, by different causes | MEDIUM | Verifying the bug-37 fix | ISA derived from `core_registry.CORE_SPECS`; a test asserts `wake_demo_config` validates for every core in the registry |

> **Bugs 22–30 were all found by the physical flow, and none of them could have
> been caught in simulation.** 22, 23 and 29 are undriven bus responses that only
> matter if firmware touches a removed peripheral's address window — the
> liveness firmware never does, so every sim passed. 24–26 are library/mapping
> facts invisible above the netlist. 27 and 30 only appear once a real PDN exists.
> The lesson recorded here: run the physical flow early, not at the end.
>
> **28 is the uncomfortable one.** It was introduced *by* the fix for 22, it sat
> in the committed Block A GDS, and it was hidden by `ERROR_ON_SYNTH_CHECKS:
> false` — a flag set to speed up the area loop, carrying a comment that called
> the remaining 108 problems "pre-existing x-heep artifacts". They were not.
> The count had been checked; the *contents* had not. Fixing it cost +1.07 %
> netlist area (831254 → 840151 µm²), which is the read-path logic that had
> been dead.

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
| ~~DRC/LVS never run on the Block A GDS~~ **CLOSED 2026-08-01** | — | — | The signoff run executed every deck with nothing skipped: Magic DRC 0, KLayout DRC 0, Netgen LVS "circuits match uniquely", XOR 0, antenna 0. See D-84 |
| ~~Block A power delivery unresolved (PSM-0069)~~ **CLOSED 2026-08-01** | — | — | Ring restored on the default M4/M5 layers; 0 power-grid violations on VDD and VSS in the signoff run. See P-08 |
| ~~Committed Block A GDS predates bug 28~~ **CLOSED 2026-08-01** | — | — | Replaced: the tracked deliverable is now `runs/blocka_signoff/final/`, built from fixed RTL and signed off |
| ~~LibreLane configs pin ~526 absolute paths into a content-addressed build dir~~ **CLOSED 2026-08-03** | — | — | The committed signoff was reproducible by nobody, and the dangerous failure was never "file not found": a path that still *resolved*, to one of the 14 bundles on the dev machine, would harden stale RTL and report clean results for the wrong design. `scripts/gen_filelist.py` resolves the list from the FuseSoC manifest at run time; a test fails the build if an absolute path reappears. See D-90 |
| ~~2 889 max-slew / 411 max-fanout / 27 max-cap violations~~ **SUPERSEDED 2026-08-02** | — | — | Post-GRT electrical repair took these to 591 / 1 / 0. What remains is the row below |
| Block A pin contract not confirmed with the MPW integrator | MED | MED | 22 pins fixed; `bufz_4` QSPI drive is a placeholder pending pad loading; `status_o[6:0]` must be bonded — sole observability with `debug:false` |
| Routing convergence is placement-sensitive near 82% utilization | MED | MED | One run stalled at 2 violations for 30 passes; a re-seed at 69% util reached 0. Budget a re-spin; do not assume determinism |
| ~~**591 max-slew violations remain**~~ **CLOSED 2026-08-16** | — | — | They were measured against `tt_025C_5v00`'s 4.0 ns applied at all nine corners; at `ss_125C_4v50`, where all 591 sat, the pins are rated 7.0 ns. 0 against per-pin liberty limits at every corner, on byte-identical netlists. Both slew waivers retired |
| **Clock target not locked** | HIGH | CERTAIN | The only item blocking a tapeout tag, and not ours to close. 25 MHz measured and closes, but at **4.2% margin** (+1.663 ns of 40 ns) and the binding path moves inside the core. If the locked target is higher, that margin is where it will be spent |
| **1 max-fanout violation, waived** | LOW | CERTAIN | Real: GF180 declares no `max_fanout`, so `MAX_FANOUT_CONSTRAINT: 10` is a rule we chose and the net genuinely exceeds it. `accepted_max: 1`, so a second violating net fails the gate |
| GitHub LFS quota (1 GB free tier) | LOW | LOW | Deliverable trimmed to gds/lef/netlist/lib/sdc/odb = 95 MB (~10%); regenerable views gitignored |

---

## 9. Next Actions (Priority Order)

1. **Lock the clock target with the track lead / integration team.** ← *the only thing
   blocking a tapeout tag, and it is not ours to close.* 25 MHz is measured and closes
   (`runs/blocka_25mhz`): setup +1.663 ns TNS 0, hold +0.0662 ns, every hard check 0, GLS
   `EXIT SUCCESS`. Two caveats to carry into that conversation: **+1.663 ns is 4.2% of a
   40 ns period**, and at 25 MHz the binding path moves off the QSPI output path onto an
   internal register-to-register path — so work on the pads buys nothing there. Once a
   target is confirmed: set `soc.objectives.target_clock_mhz`, re-run, tag, and **delete**
   `flow/librelane/experimental/config_blocka_25mhz.yaml`.
2. **Raise the timing-annotated GLS question with the organizers.** GF180 cell models use
   `ifnone` on edge-sensitive specify paths, which IEEE 1364-2005 §14.2.6 forbids;
   iverilog refuses and CVC segfaults at this scale. Ask whether multi-corner STA suffices
   for signoff, and report the non-compliant models upstream either way. Shared PDK/tooling
   item, not a Block A one.
3. ~~**Close the residual 591 max-slew violations**~~ — **done 2026-08-16, and they were
   not violations of anything the library objects to.** 0 at all nine corners against
   per-pin liberty limits, on byte-identical netlists. Both slew waivers retired. The two
   global levers that were measured to *hurt* (`CTS_MAX_CAP: 0.15` made cap worse; `bufz_8`
   QSPI pads made slew worse) remain good reasons not to reach for a blanket setting.
4. ~~Repair the electrical rule violations~~ — **done.** max-slew 0, max-cap 0, antenna 0
   on all three blocks; one accepted max-fanout waiver (Block A, `accepted_max: 1`), real
   because GF180 declares no `max_fanout` at all.
   *(DRC + LVS themselves are done — all decks clean, 2026-08-01.)*
3. ~~**Resolve Block A power delivery**~~ — **done.** The ring is back on Metal4/Metal5 by
   omitting `PDN_CORE_{VERTICAL,HORIZONTAL}_LAYER`; the signoff run reports `PSM-0040` on
   both nets and 0 power-grid violations. Superseded by: **re-generate the committed
   `runs/blocka/final/` artifacts** — done, replaced by `runs/blocka_signoff/final/`.
4. **Confirm the Block A pin contract with the MPW integrator** — 22 pins, `bufz_4` drive on
   the QSPI pads is a placeholder, and `status_o[6:0]` must be bonded (it is the only
   observability with `debug: false`).
5. **Obtain GF180 SRAM bitcell** (P-06) — extract cell1rw.gds/sp from PDK or copy from upstream OpenRAM.
   *Note: measured evidence says the GF180 SRAM macros are area-NEGATIVE below ~512 B —
   4× sram64x8 costs 0.402 mm² vs 0.252 mm² of flip-flops for 256 B (area study §8f).*
6. **LibreLane pin-binding for the chip-level flow** (P-01/P-02) — `mosaic_soc_core.sv` is
   still a stub. *Not required for the MPW Block A path, which ships a macro, not a chip.*
7. **Generate SRAM macros** (P-03) — run OpenRAM with the GF180 PDK to produce 4KB/32KB GDS/LEF/LIB
8. **Scheduling demo in full-SoC sim** — run `mosaic_demo.hex` through the `run_fw.sh` flow (currently build-verified only)
9. **Decide on the next-gen generator roadmap** — review the proposition in `docs/general_multicore_soc_generator_roadmap.md` (D-77) and accept/defer/reject as a team
