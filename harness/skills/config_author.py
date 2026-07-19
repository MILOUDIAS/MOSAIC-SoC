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
        "target": "rtl",
        "cores": [],
        "memory": {"sram_kb": 32, "boot_rom_kb": 2},
        "bus": "obi",
        "scheduler": {"tdu": False, "mode": "static"},
        "peripherals": [],
    }
}

# Core type → default ISA and per-core params.
# ONLY parameters proven by shipped configs belong here: every non-standard
# key flows verbatim into group.params and must match what the generator's
# CPU classes / SCI template branches expect (e.g. cv32e20 rv32m is an ENUM
# STRING like "RV32MFast" — a bare True crashes mcu_gen; leave such knobs to
# explicit user configs).
# `sim_only` is harness METADATA (documentation + tapeout-preset guards); it is
# stripped before the YAML is written so mcu_gen never sees it.
CORE_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "cv32e20":  {"isa": "rv32emc"},
    "cv32e40p": {"isa": "rv32imc"},
    "cv32e40px": {"isa": "rv32imc"},
    "cv32e40x": {"isa": "rv32imc"},
    "ibex":     {"isa": "rv32imc"},
    "fazyrv":   {"isa": "rv32i", "chunksize": 8},
    "serv":     {"isa": "rv32i"},
    "qerv":     {"isa": "rv32i"},
    "picorv32": {"isa": "rv32i"},
    "snitch":   {"isa": "rv32i"},   # RV32I: acc port tied off (RVM needs snitch_shared_muldiv)
    "cva6":     {"isa": "rv32imc", "sim_only": True},
    "rocket":   {"isa": "rv64imc", "sim_only": True},
    "boom":     {"isa": "rv64imc", "sim_only": True},
}

# Metadata keys stripped from core entries before YAML emission.
_META_KEYS = {"sim_only"}

# Presets: common SoC configurations
PRESETS: Dict[str, Dict[str, Any]] = {
    "poc": {
        "soc": {
            "name": "mosaic_poc_alpha",
            "pdk": "gf180mcu",
            "target": "tapeout",
            "cores": [
                {"ip": "cv32e20", "isa": "rv32emc", "count": 1, "role": "titan"},
                {"ip": "fazyrv", "isa": "rv32i", "chunksize": 8, "count": 2, "role": "atlas", "boot_addr": 0x1000},
                {"ip": "serv", "isa": "rv32i", "count": 4, "role": "nano", "boot_addr": 0x2000},
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
            "target": "rtl",
            "cores": [
                {"ip": "cv32e20", "isa": "rv32emc", "count": 1, "role": "titan"},
                {"ip": "serv", "isa": "rv32i", "count": 1, "role": "nano", "boot_addr": 0x800},
            ],
            "memory": {"sram_kb": 8, "boot_rom_kb": 1},
            "bus": "obi",
            "scheduler": {"tdu": True, "mode": "static"},
            "peripherals": ["uart"],
        }
    },
    "max_cores": {
        "soc": {
            "name": "mosaic_max_cores",
            "pdk": "gf180mcu",
            "target": "rtl",
            "cores": [
                {"ip": "cv32e20", "isa": "rv32emc", "count": 1, "role": "titan"},
                {"ip": "ibex", "isa": "rv32imc", "count": 1, "role": "atlas", "boot_addr": 0x1000},
                {"ip": "fazyrv", "isa": "rv32i", "chunksize": 8, "count": 2, "role": "atlas", "boot_addr": 0x2000},
                {"ip": "qerv", "isa": "rv32i", "count": 2, "role": "nano", "boot_addr": 0x3000},
                {"ip": "serv", "isa": "rv32i", "count": 4, "role": "nano", "boot_addr": 0x4000},
            ],
            "memory": {"sram_kb": 64, "boot_rom_kb": 2},
            "bus": "obi",
            "scheduler": {"tdu": True, "mode": "power-aware"},
            "peripherals": ["uart", "gpio", "timer", "spi"],
        }
    },
    # SIM-ONLY presets (cva6/rocket/boom are excluded from the GF180 tapeout)
    "sim_zoo": {
        "soc": {
            "name": "mosaic_sim_zoo",
            "pdk": "gf180mcu",
            "profile": "testbench",
            "target": "simulation",
            "cores": [
                {"ip": "cva6", "isa": "rv32imc", "count": 1, "role": "titan"},
                {"ip": "snitch", "isa": "rv32i", "count": 1, "role": "atlas",
                 "boot_addr": 0x1000},
                {"ip": "picorv32", "isa": "rv32i", "count": 1, "role": "nano",
                 "boot_addr": 0x2000},
            ],
            "memory": {"sram_kb": 32, "boot_rom_kb": 2},
            "bus": "obi",
            "scheduler": {"tdu": True, "mode": "dynamic"},
            "peripherals": ["uart", "gpio", "timer", "spi"],
        }
    },
    "berkeley": {
        "soc": {
            "name": "mosaic_berkeley_preset",
            "pdk": "gf180mcu",
            "profile": "testbench",
            "target": "simulation",
            "cores": [
                {"ip": "cv32e20", "isa": "rv32emc", "count": 1, "role": "titan"},
                {"ip": "rocket", "isa": "rv64imc", "count": 1, "role": "atlas",
                 "boot_addr": 0x1000},
                {"ip": "boom", "isa": "rv64imc", "count": 1, "role": "nano",
                 "boot_addr": 0x2000},
            ],
            "memory": {"sram_kb": 32, "boot_rom_kb": 2},
            "bus": "obi",
            "scheduler": {"tdu": True, "mode": "dynamic"},
            "peripherals": ["uart", "gpio", "timer", "spi"],
        }
    },
}

# Only the canonical 32-KiB GF180/OBI PoC is within the currently qualified
# implementation matrix.  The other presets remain useful RTL generators.
TAPEOUT_PRESETS = {"poc"}


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
        target: str = "rtl",
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
            target: Implementation intent (rtl/simulation/tapeout).
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
                    "target": target,
                    "cores": [],
                    "memory": {"sram_kb": sram_kb, "boot_rom_kb": boot_rom_kb},
                    "bus": bus,
                    "scheduler": {"tdu": tdu, "mode": sched_mode},
                    "peripherals": peripherals or [],
                }
            }

            # Fill core defaults
            next_worker_boot = 0x1000
            used_worker_boots = set()
            for core in cores:
                if core.get("role") == "titan" or "boot_addr" not in core:
                    continue
                try:
                    address = (
                        int(core["boot_addr"], 0)
                        if isinstance(core["boot_addr"], str)
                        else core["boot_addr"]
                    )
                except (TypeError, ValueError):
                    continue  # authoritative validation reports the bad field
                used_worker_boots.add(address)
            has_sim_only = False
            for c in cores:
                core_entry = dict(c)
                ip = core_entry.get("ip", "")
                if ip in CORE_DEFAULTS:
                    defaults = CORE_DEFAULTS[ip]
                    has_sim_only |= bool(defaults.get("sim_only", False))
                    for k, v in defaults.items():
                        if k not in core_entry:
                            core_entry[k] = v
                if (
                    ip in {"rocket", "boom"}
                    and core_entry.get("role") == "titan"
                    and "boot_addr" not in core_entry
                ):
                    core_entry["boot_addr"] = 0x180
                # A production AMP worker is reset-held until its image is
                # dispatched.  Give every authored worker *group* a distinct,
                # explicit SRAM image slot unless the caller chose one.  Harts
                # within a group intentionally share that image.
                if (
                    core_entry.get("role") != "titan"
                    and "boot_addr" not in core_entry
                ):
                    while next_worker_boot in used_worker_boots:
                        next_worker_boot += 0x1000
                    core_entry["boot_addr"] = next_worker_boot
                    used_worker_boots.add(next_worker_boot)
                    next_worker_boot += 0x1000
                cfg["soc"]["cores"].append(core_entry)

            # Cores whose wrappers are qualified only by the simulation
            # harness must never silently turn an otherwise ordinary authored
            # config into a tapeout claim.
            if has_sim_only:
                cfg["soc"]["profile"] = "testbench"
                cfg["soc"]["target"] = "simulation"

            # Worker harts are reset-held until dispatched, so an AMP design
            # cannot function without the TDU.  Treat it as mandatory platform
            # infrastructure when authoring instead of emitting a dead SoC.
            if any(c.get("role") != "titan" for c in cfg["soc"]["cores"]):
                cfg["soc"]["scheduler"]["tdu"] = True

        # Strip harness-only metadata (mcu_gen must never see it)
        for c in cfg["soc"]["cores"]:
            for k in _META_KEYS:
                c.pop(k, None)

        # Validate (tapeout presets must stay free of sim-only cores)
        allow_sim_only = preset not in TAPEOUT_PRESETS if preset else True
        errors = validate_config(cfg, allow_sim_only=allow_sim_only)
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
                "target": cfg["soc"].get("target", "rtl"),
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

    def wake_demo_config(self, core: str,
                         output_path: Optional[Path] = None) -> SkillResult:
        """Emit the canonical 3-hart TDU wake-demo config for a worker core.

        Shape (programmatic clone of configs/mosaic_picorv32.yaml): 1x cv32e20
        TITAN + 2x <core> workers at boot_addr 0x1000/0x2000, 32 KB SRAM,
        bus obi, TDU dynamic — so tb/mosaic_soc/run.sh, the demo firmware and
        the linker script are reused unchanged. Used by tb-smith wake-demo.
        """
        if core not in VALID_CORE_IPS:
            return SkillResult(
                ok=False, skill="config-author",
                summary=f"Unknown core '{core}'",
                errors=[f"Available cores: {sorted(VALID_CORE_IPS)}"],
            )
        isa = CORE_DEFAULTS.get(core, {}).get("isa", "rv32i")
        cores = [
            {"ip": "cv32e20", "isa": "rv32emc", "count": 1, "role": "titan"},
            {"ip": core, "isa": isa, "count": 1, "role": "atlas",
             "boot_addr": 0x1000},
            {"ip": core, "isa": isa, "count": 1, "role": "nano",
             "boot_addr": 0x2000},
        ]
        return self.generate(
            name=f"mosaic_{core}",
            cores=cores,
            sram_kb=32,
            boot_rom_kb=2,
            bus="obi",
            tdu=True,
            sched_mode="dynamic",
            peripherals=["uart", "gpio", "timer", "spi"],
            output_path=output_path,
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
                "target": soc.get("target", "rtl"),
            }
        return SkillResult(
            ok=True, skill="config-author",
            summary=f"{len(PRESETS)} presets available",
            details={"presets": summaries},
        )
