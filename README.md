<br />
<p align="center"><img src="docs/architecture.jpg" width="820"></p>

<h1 align="center">MOSAIC-SoC</h1>

<p align="center">
  <b>A configuration-driven, multi-core RISC-V SoC generator</b><br>
  One declarative <code>mosaic.yaml</code> → a synthesizable, tapeout-ready heterogeneous SoC, with entirely open-source EDA.
</p>

<p align="center">
  IEEE SSCS Chipathon 2026 · Track D (AI/LLM for Circuits) · Target PDK: <b>GF180MCU</b> · Built on <a href="#built-on-x-heep">X-HEEP</a>
</p>

---

## Table of contents

1. [What is MOSAIC-SoC?](#1-what-is-mosaic-soc)
2. [Architecture](#2-architecture)
3. [The single config file](#3-the-single-config-file)
4. [Repository layout](#4-repository-layout)
5. [Prerequisites](#5-prerequisites)
6. [Setup](#6-setup)
7. [Generate the SoC RTL](#7-generate-the-soc-rtl)
8. [Run the simulations & tests](#8-run-the-simulations--tests)
9. [RTL → GDSII hardening (GF180MCU)](#9-rtl--gdsii-hardening-gf180mcu)
10. [Config reference](#10-config-reference)
11. [Project status](#11-project-status)
12. [Extending the SoC](#12-extending-the-soc)
13. [Built on X-HEEP](#built-on-x-heep)

---

## 1. What is MOSAIC-SoC?

MOSAIC-SoC turns a **single YAML file** into a complete heterogeneous multi-core RISC-V
SoC — choosing the cores, their counts, the memory, the bus fabric, the hardware
scheduler, and the peripherals — and drives that all the way to a **DRC/LVS-clean GDSII**
on the open-source **GF180MCU** PDK.

It is built on EPFL's [X-HEEP](#built-on-x-heep) single-core MCU, extended into a
**config-driven multi-core generator**:

- **Heterogeneous "Big.LITTLE" cores** — mix industry cores (cv32e20/Ibex) with ultra-tiny
  serial cores (SERV, QERV, FazyRV) in one SoC.
- **Standard Core Interface (SCI)** — every core is wrapped to a common OBI 1.3 interface,
  so adding a core is one wrapper + one `.core` descriptor.
- **Task Dispatch Unit (TDU)** — a tiny (<100 GE) memory-mapped hardware scheduler that
  wakes dormant worker cores and tracks their activity.
- **Open EDA only** — Verilator + cocotb for verification, LibreLane (Yosys + OpenROAD +
  Magic/KLayout/Netgen) for hardening.

**Proof-of-concept SoC:** 1× cv32e20 (TITAN) + 2× FazyRV-CHUNK8 (ATLAS) + 4× SERV (NANO),
32 KB SRAM, 2 KB boot ROM, UART/GPIO/timer/SPI, TDU scheduler, iDMA — in **1.249 mm²** on
GF180MCU.

---

## 2. Architecture

<p align="center"><img src="docs/init_arch_by_phase.svg" width="900"></p>

### Core taxonomy (Big.LITTLE)

| Tier      | Role            | Cores                | Area       | Purpose                  |
| --------- | --------------- | -------------------- | ---------- | ------------------------ |
| **TITAN** | orchestrator    | cv32e20 (CVE2), Ibex | ~14–17 kGE | RTOS / task dispatch     |
| **ATLAS** | signal/protocol | FazyRV-CHUNK8        | ~2–5 kGE   | streaming / conditioning |
| **NANO**  | always-on       | SERV, QERV           | ~0.2–3 kGE | sensor polling           |

### Key blocks

- **Standard Core Interface (SCI)** — a thin (~100–200 line) wrapper per core
  (`hw/sci/<core>_sci.sv`) that presents identical OBI 1.3 instruction + data ports plus a
  clock-gate/wake handshake. Wishbone (SERV/QERV/FazyRV) and req/gnt (Ibex) cores are
  converted to OBI here.
- **Task Dispatch Unit (TDU)** — `hw/tdu/`, memory-mapped at `0x200A0000`. An 8-deep task
  FIFO, per-hart `WAKE_REQ` → `core_wake` pulses, a CPI-estimate array and an energy
  counter. Worker cores boot **dormant** and are released by a TDU wake.
- **iDMA** (pulp-platform) — `hw/vendor/mosaic/idma/`, replaces x-heep's simple DMA
  (register frontend + ND midend + native OBI backend, no protocol conversion).
- **Bus fabric** — a parameterized OBI N×M crossbar (`pulp-platform/obi`), sized
  automatically by the generator; banked SRAM with per-bank clock gating.

### How generation works

```
mosaic.yaml ──> util/xheep_gen/mosaic_config.py ──> XHeep config object
                                                          │
                  Mako templates (*.sv.tpl) <─────────────┘
                          │  rendered by util/xheep_gen/mcu_gen.py
                          ▼
                  generated *.sv  ──> FuseSoC (.core files) ──> Verilator / LibreLane
```

---

## 3. The single config file

Everything is driven by one declarative file. This is the PoC (`mosaic.yaml`):

```yaml
soc:
  name: mosaic_poc_alpha
  pdk: gf180mcu

  cores:
    - ip: cv32e20 # TITAN — CVE2, 2-stage, RV32E/M (orchestrator)
      isa: rv32emc
      count: 1
      role: titan

    - ip: fazyrv # ATLAS — chunk-serial datapath
      isa: rv32i
      chunksize: 8 # per-core-type parameter
      count: 2
      role: atlas

    - ip: serv # NANO — bit-serial, ~200 GE each
      isa: rv32i
      count: 4
      role: nano

  memory:
    sram_kb: 32
    boot_rom_kb: 2

  bus: obi # Open Bus Interface

  scheduler:
    tdu: true # Task Dispatch Unit
    mode: dynamic # static | dynamic | power-aware

  peripherals: [uart, gpio, timer, spi]
```

| Field                     | Drives                                                                                                      |
| ------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `cores[].ip`              | which core IP + its SCI wrapper + FuseSoC dependency                                                        |
| `cores[].count`           | how many copies (each gets its own OBI ports, hart_id, debug, wake)                                         |
| `cores[].role`            | tier → interrupt routing, clock-gate policy, TDU priority (`titan` boots immediately; workers boot dormant) |
| `cores[].*`               | extra fields (e.g. `chunksize`, `boot_addr`, `memdly1`) → per-core params                                   |
| `memory`                  | SRAM size (banked) + boot ROM size                                                                          |
| `bus`                     | interconnect fabric (`obi`)                                                                                 |
| `scheduler.tdu` / `.mode` | enable the TDU + its scheduling policy                                                                      |
| `peripherals`             | which peripheral IPs are in the memory map                                                                  |

---

## 4. Repository layout

```
mosaic.yaml                 # the PoC config (default for `make mosaic-gen`)
configs/                    # more configs: mosaic_*.yaml + x-heep *.hjson/*.py
hw/
  core-v-mini-mcu/          # the SoC RTL templates (*.sv.tpl) — generated into *.sv
  sci/                      # Standard Core Interface wrappers (serv/qerv/fazyrv/ibex/cve2)
  tdu/                      # Task Dispatch Unit (rtl + tb + .core)
  ip/                       # OBI helpers (obi_fifo, ...)
  vendor/mosaic/            # vendored cores + iDMA (serv, fazyrv, ibex, idma)
util/xheep_gen/             # the Python generator (mcu_gen.py, mosaic_config.py, cpu/)
tb/                         # testbenches (see §8)
  mosaic/                   #   multi-core cpu_subsystem harness (SV + cocotb)
  mosaic_soc/               #   full-SoC functional sim + TDU wake-and-run demo
  idma/                     #   iDMA cocotb tests
  tdu/                      #   TDU SoC-level cocotb test
flow/librelane/             # RTL→GDSII hardening flow for GF180MCU
scripts/                    # build/sim/synth helpers (fusesoc-setup.sh, ...)
refs/                       # READ-ONLY reference IPs (cores, interconnects, SoCs, tools)
```

> **Never modify `refs/`** (read-only references). **Never commit generated `.sv`** — only
> `.sv.tpl` templates are version-controlled.

---

## 5. Prerequisites

You can install everything natively, or use the [oss-cad-suite](https://github.com/YosysHQ/oss-cad-suite-build)
bundle (it ships Verilator, Icarus, cocotb and a Python). Versions below are what this
project is developed/verified against.

| Tool                                            | Needed for                                                   | Verified version                               |
| ----------------------------------------------- | ------------------------------------------------------------ | ---------------------------------------------- |
| **Python** ≥ 3.10                               | the generator + FuseSoC                                      | 3.14                                           |
| **GNU Make**                                    | top-level flow                                               | 4.4                                            |
| **Verilator** 5.x                               | all RTL simulation                                           | 5.047                                          |
| **cocotb** 2.x                                  | the cocotb test harnesses (`tb/mosaic`, `tb/idma`, `tb/tdu`) | 2.1                                            |
| **RISC-V bare-metal GCC** (`riscv32-*-elf-gcc`) | full-SoC sim firmware                                        | 16.1                                           |
| **FuseSoC** + edalize                           | dependency resolution / register gen                         | auto-installed (see §6)                        |
| _Icarus Verilog_ (optional)                     | —                                                            | 13.0 — _cannot_ compile the full SoC, see note |
| **Nix** (flakes) + GF180 PDK (optional)         | RTL→GDSII signoff                                            | 2.32                                           |

- **FuseSoC is installed automatically** into a project-local Python venv (`.venv/`) the
  first time you run a `make` target — from `util/python-requirements.txt`. You don't need
  to install it by hand.
- **RISC-V toolchain:** the full-SoC sim scripts default to
  `RISCV_TC=/opt/riscv32-gnu-toolchain-elf-bin/bin/riscv32-unknown-elf`. Override with
  `RISCV_TC=<prefix>` (the prefix before `-gcc`). Note this toolchain has **no rv32imc
  multilib**, so the demo programs are assembled `-march=rv32i` and linked with `ld`
  directly (the scripts handle this).
- **Icarus note:** Icarus is event-driven but cannot parse x-heep's OpenTitan/pulp
  SystemVerilog (package-function param defaults, named struct-pattern params). The
  `tb/mosaic_soc/run_icarus.sh` harness documents exactly where it fails. **Use Verilator.**

---

## 6. Setup

```bash
git clone https://github.com/MILOUDIAS/MOSAIC-SoC.git
cd MOSAIC-SoC

# The Python venv (with FuseSoC) is created automatically on the first make target.
# To create/refresh it explicitly:
make venv          # builds .venv/ from util/python-requirements.txt

# Make sure your simulators are on PATH (native install or oss-cad-suite):
source /path/to/oss-cad-suite/environment   # if using the bundle
verilator --version                          # expect 5.x
```

---

## 7. Generate the SoC RTL

Render the RTL templates from a config (this is the core of the "config-driven" flow):

```bash
# Generate the PoC SoC (mosaic.yaml): 1x cv32e20 + 2x fazyrv + 4x serv + TDU + iDMA
make mosaic-gen

# Generate a different config:
make mosaic-gen MOSAIC_CFG=configs/mosaic_all_cores.yaml   # all 5 core types
make mosaic-gen MOSAIC_CFG=configs/mosaic_wake_demo.yaml   # the 3-core wake demo (§8)
```

`make mosaic-gen` renders every `*.sv.tpl` into a `*.sv`, then runs the FuseSoC register
generators (via `scripts/fusesoc-setup.sh`, which excludes `refs/` so FuseSoC doesn't crash
on reference fixtures). Re-run it **after any `.sv.tpl` change** — stale generated RTL
causes confusing errors.

> Single-core x-heep generation is still available via `make mcu-gen CPU=... BUS=...` — see
> `make help`.

---

## 8. Run the simulations & tests

All simulations use **Verilator**. Each runner generates the RTL it needs, builds, runs,
and restores the default config — so they're self-contained.

### 8.1 Full-SoC TDU wake-and-run demo ✅ (the headline test)

The complete SoC (testharness → `x_heep_system` → `core_v_mini_mcu`) where TITAN boots,
**wakes both workers via the TDU**, and each woken worker runs its own program through the
shared bus and reports back:

```bash
tb/mosaic_soc/run.sh
```

Expected (3 real cores — cv32e20 TITAN + fazyrv ATLAS + serv NANO):

```
write hart=0 addr=0x200a000c: data=0x00000006   # TITAN writes TDU WAKE_REQ
write hart=1 addr=0x00003004: data=0xa71a5000    # ATLAS (fazyrv) sentinel
write hart=2 addr=0x00003008: data=0x4e414e00    # NANO  (serv)   sentinel
### RESULT: EXIT SUCCESS — full multi-core SoC executed the program ✓
```

The diagnostic top (dumps sentinels, wake latches, fetch traces) builds with:

```bash
tb/mosaic_soc/build_diag.sh
```

> See [`tb/mosaic_soc/README.md`](tb/mosaic_soc/README.md) for the single-core functional
> sim and the five RTL fixes this demo required (packed wake ports, the per-hart array
> range fix, the SCI OBI-bridge fix, and the FazyRV clock-stall adapter).

### 8.2 Multi-core SCI wake-loop ✅

Builds the **real generated `cpu_subsystem`** and exercises the SCI-wrapped serial cores
against per-hart OBI memories — proves dormancy + per-hart wake + execution.

```bash
tb/mosaic/run.sh         # pure-SV Verilator TB (no cocotb / GCC needed) — 3/3 cores
tb/mosaic/cocotb/run.sh  # cocotb TB: dormant → selective-wake → all-wake loop
```

Expected (cocotb): `TESTS=1 PASS=1 FAIL=0` — `serv`, `qerv`, `fazyrv` all
`dormant → woken → executed`.

### 8.3 Task Dispatch Unit tests ✅

```bash
tb/tdu/soc/cocotb/run.sh     # SoC-level reg-bus tap test (SCHED_MODE, FIFO, WAKE_REQ)
tb/tdu/soc/cocotb/run.sh bug # also run the original buggy tap the test is designed to catch
```

The TDU also has a self-checking **unit** testbench (`hw/tdu/tb/tdu_tb.sv`, 16/16 tests),
built/run via its FuseSoC core `hw/tdu/tdu.core`.

### 8.4 iDMA tests ✅

```bash
tb/idma/cocotb/run.sh    # mem-to-mem copy at per-block AND SoC (arbitrated) level
```

Expected: `TESTS=1 PASS=1` at each level (no RTL generation needed — iDMA is static RTL).

### 8.5 x-heep application flow (full PoC incl. cv32e20, needs a toolchain)

```bash
make mosaic-gen                 # generate the SoC
make verilator-build            # build the Verilator model via FuseSoC
make app PROJECT=hello_world    # compile an app (needs riscv32 GCC)
make verilator-run              # run firmware on the model
```

---

## 9. RTL → GDSII hardening (GF180MCU)

The LibreLane flow lives in [`flow/librelane/`](flow/librelane/). A real signoff run needs
**Nix (flakes) + ~20 GB disk** and is multi-hour; the first `nix-shell` pulls the toolchain
from the FOSSi binary cache.

```bash
cd flow/librelane
nix-shell shell.nix          # LibreLane 3.0.0 + GF180 EDA tools
make clone-pdk               # wafer-space gf180mcu @ 1.8.0

# Chip flow — full chip with pad ring + sealring:
make harden SLOT=mosaic      # mosaic-gen → flatten → librelane → GDS
make padring                 # fast pad-only placement
make harden-nodrc            # skip DRC/antenna (dev)

# Classic flow — SoC core only, no pad ring (early synth/PnR/area):
make classic
make classic-nodrc
```

> Status: the GF180 pad frame elaborates clean; the remaining authoring step is binding the
> SoC pins in `src/mosaic_soc_core.sv` and mapping the 32 KB SRAM to GF180 hard macros.
> See [`flow/librelane/README.md`](flow/librelane/README.md).

---

## 10. Config reference

| Config                          | Cores                                                 | Used by                                     |
| ------------------------------- | ----------------------------------------------------- | ------------------------------------------- |
| `mosaic.yaml`                   | **PoC:** 1× cv32e20 + 2× fazyrv + 4× serv             | default for `make mosaic-gen`, the GDS flow |
| `configs/mosaic_wake_demo.yaml` | 1× cv32e20 + 1× fazyrv + 1× serv (per-core boot addr) | `tb/mosaic_soc/run.sh` (§8.1)               |
| `configs/mosaic_sim.yaml`       | serv + qerv + fazyrv (all workers)                    | `tb/mosaic/*` (§8.2)                        |
| `configs/mosaic_all_cores.yaml` | cv32e20 + ibex + fazyrv + qerv + serv                 | acceptance (renders all 5 SCI branches)     |

Pass any of them with `MOSAIC_CFG=<path>` to `make mosaic-gen`, or via `MOSAIC_CFG`/`RISCV_TC`
env vars to the `tb/mosaic_soc` scripts.

---

## 11. Project status

**Phase 1 — config-driven multi-core generator: working.**

- ✅ `mosaic.yaml` → `make mosaic-gen` renders the full multi-core SoC; per-core master
  indices, hart IDs, interrupt routing, and the multi-master `system_bus`.
- ✅ SCI wrappers + vendored cores: **SERV, QERV, FazyRV, Ibex** (cv32e20 native). CVA6 is
  intentionally out of scope for the GF180 die.
- ✅ TDU (8-deep FIFO, per-hart wake, CPI/energy) — unit + SoC tests pass.
- ✅ iDMA integrated (OBI backend) — per-block + SoC mem-to-mem tests pass.
- ✅ **Full multi-core SoC elaborates clean** (`verilator --lint-only`, 837 modules) — the
  first time the whole top was ever elaborated; surfaced & fixed several latent
  port/type/package bugs.
- ✅ **Full-SoC functional sim passes** — single-core boot-and-run, **and the 3-core TDU
  wake-and-run demo reaches `EXIT SUCCESS`** (TITAN wakes ATLAS + NANO; each runs its own
  program and writes its sentinel). Validated against the cocotb regression too.
- 🔜 LibreLane GF180 hardening: flow wired, pad frame clean; pin-binding + SRAM macros are
  the remaining authoring steps before a tapeout signoff.

**Phase 2 — agentic harness (oh-my-pi) with skills for config authoring, flow running, DRC
triage, and doc generation: working on**.

---

## 12. Extending the SoC

**Add a new core** (summary):

1. Study the core in `refs/IP_Cores_Catalog/<core>/` (bus, params, HDL).
2. Write `hw/sci/<core>_sci.sv` presenting OBI 1.3 I+D ports.
3. Add `util/xheep_gen/cpu/<core>.py` and register it in `AVAILABLE_CPUS`
   (`util/xheep_gen/cpu/cpu.py`).
4. Add a `% elif group.name == "<core>":` branch in
   `hw/core-v-mini-mcu/cpu_subsystem.sv.tpl`.
5. Add the FuseSoC dependency in `hw/sci/sci.core`.
6. Add a config and run `make mosaic-gen` + the `tb/mosaic` harness.

**Add a new interconnect/NoC:**.

> Heads-up for serial cores on the registered system bus: cores built for _combinational_
> memory (e.g. FazyRV) need the **clock-stall adapter** in their SCI wrapper (freeze the
> core's clock while a fetch is outstanding) so the 1-cycle bus looks combinational. See
> `hw/sci/fazyrv_sci.sv`.

---

## Built on X-HEEP

MOSAIC-SoC is built on **[X-HEEP](https://github.com/esl-epfl/x-heep)** (eXtensible
Heterogeneous Energy-Efficient Platform), a RISC-V microcontroller from EPFL's
[ESL](https://www.epfl.ch/labs/esl/) lab (with UPM CEI and POLITO VLSI), founded on the
[PULP-Platform](https://pulp-platform.org/) and [OpenTitan](https://opentitan.org/)
projects. X-HEEP provides the base MCU, the FuseSoC + Mako generation flow, and the
peripheral/memory IP that MOSAIC extends into a multi-core generator. X-HEEP docs:
[Read the Docs](https://x-heep.readthedocs.io/en/latest/index.html).

If you use X-HEEP in academic work, please cite:
[X-HEEP Paper](https://doi.org/10.1109/ISVLSI65124.2025.11130281).

```bibtex
@INPROCEEDINGS{machetti2025xheep,
  author={Machetti, Simone and Schiavone, Pasquale Davide and Ansaloni, Giovanni and Peón-Quirós, Miguel and Atienza, David},
  booktitle={2025 IEEE Computer Society Annual Symposium on VLSI (ISVLSI)},
  title={X-HEEP: An Open-Source, Configurable and Extendible RISC-V Platform for TinyAI Applications},
  year={2025},
  doi={10.1109/ISVLSI65124.2025.11130281}
}
```

**License:** see [LICENSE](./LICENSE) (Apache-2.0, inherited from X-HEEP; MOSAIC additions
under the same terms unless noted). Reference IPs under `refs/` retain their own licenses.
