"""Did the routed netlist actually boot? Signoff does not answer that.

WHY THIS IS PART OF SIGNOFF NOW
-------------------------------
On 2026-08-12 `runs/blocka_reharden` passed every check the flow has: Magic
DRC 0, KLayout DRC 0, LVS 0 with no unmatched nets, XOR 0, antenna 0, routing
DRC 0, disconnected pins 0, power-grid 0, setup +20.94 ns, hold +0.0667 ns.

It does not boot. Gate-level simulation of that netlist never asserts the
flash chip-select and never fetches an instruction. The control -- the
original netlist, same testbench, same firmware, same power-up state --
reaches EXIT SUCCESS in 12 399 cycles.

The reason the flow could not see this is worth stating exactly, because it is
a category error and not an oversight: **LVS proves the layout matches the
netlist. It says nothing about whether the netlist matches the RTL.** Between
RTL and netlist sit synthesis, CTS, resizing and repair, and nothing in this
flow checked that they preserved behaviour. GLS did, and GLS was something you
had to remember to run.

THE THREE-VALUED ANSWER
-----------------------
`NOT_RUN` is a distinct status from `FAIL`, and neither is `PASS`. A signoff
summary that omitted GLS entirely read as though the question had been
answered; one that defaulted it to pass would be worse. The whole point is
that absence of the check is visible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

_PASS = re.compile(r"RESULT:\s*gate-level simulation PASSED")
_EXIT_SUCCESS = re.compile(r"EXIT SUCCESS")
_FAIL = re.compile(r"RESULT:\s*(?:gate-level simulation FAILED|FAIL\b)")
_CYCLES = re.compile(r"after (\d+) cycles")
_NETLIST = re.compile(r"### netlist\s*:\s*(\S+)")


class GlsStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_RUN = "not_run"


@dataclass(frozen=True)
class GlsResult:
    status: GlsStatus
    log: Optional[str] = None
    cycles: Optional[int] = None
    netlist: Optional[str] = None
    reasons: List[str] = None            # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.reasons is None:
            object.__setattr__(self, "reasons", [])

    @property
    def blocks_signoff(self) -> bool:
        """Anything other than a pass does. NOT_RUN is not a pass."""
        return self.status is not GlsStatus.PASS


def parse_gls_log(text: str) -> GlsResult:
    """Read a gate-level run's log.

    The oracle is the log marker, not an exit status: the simulator exits 0
    having printed FAIL, which is why run_gls.sh greps for the marker too.
    """
    reasons: List[str] = []
    cycles = _CYCLES.search(text)
    netlist = _NETLIST.search(text)
    if _PASS.search(text) or (_EXIT_SUCCESS.search(text) and not _FAIL.search(text)):
        status = GlsStatus.PASS
    elif _FAIL.search(text):
        status = GlsStatus.FAIL
        reasons.append(
            "the routed netlist did not reach EXIT SUCCESS. Signoff checks "
            "cannot see this: LVS proves the layout matches the netlist, not "
            "that the netlist matches the RTL")
    else:
        status = GlsStatus.NOT_RUN
        reasons.append("no GLS result marker in the log")
    return GlsResult(status=status,
                     cycles=int(cycles.group(1)) if cycles else None,
                     netlist=netlist.group(1) if netlist else None,
                     reasons=reasons)


def gls_for_run(run_dir: Path, *, repo_root: Path) -> GlsResult:
    """Whether THIS run's netlist has been gate-level simulated.

    Matching is by netlist identity, not by "a GLS log exists": tb/gls writes
    one log in a fixed place, so a stale log from a different run would
    otherwise be read as evidence about this one. That is precisely the
    mistake that made the re-hardened netlist look fine.
    """
    log = repo_root / "tb/gls/sim-gls.log"
    if not log.is_file():
        return GlsResult(GlsStatus.NOT_RUN, reasons=[
            f"no gate-level run recorded at {log}. Run the `gls` flow with "
            f"GLS_RUN={run_dir}"])

    result = parse_gls_log(log.read_text())
    expected = run_dir.name
    # run_gls.sh prints the netlist basename, which is the design name and not
    # the run tag, so fall back to checking the log names this run explicitly.
    text = log.read_text()
    if expected not in text:
        return GlsResult(
            GlsStatus.NOT_RUN, log=str(log), reasons=[
                f"the gate-level log does not mention {expected}, so it is "
                "evidence about a different netlist. Re-run GLS with "
                f"GLS_RUN pointing at this run"])
    return GlsResult(result.status, log=str(log), cycles=result.cycles,
                     netlist=result.netlist, reasons=result.reasons)
