# MOSAIC-SoC — LibreLane GF180MCU hardening flow

RTL→GDSII flow for the MOSAIC SoC on **GF180MCU**, using **LibreLane 3.0.0**
(`meta.flow: Chip`) and the **wafer-space gf180mcu 1.8.0** PDK. Adapted from
[chipathon-2026-gf180mcu-padring](https://github.com/Mauricio-xx/chipathon-2026-gf180mcu-padring)
(Apache-2.0, © Leo Moser / wafer-space — see `NOTICE`).

## Layout

| Path | Purpose |
|------|---------|
| `config.yaml` | **Chip flow** config (`DESIGN_NAME: mosaic_chip_top`, GF180 DRC waivers, PDN, clock) — full chip with pad ring + sealring. |
| `slots/slot_mosaic.yaml` | Floorplan + pad map (`DIE_AREA`, `PAD_{N,S,E,W}`), merged on top of `config.yaml`. |
| `config_classic.yaml` | **Classic flow** config (`DESIGN_NAME: core_v_mini_mcu`) — hardens the SoC core only, **no pad ring**. Self-contained (no slot). |
| `core_classic.sdc` | Timing constraints for the Classic flow (clock on `clk_i`, no pad cell). |
| `src/chip_top.sv` | GF180 physical pad frame (in_s/in_c/bi_24t/dvdd/dvss cells). **Complete.** |
| `src/mosaic_soc_core.sv` | Non-signoff adapter placeholder. Physical runs reject it and require a bound version in `PHYSICAL_BUNDLE`. |
| `src/slot_defines.svh` | `SLOT_MOSAIC` pad counts (from `configs/pad_cfg.py`). |
| `pdn_cfg.tcl` | OpenROAD PDN generator (stdcell grid + core ring). |
| `chip_top.sdc` | Timing constraints (50 MHz / 20 ns). |
| `scripts/` | `padring.py` (fast pad-only build), `lay2img.py`, `run_native.sh`, `run_docker_iic.sh`. |
| `scripts/preflight.py` | Fail-closed capability, hash, RTL-binding, and SRAM-view gate. |
| `Makefile` | `clone-pdk`, standalone `mosaic-gen`, bundle preflights, hardening, GUIs, `render-image`. |
| `flake.nix`/`shell.nix`/`flake.lock` | Pinned toolchain (LibreLane 3.0.0 + FOSSi cache). |

## Current physical-flow status

RTL generation is operational, but this repository does **not** currently ship a bound
`mosaic_soc_core`, a flattened physical SoC source, or qualified 32-KiB SRAM views. No
DRC/LVS-clean GDS is claimed. The checked-in `src/mosaic_soc_core.sv` is deliberately a
placeholder and is never accepted by the hardening targets.

The public schema separates these states with `soc.target`. `rtl` (the default) and
`simulation` permit all generator-supported PDK/bus/memory combinations. `tapeout` is
currently qualified only for the canonical PoC declaration: `gf180mcu`, `obi`, 32-KiB
SRAM, 2-KiB boot ROM, 1x cv32e20 TITAN, 2x FazyRV-8 ATLAS at `0x1000`, 4x SERV NANO at
`0x2000`, dynamic TDU scheduling, and UART/GPIO/timer/SPI. LOG, FlooNoC, Sky130,
alternate memory/core/scheduler/peripheral combinations, CVA6, Rocket, and BOOM remain
valid RTL/simulation work but cannot enter this flow.

## Physical bundle contract

Every physical command requires `PHYSICAL_BUNDLE=/absolute/path`. The directory must
contain `physical_bundle.json`; every input is relative to that directory and protected
by its lowercase SHA-256 digest:

```json
{
  "schema_version": 1,
  "build_key": "<manifest build_key>",
  "artifacts": {
    "manifest":       {"path": "manifest.json", "sha256": "<64 hex>"},
    "flattened_rtl":  {"path": "design.v", "sha256": "<64 hex>"},
    "bound_core_rtl": {"path": "mosaic_soc_core.sv", "sha256": "<64 hex>"},
    "sram_gds":       {"path": "sram/mosaic_sram.gds", "sha256": "<64 hex>"},
    "sram_lef":       {"path": "sram/mosaic_sram.lef", "sha256": "<64 hex>"},
    "sram_lib":       {"path": "sram/mosaic_sram.lib", "sha256": "<64 hex>"},
    "sram_verilog":   {"path": "sram/mosaic_sram.v", "sha256": "<64 hex>"}
  }
}
```

`manifest.json` must be a current-schema MOSAIC manifest whose `resolved.target` is
`tapeout` and whose resolved PDK/bus/memory/core combination passes the authoritative
capability matrix. It must also contain a `physical_attestation` object with the same
`build_key` and one `<artifact>_sha256` value for every physical artifact. This binds the
flattened closure, adapter, and SRAM views back to the exact generated build rather than
merely hashing an arbitrary collection of files. The flattened RTL must be a nontrivial
SoC closure defining `core_v_mini_mcu` or `x_heep_system`; the bound adapter must actually
instantiate `x_heep_system`; the GDS must be a structurally complete GDSII library; and
the SRAM LEF/LIB/RTL views must define the same `mosaic_sram` macro used by the flow.
Classic core hardening does not need `bound_core_rtl`, but all other artifacts remain
mandatory.

## How to run

Requires Nix (flakes) + ~20 GB disk; first `nix-shell` pulls the toolchain from
the FOSSi binary cache. A real run is multi-hour.

```bash
cd flow/librelane
nix-shell ../../flow/librelane/shell.nix      # LibreLane 3.0.0 + EDA tools
make clone-pdk                                # wafer-space gf180mcu @ 1.8.0

# RTL generation is still independent of physical collateral:
make mosaic-gen MOSAIC_CFG=mosaic.yaml

# Fail before launching LibreLane if any input is missing, stale, or unsupported:
make preflight-chip PHYSICAL_BUNDLE=/abs/path/to/bundle

# Chip flow — full chip with pad ring + sealring:
make harden SLOT=mosaic PHYSICAL_BUNDLE=/abs/path/to/bundle
make harden-nodrc PHYSICAL_BUNDLE=/abs/path/to/bundle  # development only

# Classic flow — SoC core only, no pad ring (early synth/PnR/area exploration):
make preflight-classic PHYSICAL_BUNDLE=/abs/path/to/bundle
make classic PHYSICAL_BUNDLE=/abs/path/to/bundle
```

`make harden` does not generate or discover sources implicitly. It validates the bundle,
exports its exact artifact paths, and only then launches LibreLane.

## Remaining authoring steps (before a real tapeout)

1. **Bind the SoC pins** in a bundle-owned `mosaic_soc_core.sv` — instantiate
   `x_heep_system` and map each pad bus bit to its `pad_cfg.py` pin, keeping the
   bit indices aligned with `slots/slot_mosaic.yaml`. (The pad frame itself is
   done; this adapter is the only RTL gap.)
2. **Finalize the pad map** — confirm `NUM_*_PADS` in `slot_defines.svh` and the
   `PAD_{N,S,E,W}` order in `slot_mosaic.yaml` against the bonding diagram.
3. **SRAM macros** — map the 32 KB SRAM to a GF180 `mosaic_sram` macro and package
   its GDS/LEF/LIB/Verilog views in the bundle.
4. **Flatten** — create the bundle's `design.v` from the resolved FuseSoC filelist;
   `make flatten` is now only a validator and will not bless an ad-hoc stale file.
5. **Multi-clock SDC** — add derived/gated-clock constraints if the multi-core
   PoC needs them (`chip_top.sdc` currently constrains the single pad clock).
6. **DRC posture** — review inherited waiver globs and obtain clean DRC/LVS/STA
   evidence. `ERROR_ON_MAGIC_DRC` is enabled; `*-nodrc` targets are development-only.

> Inspection-only Docker (`scripts/run_docker_iic.sh`, hpretl/iic-osic-tools) is
> for viewing a finished GDS, **not** for signoff — its LibreLane version is not
> guaranteed to match the 3.0.0 pin.
