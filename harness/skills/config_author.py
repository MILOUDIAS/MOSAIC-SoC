"""config-author skill — translate intent into valid mosaic.yaml.

The agent provides structured parameters (cores, memory, peripherals, etc.)
and this skill validates, fills defaults, and writes a correct mosaic.yaml.

Design principle: the agent *describes* what it wants; the skill *ensures*
the output is valid and generation-ready. Deterministic validation, not LLM
guesswork.
"""

import copy
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core import (
    SkillResult, REPO_ROOT, validate_config, dump_yaml,
    VALID_CORE_IPS, VALID_ROLES, VALID_ISAS, VALID_BUS,
    VALID_PERIPHERALS, VALID_SCHED_MODES, log,
)

# ── Defaults ─────────────────────────────────────────────────────────

DEFAULT_CONFIG: Dict[str, Any] = {
    "soc": {
        "name": "mosaic_soc",
        "pdk": "gf180mcu",
        "cores": [],
        "memory": {"sram_kb": 32, "boot_rom_kb": 2},
        "bus": "obi",
        "scheduler": {"tdu": False, "mode": "static"},
        "peripherals": [],
    }
}

# Core type → default ISA and per-core params
CORE_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "cv32e20":  {"isa": "rv32emc", "rv32e": True, "rv32m": True},
    "cv32e40p": {"isa": "rv32imc", "fpu": False, "zfinx": False, "corev_pulp": False},
    "cv32e40px": {"isa": "rv32imc"},
    "cv32e40x": {"isa": "rv32imc"},
    "ibex":     {"isa": "rv32imc"},
    "fazyrv":   {"isa": "rv32i", "chunksize": 8},
    "serv":     {"isa": "rv32i"},
    "qerv":     {"isa": "rv32i"},
}

# Presets: common SoC configurations
PRESETS: Dict[str, Dict[str, Any]] = {
    "poc": {
        "soc": {
            "name": "mosaic_poc_alpha",
            "pdk": "gf180mcu",
            "cores": [
                {"ip": "cv32e20", "isa": "rv32emc", "count": 1, "role": "titan"},
                {"ip": "fazyrv", "isa": "rv32i", "chunksize": 8, "count": 2, "role": "atlas"},
                {"ip": "serv", "isa": "rv32i", "count": 4, "role": "nano"},
            ],
            "memory": {"sram_kb": 32, "boot_rom_kb": 2},
            "bus": "obi",
            "scheduler": {"tdu": True, "mode": "dynamic"},
            "peripherals": ["uart", "gpio", "timer", "spi"],
        }
    },
    "minimal": {
        "soc": {
            "name": "mosaic_minimal",
            "pdk": "gf180mcu",
            "cores": [
                {"ip": "cv32e20", "isa": "rv32emc", "count": 1, "role": "titan"},
                {"ip": "serv", "isa": "rv32i", "count": 1, "role": "nano"},
            ],
            "memory": {"sram_kb": 8, "boot_rom_kb": 1},
            "bus": "obi",
            "scheduler": {"tdu": False, "mode": "static"},
            "peripherals": ["uart"],
        }
    },
    "max_cores": {
        "soc": {
            "name": "mosaic_max_cores",
            "pdk": "gf180mcu",
            "cores": [
                {"ip": "cv32e20", "isa": "rv32emc", "count": 1, "role": "titan"},
                {"ip": "ibex", "isa": "rv32imc", "count": 1, "role": "atlas"},
                {"ip": "fazyrv", "isa": "rv32i", "chunksize": 8, "count": 2, "role": "atlas"},
                {"ip": "qerv", "isa": "rv32i", "count": 2, "role": "nano"},
                {"ip": "serv", "isa": "rv32i", "count": 4, "role": "nano"},
            ],
            "memory": {"sram_kb": 64, "boot_rom_kb": 2},
            "bus": "obi",
            "scheduler": {"tdu": True, "mode": "power-aware"},
            "peripherals": ["uart", "gpio", "timer", "spi"],
        }
    },
}


class ConfigAuthor:
    """Skill: generate a valid mosaic.yaml from structured parameters.

    Usage:
        author = ConfigAuthor()
        result = author.generate(
            name="my_soc",
            cores=[
                {"ip": "cv32e20", "count": 1, "role": "titan"},
                {"ip": "serv", "count": 4, "role": "nano"},
            ],
            sram_kb=32,
            peripherals=["uart", "gpio"],
        )
        # result.ok == True, result.details["path"] = path to written YAML
    """

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or REPO_ROOT

    def generate(
        self,
        name: str = "mosaic_soc",
        cores: Optional[List[Dict[str, Any]]] = None,
        sram_kb: int = 32,
        boot_rom_kb: int = 2,
        bus: str = "obi",
        tdu: bool = False,
        sched_mode: str = "static",
        peripherals: Optional[List[str]] = None,
        pdk: str = "gf180mcu",
        preset: Optional[str] = None,
        output_path: Optional[Path] = None,
    ) -> SkillResult:
        """Generate a mosaic.yaml from parameters.

        Args:
            name: SoC name.
            cores: List of core dicts with at least 'ip', 'count', 'role'.
            sram_kb: SRAM size in KB.
            boot_rom_kb: Boot ROM size in KB.
            bus: Bus type (obi/log/floonoc).
            tdu: Enable Task Dispatch Unit.
            sched_mode: Scheduling mode (static/dynamic/power-aware).
            peripherals: List of peripheral names.
            pdk: Target PDK.
            preset: Use a named preset instead of manual params.
            output_path: Where to write the YAML. Default: configs/<name>.yaml.

        Returns:
            SkillResult with validation status and output path.
        """
        # Start from preset if specified
        if preset:
            if preset not in PRESETS:
                return SkillResult(
                    ok=False, skill="config-author",
                    summary=f"Unknown preset '{preset}'",
                    errors=[f"Available presets: {sorted(PRESETS.keys())}"],
                )
            cfg = copy.deepcopy(PRESETS[preset])
            cfg["soc"]["name"] = name
        else:
            # Build from parameters
            if not cores:
                return SkillResult(
                    ok=False, skill="config-author",
                    summary="No cores specified",
                    errors=["At least one core group is required"],
                )

            cfg = {
                "soc": {
                    "name": name,
                    "pdk": pdk,
                    "cores": [],
                    "memory": {"sram_kb": sram_kb, "boot_rom_kb": boot_rom_kb},
                    "bus": bus,
                    "scheduler": {"tdu": tdu, "mode": sched_mode},
                    "peripherals": peripherals or [],
                }
            }

            # Fill core defaults
            for c in cores:
                core_entry = dict(c)
                ip = core_entry.get("ip", "")
                if ip in CORE_DEFAULTS:
                    defaults = CORE_DEFAULTS[ip]
                    for k, v in defaults.items():
                        if k not in core_entry:
                            core_entry[k] = v
                cfg["soc"]["cores"].append(core_entry)

        # Validate
        errors = validate_config(cfg)
        if errors:
            return SkillResult(
                ok=False, skill="config-author",
                summary=f"Config validation failed with {len(errors)} error(s)",
                errors=errors,
            )

        # Write
        if output_path is None:
            output_path = self.repo_root / "configs" / f"{name}.yaml"

        dump_yaml(cfg, output_path)

        return SkillResult(
            ok=True, skill="config-author",
            summary=f"Generated valid config '{name}' -> {output_path}",
            details={
                "path": str(output_path),
                "config": cfg,
                "core_count": sum(c.get("count", 1) for c in cfg["soc"]["cores"]),
                "peripheral_count": len(cfg["soc"]["peripherals"]),
            },
        )

    def validate_file(self, path: Path) -> SkillResult:
        """Validate an existing mosaic.yaml file."""
        try:
            from ..core import load_yaml
            cfg = load_yaml(path)
        except Exception as e:
            return SkillResult(
                ok=False, skill="config-author",
                summary=f"Failed to parse {path}: {e}",
                errors=[str(e)],
            )

        errors = validate_config(cfg)
        if errors:
            return SkillResult(
                ok=False, skill="config-author",
                summary=f"{path.name} has {len(errors)} validation error(s)",
                errors=errors,
            )

        soc = cfg["soc"]
        total_cores = sum(c.get("count", 1) for c in soc.get("cores", []))
        return SkillResult(
            ok=True, skill="config-author",
            summary=f"{path.name} is valid ({total_cores} cores, {len(soc.get('peripherals', []))} peripherals)",
            details={"config": cfg, "total_cores": total_cores},
        )

    def list_presets(self) -> SkillResult:
        """List available preset configurations."""
        summaries = {}
        for pname, pcfg in PRESETS.items():
            soc = pcfg["soc"]
            cores_desc = ", ".join(
                f"{c.get('count', 1)}x {c['ip']}" for c in soc["cores"]
            )
            summaries[pname] = {
                "description": f"{soc['name']}: {cores_desc}",
                "sram_kb": soc["memory"]["sram_kb"],
                "tdu": soc["scheduler"]["tdu"],
            }
        return SkillResult(
            ok=True, skill="config-author",
            summary=f"{len(PRESETS)} presets available",
            details={"presets": summaries},
        )
