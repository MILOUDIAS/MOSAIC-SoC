# Block A — closure report against the re-review

> **Scope.** This document answers exactly one thing: the re-review comment by
> @tai08 on [sscs-ose/sscs-chipathon-2026#134][issue] (outcome: **Go**), and its
> three must-close-before-tapeout items. It was previously a general closure
> report for the *first* (schematic) review; that material is in git history at
> `ec3a194` and earlier, and the reviewer's own comment records what he verified
> from it.
>
> The reply posted to the issue is [`chipathon_rereview_response.md`](chipathon_rereview_response.md).
> This is the evidence behind it.

[issue]: https://github.com/sscs-ose/sscs-chipathon-2026/issues/134

**Branch:** `mld-rtl-freeze` · **Design:** `mosaic_block_a` · **PDK:** GF180MCU (gf180mcuD)

---

## Status against the close-out list

| Item from the re-review | State |
|---|---|
| Config consistency | **resolved** — confirmed below, unchanged |
| Signoff (DRC/LVS/XOR/antenna/PG/STA) | **verified by the reviewer**, and still clean |
| Clock target locked, re-hardened at that period | **OPEN — needs the track lead.** 25 MHz measured and closes |
| 591 max-slew closed | **CLOSED** — 0 against per-pin library limits, all nine corners |
| 1 max-fanout closed | **OPEN** — real, waived at `accepted_max: 1` |
| Timing-annotated GLS raised with the organizers | **OPEN** — to raise |
| Tag the re-hardened commit | blocked on the clock confirmation only |

Two of the three must-close items moved. The remaining two open items are both
decisions by other people, not work items on this side.

---

## 1. Config consistency — resolved

The reviewer verified: *"Die is Block A (1,248,810 µm²); `mosaic_block_a.sv` is a
22-pin all-digital interface (20 signal + VDD/VSS), confirmed against LVS
('Circuits match uniquely'). `pad_cfg.py` / `slot_mosaic.yaml` are correctly
marked not used by Block A."*

All still true. For the record, the pin arithmetic — the wrapper declares 11
ports, which expand to 20 signal pins:

| port | width |
|---|---|
| `clk_i`, `rst_ni`, `boot_select_i`, `execute_from_flash_i` | 1 each |
| `spi_flash_sck_o`, `spi_flash_cs_o` | 1 each |
| `spi_flash_sd_io[3:0]` | **4** |
| `uart_rx_i`, `uart_tx_o`, `status_valid_o` | 1 each |
| `status_o[6:0]` | **7** |
| | **20 signal** + VDD/VSS = **22** |

Die: 1117.5 × 1117.5 µm = **1,248,806 µm²** (the reviewer's 1,248,810 is the same
number rounded). All pins are digital; there is no analog pin on this block.

**The two functional bugs** the reviewer credited, and the form their regression
coverage actually takes — worth stating precisely, because the two are covered
differently:

| bug | fix | regression |
|---|---|---|
| DMA tie-off overwrote the `soc_ctrl` response | `ao_peripheral_subsystem.sv.tpl` no longer indexes `ao_peripheral_slv_rsp[DMA_CH0_IDX]` (index 0 = `SOC_CTRL_IDX`) | **static test** — `test_dma_selection.py::test_absent_dma_never_indexes_the_ao_demux_with_a_channel_index` fails if the pattern returns. `ERROR_ON_SYNTH_CHECKS` is also back **on**, which is what exposed it |
| SERV extension Wishbone port tied off | `serv_sci.sv` arbitrates both of servile's Wishbone ports onto its OBI master (`pick_ext`, `ext_owns_q`, `wb_ext_ack`) | **covered by execution** — any data access at or above `0x4000_0000` stalled the hart, so the full-SoC sim and the post-route GLS cannot reach `EXIT SUCCESS` unless flash data loads complete |

---

## 2. Signoff — what was verified, and what has changed since

The reviewer verified `runs/blocka_signoff`. Those numbers are unchanged and are
reproduced here as the baseline. Two later runs are included because the slew
work below produced them:

| | `blocka_signoff` (reviewed) | `blocka_sdc` (10 MHz, current) | `blocka_25mhz` |
|---|---|---|---|
| Magic DRC / KLayout DRC / routing DRC | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| XOR | 0 | 0 | 0 |
| Antenna | 0 | 0 | 0 |
| Netgen LVS | match uniquely, 0 errors | same | same |
| Disconnected pins | 0 | 0 | 0 |
| Power-grid violations | 0 | 0 | 0 |
| setup WS / TNS | +20.8615 ns / 0 | +20.9022 ns / 0 | **+1.6632 ns / 0** |
| hold WS / TNS | +0.0661 ns / 0 | +0.0662 ns / 0 | +0.0662 ns / 0 |
| max-slew / max-cap / max-fanout | 591 / 0 / 1 | **0** / 0 / 1 | **0** / 0 / 1 |
| utilisation | 84.39 % | 85.16 % | 85.15 % |
| functional post-route GLS | EXIT SUCCESS, 12,399 cyc | same | **EXIT SUCCESS, 12,399 cyc** |

The utilisation difference is not a floorplan change — the die is 1117.5 µm in all
three. `blocka_sdc` and `blocka_25mhz` carry a higher post-GRT repair margin
(`GRT_DESIGN_REPAIR_MAX_SLEW_PCT` 10 → 32), which buys timing-repair buffering.

**No waiver is applied to DRC, LVS, XOR, antenna or the power grid.** All return
zero without one. The single waiver on this design is the max-fanout one in §4.

---

## 3. Must close #1 — the clock target

> *"Clock target must be locked with track leads and the integration team now …
> 25 MHz should be reachable, but the numbers must be re-run at the locked period
> to count."*

**Agreed, and not closed here: locking it is the track lead's and the integration
team's call.** What this side can supply is the measurement rather than an
estimate, so the decision is not made on a projection.

Block A was re-hardened at 25 MHz — `flow/librelane/experimental/config_blocka_25mhz.yaml`,
run `runs/blocka_25mhz`. It differs from the 10 MHz config in **exactly one key**,
`CLOCK_PERIOD: 100 → 40`; same die, same pinned RTL bundle. Results are the third
column of §2: **it closes, with every check clean and GLS passing.**

Two caveats belong in the clock conversation, because *it closes* is not *it is
comfortable*:

1. **The margin is thin.** +1.663 ns is **4.2 %** of a 40 ns period. Positive at all
   nine corners with TNS 0, but there is little guardband above 25 MHz.
2. **The binding path moves, away from the one identified in the review.** At
   10 MHz the worst setup path is the half-cycle output path
   `_61322_ → spi_flash_sd_io[2]` (+20.90 ns). At 25 MHz that is no longer
   critical; the worst becomes an internal register-to-register path
   `_61219_ → _61238_` (+1.663 ns). **Work on the QSPI output path buys nothing at
   25 MHz — the limit is inside the core.**

GLS was re-run rather than argued from identity: the 25 MHz netlist is *not*
byte-identical to the 10 MHz one, because the period changed and P&R genuinely
differs.

### Where the clock lives now

`configs/mosaic_tapeout_ultra.yaml` carries `soc.objectives.target_clock_mhz: 25`,
so `physical-intent harden` derives `CLOCK_PERIOD: 40` from design intent. Before
this the frequency had nowhere to live and could only be set by hand-editing a
LibreLane config — which is the only reason `config_blocka_25mhz.yaml` exists.

**The value is a request, not an agreed target.** The key is named for that and STA
decides whether it was met. Once a clock is confirmed: change that one line,
re-run, tag, and **delete** `config_blocka_25mhz.yaml` rather than maintaining a
second place where the frequency is written down.

---

## 4. Must close #2 — 591 max-slew and 1 max-fanout

> *"591 max-slew (worst 5.19 ns vs the library's 4.0 ns) + 1 max-fanout (max-cap 0),
> all at ss_125C_4v50. TT and FF corners are clean."*

Both halves of that observation are correct, and **together they are the
diagnosis**. Chasing why they are in tension is what closed the item.

### The 591 were measured against the wrong corner's limit

`max_transition` in the GF180 standard-cell libraries is declared **per input pin
and per corner** — 836 declarations in each corner file:

| corner | `max_transition` |
|---|---|
| `tt_025C_5v00` | 4.0 ns |
| `ss_125C_4v50` | **7.0 ns** |
| `ff_n40C_5v50` | 2.6 ns |

4.0 ns is the **typical** corner's number. It reached all nine corners because
`MAX_TRANSITION_CONSTRAINT: 4` emits `set_max_transition 4.0 [current_design]`,
and `PNR_SDC_FILE` and `SIGNOFF_SDC_FILE` were **both unset** — so implementation
and signoff shared one SDC.

That is why every violation sat at `ss_125C_4v50` with TT and FF clean: they
cluster at the corner where the library is *most permissive*, which is the
opposite of what a genuine slew problem looks like.

Re-measured on `runs/blocka_signoff/final` — the netlist the reviewer verified —
with OpenSTA 2.7.0 and per-pin liberty limits:

```
CONTROL   shipped SDC, max_ss_125C_4v50        591 violations   (reproduces exactly)
LIBRARY   per-pin limits, all nine corners       0 violations
worst pin spi_flash_sd_io[3]   limit 7.00   slew 5.19   slack +1.81   MET
```

The worst pin in the design clears the limit its cells are qualified to by
1.81 ns. **The control reproducing 591 exactly is what makes the zero credible**
rather than a misconfigured run. Both halves were executed as printed in §7.

**This claim originated here.** Earlier revisions of this report said the
violations were measured "against the 4.0 ns limit the library declares for every
cell". That sentence was ours and it was wrong; the reviewer read the number he
was given correctly.

### Dropping the constraint is the obvious fix, and it is wrong

`MAX_TRANSITION_CONSTRAINT: null` was tried (`runs/blocka_libtran`). The
constraint is an **optimisation target**, not just a reporting threshold —
removing it stops P&R buffering toward 4.0 ns and the design then degrades past
the library's **own** limits:

| Block A | 4.0 ns (as reviewed) | `null` | PnR/signoff split |
|---|---|---|---|
| max-slew reported | 591 | 10 | **0** |
| max-cap reported | 0 | 5 | **0** |
| logic area µm² | 959,888 | 930,098 (−3.10 %) | 959,888 |
| violates the *library*? | no | **yes** — 7.1998 ns vs a 7.0 ns pin rating | no |

So the ~3 % of cell area the repair pass spends is not waste — it is what keeps
the design inside its qualified range. The review's instinct that a blanket lever
was the wrong tool held in both directions: `bufz_8` on the pads made slew worse
(591 → 785, worst 5.19 → 9.51 ns, because those pads are input-slew limited), and
so does removing the target.

### The fix: split PnR from signoff

`PNR_SDC_FILE` and `SIGNOFF_SDC_FILE` are separate LibreLane variables. The
template now sets only the second, to
`flow/librelane/experimental/signoff_library_limits.sdc` — a wrapper that unsets
the variable `base.sdc` guards on and then *sources* `base.sdc`, so it cannot
drift from the SDC P&R uses. P&R still targets 4.0 ns; signoff checks each pin
against its own liberty limit.

Across all three blocks, one differing config key in each case:

| design | baseline → new | post-P&R netlist | max-slew | adverse metrics |
|---|---|---|---|---|
| `mosaic_block_a` | `blocka_slew32` → `blocka_sdc` | **byte-identical** | 56 → **0** | 2 → 1 |
| `mosaic_block_b` | `blockb_slew32` → `blockb_sdc` | **byte-identical** | 17 → **0** | 2 → 1 |
| `mosaic_block_c` | `blockc_ant8` → `blockc_sdc` | **byte-identical** | 49 → **0** | 2 → 1 |

Byte-identical netlists and setup/hold slack equal to the last printed digit: the
silicon did not change, only the number it is measured against.

**It is not a blinded gate**, and that was checked rather than asserted — the same
library-limit check *caught* the degraded `null` netlist above, with 10 slew and
5 capacitance violations. It stops reporting non-defects; it still reports
defects.

### On the per-net suggestions

The review suggested per-net work: right-size the actual drivers rather than
inserting max buffers, consider a better routing-layer assignment, consider
non-default routing rules. Those are the right moves **for a real slew problem**,
and they were the plan. They became moot for max-slew when the violations turned
out not to be violations of anything the library objects to — but the reasoning
behind them (blanket levers are the wrong tool at 84 % utilisation, where inserted
cells have to fit somewhere) is what made removing the target look attractive and
then measurable, so the advice did its work.

### The max-fanout violation is real and stays open

Checked rather than assumed to be the same class of error: **the GF180
standard-cell libraries declare no `max_fanout` at all** — zero occurrences, no
`default_max_fanout`, in any corner file. So `MAX_FANOUT_CONSTRAINT: 10` overrides
nothing, there is no truer limit to defer to, and dropping it would remove the
check rather than correct it.

One net exceeds it, consistently across all nine corners — a structural fanout on
a single high-load net rather than a corner effect. It is recorded in
`flow/librelane/signoff_waivers.yaml` as the **only** waiver on the design:

| metric | design | `accepted_max` | evidence |
|---|---|---|---|
| `design__max_fanout_violation__count` | `mosaic_block_a` | **1** | `runs/blocka_sdc` |

`accepted_max` is a ceiling, not an exemption: a second violating net fails the
gate again.

---

## 5. Must close #3 — timing-annotated GLS

> *"The GF180 cell models use `ifnone` on edge-sensitive specify paths, which
> IEEE 1364-2005 §14.2.6 forbids … please raise it with the organizers / track
> lead."*

**Agreed that this is a shared PDK/tooling item rather than a Block A one, and it
will be raised.** Concretely, what to report:

- The GF180 cell models attach `ifnone` to edge-sensitive specify paths.
- iverilog refuses outright: `sorry: ifnone with an edge-sensitive path is not
  supported`.
- CVC segfaults at this design's scale (diagnosed as design size, not the specify
  library — see `tb/gls/README.md`).
- The question for the organizers: **does multi-corner STA suffice for signoff, or
  is timing-annotated GLS a required item?** The answer changes what "signed off"
  means for every team on this PDK, not just this block.

Functional post-route GLS continues to pass through the bonded interface only —
`EXIT SUCCESS` in 12,399 cycles, no backdoor memory loads and no hierarchical
forces. Timing coverage rests on STA at nine corners.

---

## 6. What is needed to tag

> *"Once the clock is confirmed and the design is re-hardened at that period, and
> slew/fanout are closed, tag that commit."*

| condition | state |
|---|---|
| clock confirmed | **waiting on the track lead / integration team** |
| re-hardened at that period | done for 25 MHz; trivially repeatable at another |
| slew closed | done — 0 at all nine corners against library limits |
| fanout closed | not closed; real, and waived at `accepted_max: 1` |

The fanout waiver is the one judgement call left for the reviewer: it is a
violation of a limit this project chose, on a design where the library states no
limit of its own. If a single high-fanout net is not acceptable in a waiver, say
so and it becomes per-net work; if it is, the tag is otherwise unblocked the
moment a clock comes back.

---

## 7. Reproducing

The slew measurement, exactly as run:

```sh
R=flow/librelane/experimental/runs/blocka_signoff/final
L=flow/librelane/gf180mcu/gf180mcuD/libs.ref
# the only change: drop the blanket constraint, keep every other SDC line
grep -v set_max_transition $R/sdc/mosaic_block_a.sdc > /tmp/nolimit.sdc
```

```tcl
# max_ss_125C_4v50 — where all 591 sit. All three libs the run itself loads at
# this corner; omitting the ws_io one changes the result.
read_liberty  $L/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__ss_125C_4v50.lib
read_liberty  $L/gf180mcu_fd_io/lib/gf180mcu_fd_io__ss_125C_4v50.lib
read_liberty  $L/gf180mcu_fd_io/lib/gf180mcu_ws_io__ss_125C_4v50.lib
read_verilog  $R/pnl/mosaic_block_a.pnl.v
link_design   mosaic_block_a
read_spef     $R/spef/max/mosaic_block_a.max.spef
read_sdc      /tmp/nolimit.sdc
report_check_types -max_slew -max_capacitance -violators
```

Run `sta` from inside `flow/librelane` (that is where `flake.nix` lives):
`nix develop --command sta -no_init -exit <script>.tcl`. Swap `/tmp/nolimit.sdc`
back for `$R/sdc/mosaic_block_a.sdc` and the same script prints all 591 again —
that is the control. Both halves were run as printed: **0** and **591**.

The 25 MHz hardening run:

```sh
make mosaic-gen MOSAIC_CFG=configs/mosaic_tapeout_ultra.yaml   # RTL bundle
cd flow/librelane
MOSAIC_CFG=<repo>/configs/mosaic_tapeout_ultra.yaml \
  ./experimental/run_signoff.sh blocka_25mhz experimental/config_blocka_25mhz.yaml
```

Gate-level simulation of any hardened run:

```sh
GLS_RUN=$PWD/flow/librelane/experimental/runs/blocka_25mhz ./tb/gls/run_gls.sh
```

### Where to look if you re-verify

The hardening config path has moved since the reviewed run, so a diff against the
old file would mislead:

| | file | still in the path? |
|---|---|---|
| SoC / RTL | `configs/mosaic_tapeout_ultra.yaml` | **yes**, plus `objectives.target_clock_mhz` |
| hardening | `flow/librelane/experimental/config_blocka_signoff.yaml` | **no** — retained as the record of what was reviewed |

Hardening configs are now derived from `flow/librelane/signoff_template.yaml` plus
a per-design floorplan block, which is what lets one template drive Blocks A, B
and C. Comparing the reviewed run's `resolved.json` against the current one, five
keys differ, of which two can affect the result:

| setting | `blocka_signoff` | `blocka_sdc` | effect |
|---|---|---|---|
| `GRT_DESIGN_REPAIR_MAX_SLEW_PCT` | 10 | 32 | more repair buffering — the 84.39 % → 85.16 % utilisation |
| `SIGNOFF_SDC_FILE` | unset | `signoff_library_limits.sdc` | **takes the 591 to 0** |
| `KLAYOUT_DRC_THREADS` | unset | 2 | none — a memory limit for an 11 GB host |
| `VERILOG_FILES` / `VERILOG_INCLUDE_DIRS` | bundle `…-04c589587b3b` | bundle `…-bf04958a677f` | none — content-identical apart from named-parameter order in two lowRISC flop wrappers |

`RUN_POST_GRT_DESIGN_REPAIR` was already on in the reviewed run,
`MAX_CAPACITANCE_CONSTRAINT` already null so per-cell liberty limits govern, and
`PNR_CORNERS` is unset in both.

---

## 8. Environment

| tool | version |
|---|---|
| LibreLane | 3.0.0 (Classic flow) |
| OpenROAD | 2026-02-17 |
| OpenSTA | 2.7.0 |
| Magic / Netgen / KLayout | as pinned by the LibreLane nix flake |
| iverilog | 12.0 (GLS; `-DFUNCTIONAL`, zero-delay) |
| PDK | GF180MCU `gf180mcuD`, `gf180mcu_fd_sc_mcu7t5v0` |

Generator test suite: **1 233 passed, 1 skipped** (`pytest test --ignore=test/test_apps`).
