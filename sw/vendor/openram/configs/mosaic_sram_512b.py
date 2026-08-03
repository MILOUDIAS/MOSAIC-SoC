# Copyright 2026 MOSAIC-SoC Contributors
# Solderpad Hardware License, Version 2.1, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0 WITH SHL-2.1

"""
mosaic_sram_512b.py — OpenRAM config for a MOSAIC-SoC 512-BYTE SRAM.

512 B byte-wide SRAM: 512 words × 8 bits = 4096 bits.
Capacity-matched to gf180mcu_fd_ip_sram__sram512x8m8wm1, whose name likewise
counts WORDS (512 x 8 bits), not bytes.

Renamed from mosaic_sram_4k.py: 512 words x 8 bits is 512 bytes, not 4 KiB.
The old name conflated bits with bytes (roadmap 14.1).

Usage:
  export OPENRAM_TECH=sw/vendor/openram
  python3 $OPENRAM_TECH/../sram_compiler.py sw/vendor/openram/configs/mosaic_sram_512b.py

Output: GDS, LEF, LIB, SPICE, Verilog for the 512 B SRAM macro.
"""

word_size = 8        # 8-bit words (byte-wide, matching PDK macros)
num_words = 512      # 512 words x 8 bits = 4096 bits = 512 BYTES
write_size = 8       # Byte-granularity write mask (WEN[7:0])
num_banks = 1        # Single bank
words_per_row = 1    # No column mux (1 word per row) — simple, low latency
num_spare_rows = 2   # 2 spare rows for yield improvement
num_spare_cols = 0   # No spare columns

# ── Computed geometry ───────────────────────────────────────────────
# num_cols = words_per_row × word_size = 1 × 8 = 8 columns
# num_rows = num_words / words_per_row + spare = 512 + 2 = 514 rows
# Bitcell array: 8 cols × 514 rows = 4,112 cells
# Estimated area: ~514 × 2.22um × 8 × 1.24um ≈ 11,400 um² ≈ 0.011 mm²
# (periphery adds ~3-5x → ~0.04-0.06 mm² total)
