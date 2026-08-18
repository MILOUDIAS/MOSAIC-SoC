"""Structural netlist diff, and the reading it exists to prevent.

`blocka_reharden` has 714 fewer instances than `blocka_signoff`. That was
reported -- twice, by me -- as "logic was removed", which turned a boot failure
into a hunt for an optimisation bug. It is fill being displaced by the buffers
the slew fix added, on a die that cannot grow. The classification here makes
the tool say that rather than the reader guess it.
"""

import pytest

from harness.physical.netlist import NetlistSummary, classify, diff

def have_najaeda() -> bool:
    try:
        import najaeda  # noqa: F401
        return True
    except ImportError:
        return False


# ── classification: order matters ────────────────────────────────────

@pytest.mark.parametrize("cell,kind", [
    ("gf180mcu_fd_sc_mcu7t5v0__fillcap_8", "fill"),
    ("gf180mcu_fd_sc_mcu7t5v0__fill_1", "fill"),
    ("gf180mcu_fd_sc_mcu7t5v0__clkbuf_3", "clock"),
    ("gf180mcu_fd_sc_mcu7t5v0__buf_2", "buffer"),
    ("gf180mcu_fd_sc_mcu7t5v0__dlyb_1", "delay"),
    ("gf180mcu_fd_sc_mcu7t5v0__dffq_1", "sequential"),
    ("gf180mcu_fd_sc_mcu7t5v0__tap", "physical"),
    ("gf180mcu_fd_sc_mcu7t5v0__nand2_1", "logic"),
    ("gf180mcu_fd_sc_mcu7t5v0__aoi21_2", "logic"),
])
def test_cells_land_in_the_right_bucket(cell, kind):
    assert classify(cell) == kind


def test_the_specific_orderings_that_would_misbucket():
    """`fillcap` contains `fill`, and `clkbuf` contains `buf`.

    Either test performed in the wrong order sends ~1,400 cells into the wrong
    bucket, which is exactly enough to invert the verdict.
    """
    assert classify("x__fillcap_4") == "fill"
    assert classify("x__clkbuf_1") == "clock"
    assert classify("x__buf_1") == "buffer"


# ── the verdict ──────────────────────────────────────────────────────

def summary(name, cells, flops=()):
    return NetlistSummary(path=name, top="t", instances=sum(cells.values()),
                          cells=dict(cells), flops=sorted(flops))


def test_fill_displaced_by_buffers_is_not_a_logic_change():
    """The real shape of blocka_signoff -> blocka_reharden."""
    a = summary("a", {"x__fill_1": 2000, "x__buf_2": 100, "x__nand2_1": 500})
    b = summary("b", {"x__fill_1": 45, "x__buf_2": 1135, "x__nand2_1": 500})
    report = diff(a, b)
    assert report["instances"]["delta"] == -920   # -1955 fill + 1035 buf
    assert report["logic_changed"] is False
    assert report["by_kind"]["fill"] == -1955
    assert report["by_kind"]["buffer"] == 1035


def test_actual_logic_removal_is_reported_as_such():
    a = summary("a", {"x__nand2_1": 500, "x__fill_1": 100})
    b = summary("b", {"x__nand2_1": 450, "x__fill_1": 100})
    report = diff(a, b)
    assert report["logic_changed"] is True
    assert report["by_kind"]["logic"] == -50


def test_a_changed_flop_set_is_flagged():
    """The power-up init deposits into flops BY NAME.

    A changed flop set silently disables it, and a gate-level run then fails
    for a reason that has nothing to do with the netlist being wrong.
    """
    a = summary("a", {"x__dffq_1": 2}, flops=["u1", "u2"])
    b = summary("b", {"x__dffq_1": 2}, flops=["u1", "u3"])
    report = diff(a, b)
    assert report["flops"]["identical_names"] is False
    assert report["flops"]["only_in_a"] == 1 and report["flops"]["only_in_b"] == 1


def test_identical_netlists_diff_to_nothing():
    a = summary("a", {"x__nand2_1": 10}, flops=["u1"])
    report = diff(a, summary("b", {"x__nand2_1": 10}, flops=["u1"]))
    assert report["instances"]["delta"] == 0
    assert report["logic_changed"] is False
    assert report["top_cell_changes"] == {}
    assert report["flops"]["identical_names"] is True


def test_a_cell_type_that_disappeared_is_named():
    a = summary("a", {"x__dlya_2": 5, "x__nand2_1": 1})
    b = summary("b", {"x__nand2_1": 1})
    report = diff(a, b)
    assert report["cell_types_only_in_a"] == ["x__dlya_2"]
    assert report["cell_types_only_in_b"] == []


# ── against the real netlists ────────────────────────────────────────

def test_the_real_block_a_pair_shows_no_logic_change():
    """The finding, asserted: the 714-cell drop is fill, not logic."""
    from harness.core import REPO_ROOT
    from harness.physical.netlist import load_summary, summarise_run

    if not have_najaeda():
        # najaeda is optional and PEP 668 blocks installing it into the system
        # interpreter, so this skips under a bare `python3 -m pytest`. Its
        # assertions were verified to hold on 2026-08-12 under
        # `.venv/bin/python`; run the suite from the venv to exercise it.
        pytest.skip("najaeda not installed -- run under .venv/bin/python")
    runs = REPO_ROOT / "flow/librelane/experimental/runs"
    a_dir, b_dir = runs / "blocka_signoff", runs / "blocka_reharden"
    if not (a_dir / "final" / "nl").is_dir() or not (b_dir / "final" / "nl").is_dir():
        pytest.skip("run trees not present")

    summaries = []
    for run in (a_dir, b_dir):
        netlist_path, libs = summarise_run(run)
        assert netlist_path is not None
        summaries.append(load_summary(netlist_path, libs))
    report = diff(*summaries)

    assert report["instances"]["delta"] == -714
    assert report["logic_changed"] is False, report["by_kind"]
    assert report["by_kind"]["fill"] < -1900
    assert report["by_kind"]["buffer"] > 1000
    # And the flop set is unchanged, so the power-up init is not the cause of
    # the gate-level boot failure.
    assert report["flops"]["identical_names"] is True
    assert report["flops"]["a"] == 5587
