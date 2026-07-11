# Makefile — MOSAIC-SoC firmware build system.
#
# Builds the multi-core firmware (TITAN + ATLAS + NANO) and converts
# to Verilog hex format for simulation testbench loading.
#
# Toolchain: riscv64-unknown-elf-gcc (from system or oss-cad-suite)
# Usage:
#   make              — build all firmware
#   make titan        — build TITAN only
#   make clean        — remove build artifacts
#   make disasm       — generate disassembly listings
#
# The hex file (mosaic_fw.hex) is compatible with the tb/mosaic_soc/
# simulation testbench ($readmemh format).

# ── Toolchain ───────────────────────────────────────────────────────
# Override with: make RISCV_TC=/path/to/toolchain
RISCV_TC    ?= riscv64-unknown-elf
CC          = $(RISCV_TC)-gcc
OBJCOPY     = $(RISCV_TC)-objcopy
OBJDUMP     = $(RISCV_TC)-objdump
SIZE        = $(RISCV_TC)-size

# ── Architecture flags ──────────────────────────────────────────────
# All cores compiled as rv32i for maximum compatibility (serial cores
# can't execute compressed instructions).
ARCH        = -march=rv32i -mabi=ilp32

# ── Compiler flags ──────────────────────────────────────────────────
CFLAGS      = -Os -g -Wall -Wextra \
              -ffreestanding -nostdlib -nostartfiles \
              -ffunction-sections -fdata-sections \
              -I$(ROOT)/sw/device/lib/base \
              $(ARCH)

ASFLAGS     = -g $(ARCH) -ffreestanding -nostdlib

LDFLAGS     = -T $(LINKSCRIPT) -nostdlib -nostartfiles \
              -Wl,-Map=$(BUILD)/firmware.map

# ── Directories ─────────────────────────────────────────────────────
ROOT        = $(shell git rev-parse --show-toplevel 2>/dev/null || pwd)
BUILD       = $(ROOT)/sw/firmware/build
LINKSCRIPT  = $(ROOT)/sw/firmware/mosaic_link.ld

# ── Source files ────────────────────────────────────────────────────
TITAN_C_SRC = $(ROOT)/sw/firmware/common/tdu.c \
              $(ROOT)/sw/firmware/titan/titan_main.c
DEMO_C_SRC  = $(ROOT)/sw/firmware/common/tdu.c \
              $(ROOT)/sw/firmware/titan/titan_scheduling_demo.c
TITAN_A_SRC = $(ROOT)/sw/firmware/titan/start.S
ATLAS_A_SRC = $(ROOT)/sw/firmware/atlas/atlas_worker.S
NANO_A_SRC  = $(ROOT)/sw/firmware/nano/nano_worker.S

# ── Object files (flat names in build dir) ──────────────────────────
TITAN_OBJ   = $(BUILD)/start.o $(BUILD)/tdu.o $(BUILD)/titan_main.o
DEMO_OBJ    = $(BUILD)/start.o $(BUILD)/tdu.o $(BUILD)/titan_scheduling_demo.o
ATLAS_OBJ   = $(BUILD)/atlas_worker.o
NANO_OBJ    = $(BUILD)/nano_worker.o
ALL_OBJ     = $(TITAN_OBJ) $(ATLAS_OBJ) $(NANO_OBJ)
DEMO_ALL    = $(DEMO_OBJ) $(ATLAS_OBJ) $(NANO_OBJ)

# ── Outputs ─────────────────────────────────────────────────────────
ELF         = $(BUILD)/mosaic_fw.elf
HEX         = $(BUILD)/mosaic_fw.hex
DEMO_ELF    = $(BUILD)/mosaic_demo.elf
DEMO_HEX    = $(BUILD)/mosaic_demo.hex

# ── Targets ─────────────────────────────────────────────────────────
.PHONY: all demo clean disasm size

all: $(HEX)
	@echo "=== Firmware build complete ==="
	@echo "  ELF: $(ELF)"
	@echo "  HEX: $(HEX)"
	@$(SIZE) $(ELF)

demo: $(DEMO_HEX)
	@echo "=== Scheduling demo build complete ==="
	@echo "  ELF: $(DEMO_ELF)"
	@echo "  HEX: $(DEMO_HEX)"
	@$(SIZE) $(DEMO_ELF)

clean:
	rm -rf $(BUILD)

disasm: $(ELF)
	$(OBJDUMP) -d -S $< > $(BUILD)/firmware.dis

size: $(ELF)
	$(SIZE) -A $<

# ── Build directory ─────────────────────────────────────────────────
$(BUILD):
	mkdir -p $@

# ── Compile C sources (TITAN) ──────────────────────────────────────
$(BUILD)/tdu.o: $(ROOT)/sw/firmware/common/tdu.c | $(BUILD)
	@echo "  CC    $<"
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/titan_main.o: $(ROOT)/sw/firmware/titan/titan_main.c | $(BUILD)
	@echo "  CC    $<"
	$(CC) $(CFLAGS) -I$(ROOT)/sw/firmware/common -c $< -o $@

$(BUILD)/titan_scheduling_demo.o: $(ROOT)/sw/firmware/titan/titan_scheduling_demo.c | $(BUILD)
	@echo "  CC    $<"
	$(CC) $(CFLAGS) -I$(ROOT)/sw/firmware/common -c $< -o $@

# ── Compile assembly sources ───────────────────────────────────────
$(BUILD)/start.o: $(ROOT)/sw/firmware/titan/start.S | $(BUILD)
	@echo "  AS    $<"
	$(CC) $(ASFLAGS) -c $< -o $@

$(BUILD)/atlas_worker.o: $(ROOT)/sw/firmware/atlas/atlas_worker.S | $(BUILD)
	@echo "  AS    $<"
	$(CC) $(ASFLAGS) -c $< -o $@

$(BUILD)/nano_worker.o: $(ROOT)/sw/firmware/nano/nano_worker.S | $(BUILD)
	@echo "  AS    $<"
	$(CC) $(ASFLAGS) -c $< -o $@

# ── Link multi-core ELF ────────────────────────────────────────────
$(ELF): $(ALL_OBJ) $(LINKSCRIPT) | $(BUILD)
	@echo "  LD    $@"
	$(CC) $(LDFLAGS) $(ALL_OBJ) -o $@

# ── Link scheduling demo ELF ────────────────────────────────────────
$(DEMO_ELF): $(DEMO_ALL) $(LINKSCRIPT) | $(BUILD)
	@echo "  LD    $@"
	$(CC) $(LDFLAGS) $(DEMO_ALL) -o $@

# ── Convert to Verilog hex ──────────────────────────────────────────
$(HEX): $(ELF)
	@echo "  HEX   $@"
	$(OBJCOPY) -O verilog $< $@

$(DEMO_HEX): $(DEMO_ELF)
	@echo "  HEX   $@"
	$(OBJCOPY) -O verilog $< $@
