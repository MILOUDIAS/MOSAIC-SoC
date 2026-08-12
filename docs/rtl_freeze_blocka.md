# RTL freeze — Chipathon Block A

**Frozen config:** [`configs/mosaic_tapeout_ultra.yaml`](../configs/mosaic_tapeout_ultra.yaml)
**Target:** Chipathon 2026 shared-die **Block A** — 1117.5 µm square (¼ of the 2235 µm
project area), 22 pins, delivered as a **hard macro with no pad ring**.
**Date:** 2026-08-01

This document exists because the schematic review asked one question the project could
not previously answer in one place: *which single configuration is being taped out, and
does it pass verification end-to-end?* Everything below is measured output, with the
command that produced it.

---

## 1. Which chip is frozen

**Neither of the two the review saw.** The `1× FazyRV + 2× SERV` die on the slide and the
7-hart PoC in the appendix are both superseded. The frozen part is:

| | |
|---|---|
| harts | **2** — SERV TITAN (`rv32ic`, CSRs, compressed) + SERV worker (`rv32i`, no CSRs, boots at `0x40010000`) |
| memory | no SRAM pool; **128 B scratchpad** (flip-flops), 1 KB boot ROM; code executes **XIP from external QSPI flash** |
| bus | OBI crossbar |
| dispatch | TDU enabled, `dynamic` |
| peripherals | UART only |
| removed | DMA, debug/JTAG, PLIC, SPI host (XIP reader only), AO rv_timer, AO fast-intr, GPIO-AO, multicore timer |

**The boot hart is SERV, not FazyRV.** The review asked whether boot had been verified on
FazyRV; that question is moot for this part — FazyRV is not in it. SERV boot is
demonstrated in §3.

FazyRV, and the other 10 core IPs, remain in the generator and are exercised by the
regression suite. None of them is in the tapeout config.

---

## 2. The RTL that was verified is the RTL that was hardened

The generator is content-addressed: a config resolves to `build/mosaic/<name>-<hash>/`.
Simulation and hardening ran from *different* hashes, because the simulation flow adds a
generated-firmware directory to the bundle. The RTL is the same, and that is checkable
rather than assertable:

```bash
A=build/mosaic/mosaic_tapeout_ultra-214a95bd8a9f/generated   # hardened -> the GDS
B=build/mosaic/mosaic_tapeout_ultra-cd64bd6a47c8/generated   # current tree
for f in $(cd $A && find . -name '*.sv' -o -name '*.svh' | sort); do
    cmp -s "$A/$f" "$B/$f" || echo "DIFFERS: $f"
done
# compared 26 RTL files, 0 differ
```

Three *software-contract* files do differ, and by design: `sw/boot_images.json`,
`sw/include/mosaic_topology.h` and `sw/include/mosaic_deployment.h` carry the
`target` string (`simulation` -> `tapeout`, §8) and its derived CRC. They are firmware
headers and do not enter synthesis.

The same comparison against the simulated bundle (`d35163443e02`) differs only by the
added `generic_fw/` directory; all 26 `.sv`/`.svh` files are byte-identical.

This also means the documentation-only changes in this branch changed **no** generated
output: the config's comment correction (it described "three SERV cores" while listing two
— exactly the drift the review flagged) and the "not the tapeout target" headers added to
`configs/pad_cfg.py` and `slot_mosaic.yaml`. Both files feed the content-addressed build
hash, so the bundle name moved; the 56 generated files did not. **The signed-off GDS
remains the artifact of this config**, and the command above is how to re-confirm that
rather than take it on trust.

---

## 3. Functional verification on the frozen config

```bash
MOSAIC_CFG=configs/mosaic_tapeout_ultra.yaml bash tb/mosaic_soc/run_generic.sh
```

This TB consumes the *generated* boot metadata, builds one ABI-correct firmware image per
boot slot, and requires **every** configured hart to report — it cannot pass by ignoring a
hart. Result:

```
image 0: flash offset 0x00000180 (XIP at 0x40000180), harts [0]
image 1: flash offset 0x00010000 (XIP at 0x40010000), harts [1]
flash image: .../generic_fw/generic.hex (2 harts, wake mask 2, XIP)
write hart=0 addr=0x200a0010: data=0x00010800      <- TITAN programs the TDU
write hart=1 addr=0x00000044: data=0x00000002      <- worker runs after its wake
write hart=0 addr=0x20000004: data=0x00000000      <- soc_ctrl exit value
write hart=0 addr=0x20000000: data=0x00000001      <- soc_ctrl exit valid
EXIT SUCCESS
### RESULT: EXIT SUCCESS — all 2 configured harts executed ✓
```

What this proves for this exact part, in order: the SERV TITAN boots from the boot ROM and
executes XIP from flash; it reaches the TDU at `0x200A0010`; the worker — which boots
**dormant**, since with `plic: false` and `debug: false` the TDU wake is its only possible
release — subsequently executes and writes its sentinel; and the exit register that drives
`status_o`/`status_valid_o`, the part's only observability, is written.

### What that program does and does not exercise

`tb/mosaic_soc/prog_generic/generic.S` is 60 lines of assembly. It identifies each hart by
`mhartid` (hart 0 by the reset-empty TDU queue), writes `sentinel[mhartid] = hartid + 1`,
wakes every non-TITAN hart through the TDU, waits for all configured harts, and exits.

Covered on the frozen part: boot-ROM entry, XIP execution from external flash, TDU register
access and worker wake, multi-hart execution, and the `soc_ctrl` exit register that drives
`status_o`.

Not covered by *this* program: UART traffic. That gap is closed separately by
`tb/mosaic_soc/run_uart.sh` (below), which was written because the area work had modified
the UART's RTL and nothing exercised it.

### UART bring-up test

```bash
MOSAIC_CFG=configs/mosaic_tapeout_ultra.yaml bash tb/mosaic_soc/run_uart.sh
### RESULT: EXIT SUCCESS — UART verified on configs/mosaic_tapeout_ultra.yaml
```

The area work cut BOTH OpenTitan UART FIFOs from 32 to 4 entries (0.066 mm², 61% of the
UART). That is hand-modified vendored RTL in a tapeout candidate, and it was untested.
`prog_uart/uart.S` checks three things on the frozen part:

| Phase | Check |
|---|---|
| 1 | **TX FIFO depth is really 4.** TX is left *disabled* so the FIFO cannot drain (`tx_fifo_rready` is gated by `tx_enable`, `wvalid_i` is not), 8 bytes are written blind, and `FIFO_STATUS.TXLVL` must read exactly 4. A positive measurement, not an inference from "it still prints" |
| 2 | **A polling driver loses nothing:** 23 bytes sent waiting on `!TXFULL`; the UART DPI log must match the string byte for byte |
| 3 | **RX path and RX FIFO** through the UART's own system loopback (`CTRL.SLPBK`), so no external stimulus is needed |

A failed phase parks *without* writing the exit register, so the run ends in timeout rather
than a false EXIT SUCCESS.

### The 7-hart production demo does not apply here, and says so

The review's step 4 asked for "end-to-end firmware on that exact config". The firmware
above *is* that: real per-hart images, built from this config's generated boot metadata.
The separate **7-hart production demo** (`tb/mosaic_soc/run_fw.sh`) is a different
config's demo and refuses this one:

```
$ MOSAIC_CFG=configs/mosaic_tapeout_ultra.yaml bash tb/mosaic_soc/run_fw.sh
production sw/firmware demo is not applicable to this topology:
  - production demo requires at least one NANO group
Generated BSP headers, per-image linkers, and boot_images.json remain valid;
provide topology-specific application images instead.
```

That demo's task-dispatch scenario is written against a TITAN + ATLAS + **NANO** topology;
the frozen part has no NANO group. The generator detects the mismatch and declines rather
than emitting an image that would not run — which is the failure-handling behaviour the
review asked about separately (§11).

Making it apply would mean re-roling the worker `atlas` → `nano`. Role drives interrupt
routing, clock-gate policy and TDU priority, so that is an RTL change, and it would
invalidate the signed-off GDS. **It is not being done for this freeze.** A topology-
specific application image for the 2-hart part is the correct follow-up, and is not
written yet.

---

## 4. The 22-pin interface

[`flow/librelane/experimental/mosaic_block_a.sv`](../flow/librelane/experimental/mosaic_block_a.sv)
wraps `core_v_mini_mcu` and terminates its other 251 ports internally.

| # | Pin | Dir | Function |
|--:|---|---|---|
| 1 | `clk_i` | in | clock |
| 2 | `rst_ni` | in | reset, active low |
| 3 | `boot_select_i` | in | boot source select |
| 4 | `execute_from_flash_i` | in | XIP enable |
| 5 | `uart_rx_i` | in | UART receive |
| 6 | `uart_tx_o` | out | UART transmit |
| 7 | `spi_flash_sck_o` | out | QSPI clock |
| 8 | `spi_flash_cs_o` | out | QSPI chip select |
| 9–12 | `spi_flash_sd_io[3:0]` | **inout** | QSPI data (true tristate, `bufz_4`) |
| 13 | `status_valid_o` | out | exit-value strobe |
| 14–20 | `status_o[6:0]` | out | exit value — **the only observability** with `debug: false` |
| 21 | `VDD` | power | 5 V |
| 22 | `VSS` | power | ground |

**This list is LVS-verified, not asserted.** Netgen compared the extracted layout against
the netlist and matched every pin, reporting *"Cell pin lists are equivalent"* and
*"Circuits match uniquely"*. See `runs/blocka_signoff/final/` and §6.

`status_o[6:0]` must be bonded. With no JTAG it is the only way to observe the part.

### Reconciling the review's pin finding

The review correctly noted that `configs/pad_cfg.py` declares ~55 signal pins and
`flow/librelane/slots/slot_mosaic.yaml` a multi-millimetre die. Both are real, both are
**chip-level artifacts, and neither is used by Block A** — an MPW block ships a macro and
inherits the shared pad ring. The frozen config references neither file for its pin
contract. Both now carry headers saying so.

---

## 5. Physical result (2026-08-01, full signoff, nothing skipped)

```bash
cd flow/librelane && ./experimental/run_signoff.sh
```

The runner refuses to start if its config contains a step substitution, so a signoff run
cannot silently become a partial one.

| | |
|---|---:|
| die | **1117.5 × 1117.5 µm = 1.2488 mm²** — exactly the Block A slot |
| utilization | 84.4% (44 355 std cells) |
| Magic DRC | **0** |
| KLayout DRC | **0** |
| Magic illegal overlap | **0** |
| Netgen LVS | **0** — *"Circuits match uniquely"*, 0 unmatched devices/nets/pins |
| KLayout↔Magic XOR | **0** |
| routing DRC | **0** |
| antenna | **0** |
| disconnected pins | **0** |
| power-grid violations | **0** (VDD, VSS) |
| worst IR drop | **120 µV** on 5 V |
| max-cap / max-fanout / max-slew | **0** / **1** / **591** (vs the library's 4.0 ns) |
| setup / hold WS | **+20.86 ns** / **+0.066 ns**, TNS 0 at all 9 corners |

**Clock: 10 MHz** (`CLOCK_PERIOD: 100`). The review advised starting below the 50 MHz on
the slide, and noted the official padring config uses 25 MHz. This run is deliberately
below both — the 20.7 ns of setup slack says the part is nowhere near its limit, and the
frequency can be raised once the electrical violations in §7 are repaired. Confirming a
target with the organizers is still open.

---

## 6. Waivers

The review asked for no inherited or blanket waivers. The complete list:

| Setting | Status | Justification |
|---|---|---|
| `ERROR_ON_SYNTH_CHECKS` | **on** (was off) | Turning it back on is what exposed bugs 28–29. No longer waived. |
| `ERROR_ON_MAGIC_DRC` | **on** | A real violation fails the flow. |
| `ERROR_ON_UNMAPPED_CELLS` | **on** | An unmapped cell has no physical master; cannot be waived. |
| `MAGIC_GDS_FLATGLOB` | inherited, **inert** | Suppresses GF180 SRAM-macro DRC false positives. This design binds **no** macro (`design__instance__count__macros = 0`), so these patterns match nothing. Kept only so a macro-backed variant does not rediscover them. Should be deleted if the macro path is abandoned. |
| `KLAYOUT_FILLER_OPTIONS: Metal2_ignore_active` | active | KLayout filler option carried from the qualified config. |
| `ERROR_ON_LINTER_WARNINGS: false` | active | 3 778 Verilator lint warnings, overwhelmingly from vendored IP (OpenTitan, pulp). Lint *errors* still fail. |
| `GRT_ALLOW_CONGESTION: true` | active | Lets global routing proceed into detailed routing, which then converged to **0** violations — so nothing was actually waived in the result. |
| `PL_RESIZER_HOLD_SLACK_MARGIN: 0.05` | active | Traded hold margin for area. Hold is positive at every corner but only **+66 ps**; re-check before raising the clock. |

No waiver is applied to DRC, LVS, XOR, antenna or the power grid. All returned zero
without one.

---

## 7. Open items — honestly

1. **591 max-slew violations**, worst 5.19 ns. Max-cap is **0** and max-fanout **1**,
   down from 27 and 411. No DRC or LVS deck examines these and setup/hold closing does not
   imply them. **This is the gap between the current macro and a tapeout-ready one.**
   Measured against the 4.0 ns limit the library declares for every cell — the original
   2 889 was largely an artifact of a blanket 3 ns / 0.2 pF constraint tighter than the
   library's own — the 0.2 pF cap limit sat below even the weakest clock buffer's
   0.2394 pF rating; the reasoning is in `config_blocka_signoff.yaml`. What remains is real and needs per-net work: two global levers were
   tried and measured to HURT — `CTS_MAX_CAP: 0.15` made cap worse (27 → 35), and upsizing
   the QSPI pads to `bufz_8` made slew worse (591 → 785, worst 5.19 → 9.51 ns), because
   those pads are input-slew limited rather than driver limited.
2. **Hold margin is +66 ps.** Positive everywhere, thin.
3. **`bufz_4` drive strength on the QSPI pads is provisional**, pending the integrator's
   pad loading.
4. **This flow bypasses the `PHYSICAL_BUNDLE` attestation gate.** A clean result here is
   evidence about the layout, not a qualified tapeout input.
5. **Clock target unconfirmed with the organizers.**
6. ~~Data loads from the flash XIP window never complete~~ **FIXED** (bug 31).
   SERV's ext Wishbone port was tied off, so any data access at or above `0x4000_0000`
   stalled the hart. `serv_sci.sv` now arbitrates both of servile's Wishbone ports onto
   its OBI master. **This changed RTL that is inside the hardened design**, so the
   signed-off GDS in §5 predates the fix and must be re-hardened before it is submitted.
7. **Timing-annotated GLS is unavailable with open tools** (§10). Functional GLS on the
   routed netlist passes; SDF back-annotation is blocked by a non-standard construct in
   the PDK models plus a CVC crash at this design's scale. Timing rests on STA.
8. **4 081 of 5 587 flops have no reset** (§10). Not a defect on its own -- datapath flops
   are written before use -- but it is why gate-level simulation needs an explicit
   power-up model, and it deserves a deliberate look before tapeout.
8. ~~Absolute paths in the LibreLane configs~~ **FIXED** -- resolved at run time by
   `flow/librelane/scripts/gen_filelist.py`; the configs are machine-independent and a
   test keeps them that way.

---

## 8. The generator's own target validation now describes this part

The review's request 2 was to *reconcile the die configuration with the generator's own
target validation*. It did not reconcile: `core_registry.TAPEOUT_*` encoded the **7-hart
PoC** (1× cv32e20 + 2× FazyRV + 4× SERV, 32 KB SRAM, uart/gpio/timer/spi) as the qualified
physical matrix. The part being taped out would have been **rejected** by that gate, which
is precisely why the frozen config said `target: simulation`. The reviewer's phrasing —
"the deck and the generator's target validation describe different chips" — was exact.

Changed:

- `TAPEOUT_CORE_MATRIX` is now the Block A topology; `TAPEOUT_SRAM_KB = 0`,
  `TAPEOUT_BOOT_ROM_KB = 1`, `TAPEOUT_SCRATCHPAD_BYTES = 128`,
  `TAPEOUT_PERIPHERALS = {uart}`.
- New `TAPEOUT_PLATFORM`: the gate now also checks the eight selectable blocks
  (`dma: none`, `debug: false`, `plic: false`, `spi_mode: xip_only`, …). A design is
  defined as much by what it removes as by its core list, and a config that re-enables the
  debug module has no physical evidence behind it. An **omitted** knob is judged on its
  effective default, so silence does not pass.
- `configs/mosaic_tapeout_ultra.yaml` declares **`target: tapeout`**. That is now a
  checkable claim rather than an aspiration.
- `mosaic.yaml` (the 7-hart PoC) claimed `target: tapeout` while being far larger than the
  22-pin budget. It is now `simulation`.
- The `poc` config-author preset no longer emits `target: tapeout`; a new **`blocka`**
  preset does, and a test validates it against the gate.

**The attestation chain had a matching hole.** The build manifest recorded no platform
knobs at all, so `PHYSICAL_BUNDLE` preflight could not tell a Block A build from one
carrying a debug module and a DMA. `build_manifest.py` now records `resolved.platform` and
`declared_scratchpad_bytes`; `preflight.py` carries them into the check and **rejects a
manifest that predates the field** rather than passing on defaults.

Verified rejections (each an updated test case): debug re-enabled, DMA re-added, SPI host
restored, a knob omitted entirely, 32 KB SRAM, the old 7-hart core list, an extra
peripheral, a different scratchpad size. 648 pytests pass.

---

## 9. Physical-phase items the review flagged for later

| Item | Status |
|---|---|
| Gate count / cell area / liberty corner | **44 355** standard cells, 84.4% utilization, characterised at 9 corners from `gf180mcu_fd_sc_mcu7t5v0__{tt_025C_5v00, ss_125C_4v50, ff_n40C_5v50}` (min/nom/max RC each) |
| The flatten/slang path | There is **no flatten step** for Block A. Yosys reads SystemVerilog directly through the `slang` plugin (`USE_SLANG: true`); sv2v is not used and is broken in this environment. The "flattened RTL" input belongs to the chip-level `PHYSICAL_BUNDLE` path, not this one |
| Post-synthesis gate-level simulation | **Done, functionally.** `tb/gls/run_gls.sh` simulates the POST-PLACE-AND-ROUTE netlist with the PDK cell models, booting XIP from a behavioural QSPI flash through only the 22 bonded pins: **EXIT SUCCESS in 12 399 cycles vs the RTL's ~12 400**. **Timing-annotated GLS is not achievable with open tools** — see §10 |
| Chip wrapper `flow/librelane/src/mosaic_soc_core.sv` | **Still a template.** Line 68 is `// TODO(authoring step): instantiate x_heep_system and bind pads to pins`. It is chip-level only — Block A ships a macro and does not use it. The hierarchy slide was misleading; this is the correction |
| Closing package (your Q6) | `runs/blocka_signoff/final/` — `gds/`, `lef/`, `nl/` + `pnl/` (netlists), `lib/` (9 corners), `sdc/`, `odb/`, `spice/` (the extracted netlist LVS compared against), `metrics.json`. STA is in the run's `*-stapostpnr` reports; DRC/LVS/antenna reports listed by `run_signoff.sh` |

On pads: the Integration doc's note that 5 V pads run at 3.3 V costs speed applies to the
**shared ring**, which this block does not contain. Our only pad-adjacent choice is the
`bufz_4` drive strength on the four QSPI data pins, which is provisional pending the
integrator's loading.

---

## 10. Gate-level simulation, and why the timing-annotated half is blocked

`tb/gls/run_gls.sh` runs the **post-place-and-route** netlist -- the gates in the
GDS -- against the PDK's own cell models, driven only through the 22 pins the
integrator bonds. No backdoor memory load, no hierarchical forces, no internal
probes.

```
[GLS] status_valid_o asserted at 1239950000 after 12399 cycles, status_o = 0x00
### RESULT: EXIT SUCCESS - gate-level netlist booted and reported 0
```

Cycle-for-cycle agreement with RTL is the point: synthesis, CTS and P&R
preserved the behaviour. This is the complementary check to bugs 28 and 31,
which were RTL that simulated happily while being wrong.

**Two findings came out of building it.**

**4 081 of the design's 5 587 flops have no reset** (plain `dffq_1`). At time
zero they are X, and X-propagation stalled the netlist for 126 000 cycles with
the QSPI pins stuck at `x`. Verilator hides this by zero-initialising, so no RTL
run ever showed it. Silicon powers up to a definite 0 or 1, so power-up is
modelled explicitly -- `$deposit` per flop under Icarus, `+random_2state=<seed>`
under CVC. The reset coverage is worth a look in its own right.

**The PDK cell models are not standard-compliant.** They use `ifnone` on
edge-sensitive specify paths:

```verilog
ifnone
 (posedge A1 => (ZN:A1)) = (1.0,1.0);
```

IEEE 1364-2005 SS14.2.6 allows `ifnone` only as the default for *state-dependent
simple* paths. Two independent simulators reject it, both correctly:

| iverilog | `sorry: ifnone with an edge-sensitive path is not supported` |
|---|---|
| CVC | `ERROR [1012] ifnone path illegal - has edge or is state dependent` |

There are 120 such paths. Under Icarus the models must therefore be compiled
`-DFUNCTIONAL`, which strips the specify blocks -- and with them exactly the
paths SDF would annotate. `run_gls.sh --sdf` **refuses** rather than running
zero-delay and labelling it timing-annotated.

CVC (OSS CVC 7.00b, IEEE 1364-2005) does compile specify blocks and supports
SDF, and `tb/gls/mk_cells_cvc.py` patches the illegal keyword out so the paths
survive as annotation targets. It gets as far as compiling and then
**segfaults** on the 45 022-instance netlist -- peak RSS 210 MB against 7.3 GB
free, so a simulator bug at scale rather than resource exhaustion. The same
patched library builds and runs a small design in 0.1 s.

**Timing coverage therefore rests on STA at nine corners**, which is where it
normally rests anyway. Closing this needs a commercial simulator or a newer CVC;
it is recorded as open rather than worked around.

---

## 11. Environment

Measured on the machine that produced the results above.

| Tool | Version |
|---|---|
| LibreLane | 3.0.0 |
| Yosys | 0.62 (`7326bb7d`) + `slang` plugin |
| OpenROAD | `dcf36133a369abc8f3c5e5738cd4d82e4903c0e0` |
| Magic | 8.3.623 |
| Netgen | 1.5.316 |
| KLayout | 0.30.7 |
| PDK | `gf180mcuD` via open_pdks `40cee970d8a9b7eaea35a34fe7d6068f05721f0a` |
| Verilator | **5.050** (pinned — the oss-cad-suite nightly's DFG pass miscompiles cv32e40x; see bug 21) |
| RISC-V GCC | 16.1.0, `riscv32-unknown-elf` |
| Python | 3.14.6 |
| FuseSoC | `0.2.dev3+gc36dffc85` (x-heep `ot` fork) |
| Nix | 2.32.2 |
| Git LFS | 3.7.1 |

EDA tools come from the pinned flake in `flow/librelane/`; `nix develop` reproduces them.

---

## 12. Harness reliability

The review asked for failure handling rather than LLM sophistication. Each is a command:

**Schema gate rejects an invalid config** — exit 1, structured, names the field:

```bash
$ ./oh-my-soc config-author validate bad.yaml ; echo "exit: $?"
[FAIL] bad.yaml has 1 validation error(s)
  ERROR: cores[0].ip 'nosuchcore' not in ['boom', 'cv32e20', ..., 'serv', 'snitch']
exit: 1
$ ./oh-my-soc config-author validate configs/mosaic_tapeout_ultra.yaml ; echo "exit: $?"
exit: 0
```

**A non-zero tool exit surfaces as a structured failure, not a false pass:**

```bash
$ ./oh-my-soc --json flow-runner run mosaic-gen-config --config bad.yaml ; echo "exit: $?"
{"ok": false, "skill": "flow-runner",
 "summary": "Flow 'mosaic-gen-config' FAIL (79.6s, exit=2)",
 "details": {"exit_code": 2, "elapsed_s": 79.57, "stdout_tail": "..."}}
exit: 1
```

**Paths containing spaces** — config path, output root and manifest path all with spaces:

```bash
$ python util/xheep_gen/mcu_gen.py --mosaic_config "dir with space/frozen cfg.yaml" \
    --output-root "out with space" ...
exit: 0   # 23 .sv files generated
$ ./oh-my-soc config-author validate "dir with space/frozen cfg.yaml"   # exit 0
$ ./oh-my-soc topo-viz check      "dir with space/frozen cfg.yaml"      # exit 0
```

Scope note: these exercise space-containing *config and output* paths. The repository has
not been relocated to a space-containing root and cloned-fresh; that remains untested.

---

## 13. Reproducing

```bash
make mosaic-gen MOSAIC_CFG=configs/mosaic_tapeout_ultra.yaml      # RTL
MOSAIC_CFG=configs/mosaic_tapeout_ultra.yaml bash tb/mosaic_soc/run_generic.sh
cd flow/librelane && ./experimental/run_signoff.sh                 # hours
```

Nothing above depends on paths from the machine that built it. The LibreLane configs used
to carry ~526 absolute paths into a content-addressed FuseSoC build directory, which meant
the committed signoff could not be reproduced anywhere else, and which had a worse failure
mode than a missing file: a path that still *resolved*, to an older bundle, would harden
stale RTL and report clean results for the wrong design.

`flow/librelane/scripts/gen_filelist.py` now resolves the source list from the manifest at
run time -- the same approach `tb/mosaic_soc/gen_filelist.py` has always used for the
simulation flow -- and `run_signoff.sh` merges it into the config it hands to LibreLane.
The checked-in configs contain no absolute paths at all, and a test fails the build if any
reappear. Verified equivalent: the generated list reproduces the previous 507 files
exactly, and a flow run from the composed config synthesises to the same 854 954 µm² /
33 852 cells as the signed-off run.

If the RTL has not been generated yet, the runner stops and says so rather than reaching
for whatever bundle happens to be on disk.
