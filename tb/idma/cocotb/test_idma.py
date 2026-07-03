"""cocotb per-block test for the MOSAIC iDMA (idma_xheep_wrapper).

Programs a memory-to-memory copy through the iDMA register frontend and checks
the data actually moved, exercising the full datapath:
    reg frontend → ND midend → rw_obi backend → pulp-OBI⇄x-heep-OBI → memory.

Register map (idma_reg32_3d): CONF=0x00, NEXT_ID=0x44 (read launches),
DST_ADDR=0xd0, SRC_ADDR=0xd8, LENGTH=0xe0, REPS_2=0xf8.
CONF.src_protocol=[14:12], CONF.dst_protocol=[17:15]; OBI=1 → CONF=0x9000.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles

CONF = 0x00
NEXT_ID = 0x44
DST_ADDR = 0xD0
SRC_ADDR = 0xD8
LENGTH = 0xE0
REPS_2 = 0xF8
CONF_OBI = (1 << 12) | (1 << 15)  # src=OBI, dst=OBI


async def reg_write(dut, addr, data):
    dut.reg_addr_i.value = addr
    dut.reg_wdata_i.value = data
    dut.reg_write_i.value = 1
    dut.reg_valid_i.value = 1
    await RisingEdge(dut.clk_i)
    for _ in range(64):
        if int(dut.reg_ready_o.value) == 1:
            break
        await RisingEdge(dut.clk_i)
    dut.reg_valid_i.value = 0
    dut.reg_write_i.value = 0
    await RisingEdge(dut.clk_i)


async def reg_read(dut, addr):
    dut.reg_addr_i.value = addr
    dut.reg_write_i.value = 0
    dut.reg_valid_i.value = 1
    await RisingEdge(dut.clk_i)
    val = 0
    for _ in range(64):
        if int(dut.reg_ready_o.value) == 1:
            val = int(dut.reg_rdata_o.value)
            break
        await RisingEdge(dut.clk_i)
    dut.reg_valid_i.value = 0
    await RisingEdge(dut.clk_i)
    return val


@cocotb.test()
async def idma_mem_to_mem_copy(dut):
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    dut.reg_valid_i.value = 0
    dut.reg_write_i.value = 0
    dut.reg_addr_i.value = 0
    dut.reg_wdata_i.value = 0
    dut.rst_ni.value = 0
    await ClockCycles(dut.clk_i, 10)
    dut.rst_ni.value = 1
    await ClockCycles(dut.clk_i, 5)

    SRC, DST, NBYTES = 0x100, 0x800, 16
    src_w, dst_w, nwords = SRC >> 2, DST >> 2, NBYTES >> 2
    pattern = [0x1111_1111, 0x2222_2222, 0x3333_3333, 0x4444_4444]

    # Preload source, clear destination (hierarchical memory access).
    for i in range(nwords):
        dut.i_mem.mem[src_w + i].value = pattern[i]
        dut.i_mem.mem[dst_w + i].value = 0
    await ClockCycles(dut.clk_i, 2)

    # Program the descriptor + launch.
    await reg_write(dut, CONF, CONF_OBI)
    await reg_write(dut, DST_ADDR, DST)
    await reg_write(dut, SRC_ADDR, SRC)
    await reg_write(dut, LENGTH, NBYTES)
    await reg_write(dut, REPS_2, 1)
    await reg_read(dut, NEXT_ID)  # read NEXT_ID launches the transfer

    # Let the transfer run.
    done = False
    for _ in range(2000):
        await RisingEdge(dut.clk_i)
        if int(dut.dma_done_o.value) == 1:
            done = True
    await ClockCycles(dut.clk_i, 20)

    # Check the data moved.
    dut._log.info("=== iDMA mem-to-mem copy ===")
    errs = 0
    for i in range(nwords):
        got = int(dut.i_mem.mem[dst_w + i].value)
        exp = pattern[i]
        dut._log.info(f"dst[{i}] = 0x{got:08x}  (expected 0x{exp:08x})")
        if got != exp:
            errs += 1
    dut._log.info(f"done_seen={done}  mismatches={errs}")
    assert errs == 0, f"iDMA copy FAILED: {errs}/{nwords} words wrong"
    dut._log.info("iDMA per-block test: PASS — data copied src→dst")
