# Copyright 2026 MOSAIC-SoC Contributors
# Solderpad Hardware License, Version 2.1, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0 WITH SHL-2.1

"""
mosaic_sram_4k.py — OpenRAM config for a MOSAIC-SoC 4 KiB SRAM.

4 KiB SRAM: 4096 words × 8 bits = 32,768 bits = 4096 BYTES.
Requires careful floorplanning; built as two banks to halve row depth.

Renamed from mosaic_sram_32k.py: 4096 words x 8 bits is 32,768 BITS, which
is 4 KiB, not 32 KB. The old name reported the bit count as bytes and
overstated capacity by 8x (roadmap 14.1).

Usage:
  export OPENRAM_TECH=sw/vendor/openram
  python3 $OPENRAM_TECH/../sram_compiler.py sw/vendor/openram/configs/mosaic_sram_4k.py

Output: GDS, LEF, LIB, SPICE, Verilog for the 4 KiB SRAM macro.

AREA CAUTION. The estimate below (~0.3-0.6 mm²) is OpenRAM geometry for
THIS array and was always for 4 KiB -- only the label was wrong, so the
number itself did not change. For scale, the foundry's own macros are far
larger: gf180mcu_fd_ip_sram__sram512x8m8wm1 measures 431.9 x 484.9 um =
0.209 mm² for 512 BYTES (LEF SIZE), i.e. 0.419 mm²/KB, which puts 4 KiB at
1.675 mm² using PDK macros. The OpenRAM estimate is therefore optimistic by
roughly 3-5x and is UNVERIFIED -- it has never been compiled or measured.
Do not use it in an area budget until a real OpenRAM run exists.
See docs/area_study_gf180_min_soc.md.
"""

word_size = 8        # 8-bit words (byte-wide)
num_words = 4096     # 4096 words x 8 bits = 32,768 bits = 4 KiB
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
# This is significant area for a 1.249 mm² die -- and note this array
# holds 4 KiB, not the 32 KB the old filename claimed. Consider:
#   - Reducing to 1 bank if area is tight
#   - Using mosaic_sram_512b.py if 4 KiB isn't essential for the PoC
