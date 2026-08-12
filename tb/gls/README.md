# Gate-level simulation — Chipathon Block A

Simulates the **post-place-and-route netlist** — the gates that are in the GDS —
with the PDK's own cell models, booting XIP from a behavioural QSPI flash and
reporting only through the **22 pins the MPW integrator bonds**. No backdoor
memory load, no hierarchical forces, no internal probes: if this passes, the
part can be brought up on a board the same way.

It is the complementary check to bugs 28 and 31, which were RTL that elaborated
and simulated happily while being wrong. This catches the opposite failure —
RTL correct, implementation broken.

## Status

| | |
|---|---|
| **Functional GLS (Icarus)** | ✅ **passes** — boots in 12 399 cycles vs the RTL's ~12 400 |
| **Timing-annotated GLS (CVC)** | ❌ blocked by a CVC crash — see below |

```bash
./run_gls.sh                      # functional GLS on the routed netlist
GLS_NETLIST=<nl.v> ./run_gls.sh   # post-synthesis netlist instead
```

```
[GLS] reset released at 1950000
[GLS] status_valid_o asserted at 1239950000 after 12399 cycles, status_o = 0x00
### RESULT: EXIT SUCCESS — gate-level netlist booted and reported 0
```

Cycle-for-cycle agreement with RTL is the result that matters: synthesis, CTS
and place-and-route preserved the behaviour.

## Why there are two flows

**Icarus cannot do timing annotation on this PDK.** The GF180 cell models use
`ifnone` on edge-sensitive specify paths, which iverilog rejects:

```
sorry: ifnone with an edge-sensitive path is not supported
```

so they must be compiled `-DFUNCTIONAL`, which strips the specify blocks — and
with them the very paths SDF would annotate. `run_gls.sh --sdf` therefore
**refuses** rather than running zero-delay and calling it timing-annotated.

**CVC** (OSS CVC 7.00b, IEEE 1364-2005) does compile specify blocks, has SDF
annotation and `+min/typ/maxdelays`, and offers `+random_2state=<seed>` — a
better power-up model than Icarus allows. `run_gls_cvc.sh` is complete and
correct as far as it goes, but CVC **segfaults** compiling the 45 022-instance
netlist against the full specify library (peak RSS 210 MB of 7.3 GB available,
so a bug at scale, not memory). The same patched library compiles and simulates
a small design in 0.1 s.

Timing coverage is therefore STA's, at nine corners. Closing this gap needs a
commercial simulator or a newer CVC.

## The PDK defect

The models are **not standard-compliant**:

```verilog
ifnone
 (posedge A1 => (ZN:A1)) = (1.0,1.0);
```

IEEE 1364-2005 §14.2.6 permits `ifnone` only as the default for *state-dependent
simple* paths, never edge-sensitive ones. Two independent simulators reject it
and both are right:

| | |
|---|---|
| iverilog | `sorry: ifnone with an edge-sensitive path is not supported` |
| CVC | `ERROR [1012] ifnone path illegal - has edge or is state dependent` |

`mk_cells_cvc.py` removes the 120 illegal keywords and keeps the paths (225
legal state-dependent blocks are untouched), so they survive as SDF annotation
targets instead of losing their delays. Worth reporting upstream.

## Power-up

**4 081 of the design's 5 587 flops are plain `dffq_1` with no reset.** At time
zero they are X, and X-propagation stalls the netlist — the first attempt sat at
126 000 cycles with the QSPI pins stuck at `x`. Verilator hides this by
zero-initialising, which is why no RTL run ever showed it.

Real silicon powers up to a definite 0 or 1, so:

- **Icarus:** `gen_powerup_init.py` emits a `$deposit` per flop. The deposit
  holds only until each flop's first clock edge.
- **CVC:** `+random_2state=<seed>` — random 0/1 for all state, and a different
  seed is a different power-up state. Stronger, and worth sweeping on a design
  with this much unreset state.

## Files

| | |
|---|---|
| `gls_tb.sv` | Icarus testbench (SystemVerilog) |
| `run_gls.sh` | functional GLS runner |
| `gls_tb_cvc.v` | CVC testbench (Verilog-2001 — CVC is not a SystemVerilog simulator) |
| `run_gls_cvc.sh` | timing-annotated runner (blocked on the CVC crash) |
| `gen_powerup_init.py` | → `gls_powerup_init.svh` (generated, gitignored) |
| `mk_cells_cvc.py` | → `gf180mcu_cells_cvc.v`, standards-compliant cell copy (generated, gitignored) |
| `mk_spiflash_v2001.py` | → `spiflash_v2001.v`, Verilog-2001 flash model |

Generated artifacts are reproducible from the scripts and are not committed; run
the generators after a re-harden, since the flop list comes from the netlist.

Note that `final/sdf/` is gitignored (185 MB across nine corners), so the CVC
flow needs a local signoff run present — not just the committed deliverable.
