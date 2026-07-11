# oh-my-soc — Agentic Harness for MOSAIC-SoC

> Based on [oh-my-pi](https://github.com/oh-my-pi), adapted for MOSAIC-SoC EDA flows.

oh-my-soc is the Phase 2 agentic harness for MOSAIC-SoC. It provides four
deterministic skills that an LLM agent (or a human) can compose to automate
RTL-to-GDS tasks — without replacing signoff tooling.

**Design principle:** The agent *assists and is checked by* deterministic
tooling. It never replaces signoff.

## Quick start

```bash
# From the repo root:
python -m harness <skill> <command> [args...]

# Generate a config from a preset
python -m harness config-author generate --preset poc --name my_soc

# Validate an existing config
python -m harness config-author validate mosaic.yaml

# Run an EDA flow
python -m harness flow-runner run firmware-build

# Analyze a DRC report
python -m harness drc-triage analyze build/reports/magic_drc.rpt

# Generate documentation
python -m harness doc-gen memory-map
```

## Skills

| Skill | Purpose | Input → Output |
|-------|---------|---------------|
| **config-author** | Generate/validate `mosaic.yaml` | Structured params → valid YAML |
| **flow-runner** | Run EDA flows with structured reporting | Flow name → timed, parsed result |
| **drc-triage** | Parse DRC/LVS reports, propose fixes | Report file → classified violations + suggestions |
| **doc-gen** | Generate docs from project artifacts | Config/RTL → markdown documentation |

### config-author

Translates intent into valid `mosaic.yaml` configs. Provides three presets
(`poc`, `minimal`, `max_cores`) and validates against the project schema
(core IPs, roles, ISAs, peripherals, memory constraints).

```bash
# List presets
python -m harness config-author presets

# Generate from preset
python -m harness config-author generate --preset poc --name test

# Generate custom
python -m harness config-author generate \
  --name my_soc \
  --core cv32e20:1:titan \
  --core serv:4:nano \
  --sram 16 --tdu --mode dynamic \
  --peripheral uart,gpio
```

### flow-runner

Wraps 11 EDA make targets with timeout protection, structured log parsing,
and timing. Returns `SkillResult` JSON instead of raw stdout.

Available flows: `mosaic-gen`, `verilator-lint`, `verilator-run`,
`tb-multicore`, `tb-tdu`, `tb-idma`, `harden-classic`, `harden-chip`,
`firmware-build`, `firmware-demo`.

```bash
python -m harness flow-runner list
python -m harness flow-runner run mosaic-gen
python -m harness flow-runner run tb-multicore
```

### drc-triage

Parses DRC/LVS reports in Magic, KLayout, and Netgen formats. Classifies
violations by type (short/open/spacing/width/antenna/LVS mismatch),
assesses severity, and suggests targeted RTL fixes.

```bash
python -m harness drc-triage analyze report.rpt
python -m harness drc-triage analyze report.rpt --format klayout
python -m harness drc-triage scan build/reports/
```

### doc-gen

Generates structured documentation from project artifacts:
- Config summaries from `mosaic.yaml`
- Memory-map reference from RTL package definitions
- Run reports from EDA flow results
- Dashboard metric extraction

```bash
python -m harness doc-gen config mosaic.yaml
python -m harness doc-gen memory-map
python -m harness doc-gen dashboard
```

## Architecture

```
harness/
├── __init__.py              # Package: oh-my-soc v0.1.0 (based on oh-my-pi)
├── __main__.py              # CLI entry point
├── core.py                  # SkillResult, validate_config, run_cmd, I/O helpers
└── skills/
    ├── __init__.py
    ├── config_author.py     # Generate/validate mosaic.yaml
    ├── flow_runner.py       # 11 EDA flows, structured log parsing
    ├── drc_triage.py        # Magic/KLayout/Netgen parsers, fix suggestions
    └── doc_gen.py           # Config summary, memory map, run reports
```

## How it fits the project

The harness sits between the agent and the EDA tools:

```
Agent (LLM or human)
    │  "I want X"
    ▼
oh-my-soc skills
    │  validate, execute, parse, structure
    ▼
Deterministic SkillResult JSON
    │  agent reads, decides next step
    ▼
Agent continues...
```

The agent never runs raw `make` or parses raw DRC output. It always goes
through the harness, which guarantees validation before execution, structured
results, timeout protection, and consistent parsing.

## Relationship to oh-my-pi

oh-my-soc is based on [oh-my-pi](https://github.com/oh-my-pi), a general-purpose
agentic harness pattern. Our version is customized for:

- **MOSAIC-SoC config schema** (cores, roles, TDU, peripherals)
- **MOSAIC-SoC EDA flows** (mosaic-gen, Verilator, LibreLane, cocotb testbenches)
- **MOSAIC-SoC artifacts** (memory map, TDU registers, RTL package definitions)
- **GF180MCU PDK** (DRC rules, hardening flow)
