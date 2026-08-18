"""Choosing the next die after routing refused to converge.

The ladder exists to turn a failure into a finished GDS without a human in the
loop, so its failure modes are: retrying at a density so close to the last one
that the attempt is wasted, and retrying forever.
"""

import pytest

from harness.physical.retry import (
    DEFAULT_MAX_ATTEMPTS,
    FLOOR,
    STEP,
    describe,
    next_utilisation,
    retry_ladder,
)
from harness.physical.routability import recommended_utilisation


def test_the_block_c_case_jumps_to_the_value_that_worked():
    """The whole point, stated against the run that motivated it.

    4 harts failed at 75% and routed clean at 65%. The retry goes straight to
    65% rather than spending hours on 70% to maybe discover the true ceiling —
    that is a deliberate experiment, not something to do inside a build.
    """
    decision = next_utilisation(harts=4, current=0.75, attempts_so_far=1)
    assert decision.retry
    assert decision.utilisation == pytest.approx(0.65)
    assert "demonstrated clean" in decision.reason


def test_a_retry_always_moves_far_enough_to_be_worth_a_run():
    """3 harts is demonstrated at 79.2%; retrying 80% -> 79.2% tests nothing.

    Every rung must be at least a full step below the one above it, or the
    ladder burns hours to change the die by half a percent.
    """
    for harts in (2, 3, 4, 5):
        for start in (0.85, 0.80, 0.75, 0.70):
            ladder = retry_ladder(harts, start)
            for above, below in zip(ladder, ladder[1:]):
                assert above - below >= STEP - 1e-9, (
                    f"{harts} harts: {above:.3f} -> {below:.3f} is not worth "
                    "a run")


def test_the_ladder_is_strictly_decreasing_and_bounded():
    for harts in (2, 3, 4, 5, 8):
        ladder = retry_ladder(harts, 0.80, max_attempts=10)
        assert ladder == sorted(ladder, reverse=True)
        assert len(set(ladder)) == len(ladder)
        assert all(u >= FLOOR - 1e-9 for u in ladder)


def test_retrying_stops_rather_than_shrinking_for_ever():
    assert not next_utilisation(4, FLOOR + 0.01, 1).retry
    assert not next_utilisation(4, 0.20, 1).retry


def test_the_attempt_limit_is_honoured():
    assert next_utilisation(4, 0.75, DEFAULT_MAX_ATTEMPTS - 1).retry
    stopped = next_utilisation(4, 0.75, DEFAULT_MAX_ATTEMPTS)
    assert not stopped.retry
    assert "limit" in stopped.reason
    assert len(retry_ladder(4, 0.75)) <= DEFAULT_MAX_ATTEMPTS


def test_the_ladder_starts_where_it_was_told_to():
    """The first entry is the attempt already made, not the first retry."""
    assert retry_ladder(4, 0.75)[0] == pytest.approx(0.75)
    assert describe(4, 0.75)[1][0] == pytest.approx(0.75)


def test_being_already_at_the_demonstrated_value_still_steps_down():
    """65% is demonstrated at 4 harts. If 65% itself plateaus, keep going.

    A design can be denser than the measurement covers -- same hart count,
    more logic -- so "already at the demonstrated value" is not a reason to
    give up, and the reason string must not claim nothing is demonstrated.
    """
    decision = next_utilisation(harts=4, current=0.65, attempts_so_far=1)
    assert decision.retry
    assert decision.utilisation == pytest.approx(0.60)
    assert "nothing closer is demonstrated" not in decision.reason


def test_a_size_with_no_measurement_just_steps():
    advice = recommended_utilisation(9)
    assert not advice.validated
    decision = next_utilisation(harts=9, current=0.70, attempts_so_far=1)
    assert decision.utilisation == pytest.approx(0.70 - STEP)


def test_describe_renders_the_plan_before_the_hours_are_spent():
    text, ladder = describe(4, 0.75)
    assert text == "75% -> 65% -> 60%"
    assert ladder[0] == pytest.approx(0.75)
