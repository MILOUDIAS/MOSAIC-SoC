// Copyright 2026 MOSAIC-SoC Contributors
// Solderpad Hardware License, Version 2.1, see LICENSE.md for details.
// SPDX-License-Identifier: Apache-2.0 WITH SHL-2.1

// start.S — TITAN startup code for MOSAIC-SoC firmware.
//
// Placed at 0x180 (boot ROM jumps here). Initializes the stack pointer
// and jumps to main(). This is the true entry point for the TITAN core.

    .section .text.start, "ax", @progbits
    .global _start
    .type _start, @function

_start:
    // Initialize stack pointer (top of SRAM)
    la      sp, _sp

    // Jump to main()
    jal     ra, main

    // Should never return; spin if it does
1:  wfi
    j       1b

    .size _start, .-_start
