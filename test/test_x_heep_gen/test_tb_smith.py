"""tb-smith tests: generated artifacts, marker parsing, and (slow) a real
single-hart TB run for picorv32.

Run from the repo root: python3 -m pytest test/test_x_heep_gen/test_tb_smith.py
"""

import pathlib
import shutil
import sys

import pytest

directory = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(directory))

from harness.skills.tb_smith import TbSmith  # noqa: E402

REPO_ROOT = directory


@pytest.mark.parametrize(
    "core", ["../escape", "foo/bar", "/tmp/escape", ".", "..", "bad-core"]
)
def test_tb_smith_rejects_noncanonical_core_before_path_io(tmp_path, core):
    ts = TbSmith(tmp_path)
    assert not ts.generate(core).ok
    assert not ts.run(core).ok
    assert not ts.wake_demo(core, execute=False).ok


def test_generate_serv_artifacts():
    ts = TbSmith(REPO_ROOT)
    result = ts.generate("serv")
    assert result.ok, result.errors
    d = pathlib.Path(result.details["dir"])
    assert (d / "tb_serv_sci.sv").exists()
    assert (d / "run.sh").exists()
    assert (d / "deps.f").exists()
    run_sh = (d / "run.sh").read_text()
    # the pinned-Verilator block and the SHARED memory model must be present
    assert "VERILATOR_PIN" in run_sh
    assert "tb/mosaic/tb_obi_mem.sv" in run_sh
    tb = (d / "tb_serv_sci.sv").read_text()
    assert "serv_sci dut" in tb
    assert "TB PASS" in tb and "TB FAIL" in tb
    # serv is unified: single memory
    assert "u_mem (" in tb and "u_dmem" not in tb


def test_generate_split_core():
    ts = TbSmith(REPO_ROOT)
    result = ts.generate("fazyrv")
    assert result.ok
    tb = (pathlib.Path(result.details["dir"]) / "tb_fazyrv_sci.sv").read_text()
    assert "u_imem" in tb and "u_dmem" in tb


def test_generate_unknown_wrapper_fails():
    ts = TbSmith(REPO_ROOT)
    result = ts.generate("nonexistentcore")
    assert not result.ok
    assert "wrapper-smith scaffold first" in result.summary


def test_run_marker_parsing(monkeypatch, tmp_path):
    ts = TbSmith(REPO_ROOT)

    class _P:
        returncode = 0
        stdout = "TB PASS instr_reqs=3 data_reqs=4 cycles=250"
        stderr = ""

    import harness.skills.tb_smith as mod

    monkeypatch.setattr(mod, "run_cmd", lambda *a, **k: _P())
    # needs the script to exist
    (REPO_ROOT / "tb/sci/serv/run.sh").exists() or ts.generate("serv")
    result = ts.run("serv")
    assert result.ok
    assert result.details["metrics"] == {
        "pass": True,
        "reason": None,
        "instr_reqs": 3,
        "data_reqs": 4,
        "cycles": 250,
    }


def test_run_fail_reason(monkeypatch):
    ts = TbSmith(REPO_ROOT)

    class _P:
        returncode = 0
        stdout = (
            "TB FAIL reason=dormancy_bus_activity instr_reqs=9 data_reqs=0 cycles=205"
        )
        stderr = ""

    import harness.skills.tb_smith as mod

    monkeypatch.setattr(mod, "run_cmd", lambda *a, **k: _P())
    result = ts.run("serv")
    assert not result.ok
    assert "dormancy_bus_activity" in result.summary


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("verilator") is None, reason="no verilator")
def test_real_run_picorv32():
    ts = TbSmith(REPO_ROOT)
    assert ts.generate("picorv32").ok
    result = ts.run("picorv32")
    assert result.ok, result.details.get("stderr_tail", "")
    assert result.details["metrics"]["pass"] is True
    assert result.details["metrics"]["data_reqs"] > 0
