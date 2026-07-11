# Copyright 2026 MOSAIC-SoC Contributors
# Solderpad Hardware License, Version 2.1, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0 WITH SHL-2.1

"""
tech.py — OpenRAM technology configuration for GF180MCU.

Process: GlobalFoundries GF180MCU 180nm
PDK variant: gf180mcuD (5LM_1TM_11K)
Voltage flavor: 3.3V (nfet_03v3 / pfet_03v3)

Based on:
  - OpenRAM sky130 tech (reference port)
  - GF180MCU PDK layer map and DRC rules
  - wafer-space/gf180mcu-project-template

Usage:
  export OPENRAM_TECH=/path/to/OpenRAM/technology
  python3 sram_compiler.py mosaic_sram_config.py
"""

import os
import datetime
from datetime import date

# ── Custom module overrides ──────────────────────────────────────────
# Point to GF180-specific implementations where the default doesn't work.

tech_modules = d.module_type()
tech_modules["bitcell_1port"] = "gf180_bitcell"

# ── Cell properties (port mappings, pin directions) ──────────────────

cell_properties = d.cell_properties()

# Bitcell: 6T SRAM cell (cell1rw)
cell_properties.bitcell_1port.port_order = [
    "bl", "br", "gnd", "vdd", "vpb", "vnb", "wl"
]
cell_properties.bitcell_1port.port_types = [
    "OUTPUT", "OUTPUT", "GROUND", "POWER", "BIAS", "BIAS", "INPUT"
]
cell_properties.bitcell_1port.port_map = {
    "bl": "BL",
    "br": "BR",
    "wl": "WL",
    "vdd": "VDD",
    "gnd": "GND",
    "vpb": "nwell",
    "vnb": "pwell",
}

# Metal layer assignments for bitcell routing
cell_properties.bitcell_1port.wl_layer = "m3"    # Wordline on Metal3
cell_properties.bitcell_1port.bl_layer = "m2"    # Bitline on Metal2
cell_properties.bitcell_1port.vdd_layer = "m1"   # Power on Metal1
cell_properties.bitcell_1port.gnd_layer = "m1"   # Ground on Metal1

# ── GDS layer map ───────────────────────────────────────────────────
# GF180MCU layer numbers from the PDK (gf180mcuD).

layer = {}
layer["pwell"]      = (204, 0)
layer["nwell"]      = (21, 0)
layer["dnwell"]     = (12, 0)
layer["active"]     = (22, 0)
layer["pimplant"]   = (31, 0)
layer["nimplant"]   = (32, 0)
layer["poly"]       = (30, 0)
layer["contact"]    = (33, 0)
layer["m1"]         = (34, 0)
layer["via1"]       = (35, 0)
layer["m2"]         = (36, 0)
layer["via2"]       = (38, 0)
layer["m3"]         = (42, 0)
layer["via3"]       = (40, 0)
layer["m4"]         = (46, 0)
layer["via4"]       = (41, 0)
layer["m5"]         = (81, 0)
layer["mem"]        = (108, 5)   # Memory boundary
layer["boundary"]   = (0, 0)
layer["text"]       = (234, 5)
layer["dpoly"]      = (30, 0)    # Drawing poly (same as poly)
layer["dcontact"]   = (33, 0)    # Drawing contact

# ── DRC rules ───────────────────────────────────────────────────────
# From GF180MCU PDK design rules (180nm, 3.3V flavor).

drc = d.design_rules("gf180")
drc["grid"] = 0.005

# Transistor parameters
drc["min_tx_size"] = 0.250
drc["minlength_channel"] = 0.28        # 3.3V NMOS
drc["minlength_channel_pmos"] = 0.55
drc["minlength_channel_nmos"] = 0.7

# Well rules
drc.add_layer("nwell",   width=0.86, spacing=0.6)
drc.add_layer("pwell",   width=0.74, spacing=0.86)
drc.add_layer("dnwell",  width=0.86, spacing=0.0)

# Poly rules
drc.add_layer("poly",    width=0.28, spacing=0.24)
drc.add_layer("poly",
              minwidth=0.28, minlength=0.28,
              extension=[None, 0.07])

# Active rules
drc.add_layer("active",  width=0.22, spacing=0.33)

# Contact rules
drc.add_layer("contact", width=0.22, spacing=0.25)

# Metal1 rules
drc.add_layer("m1",      width=0.26, spacing=0.23)

# Via1 rules
drc.add_layer("via1",    width=0.26, spacing=0.26)

# Metal2 rules
drc.add_layer("m2",      width=0.28, spacing=0.28)

# Via2 rules
drc.add_layer("via2",    width=0.26, spacing=0.26)

# Metal3 rules
drc.add_layer("m3",      width=0.28, spacing=0.28)

# Via3 rules
drc.add_layer("via3",    width=0.26, spacing=0.26)

# Metal4 rules
drc.add_layer("m4",      width=0.28, spacing=0.28)

# Via4 rules
drc.add_layer("via4",    width=0.26, spacing=0.26)

# Metal5 rules (thick top metal)
drc.add_layer("m5",      width=0.36, spacing=0.28)

# ── SPICE parameters ────────────────────────────────────────────────
# NMOS/PMOS model names for GF180MCU 3.3V flavor.

spice = {}
spice["nmos"] = "nfet_03v3"
spice["pmos"] = "pfet_03v3"
spice["power"] = "VDD"
spice["ground"] = "GND"
spice["device_prefix"] = "X"
spice["device_prefix_vector"] = "X"

# SPICE model libraries (TT corner)
_spice_model_dir = os.environ.get("SPICE_MODEL_DIR", "")
if _spice_model_dir:
    spice["fet_libraries"] = {
        "TT": [[os.path.join(_spice_model_dir, "sm141064.ngspice"), "typical"]]
    }
else:
    # Fallback: use PDK-provided models if available
    _pdk_root = os.environ.get("PDK_ROOT", "")
    if _pdk_root:
        _model_path = os.path.join(
            _pdk_root, "libs.ref/gf180mcu_fd_sc_mcu7t5v0/netlist"
        )
        spice["fet_libraries"] = {
            "TT": [[os.path.join(_model_path, "gf180mcu_fd_sc_mcu7t5v0.tt.spice"), "typical"]]
        }

# GF180MCU 3.3V operating conditions
spice["feasible_period"] = 10             # ns — conservative for 180nm
spice["supply_voltages"] = [3.0, 3.3, 3.6]   # V — 3.3V ±10%
spice["nom_supply_voltage"] = 3.3         # V
spice["temperatures"] = [-40, 25, 125]    # °C

# Wire parasitic estimates (per unit length)
# NOTE: PR #223 fixes units — these are approximate for GF180 M2/M3
spice["wire_unit_r"] = 0.125             # Ohm/um
spice["wire_unit_c"] = 0.000134          # fF/um² → corrected from sky130

# ── Transistor sizing ───────────────────────────────────────────────
# GF180MCU 6T bitcell sizing (from cell1rw.sp)

parameter = {}
parameter["min_tx_size"] = 0.250
parameter["beta"] = 3                     # PMOS/NMOS drive ratio
parameter["6T_inv_nmos_size"] = 0.6       # um — inverter NMOS width
parameter["6T_inv_pmos_size"] = 0.95      # um — inverter PMOS width
parameter["6T_access_size"] = 0.6         # um — access transistor width
parameter["6T_nmos_size"] = 0.95          # um — pull-down NMOS width
parameter["6T_pmos_size"] = 0.6           # um — pull-up PMOS width

# ── Tool preferences ────────────────────────────────────────────────

drc_name = "magic"
lvs_name = "netgen"
pex_name = "magic"

# ── Process info ─────────────────────────────────────────────────────

tech_info = d.technology_data("GF180MCU")
tech_info["technology_name"] = "gf180mcu"
tech_info["drc_name"] = drc_name
tech_info["lvs_name"] = lvs_name
tech_info["pex_name"] = pex_name
tech_info["email"] = "mosaic-soc@example.com"
tech_info["date"] = str(date.today())
tech_info["process"] = "GF180MCU"
tech_info["temperature"] = 25
tech_info["voltage"] = 3.3
tech_info["technology_id"] = 1

# ── Bitcell array configuration ─────────────────────────────────────
# GF180 6T bitcell dimensions (from extracted cell1rw.gds)
# These drive OpenRAM's bank sizing calculations.

bitcell_width = 1.24    # um — measured from GF180 cell1rw
bitcell_height = 2.22   # um — measured from GF180 cell1rw
bitcell_area = bitcell_width * bitcell_height  # ~2.75 um²
