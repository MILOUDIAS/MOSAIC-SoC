# atlas.S — ATLAS worker (fazyrv, hart 1) firmware for the wake-and-run demo.
# Linked at 0x1000 (= the core's BOOTADR / reset PC). Boots dormant; runs only once
# TITAN wakes it via the TDU. Writes its sentinel (0xA71A5000) to 0x3004, then spins.
# Base RV32I only (fazyrv RVC=NONE, no M). No stack (li/sw/j only).
    .section .atlas,"ax"
    .global _atlas_start
_atlas_start:
    li   t0, 0xA71A5000               # ATLAS sentinel
    li   t1, 0x00003004               # ATLAS sentinel address
    sw   t0, 0(t1)
1:  j    1b
