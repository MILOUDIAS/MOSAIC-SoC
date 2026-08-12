"""Signoff evidence read from a real LibreLane run layout.

The directory shapes exercised here are ground truth from
`mattvenn/librelane_summary` (MIT), which reads working LibreLane runs::

    runs/<TAG>/final/metrics.csv
    runs/<TAG>/*-magic-drc/reports/drc_violations.magic.rpt
    runs/<TAG>/*-openroad-stapostpnr/summary.rpt

The properties under test:

- structured metrics beat console scraping;
- a run whose metrics file is missing is not "clean";
- a violation counter we have never heard of still fails the gate;
- a zero metric cannot outvote a report body that holds violations.
"""

import json

import pytest

import harness.skills.flow_runner as fr
from harness.evidence.librelane import (
    adverse_metrics,
    find_latest_run,
    load_metrics,
    load_run,
    locate_reports,
)
from harness.evidence.signoff import parse_signoff
from harness.evidence.status import EvidenceStatus

CLEAN_METRICS = {
    "design__instance__count": "12043",
    "design__die__area": "1050000",
    "magic__drc_error__count": "0",
    "klayout__drc_error__count": "0",
    "design__lvs_error__count": "0",
    "route__antenna_violation__count": "0",
    "timing__setup__ws": "0.42",
    "timing__setup__tns": "0",
}


def _make_run(tmp_path, tag="RUN_2026.07.27_10.00.00", metrics=None, csv=True):
    """Build a LibreLane-shaped run tree and return the runs/ directory."""
    runs = tmp_path / "runs"
    run = runs / tag
    final = run / "final"
    final.mkdir(parents=True)
    data = CLEAN_METRICS if metrics is None else metrics
    if data is not None:
        if csv:
            lines = ["Metric,Value"] + [f"{k},{v}" for k, v in data.items()]
            (final / "metrics.csv").write_text("\n".join(lines) + "\n")
        else:
            (final / "metrics.json").write_text(json.dumps(data))
    return runs, run


def _add_report(run, step, name, body):
    d = run / step / "reports"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body)


# ── run location and metric loading ──────────────────────────────────

def test_finds_the_newest_run(tmp_path):
    runs, first = _make_run(tmp_path, tag="RUN_A")
    import os
    import time
    second = runs / "RUN_B"
    (second / "final").mkdir(parents=True)
    now = time.time()
    os.utime(first, (now - 500, now - 500))
    os.utime(second, (now, now))
    assert find_latest_run(runs) == second


def test_no_runs_directory_yields_none(tmp_path):
    assert find_latest_run(tmp_path / "nope") is None
    assert load_run(tmp_path / "nope") is None


def test_reads_metrics_csv(tmp_path):
    _, run = _make_run(tmp_path)
    metrics, source = load_metrics(run)
    assert metrics["magic__drc_error__count"] == "0"
    assert source.endswith("metrics.csv")


def test_metrics_json_is_preferred_over_csv(tmp_path):
    _, run = _make_run(tmp_path, csv=False)
    metrics, source = load_metrics(run)
    assert source.endswith("metrics.json")
    assert metrics["design__lvs_error__count"] == "0"


def test_locates_step_reports(tmp_path):
    _, run = _make_run(tmp_path)
    _add_report(run, "42-magic-drc", "drc_violations.magic.rpt", "clean\n")
    reports = locate_reports(run)
    assert "magic_drc" in reports
    assert reports["magic_drc"].name == "drc_violations.magic.rpt"


# ── the generic adverse sweep ────────────────────────────────────────

def test_generic_sweep_catches_unknown_violation_keys():
    found = dict(adverse_metrics({
        "some__future_violation__count": "4",
        "another__error__count": 2,
        "design__instance__count": "9999",
        "magic__drc_error__count": "0",
    }))
    assert found == {"some__future_violation__count": 4.0,
                     "another__error__count": 2.0}


def test_generic_sweep_flags_negative_worst_slack():
    assert ("timing__setup__ws", -0.5) in adverse_metrics(
        {"timing__setup__ws": "-0.5"}
    )
    assert adverse_metrics({"timing__setup__ws": "0.5"}) == []


def test_generic_sweep_ignores_non_numeric_values():
    assert adverse_metrics({"some__error__note": "see log"}) == []


# ── verdicts from a run ──────────────────────────────────────────────

def test_clean_run_passes(tmp_path):
    runs, _ = _make_run(tmp_path)
    ev = parse_signoff("", runs_dir=runs)
    assert ev.status is EvidenceStatus.PASS
    assert ev.drc_violations == 0
    assert ev.lvs_match is True
    assert ev.area["design__die__area"] == 1050000


def test_drc_metric_violation_fails(tmp_path):
    metrics = dict(CLEAN_METRICS, magic__drc_error__count="7")
    runs, _ = _make_run(tmp_path, metrics=metrics)
    ev = parse_signoff("", runs_dir=runs)
    assert ev.status is EvidenceStatus.FAIL
    assert ev.drc_violations == 7


def test_zero_metric_cannot_outvote_a_dirty_report(tmp_path):
    """The corroborated-zero rule, against a real report path."""
    runs, run = _make_run(tmp_path)
    _add_report(
        run, "42-magic-drc", "drc_violations.magic.rpt",
        "Violation: minspacing (count: 5) met1 spacing\n",
    )
    ev = parse_signoff("", runs_dir=runs)
    assert ev.status is EvidenceStatus.FAIL
    assert ev.drc_violations == 5
    assert any("report body holds" in r for r in ev.reasons)


def test_lvs_error_metric_fails(tmp_path):
    metrics = dict(CLEAN_METRICS, design__lvs_error__count="3")
    runs, _ = _make_run(tmp_path, metrics=metrics)
    ev = parse_signoff("", runs_dir=runs)
    assert ev.status is EvidenceStatus.FAIL
    assert ev.lvs_match is False


def test_unknown_violation_metric_fails_the_run(tmp_path):
    """A LibreLane upgrade must not be able to blind the gate."""
    metrics = dict(CLEAN_METRICS, librelane__brand_new_violation__count="1")
    runs, _ = _make_run(tmp_path, metrics=metrics)
    ev = parse_signoff("", runs_dir=runs)
    assert ev.status is EvidenceStatus.FAIL
    assert any("brand_new_violation" in v for v in ev.other_violations)


def test_missing_drc_evidence_is_infrastructure_error(tmp_path):
    metrics = {k: v for k, v in CLEAN_METRICS.items() if "drc" not in k}
    runs, _ = _make_run(tmp_path, metrics=metrics)
    ev = parse_signoff("", runs_dir=runs)
    assert ev.status is EvidenceStatus.INFRASTRUCTURE_ERROR
    assert any("DRC was not evaluated" in r for r in ev.reasons)


def test_antenna_only_gates_when_required(tmp_path):
    metrics = dict(CLEAN_METRICS, route__antenna_violation__count="2")
    runs, _ = _make_run(tmp_path, metrics=metrics)
    # The generic sweep still catches it even when not explicitly required,
    # which is the point of the sweep.
    ev = parse_signoff("", runs_dir=runs, require_antenna=True)
    assert ev.status is EvidenceStatus.FAIL
    assert ev.antenna_violations == 2


def test_negative_slack_fails_when_timing_required(tmp_path):
    metrics = dict(CLEAN_METRICS, timing__setup__ws="-0.13")
    runs, _ = _make_run(tmp_path, metrics=metrics)
    ev = parse_signoff("", runs_dir=runs, require_timing=True)
    assert ev.status is EvidenceStatus.FAIL
    assert ev.wns_ns == pytest.approx(-0.13)


def test_skipped_checks_are_reported_not_assumed_clean(tmp_path):
    """`harden-nodrc` skips Magic.DRC/KLayout.DRC/KLayout.Antenna."""
    metrics = {k: v for k, v in CLEAN_METRICS.items() if "drc" not in k}
    runs, _ = _make_run(tmp_path, metrics=metrics)
    ev = parse_signoff("", runs_dir=runs, require_drc=False)
    assert "drc" in ev.checks_skipped
    assert ev.drc_violations is None
    assert ev.status is EvidenceStatus.PASS  # LVS still evaluated and clean


def test_run_without_metrics_falls_back_to_text(tmp_path):
    runs = tmp_path / "runs"
    (runs / "RUN_X" / "final").mkdir(parents=True)
    ev = parse_signoff("DRC count: 0\nCircuits match uniquely.\n", runs_dir=runs)
    assert ev.status is EvidenceStatus.PASS


def test_evidence_records_its_sources(tmp_path):
    runs, run = _make_run(tmp_path)
    _add_report(run, "42-magic-drc", "drc_violations.magic.rpt", "clean\n")
    ev = parse_signoff("", runs_dir=runs)
    assert ev.run_dir == str(run)
    assert "metrics" in ev.sources and "magic_drc" in ev.sources


# ── flow_runner integration ──────────────────────────────────────────

class _Proc:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


def test_harden_flows_point_at_the_librelane_runs_tree():
    for name in ("harden-classic", "harden-chip"):
        assert fr.FLOWS[name]["runs_dir"] == "flow/librelane/runs"
    # harden-classic saves views to final_classic, harden-chip to final
    assert fr.FLOWS["harden-classic"]["report_dir"].endswith("final_classic")
    assert fr.FLOWS["harden-chip"]["report_dir"].endswith("/final")


def test_harden_reads_the_run_tree(tmp_path, monkeypatch):
    metrics = dict(CLEAN_METRICS, magic__drc_error__count="9")
    _make_run(tmp_path / "flow" / "librelane", metrics=metrics)
    monkeypatch.setattr(fr, "run_cmd", lambda *a, **k: _Proc("done\n"))
    runner = fr.FlowRunner(repo_root=tmp_path)
    result = runner.run("harden-classic")
    assert not result.ok
    assert result.details["metrics"]["drc_violations"] == 9
    assert "signoff=FAIL" in result.summary
