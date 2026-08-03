# Evidence Gates: Hardening the MOSAIC Harness Against False PASS

> **Status:** Proposal for team review — partially implemented on branch `mld-exp`
> **Date:** 2026-07-27 (revised 2026-07-28: standalone positioning, LibreLane evidence)
> **Scope:** `harness/` gate semantics, physical-flow truthfulness, evidence
> records, agent-loop discipline, and what it takes to ship MOSAIC as a
> standalone project rather than a competition entry
> **Relationship to existing plans:** This is an **acceleration of M0** in
> [`general_multicore_soc_generator_roadmap.md`](general_multicore_soc_generator_roadmap.md),
> not a competing architecture. It adopts that document's evidence-state
> vocabulary verbatim and supplies the implementation mechanics M0 leaves open.
> **Non-goal:** This proposal does not itself introduce the v2 schema, the
> `DesignIntentIR`/`ResolvedSoCIR` split, platform backends, or DSE — but see
> §10, which argues the standalone goal makes those *more* urgent, not less.

## Contents

- [1. Why this document exists](#1-why-this-document-exists)
- [2. The two upstream projects](#2-the-two-upstream-projects)
- [3. Verified findings in this repository](#3-verified-findings-in-this-repository)
- [4. What we adopt, and from where](#4-what-we-adopt-and-from-where)
- [5. What the roadmap already covers better](#5-what-the-roadmap-already-covers-better)
- [6. Implemented on this branch](#6-implemented-on-this-branch)
- [7. Proposed work packages](#7-proposed-work-packages)
- [8. Decisions requested from the team](#8-decisions-requested-from-the-team)
- [9. Standalone positioning](#9-standalone-positioning)
- [10. Limits of this analysis](#10-limits-of-this-analysis)

## 1. Why this document exists

Two open-source projects published agentic silicon-design flows that overlap
our Track D thesis. Reading them surfaced one concrete defect in our harness
and a set of small, cheap mechanisms that make the roadmap's M0 exit criteria
achievable now rather than aspirational.

The single sentence version:

> **Our physical gate cannot currently fail.** `harden-classic` and
> `harden-chip` report PASS whenever `make` exits zero, regardless of DRC, LVS,
> or timing. We already have the parsers to fix this; they are simply not
> wired into the gate.

The roadmap already identified this (§2.2, §14.3) twelve days before this
document. It is still open. This proposal makes it the first thing we fix and
supplies the mechanism.

## 2. The two upstream projects

Both are MIT licensed, so patterns and small code excerpts may be reused with
attribution.

### 2.1 `simra-tech/OpenADA` — a semantic contract, not a generator

OpenADA is a "narrow waist" between agents and EDA tools. It deliberately
contains **no design intelligence**: agents express versioned engineering
intent, deterministic drivers execute, and a normalized evidence envelope comes
back. Sixteen CLI command families over eight OSS tools (ngspice, Xyce,
KLayout, Netgen, Yosys, Verilator, OpenSTA, Xschem).

Its load-bearing idea is the `openada.result/v0alpha1` envelope:

```json
{ "schema", "operation", "tool": {"name","path","version"},
  "execution":  {"status","exit_code","duration_ms","command","cwd"},
  "engineering":{"status","summary"},
  "inputs":  [{"kind","role","path","exists","bytes","sha256"}],
  "artifacts":[{"kind","role","path","exists","bytes","sha256"}],
  "diagnostics":[{"level","message"}], "data": {}, "provenance": {} }
```

with two **disjoint** status enums:

| Field | Values | Question answered |
|---|---|---|
| `execution.status` | `completed`, `timed_out`, `not_available`, `invalid_request`, `failed` | Could we invoke and observe the process? |
| `engineering.status` | `pass`, `fail`, `unknown`, `not_applicable` | What does the evidence support? |

Documented rule: *a zero exit never implies pass; a nonzero exit never implies
fail; an incomplete execution normally leaves engineering `unknown`.*

Two further mechanisms are worth more to us than the envelope itself:

- **Assertion profiles with mandatory `non_goals`.** Each operation publishes
  one primary assertion: an `id`, a one-sentence `statement`, a `non_goals`
  array with `minItems: 1` — *you cannot ship an operation without stating what
  it does not prove* — and a truth table whose pass/fail/unknown branches each
  declare `allowed_execution_statuses` and `required_evidence`.
- **A machine-derived coverage ledger.** A catalog cross-products every CLI
  leaf, profile, feature, native mapping and provider capability into rows.
  Adding any capability *mechanically materializes a new row* at
  `unverified`, so shipping a feature automatically creates visible,
  CI-enforced debt. Rows climb `unverified → contract-tested →
  native-replayed → workflow-validated → agent-ready`, where `agent-ready`
  additionally requires a **trustworthy negative replay** and a **fail-closed
  tamper replay**. Release CI demands every active row reach `agent-ready`,
  and *"a waiver array is intentionally rejected."*

Caveats we verified: OpenADA has **no MCP binding** (deferred), and its
external-provider dispatch registry currently contains exactly one operation
(`circuit.simulate`). **MOSAIC cannot become an OpenADA provider today.**
Consuming their drivers, or exporting an OpenADA-shaped view of our evidence,
are both feasible.

### 2.2 `facebookexperimental/coresmith` — prompt to GDS

CoreSmith is the opposite bet: LangGraph state machines drive LLM agents that
write the architecture spec, the Verilog-2005 RTL, and the cocotb testbenches,
then Yosys/Sky130 and OpenROAD/Magic/netgen close it physically. Published
results: five PPABench designs, four signed off at 0 DRC and LVS match at
50 MHz.

**We should not copy its premise.** LLM-authored RTL is the direct negation of
our contract that generated RTL comes from reviewed templates. What is worth
copying is the machinery it built to survive that premise:

- `orchestrator/langgraph/gate_guard.py` — a gate that **raises** is
  `passed=False`, never a pass. One global rollback env var is the only escape
  hatch, and an errored gate synthesizes a violation record so it flows into
  normal handling instead of vanishing. Their own docstring names the bug this
  fixed: call sites that wrapped a gate in `try/except` and returned
  `passed=True`, *"a fail-OPEN default that silently shipped a block whose gate
  could not run."*
- **DRC honesty fallback** (`backend_helpers.py:1289-1308`) — when the DRC
  count parsed from stdout is blank or zero, recount from the report file and
  **take the larger number**, so a blank tool summary can never mask real
  violations.
- **Coverage as a reject-only gate** (`harness/coverage.py`) — below-floor line
  coverage demotes a DV pass to a failure with the uncovered regions fed back
  as testbench repair guidance, while *above-floor coverage proves nothing and
  is never treated as evidence of correctness*.
- **Deterministic router over LLM diagnosis** (`_route_decision`) — the debug
  agent emits `{category, confidence, needs_human, ...}`, but a fixed Python
  ladder picks the next node. Anti-thrash rules: same category three times →
  escalate; infrastructure error → retry once then ask a human; confidence
  below 0.3 → ask a human. **The model never chooses the next graph node.**
- **Disk-first append-only constraint memory** — corrective constraints are
  appended to `.coresmith/blocks/<b>/constraints.json`, which every subsequent
  prompt is told to read, so a lesson survives across retries *and sessions*
  instead of dying with the conversation.
- **Oracle tamper manifest** (`state_store/trust.py`) — SHA-256 of the golden
  model, stimulus and specs snapshotted at run start and recomputed at
  gate-accept time; drift is reported as `ORACLE_TAMPER`.

### 2.3 `mattvenn/librelane_summary` — ground truth for the run layout

A 300-line MIT tool (31★) that reads working LibreLane runs. It contributed no
architecture but settled the question our signoff parsers could not answer from
documentation: **where the evidence actually is.**

```text
runs/<RUN_TAG>/
  final/metrics.csv                                  # Metric,Value rows
  final/metrics.json                                 # same data when present
  final/gds/*.gds
  *-magic-drc/reports/drc_violations.magic.rpt
  *-netgen-lvs/reports/lvs.rpt
  *-openroad-stapostpnr/summary.rpt
  *-openroad-checkantennas/openroad-checkantennas.log
  *-yosys-synthesis/reports/stat.json
```

Two of its behaviours became design rules for us:

- Its summary view selects **every** metric row whose key contains
  `violation` or `error`, rather than a hardcoded key list. LibreLane's metric
  vocabulary drifts between versions, so a fixed key list silently goes blind
  on upgrade. We adopted this as a **generic adverse sweep running alongside**
  the curated key map: an unknown or renamed violation counter still fails the
  gate.
- When the DRC report is absent it prints *"no DRC file, DRC clean?"* — with a
  question mark, because it genuinely cannot tell. That ambiguity is exactly
  the `PASS`/`INFRASTRUCTURE_ERROR` boundary, and we resolve it the other way:
  **no evidence is never clean.**

It also corrected two wrong guesses in the first version of this branch:
`harden-classic` saves views to `final_classic`, not `final`, and the real
evidence is in the `runs/` tree rather than the saved-views directory at all.

### 2.4 The essential difference

OpenADA puts zero intelligence in the system and buys trust from a stable,
content-addressed evidence boundary — so it cannot build anything. CoreSmith
puts all intelligence in LLM agents and buys trust back with fail-closed gates
— so it is only as good as those gates, and it is welded to one PDK and one
flow.

MOSAIC sits between them and, on one axis, ahead of both: `tb-matrix` proves a
**pairwise covering array over the generated design space**, where CoreSmith
proves five hand-chosen designs and OpenADA proves none. What we lack is the
part both have: gates on the physical side that can actually fail.

## 3. Verified findings in this repository

All checked directly on `dev-mld` at the date of this document.

### 3.1 The physical gate is fail-open (blocking)

`harness/skills/flow_runner.py:360` computes:

```python
ok = proc.returncode == 0
if spec.get("require_exit_success"):
    ok = ok and metrics.get("exit_success") is True
elif "exit_success" in metrics:
    ok = ok and bool(metrics["exit_success"])
if "all_pass" in metrics:
    ok = ok and bool(metrics["all_pass"])
```

Line 344 routes any flow whose name contains `harden` into
`_parse_cocotb_result`, which searches for `TESTS=/PASS=/FAIL=` and
`EXIT SUCCESS` — **markers LibreLane never emits**. Neither `harden-classic`
nor `harden-chip` sets `require_exit_success`. Both metric keys are therefore
absent and `ok` collapses to the exit code.

`harness/skills/drc_triage.py` already contains working parsers —
`_parse_magic_drc` (`:72`), `_parse_klayout_drc` (`:98`),
`_parse_netgen_lvs` (`:125`) — that are never consulted by the gate.

**Consequence:** a LibreLane run that completes with DRC violations reports
`Flow 'harden-classic' PASS`.

### 3.2 `physical_ok` overstates what happened

`harness/agent.py:423, 794, 919` — set after a successful registered physical
flow, with freshness checks but no timing, area, power, DRC, or LVS threshold.
Roadmap §14.3 asks for the rename to `physical_command_completed`; still open.

### 3.3 SRAM capacity labels conflate bits and bytes

`sw/vendor/openram/configs/mosaic_sram_32k.py:21-22`:

```python
word_size = 8        # 8-bit words (byte-wide)
num_words = 4096     # 4096 words → 4096 × 8 = 32,768 bits = 32KB
```

32,768 bits is 4 KiB, not 32 KB. `mosaic_sram_4k.py:18-19` has the same
conflation (`512 × 8 = 4096 bits` labelled "4KB"; it is 512 bytes).

This is listed in roadmap §14.1 as a labelling issue. **It is more than that.**
Any area, power, or memory-map reasoning that used "32 KB" for a macro that is
4 KiB will propagate a factor-of-eight error into the first PPA numbers we
produce. Resolving it requires a design decision (see §8), not just a comment
fix.

> **RESOLVED 2026-07-28.** The macro is a 4 KiB array; the names were wrong.
> Renamed to true capacity (`mosaic_sram_4k.py` = 4096×8 = 4 KiB,
> `mosaic_sram_512b.py` = 512×8 = 512 B) with the capacity claims corrected in
> both config headers, the OpenRAM README and DASHBOARD. Nothing in the flow
> referenced either filename, so no build path changed.

### 3.4 TDU energy counter

`hw/tdu/rtl/tdu.sv:67` — `energy_counter_q`, documented at `:14` as an
"active cores × cycles proxy". It weights a SERV hart and a BOOM hart equally
and performs ordinary 32-bit addition despite a comment claiming saturation.
Roadmap §14.2; still open.

### 3.5 What is already strong and must not regress

- The agent runtime binds completion evidence to a config SHA-256 **and** the
  same source-closure digest used by the build manifest; a pass for another
  target, or after any RTL/firmware/flow edit, does not count
  (`harness/EVALUATION.md`).
- `flow/librelane/Makefile` accepts physical source only through a bound,
  hashed `PHYSICAL_BUNDLE` validated by `scripts/preflight.py`. This is real
  provenance and the natural anchor for evidence records.
- Gate prerequisites are executable policy, not prose: `mosaic-gen-config` is
  blocked until `topology_check` passes; `tb-soc-*` until `mosaic-gen-config`
  passes; physical flows require `--allow-physical`.
- API keys are environment-only and stripped from every EDA subprocess.

## 4. What we adopt, and from where

Ranked by payoff over effort. Items 1–3 are prerequisites for the rest.

| # | Adoption | Source | Effort |
|---|---|---|---|
| 1 | **Fail-closed gate guard.** Every gate runs wrapped; a gate that raises, or that produces none of its declared required evidence, is `FAIL`/`INFRASTRUCTURE_ERROR`, never PASS. Single documented rollback env var. | CoreSmith `gate_guard.py` | S |
| 2 | **`required_evidence` on every `FlowSpec`.** A flow declares the evidence keys it must produce. Absent evidence is `INFRASTRUCTURE_ERROR`. This is what closes §3.1 generally rather than special-casing `harden`. | roadmap §12.5 + CoreSmith | S |
| 3 | **Signoff parsers bound into the gate**, reusing `drc_triage`'s existing parsers, plus WNS/TNS/area, plus the **corroborated-zero rule**: a zero violation count from a primary source must be confirmed by an independent recount of the report; take the larger. | CoreSmith DRC honesty fallback | M |
| 4 | **Assertion records with mandatory `non_goals`.** Each gate publishes one sentence of what it proves and at least one sentence of what it does not. `all-harts-live` states plainly that it does not establish functional correctness, timing closure, or physical realizability. | OpenADA assertion profiles | S |
| 5 | **Evidence record over today's flows** (roadmap §12.3 shape) with an **OpenADA-shaped export** for interop. Start with `config_sha256` + `source_closure_sha256`, which we already compute; leave `resolved_ir_sha256` as `UNKNOWN` until M1. | roadmap §12.3 + OpenADA | M |
| 6 | **Operation-maturity ledger.** A third axis beside component maturity (§1 of the roadmap) and design evidence maturity (§3.3): which of our flows and skills have ever been proven to produce trustworthy evidence, *including a trustworthy negative*. Rows auto-materialize at `unverified` when a flow or core is added. | OpenADA semantic coverage | M |
| 7 | **Coverage as a reject-only gate** on the `tb-matrix` sim tier and `tb-smith`. Below floor fails with uncovered regions as feedback; above floor proves nothing. | CoreSmith `coverage.py` | M |
| 8 | **Per-row coverage, no borrowing.** Today a passing full-SoC wake demo implicitly "covers" every core in the config. A core's row should be covered only if the log contains *that hart's own* sentinel write. | OpenADA non-borrowing rule | S |
| 9 | **Pre-launch snapshot / post-run re-verification.** Snapshot `(st_dev, st_ino, st_size, st_mtime_ns)` + SHA-256 of every input before a run; re-verify before accepting the result. Directly kills the stale-RTL trap this project already documents. | OpenADA tamper gate + CoreSmith `trust.py` | S |
| 10 | **Structural acceptance predicates on agent output.** An SCI wrapper must declare `module <core>_sci`, expose the exact SCI port set, and appear in both `AVAILABLE_CPUS` and the `cpu_subsystem.sv.tpl` branch. Cheap, deterministic, and they should raise. | CoreSmith post-generation validators | S |
| 11 | **Disk-first constraint memory** at `.mosaic/cores/<core>/constraints.json`, read by `wrapper-smith` and `tb-smith`, so an integration lesson survives across retries and sessions. | CoreSmith constraint memory | S |
| 12 | **Bounded repair loop with a deterministic router.** Two same-context retries, then a classify step over a **closed** failure vocabulary (`BUS_PROTOCOL_MISMATCH`, `ADDRESS_WINDOW_OVERLAP`, `WAKE_TIMEOUT`, `LINT_FAIL`, `MACRO_AREA_OVERFLOW`, …). A Python ladder picks the next action; the model never does. Same category three times → escalate. | CoreSmith `_route_decision` | L |
| 13 | **Resumable long runs with human approval.** `harden` is 2–4 h; a killed process currently loses everything. | CoreSmith daemon | L |
| 14 | **Paired-agent evaluation.** The cheapest useful piece is the campaign-local monotonic clock domain — no crypto, and it makes retroactive reordering and cherry-picked reruns detectable. | OpenADA evaluation kit | L |

## 5. What the roadmap already covers better

For the reviewer's benefit, several things I initially proposed are already
specified more precisely in `general_multicore_soc_generator_roadmap.md`:

- **Evidence states.** §12.2's six states are a strict superset of OpenADA's
  four, adding `UNSUPPORTED` (a deterministic capability proof) and
  `INFRASTRUCTURE_ERROR` (ran, but no parseable mandatory report). We adopt
  §12.2's vocabulary, not OpenADA's.
- **The evidence record.** §12.3 already carries `subject{}`, `producer{}`
  including `parser_sha256` and `flow_spec_sha256`, `context{}` with PDK
  revision/corner/voltage/workload, and `metrics[]`/`requirements[]` with
  units and fidelity. OpenADA has no metrics or requirements concept at all.
- **Cache invalidation.** §12.7's rule that a *parser* change invalidates
  dependent evidence is handled by neither upstream project.
- **Bounded multi-fidelity DSE with a Pareto frontier** (§12.6) has no
  counterpart anywhere upstream.

The upstream contribution is therefore **mechanism and discipline, not
architecture**: `gate_guard` makes `INFRASTRUCTURE_ERROR` real rather than
aspirational, the corroborated-zero rule closes a hole in §12.5, and the
maturity ledger is the CI that stops §3.1 from silently returning.

## 6. Implemented on this branch

Branch `mld-exp`, incremental and additive — no existing flow behaviour changes
except that a flow which declares required evidence and does not produce it now
fails.

- `harness/evidence/status.py` — the roadmap §12.2 evidence states and the
  OpenADA execution states, with the `only PASS closes a required node` rule
  encoded as `EvidenceStatus.closes_required_node`.
- `harness/evidence/gate_guard.py` — fail-closed gate wrapper, structured
  finding on gate error, `MOSAIC_GATE_FAIL_OPEN` rollback knob.
- `harness/evidence/librelane.py` — locates the newest run under `runs/`,
  reads `final/metrics.json` or `final/metrics.csv`, resolves the per-step
  report paths, and runs the generic adverse sweep. PDK-neutral.
- `harness/evidence/signoff.py` — verdicts from a run's structured metrics
  when available, falling back to console/report scraping otherwise; the
  corroborated-zero rule applies on both paths.
- `harness/skills/flow_runner.py` — `required_evidence` on `FlowSpec`s;
  `harden-*` now read the LibreLane run tree instead of cocotb markers; the
  gate is fail-closed.
- `test/test_x_heep_gen/test_evidence_gates.py` (25 tests) and
  `test_librelane_evidence.py` (21 tests) — negative fixtures, per the
  roadmap's own M0 exit criteria: an exit-zero run with DRC violations must
  FAIL; an exit-zero run with no parseable report must be
  `INFRASTRUCTURE_ERROR`; a gate that raises must not pass; a violation
  counter we have never heard of must still fail the run.

Full suite: 486 passed.

## 7. Proposed work packages

**WP0 — truth (this branch, in progress).** Items 1–3 above, plus the
`physical_ok` → `physical_command_completed` rename. Exit criterion: the
roadmap's own M0 negative fixtures pass.

**WP1 — evidence record.** Items 4–5. Build roadmap §12.3's record on today's
`RunReport`, with `resolved_ir_sha256` and `design_lock_sha256` reported as
`UNKNOWN` — exactly what the roadmap's truth rules prescribe for a missing
value. This deliberately decouples the evidence engine from the M1 IR
migration.

**WP2 — ledger and coverage.** Items 6–9. This is what prevents regression.

**WP3 — agentic hardening.** Items 10–12. The Phase-2 differentiators.

**WP4 — standalone packaging.** §9.2: package boundary, agent-plugin
manifests, a second PDK, pinned toolchain. Parallelizable with WP2/WP3.

**WP5 — the roadmap's M1/M2**, then M3 as the first published vertical slice.

**Sequencing note (revised 2026-07-28).** An earlier version of this document
argued for deferring M1/M2 until after tapeout, because M1's own exit criterion
is that generated RTL stays byte-identical and it puts a working generator at
risk under deadline pressure. With MOSAIC repositioned as a standalone project
(§9) that argument no longer holds: every axis of breadth a standalone
generator is judged on runs through the backend abstraction M1/M2 provides.
The order becomes gates → evidence → packaging → IR → published slice. What
does *not* change is that gates come first: breadth on top of a gate that
cannot fail is worse than no breadth.

## 8. Decisions requested from the team

1. ~~**SRAM capacity (§3.3):** is the intended macro 4 KiB or 32 KiB?~~
   **Answered 2026-07-28: 4 KiB.** Names and docs corrected; arrays unchanged.
2. **`harden-nodrc` / `classic-nodrc`:** confirm these are developer
   conveniences that are structurally incapable of producing signoff evidence,
   so the gate can mark them `NOT_APPLICABLE` for DRC rather than `PASS`.
3. **Coverage floor:** what line-coverage floor, if any, should reject a
   `tb-matrix` sim pass? CoreSmith defaults to 70%. Suggest starting the gate
   in report-only mode.
4. **Repair loop (item 12):** do we accept a bounded loop where the model
   *proposes* a fix and the deterministic gate re-adjudicates from scratch?
   This is compatible with roadmap §12.1 only if the model can never annotate a
   failure into a pass.
5. **Sequencing:** do we agree to defer M1's IR work until after tapeout in
   favour of WP0–WP2?

## 9. Standalone positioning

**Decision taken 2026-07-28: MOSAIC is to be a standalone project, comparable
to OpenADA and CoreSmith, not a competition deliverable.** This section records
what that changes. It reverses one recommendation made earlier in this document.

### 9.1 What it reverses

§7 previously argued for deferring the roadmap's M1/M2 (v2 schema, intent and
resolved IR, catalogs) until after tapeout, on the grounds that M1 produces no
new evidence and risks a working generator during deadline pressure. **With the
deadline removed, that argument collapses.** A standalone generator is defined
by the breadth of what it can generate and sign off, and every axis of breadth
runs through the backend abstraction M1/M2 provides:

- more than one PDK (today: GF180 only, hardcoded in `flow/librelane/`);
- more than one physical flow (today: LibreLane only);
- more than one platform class (today: `xheep_mcu_amp` only, and it is not
  named as a backend because there is nothing to distinguish it from);
- PPA objectives at all, which is what makes a generator worth pointing at a
  design space rather than a config file.

Revised position: **WP0–WP2 still come first**, because a generator whose gates
cannot fail has nothing to be broad *about*. But M1/M2 become the next
priority rather than deferred work, and the ULP vertical slice (M3) becomes the
first *published* result — the standalone equivalent of CoreSmith's PPABench
table.

### 9.2 What standalone additionally requires

None of this is in the roadmap, because the roadmap assumed an in-repo tool.

| Requirement | Today | Gap |
|---|---|---|
| **Installable off the repo** | `harness/` imports `util.xheep_gen.core_registry` and resolves `REPO_ROOT` from `__file__` | Needs a package boundary; the registry is a legitimate dependency but the repo-root assumption is not |
| **Agent-plugin distribution** | `.claude/skills/` is project-local; the `.omp/tools/` shim is repo-relative | OpenADA ships `.claude-plugin/` + `.codex-plugin/` marketplace manifests so third parties can `/plugin marketplace add`. We should do the same with our existing cards — the cards are already the right shape |
| **PDK-neutral signoff** | `flow/librelane/` is GF180-specific; `harness/evidence/librelane.py` is deliberately PDK-neutral | Add sky130 as the second PDK; it is the widest-tested open PDK and the one CoreSmith uses, which makes results comparable |
| **Flow-neutral signoff** | LibreLane only | The evidence layer already separates *reading* signoff from *running* it; a second reader (ORFS) proves the boundary |
| **Reproducible conformance** | No pinned container; Verilator pinned by convention only | OpenADA pins an IIC-OSIC-TOOLS image and runs conformance network-disabled; CoreSmith ships a devcontainer and a Nix flake. We have `flow/librelane/flake.nix` already — extend it to the whole toolchain |
| **Published evidence bundles** | Evidence is internal to a run | The §12.3 record plus the OpenADA-shaped export becomes the public artifact: this is how an outsider checks a claim without rerunning it |
| **Outward-facing identity** | README addresses Chipathon Track D | Rewrite around the capability, not the competition. The tapeout work becomes *a proof point*, not the purpose |
| **A comparable published result** | tb-matrix covers the space in simulation | Neither upstream project has a covering array — this is our headline. It needs a table an outsider can read, and at least a few points carried through to GDS |

### 9.3 Honest competitive position

Stated plainly, so the README does not overclaim:

- **Ahead of both:** systematic coverage of a generated design space
  (`tb-matrix` pairwise covering array over 11 axes) and a real heterogeneous
  multi-core integration mechanism (`wrapper-smith`, 9 protocol families, 8
  touchpoints). CoreSmith proves five hand-picked designs; OpenADA generates
  nothing.
- **Behind OpenADA:** the evidence contract is internal, unversioned, and not
  exported; there is no conformance kit, no driver abstraction, and no
  published maturity ledger.
- **Behind CoreSmith:** no repair loop, no human-escalation model, no resumable
  long runs, no published PPA results, and — until this branch — no working
  physical gate.
- **Behind both:** not installable as a package, not distributable as a
  plugin, single PDK, single flow.

The shortest path to a defensible standalone claim is therefore WP0–WP2
(gates and evidence), then packaging and a second PDK, then M1/M2, then a
published vertical slice. Breadth without trustworthy gates would be the worst
possible order.

## 10. Limits of this analysis

Stated explicitly so the reviewer can calibrate.

- The upstream reads are first-hand: both READMEs, OpenADA's `CONTRACT.md`,
  `PROVIDERS_AND_MCP.md`, `SEMANTIC_COVERAGE.md`, `ENGINEERING_SKILLS.md` and
  several schemas; CoreSmith's `gate_guard.py`, `trust.py`, `coverage.py` and
  the DRC/LVS regions of `backend_helpers.py`.
- A planned automated cross-check of these recommendations against our
  repository **did not complete** (it exhausted its budget partway). The
  repository findings in §3 were verified by hand at the cited lines; the
  effort estimates in §4 were not independently reviewed.
- CoreSmith's published PPABench results are taken from its README and were not
  reproduced.
- **Nothing here has been run against real LibreLane output.** The run *layout*
  is now ground truth from `librelane_summary`, and the tests build that
  layout on disk — but the metric **key names** (`magic__drc_error__count`,
  `design__lvs_error__count`, `timing__setup__ws`, …) are from the
  OpenLane 2/LibreLane metric vocabulary and are **not** verified against our
  GF180 flow. If a key is wrong, the curated path misses it and only the
  generic `violation|error` sweep catches it — which is why that sweep exists,
  but it is a safety net, not a substitute. **One real hardening run remains
  the most important open verification item.**
- `harden-nodrc` / `classic-nodrc` are Make targets that are not registered as
  harness flows. If they are ever registered they must be given
  `require_drc=False` and `require_antenna=False`, or the gate will report
  `INFRASTRUCTURE_ERROR` for checks the flow deliberately skipped.
