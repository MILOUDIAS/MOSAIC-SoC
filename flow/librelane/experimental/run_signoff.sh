#!/usr/bin/env bash
# End-to-end signoff run for the Chipathon Block A macro.
#
# The point of this script is what it does NOT contain: there is no --skip.
# Every other run in experimental/ passes a long list of them to shorten the
# loop, which is how "0 routing DRC" got mistaken for "DRC clean". Here Magic
# DRC, KLayout DRC, Magic SPICE extraction, Netgen LVS, KLayout XOR, the
# antenna checks and the IR-drop/power-grid analysis all run, and any of them
# can fail the flow.
#
# Runtime is hours. Expect DRC and LVS to find things on the first attempt --
# that is the purpose.
#
# Usage:  ./run_signoff.sh [run-tag]
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLOW="$(cd "$HERE/.." && pwd)"
TAG="${1:-blocka_signoff}"
LOG="/tmp/ll_${TAG}.log"

cd "$FLOW"

if [ ! -d "$FLOW/gf180mcu" ]; then
  echo "ERROR: PDK missing. Run 'make clone-pdk' in $FLOW first." >&2
  exit 2
fi

# Refuse to run if anyone has added a skip to the config itself.
# Match a STEP substitution only -- `substituting_steps`, or a LibreLane step id
# (Namespace.Step) nulled out. An earlier version rejected ANY `: null`, which
# also caught legitimate config values such as MAX_CAPACITANCE_CONSTRAINT: null
# (used to fall back to per-cell liberty limits). That would have blocked a
# correct signoff config for looking superficially like a skip.
if grep -qE '^\s*(substituting_steps\b|[A-Za-z][A-Za-z0-9]*\.[A-Za-z][A-Za-z0-9]*\s*: *null)' \
     experimental/config_blocka_signoff.yaml; then
  echo "ERROR: config_blocka_signoff.yaml substitutes or nulls a flow step." >&2
  echo "       A signoff run must not skip steps. Aborting." >&2
  exit 3
fi

# ── resolve the source list for THIS machine ──────────────────────────────
# The config deliberately carries no absolute paths (see the note in it). The
# file list is derived from the FuseSoC manifest at run time, so a fresh clone
# hardens without hand-editing 526 paths, and a stale bundle cannot silently
# feed old RTL into the flow.
REPO="$(cd "$FLOW/../.." && pwd)"
MANIFEST="${MOSAIC_MANIFEST:-}"
if [ -z "$MANIFEST" ]; then
  # Absolute paths: this script runs from flow/librelane, not the repo root.
  MANIFEST="$("$REPO/.venv/bin/python" "$REPO/util/xheep_gen/build_manifest.py" locate \
      --config "${MOSAIC_CFG:-$REPO/configs/mosaic_tapeout_ultra.yaml}" \
      --base-config "$REPO/configs/general.hjson" \
      --pads-cfg "$REPO/configs/pad_cfg.py" \
      --repo-root "$REPO" 2>/dev/null)" || MANIFEST=""
fi
if [ -z "$MANIFEST" ] || [ ! -f "$MANIFEST" ]; then
  echo "ERROR: no MOSAIC manifest. Generate the RTL first:" >&2
  echo "  make mosaic-gen MOSAIC_CFG=configs/mosaic_tapeout_ultra.yaml" >&2
  exit 2
fi
BUILD_ROOT="$(ls -dt "$(dirname "$MANIFEST")"/runs/fusesoc.*/build 2>/dev/null | head -1)"
if [ -z "$BUILD_ROOT" ] || [ ! -d "$BUILD_ROOT" ]; then
  echo "ERROR: no FuseSoC build root under $(dirname "$MANIFEST")/runs/" >&2
  echo "  make mosaic-gen MOSAIC_CFG=configs/mosaic_tapeout_ultra.yaml" >&2
  exit 2
fi

RESOLVED="$HERE/.resolved_${TAG}.yaml"
FRAGMENT="$HERE/.filelist_${TAG}.yaml"
python3 "$FLOW/scripts/gen_filelist.py" "$REPO" \
    --manifest "$MANIFEST" --build-root "$BUILD_ROOT" --output "$FRAGMENT" \
    || { echo "ERROR: could not resolve the source list" >&2; exit 2; }
# LibreLane takes one config file, so the template and the resolved lists are
# concatenated into a run-local copy. It lives beside the template so any
# `dir::` references keep resolving.
cat experimental/config_blocka_signoff.yaml "$FRAGMENT" > "$RESOLVED"
echo "### sources : $(grep -c '^- /' "$FRAGMENT") files + include dirs, resolved from $(basename "$(dirname "$MANIFEST")")"

echo "### Block A SIGNOFF — no steps skipped"
echo "### config : experimental/config_blocka_signoff.yaml"
echo "### tag    : $TAG"
echo "### log    : $LOG"
echo

nix develop --command librelane "$RESOLVED" \
    --pdk gf180mcuD --pdk-root "$FLOW/gf180mcu" --manual-pdk \
    --run-tag "$TAG" \
    --save-views-to "$HERE/final_${TAG}" \
    2>&1 | tee "$LOG"

RUN="$HERE/runs/$TAG"
echo
echo "### SIGNOFF EVIDENCE"
# Report names as LibreLane 3.0 actually writes them. An earlier version of
# this list guessed, matched nothing, and printed an empty evidence section
# under a passing run -- which is the exact failure this script exists to stop.
for name in \
    "*-magic-drc/reports/drc.magic.rpt" \
    "*-klayout-drc/reports/*.rpt" \
    "*-netgen-lvs/reports/lvs.netgen.rpt" \
    "*-klayout-xor/reports/*.rpt" \
    "*-openroad-checkantennas-*/reports/antenna_summary.rpt" \
    "*-openroad-irdropreport/*.rpt"
do
    for f in $RUN/$name; do
        [ -f "$f" ] && printf '  %-58s %s\n' "${f#$RUN/}" "$(wc -l < "$f") lines"
    done
done

# Reported through the evidence parser rather than by eye: it will not call a
# missing metrics file clean.
cd "$FLOW/../.."
python3 - "$RUN" <<'PY'
import sys, pathlib
sys.path.insert(0, ".")
from harness.evidence import librelane as L
run = pathlib.Path(sys.argv[1])
# load_metrics returns (data, source_path). The second value is NOT an error --
# treating it as one made this script report "metrics unavailable" for a run
# that had completed cleanly. Absence shows up as an empty dict.
metrics, source = L.load_metrics(run)
if not metrics:
    print(f"  METRICS UNAVAILABLE under {run}/final -- verdict is UNKNOWN, not clean")
    raise SystemExit(1)
print(f"  source: {source}\n")
for k in ("magic__drc_error__count", "klayout__drc_error__count",
          "magic__illegal_overlap__count", "design__lvs_error__count",
          "design__lvs_unmatched_device__count", "design__lvs_unmatched_net__count",
          "design__lvs_unmatched_pin__count", "design__xor_difference__count",
          "route__drc_errors", "route__antenna_violation__count",
          "design__disconnected_pin__count"):
    print(f"  {k:42s} {metrics.get(k, '(NOT REPORTED)')}")

# Setup/hold closing says nothing about slew/cap/fanout, and those are the ones
# this design actually violates.
print()
for k in ("timing__setup__ws", "timing__hold__ws",
          "design__max_slew_violation__count",
          "design__max_cap_violation__count",
          "design__max_fanout_violation__count"):
    print(f"  {k:42s} {metrics.get(k, '(NOT REPORTED)')}")

adverse = L.adverse_metrics(metrics)
per_corner = [kv for kv in adverse if "__corner:" not in kv[0]]
print(f"\n  adverse metrics flagged: {len(adverse)} ({len(per_corner)} excluding per-corner duplicates)")
for k, v in per_corner[:12]:
    print(f"    {k:52s} {v}")
PY
