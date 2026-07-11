# Copyright 2026 MOSAIC-SoC Contributors
# Solderpad Hardware License, Version 2.1, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0 WITH SHL-2.1

"""
mosaic_sram_32k.py — OpenRAM config for MOSAIC-SoC 32KB SRAM.

32KB SRAM: 4096 words × 8 bits.
Large memory — requires careful floorplanning and multi-bank design.

Usage:
  export OPENRAM_TECH=sw/vendor/openram
  python3 $OPENRAM_TECH/../sram_compiler.py sw/vendor/openram/configs/mosaic_sram_32k.py

Output: GDS, LEF, LIB, SPICE, Verilog for the 32KB SRAM macro.

CAUTION: At 180nm, this macro will be ~0.5-1.0 mm². Verify it fits
the MOSAIC-SoC die area budget before taping out.
"""

word_size = 8        # 8-bit words (byte-wide)
num_words = 4096     # 4096 words → 4096 × 8 = 32,768 bits = 32KB
write_size = 8       # Byte-granularity write mask
num_banks = 2        # 2 banks for reduced row depth (2048 rows/bank)
words_per_row = 4    # Column mux = 4 → reduces row count by 4x
num_spare_rows = 4   # 4 spare rows for yield (larger macro = more defects)
num_spare_cols = 2   # 2 spare columns

# ── Computed geometry ───────────────────────────────────────────────
# Per bank:
#   num_cols = words_per_row × word_size = 4 × 8 = 32 columns
#   num_rows = num_words / (num_banks × words_per_row) + spare
#            = 4096 / (2 × 4) + 4 = 516 rows
#   Bitcell array per bank: 32 cols × 516 rows = 16,512 cells
#   Total: 2 banks × 16,512 = 33,024 cells
#
# Estimated area:
#   Per bank: 516 × 2.22um × 32 × 1.24um ≈ 45,600 um² ≈ 0.046 mm²
#   2 banks: ~0.092 mm² (bitcells only)
#   With periphery: ~0.3-0.6 mm² total
#
# This is significant area for a 1.249 mm² die. Consider:
#   - Reducing to 1 bank if area is tight
#   - Using 4KB if 32KB isn't essential for the PoC
