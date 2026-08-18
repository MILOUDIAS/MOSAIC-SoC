"""Workload power: a second STA pass over a finished run, with real activity.

Hardening is hours; this is minutes. It has to be separate because the
activity comes from simulating the ROUTED NETLIST, and that netlist is the
output of the run being analysed.

The comparison is the deliverable. The same netlist, parasitics and corner are
reported twice -- once with OpenSTA's default toggle model, which is what every
run in this project has silently been reporting, and once with activity read
from a gate-level VCD. Printing both is the point: a single number would just
replace one unlabelled figure with another.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_TOTAL = re.compile(
    r"^Total\s+([\d.e+-]+)\s+([\d.e+-]+)\s+([\d.e+-]+)\s+([\d.e+-]+)", re.M)
_SECTION = re.compile(r"^=== (DEFAULT ACTIVITY|WORKLOAD ACTIVITY)", re.M)


@dataclass(frozen=True)
class PowerBreakdown:
    internal_w: float
    switching_w: float
    leakage_w: float
    total_w: float

    @property
    def switching_fraction(self) -> float:
        """The tell. Default activity leaves this near zero on this design:
        combinational switching was 0.5% of total, clock and sequential 99.5%.
        """
        return self.switching_w / self.total_w if self.total_w else 0.0


def parse_power_report(text: str) -> Dict[str, PowerBreakdown]:
    """`{"default": ..., "workload": ...}` from the two-pass script's output."""
    out: Dict[str, PowerBreakdown] = {}
    sections = list(_SECTION.finditer(text))
    for index, marker in enumerate(sections):
        end = sections[index + 1].start() if index + 1 < len(sections) else len(text)
        body = text[marker.end():end]
        total = _TOTAL.search(body)
        if not total:
            continue
        key = "default" if "DEFAULT" in marker.group(1) else "workload"
        out[key] = PowerBreakdown(
            internal_w=float(total.group(1)), switching_w=float(total.group(2)),
            leakage_w=float(total.group(3)), total_w=float(total.group(4)))
    return out


def normalise_vcd(source: Path, target: Path) -> Tuple[int, List[str]]:
    """Strip what OpenSTA's VCD reader cannot parse. Returns (lines, notes).

    OpenSTA rejects `$dumpon` outright -- `[ERROR STA-0800] unknown vcd
    command` -- and `$dumpoff` is followed by every signal going to x, which
    would be read as activity if it were kept. The gate-level bench now defers
    `$dumpvars` to the start of the ROI so no `$dumpon` is ever emitted, but
    the trailing `$dumpoff` still has to go, and older traces have both.
    """
    notes: List[str] = []
    written = 0
    with source.open() as fin, target.open("w") as fout:
        for line in fin:
            stripped = line.strip()
            if stripped == "$dumpoff":
                notes.append("truncated at $dumpoff (end of the ROI)")
                break
            if stripped == "$dumpon":
                notes.append("dropped a $dumpon marker OpenSTA cannot parse")
                continue
            fout.write(line)
            written += 1
    return written, notes


def locate_artifacts(run_dir: Path, corner: str = "nom") -> Tuple[Dict[str, Path], List[str]]:
    """The netlist, parasitics and constraints a standalone STA needs."""
    final = run_dir / "final"
    problems: List[str] = []
    found: Dict[str, Path] = {}

    # The ODB, not the netlist: OpenROAD's read_spef annotates the database and
    # needs the technology loaded, so a bare netlist gives "ORD-2010 no
    # technology has been read". The ODB carries tech, netlist and placement
    # together -- the state the numbers should describe.
    odb = sorted(final.glob("odb/*.odb"))
    if odb:
        found["odb"] = odb[0]
    else:
        problems.append(f"no ODB under {final}/odb")

    spef = sorted(final.glob(f"spef/{corner}/*.spef"))
    if spef:
        found["spef"] = spef[0]
    else:
        # Not fatal: without parasitics the switching estimate is optimistic,
        # and saying so beats refusing to run.
        problems.append(f"no {corner} SPEF; switching power will be understated")

    sdc = sorted(final.glob("sdc/*.sdc"))
    if sdc:
        found["sdc"] = sdc[0]
    else:
        problems.append(f"no SDC under {final}/sdc")
    return found, problems


def liberty_files(run_dir: Path) -> List[Path]:
    """The liberty the run itself resolved, read from its own config."""
    import json

    resolved = run_dir / "resolved.json"
    if not resolved.is_file():
        return []
    config = json.loads(resolved.read_text())
    libs: List[Path] = []
    for value in config.get("LIB", {}).values() if isinstance(
            config.get("LIB"), dict) else []:
        for entry in (value if isinstance(value, list) else [value]):
            path = Path(str(entry))
            if path.is_file():
                libs.append(path)
    return libs


def run_power_analysis(
    run_dir: Path, *, repo_root: Path, vcd: Optional[Path] = None,
    vcd_scope: str = "gls_tb/dut", corner: str = "nom",
    design: Optional[str] = None, timeout: int = 1800,
) -> Tuple[Optional[Dict[str, PowerBreakdown]], List[str]]:
    """Report power with and without workload activity."""
    from harness.evidence.librelane import load_design_name

    artifacts, problems = locate_artifacts(run_dir, corner)
    if "odb" not in artifacts or "sdc" not in artifacts:
        return None, problems

    libs = liberty_files(run_dir)
    if not libs:
        return None, problems + [
            f"no liberty files resolvable from {run_dir}/resolved.json"]

    design = design or load_design_name(run_dir)
    if not design:
        return None, problems + ["cannot determine DESIGN_NAME for link_design"]

    script = repo_root / "flow/librelane/scripts/power_from_activity.tcl"
    env = {
        "MOSAIC_ODB": str(artifacts["odb"]),
        "MOSAIC_SDC": str(artifacts["sdc"]),
        "MOSAIC_LIBS": " ".join(str(p) for p in libs),
        "MOSAIC_DESIGN": design,
    }
    if "spef" in artifacts:
        env["MOSAIC_SPEF"] = str(artifacts["spef"])
    if vcd is not None:
        if not vcd.is_file():
            return None, problems + [f"no such VCD: {vcd}"]
        cleaned = vcd.with_suffix(".sta.vcd")
        _, notes = normalise_vcd(vcd, cleaned)
        problems.extend(notes)
        env["MOSAIC_VCD"] = str(cleaned)
        env["MOSAIC_VCD_SCOPE"] = vcd_scope

    import os

    completed = subprocess.run(
        ["nix", "develop", "--command", "openroad", "-no_init", "-exit",
         str(script)],
        cwd=str(repo_root / "flow/librelane"),
        env={**os.environ, **env},
        capture_output=True, text=True, timeout=timeout)
    parsed = parse_power_report(completed.stdout)
    if not parsed:
        return None, problems + [
            "openroad produced no parsable power report",
            (completed.stderr or completed.stdout)[-600:]]
    return parsed, problems
