"""Derive a floorplan from a design, instead of fitting one by hand.

Phase 1 established that the floorplan is the *only* hand-fitted part of the
hardening config. Block B differed from Block A in three knobs, two of them the
same knob: the design name, and absolute `DIE_AREA`/`CORE_AREA` replaced by
relative sizing. `CLOCK_PERIOD`, all six PDN knobs, `PL_TARGET_DENSITY_PCT`,
both hold-slack margins and the core-ring arrangement carried over untouched
and produced a clean result on a design they were never tuned for.

So this module derives exactly that part, and nothing else.

WHY ABSOLUTE SIZING
-------------------
LibreLane's `FP_CORE_UTIL` sizes the die from the *pre-CTS* cell area, and
clock-tree synthesis plus timing repair then add cells inside that fixed die.
Block A's own config records what that costs in practice: a run grew 0.877 to
1.346 mm2 (1.53x), so a 75% target landed near 98% and DPL-0036 "Detailed
placement failed". Every number in the calibration below is *post-CTS*, which
is the quantity that actually has to fit. Sizing the die directly from a
post-CTS estimate removes the pre/post confusion rather than compensating for
it with a fudged utilisation target.

WHAT THIS DOES NOT DO
---------------------
It does not predict timing, power, or whether the design closes. It computes
how much silicon the cells need and where the core boundary goes. STA remains
the only thing that decides whether a clock period was met, and `objectives.
target_clock_mhz` is a REQUEST carried into the config, never a claim.

It also refuses to guess. The calibration has three points, all SERV-only, OBI,
no SRAM macros. A topology outside that family returns `basis="unsupported"`
with the reason, because an area model extrapolated past its evidence is the
kind of number that reads as measured and is not.

WHAT THE THIRD POINT CHANGED
----------------------------
Block C's 4-hart area was predicted from the first two points and registered
before the run: 1,278,928 um2 against 1,358,524 measured, **-5.86%**. Against
-0.36% and -0.10% at the points themselves. Roughly half of that gap is a
confound rather than model error -- the scoring run went at a 65% target
because 75% would not route, and a looser die buys more timing-repair
buffering -- but the sign is not in doubt: the per-hart increment GROWS.

  2 -> 3 harts   +170,169 um2
  3 -> 4 harts   +259,584 um2

So the two-point straight line was replaced by piecewise-linear interpolation
between measured points, extrapolating on the LAST segment's slope rather than
the average of all of them. That is the locally valid rate, it is the
conservative direction, and it assumes no curve shape -- three points do not
justify fitting one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from harness.intent import DesignIntent, coerce

# Either the typed view or a raw validated mapping, while callers migrate.
SocInput = Union[DesignIntent, Mapping[str, Any]]
from harness.physical.routability import recommended_utilisation

# GF180MCU standard-cell site, from
# gf180mcu/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/techlef/*.tlef:
#   SITE GF018hv5v_mcu_sc7 ... SIZE 0.56 BY 3.92
# Margins are expressed to LibreLane in site multiples, so the two axes need
# different numbers to reach the same distance in micrometres.
SITE_WIDTH_UM = 0.56
SITE_HEIGHT_UM = 3.92


@dataclass(frozen=True)
class AreaMeasurement:
    """One hardened design, measured rather than estimated."""

    design: str
    run_tag: str
    serv_harts: int
    logic_um2: float          # post-CTS, filler/tap/endcap/antenna excluded
    core_um2: float
    die_side_um: float
    utilisation: float
    source: str
    # Electrical-quality violations at signoff. Recorded because Phase 1
    # measured them growing FASTER than area -- +43% slew and six-fold fanout
    # against +17.2% logic between these two designs -- so they are not a fixed
    # per-design cost. Not yet modelled: two points establish that the trend is
    # adverse, not what its shape is, and a curve fitted to two points would be
    # a claim rather than a measurement.
    max_slew_violations: int = 0
    max_fanout_violations: int = 0
    max_cap_violations: int = 0
    # Which signoff template produced this. "current" means
    # GRT_DESIGN_REPAIR_MAX_SLEW_PCT is 32 and signoff runs against per-pin
    # liberty limits via SIGNOFF_SDC_FILE; "margin-45" means the repair margin
    # the template shipped for one day; "pre-fix" means the LibreLane default
    # 10. (PNR_CORNERS also differs between the eras but was measured inert --
    # it changes no output, so it does not define an era.)
    # Not decoration -- the violation counts differ by two orders of magnitude
    # between eras, so comparing a pre-fix run's 845 slew against a current
    # run's 5 reads as a utilisation effect when it is entirely the template.
    # Only compare within an era.
    flow_era: str = "current"

    def __str__(self) -> str:                      # pragma: no cover - display
        return f"{self.design} ({self.serv_harts} harts, {self.logic_um2:,.0f} um2)"


# Measured from the signoff runs themselves, not from synthesis reports or
# datasheets. `logic_um2` is the sum of design__instance__area__class:* with
# fill_cell, tap_cell, endcap_cell and antenna_cell excluded -- those are
# physical-only cells that scale with the die, not with the design, so
# including them would make the model chase its own tail.
#
# *** THE 2026-08-12 WARNING HERE IS WITHDRAWN. It said the re-hardened
# netlists "MAY BE FUNCTIONALLY BROKEN" because runs/blocka_reharden failed
# gate-level simulation. That failure was an artefact of the ORACLE, not the
# netlist: the booting and failing netlists hold the same 36,572 logic
# instances and differ only in buffer/inverter/delay/clkbuf/fill cells, every
# one of which is transparent in a zero-delay simulation compiled -DFUNCTIONAL
# against UDP flops. Blocks B and C at the SAME repair margin both boot, which
# is what a race looks like and not what a repair defect looks like.
#
# All three designs have since been gate-level simulated and all three reach
# EXIT SUCCESS (A and B at 12,399 cycles, C at 12,400). The table below is
# validated.
#
# What survives from that bisect: PNR_CORNERS is inert -- blocka_slewonly
# differs from blocka_reharden in that one key and produces a BYTE-IDENTICAL
# netlist (ae511ec94850fab00e212fdf370ba7b6).
#
# REFRESHED 2026-08-11: all three designs re-hardened under the current
# template, each at its own previous die, so the fit is uniform again. The
# earlier table was ~3% low because every point predated the repair-margin
# change (GRT_DESIGN_REPAIR_MAX_SLEW_PCT 45), which cost cell area:
#
#   mosaic_block_a   950,908 ->   976,364   +2.68%
#   mosaic_block_b 1,114,918 -> 1,146,533   +2.84%
#   mosaic_block_c 1,358,524 -> 1,406,117   +3.41%
#
# and bought a ~99% reduction in max-slew violations: 591 -> 4, 845 -> 5,
# 826 -> 12. Under-predicting UNDER-sizes a die, which is the dangerous
# direction, so the refresh matters at tight targets even though the shift is
# small.
# ---- THE max_slew_violations FIELD CHANGED MEANING 2026-08-16 ----------------
# The three CALIBRATION points below now cite runs/<block>_sdc and record 0
# max-slew violations. Their predecessors recorded 56, 17 and 49. The SILICON IS
# THE SAME -- each _sdc run's post-PnR netlist is byte-identical to the run it
# replaces (blocka_slew32, blockb_slew32, blockc_ant8), and setup/hold slack
# matches to the last printed digit. Only the limit changed: signoff now uses
# SIGNOFF_SDC_FILE, so each pin is checked against its own liberty
# max_transition (7.0 ns at ss_125C_4v50) instead of a blanket 4.0 ns imported
# from the typical corner.
#
# CONSEQUENCE FOR ANYONE COMPARING ROWS: max_slew_violations is NOT comparable
# across this boundary. The margin-45 observations further down record 4, 5 and
# 12 -- measured against the blanket 4.0 ns. Reading those against the 0s here
# would say margin 32 beats margin 45 on slew, which is meaningless: they are
# counts of different things. logic_um2, core_um2, die_side_um and utilisation
# ARE comparable throughout; only the violation counts moved.
CALIBRATION: Tuple[AreaMeasurement, ...] = (
    # blocka_1110_ndr is the SUBMITTED configuration: 1110 um (the A-block
    # maximum, mandated -- 1117.5 exceeded it) at 20 MHz, with a non-default
    # routing rule on three fanout-1 nets. Zero max-slew and zero max-cap at all
    # nine corners, which no earlier Block A run achieved.
    AreaMeasurement(
        design="mosaic_block_a", run_tag="blocka_1110_ndr", serv_harts=2,
        logic_um2=952_726, core_um2=1_157_260,
        die_side_um=1110.0, utilisation=0.823,
        max_slew_violations=0, max_fanout_violations=4, max_cap_violations=0,
        source="flow/librelane/experimental/runs/blocka_1110_ndr/final/metrics.json",
    ),
    AreaMeasurement(
        design="mosaic_block_b", run_tag="blockb_sdc", serv_harts=3,
        logic_um2=1_124_355, core_um2=1_503_360,
        die_side_um=1261.6, utilisation=0.748,
        max_slew_violations=0, max_fanout_violations=1, max_cap_violations=0,
        source="flow/librelane/experimental/runs/blockb_sdc/final/metrics.json",
    ),
    # Still the loosest point at 67.6%, and still for the same reason: 4 harts
    # does not route at the tighter targets (see ROUTABILITY_OBSERVATIONS). A
    # looser die carries more timing-repair buffering, so this logic area is
    # inflated by roughly 3% relative to what the design would measure at ~80%.
    # The model over-predicts slightly at 4+ harts, which is the safe direction,
    # but it is a known bias rather than measurement noise.
    # blockc_ant8, not blockc_slew32. Same design, same die, same everything but
    # ONE antenna diode: raising DRT_ANTENNA_REPAIR_ITERS 3 -> 8 let the post-DRT
    # repair loop finish instead of stopping on its cap, and took
    # route__antenna_violation__count 1 -> 0. slew32 is not signed off.
    #
    # Every number below is UNCHANGED by that fix, which is a property of the
    # measurement rather than a coincidence: logic_um2 is the sum of the
    # functional cell classes and deliberately excludes fill, tap, endcap and
    # ANTENNA cells. A diode is a physical fix, not logic, so it cannot move the
    # area model. Only the citation moves.
    AreaMeasurement(
        design="mosaic_block_c", run_tag="blockc_sdc", serv_harts=4,
        logic_um2=1_375_437, core_um2=2_079_350,
        die_side_um=1477.7, utilisation=0.662,
        max_slew_violations=0, max_fanout_violations=4, max_cap_violations=0,
        source="flow/librelane/experimental/runs/blockc_sdc/final/metrics.json",
    ),
)

# Every signoff run, for the "what does packing it tighter cost" question --
# which is NOT the question CALIBRATION answers, and must not be mixed into the
# area fit.
#
# READ THE flow_era FIELD BEFORE COMPARING ANY TWO OF THESE. The utilisation
# trade was measured entirely in the pre-fix era:
#
#   73.9%, 1261.6 um  ->  845 slew,  0 max-cap,  6 fanout
#   79.2%, 1212.5 um  -> 1459 slew,  2 max-cap,  4 fanout
#
# +5.3 points of utilisation bought 7.6% less area and cost +73% slew plus a
# violation class that had been zero. That trade is real and has NOT been
# re-measured since the fixes -- and it cannot be inferred from the current-era
# points, because those sit at 83.5%, 76.3% and 67.6% with 4, 5 and 12
# violations, an ordering that reflects design size and template, not density.
#
# It also bounds the area model: the two pre-fix Block B runs differ by 1.5% in
# logic area at the same topology (1,114,918 against 1,098,717), because a
# tighter die needs less timing-repair buffering. Cell area is not purely a
# property of the design.
UTILISATION_OBSERVATIONS: Tuple[AreaMeasurement, ...] = CALIBRATION + (
    AreaMeasurement(
        design="mosaic_block_a", run_tag="blocka_signoff", serv_harts=2,
        logic_um2=950_908, core_um2=1_169_330,
        die_side_um=1117.5, utilisation=0.813,
        max_slew_violations=591, max_fanout_violations=1,
        flow_era="pre-fix",
        source="flow/librelane/experimental/runs/blocka_signoff/final/metrics.json",
    ),
    AreaMeasurement(
        design="mosaic_block_b", run_tag="blockb_signoff", serv_harts=3,
        logic_um2=1_114_918, core_um2=1_508_180,
        die_side_um=1261.6, utilisation=0.739,
        max_slew_violations=845, max_fanout_violations=6,
        flow_era="pre-fix",
        source="flow/librelane/experimental/runs/blockb_signoff/final/metrics.json",
    ),
    AreaMeasurement(
        design="mosaic_block_b", run_tag="blockb_generated", serv_harts=3,
        logic_um2=1_098_717, core_um2=1_387_590,
        die_side_um=1212.5, utilisation=0.792,
        max_slew_violations=1459, max_fanout_violations=4, max_cap_violations=2,
        flow_era="pre-fix",
        source="flow/librelane/experimental/runs/blockb_generated/final/metrics.json",
    ),
    AreaMeasurement(
        design="mosaic_block_c", run_tag="blockc_u65", serv_harts=4,
        logic_um2=1_358_524, core_um2=1_956_850,
        die_side_um=1434.71, utilisation=0.694,
        max_slew_violations=1018, max_fanout_violations=3, max_cap_violations=0,
        flow_era="pre-fix",
        source="flow/librelane/experimental/runs/blockc_u65/final/metrics.json",
    ),
    # ---- margin-45 era -------------------------------------------------------
    # Kept as observations, not deleted, and NOT in CALIBRATION. These are the
    # same three designs at repair margin 45, which is what the template shipped
    # for one day. They are the tightest slew results this project has, and they
    # bound what the last stretch of margin costs in area: +1.7%, +2.0%, +2.2%
    # over the same designs at 32, for 52, 12 and 37 fewer slew violations.
    #
    # Block A's netlist here is the one that fails zero-delay GLS. B and C at
    # the SAME margin both boot, which is the strongest evidence that the
    # failure is a simulation race and not a repair defect -- a defect in the
    # margin would not spare two designs out of three.
    AreaMeasurement(
        design="mosaic_block_a", run_tag="blocka_slewonly", serv_harts=2,
        logic_um2=976_364, core_um2=1_169_330,
        die_side_um=1117.5, utilisation=0.835,
        max_slew_violations=4, max_fanout_violations=1, max_cap_violations=0,
        flow_era="margin-45",
        source="flow/librelane/experimental/runs/blocka_slewonly/final/metrics.json",
    ),
    AreaMeasurement(
        design="mosaic_block_b", run_tag="blockb_reharden", serv_harts=3,
        logic_um2=1_146_533, core_um2=1_503_360,
        die_side_um=1261.6, utilisation=0.763,
        max_slew_violations=5, max_fanout_violations=2, max_cap_violations=0,
        flow_era="margin-45",
        source="flow/librelane/experimental/runs/blockb_reharden/final/metrics.json",
    ),
    AreaMeasurement(
        design="mosaic_block_c", run_tag="blockc_slew45", serv_harts=4,
        logic_um2=1_406_117, core_um2=2_079_350,
        die_side_um=1477.7, utilisation=0.676,
        max_slew_violations=12, max_fanout_violations=4, max_cap_violations=0,
        flow_era="margin-45",
        source="flow/librelane/experimental/runs/blockc_slew45/final/metrics.json",
    ),
)

# Utilisation to aim for. This was 0.80, and hardening Block B from a generated
# config at that target measured what it costs. Same RTL, same everything but
# the die:
#
#   73.9%, 1261.6 um die   ->  845 slew,  0 max-cap,  6 fanout
#   79.2%, 1212.5 um die   -> 1459 slew,  2 max-cap,  4 fanout
#
# +5.3 points of utilisation bought 7.6% less area and cost +73% slew
# violations plus a violation class that had been zero in every previous run.
# The flow still legalised and every hard check stayed clean -- DRC, LVS, XOR,
# antenna, routing DRC all 0, setup +20.89 ns -- so this is not a correctness
# cliff. It is a quality trade, and it was being made silently.
#
# 0.75 is the conservative side of that trade. Note the confound: Block A ran
# at 81.3% with 591 slew and 0 max-cap, so the tolerable utilisation is not a
# constant -- it falls as the design grows, and separating "bigger design" from
# "tighter die" needs points we do not have. Callers who want the area can pass
# --utilisation explicitly; the default should not spend electrical quality
# without being asked.
DEFAULT_TARGET_UTILISATION = 0.75

# Ring allowance, matching Block A: the ring consumes 10 um (offset 2 + width 3
# on each side) and Block A left 6 um clearance beyond it.
DEFAULT_MARGIN_UM = 16.0


@dataclass(frozen=True)
class AreaEstimate:
    """A cell-area figure and, more importantly, where it came from."""

    logic_um2: Optional[float]
    basis: str                       # "measured" | "interpolated" | "unsupported"
    reason: str
    references: Tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.logic_um2 is not None


def estimate_logic_area(soc: SocInput) -> AreaEstimate:
    """Post-CTS logic-cell area for a config, or a refusal with its reason.

    Piecewise-linear between measured points, extrapolating past the last one
    on the last segment's slope. Three points do not justify fitting a curve,
    but they are enough to show the per-hart increment is not constant, so a
    single straight line through the endpoints would discard the middle
    measurement and understate growth (see the module docstring).

    Restricted to SERV-only designs, and that is not conservatism for its own
    sake: the SCI wrapper dominates a SERV worker (162,000 um2 against the
    core's 21,151), so a different core family has a different constant, and
    nothing here has measured one.
    """
    intent = coerce(soc)
    harts = intent.hart_count

    if not intent.is_only("serv"):
        return AreaEstimate(
            None, "unsupported",
            f"calibration covers SERV-only designs; this config uses "
            f"{sorted(ip for ip in intent.core_ips if ip)}",
        )
    if intent.memory.has_macros:
        # Quantified rather than shrugged at. "Macro placement is not
        # modelled" was true and useless -- it reads as a gap in the tool when
        # the design is in fact impossible in this PDK, and the difference
        # matters to whoever asked. See harness/physical/sram.py.
        from harness.physical.sram import sram_cost

        cost = sram_cost(int(intent.memory.sram_kb))
        detail = f" {cost.describe()}." if cost else ""
        return AreaEstimate(
            None, "unsupported",
            f"this design asks for {intent.memory.sram_kb} KB of on-chip SRAM."
            f"{detail} Block A's entire die is 1.25 mm2 and Block C's is 2.18, "
            "so that does not fit any area this project has. Every design "
            "hardened so far runs execute-in-place from flash with "
            "memory.sram_kb: 0, which is why the calibration covers no SRAM "
            "designs. Separately, nothing in hw/ instantiates a PDK SRAM "
            "macro today, so sram_kb > 0 currently synthesises to flip-flops "
            "instead -- comparably large, and also unplaced",
        )
    if harts < 2:
        return AreaEstimate(
            None, "unsupported",
            f"calibration starts at 2 harts; this config has {harts}",
        )

    exact = [m for m in CALIBRATION if m.serv_harts == harts]
    if exact:
        m = exact[0]
        return AreaEstimate(m.logic_um2, "measured",
                            f"measured on {m.design} ({m.run_tag})", (m.source,))

    points = sorted(CALIBRATION, key=lambda m: m.serv_harts)

    # Between two measurements: interpolate on the segment that brackets it.
    for lo, hi in zip(points, points[1:]):
        if lo.serv_harts < harts < hi.serv_harts:
            per_hart = ((hi.logic_um2 - lo.logic_um2)
                        / (hi.serv_harts - lo.serv_harts))
            value = lo.logic_um2 + (harts - lo.serv_harts) * per_hart
            return AreaEstimate(
                value, "interpolated",
                f"interpolated between {lo.design} ({lo.serv_harts} harts, "
                f"{lo.logic_um2:,.0f} um2) and {hi.design} ({hi.serv_harts} "
                f"harts, {hi.logic_um2:,.0f} um2): {per_hart:,.0f} um2 per hart "
                "on that segment",
                (lo.source, hi.source),
            )

    # Past the largest measured design: use the last segment's slope. The
    # increment grew 170,169 -> 259,584 across the three points, so averaging
    # over all of them would understate it; the most recent pair is the best
    # available estimate of the current rate.
    lo, hi = points[-2], points[-1]
    per_hart = (hi.logic_um2 - lo.logic_um2) / (hi.serv_harts - lo.serv_harts)
    value = hi.logic_um2 + (harts - hi.serv_harts) * per_hart
    return AreaEstimate(
        value, "interpolated",
        f"extrapolated beyond {hi.design}, the largest measured design "
        f"({hi.serv_harts} harts, {hi.logic_um2:,.0f} um2), on the last "
        f"measured segment: {per_hart:,.0f} um2 per additional hart. "
        f"{harts} harts is beyond every calibration point, and the per-hart "
        "increment has grown at every step so far, so treat this as a lower "
        "bound that the first run will correct",
        (lo.source, hi.source),
    )


def margin_multiples(margin_um: float) -> Dict[str, int]:
    """Convert a micrometre margin into LibreLane's per-axis site multiples.

    There is no absolute core-margin variable. `{TOP,BOTTOM}_MARGIN_MULT` are
    multiples of site HEIGHT and `{LEFT,RIGHT}_MARGIN_MULT` of site WIDTH, so
    the same distance needs different numbers on each axis. Rounded up, never
    down: the ring has to fit.
    """
    import math
    vertical = max(1, math.ceil(margin_um / SITE_HEIGHT_UM))
    horizontal = max(1, math.ceil(margin_um / SITE_WIDTH_UM))
    return {
        "BOTTOM_MARGIN_MULT": vertical,
        "TOP_MARGIN_MULT": vertical,
        "LEFT_MARGIN_MULT": horizontal,
        "RIGHT_MARGIN_MULT": horizontal,
    }


@dataclass(frozen=True)
class Floorplan:
    """A derived floorplan and the arithmetic that produced it."""

    die_side_um: float
    core_side_um: float
    margin_um: float
    target_utilisation: float
    logic_um2: float
    basis: str
    reason: str
    references: Tuple[str, ...] = ()
    # Non-fatal. A utilisation above the demonstrated ceiling is allowed --
    # someone has to run the experiment that moves the ceiling -- but it is
    # never silent.
    warnings: Tuple[str, ...] = ()

    @property
    def die_area_mm2(self) -> float:
        return self.die_side_um ** 2 / 1e6

    def as_librelane(self) -> Dict[str, Any]:
        """The LibreLane keys this floorplan implies.

        Absolute sizing only, so `{TOP,BOTTOM,LEFT,RIGHT}_MARGIN_MULT` are
        deliberately NOT emitted: LibreLane documents them as having no effect
        once `DIE_AREA` and `CORE_AREA` are both set, and shipping an inert
        knob beside the one that governs invites someone to tune the wrong one.
        `margin_multiples()` remains available for the relative-sizing path,
        where those variables are what actually applies.
        """
        d = round(self.die_side_um, 2)
        m = round(self.margin_um, 2)
        return {
            "FP_SIZING": "absolute",
            "DIE_AREA": [0, 0, d, d],
            "CORE_AREA": [m, m, round(d - m, 2), round(d - m, 2)],
        }


def derive_floorplan(
    soc: SocInput,
    *,
    target_utilisation: Optional[float] = None,
    margin_um: float = DEFAULT_MARGIN_UM,
) -> Tuple[Optional[Floorplan], List[str]]:
    """Size a die from the design. Returns ``(floorplan, errors)``.

    `target_utilisation=None` means "pick the densest target this design size
    has been shown to route at" -- see `routability.recommended_utilisation`.
    That is a change of default: it used to be a flat 0.75 regardless of size,
    and a flat default is what put a 4-hart design on a die that spent eleven
    hours failing to route. An explicit value is still honoured, with a warning
    if it exceeds the demonstrated ceiling.
    """
    intent = coerce(soc)
    harts = intent.hart_count
    advice = recommended_utilisation(harts)
    warnings: List[str] = []

    if target_utilisation is None:
        utilisation = advice.utilisation
        warnings.append(f"utilisation {utilisation:.0%}: {advice.reason}")
    else:
        utilisation = float(target_utilisation)
        if utilisation > advice.utilisation:
            warnings.append(
                f"requested utilisation {utilisation:.0%} is above the "
                f"demonstrated {advice.utilisation:.0%} for {harts} harts. "
                f"{advice.reason}. Watch the detailed-routing trajectory")

    if not 0 < utilisation < 1:
        return None, ["target utilisation must be between 0 and 1"]
    if margin_um < 0:
        return None, ["margin must not be negative"]

    estimate = estimate_logic_area(intent)
    logic_um2 = estimate.logic_um2
    if logic_um2 is None:
        return None, [f"cannot size a die: {estimate.reason}"]

    core_um2 = logic_um2 / utilisation
    core_side = core_um2 ** 0.5
    die_side = core_side + 2 * margin_um

    objectives = intent.objectives
    errors: List[str] = []

    # An MPW slot is an input, not an output: Block A is a quarter of a shared
    # 2235 um project area and must match it exactly. Honour the mandate, but
    # still check the cells fit -- a slot the design overflows is the failure
    # this whole module exists to catch early rather than at DPL-0036.
    mandated = objectives.die_um
    if mandated is not None:
        required = die_side
        if required > mandated:
            return None, [
                f"design needs a {required:.1f} um die at "
                f"{utilisation:.0%} utilisation but objectives.die_um "
                f"mandates {mandated}; it does not fit the slot"
            ]
        die_side = float(mandated)
        core_side = die_side - 2 * margin_um
    max_die = objectives.max_die_um
    if max_die is not None and die_side > max_die:
        errors.append(
            f"derived die {die_side:.1f} um exceeds objectives.max_die_um "
            f"{max_die}; the design does not fit the requested slot"
        )
    max_area = objectives.max_area_mm2
    if max_area is not None and die_side ** 2 / 1e6 > max_area:
        errors.append(
            f"derived die {die_side ** 2 / 1e6:.4f} mm2 exceeds "
            f"objectives.max_area_mm2 {max_area}"
        )
    if errors:
        return None, errors

    return Floorplan(
        die_side_um=die_side, core_side_um=core_side, margin_um=margin_um,
        target_utilisation=utilisation, logic_um2=logic_um2,
        basis=estimate.basis, reason=estimate.reason,
        references=estimate.references, warnings=tuple(warnings),
    ), []


def clock_period_ns(soc: SocInput) -> Optional[float]:
    """`CLOCK_PERIOD` from `objectives.target_clock_mhz`, if stated."""
    return coerce(soc).objectives.clock_period_ns
