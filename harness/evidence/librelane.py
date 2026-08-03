"""Read signoff evidence out of a real LibreLane run directory.

The run layout below is ground truth taken from `mattvenn/librelane_summary`
(MIT), which is a working tool against real LibreLane runs::

    runs/<RUN_TAG>/
      final/metrics.csv                                  # Metric,Value rows
      final/metrics.json                                 # same data, when present
      final/gds/*.gds
      *-magic-drc/reports/drc_violations.magic.rpt
      *-openroad-stapostpnr/summary.rpt
      *-openroad-checkantennas/openroad-checkantennas.log
      *-yosys-synthesis/reports/stat.json

Two design rules follow from that tool's behaviour.

**The metrics file is authoritative, but its absence is not "clean".**
`librelane_summary` prints *"no DRC file, DRC clean?"* — with a question mark,
because it genuinely cannot tell. We resolve that ambiguity the other way: no
evidence is ``INFRASTRUCTURE_ERROR``, never ``PASS``.

**Unknown metric keys must still be able to fail the run.** LibreLane's metric
vocabulary changes between versions, so a hardcoded key list silently goes
blind on upgrade. `librelane_summary`'s own summary view selects every row
whose key contains ``violation`` or ``error``; we do the same as a generic
sweep *in addition to* the curated key map, so a renamed or newly added
violation counter still fails the gate instead of disappearing.

Nothing here is PDK-specific.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Curated keys: precise semantics where we are confident of the name.
DRC_METRIC_KEYS = (
    "magic__drc_error__count",
    "klayout__drc_error__count",
    "magic__illegal__overlaps",
)
LVS_METRIC_KEYS = (
    "design__lvs_error__count",
    "design__lvs_device_difference__count",
    "design__lvs_unmatched_devices__count",
    "design__lvs_unmatched_nets__count",
    "design__lvs_unmatched_pins__count",
)
ANTENNA_METRIC_KEYS = ("route__antenna_violation__count",)
WORST_SLACK_KEYS = ("timing__setup__ws", "timing__hold__ws")
TNS_KEYS = ("timing__setup__tns", "timing__hold__tns")
AREA_KEYS = (
    "design__die__area",
    "design__core__area",
    "design__instance__area",
    "design__instance__count",
)

# Generic sweep, mirroring librelane_summary's own violation view.
_ADVERSE_KEY = re.compile(r"(?i)violation|error|_vio__")
# Keys that match the sweep but are descriptive rather than counts.
_ADVERSE_EXEMPT = re.compile(r"(?i)__ws$|__tns$|_slack$")

_STEP_GLOBS = {
    "magic_drc": "*-magic-drc/reports/drc_violations.magic.rpt",
    "klayout_drc": "*-klayout-drc/reports/*.rpt",
    "netgen_lvs": "*-netgen-lvs/reports/lvs.rpt",
    "sta_postpnr": "*-openroad-stapostpnr/summary.rpt",
    "antenna": "*-openroad-checkantennas/openroad-checkantennas.log",
}


@dataclass
class LibreLaneRun:
    """One located LibreLane run and the evidence read out of it."""

    run_dir: Path
    metrics: Dict[str, Any] = field(default_factory=dict)
    metrics_source: Optional[str] = None
    reports: Dict[str, Path] = field(default_factory=dict)

    @property
    def has_metrics(self) -> bool:
        return bool(self.metrics)


def _numeric(value: Any) -> Optional[float]:
    """Coerce a metric value to a number, or None if it is not numeric."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def find_latest_run(runs_dir: Path) -> Optional[Path]:
    """Newest run directory under ``runs_dir``, or None.

    Selection is by directory mtime rather than by parsing the run tag, so it
    does not depend on a particular LibreLane tag format.
    """
    if not runs_dir.is_dir():
        return None
    candidates = [p for p in runs_dir.iterdir() if p.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def load_metrics(run_dir: Path) -> Tuple[Dict[str, Any], Optional[str]]:
    """Load ``final/metrics.json`` if present, else ``final/metrics.csv``."""
    final = run_dir / "final"
    as_json = final / "metrics.json"
    if as_json.is_file():
        try:
            data = json.loads(as_json.read_text(errors="replace"))
            if isinstance(data, dict):
                return data, str(as_json)
        except (OSError, json.JSONDecodeError):
            pass
    as_csv = final / "metrics.csv"
    if as_csv.is_file():
        try:
            rows: Dict[str, Any] = {}
            with as_csv.open(newline="") as fh:
                for row in csv.DictReader(fh):
                    key = (row.get("Metric") or row.get("metric") or "").strip()
                    if key:
                        rows[key] = (row.get("Value") or row.get("value") or "").strip()
            if rows:
                return rows, str(as_csv)
        except OSError:
            pass
    return {}, None


def locate_reports(run_dir: Path) -> Dict[str, Path]:
    """Resolve the per-step report files this run produced."""
    found: Dict[str, Path] = {}
    for name, pattern in _STEP_GLOBS.items():
        matches = sorted(run_dir.glob(pattern))
        if matches:
            found[name] = matches[0]
    return found


def load_run(runs_dir: Path) -> Optional[LibreLaneRun]:
    """Locate the newest run under ``runs_dir`` and read its evidence."""
    run_dir = find_latest_run(runs_dir)
    if run_dir is None:
        return None
    metrics, source = load_metrics(run_dir)
    return LibreLaneRun(
        run_dir=run_dir,
        metrics=metrics,
        metrics_source=source,
        reports=locate_reports(run_dir),
    )


def first_metric(metrics: Dict[str, Any], keys) -> Tuple[Optional[str], Optional[float]]:
    """First present, numeric metric among ``keys``."""
    for key in keys:
        if key in metrics:
            value = _numeric(metrics[key])
            if value is not None:
                return key, value
    return None, None


def sum_metrics(metrics: Dict[str, Any], keys) -> Tuple[List[str], Optional[float]]:
    """Sum every present numeric metric among ``keys``.

    Returns ``(matched_keys, total)``; ``total`` is None when none matched, so
    a caller can tell "all zero" from "never measured".
    """
    matched: List[str] = []
    total = 0.0
    for key in keys:
        if key in metrics:
            value = _numeric(metrics[key])
            if value is not None:
                matched.append(key)
                total += value
    return (matched, total) if matched else ([], None)


def adverse_metrics(metrics: Dict[str, Any]) -> List[Tuple[str, float]]:
    """Every metric that indicates a problem, including unknown keys.

    Two rules:

    - any key matching ``violation`` / ``error`` / ``_vio__`` whose value is a
      number greater than zero;
    - any worst-slack key whose value is negative.

    The first is the version-drift safety net: a LibreLane upgrade that renames
    or adds a violation counter still fails the gate.
    """
    adverse: List[Tuple[str, float]] = []
    for key, raw in metrics.items():
        value = _numeric(raw)
        if value is None:
            continue
        if _ADVERSE_KEY.search(key) and not _ADVERSE_EXEMPT.search(key):
            if value > 0:
                adverse.append((key, value))
        elif key.endswith("__ws") and value < 0:
            adverse.append((key, value))
    return sorted(adverse)
