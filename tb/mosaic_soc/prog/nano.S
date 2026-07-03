# nano.S — NANO worker (serv, hart 2) firmware for the wake-and-run demo.
# Linked at 0x2000 (= the core's RESET_PC). Boots dormant; runs only once TITAN
# wakes it via the TDU. Writes its sentinel (0x4E414E00) to 0x3008, then spins.
# Base RV32I only (serv COMPRESSED=0, no M). No stack (li/sw/j only).
    .section .nano,"ax"
    .global _nano_start
_nano_start:
    li   t0, 0x4E414E00               # NANO sentinel ("NANE")
    li   t1, 0x00003008               # NANO sentinel address
    sw   t0, 0(t1)
1:  j    1b
