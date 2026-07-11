#!/bin/bash
# Run the MOSAIC-SoC FuseSoC build setup (dependency resolution + file generation).
#
# This script creates a temporary fusesoc cores-root that includes only the
# parts of the tree that contain valid FuseSoC cores (excluding refs/, which
# has broken test .core files). It then runs `fusesoc run --setup` to verify
# that all dependencies resolve and all generated files are produced.
#
# Required env:
#   REGTOOL           - path to regtool.py
#   PERIPH_STRUCTS_GEN - path to periph_structs_gen.py
#   TEMPLATE_FILE     - path to periph_structs.tpl
#
# Usage:
#   ./scripts/fusesoc-setup.sh
#
# Exit codes:
#   0 - all dependencies resolved and generated files produced
#   1 - a dependency failed to resolve or a generator failed

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="${REPO_ROOT}/.venv/bin/python"
FUSESOC="${REPO_ROOT}/.venv/bin/fusesoc"

if [ ! -x "$(command -v "$FUSESOC" 2>/dev/null)" ] && [ ! -f "$FUSESOC" ]; then
    echo "ERROR: fusesoc not found at $FUSESOC"
    echo "Install with: pip install git+https://github.com/x-heep/fusesoc.git@ot"
    exit 1
fi

# Export tool paths for FuseSoC generators
export REGTOOL="${REGTOOL:-${REPO_ROOT}/hw/vendor/pulp_platform/register_interface/vendor/lowrisc_opentitan/util/regtool.py}"
export PERIPH_STRUCTS_GEN="${PERIPH_STRUCTS_GEN:-${REPO_ROOT}/util/periph_structs_gen/periph_structs_gen.py}"
export TEMPLATE_FILE="${TEMPLATE_FILE:-${REPO_ROOT}/util/periph_structs_gen/periph_structs.tpl}"

echo "MOSAIC-SoC FuseSoC build setup"
echo "  REGTOOL:           $REGTOOL"
echo "  PERIPH_STRUCTS_GEN: $PERIPH_STRUCTS_GEN"
echo "  TEMPLATE_FILE:     $TEMPLATE_FILE"
echo ""

# Create a temporary cores-root that includes only the project tree (excludes refs/)
FUSESOC_ROOT="/tmp/mosaic_fusesoc_root"
rm -rf "$FUSESOC_ROOT"
mkdir -p "$FUSESOC_ROOT"
cp "$REPO_ROOT/core-v-mini-mcu.core" "$FUSESOC_ROOT/"
cp "$REPO_ROOT/waiver_v5.core" "$FUSESOC_ROOT/"
ln -sf "$REPO_ROOT/hw" "$FUSESOC_ROOT/hw"
ln -sf "$REPO_ROOT/tb" "$FUSESOC_ROOT/tb"
ln -sf "$REPO_ROOT/util" "$FUSESOC_ROOT/util"
ln -sf "$REPO_ROOT/configs" "$FUSESOC_ROOT/configs"
ln -sf "$REPO_ROOT/sw" "$FUSESOC_ROOT/sw"

echo "Running fusesoc --setup (dependency resolution + file generation)..."
echo ""
$FUSESOC --cores-root "$FUSESOC_ROOT" run --target=sim --tool=verilator --setup openhwgroup.org:systems:core-v-mini-mcu

echo ""
echo "FuseSoC setup completed successfully."
echo "Build directory: /tmp/build/openhwgroup.org_systems_core-v-mini-mcu_1.0.5/sim-verilator/"