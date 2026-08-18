"""Decide whether detailed routing is going to converge, while it still can.

WHY THIS EXISTS
---------------
Block C at a 75% utilisation target ran detailed routing for eleven hours and
never converged. It plateaued near 3500 violations from iteration 4 to 16, a
rip-up then RAISED it 2906 -> 8552, and it was still at 1049 when the session
that launched it died -- without ever reaching its 64-iteration budget. The
same design at 65% routed to zero by iteration 10 and finished the whole flow
in 2 h 19 m.

Nothing available before the run predicted that. Two things were tried:

  * Utilisation compared across designs. Block C failed at 80.9% achieved while
    Block B routed clean at 82.2%. A bigger die means longer average nets, so
    the same density is harder to route in a bigger design; the comparison is
    only valid within one design.
  * Global-route overflow. GRT reported ZERO overflow on every layer for the
    run that then failed for eleven hours. It works on a coarse gcell grid with
    -allow_congestion and is not a routability signal.

What does discriminate is the SHAPE OF THE TRAJECTORY, which is only visible
once routing is under way. So this module does not predict. It watches, and it
calls a plateau early enough to be worth something.

THE RULE, AND THE MARGIN BEHIND IT
----------------------------------
Plateau = over a window of 5 iterations, violations fell by less than 25%,
while still above a floor. Measured against the three real trajectories:

    worst 5-iteration improvement, healthy runs
      Block B @ 82.2% achieved      77.6%
      Block C @ 70.2% achieved      98.0%
    worst 5-iteration improvement, the failure
      Block C @ 80.9% achieved       7.2%   <- fires at iteration 9

A threshold of 25% sits an order of magnitude away from both healthy runs and
3x away from the failure. That is a wide gap, but it rests on THREE
trajectories, one of them a failure. Treat the number as provisional and
re-derive it as runs accumulate.

The floor exists because a converging run legitimately stalls near zero: Block
B sat at 1, 1, 1 before its final 0, which is a 0% improvement window and must
not be called a plateau. Below max(50, 1% of the initial count), a flat
trajectory is a run that has essentially finished.

A rise is caught by the same rule -- improvement goes negative, which is below
any positive threshold -- so the iteration-17 blowup needs no separate case.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

# "[INFO DRT-0199]   Number of violations = 1049."
_VIOLATIONS = re.compile(r"Number of violations\s*=\s*(\d+)")

# "[INFO DRT-0195] Start 0th optimization iteration." -- the flow runs detailed
# routing more than once (a main pass, then shorter repair passes), and each
# invocation restarts its iteration counter at 0. Splitting on this marker is
# not cosmetic: Block C @65% goes 26579 -> ... -> 0, then a repair pass STARTS
# at 441. Concatenated, that reads as a 2840% rise and the plateau rule
# condemns a run that in fact finished clean. It did exactly that before this
# split existed.
_PASS_START = re.compile(r"Start 0th optimization iteration")

# Window and threshold: see the module docstring for the measurements these
# were chosen against. Deliberately not tunable per-run -- a threshold someone
# can loosen when a run is inconvenient is not a guard.
PLATEAU_WINDOW = 5
PLATEAU_MIN_IMPROVEMENT = 0.25

# Below this, a flat trajectory means "finished", not "stuck".
PLATEAU_FLOOR_ABS = 50
PLATEAU_FLOOR_FRAC = 0.01

CONVERGED = "converged"
CONVERGING = "converging"
PLATEAUED = "plateaued"
TOO_EARLY = "too_early"


@dataclass(frozen=True)
class RoutabilityObservation:
    """Whether a design at a given density actually finished routing.

    Separate from AreaMeasurement because a run that never routed has no
    signoff metrics to measure -- and that absence is exactly the observation.

    `target_utilisation` is the knob (`logic area / core area`), which is what
    a caller can actually set. `placement_utilisation` is GPL's achieved
    figure, recorded because it is what tempts people into the invalid
    cross-design comparison described below.
    """

    design: str
    run_tag: str
    serv_harts: int
    target_utilisation: float
    placement_utilisation: float
    routed: bool
    note: str


# The evidence behind the ceiling. Read the failure first: it cost eleven hours
# and it is the only reason the ceiling exists.
#
# Block A and Block B's first run were hardened from hand-written absolute
# dies, so they had no target knob; their `target_utilisation` is the effective
# value backed out as logic area / core area, which is the same quantity the
# knob sets.
ROUTABILITY_OBSERVATIONS: Tuple[RoutabilityObservation, ...] = (
    RoutabilityObservation(
        "mosaic_block_a", "blocka_signoff", 2, 0.813, 0.844, True,
        "clean; the taped-out configuration. Hand-written die",
    ),
    RoutabilityObservation(
        "mosaic_block_b", "blockb_signoff", 3, 0.739, 0.770, True,
        "clean. Hand-written die",
    ),
    RoutabilityObservation(
        "mosaic_block_b", "blockb_generated", 3, 0.792, 0.822, True,
        "clean at an 0.80 target, and the densest run that has ever routed",
    ),
    RoutabilityObservation(
        "mosaic_block_c", "blockc_generated", 4, 0.750, 0.809, False,
        "FAILED at an 0.75 target: detailed routing plateaued near 3500 "
        "violations from iteration 4-16, a rip-up then RAISED it 2906 -> 8552, "
        "and it was at 1049 after ~11 h when the session that launched it "
        "died. 86% shorts on Metal2/3/4. Never reached its 64-iteration budget",
    ),
    RoutabilityObservation(
        "mosaic_block_c", "blockc_u65", 4, 0.650, 0.702, True,
        "clean at an 0.65 target; 26579 -> 11986 -> 10827 -> 620 -> 55 -> ... "
        "-> 0 by iteration 10, whole flow in 2 h 19 m",
    ),
)


@dataclass(frozen=True)
class UtilisationAdvice:
    """A recommended target utilisation and the strength of its evidence."""

    utilisation: float
    basis: str        # "bounded" | "demonstrated" | "unvalidated"
    reason: str

    @property
    def validated(self) -> bool:
        return self.basis != "unvalidated"


def recommended_utilisation(harts: int) -> UtilisationAdvice:
    """The densest target this hart count has been shown to route at.

    NOT a model. It reports measurements and refuses to extrapolate, because
    the only two adjacent points -- 3 harts clean at 0.80, 4 harts failing at
    0.75 -- imply a decline of 0.15 per hart, and continuing that line gives
    0.50 at five harts and 0.35 at six. A two-point slope bounded by a single
    failure does not support that, and the die area it would demand is enormous.

    So past the measured range this returns the lowest demonstrated-clean
    value and says it is unvalidated. The real protection is `assess()`, which
    watches the run rather than guessing before it.
    """
    clean = [o for o in ROUTABILITY_OBSERVATIONS if o.routed and o.serv_harts == harts]
    failed = [o for o in ROUTABILITY_OBSERVATIONS
              if not o.routed and o.serv_harts == harts]

    if clean:
        best = max(o.target_utilisation for o in clean)
        if failed:
            worst_failure = min(o.target_utilisation for o in failed)
            return UtilisationAdvice(
                best, "bounded",
                f"{harts} harts routed at {best:.0%} and failed at "
                f"{worst_failure:.0%}; the ceiling is somewhere between, and "
                f"{best:.0%} is the demonstrated side of it")
        return UtilisationAdvice(
            best, "demonstrated",
            f"{harts} harts has routed cleanly at {best:.0%} "
            f"({len(clean)} run(s)); no failure recorded at this size")

    measured = sorted({o.serv_harts for o in ROUTABILITY_OBSERVATIONS})
    floor = min(o.target_utilisation
                for o in ROUTABILITY_OBSERVATIONS if o.routed)
    return UtilisationAdvice(
        floor, "unvalidated",
        f"no run at {harts} harts; routability has only been measured at "
        f"{measured} harts and the ceiling falls as designs grow. Using the "
        f"lowest demonstrated-clean target ({floor:.0%}) — this is a guess, "
        f"and the detailed-routing guard is what will actually catch it")


@dataclass(frozen=True)
class RoutabilityVerdict:
    """What the trajectory says so far, and why."""

    state: str
    iterations: int
    initial: Optional[int]
    latest: Optional[int]
    reason: str
    worst_window_improvement: Optional[float] = None

    @property
    def should_abort(self) -> bool:
        """True only for a plateau. `too_early` is not a licence to kill."""
        return self.state == PLATEAUED

    def __str__(self) -> str:                      # pragma: no cover - display
        return f"{self.state}: {self.reason}"


def parse_drt_passes(text: str) -> List[List[int]]:
    """Violation counts per iteration, split into detailed-routing passes.

    One list per DRT invocation, in log order. A pass that is still running
    simply has fewer entries -- there is no end marker to wait for, which is
    what makes this usable on a log being written.
    """
    passes: List[List[int]] = []
    current: List[int] = []
    for m in re.finditer(
            f"({_PASS_START.pattern})|({_VIOLATIONS.pattern})", text):
        if m.group(1) is not None:
            if current:
                passes.append(current)
            current = []
        else:
            current.append(int(m.group(3)))
    if current:
        passes.append(current)
    return passes


def parse_drt_trajectory(text: str) -> List[int]:
    """The trajectory of the CURRENT (last) detailed-routing pass.

    Not every count in the log: see `_PASS_START` for why concatenating passes
    turns a clean run into a false plateau.
    """
    passes = parse_drt_passes(text)
    return passes[-1] if passes else []


def _floor(initial: int) -> float:
    return max(PLATEAU_FLOOR_ABS, PLATEAU_FLOOR_FRAC * initial)


def assess(
    trajectory: Sequence[int],
    *,
    window: int = PLATEAU_WINDOW,
    min_improvement: float = PLATEAU_MIN_IMPROVEMENT,
) -> RoutabilityVerdict:
    """Classify a detailed-routing trajectory.

    Returns one of `converged`, `converging`, `plateaued`, `too_early`. Only
    `plateaued` justifies killing a run; `too_early` means keep watching.
    """
    counts = list(trajectory)
    if not counts:
        return RoutabilityVerdict(
            TOO_EARLY, 0, None, None,
            "no DRT iterations reported yet")

    initial, latest = counts[0], counts[-1]

    if latest == 0:
        return RoutabilityVerdict(
            CONVERGED, len(counts), initial, latest,
            f"reached 0 violations after {len(counts) - 1} iterations")

    if len(counts) <= window:
        return RoutabilityVerdict(
            TOO_EARLY, len(counts), initial, latest,
            f"{len(counts)} iterations so far; need more than {window} "
            "before a plateau means anything")

    floor = _floor(initial)
    if latest < floor:
        return RoutabilityVerdict(
            CONVERGING, len(counts), initial, latest,
            f"{latest} violations is below the {floor:,.0f} floor -- a flat "
            "trajectory this low is a run finishing, not one stuck")

    # Improvement across the most recent window, and the worst such window seen
    # so far (reported for context, not used for the decision).
    def improvement(start: int, end: int) -> float:
        old = counts[start]
        return 1.0 if old == 0 else (old - counts[end]) / old

    recent = improvement(len(counts) - 1 - window, len(counts) - 1)
    worst = min(improvement(i, i + window)
                for i in range(len(counts) - window))

    if recent < min_improvement:
        direction = "rose" if recent < 0 else "fell by only"
        magnitude = (f"{abs(recent):.1%}" if recent < 0 else f"{recent:.1%}")
        return RoutabilityVerdict(
            PLATEAUED, len(counts), initial, latest, worst_window_improvement=worst,
            reason=(
                f"violations {direction} {magnitude} over the last {window} "
                f"iterations ({counts[-1 - window]:,} -> {latest:,}), still "
                f"above the {floor:,.0f} floor. Healthy runs clear "
                f"{min_improvement:.0%} in every window"),
        )

    return RoutabilityVerdict(
        CONVERGING, len(counts), initial, latest, worst_window_improvement=worst,
        reason=(f"{initial:,} -> {latest:,} over {len(counts) - 1} iterations; "
                f"last {window} improved {recent:.1%}"),
    )


def assess_log(text: str, **kwargs) -> RoutabilityVerdict:
    """`assess` straight from a detailed-routing log."""
    return assess(parse_drt_trajectory(text), **kwargs)


def first_plateau(trajectory: Sequence[int], **kwargs) -> Optional[int]:
    """The earliest iteration at which a live watcher would have aborted.

    `assess` answers "what is happening now", which is the right question
    while a run is in flight and the WRONG one afterwards: Block C's failed
    run plateaued at iteration 9, drifted for thirty more, and by iteration 39
    its last five had improved 47.5% -- so a single check at the end calls it
    "converging" when it in fact never converged at all.

    Replaying the prefixes recovers what the guard would actually have done.
    Cheap: the iteration budget is 64.
    """
    counts = list(trajectory)
    for n in range(1, len(counts) + 1):
        if assess(counts[:n], **kwargs).should_abort:
            return n - 1
    return None
