"""Shared types, validation, and logging for oh-my-soc skills."""

import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("oh-my-soc")

# ── Repo root ────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[1]


# ── Result types ─────────────────────────────────────────────────────

@dataclass
class SkillResult:
    """Standard return type for all skills."""

    ok: bool
    skill: str
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)


@dataclass
class RunReport:
    """Structured report from an EDA flow run."""

    skill: str
    config: str
    elapsed_s: float
    exit_code: int
    log_path: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# ── Validation helpers ───────────────────────────────────────────────

VALID_CORE_IPS = {"cv32e20", "cv32e40p", "cv32e40px", "cv32e40x",
                  "ibex", "fazyrv", "serv", "qerv"}
VALID_ROLES = {"titan", "atlas", "nano"}
VALID_ISAS = {"rv32i", "rv32e", "rv32em", "rv32emc", "rv32imc", "rv32im"}
VALID_BUS = {"obi", "log", "floonoc"}
VALID_PERIPHERALS = {"uart", "gpio", "timer", "spi", "i2c", "serial_link"}
VALID_SCHED_MODES = {"static", "dynamic", "power-aware"}


def validate_config(cfg: Dict[str, Any]) -> List[str]:
    """Validate a mosaic.yaml-shaped dict. Returns list of errors (empty = valid)."""
    errors = []
    soc = cfg.get("soc")
    if not soc:
        return ["Missing top-level 'soc' key"]

    # cores
    cores = soc.get("cores", [])
    if not cores:
        errors.append("At least one core group required in 'cores'")
    has_titan = False
    for i, c in enumerate(cores):
        ip = c.get("ip", "")
        if ip not in VALID_CORE_IPS:
            errors.append(f"cores[{i}].ip '{ip}' not in {sorted(VALID_CORE_IPS)}")
        role = c.get("role", "")
        if role not in VALID_ROLES:
            errors.append(f"cores[{i}].role '{role}' not in {sorted(VALID_ROLES)}")
        if role == "titan":
            has_titan = True
        count = c.get("count", 1)
        if not isinstance(count, int) or count < 1:
            errors.append(f"cores[{i}].count must be >= 1, got {count}")
        isa = c.get("isa", "rv32i")
        if isa not in VALID_ISAS:
            errors.append(f"cores[{i}].isa '{isa}' not in {sorted(VALID_ISAS)}")
    if not has_titan:
        errors.append("Exactly one core group must have role 'titan'")

    # memory
    mem = soc.get("memory", {})
    sram = mem.get("sram_kb", 32)
    if not isinstance(sram, int) or sram < 4:
        errors.append(f"memory.sram_kb must be >= 4, got {sram}")

    # bus
    bus = soc.get("bus", "obi")
    if bus not in VALID_BUS:
        errors.append(f"bus '{bus}' not in {sorted(VALID_BUS)}")

    # scheduler
    sched = soc.get("scheduler", {})
    mode = sched.get("mode", "static")
    if mode not in VALID_SCHED_MODES:
        errors.append(f"scheduler.mode '{mode}' not in {sorted(VALID_SCHED_MODES)}")

    # peripherals
    for p in soc.get("peripherals", []):
        if p not in VALID_PERIPHERALS:
            errors.append(f"peripheral '{p}' not in {sorted(VALID_PERIPHERALS)}")

    return errors


# ── Process runner ───────────────────────────────────────────────────

def run_cmd(cmd: List[str], cwd: Optional[Path] = None,
            timeout: int = 3600, env: Optional[Dict[str, str]] = None
            ) -> subprocess.CompletedProcess:
    """Run a command, capture output, enforce timeout."""
    log.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd, cwd=cwd or REPO_ROOT, capture_output=True, text=True,
        timeout=timeout, env=env,
    )
    if result.returncode != 0:
        log.warning(f"Command exited {result.returncode}")
    return result


# ── Config I/O ───────────────────────────────────────────────────────

def load_yaml(path: Path) -> Dict[str, Any]:
    """Load a YAML file (uses PyYAML or fallback parser)."""
    import yaml
    with open(path) as f:
        return yaml.safe_load(f)


def dump_yaml(data: Dict[str, Any], path: Path) -> None:
    """Write a YAML file with clean formatting."""
    import yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False,
                  width=120, allow_unicode=True)
    log.info(f"Wrote {path}")


def load_json(path: Path) -> Dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def dump_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    log.info(f"Wrote {path}")
