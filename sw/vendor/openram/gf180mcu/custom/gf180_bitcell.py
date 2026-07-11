# Copyright 2026 MOSAIC-SoC Contributors
# Solderpad Hardware License, Version 2.1, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0 WITH SHL-2.1

"""
gf180_bitcell.py — GF180MCU 6T bitcell wrapper for OpenRAM.

Wraps the pre-built cell1rw from the GF180MCU PDK for use in OpenRAM's
bitcell array. The cell uses 3.3V transistors (nfet_03v3 / pfet_03v3)
and is routed on Metal1 (power) / Metal2 (bitlines) / Metal3 (wordline).
"""

from tech import tech
from base import design
from base import utils


class gf180_bitcell(design):
    """GF180MCU 6T SRAM bitcell (cell1rw).

    This is a wrapper around the pre-built GF180 bitcell GDS/SPICE
    that provides the interface OpenRAM expects for bitcell_array.
    """

    def __init__(self, name="cell1rw"):
        design.__init__(self, name)
        self.name = name

        # Load the pre-built cell from gds_lib/
        self.gds_file = os.path.join(
            os.path.dirname(__file__), "..", "gds_lib", "cell1rw.gds"
        )
        self.sp_file = os.path.join(
            os.path.dirname(__file__), "..", "sp_lib", "cell1rw.sp"
        )

        # Pin mapping (matches cell_properties in tech.py)
        self.pin_map = {
            "BL": "bl",
            "BR": "br",
            "WL": "wl",
            "VDD": "vdd",
            "GND": "gnd",
            "nwell": "vpb",
            "pwell": "vnb",
        }

        # Physical dimensions (from extracted GDS)
        self.width = 1.24    # um
        self.height = 2.22   # um

    def get_pin(self, name):
        """Get a pin by its electrical name."""
        return self.pin_map.get(name, name)


# Need os for path operations
import os
