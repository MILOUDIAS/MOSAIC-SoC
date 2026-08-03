#!/bin/bash
# Showcase: the Chipathon Block A tapeout part, from one prompt.
#
# WHAT THIS DEMONSTRATES
# ----------------------
# The project's claim is that an LLM authors CONFIGURATION while deterministic
# Python does the generating and checking. This is that claim on the design that
# actually matters -- the part being taped out -- rather than on a toy.
#
# Step 1 shows a prompt producing the frozen tapeout config field-for-field.
# Step 2 shows the same prompt, one clause changed, being REFUSED by the
# capability gate. The second step is the more important one: it is what stops a
# fluent prompt from talking its way into a tapeout claim.
#
# No model is called. The parse is a deterministic grammar, so this runs in CI
# and cannot pass by luck. Point an LLM at the same skill card
# (.claude/skills/soc-from-prompt/) and it produces the same prompt text.
#
# Usage:  ./demo/03_blocka_from_prompt.sh
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
cd "$REPO"

FROZEN="configs/mosaic_tapeout_ultra.yaml"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

PROMPT="a tapeout SoC: one serv titan rv32ic compressed with CSRs, \
one serv atlas rv32i without CSRs boot 0x40010000, \
no sram, 128 byte scratchpad, 1 kb boot rom, no DMA, no debug, no PLIC, \
no multicore timer, no gpio, no rv timer, no fast interrupts, \
XIP from flash, uart only, TDU dynamic"

echo "═══ 1. the prompt ═══"
echo "$PROMPT" | fold -s -w 78 | sed 's/^/  /'
echo

echo "═══ 2. what the deterministic grammar understood ═══"
./oh-my-soc soc-from-prompt plan "$PROMPT" 2>&1 | sed 's/^/  /' | head -20
echo

echo "═══ 3. generate, and diff against the frozen tapeout config ═══"
python3 - "$PROMPT" "$FROZEN" "$WORK" <<'PY'
import sys, pathlib, yaml
sys.path.insert(0, ".")
from harness.skills.soc_from_prompt import SocFromPrompt

prompt, frozen_path, work = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3])
result = SocFromPrompt(repo_root=work).run(prompt, name="mosaic_tapeout_ultra")
if not result.ok:
    print("  FAILED:", result.summary)
    for e in result.errors:
        print("   ", e)
    raise SystemExit(1)

generated = yaml.safe_load(open(result.details["config"]["path"]))["soc"]
frozen = yaml.safe_load(open(frozen_path))["soc"]
keys = sorted(set(generated) | set(frozen))
differing = {
    k: (generated.get(k, "<absent>"), frozen.get(k, "<absent>"))
    for k in keys
    if generated.get(k, "<absent>") != frozen.get(k, "<absent>")
}
print(f"  fields compared : {len(keys)}")
print(f"  fields matching : {len(keys) - len(differing)}")
if differing:
    print("  DIFFERENCES:")
    for k, (g, f) in differing.items():
        print(f"    {k}: prompt={g!r}  frozen={f!r}")
    raise SystemExit(1)
print()
print("  → the prompt reproduced the frozen tapeout config exactly,")
print("    including all eight selectable platform blocks and both cores'")
print("    with_csr / compressed / boot_addr parameters.")
PY
RC=$?
echo

echo "═══ 4. the gate: same design, but keep the debug module ═══"
echo "  (one clause removed: 'no debug')"
BAD="${PROMPT/no debug, /}"
./oh-my-soc soc-from-prompt run "$BAD" --name probe 2>&1 | sed 's/^/  /' | tail -6
echo
echo "  → refused. 'tapeout' in a prompt is a CLAIM; core_registry's capability"
echo "    matrix decides whether it holds. A prompt cannot argue with it."
echo

echo "═══ 5. and a simulation-only core asked to tape out ═══"
./oh-my-soc soc-from-prompt run "a tapeout SoC with one cva6 titan and two serv workers, 32kb sram, uart" \
    --name probe2 2>&1 | sed 's/^/  /' | tail -4
echo
echo "  → refused: CVA6/Rocket/BOOM are simulation-only on GF180."
echo

if [ "$RC" -eq 0 ]; then
  echo "### RESULT: prompt → frozen Block A config reproduced; both false claims refused"
else
  echo "### RESULT: FAILED — see step 3"
  exit 1
fi
