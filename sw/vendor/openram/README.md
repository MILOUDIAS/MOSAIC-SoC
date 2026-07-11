# OpenRAM GF180MCU Port for MOSAIC-SoC

## Overview

This directory contains an OpenRAM technology port for GF180MCU (180nm),
used to generate custom SRAM macros for the MOSAIC-SoC multi-core generator.

## Status

| Component | Status | Notes |
|-----------|--------|-------|
| `tech/tech.py` | ✅ Created | GF180MCU 3.3V process params, layer map, DRC rules |
| `gds_lib/cell1rw.gds` | ⚠️ Needed | 6T bitcell GDS — extract from PDK or copy from upstream OpenRAM |
| `sp_lib/cell1rw.sp` | ⚠️ Needed | 6T bitcell SPICE — extract from PDK or copy from upstream OpenRAM |
| `custom/gf180_bitcell.py` | ✅ Created | Bitcell wrapper for OpenRAM factory |
| `configs/mosaic_sram_4k.py` | ✅ Created | 4KB SRAM config (512×8, conservative) |
| `configs/mosaic_sram_32k.py` | ✅ Created | 32KB SRAM config (4096×8, 2-bank) |

## Porting steps

1. **Install OpenRAM**: `git clone https://github.com/VLSIDA/OpenRAM.git`
2. **Copy this directory** into `OpenRAM/technology/gf180mcu/`
3. **Obtain bitcell files**:
   - Extract `cell1rw.gds` from GF180MCU PDK: `gf180mcu_fd_ip_sram__sram64x8m8wm1`
   - Or copy from upstream OpenRAM's `gf180mcu` branch (if available)
4. **Set environment**:
   ```bash
   export OPENRAM_TECH=/path/to/OpenRAM/technology
   export SPICE_MODEL_DIR=/path/to/gf180mcu/models
   ```
5. **Generate SRAM**:
   ```bash
   cd OpenRAM/compiler
   python3 sram_compiler.py /path/to/mosaic_sram_4k.py
   ```

## Known issues

- Upstream OpenRAM GF180 port has wrong supply voltages (1.8V instead of 3.3V) — fixed in our `tech.py`
- PR #223 fixes wire capacitance units — our `tech.py` applies the corrected values
- Magic DRC has limited GF180 support — use KLayout or Calibre for signoff
- Missing library cells (sense_amp, write_driver) — OpenRAM can generate these from transistors if not provided as GDS

## SRAM configs

| Config | Size | Words × Bits | Banks | Area (est.) |
|--------|------|-------------|-------|-------------|
| `mosaic_sram_4k.py` | 4 KB | 512 × 8 | 1 | ~0.05 mm² |
| `mosaic_sram_32k.py` | 32 KB | 4096 × 8 | 2 | ~0.3-0.6 mm² |

## Integration with LibreLane

After generating SRAM macros, add them to `flow/librelane/config.yaml`:

```yaml
MACROS:
  mosaic_sram:
    gds: $OPENRAM_OUT/mosaic_sram_4k.gds
    lef: $OPENRAM_OUT/mosaic_sram_4k.lef
    lib: $OPENRAM_OUT/mosaic_sram_4k__tt_25C_3v3.lib
    verilog: $OPENRAM_OUT/mosaic_sram_4k.v
    power_pin: VDD
    ground_pin: GND
```

And add SRAM PDN grids to `flow/librelane/pdn_cfg.tcl`.
