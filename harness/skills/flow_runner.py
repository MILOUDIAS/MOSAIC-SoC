"""flow-runner skill — invoke EDA flows and summarize results.

Wraps make targets (mosaic-gen, verilator-build, librelane harden, etc.)
with structured logging, timing, and result parsing. The agent calls this
skill instead of shelling out directly — giving it structured reports
instead of raw stdout.

Design principle: deterministic execution + structured output. The agent
decides *what* to run; the skill ensures it runs correctly and captures
everything.
"""

import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core import (
    SkillResult, RunReport, REPO_ROOT, run_cmd, load_yaml, log,
)

# ── Flow definitions ─────────────────────────────────────────────────

FLOWS: Dict[str, Dict[str, Any]] = {
    "mosaic-gen": {
        "cmd": ["make", "mosaic-gen"],
        "description": "Generate multi-core SoC RTL from mosaic.yaml",
        "timeout": 300,
        "outputs": ["hw/core-v-mini-mcu/core_v_mini_mcu.sv"],
    },
    "mosaic-gen-config": {
        "cmd_prefix": ["make", "mosaic-gen", "MOSAIC_CFG="],
        "description": "Generate SoC RTL from a specific config",
        "timeout": 300,
    },
    "verilator-lint": {
        "cmd": ["make", "verilator-build"],
        "description": "Build Verilator model (includes lint)",
        "timeout": 600,
    },
    "verilator-run": {
        "cmd": ["make", "verilator-run"],
        "description": "Run Verilator simulation",
        "timeout": 300,
    },
    "tb-multicore": {
        "cmd": ["bash", "tb/mosaic/run.sh"],
        "description": "Multi-core SCI wake-loop test",
        "timeout": 300,
    },
    "tb-tdu": {
        "cmd": ["bash", "tb/tdu/soc/cocotb/run.sh"],
        "description": "TDU SoC-level cocotb test",
        "timeout": 300,
    },
    "tb-idma": {
        "cmd": ["bash", "tb/idma/cocotb/run.sh"],
        "description": "iDMA cocotb test",
        "timeout": 300,
    },
    "harden-classic": {
        "cmd": ["make", "classic"],
        "cwd": "flow/librelane",
        "description": "LibreLane classic flow (SoC core only)",
        "timeout": 7200,
    },
    "harden-chip": {
        "cmd": ["make", "harden", "SLOT=mosaic"],
        "cwd": "flow/librelane",
        "description": "LibreLane chip flow (full chip + pad ring)",
        "timeout": 14400,
    },
    "firmware-build": {
        "cmd": ["make"],
        "cwd": "sw/firmware",
        "description": "Build firmware (TITAN + workers)",
        "timeout": 60,
    },
    "firmware-demo": {
        "cmd": ["make", "demo"],
        "cwd": "sw/firmware",
        "description": "Build scheduling demo firmware",
        "timeout": 60,
    },
}


# ── Log parsers ──────────────────────────────────────────────────────

def _parse_verilator_lint(output: str) -> Dict[str, Any]:
    """Extract lint warnings/errors from Verilator output."""
    warnings = []
    errors = []
    for line in output.splitlines():
        if "%Warning" in line:
            warnings.append(line.strip())
        elif "%Error" in line:
            errors.append(line.strip())
    return {"warnings": warnings, "errors": errors,
            "warning_count": len(warnings), "error_count": len(errors)}


def _parse_make_output(output: str) -> Dict[str, Any]:
    """Extract timing and status from make output."""
    metrics: Dict[str, Any] = {}
    # Look for real time
    m = re.search(r"real\s+(\d+)m(\d+\.\d+)s", output)
    if m:
        metrics["wall_time_s"] = int(m.group(1)) * 60 + float(m.group(2))
    # Look for size info
    for line in output.splitlines():
        if "text" in line and "data" in line and "bss" in line:
            # Size output line
            parts = line.split()
            if len(parts) >= 5:
                metrics["text_bytes"] = parts[0]
                metrics["data_bytes"] = parts[1]
                metrics["bss_bytes"] = parts[2]
    return metrics


def _parse_cocotb_result(output: str) -> Dict[str, Any]:
    """Extract PASS/FAIL from cocotb output."""
    result: Dict[str, Any] = {}
    m = re.search(r"TESTS=(\d+)\s+PASS=(\d+)\s+FAIL=(\d+)", output)
    if m:
        result["tests"] = int(m.group(1))
        result["pass"] = int(m.group(2))
        result["fail"] = int(m.group(3))
        result["all_pass"] = result["fail"] == 0
    # Check for EXIT SUCCESS
    if "EXIT SUCCESS" in output:
        result["exit_success"] = True
    elif "EXIT FAILURE" in output:
        result["exit_success"] = False
    return result


# ── FlowRunner ───────────────────────────────────────────────────────

class FlowRunner:
    """Skill: run EDA flows with structured reporting.

    Usage:
        runner = FlowRunner()
        result = runner.run("mosaic-gen")
        result = runner.run("mosaic-gen-config", config="configs/mosaic_sim.yaml")
        result = runner.run("tb-multicore")
    """

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or REPO_ROOT
        self.reports: List[RunReport] = []

    def list_flows(self) -> SkillResult:
        """List all available flows."""
        flows = {}
        for name, spec in FLOWS.items():
            flows[name] = {
                "description": spec["description"],
                "timeout": spec["timeout"],
                "cwd": spec.get("cwd", "."),
            }
        return SkillResult(
            ok=True, skill="flow-runner",
            summary=f"{len(FLOWS)} flows available",
            details={"flows": flows},
        )

    def run(
        self,
        flow_name: str,
        config: Optional[str] = None,
        extra_args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> SkillResult:
        """Run an EDA flow by name.

        Args:
            flow_name: Name of the flow (key in FLOWS dict).
            config: Optional config path for mosaic-gen-config.
            extra_args: Additional command-line arguments.
            env: Additional environment variables.

        Returns:
            SkillResult with timing, metrics, and parsed log output.
        """
        if flow_name not in FLOWS:
            return SkillResult(
                ok=False, skill="flow-runner",
                summary=f"Unknown flow '{flow_name}'",
                errors=[f"Available flows: {sorted(FLOWS.keys())}"],
            )

        spec = FLOWS[flow_name]
        cmd = list(spec["cmd"])

        # Handle config override
        if config and flow_name == "mosaic-gen-config":
            cmd[-1] = f"MOSAIC_CFG={config}"
        elif config:
            cmd.extend(["MOSAIC_CFG=", config])

        if extra_args:
            cmd.extend(extra_args)

        cwd = self.repo_root / spec["cwd"] if spec.get("cwd") else self.repo_root
        timeout = spec["timeout"]

        start = time.monotonic()
        try:
            proc = run_cmd(cmd, cwd=cwd, timeout=timeout, env=env)
            elapsed = time.monotonic() - start
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start
            return SkillResult(
                ok=False, skill="flow-runner",
                summary=f"Flow '{flow_name}' timed out after {timeout}s",
                details={"timeout": timeout},
            )
        except Exception as e:
            elapsed = time.monotonic() - start
            return SkillResult(
                ok=False, skill="flow-runner",
                summary=f"Flow '{flow_name}' failed: {e}",
                errors=[str(e)],
            )

        # Build report
        combined_output = proc.stdout + "\n" + proc.stderr

        # Parse flow-specific output
        metrics: Dict[str, Any] = {}
        warnings: List[str] = []
        errors: List[str] = []

        if "verilator" in flow_name:
            parsed = _parse_verilator_lint(combined_output)
            warnings = parsed["warnings"]
            errors = parsed["errors"]
            metrics.update(parsed)
        elif "tb-" in flow_name or "harden" in flow_name:
            metrics.update(_parse_cocotb_result(combined_output))

        metrics.update(_parse_make_output(combined_output))

        report = RunReport(
            skill="flow-runner",
            config=flow_name,
            elapsed_s=elapsed,
            exit_code=proc.returncode,
            metrics=metrics,
            warnings=warnings,
            errors=errors,
        )
        self.reports.append(report)

        ok = proc.returncode == 0
        summary_parts = [f"Flow '{flow_name}' {'PASS' if ok else 'FAIL'}"]
        summary_parts.append(f"({elapsed:.1f}s, exit={proc.returncode})")
        if metrics.get("all_pass"):
            summary_parts.append("tests=all_pass")
        if errors:
            summary_parts.append(f"{len(errors)} errors")

        return SkillResult(
            ok=ok, skill="flow-runner",
            summary=" ".join(summary_parts),
            details={
                "exit_code": proc.returncode,
                "elapsed_s": round(elapsed, 2),
                "metrics": metrics,
                "stdout_tail": proc.stdout[-2000:] if proc.stdout else "",
                "stderr_tail": proc.stderr[-2000:] if proc.stderr else "",
            },
            errors=errors,
        )

    def run_all(self, flow_names: List[str], **kwargs) -> SkillResult:
        """Run multiple flows in sequence. Stops on first failure."""
        results = []
        for name in flow_names:
            r = self.run(name, **kwargs)
            results.append(r)
            if not r.ok:
                return SkillResult(
                    ok=False, skill="flow-runner",
                    summary=f"Sequence stopped at '{name}': {r.summary}",
                    details={"results": [rr.to_json() for rr in results]},
                    errors=r.errors,
                )
        return SkillResult(
            ok=True, skill="flow-runner",
            summary=f"All {len(flow_names)} flows passed",
            details={"results": [r.to_json() for r in results]},
        )

    def get_latest_report(self) -> Optional[RunReport]:
        return self.reports[-1] if self.reports else None
