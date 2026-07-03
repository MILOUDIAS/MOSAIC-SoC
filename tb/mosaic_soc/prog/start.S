# start.S — TITAN (cv32e20, hart 0) firmware for the MOSAIC full-SoC wake-and-run demo.
#
# Linked at 0x180 (= soc_ctrl.boot_address; the boot ROM jumps here). TITAN:
#   1. writes its own sentinel (0xC0FFEE00) to 0x3000,
#   2. wakes the worker cores via the TDU — a single store of 0x6 (=(1<<1)|(1<<2))
#      to WAKE_REQ at TDU_START_ADDRESS+0x0C = 0x200A000C pulses core_wake_o[1] and
#      core_wake_o[2], releasing ATLAS (fazyrv, hart 1) and NANO (serv, hart 2) from
#      their dormant reset; cpu_subsystem latches the pulse into fetch_enable,
#   3. polls until BOTH workers have written their sentinels (0x3004, 0x3008),
#   4. signals soc_ctrl EXIT_VALUE=0 / EXIT_VALID=1 -> the testbench prints EXIT SUCCESS.
#
# Bare-metal, no libc (the toolchain has no rv32imc multilib). Uses only x2/x5/x6/x7
# so it is RV32E-safe (TITAN's ISA is rv32emc). The poll loop makes the run
# deterministic regardless of serv's bit-serial slowness.

    .equ TITAN_SENT,   0xC0FFEE00      # TITAN's sentinel value
    .equ SENT_BASE,    0x00003000      # sentinel block: TITAN@0, ATLAS@4, NANO@8
    .equ TDU_WAKE_REQ, 0x200A000C      # TDU_START_ADDRESS(0x200A0000) + WAKE_REQ(0x0C)
    .equ WAKE_WORKERS, 0x6             # (1<<1)|(1<<2): wake hart1 (ATLAS) + hart2 (NANO)
    .equ SOC_CTRL,     0x20000000      # soc_ctrl base (EXIT_VALID@0x00, EXIT_VALUE@0x04)

    .section .text.init,"ax"
    .global _start
_start:
    li   sp, 0x00007FF0                # stack near top of RAM0

    # 1. TITAN sentinel
    li   t0, TITAN_SENT
    li   t1, SENT_BASE
    sw   t0, 0(t1)                     # mem[0x3000] = 0xC0FFEE00

    # 2. wake the workers via the TDU (single write to WAKE_REQ)
    li   t0, TDU_WAKE_REQ
    li   t2, WAKE_WORKERS
    sw   t2, 0(t0)                     # mem[0x200A000C] = 0x6  -> core_wake[1],[2]

    # 3. wait for both worker sentinels (they boot dormant, run when woken)
1:  lw   t2, 4(t1)                     # ATLAS sentinel @ 0x3004
    beqz t2, 1b
2:  lw   t2, 8(t1)                     # NANO sentinel  @ 0x3008
    beqz t2, 2b

    # 4. signal success
    li   t0, SOC_CTRL
    li   t1, 0
    sw   t1, 0x04(t0)                  # EXIT_VALUE = 0
    li   t1, 1
    sw   t1, 0x00(t0)                  # EXIT_VALID = 1  -> "EXIT SUCCESS"

3:  j    3b                           # spin
