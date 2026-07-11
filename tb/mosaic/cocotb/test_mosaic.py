"""cocotb test for the MOSAIC multi-core cpu_subsystem + TDU wake loop.

Drives the generated multi-core SoC (serv + qerv + fazyrv via their SCI wrappers)
through cocotb_top.sv. All three sim cores are *workers* (no TITAN), so they boot
dormant and only run once woken — exactly the TDU.core_wake_o → cpu_subsystem
fetch-enable path this test exercises end-to-end:

  1. Reset, then run a while WITHOUT waking → every worker must stay dormant
     (no bus traffic, core_sleep_o asserted, sentinel never written).
  2. Wake hart 0 ONLY → only hart 0 comes alive and retires its program; the
     other two stay parked. Proves the wake is per-hart, not global.
  3. Wake the remaining harts → all three retire (write 0x55 to 0x40).

This closes the loop the TDU SoC test flagged as open: the wake signal now
actually releases the cores.

Run via tb/mosaic/cocotb/run.sh (generates the RTL first), or:
    make -C tb/mosaic/cocotb SIM=verilator
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

SENTINEL = 0x55
# (label, sentinel signal, alive signal, sleep signal, wake bit)
CORES = [
    ("serv  (W=1)", "sentinel0", "alive0", "sleep0", 0),
    ("qerv  (W=4)", "sentinel1", "alive1", "sleep1", 1),
    ("fazyrv     ", "sentinel2", "alive2", "sleep2", 2),
]


def _sent(dut, sig):
    return int(getattr(dut, sig).value)


async def _run_until_executed(dut, bits, max_chunks=30, chunk=2000):
    """Run, polling until every hart whose wake bit is set has written 0x55."""
    targets = [c for c in CORES if (bits >> c[4]) & 1]
    for _ in range(max_chunks):
        await ClockCycles(dut.clk_i, chunk)
        if all(_sent(dut, c[1]) == SENTINEL for c in targets):
            break


@cocotb.test()
async def multicore_wake_loop(dut):
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())

    # ── Reset, wake held low: every worker must stay parked ────────────────
    dut.core_wake.value = 0b000
    dut.rst_ni.value = 0
    await ClockCycles(dut.clk_i, 20)
    dut.rst_ni.value = 1

    # Give them ample time to misbehave if gating were broken.
    await ClockCycles(dut.clk_i, 4000)

    dut._log.info("=== Phase 1: dormant out of reset (no wake) ===")
    failures = 0
    for name, sent_sig, alive_sig, sleep_sig, _ in CORES:
        alive = int(getattr(dut, alive_sig).value)
        slp = int(getattr(dut, sleep_sig).value)
        sval = _sent(dut, sent_sig)
        ok = alive == 0 and slp == 1 and sval != SENTINEL
        dut._log.info(
            f"hart {name}: alive={alive} sleep={slp} sentinel=0x{sval:08x} "
            f"{'PASS (parked)' if ok else 'FAIL (ran without wake!)'}"
        )
        if not ok:
            failures += 1
    assert failures == 0, "a worker executed before being woken — gating is broken"

    # ── Phase 2: wake hart 0 only ──────────────────────────────────────────
    dut._log.info("=== Phase 2: wake hart 0 only (selective) ===")
    # A one-cycle pulse is enough — cpu_subsystem latches it.
    dut.core_wake.value = 0b001
    await ClockCycles(dut.clk_i, 2)
    dut.core_wake.value = 0b000
    await _run_until_executed(dut, 0b001)

    h0 = CORES[0]
    assert int(getattr(dut, h0[2]).value) == 1, "hart 0 did not wake"
    assert _sent(dut, h0[1]) == SENTINEL, "hart 0 woke but did not execute"
    assert int(getattr(dut, h0[3]).value) == 0, "hart 0 still reports sleep"
    # The other two must still be parked.
    for name, sent_sig, alive_sig, sleep_sig, _ in CORES[1:]:
        assert int(getattr(dut, alive_sig).value) == 0, f"{name} woke unexpectedly"
        assert _sent(dut, sent_sig) != SENTINEL, f"{name} executed unexpectedly"
        assert int(getattr(dut, sleep_sig).value) == 1, f"{name} not parked"
    dut._log.info("hart 0 ran; harts 1,2 still parked — per-hart wake confirmed")

    # ── Phase 3: wake the rest ─────────────────────────────────────────────
    dut._log.info("=== Phase 3: wake remaining harts ===")
    dut.core_wake.value = 0b110
    await ClockCycles(dut.clk_i, 2)
    dut.core_wake.value = 0b000
    await _run_until_executed(dut, 0b110)

    dut._log.info("=== Final state ===")
    failures = 0
    for name, sent_sig, alive_sig, sleep_sig, _ in CORES:
        alive = int(getattr(dut, alive_sig).value)
        slp = int(getattr(dut, sleep_sig).value)
        sval = _sent(dut, sent_sig)
        ok = alive == 1 and slp == 0 and sval == SENTINEL
        dut._log.info(
            f"hart {name}: alive={alive} sleep={slp} sentinel=0x{sval:08x} "
            f"{'PASS' if ok else 'FAIL'}"
        )
        if not ok:
            failures += 1

    assert failures == 0, f"{failures} core(s) failed after wake (see log above)"
    dut._log.info("ALL WORKERS: dormant→woken→executed — TDU wake loop closed")
