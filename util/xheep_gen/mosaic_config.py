#!/usr/bin/env python3

"""
mosaic_config.py — MOSAIC-SoC YAML config parser and XHeep loader.

Parses a mosaic.yaml file and produces a multi-core XHeep configuration
object suitable for template rendering by mcu_gen.py.
"""

import yaml
import sys
import logging
import hjson
from pathlib import PurePath
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from jsonref import JsonRef

from xheep import XHeep, BusType, CpuConfig
from cpu.cpu import CPU
from memory_ss.memory_ss import MemorySS

# ──────────────────────────────────────────────
# Data classes for the parsed YAML structure
# ──────────────────────────────────────────────


@dataclass
class CpuGroupConfig:
    """Configuration for a group of identical cores."""

    ip: str  # core IP name (ibex, fazyrv, serv, ...)
    isa: str  # ISA string (rv32i, rv32imc, ...)
    count: int  # number of instances of this core type
    role: str  # tier: titan, atlas, nano
    params: Dict[str, Any] = field(default_factory=dict)  # per-core-type parameters
    hart_id_base: int = 0  # assigned during build()


@dataclass
class MemoryConfig:
    """Memory subsystem configuration."""

    sram_kb: int = 32
    boot_rom_kb: int = 2


@dataclass
class SchedulerConfig:
    """Task Dispatch Unit configuration."""

    tdu: bool = False
    mode: str = "static"  # static | dynamic | power-aware


@dataclass
class MosaicConfig:
    """Top-level parsed mosaic.yaml configuration."""

    soc_name: str = "mosaic_soc"
    pdk: str = "gf180mcu"
    cpu_groups: List[CpuGroupConfig] = field(default_factory=list)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    bus: str = "obi"
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    peripherals: List[str] = field(default_factory=list)

    # Derived fields (set during build())
    total_cores: int = 0
    hart_id_map: Dict[str, List[int]] = field(default_factory=dict)  # ip -> [hart_ids]


# ──────────────────────────────────────────────
# YAML Parsing
# ──────────────────────────────────────────────


def parse_yaml(path: PurePath) -> MosaicConfig:
    """
    Parse a mosaic.yaml file into a MosaicConfig dataclass.

    Args:
        path: Path to the YAML file.

    Returns:
        Filled MosaicConfig instance.

    Raises:
        RuntimeError on validation failures.
    """
    with open(path, "r") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict) or "soc" not in raw:
        raise RuntimeError("mosaic.yaml must contain a top-level 'soc' key")

    soc = raw["soc"]
    cfg = MosaicConfig()

    # ── soc.name ──
    cfg.soc_name = soc.get("name", "mosaic_soc")

    # ── soc.pdk ──
    cfg.pdk = soc.get("pdk", "gf180mcu")

    # ── soc.cores ──
    cores_raw = soc.get("cores", [])
    if not cores_raw:
        raise RuntimeError(
            "mosaic.yaml: at least one core group must be defined in 'cores'"
        )

    for entry in cores_raw:
        ip = entry.get("ip", "").strip().lower()
        if not ip:
            raise RuntimeError(
                "mosaic.yaml: each core entry must have a non-empty 'ip' field"
            )

        isa = entry.get("isa", "rv32i")
        count = entry.get("count", 1)
        if not isinstance(count, int) or count < 1:
            raise RuntimeError(
                f"mosaic.yaml: core '{ip}': 'count' must be an integer >= 1"
            )

        role = entry.get("role", "nano").strip().lower()
        if role not in ("titan", "atlas", "nano"):
            raise RuntimeError(
                f"mosaic.yaml: core '{ip}': 'role' must be one of titan, atlas, nano"
            )

        # Collect per-core-type parameters (everything except standard fields)
        standard_keys = {"ip", "isa", "count", "role"}
        params = {k: v for k, v in entry.items() if k not in standard_keys}

        cfg.cpu_groups.append(
            CpuGroupConfig(ip=ip, isa=isa, count=count, role=role, params=params)
        )

    # ── soc.memory ──
    mem_raw = soc.get("memory", {})
    cfg.memory.sram_kb = mem_raw.get("sram_kb", 32)
    cfg.memory.boot_rom_kb = mem_raw.get("boot_rom_kb", 2)

    # ── soc.bus ──
    cfg.bus = soc.get("bus", "obi").strip().lower()
    if cfg.bus not in ("obi", "axi", "floonoc"):
        raise RuntimeError(f"mosaic.yaml: unsupported bus type '{cfg.bus}'")

    # ── soc.scheduler ──
    sched_raw = soc.get("scheduler", {})
    cfg.scheduler.tdu = sched_raw.get("tdu", False)
    cfg.scheduler.mode = sched_raw.get("mode", "static")

    # ── soc.peripherals ──
    cfg.peripherals = [p.strip().lower() for p in soc.get("peripherals", [])]

    # ── Build derived state ──
    _build_derived(cfg)

    return cfg


def _build_derived(cfg: MosaicConfig):
    """Assign hart IDs and compute derived quantities."""
    hart_id = 0
    for group in cfg.cpu_groups:
        group.hart_id_base = hart_id
        cfg.hart_id_map[group.ip] = list(range(hart_id, hart_id + group.count))
        hart_id += group.count
    cfg.total_cores = hart_id


def load_mosaic_yaml(path: PurePath) -> MosaicConfig:
    """
    Load and parse a mosaic.yaml file. Convenience wrapper around parse_yaml.

    Args:
        path: Path to the YAML file.

    Returns:
        Parsed MosaicConfig.
    """
    cfg = parse_yaml(path)
    logging.info(
        f"[MOSAIC] Loaded config '{cfg.soc_name}' with {cfg.total_cores} total cores"
    )
    for g in cfg.cpu_groups:
        logging.info(
            f"  {g.role:6s}  {g.ip:10s}  x{g.count:2d}  ISA={g.isa}  params={g.params}"
        )
    return cfg


# ──────────────────────────────────────────────
# Conversion: MosaicConfig → XHeep kwargs
# ──────────────────────────────────────────────


RESERVED_MASTER_SLOTS = 2  # DEBUG + error slave

# Cores that are integrated via an SCI wrapper (Wishbone/req-gnt → OBI).
# These use the base CPU class; their per-core parameters are passed to the
# SCI wrapper directly by the cpu_subsystem template.
SCI_CORES = {"fazyrv", "serv", "qerv", "ibex", "cva6"}


def _make_cpu(group: "CpuGroupConfig") -> CPU:
    """Construct the proper CPU subclass for a core group.

    Cores integrated via an SCI wrapper (fazyrv, serv, qerv, ...) use the
    base CPU class since their parameters are consumed by the SCI wrapper in
    the cpu_subsystem template. Native x-heep cores (cv32e20, cv32e40p, ...)
    use their dedicated subclass so that template helpers like ``get_sv_str``
    are available.
    """
    ip = group.ip
    p = group.params
    if ip == "cv32e20":
        from cpu.cv32e20 import cv32e20 as _Cv32e20

        return _Cv32e20(rv32e=p.get("rv32e"), rv32m=p.get("rv32m"))
    if ip == "cv32e40p":
        from cpu.cv32e40p import cv32e40p as _Cv32e40p

        return _Cv32e40p(
            fpu=p.get("fpu"), zfinx=p.get("zfinx"), corev_pulp=p.get("corev_pulp")
        )
    if ip == "cv32e40px":
        from cpu.cv32e40px import cv32e40px as _Cv32e40px

        return _Cv32e40px(
            fpu=p.get("fpu"), zfinx=p.get("zfinx"), corev_pulp=p.get("corev_pulp")
        )
    if ip == "cv32e40x":
        from cpu.cv32e40x import cv32e40x as _Cv32e40x

        return _Cv32e40x()
    # SCI-wrapped cores (fazyrv, serv, qerv, ibex, cva6, ...)
    cpu = CPU(ip)
    for k, v in p.items():
        cpu.set_param(k, v)
    return cpu


def mosaic_to_xheep_kwargs(
    cfg: "MosaicConfig",
    base_config: str = "configs/general.hjson",
    pads_cfg_path: str = "configs/pad_cfg.py",
) -> dict:
    """
    Convert a MosaicConfig into the kwargs dict expected by mcu_gen.py's
    write_template().

    This reuses the standard x-heep configuration flow (``load_config``) to
    build the memory subsystem, peripheral domains, DMA, power manager and
    interrupts from a base HJSON file (default ``configs/general.hjson``).
    The multi-core CPU topology from ``mosaic.yaml`` is then overlaid on top
    of that base system. This avoids reimplementing the peripheral/memory
    infrastructure while keeping the single declarative ``mosaic.yaml`` as
    the source of truth for the core topology, scheduler and peripherals.

    Args:
        cfg: Parsed mosaic configuration.
        base_config: Path to the base x-heep HJSON config used for the
            peripheral/memory/interrupt infrastructure.
        pads_cfg_path: Path to the pad configuration Python file.

    Returns:
        kwargs dict suitable for write_template(**kwargs).
    """
    import load_config

    # ── 1. Load the base x-heep system from HJSON ──
    # This builds memory (banks + linker sections), peripheral domains
    # (base/AO + user), DMA, power manager and the single-core CPU declared
    # in the HJSON. We then override the CPU topology with the multi-core
    # groups from mosaic.yaml below.
    base_path = _resolve_repo_path(base_config)
    system = load_config.load_cfg_file(base_path)

    # Read the raw HJSON to extract the standard template kwargs fields
    # (debug, ext_slaves, flash_mem, linker_script, interrupts) exactly as
    # mcu_gen.py does for the standard flow.
    with open(base_path, "r") as file:
        config = hjson.loads(file.read(), use_decimal=True)
        config = JsonRef.replace_refs(config)

    # ── 2. Overlay multi-core CPU topology from mosaic.yaml ──
    cpu_groups = []
    for group in cfg.cpu_groups:
        cpu = _make_cpu(group)
        cpu_groups.append(
            CpuConfig(
                cpu=cpu,
                role=group.role,
                isa=group.isa,
                count=group.count,
                hart_id_base=group.hart_id_base,
                params=group.params,
            )
        )
    system.set_cpus(cpu_groups)

    # If the base HJSON CPU differs from the mosaic TITAN core, keep the
    # _cpu slot consistent with the first mosaic group (the TITAN).
    # set_cpus() already does this, so nothing more is needed here.

    # ── 3. Bus type ──
    bus_type_map = {"obi": BusType.NtoM, "axi": BusType.NtoM, "floonoc": BusType.NtoM}
    system.set_bus_type(bus_type_map.get(cfg.bus, BusType.NtoM))

    # ── 4. Pad ring ──
    pad_path = _resolve_repo_path(pads_cfg_path)
    try:
        pad_ring = load_config.load_pad_cfg(pad_path, system)
        system.set_padring(pad_ring)
    except Exception as e:
        logging.warning(f"[MOSAIC] Could not load pad config: {e}")
        from pads.pad_ring import PadRing

        system.set_padring(PadRing())

    # ── 5. Register the mosaic config as an extension so templates that
    #        need it (e.g. TDU, multi-core scheduling) can access it. ──
    system.add_extension("mosaic_cfg", cfg)
    system.add_extension("tdu_enabled", cfg.scheduler.tdu)
    system.add_extension("sched_mode", cfg.scheduler.mode)

    # ── 6. Build and validate ──
    system.build()
    system.validate()

    # ── 7. Extract standard kwargs fields from the base HJSON ──
    debug_start_address = _string2int(config["debug"]["address"])
    debug_size_address = _string2int(config["debug"]["length"])
    has_spi_slave = 1 if config["debug"].get("has_spi_slave") == "yes" else 0
    ext_slave_start_address = _string2int(config["ext_slaves"]["address"])
    ext_slave_size_address = _string2int(config["ext_slaves"]["length"])
    flash_mem_start_address = _string2int(config["flash_mem"]["address"])
    flash_mem_size_address = _string2int(config["flash_mem"]["length"])
    stack_size = _string2int(config["linker_script"]["stack_size"])
    heap_size = _string2int(config["linker_script"]["heap_size"])

    plic_used_n_interrupts = len(config["interrupts"]["list"])
    plit_n_interrupts = config["interrupts"]["number"]
    ext_int_list = {
        f"EXT_INTR_{k}": v
        for k, v in enumerate(range(plic_used_n_interrupts, plit_n_interrupts))
    }
    interrupts = {**config["interrupts"]["list"], **ext_int_list}

    if (
        int(stack_size, 16) + int(heap_size, 16)
    ) > system.memory_ss().ram_size_address():
        raise RuntimeError("[MOSAIC] stack + heap exceeds RAM size of the base config")

    # ── 8. Render kwargs (matching mcu_gen.py's generate_xheep output) ──
    kwargs = {
        "xheep": system,
        "debug_start_address": debug_start_address,
        "debug_size_address": debug_size_address,
        "has_spi_slave": has_spi_slave,
        "ext_slave_start_address": ext_slave_start_address,
        "ext_slave_size_address": ext_slave_size_address,
        "flash_mem_start_address": flash_mem_start_address,
        "flash_mem_size_address": flash_mem_size_address,
        "stack_size": stack_size,
        "heap_size": heap_size,
        "plic_used_n_interrupts": plic_used_n_interrupts,
        "plit_n_interrupts": plit_n_interrupts,
        "interrupts": interrupts,
        # MOSAIC multi-core additions
        "mosaic_cfg": cfg,
        "num_harts": system.num_harts(),
        "is_multi_core": system.is_multi_core(),
    }

    return kwargs


def _string2int(hex_json_string) -> str:
    """Extract the hex value from an hjson string like '0x10000000'."""
    s = str(hex_json_string)
    return (s.split("x")[1]).split(",")[0]


def _resolve_repo_path(path: str) -> PurePath:
    """Resolve a path that may be relative to the repository root.

    The Makefile invokes mcu_gen.py from the repo root, but the script can
    also be run directly from ``util/xheep_gen/``. This helper tries the
    given path as-is first (cwd-relative), then falls back to resolving it
    against the repository root (two levels above this file).
    """
    from pathlib import Path

    p = Path(path)
    if p.exists():
        return PurePath(str(p.resolve()))
    repo_root = Path(__file__).resolve().parents[2]
    p2 = repo_root / path
    if p2.exists():
        return PurePath(str(p2))
    # Return the original (will produce a clear FileNotFoundError downstream)
    return PurePath(path)


# ──────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <mosaic.yaml>")
        sys.exit(1)

    cfg = load_mosaic_yaml(PurePath(sys.argv[1]))
    print(f"Config: {cfg}")
    for g in cfg.cpu_groups:
        print(
            f"  {g.role:6s}  {g.ip:10s}  x{g.count:2d}  hart_ids={cfg.hart_id_map[g.ip]}"
        )
