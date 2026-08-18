"""Deriving a die size instead of fitting one.

Phase 1 measured that the floorplan is the only design-dependent part of a
hardening config: Block B changed three knobs against Block A, two of them the
same knob, while PDN, timing and check configuration carried over untouched and
produced a clean result on a design they were never tuned for.

The load-bearing claim of this module is therefore narrow and checkable: given
a design, the die size is *derivable*. These tests hold it to the three designs
that have actually been hardened, and hold the model to refusing anything it
has no evidence for.
"""

import yaml

import pytest

from harness.core import REPO_ROOT
from harness.physical import (
    CALIBRATION,
    DEFAULT_MARGIN_UM,
    Floorplan,
    clock_period_ns,
    derive_floorplan,
    estimate_logic_area,
    margin_multiples,
)

# design name -> the config that produced it
HARDENED = {
    "mosaic_block_a": "configs/mosaic_tapeout_ultra.yaml",
    "mosaic_block_b": "configs/mosaic_blockb_3hart.yaml",
    "mosaic_block_c": "configs/mosaic_blockc_4hart.yaml",
}


def soc_of(design: str) -> dict:
    return yaml.safe_load((REPO_ROOT / HARDENED[design]).read_text())["soc"]


# ── the headline: reproduce both measured dies ───────────────────────

@pytest.mark.parametrize("measurement", CALIBRATION, ids=lambda m: m.design)
def test_derivation_reproduces_a_measured_die(measurement):
    """At the utilisation each design ACHIEVED, the derived die matches.

    This is the claim Phase 2 rests on. Under the current template Block A
    comes out at 83.5% utilisation, Block B at 76.3% and Block C at 67.6%;
    feeding each design's own achieved utilisation back in must reproduce the
    die that was actually built, or the model is not describing what the flow
    does.
    """
    floorplan, errors = derive_floorplan(
        soc_of(measurement.design),
        target_utilisation=measurement.utilisation,
    )
    assert not errors, errors
    error = floorplan.die_side_um / measurement.die_side_um - 1
    assert abs(error) < 0.01, (
        f"{measurement.design}: derived {floorplan.die_side_um:.1f} um vs "
        f"measured {measurement.die_side_um} um ({error:+.2%})"
    )


@pytest.mark.parametrize("measurement", CALIBRATION, ids=lambda m: m.design)
def test_a_hardened_design_uses_its_measured_area_not_a_fit(measurement):
    """A design we have hardened must report `measured`, never a guess."""
    estimate = estimate_logic_area(soc_of(measurement.design))
    assert estimate.basis == "measured"
    assert estimate.logic_um2 == measurement.logic_um2
    assert measurement.source in estimate.references


def test_more_harts_need_more_die():
    a, b = (derive_floorplan(soc_of(d))[0] for d in ("mosaic_block_a", "mosaic_block_b"))
    assert b.die_side_um > a.die_side_um


# ── refusing to guess ────────────────────────────────────────────────
#
# The calibration is three points, all SERV-only, OBI, no SRAM. An area model
# extrapolated past its evidence produces a number that reads as measured and
# is not, so the refusals matter more than the estimates.

@pytest.mark.parametrize("soc, fragment", [
    ({"cores": [{"ip": "picorv32", "count": 2}], "memory": {"sram_kb": 0}},
     "SERV-only"),
    ({"cores": [{"ip": "serv", "count": 2}, {"ip": "cv32e20", "count": 1}],
      "memory": {"sram_kb": 0}}, "SERV-only"),
    # The SRAM refusal now carries the cost rather than the excuse: 32 KB is
    # 13.40 mm2 of macro against a 2.18 mm2 largest die. See test_sram_cost.py.
    ({"cores": [{"ip": "serv", "count": 3}], "memory": {"sram_kb": 32}},
     "13.40 mm2"),
    ({"cores": [{"ip": "serv", "count": 1}], "memory": {"sram_kb": 0}},
     "starts at 2 harts"),
])
def test_an_uncalibrated_design_is_refused_with_its_reason(soc, fragment):
    estimate = estimate_logic_area(soc)
    assert estimate.basis == "unsupported"
    assert estimate.logic_um2 is None
    assert fragment in estimate.reason
    floorplan, errors = derive_floorplan(soc)
    assert floorplan is None
    assert errors and fragment in errors[0]


def test_sram_defaults_to_present_so_silence_is_not_taken_as_zero():
    """A config omitting `memory` must not be read as having no SRAM."""
    estimate = estimate_logic_area({"cores": [{"ip": "serv", "count": 2}]})
    assert estimate.basis == "unsupported"
    assert "SRAM" in estimate.reason


def test_extrapolation_is_labelled_as_such():
    """Five harts is past every calibration point and must say so."""
    estimate = estimate_logic_area(
        {"cores": [{"ip": "serv", "count": 5}], "memory": {"sram_kb": 0}})
    assert estimate.basis == "interpolated"
    assert "extrapolat" in estimate.reason
    assert "beyond every calibration point" in estimate.reason
    # Still monotonic and beyond the largest measured design.
    biggest = max(CALIBRATION, key=lambda m: m.serv_harts)
    assert estimate.logic_um2 > biggest.logic_um2


def test_extrapolation_uses_the_last_segment_not_the_average():
    """The per-hart increment grows, so averaging all points understates it.

    Measured: +170,169 um2 from 2 to 3 harts, +259,584 from 3 to 4. A straight
    line through the endpoints would carry 214,877 per hart, and Block C's
    prediction from exactly that kind of two-point fit came in 5.86% under.
    Extrapolation must use the most recent measured rate.
    """
    five = estimate_logic_area(
        {"cores": [{"ip": "serv", "count": 5}], "memory": {"sram_kb": 0}})
    points = sorted(CALIBRATION, key=lambda m: m.serv_harts)
    last_slope = ((points[-1].logic_um2 - points[-2].logic_um2)
                  / (points[-1].serv_harts - points[-2].serv_harts))
    assert five.logic_um2 == pytest.approx(points[-1].logic_um2 + last_slope)

    endpoint_slope = ((points[-1].logic_um2 - points[0].logic_um2)
                      / (points[-1].serv_harts - points[0].serv_harts))
    assert last_slope > endpoint_slope
    assert five.logic_um2 > points[-1].logic_um2 + endpoint_slope


def test_interpolation_uses_the_bracketing_segment(monkeypatch):
    """A hart count between two measurements must use the segment around it.

    The calibration is currently 2, 3 and 4 harts -- contiguous, so no integer
    falls strictly between two points and this branch is unreachable through
    the real table. It becomes reachable the moment a gap appears (a 6-hart
    design measured before a 5-hart one), so it is exercised here against a
    calibration with a deliberate hole rather than left untested until then.
    """
    from harness.physical import floorplan as fp

    gapped = tuple(m for m in fp.CALIBRATION if m.serv_harts != 3)
    monkeypatch.setattr(fp, "CALIBRATION", gapped)

    est = fp.estimate_logic_area(
        {"cores": [{"ip": "serv", "count": 3}], "memory": {"sram_kb": 0}})
    lo = next(m for m in gapped if m.serv_harts == 2)
    hi = next(m for m in gapped if m.serv_harts == 4)

    assert est.basis == "interpolated"
    assert "interpolated between" in est.reason
    assert lo.logic_um2 < est.logic_um2 < hi.logic_um2
    # Exactly the midpoint of the bracketing segment, not an endpoint fit.
    assert est.logic_um2 == pytest.approx((lo.logic_um2 + hi.logic_um2) / 2)


# ── margins are site multiples, and the axes differ ──────────────────

def test_margins_convert_to_per_axis_site_multiples():
    """0.56 um sites horizontally, 3.92 um vertically: different numbers.

    5 vertically, not 4. The Block B config was hand-written with 4, which is
    15.68 um -- 0.32 um UNDER the 16 um asked for, because it was rounded to
    the nearer multiple by hand. Rounding up is the safe direction and is what
    the derivation does; the hand-written value happened to be fine because the
    ring only needs 10 um, but "happened to be fine" is not a rule.
    """
    mults = margin_multiples(16.0)
    assert mults["TOP_MARGIN_MULT"] == mults["BOTTOM_MARGIN_MULT"] == 5
    assert mults["LEFT_MARGIN_MULT"] == mults["RIGHT_MARGIN_MULT"] == 29
    assert mults["TOP_MARGIN_MULT"] * 3.92 >= 16.0


def test_margins_round_up_because_the_ring_has_to_fit():
    assert margin_multiples(16.0)["TOP_MARGIN_MULT"] * 3.92 >= 16.0
    assert margin_multiples(16.0)["LEFT_MARGIN_MULT"] * 0.56 >= 16.0
    assert margin_multiples(0.1)["TOP_MARGIN_MULT"] == 1


# ── objectives feed the config, and bound it ─────────────────────────

def test_clock_period_comes_from_the_objective():
    assert clock_period_ns({"objectives": {"target_clock_mhz": 10}}) == 100.0
    assert clock_period_ns({"objectives": {"target_clock_mhz": 25}}) == 40.0


def test_no_objective_means_no_derived_clock_period():
    """Silence is not 10 MHz. The caller must decide."""
    assert clock_period_ns({}) is None
    assert clock_period_ns({"objectives": {}}) is None


def test_a_die_budget_that_the_design_exceeds_is_an_error():
    """Block B does not fit Block A's slot, and saying so is the point."""
    soc = dict(soc_of("mosaic_block_b"), objectives={"max_die_um": 1117.5})
    floorplan, errors = derive_floorplan(soc)
    assert floorplan is None
    assert errors and "does not fit the requested slot" in errors[0]


def test_a_die_budget_the_design_meets_is_accepted():
    soc = dict(soc_of("mosaic_block_a"), objectives={"max_die_um": 1200})
    floorplan, errors = derive_floorplan(soc)
    assert not errors and floorplan is not None


def test_an_area_budget_is_checked_too():
    soc = dict(soc_of("mosaic_block_b"), objectives={"max_area_mm2": 1.0})
    floorplan, errors = derive_floorplan(soc)
    assert floorplan is None
    assert errors and "max_area_mm2" in errors[0]


# ── the emitted knobs ────────────────────────────────────────────────

def test_emitted_knobs_are_absolute_and_self_consistent():
    floorplan, _ = derive_floorplan(soc_of("mosaic_block_a"))
    knobs = floorplan.as_librelane()
    assert knobs["FP_SIZING"] == "absolute"
    die, core = knobs["DIE_AREA"], knobs["CORE_AREA"]
    assert die[0] == die[1] == 0
    # The core box is inset from the die by exactly the margin on every side.
    assert core[0] == core[1] == pytest.approx(DEFAULT_MARGIN_UM, abs=0.01)
    assert die[2] - core[2] == pytest.approx(DEFAULT_MARGIN_UM, abs=0.01)
    assert die[3] - core[3] == pytest.approx(DEFAULT_MARGIN_UM, abs=0.01)


def test_absolute_sizing_does_not_emit_inert_margin_multipliers():
    """LibreLane: those variables "have no effect" once DIE/CORE are set.

    Emitting an inert knob next to the one that governs is how someone ends up
    tuning the wrong one and concluding the flow ignored them.
    """
    floorplan, _ = derive_floorplan(soc_of("mosaic_block_a"))
    knobs = floorplan.as_librelane()
    assert not any(k.endswith("_MARGIN_MULT") for k in knobs)


def test_emitted_knobs_are_all_real_librelane_variables():
    """An invented key fails the flow minutes in; catch it here instead.

    `FP_CORE_MARGIN` was invented while deriving the Block B config by hand and
    LibreLane refused to load it. Nothing but the flow itself would have said
    so, and only after a nix shell and a filelist resolve.
    """
    known = {
        "FP_SIZING", "DIE_AREA", "CORE_AREA",
        "BOTTOM_MARGIN_MULT", "TOP_MARGIN_MULT",
        "LEFT_MARGIN_MULT", "RIGHT_MARGIN_MULT",
    }
    floorplan, _ = derive_floorplan(soc_of("mosaic_block_a"))
    assert set(floorplan.as_librelane()) <= known


def test_utilisation_must_be_a_fraction():
    for bad in (0, 1, 1.5, -0.2):
        _, errors = derive_floorplan(soc_of("mosaic_block_a"),
                                     target_utilisation=bad)
        assert errors


# ── calibration integrity ────────────────────────────────────────────

def test_every_calibration_point_cites_a_run_that_exists():
    for measurement in CALIBRATION:
        assert (REPO_ROOT / measurement.source).is_file(), (
            f"{measurement.design} cites {measurement.source}, which is absent"
        )


def test_calibration_is_ordered_and_distinct():
    harts = [m.serv_harts for m in CALIBRATION]
    assert harts == sorted(harts) and len(set(harts)) == len(harts)


def test_calibration_matches_the_metrics_it_claims_to_come_from():
    """Guard against the table drifting from the runs it was read out of."""
    import json
    filler = {"fill_cell", "tap_cell", "endcap_cell", "antenna_cell"}
    for measurement in CALIBRATION:
        metrics = json.loads((REPO_ROOT / measurement.source).read_text())
        logic = sum(
            value for key, value in metrics.items()
            if key.startswith("design__instance__area__class:")
            and key.split("class:")[1] not in filler
        )
        assert logic == pytest.approx(measurement.logic_um2, rel=0.001), (
            f"{measurement.design}: table says {measurement.logic_um2:,.0f} um2, "
            f"the run says {logic:,.0f} um2"
        )
        assert metrics["design__die__area"] == pytest.approx(
            measurement.die_side_um ** 2, rel=0.001)
        # core_um2 went unchecked until 2026-08-09 and had silently drifted:
        # blockb_generated carried 1,361,200 against the run's 1,387,590. It is
        # stored evidence that nothing reads, which is precisely why nothing
        # caught it.
        assert metrics["design__core__area"] == pytest.approx(
            measurement.core_um2, rel=0.001), (
            f"{measurement.run_tag}: table says core {measurement.core_um2:,.0f} "
            f"um2, the run says {metrics['design__core__area']:,.0f} um2"
        )
        # ...and the recorded utilisation is the ratio of the two, not an
        # independent number to be typed in by hand.
        assert measurement.utilisation == pytest.approx(
            measurement.logic_um2 / measurement.core_um2, abs=0.001)


# ── the utilisation trade, measured ──────────────────────────────────

def test_utilisation_observations_include_every_run():
    from harness.physical import UTILISATION_OBSERVATIONS

    tags = {m.run_tag for m in UTILISATION_OBSERVATIONS}
    assert tags == {
        # current template -- repair margin 32 plus SIGNOFF_SDC_FILE, and the
        # CALIBRATION points. Each _sdc run's post-PnR netlist is BYTE-IDENTICAL
        # to the run it replaces (blocka_slew32, blockb_slew32, blockc_ant8):
        # same silicon, signed off against each pin's own liberty
        # max_transition instead of a blanket 4.0 ns. Citation change, not a
        # re-measurement -- logic_um2 is unchanged in all three.
        "blocka_sdc", "blockb_sdc", "blockc_sdc",
        # margin 45: what the template shipped for one day. Kept because they
        # are the tightest slew results we have and they bound what the last
        # stretch of margin costs in area.
        "blocka_slewonly", "blockb_reharden", "blockc_slew45",
        # pre-fix, kept because the utilisation trade was measured there and
        # has not been re-measured since
        "blocka_signoff", "blockb_signoff", "blockb_generated", "blockc_u65",
    }


def test_the_area_fit_uses_one_flow_era_only():
    """Mixing templates inside the fit is the failure this guards.

    The repair-margin change costs 2.7-3.4% cell area, so a calibration holding
    some pre-fix and some current points would be wrong by a variable amount
    depending on which hart count you asked about.
    """
    assert {m.flow_era for m in CALIBRATION} == {"current"}


def test_the_three_eras_are_distinguishable_in_the_observations():
    """Comparing across eras reads a template change as a density effect.

    blockb_signoff has 845 max-slew at 73.9% and blockb_sdc has 0 at 74.8%.
    Read without the era, that says a TIGHTER die eliminated every violation,
    which is nonsense.

    There are three eras: "pre-fix" (repair margin 10), "margin-45" (what the
    template shipped for one day), and "current" (margin 32 plus
    SIGNOFF_SDC_FILE). The margin-45 points are kept rather than deleted --
    they bound what the last stretch of repair margin costs in area.
    """
    from harness.physical import UTILISATION_OBSERVATIONS

    eras = {m.flow_era for m in UTILISATION_OBSERVATIONS}
    assert eras == {"current", "margin-45", "pre-fix"}
    by_era = {e: [m for m in UTILISATION_OBSERVATIONS if m.flow_era == e] for e in eras}
    # Pre-fix is separated from both repaired eras by two orders of magnitude.
    assert min(m.max_slew_violations for m in by_era["pre-fix"]) > 100
    assert max(m.max_slew_violations for m in by_era["current"]) < 100
    assert max(m.max_slew_violations for m in by_era["margin-45"]) < 100

    # This test USED to also assert `m45.max_slew_violations < cur.…` -- "45 is
    # tighter than 32 on every design". Removed 2026-08-16, because it was a
    # cross-era comparison inside the test whose whole point is that those are
    # meaningless, and it is now false: the current era counts violations of
    # each pin's OWN liberty max_transition and reports 0, while margin-45
    # counted violations of a blanket 4.0 ns and reported 12. Those are counts
    # of different things, not evidence that 32 beats 45.
    assert all(m.max_slew_violations == 0 for m in by_era["current"]), (
        "under per-pin library limits every current design measures zero; a "
        "non-zero here is a real violation of what the cells are qualified to")

    # Area IS comparable across eras -- it is micrometres either way, and this
    # is the relationship the margin-45 points are retained to document.
    for design in {m.design for m in by_era["current"]}:
        cur = next(m for m in by_era["current"] if m.design == design)
        m45 = next(m for m in by_era["margin-45"] if m.design == design)
        assert m45.logic_um2 > cur.logic_um2, design


def test_the_area_model_has_one_point_per_topology():
    """Two runs of one design are not two data points about its size.

    They differ: 1,114,918 um2 at 73.9% against 1,098,717 at 79.2%, because a
    tighter die needs less timing-repair buffering. Feeding both into the area
    fit would treat a floorplan effect as a topology effect.
    """
    harts = [m.serv_harts for m in CALIBRATION]
    assert len(set(harts)) == len(harts)


def test_every_observation_matches_its_run():
    import json

    from harness.physical import UTILISATION_OBSERVATIONS

    for m in UTILISATION_OBSERVATIONS:
        metrics = json.loads((REPO_ROOT / m.source).read_text())
        for field, key in (
            ("max_slew_violations", "design__max_slew_violation__count"),
            ("max_fanout_violations", "design__max_fanout_violation__count"),
            ("max_cap_violations", "design__max_cap_violation__count"),
        ):
            assert getattr(m, field) == metrics.get(key, 0), (
                f"{m.run_tag}.{field} disagrees with {key} in the run"
            )


def test_the_default_utilisation_is_not_the_one_that_cost_quality():
    """0.80 produced 2 max-cap violations where every other run had 0."""
    from harness.physical import DEFAULT_TARGET_UTILISATION, UTILISATION_OBSERVATIONS

    dirty = [m for m in UTILISATION_OBSERVATIONS if m.max_cap_violations]
    assert dirty, "expected the tight run to be recorded as costing quality"
    assert DEFAULT_TARGET_UTILISATION < min(m.utilisation for m in dirty)
