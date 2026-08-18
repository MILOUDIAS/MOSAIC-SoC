"""Bounded, design-scoped waivers for signoff metrics.

A waiver mechanism is the single feature most capable of quietly destroying an
evidence gate, so this one is built to make the dangerous shapes unexpressible
rather than merely discouraged.

Five rules, each enforced at load time:

**A waiver is a ceiling, not an exemption.** Every record carries
``accepted_max``. Waiving 591 max-slew violations accepts *591*; 592 fails.
A waiver therefore freezes a known defect at its measured size and cannot
absorb a regression that grows it.

**A waiver names one design.** ``design`` must equal the run's ``DESIGN_NAME``.
This is the trap the mechanism exists to avoid: the next thing we do is harden
a second configuration, and a waiver granted for Block A must not travel to it.
A waiver for a design that is not the one being evaluated is inert.

**A waiver names one metric, exactly.** No wildcards, no prefixes, no regular
expressions. ``metric`` is compared literally against the key the sweep
reports, so a waiver cannot broaden itself as LibreLane's vocabulary drifts.

**A waiver must say what it costs.** ``justification`` is mandatory and must be
substantive; a record without one does not load. This follows OpenADA's
assertion profiles, where ``non_goals`` has ``minItems: 1`` -- you cannot ship
a claim without stating what it does not prove.

**A waiver expires.** ``review_by`` is mandatory. Past that date the waiver
stops applying and the metric fails again. A waiver with no expiry is
indistinguishable from a deleted check after the person who granted it leaves.

Finally, applying a waiver never yields a silent pass: the waived records
travel in the evidence as ``waived`` and appear in the flow summary, so
"PASS with 2 waivers" is never rendered as "PASS".
"""

from __future__ import annotations

import datetime as _datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Minimum characters of justification. Enough to reject "n/a", "known", "ok",
# and the empty string, without pretending prose length is rigour.
_MIN_JUSTIFICATION = 40

_REQUIRED = ("metric", "design", "accepted_max", "justification", "review_by",
             "recorded_by", "evidence")


@dataclass(frozen=True)
class Waiver:
    """One accepted, bounded, dated exception for one metric on one design."""

    metric: str
    design: str
    accepted_max: float
    justification: str
    review_by: _datetime.date
    recorded_by: str
    evidence: str

    def expired(self, today: _datetime.date) -> bool:
        return today > self.review_by

    def as_record(self) -> Dict[str, Any]:
        return {
            "metric": self.metric,
            "design": self.design,
            "accepted_max": self.accepted_max,
            "review_by": self.review_by.isoformat(),
            "recorded_by": self.recorded_by,
            "evidence": self.evidence,
        }


class WaiverError(ValueError):
    """A waiver file that does not load. Never degraded to "no waivers"."""


def _as_date(value: Any, where: str) -> _datetime.date:
    if isinstance(value, _datetime.date) and not isinstance(value, _datetime.datetime):
        return value
    if isinstance(value, _datetime.datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return _datetime.date.fromisoformat(value.strip())
        except ValueError:
            pass
    raise WaiverError(f"{where}: review_by must be an ISO date (YYYY-MM-DD)")


def parse_waivers(data: Any, *, source: str = "<memory>") -> List[Waiver]:
    """Validate a waiver document into records, or raise.

    Raising rather than skipping is deliberate: a malformed waiver file must
    stop the gate, not silently reduce to an empty waiver set, which would
    turn a typo into an unexplained FAIL and a deleted key into a silent
    tightening nobody notices.
    """
    if data is None:
        return []
    if not isinstance(data, dict):
        raise WaiverError(f"{source}: waiver document must be a mapping")
    raw = data.get("waivers", [])
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        raise WaiverError(f"{source}: 'waivers' must be a list")

    waivers: List[Waiver] = []
    seen: set = set()
    for index, entry in enumerate(raw):
        where = f"{source}: waivers[{index}]"
        if not isinstance(entry, dict):
            raise WaiverError(f"{where}: must be a mapping")
        unknown = set(entry) - set(_REQUIRED)
        if unknown:
            raise WaiverError(f"{where}: unknown key(s) {sorted(unknown)}")
        missing = [key for key in _REQUIRED if key not in entry]
        if missing:
            raise WaiverError(f"{where}: missing required key(s) {missing}")

        metric = entry["metric"]
        if not isinstance(metric, str) or not metric.strip():
            raise WaiverError(f"{where}: metric must be a non-empty string")
        if any(char in metric for char in "*?["):
            raise WaiverError(
                f"{where}: metric {metric!r} looks like a pattern; waivers name "
                "exactly one metric so they cannot broaden themselves"
            )
        design = entry["design"]
        if not isinstance(design, str) or not design.strip():
            raise WaiverError(f"{where}: design must be a non-empty string")

        accepted = entry["accepted_max"]
        if isinstance(accepted, bool) or not isinstance(accepted, (int, float)):
            raise WaiverError(f"{where}: accepted_max must be a number")
        if accepted < 0:
            raise WaiverError(f"{where}: accepted_max must not be negative")

        justification = entry["justification"]
        if not isinstance(justification, str):
            raise WaiverError(f"{where}: justification must be a string")
        if len(justification.strip()) < _MIN_JUSTIFICATION:
            raise WaiverError(
                f"{where}: justification must be at least {_MIN_JUSTIFICATION} "
                "characters -- a waiver records why a known defect is accepted, "
                "and an unexplained waiver is a deleted check"
            )
        for field_name in ("recorded_by", "evidence"):
            value = entry[field_name]
            if not isinstance(value, str) or not value.strip():
                raise WaiverError(f"{where}: {field_name} must be a non-empty string")

        key = (metric.strip(), design.strip())
        if key in seen:
            raise WaiverError(
                f"{where}: duplicate waiver for {key[0]!r} on {key[1]!r}; "
                "two ceilings for one metric is ambiguous"
            )
        seen.add(key)

        waivers.append(Waiver(
            metric=metric.strip(),
            design=design.strip(),
            accepted_max=float(accepted),
            justification=justification.strip(),
            review_by=_as_date(entry["review_by"], where),
            recorded_by=entry["recorded_by"].strip(),
            evidence=entry["evidence"].strip(),
        ))
    return waivers


def load_waivers(path: Optional[Path]) -> List[Waiver]:
    """Read and validate a waiver YAML file. A missing path means no waivers."""
    if path is None or not Path(path).is_file():
        return []
    import yaml

    text = Path(path).read_text(errors="replace")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise WaiverError(f"{path}: not valid YAML: {error}") from error
    return parse_waivers(data, source=str(path))


def apply_waivers(
    findings: Sequence[Tuple[str, float]],
    waivers: Sequence[Waiver],
    *,
    design: Optional[str],
    today: Optional[_datetime.date] = None,
) -> Tuple[List[Tuple[str, float]], List[Dict[str, Any]], List[str]]:
    """Split findings into (still failing, waived, notes).

    A finding is waived only when a waiver matches its metric *and* the design
    under evaluation, has not expired, and the observed value is within the
    accepted ceiling. Anything else leaves the finding failing, with a note
    explaining which condition was not met -- a waiver that does not apply is
    reported, never silently ignored.
    """
    today = today or _datetime.date.today()
    remaining: List[Tuple[str, float]] = []
    waived: List[Dict[str, Any]] = []
    notes: List[str] = []

    by_metric = {w.metric: w for w in waivers if design and w.design == design}
    for key, value in findings:
        waiver = by_metric.get(key)
        if waiver is None:
            remaining.append((key, value))
            continue
        if waiver.expired(today):
            remaining.append((key, value))
            notes.append(
                f"waiver for {key} expired on {waiver.review_by.isoformat()} "
                "and no longer applies"
            )
            continue
        if value > waiver.accepted_max:
            remaining.append((key, value))
            notes.append(
                f"{key}={value:g} exceeds its waived ceiling of "
                f"{waiver.accepted_max:g}"
            )
            continue
        record = waiver.as_record()
        record["observed"] = value
        waived.append(record)

    inert = [w for w in waivers if design and w.design != design]
    if inert:
        notes.append(
            f"{len(inert)} waiver(s) not applied: recorded for a different "
            f"design than {design!r}"
        )
    return remaining, waived, notes
