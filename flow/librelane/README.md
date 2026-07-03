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
| `src/mosaic_soc_core.sv` | Adapter: generic pad buses ⇄ `x_heep_system` pins. **Has the authoring TODO.** |
| `src/slot_defines.svh` | `SLOT_MOSAIC` pad counts (from `configs/pad_cfg.py`). |
| `pdn_cfg.tcl` | OpenROAD PDN generator (stdcell grid + core ring). |
| `chip_top.sdc` | Timing constraints (50 MHz / 20 ns). |
| `scripts/` | `padring.py` (fast pad-only build), `lay2img.py`, `run_native.sh`, `run_docker_iic.sh`. |
| `Makefile` | `clone-pdk`, `mosaic-gen`, `flatten`, `harden`, `padring`, GUIs, `render-image`. |
| `flake.nix`/`shell.nix`/`flake.lock` | Pinned toolchain (LibreLane 3.0.0 + FOSSi cache). |

## How to run (signoff)

Requires Nix (flakes) + ~20 GB disk; first `nix-shell` pulls the toolchain from
the FOSSi binary cache. A real run is multi-hour.

```bash
cd flow/librelane
nix-shell ../../flow/librelane/shell.nix      # LibreLane 3.0.0 + EDA tools
make clone-pdk                                # wafer-space gf180mcu @ 1.8.0

# Chip flow — full chip with pad ring + sealring:
make harden SLOT=mosaic                        # mosaic-gen → flatten → librelane → GDS
make padring                                   # fast pad placement only
make harden-nodrc                              # skip DRC/antenna

# Classic flow — SoC core only, no pad ring (early synth/PnR/area exploration):
make classic                                   # harden core_v_mini_mcu as a macro
make classic-nodrc                             # skip DRC/antenna
```

`make harden` chains: `mosaic-gen` (generate SoC RTL) → `flatten`
(SoC SystemVerilog → `build/mosaic/design.v`) → `librelane` (Yosys → OpenROAD →
KLayout/Magic/Netgen signoff).

## Remaining authoring steps (before a real tapeout)

1. **Bind the SoC pins** in `src/mosaic_soc_core.sv` — instantiate
   `x_heep_system` and map each pad bus bit to its `pad_cfg.py` pin, keeping the
   bit indices aligned with `slots/slot_mosaic.yaml`. (The pad frame itself is
   done; this adapter is the only RTL gap.)
2. **Finalize the pad map** — confirm `NUM_*_PADS` in `slot_defines.svh` and the
   `PAD_{N,S,E,W}` order in `slot_mosaic.yaml` against the bonding diagram.
3. **SRAM macros** — map the 32 KB SRAM to GF180 hard macros, add them to
   `MACROS` in `config.yaml` + `PDN_MACRO_CONNECTIONS`, and restore the SRAM
   `define_pdn_grid` blocks in `pdn_cfg.tcl`.
4. **Flatten** — wire up `make flatten` to the repo's `sv2v`
   (`util/sv2v_in_place.py`) over the FuseSoC filelist, or enable `USE_SLANG` in
   `config.yaml`.
5. **Multi-clock SDC** — add derived/gated-clock constraints if the multi-core
   PoC needs them (`chip_top.sdc` currently constrains the single pad clock).
6. **DRC posture** — `ERROR_ON_MAGIC_DRC: False` + the waiver globs are inherited
   from the workshop template; review them, since CLAUDE.md mandates DRC/LVS-clean
   signoff.

> Inspection-only Docker (`scripts/run_docker_iic.sh`, hpretl/iic-osic-tools) is
> for viewing a finished GDS, **not** for signoff — its LibreLane version is not
> guaranteed to match the 3.0.0 pin.
