MAKEFILE_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
REPO_ROOT    := $(realpath $(MAKEFILE_DIR)/../..)

TOP = mosaic_chip_top

PDK_ROOT ?= $(MAKEFILE_DIR)/gf180mcu
PDK      ?= gf180mcuD
PDK_TAG  ?= 1.8.0

AVAILABLE_SLOTS = mosaic
DEFAULT_SLOT    = mosaic
SLOT ?= $(DEFAULT_SLOT)
ifeq ($(SLOT),default)
    SLOT = $(DEFAULT_SLOT)
endif
ifeq ($(filter $(SLOT),$(AVAILABLE_SLOTS)),)
    $(error $(SLOT) not in AVAILABLE_SLOTS: $(AVAILABLE_SLOTS))
endif

# MOSAIC SoC RTL → single flattened Verilog file consumed by config.yaml.
MOSAIC_CFG    ?= mosaic.yaml
DESIGN_V       = $(REPO_ROOT)/build/mosaic/design.v

LIBRELANE = librelane slots/slot_$(SLOT).yaml config.yaml \
            --pdk $(PDK) --pdk-root $(PDK_ROOT) --manual-pdk

# Classic flow = harden the SoC core (core_v_mini_mcu) as a macro, no pad ring.
LIBRELANE_CLASSIC = librelane config_classic.yaml \
            --pdk $(PDK) --pdk-root $(PDK_ROOT) --manual-pdk

.DEFAULT_GOAL := help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "};{printf "  %-22s %s\n",$$1,$$2}'
.PHONY: help

clone-pdk: ## Clone the wafer-space GF180MCU PDK (matched to LibreLane 3.0.0)
	rm -rf $(MAKEFILE_DIR)/gf180mcu
	git clone https://github.com/wafer-space/gf180mcu.git $(MAKEFILE_DIR)/gf180mcu --depth 1 --branch $(PDK_TAG)
.PHONY: clone-pdk

mosaic-gen: ## Generate the MOSAIC SoC RTL from the config (repo-root target)
	$(MAKE) -C $(REPO_ROOT) mosaic-gen MOSAIC_CFG=$(MOSAIC_CFG)
.PHONY: mosaic-gen

flatten: ## Flatten the generated SoC SystemVerilog → build/mosaic/design.v (sv2v)
	@mkdir -p $(REPO_ROOT)/build/mosaic
	@echo "Flatten x-heep SoC RTL into $(DESIGN_V)."
	@echo "Use the repo's vendored sv2v (util/sv2v_in_place.py, as the asic flow"
	@echo "does) over the FuseSoC-resolved filelist, OR enable USE_SLANG in"
	@echo "config.yaml to feed the SystemVerilog to Yosys directly (no sv2v)."
	@test -f $(DESIGN_V) || { echo "ERROR: $(DESIGN_V) missing — produce it via sv2v or switch to USE_SLANG."; exit 1; }
.PHONY: flatten

harden: mosaic-gen flatten ## Full RTL→GDS signoff on GF180MCU (needs nix-shell + clone-pdk)
	$(LIBRELANE) --save-views-to $(MAKEFILE_DIR)/final
.PHONY: harden

harden-nodrc: mosaic-gen flatten ## harden but skip DRC/antenna (fast dev iterations)
	$(LIBRELANE) --save-views-to $(MAKEFILE_DIR)/final --skip KLayout.Antenna --skip KLayout.DRC --skip Magic.DRC
.PHONY: harden-nodrc

classic: mosaic-gen flatten ## Harden the SoC core only (Classic flow, no pad ring)
	$(LIBRELANE_CLASSIC) --save-views-to $(MAKEFILE_DIR)/final_classic
.PHONY: classic

classic-nodrc: mosaic-gen flatten ## Classic harden, skip DRC/antenna (fast iterations)
	$(LIBRELANE_CLASSIC) --save-views-to $(MAKEFILE_DIR)/final_classic --skip KLayout.Antenna --skip KLayout.DRC --skip Magic.DRC
.PHONY: classic-nodrc

padring: ## Fast padring-only build (PadringFlow, no full PnR)
	PDK_ROOT=$(PDK_ROOT) PDK=$(PDK) python3 scripts/padring.py slots/slot_$(SLOT).yaml config.yaml
.PHONY: padring

openroad: ## Open the last run in OpenROAD GUI
	$(LIBRELANE) --last-run --flow OpenInOpenROAD
.PHONY: openroad

klayout: ## Open the last run in KLayout GUI
	$(LIBRELANE) --last-run --flow OpenInKLayout
.PHONY: klayout

render-image: ## Render a PNG from the final GDS
	mkdir -p img/
	PDK_ROOT=$(PDK_ROOT) PDK=$(PDK) python3 scripts/lay2img.py final/gds/$(TOP).gds img/$(TOP).png --width 2048 --oversampling 4
.PHONY: render-image
