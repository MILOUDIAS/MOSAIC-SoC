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
import copy
from pathlib import PurePath
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from jsonref import JsonRef

from xheep import XHeep, BusType, CpuConfig
from cpu.cpu import CPU
from memory_ss.memory_ss import MemorySS

try:
    from .core_registry import (
        CORE_SPECS,
        SCI_CORES,
        resolved_capabilities,
        VALID_BUS,
        VALID_TARGETS,
        expanded_user_peripherals,
        validate_soc_config,
    )
except ImportError:  # mcu_gen adds util/xheep_gen directly to sys.path
    from core_registry import (
        CORE_SPECS,
        SCI_CORES,
        resolved_capabilities,
        VALID_BUS,
        VALID_TARGETS,
        expanded_user_peripherals,
        validate_soc_config,
    )

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

    @property
    def mode_value(self) -> int:
        """SystemVerilog ``sched_mode_e`` encoding."""

        return {"static": 0, "dynamic": 1, "power-aware": 2}[self.mode]


@dataclass(frozen=True)
class HartConfig:
    """Resolved per-hart topology entry consumed by templates and software."""

    hart_id: int
    group_index: int
    group_instance: int
    ip: str
    isa: str
    role: str
    params: Dict[str, Any]


@dataclass
class MosaicConfig:
    """Top-level parsed mosaic.yaml configuration."""

    soc_name: str = "mosaic_soc"
    pdk: str = "gf180mcu"
    profile: str = "soc"
    target: str = "rtl"
    cpu_groups: List[CpuGroupConfig] = field(default_factory=list)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    bus: str = "obi"
    bus_opts: Dict[str, Any] = field(default_factory=dict)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    peripherals: List[str] = field(default_factory=list)

    # Derived fields (set during build())
    total_cores: int = 0
    hart_id_map: Dict[str, List[int]] = field(default_factory=dict)  # ip -> [hart_ids]
    harts: List[HartConfig] = field(default_factory=list)


# ──────────────────────────────────────────────
# Bus fabric options
# ──────────────────────────────────────────────

VALID_BUS_TYPES = tuple(sorted(VALID_BUS))
VALID_TARGET_TYPES = tuple(sorted(VALID_TARGETS))

# Per-fabric option defaults. Every key a fabric supports must appear here —
# unknown keys in mosaic.yaml are rejected so typos can't silently no-op.
DEFAULT_BUS_OPTS: Dict[str, Dict[str, Any]] = {
    "log": {
        "topology": "lic",  # current tcdm backend topology
        "num_banks": "auto",  # auto = next_pow2(number of bus masters)
    },
    "floonoc": {
        "route_algo": "ID",  # compact topology uses one ID-table router
        "endpoints": "compact",  # compact = nh+1 managers / 2 subordinates
    },
}

VALID_LOG_TOPOLOGIES = ("lic",)
VALID_FLOONOC_ROUTE_ALGOS = ("ID",)


def _parse_bus_opts(raw: Any, bus: str) -> Dict[str, Any]:
    """Merge user bus_opts over the per-fabric defaults and validate them."""
    opts = {fabric: dict(defaults) for fabric, defaults in DEFAULT_BUS_OPTS.items()}

    if raw in (None, {}):
        return opts
    if not isinstance(raw, dict):
        raise RuntimeError("mosaic.yaml: 'bus_opts' must be a mapping")

    for fabric, fabric_raw in raw.items():
        if fabric not in DEFAULT_BUS_OPTS:
            raise RuntimeError(
                f"mosaic.yaml: bus_opts.{fabric}: unknown fabric "
                f"(valid: {', '.join(sorted(DEFAULT_BUS_OPTS))})"
            )
        if not isinstance(fabric_raw, dict):
            raise RuntimeError(f"mosaic.yaml: bus_opts.{fabric} must be a mapping")
        for key, value in fabric_raw.items():
            if key not in DEFAULT_BUS_OPTS[fabric]:
                raise RuntimeError(
                    f"mosaic.yaml: bus_opts.{fabric}.{key}: unknown option "
                    f"(valid: {', '.join(sorted(DEFAULT_BUS_OPTS[fabric]))})"
                )
            opts[fabric][key] = value

    topo = str(opts["log"]["topology"]).strip().lower()
    if topo not in VALID_LOG_TOPOLOGIES:
        raise RuntimeError(
            f"mosaic.yaml: bus_opts.log.topology '{topo}' invalid "
            f"(valid: {', '.join(VALID_LOG_TOPOLOGIES)})"
        )
    opts["log"]["topology"] = topo

    nb = opts["log"]["num_banks"]
    if nb != "auto" and (not isinstance(nb, int) or nb < 1):
        raise RuntimeError(
            "mosaic.yaml: bus_opts.log.num_banks must be 'auto' or an integer >= 1"
        )

    algo = str(opts["floonoc"]["route_algo"]).strip().upper()
    if algo not in VALID_FLOONOC_ROUTE_ALGOS:
        raise RuntimeError(
            f"mosaic.yaml: bus_opts.floonoc.route_algo '{algo}' invalid "
            f"(valid: {', '.join(VALID_FLOONOC_ROUTE_ALGOS)})"
        )
    opts["floonoc"]["route_algo"] = algo

    return opts


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

    # Retain the long-standing actionable migration error for the historical
    # `axi` spelling before applying the shared strict schema.
    raw_soc = raw.get("soc") if isinstance(raw, dict) else None
    raw_bus = raw_soc.get("bus") if isinstance(raw_soc, dict) else None
    if raw_bus == "axi":
        raise RuntimeError(
            "mosaic.yaml: bus 'axi' was never a distinct fabric; use 'obi' "
            "(OBI crossbar), 'log' (logarithmic interconnect), or 'floonoc' "
            "(FlooNoC AXI NoC)"
        )
    if isinstance(raw_bus, str) and raw_bus not in VALID_BUS_TYPES:
        raise RuntimeError(
            f"mosaic.yaml: unsupported bus type '{raw_bus}' "
            f"(valid: {', '.join(VALID_BUS_TYPES)})"
        )
    errors = validate_soc_config(raw)
    if errors:
        raise RuntimeError("mosaic.yaml:\n  - " + "\n  - ".join(errors))

    soc = raw["soc"]
    cfg = MosaicConfig()

    # ── soc.name ──
    cfg.soc_name = soc.get("name", "mosaic_soc")

    # ── soc.pdk ──
    cfg.pdk = soc.get("pdk", "gf180mcu")

    # ── soc.profile ──
    cfg.profile = soc.get("profile", "soc")

    # ── soc.target ──
    # `rtl` preserves the broad generator design space.  `tapeout` is accepted
    # only after core_registry's strict physical capability matrix passes.
    cfg.target = soc.get("target", "rtl")

    # ── soc.cores ──
    cores_raw = soc.get("cores", [])
    if not cores_raw:
        raise RuntimeError(
            "mosaic.yaml: at least one core group must be defined in 'cores'"
        )

    for entry in cores_raw:
        ip = entry["ip"]
        isa = entry["isa"]
        count = entry.get("count", 1)
        role = entry["role"]

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
    cfg.bus = soc.get("bus", "obi")
    if cfg.bus not in VALID_BUS_TYPES:
        raise RuntimeError(
            f"mosaic.yaml: unsupported bus type '{cfg.bus}' "
            f"(valid: {', '.join(sorted(VALID_BUS_TYPES))})"
        )

    # ── soc.bus_opts ──
    cfg.bus_opts = _parse_bus_opts(soc.get("bus_opts", {}), cfg.bus)

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
    cfg.hart_id_map.clear()
    cfg.harts.clear()
    for group_index, group in enumerate(cfg.cpu_groups):
        group.hart_id_base = hart_id
        group_harts = list(range(hart_id, hart_id + group.count))
        cfg.hart_id_map.setdefault(group.ip, []).extend(group_harts)
        for group_instance, resolved_hart_id in enumerate(group_harts):
            cfg.harts.append(
                HartConfig(
                    hart_id=resolved_hart_id,
                    group_index=group_index,
                    group_instance=group_instance,
                    ip=group.ip,
                    isa=group.isa,
                    role=group.role,
                    params=copy.deepcopy(group.params),
                )
            )
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

        # ISA is the public contract. Derive native core parameters when the
        # YAML does not provide an implementation choice, rather than building
        # RV32I hardware for a declared rv32emc software ABI.
        rv32e = p.get("rv32e", group.isa.startswith("rv32e"))
        isa_ext = group.isa[4:]
        rv32m = p.get("rv32m", "RV32MFast" if "m" in isa_ext else "RV32MNone")
        return _Cv32e20(rv32e=rv32e, rv32m=rv32m)
    if ip == "cv32e40p":
        from cpu.cv32e40p import cv32e40p as _Cv32e40p

        return _Cv32e40p(
            fpu=p.get("fpu"),
            fpu_addmul_lat=p.get("fpu_addmul_lat"),
            fpu_others_lat=p.get("fpu_others_lat"),
            zfinx=p.get("zfinx"),
            corev_pulp=p.get("corev_pulp"),
            num_mhpmcounters=p.get("num_mhpmcounters"),
        )
    if ip == "cv32e40px":
        from cpu.cv32e40px import cv32e40px as _Cv32e40px

        return _Cv32e40px(
            fpu=p.get("fpu"),
            fpu_addmul_lat=p.get("fpu_addmul_lat"),
            fpu_others_lat=p.get("fpu_others_lat"),
            zfinx=p.get("zfinx"),
            corev_pulp=p.get("corev_pulp"),
            num_mhpmcounters=p.get("num_mhpmcounters"),
        )
    if ip == "cv32e40x":
        from cpu.cv32e40x import cv32e40x as _Cv32e40x

        return _Cv32e40x(num_mhpmcounters=p.get("num_mhpmcounters"))
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

    # ── 1. Resolve the base x-heep HJSON from mosaic.yaml ──
    # The base file supplies register offsets and platform-service defaults;
    # RAM, boot ROM, and optional user peripherals are rewritten before the
    # XHeep object is constructed.  This makes mosaic.yaml authoritative for
    # every bus fabric rather than leaving the general.hjson defaults active.
    base_path = _resolve_repo_path(base_config)
    with open(base_path, "r") as file:
        config = hjson.loads(file.read(), use_decimal=True)
        config = JsonRef.replace_refs(config)
    config = _resolve_base_config(config, cfg)
    system = load_config.load_cfg_hjson(hjson.dumps(config))

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
    bus_type_map = {
        "obi": BusType.NtoM,
        "log": BusType.LOG,
        "floonoc": BusType.FLOONOC,
    }
    system.set_bus_type(bus_type_map.get(cfg.bus, BusType.NtoM))

    # ── 3b. LOG bus memory override ──
    # The logarithmic interconnect interleaves the whole banked pool, so the
    # base-config RAM layout is replaced by a single interleaved group sized
    # to the fabric (banks >= bus masters, power of two).
    if cfg.bus == "log":
        _override_memory_for_log(system, cfg)

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
    system.add_extension("soc_name", cfg.soc_name)
    system.add_extension("pdk", cfg.pdk)
    system.add_extension("soc_profile", cfg.profile)
    system.add_extension("implementation_target", cfg.target)
    system.add_extension("tdu_enabled", cfg.scheduler.tdu)
    system.add_extension("sched_mode", cfg.scheduler.mode)
    system.add_extension("sched_mode_value", cfg.scheduler.mode_value)
    system.add_extension("resolved_harts", tuple(cfg.harts))
    system.add_extension("hart_id_map", copy.deepcopy(cfg.hart_id_map))
    debug_hart_mask = 0
    interrupt_hart_mask = 0
    for hart in cfg.harts:
        capabilities = resolved_capabilities(hart.ip, hart.params)
        if "debug" in capabilities:
            debug_hart_mask |= 1 << hart.hart_id
        if "interrupts" in capabilities:
            interrupt_hart_mask |= 1 << hart.hart_id
    system.add_extension("debug_hart_mask", debug_hart_mask)
    system.add_extension("interrupt_hart_mask", interrupt_hart_mask)
    system.add_extension("bus_opts", cfg.bus_opts or _parse_bus_opts({}, cfg.bus))

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


def _resolve_base_config(config: dict, cfg: "MosaicConfig") -> dict:
    """Apply authoritative mosaic.yaml memory/peripheral choices to HJSON.

    The fixed base HJSON remains useful as an address/register catalog.  It is
    not allowed to override public mosaic.yaml fields, so this function
    produces the concrete HJSON consumed by ``load_cfg_hjson``.
    """

    config = copy.deepcopy(config)
    sram_kb = cfg.memory.sram_kb
    # MemorySS supports at most 16 banks and requires power-of-two bank sizes.
    # Split larger memories into 32 KiB banks; smaller memories use one bank.
    bank_size_kb = min(32, sram_kb)
    bank_sizes = [bank_size_kb] * (sram_kb // bank_size_kb)
    config["ram_banks"] = {"code_and_data": {"sizes": bank_sizes}}

    code_size = min(0xE800, sram_kb * 1024 // 2)
    config["linker_sections"] = [
        {"name": "code", "start": 0, "size": code_size},
        {"name": "data", "start": code_size},
    ]

    bootrom = config["ao_peripherals"]["bootrom"]
    bootrom["length"] = f"0x{cfg.memory.boot_rom_kb * 1024:08x}"

    selected = expanded_user_peripherals(
        cfg.peripherals, multicore=cfg.total_cores > 1
    )
    for name, peripheral in config["peripherals"].items():
        if name in {"address", "length"}:
            continue
        peripheral["is_included"] = "yes" if name in selected else "no"

    return config


def _override_memory_for_log(system: XHeep, cfg: "MosaicConfig"):
    """Rebuild the RAM as one interleaved group for the LOG bus.

    The tcdm_interconnect computes the bank select from the low address bits
    for every access, so the entire SRAM must be a single word-interleaved
    group with banks >= bus masters (see XHeep._validate_log_bus). Bank count
    comes from bus_opts.log.num_banks ('auto' = next power of two above the
    master count); the total size stays memory.sram_kb.
    """
    from memory_ss.memory_ss import MemorySS
    from memory_ss.linker_section import LinkerSection

    n_masters = system.num_bus_masters()
    num_banks = cfg.bus_opts.get("log", {}).get("num_banks", "auto")
    if num_banks == "auto":
        num_banks = 1 << (n_masters - 1).bit_length()  # next power of two

    sram_kb = cfg.memory.sram_kb
    if sram_kb % num_banks != 0 or sram_kb // num_banks < 1:
        raise RuntimeError(
            f"mosaic.yaml: bus 'log' with {num_banks} banks needs "
            f"memory.sram_kb divisible by the bank count with >= 1 KB per "
            f"bank, got sram_kb={sram_kb}. This config has {n_masters} bus "
            f"masters (auto bank count: {1 << (n_masters - 1).bit_length()})."
        )
    bank_kb = sram_kb // num_banks

    mem = MemorySS()
    mem.add_ram_banks_il(num_banks, bank_kb)
    # Same code/data split as general.hjson (code capped to half the RAM for
    # small memories); the data section end is inferred by build().
    code_size = min(0xE800, sram_kb * 1024 // 2)
    mem.add_linker_section(LinkerSection("code", 0, code_size))
    mem.add_linker_section(LinkerSection("data", code_size, None))
    system.set_memory_ss(mem)
    logging.info(
        f"[MOSAIC] bus 'log': RAM rebuilt as {num_banks} interleaved banks "
        f"x {bank_kb} KB ({n_masters} bus masters)"
    )


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
