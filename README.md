# MOSAIC-SoC

**Agent-Driven, Reconfigurable Multi-Core SoC Generator in Open-Source EDA**

> Describe your SoC in one config file. Let an LLM-driven harness drive the open-source flow.
> Generate, verify, and tape out reproducible SoC variants — *Build It. Test It. Publish It.*

---

## 1. Summary

MOSAIC-SoC is a configuration-driven generator that turns a single high-level
description (YAML/Python) into a synthesizable, tapeout-ready System-on-Chip in an
open-source EDA flow. On top of the generator, we build an **agentic harness**: an
LLM-driven assistant equipped with VLSI/SoC "skills" that helps author configurations,
run the RTL-to-GDSII flow, and triage failures (lint, synthesis, DRC/LVS).

The project directly targets **Track D – AI/LLM for Circuits**: it uses LLM agents as a
practical, measurable aid to digital hardware generation, not as a gimmick. The headline
deliverable is a **reproducible, DRC/LVS-clean single-core SoC** generated from config,
with multi-core generation and a fuller agent skill set as stretch goals.

---

## 2. Motivation

Building an SoC by hand in open-source EDA is slow and error-prone: stitching together a
core, memory, and peripherals, then babysitting synthesis and physical design through
many DRC/LVS iterations. Two ideas address this:

- **Reconfigurability** — capture the design intent (cores, memory map, peripherals,
  interconnect) in one declarative config so variants are generated, not rebuilt by hand.
- **Agentic assistance** — use an LLM harness to author/validate configs and to drive and
  debug the flow, lowering the barrier for newcomers and shortening iteration time.

The hypothesis we want to *measure*: an LLM-driven harness reduces the manual effort and
iteration count to reach a clean, tapeout-ready SoC.

---

## 3. Approach & Architecture

### 3.0 System overview

MOSAIC-SoC is organized as layers. Data flows top to bottom; the two **bold** layers are
the project's contribution (Phase 2 and Phase 1), wrapped around the standard open-source
flow. A signoff feedback loop returns DRC/LVS results to the harness so the agent can
triage and regenerate — closing the agentic cycle.

```
            ┌─────────────────┐   ┌─────────────────┐
  Inputs    │   User intent   │   │  Config (YAML)  │
            └────────┬────────┘   └────────┬────────┘
                     └───────────┬──────────┘
                                 v
  Phase 2          ╔═════════════════════════════╗
  (agentic)        ║       AGENTIC HARNESS        ║ <──────────┐
                   ║   LLM orchestrator + skills  ║            │
                   ╚══════════════╤══════════════╝            │
                                  v                            │
  Phase 1          ╔═════════════════════════════╗            │
  (generator)      ║        SoC GENERATOR         ║            │
                   ║  config parser · IP lib · RTL║            │
                   ╚══════════════╤══════════════╝            │
                                  v                            │
  Build it         ┌─────────────────────────────┐            │
                   │     Open-source EDA flow     │  DRC/LVS   │
                   │   synthesis · P&R · signoff  ├── loop ────┘
                   └──────────────┬──────────────┘
                                  v
  Test + publish   ┌─────────────────────────────┐
                   │     Tapeout-ready GDSII      │
                   │    DRC/LVS clean + reports   │
                   └─────────────────────────────┘
```

![Our Initinal Architecture](init_arch_by_phase.svg)

**Layer responsibilities**

- **Inputs** — a natural-language request and/or a declarative `mosaic.yaml` describing the SoC.
- **Agentic harness (Phase 2)** — an LLM orchestrator with scoped skills (`config-author`,
  `flow-runner`, `drc-triage`, `doc-gen`); every action is gated by a deterministic check.
- **SoC generator (Phase 1)** — validates the config and elaborates parameterized RTL from a
  small IP library, plus the flow configuration.
- **Open-source EDA flow** — Yosys/OpenROAD-class RTL-to-GDSII (synthesis, place & route, signoff).
- **Outputs** — a DRC/LVS-clean, tapeout-ready GDSII with reproducible run reports.
- **Feedback loop** — signoff results return to the harness; `drc-triage` proposes fixes and
  the generator re-runs. This loop is the core measurable claim of the project.

### 3.1 Phase 1 — Reconfigurability (configuration-driven generation)

A single declarative config describes the SoC; the generator emits RTL + flow scripts.

```yaml
# example: mosaic.yaml  (illustrative)
soc:
  name: mosaic_mini
  cores:
    - ip: ibex             # open-source core from the IP library (see §3.3)
      isa: rv32imc
      count: 1             # MVP = 1; multi-core is a stretch goal
  memory:
    sram_kb: 8
  bus: wishbone            # or obi — see §3.3
  peripherals: [uart, gpio, timer]
  pdk: gf180mcu            # [TBD] confirm target PDK for Track D
```

The generator (Python) parses this into: parameterized RTL (elaborated from a small IP
library), a memory map, and the configuration for the digital flow (e.g. OpenLane2 /
OpenROAD).

### 3.2 Phase 2 — Agentic harness

An LLM-driven harness with a set of well-scoped **skills**:

| Skill | What the agent does | How we verify it helped |
| -- | -- | -- |
| `config-author` | Translate natural-language intent into a valid `mosaic.yaml` | Schema validation + diff vs. golden config |
| `flow-runner` | Invoke synthesis / P&R / signoff and parse logs | Flow completes; reports captured |
| `drc-triage` | Read DRC/LVS reports and suggest/apply fixes | Reduction in violation count per iteration |
| `doc-gen` | Generate run reports and reproducibility notes | Report completeness checklist |

> **Design note:** the agent *assists and is checked by* deterministic tooling — it never
> replaces signoff. Every agent action is gated by a verifiable check.

**Architecture diagram, harness pattern (single-agent + tools vs. multi-agent), and the
exact LLM/runtime are `[TBD]` — add before submission.**

### 3.3 Open-source IP library

Every core and IP block is permissively licensed open source, so the whole SoC is
reproducible and tapeout-eligible. The generator selects and parameterizes blocks from a
catalog; reconfigurability extends down to the core itself (e.g. FazyRV's datapath width).

**Cores (RISC-V):**

| Core | Class | Notes |
| -- | -- | -- |
| SERV | bit-serial RV32 | smallest possible footprint; area-first |
| FazyRV | scalable RV32I | 1/2/4/8-bit datapath at synthesis — pairs perfectly with config-driven generation |
| PicoRV32 | small RV32 | simple, well-proven, fast bring-up |
| Ibex | RV32IMC, 2-stage | industrial-grade; strong MVP candidate |
| CVA6 | application-class RV64 | Linux-capable; multi-core / stretch target |

**Buses / interconnect:** Wishbone, OBI (Open Bus Interface); APB / AXI-lite optional for peripherals.

**Peripherals:** UART, GPIO, timer, SPI, I2C (open-source RTL).

> Core choice drives feasibility. SERV / FazyRV / PicoRV32 / Ibex are realistic for a
> GF180MCU MVP; CVA6 (RV64, Linux-class) is a stretch / multi-core ambition, not a
> first-cycle target. Pin the exact IP repos and commit hashes for reproducibility.

---

## 4. Scope: MVP vs. Stretch Goals

Scoping is deliberate so there is always a demonstrable, tapeout-ready result.

**MVP (committed):**
- Config-driven generation of a **single small RISC-V core SoC** (core + SRAM + UART + GPIO).
- Full RTL-to-GDSII in open-source EDA with **clean DRC and LVS**.
- Agent skills `config-author` + `flow-runner` working end-to-end.
- Reproducible repo: one command regenerates the design from config.

**Stretch goals:**
- **Multi-core** generation (2+ cores + interconnect + shared memory).
- `drc-triage` and `doc-gen` agent skills.
- A measurement study comparing agent-assisted vs. manual iteration effort.

---

## 5. Test It — Verification & Measurement Plan

- **Functional:** RTL simulation of generated SoC (UART/GPIO smoke tests, simple firmware).
- **Flow signoff:** DRC + LVS clean against the target PDK; STA timing closure at target clock.
- **Agent evaluation:** quantitative metrics — config validity rate, flow success rate,
  DRC violations resolved per iteration, manual edits required. Report agent-assisted vs.
  baseline manual runs.
- **Reproducibility:** pinned tool versions (IIC-OSIC-TOOLS container), seeds, and a
  single regeneration command; results checked into the repo.

---

## 6. Publish It — Dissemination Plan

- Public, documented, reproducible repository (this repo) with example configs and runs.
- Final report + presentation slides + optional demo video.
- Write-up of the agent-assisted-vs-manual measurement results.
- `[TBD]` Consider an SSCS Code-a-Chip / OSE submission or short paper.

---

## 7. Tools & Technology

- **EDA flow:** open-source RTL-to-GDSII — `Librelane` .
- **PDK:**  confirm Track D target (GF180MCU expected).
- **Environment:** IIC-OSIC-TOOLS container for reproducibility.
- **Cores/IP:** open-source RISC-V cores — SERV, FazyRV, PicoRV32, Ibex, CVA6, and any other Open-Source Core through a wrapper — over Wishbone / OBI /NoC, with open peripherals (UART, GPIO, timer, SPI, I2C). See §3.3.
- **Agent stack:** LLM + harness framework + tool-calling interface, probably based on Pi harness or OpenCode.

---

## 8. Timeline (aligned to Chipathon phases)

> Adjust to the official 2026 schedule; this maps work to the typical phase structure.

| Phase | Window | Milestone |
| -- | -- | -- |
| Setup | Phase 1 | Tools/PDK installed; config schema v0; minimal RTL generated |
| Build | Phase 2 | MVP single-core SoC through full flow; `config-author` + `flow-runner` skills |
| Review | Phase 3 | Interim design review; DRC/LVS clean MVP; begin stretch goals |
| Signoff | Phase 4 | Tapeout-ready database; measurement study; final report + slides |

---

## 9. Risks & Mitigation

| Risk | Mitigation |
| -- | -- |
| Multi-core + tapeout too ambitious for the cycle | MVP is a simple prototype; multi-core is an explicit stretch goal |
| Agent unreliable / hallucinates flow steps | Every agent action gated by deterministic checks; agent is optional over a working manual path |
| Flow/PDK setup delays | Start with IIC-OSIC-TOOLS container day one; use a known-good example design as baseline |
| Solo bandwidth | Scope locked to MVP; recruit 1–2 collaborators if possible |

---

## 10. Team

**Track:** D – AI/LLM for Circuits  
**Team name:** MOSAIC-SoC

| Discord | GitHub | Affiliation (experience) | Role (suggested) |
| -- | -- | -- | -- |
| @MILOUDIAS | @MILOUDIAS | `PhD Student/ Researcher` | RTL & SoC integration (Phase 1) |
| kewenlee | trabdelbasset | `PhD Student/ Researcher` | Team Lead — agentic harness (Phase 2)  |
| yassinehk | yacine-hk | `PhD Student/ Researcher` | EDA flow, physical design & verification |

**Background:** Open-source EDA (Librelane, ORFS, Cocotb...), SoC design, LLM agents.

---

## 11. Open Questions

- Confirm target core IPs and bus standard.
- Define the agent harness pattern and LLM runtime.

---

## References

- IEEE SSCS Chipathon 2026 — *Build It. Test It. Publish It.*: https://github.com/sscs-ose/sscs-chipathon-2026
- SSCS PICO design contest: https://sscs.ieee.org/technical-committees/tc-ose/sscs-pico-design-contest/
- Participation guidelines: https://github.com/sscs-ose/sscs-chipathon-2026/blob/main/docs/guidelines.md

