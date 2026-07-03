# iDMA functional tests (cocotb + Verilator)

Verifies that MOSAIC's iDMA (`hw/vendor/mosaic/idma/idma_xheep_wrapper.sv`) — the
drop-in replacement for x-heep's simple DMA in multi-core mode — actually moves
data, at two integration levels.

The iDMA datapath under test:
`reg frontend (idma_reg32_3d) → ND midend → rw_obi backend → pulp-OBI⇄x-heep-OBI`.

## Run

```bash
tb/idma/cocotb/run.sh          # runs BOTH levels
# or individually:
make -C tb/idma/cocotb SIM=verilator TOPLEVEL=idma_tb_top        # per-block
make -C tb/idma/cocotb SIM=verilator TOPLEVEL=idma_soc_tb_top    # SoC-level
```

Needs cocotb + Verilator only (no RTL generation, no RISC-V GCC — the iDMA is
static vendored RTL and the test drives the register frontend directly).

## What each level does

The cocotb test (`cocotb/test_idma.py`) programs a memory-to-memory copy through
the iDMA register map and checks the bytes arrived:

```
CONF (0x00)     = 0x9000      # src_protocol=OBI, dst_protocol=OBI
DST_ADDR (0xd0) = <dst>
SRC_ADDR (0xd8) = <src>
LENGTH (0xe0)   = <bytes>
REPS_2 (0xf8)   = 1           # 1D transfer
read NEXT_ID (0x44)           # launches the transfer
```

| Level | Top | Memory | What it adds |
|-------|-----|--------|--------------|
| **per-block** | `idma_tb_top` | `tb_idma_mem` (dual-port) | iDMA read + write masters to a 2-port memory |
| **SoC-level** | `idma_soc_tb_top` | `tb_idma_xbar_mem` (1 port, arbitrated) | read/write **contend** for one memory (write priority) — models the SoC crossbar serialising the iDMA's two masters onto the shared SRAM |

Both currently **PASS** (copy the 4-word pattern src→dst, `TESTS=1 PASS=1`).

## Background: the iDMA bugs this fixed

The vendored iDMA was non-buildable; bringing it up required:
1. **Wrapper rewrite** — `idma_xheep_wrapper.sv` was written against a different
   iDMA version (wrong `IDMA_TYPEDEF_*` arity, wrong submodule param/pin names).
   It was rewritten against the **latest iDMA 0.6.5** modules: build the 1D/ND
   request types + OBI meta channels, instantiate `idma_reg32_3d` + `id_gen` +
   `idma_nd_midend` + `idma_backend_rw_obi`, and convert the backend's
   pulp-platform OBI masters to x-heep's simpler `obi_pkg` bus.
2. **Vendored the OBI package** — `hw/vendor/pulp_platform/obi` (v0.1.2), for the
   `OBI_TYPEDEF_*` macros the backend needs. Added `obi.core`.
3. **Fixed `idma.core`** — it never declared the `idma/typedef.svh` include dir
   (so the build couldn't find it) and listed `*_synth` wrappers that pull an
   un-vendored AXI backend. Now lists the exact rw_obi closure + the obi dep.

## Files

```
cocotb/test_idma.py    cocotb test (program copy, check data)
cocotb/Makefile        cocotb+Verilator build (TOPLEVEL selects the level)
cocotb/run.sh          runs both levels
idma_tb_top.sv         per-block top (iDMA + dual-port memory)
idma_soc_tb_top.sv     SoC-level top (iDMA + shared arbitrated memory)
tb_idma_mem.sv         dual-port OBI memory
tb_idma_xbar_mem.sv    shared single-port OBI memory with 2→1 arbitration
```
