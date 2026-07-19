"""Authoritative MOSAIC core capabilities and configuration validation.

This module deliberately has no x-heep imports.  It is shared by the RTL
generator and the agent harness, so a configuration accepted by one path is
accepted by the other path with exactly the same semantics.
"""

from dataclasses import dataclass, field
import re
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Tuple, Type


@dataclass(frozen=True)
class ParamSpec:
    """Type and range contract for one core-specific YAML parameter."""

    types: Tuple[Type[Any], ...]
    choices: Optional[FrozenSet[Any]] = None
    minimum: Optional[int] = None
    maximum: Optional[int] = None
    address: bool = False

    def validate(self, path: str, value: Any) -> Optional[str]:
        if self.address:
            try:
                parsed = value if type(value) is int else int(value, 0)
            except (TypeError, ValueError):
                return f"{path} must be an integer or base-prefixed integer string"
            if parsed < 0 or parsed > 0xFFFFFFFF:
                return f"{path} must be in the 32-bit address range"
            if parsed & 0x3:
                return f"{path} must be 4-byte aligned"
            return None

        # Exact types are intentional: bool is a subclass of int in Python,
        # but accepting `true` for a counter or bank count is a schema bug.
        if type(value) not in self.types:
            expected = " or ".join(t.__name__ for t in self.types)
            return f"{path} must be {expected}, got {type(value).__name__}"
        if self.choices is not None and value not in self.choices:
            return f"{path} must be one of {sorted(self.choices, key=str)}, got {value!r}"
        if self.minimum is not None and value < self.minimum:
            return f"{path} must be >= {self.minimum}, got {value}"
        if self.maximum is not None and value > self.maximum:
            return f"{path} must be <= {self.maximum}, got {value}"
        return None


BOOL = ParamSpec((bool,))
BOOL_BIT = ParamSpec((bool, int), choices=frozenset({False, True, 0, 1}))
NONNEG_INT = ParamSpec((int,), minimum=0)
MHPM_COUNTERS = ParamSpec((int,), minimum=0, maximum=29)
BOOT_ADDR = ParamSpec((int, str), address=True)


@dataclass(frozen=True)
class CoreSpec:
    """Capabilities that the current MOSAIC integration actually supports."""

    name: str
    isas: FrozenSet[str]
    parameters: Mapping[str, ParamSpec] = field(default_factory=dict)
    sci: bool = True
    sim_only: bool = False
    capabilities: FrozenSet[str] = field(default_factory=frozenset)

    @property
    def xlen(self) -> int:
        return 64 if any(isa.startswith("rv64") for isa in self.isas) else 32

    @property
    def fusesoc_flag(self) -> str:
        """Conditional fileset flag for this catalog entry."""

        shared = {
            "serv": "mosaic_serv",
            "qerv": "mosaic_serv",
            "rocket": "mosaic_berkeley",
            "boom": "mosaic_berkeley",
        }
        return shared.get(self.name, f"mosaic_{self.name}")

    @property
    def fusesoc_dependency(self) -> str:
        """VLNV that closes the concrete implementation of this entry."""

        dependencies = {
            "cv32e20": "openhwgroup:cve2:cve2_top",
            "cv32e40p": "openhwgroup.org:ip:cv32e40p",
            "cv32e40px": "x-heep:ip:cv32e40px",
            "cv32e40x": "openhwgroup.org:ip:cv32e40x",
            "serv": "mosaic:ip:servile",
            "qerv": "mosaic:ip:servile",
            "rocket": "mosaic:ip:berkeley",
            "boom": "mosaic:ip:berkeley",
        }
        return dependencies.get(self.name, f"mosaic:ip:{self.name}")


_COMMON_BOOT = {"boot_addr": BOOT_ADDR}
_CV32_ISAS = frozenset({"rv32imc"})

CORE_SPECS: Dict[str, CoreSpec] = {
    "cv32e20": CoreSpec(
        "cv32e20",
        frozenset({"rv32ec", "rv32emc", "rv32ic", "rv32imc"}),
        {
            **_COMMON_BOOT,
            "rv32e": BOOL_BIT,
            "rv32m": ParamSpec(
                (str,),
                choices=frozenset(
                    {"RV32MNone", "RV32MSlow", "RV32MFast", "RV32MSingleCycle"}
                ),
            ),
        },
        sci=False,
        capabilities=frozenset({"split_obi", "debug", "interrupts", "mhartid"}),
    ),
    "cv32e40p": CoreSpec(
        "cv32e40p",
        _CV32_ISAS,
        {
            **_COMMON_BOOT,
            "num_mhpmcounters": MHPM_COUNTERS,
        },
        sci=False,
        capabilities=frozenset({"split_obi", "debug", "interrupts", "mhartid"}),
    ),
    "cv32e40px": CoreSpec(
        "cv32e40px",
        _CV32_ISAS,
        {
            **_COMMON_BOOT,
            "num_mhpmcounters": MHPM_COUNTERS,
        },
        sci=False,
        capabilities=frozenset(
            {"split_obi", "debug", "interrupts", "xif", "mhartid"}
        ),
    ),
    "cv32e40x": CoreSpec(
        "cv32e40x",
        _CV32_ISAS,
        {**_COMMON_BOOT, "num_mhpmcounters": MHPM_COUNTERS},
        sci=False,
        capabilities=frozenset({"split_obi", "debug", "interrupts", "mhartid"}),
    ),
    "fazyrv": CoreSpec(
        "fazyrv",
        frozenset({"rv32i", "rv32ic"}),
        {
            **_COMMON_BOOT,
            "chunksize": ParamSpec((int,), choices=frozenset({1, 2, 4, 8})),
            "conf": ParamSpec((str,), choices=frozenset({"MIN", "INT", "CSR"})),
            "rftype": ParamSpec(
                (str,),
                choices=frozenset(
                    {"LOGIC", "BRAM", "BRAM_BP", "BRAM_DP", "BRAM_DP_BP"}
                ),
            ),
            "rvc": ParamSpec(
                (str,), choices=frozenset({"NONE", "COMB", "REG", "HYBR"})
            ),
            "memdly1": BOOL_BIT,
        },
        capabilities=frozenset({"split_obi", "timer_interrupt"}),
    ),
    "serv": CoreSpec(
        "serv",
        frozenset({"rv32i", "rv32ic", "rv32im", "rv32imc"}),
        {
            **_COMMON_BOOT,
            "w": ParamSpec((int,), choices=frozenset({1})),
            "with_csr": BOOL_BIT,
            "compressed": BOOL_BIT,
            "mdu": BOOL_BIT,
            "pre_register": BOOL_BIT,
        },
        capabilities=frozenset({"unified_obi", "timer_interrupt"}),
    ),
    "qerv": CoreSpec(
        "qerv",
        frozenset({"rv32i", "rv32ic", "rv32im", "rv32imc"}),
        {
            **_COMMON_BOOT,
            "w": ParamSpec((int,), choices=frozenset({4})),
            "with_csr": BOOL_BIT,
            "compressed": BOOL_BIT,
            "mdu": BOOL_BIT,
            "pre_register": BOOL_BIT,
        },
        capabilities=frozenset({"unified_obi", "timer_interrupt"}),
    ),
    "ibex": CoreSpec(
        "ibex",
        frozenset({"rv32ic", "rv32imc", "rv32ec", "rv32emc"}),
        {**_COMMON_BOOT, "rv32e": BOOL_BIT, "mhpmcounters": MHPM_COUNTERS},
        capabilities=frozenset({"split_obi", "debug", "interrupts", "mhartid"}),
    ),
    "hazard3": CoreSpec(
        "hazard3",
        frozenset({"rv32imc"}),
        _COMMON_BOOT,
        capabilities=frozenset({"split_obi", "interrupts", "mhartid"}),
    ),
    "picorv32": CoreSpec(
        "picorv32",
        frozenset({"rv32i", "rv32im", "rv32imc"}),
        {
            **_COMMON_BOOT,
            "counters": BOOL_BIT,
            "barrel_shifter": BOOL_BIT,
            "compressed": BOOL_BIT,
            "mul": BOOL_BIT,
            "div": BOOL_BIT,
        },
        capabilities=frozenset({"unified_obi"}),
    ),
    "snitch": CoreSpec(
        "snitch",
        frozenset({"rv32i"}),
        {**_COMMON_BOOT, "rve": BOOL_BIT, "rvm": BOOL_BIT},
        capabilities=frozenset({"split_obi", "mhartid"}),
    ),
    "cva6": CoreSpec(
        "cva6",
        frozenset({"rv32imc"}),
        _COMMON_BOOT,
        sim_only=True,
        capabilities=frozenset(
            {"unified_obi", "cached", "interrupts", "mhartid"}
        ),
    ),
    "rocket": CoreSpec(
        "rocket",
        frozenset({"rv64imc"}),
        _COMMON_BOOT,
        sim_only=True,
        capabilities=frozenset({"unified_obi", "cached", "interrupts"}),
    ),
    "boom": CoreSpec(
        "boom",
        frozenset({"rv64imc"}),
        _COMMON_BOOT,
        sim_only=True,
        capabilities=frozenset({"unified_obi", "cached", "interrupts"}),
    ),
}

VALID_CORE_IPS = frozenset(CORE_SPECS)
SCI_CORES = frozenset(name for name, spec in CORE_SPECS.items() if spec.sci)
SIM_ONLY_CORES = frozenset(name for name, spec in CORE_SPECS.items() if spec.sim_only)
VALID_ROLES = frozenset({"titan", "atlas", "nano"})
VALID_BUS = frozenset({"obi", "log", "floonoc"})
VALID_SCHED_MODES = frozenset({"static", "dynamic", "power-aware"})
VALID_PDKS = frozenset({"gf180mcu", "sky130"})
VALID_PROFILES = frozenset({"soc", "testbench"})
VALID_TARGETS = frozenset({"rtl", "simulation", "tapeout"})
VALID_PERIPHERALS = frozenset({"uart", "gpio", "timer", "spi", "i2c", "serial_link"})
VALID_ISAS = frozenset(isa for spec in CORE_SPECS.values() for isa in spec.isas)

# This is deliberately a *qualified implementation matrix*, not a list of
# syntactically valid generator settings.  LOG, FlooNoC, Sky130, and alternate
# memory sizes remain useful RTL/simulation configurations, but the repository
# does not currently ship the physical collateral needed to call them tapeout
# targets.  Expanding this matrix requires physical-flow evidence and tests.
TAPEOUT_PDK = "gf180mcu"
TAPEOUT_BUS = "obi"
TAPEOUT_SRAM_KB = 32
TAPEOUT_BOOT_ROM_KB = 2
MIN_BOOT_IMAGE_BYTES = 0x400
TAPEOUT_CORE_MATRIX = (
    {
        "ip": "cv32e20",
        "isa": "rv32emc",
        "count": 1,
        "role": "titan",
    },
    {
        "ip": "fazyrv",
        "isa": "rv32i",
        "chunksize": 8,
        "count": 2,
        "role": "atlas",
        "boot_addr": 0x1000,
    },
    {
        "ip": "serv",
        "isa": "rv32i",
        "count": 4,
        "role": "nano",
        "boot_addr": 0x2000,
    },
)
TAPEOUT_PERIPHERALS = frozenset({"uart", "gpio", "timer", "spi"})

# The public MOSAIC schema fixes iDMA at two streams. Each stream contributes
# exactly two OBI masters (read and write); the legacy simple-DMA address
# master is not part of an explicit MOSAIC topology.
STANDARD_DMA_MASTER_PORTS = 2
IDMA_OBI_PORTS_PER_STREAM = 2
MAX_LOG_BANKS = 32

PERIPHERAL_EXPANSION: Mapping[str, FrozenSet[str]] = {
    "uart": frozenset({"uart"}),
    "gpio": frozenset({"gpio"}),
    "timer": frozenset({"rv_timer"}),
    "spi": frozenset({"spi_host"}),
    "i2c": frozenset({"i2c"}),
    # The serial-link data window requires its register and receive-FIFO blocks.
    "serial_link": frozenset(
        {"serial_link", "serial_link_reg", "serial_link_receiver_fifo"}
    ),
}
MANDATORY_USER_PERIPHERALS = frozenset({"rv_plic"})
MULTICORE_USER_PERIPHERALS = frozenset({"rv_timer"})

SOC_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _unknown_keys(path: str, value: Mapping[str, Any], allowed: FrozenSet[str]) -> List[str]:
    return [f"{path}.{key}: unknown key" for key in sorted(set(value) - set(allowed))]


def target_capability_errors(soc: Mapping[str, Any]) -> List[str]:
    """Return implementation-target errors for an otherwise public SoC map.

    ``target: rtl`` (the default) and ``target: simulation`` describe generator
    products and therefore retain the full schema-supported design space.
    ``target: tapeout`` is intentionally narrower: it is a claim that the
    selected combination is covered by the checked-in GF180 implementation
    flow.  A later LibreLane preflight also requires the concrete bound RTL and
    SRAM macro bundle; schema validation alone never claims signoff completion.
    """

    target = soc.get("target", "rtl")
    if not isinstance(target, str) or target not in VALID_TARGETS:
        return [f"soc.target {target!r} not in {sorted(VALID_TARGETS)}"]
    if target != "tapeout":
        return []

    errors: List[str] = []
    profile = soc.get("profile", "soc")
    pdk = soc.get("pdk", "gf180mcu")
    bus = soc.get("bus", "obi")
    memory = soc.get("memory", {})

    if profile != "soc":
        errors.append("soc.target 'tapeout' requires soc.profile: soc")
    if pdk != TAPEOUT_PDK:
        errors.append(
            "soc.target 'tapeout' is qualified only for pdk 'gf180mcu'; "
            f"{pdk!r} is RTL/simulation-only"
        )
    if bus != TAPEOUT_BUS:
        errors.append(
            "soc.target 'tapeout' is qualified only for bus 'obi'; "
            f"{bus!r} is RTL/simulation-only until physical qualification"
        )

    if isinstance(memory, Mapping):
        sram_kb = memory.get("sram_kb", 32)
        boot_rom_kb = memory.get("boot_rom_kb", 2)
        if sram_kb != TAPEOUT_SRAM_KB:
            errors.append(
                "soc.target 'tapeout' requires memory.sram_kb=32; "
                f"{sram_kb!r} has no qualified GF180 macro integration"
            )
        if boot_rom_kb != TAPEOUT_BOOT_ROM_KB:
            errors.append(
                "soc.target 'tapeout' requires memory.boot_rom_kb=2; "
                f"{boot_rom_kb!r} has no qualified GF180 physical configuration"
            )

    cores = soc.get("cores", [])
    if isinstance(cores, list):
        normalized_cores: List[Dict[str, Any]] = []
        for entry in cores:
            if not isinstance(entry, Mapping):
                continue
            normalized = dict(entry)
            normalized["count"] = normalized.get("count", 1)
            if "boot_addr" in normalized:
                try:
                    normalized["boot_addr"] = (
                        normalized["boot_addr"]
                        if type(normalized["boot_addr"]) is int
                        else int(normalized["boot_addr"], 0)
                    )
                except (TypeError, ValueError):
                    pass
            normalized_cores.append(normalized)
        if normalized_cores != list(TAPEOUT_CORE_MATRIX):
            errors.append(
                "soc.target 'tapeout' is qualified only for the canonical PoC "
                "topology (1x cv32e20 TITAN, 2x FazyRV-8 ATLAS at 0x1000, "
                "4x SERV NANO at 0x2000)"
            )
    scheduler = soc.get("scheduler", {})
    if not isinstance(scheduler, Mapping) or scheduler.get("tdu") is not True:
        errors.append("soc.target 'tapeout' requires scheduler.tdu=true")
    if not isinstance(scheduler, Mapping) or scheduler.get("mode") != "dynamic":
        errors.append("soc.target 'tapeout' requires scheduler.mode='dynamic'")
    peripherals = soc.get("peripherals", [])
    if not isinstance(peripherals, list) or set(peripherals) != TAPEOUT_PERIPHERALS:
        errors.append(
            "soc.target 'tapeout' requires peripherals uart/gpio/timer/spi"
        )
    return errors


def validate_soc_config(cfg: Any, allow_sim_only: bool = True) -> List[str]:
    """Validate the complete public YAML schema and topology invariants."""

    errors: List[str] = []
    if not isinstance(cfg, dict):
        return ["configuration must be a mapping"]
    errors.extend(_unknown_keys("root", cfg, frozenset({"soc"})))
    soc = cfg.get("soc")
    if not isinstance(soc, dict):
        return errors + ["Missing top-level 'soc' mapping"]

    allowed_soc = frozenset(
        {
            "name", "pdk", "profile", "target", "cores", "memory", "bus", "bus_opts",
            "scheduler", "peripherals",
        }
    )
    errors.extend(_unknown_keys("soc", soc, allowed_soc))

    name = soc.get("name", "mosaic_soc")
    if not isinstance(name, str) or not SOC_NAME_RE.fullmatch(name):
        errors.append(
            "soc.name must start with a lowercase letter and contain only "
            "lowercase letters, digits, or underscores (maximum 64 characters)"
        )
    pdk = soc.get("pdk", "gf180mcu")
    if not isinstance(pdk, str) or pdk not in VALID_PDKS:
        errors.append(f"soc.pdk {pdk!r} not in {sorted(VALID_PDKS)}")
    profile = soc.get("profile", "soc")
    if not isinstance(profile, str) or profile not in VALID_PROFILES:
        errors.append(f"soc.profile {profile!r} not in {sorted(VALID_PROFILES)}")
    target = soc.get("target", "rtl")
    if not isinstance(target, str) or target not in VALID_TARGETS:
        errors.append(f"soc.target {target!r} not in {sorted(VALID_TARGETS)}")

    cores = soc.get("cores")
    if not isinstance(cores, list) or not cores:
        errors.append("At least one core group required in 'cores'")
        cores = []

    total_cores = 0
    roles: List[str] = []
    for index, entry in enumerate(cores):
        path = f"cores[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{path} must be a mapping")
            continue
        ip = entry.get("ip")
        if not isinstance(ip, str) or ip not in CORE_SPECS:
            errors.append(f"{path}.ip {ip!r} not in {sorted(CORE_SPECS)}")
            spec = None
        else:
            spec = CORE_SPECS[ip]
            if spec.sim_only and profile != "testbench":
                errors.append(
                    f"{path}.ip '{ip}' is demo/simulation-only and requires "
                    "soc.profile: testbench"
                )
            if spec.sim_only and target == "tapeout":
                errors.append(
                    f"{path}.ip '{ip}' is simulation-only and cannot be used with "
                    "soc.target: tapeout"
                )
            if not allow_sim_only and spec.sim_only:
                errors.append(
                    f"{path}.ip '{ip}' is SIMULATION-ONLY and is not allowed "
                    "in a tapeout configuration"
                )

        allowed_core = {"ip", "isa", "count", "role"}
        if spec is not None:
            allowed_core.update(spec.parameters)
        errors.extend(_unknown_keys(path, entry, frozenset(allowed_core)))

        count = entry.get("count", 1)
        if type(count) is not int or count < 1:
            errors.append(f"{path}.count must be an integer >= 1, got {count!r}")
        else:
            total_cores += count

        role = entry.get("role")
        if not isinstance(role, str) or role not in VALID_ROLES:
            errors.append(f"{path}.role {role!r} not in {sorted(VALID_ROLES)}")
        else:
            roles.append(role)
            if ip in {"rocket", "boom"} and role == "titan":
                # The extracted tile exposes only one hart-id bit.  A singleton
                # leading tile is nevertheless a truthful simulation controller:
                # its uncached windows reach shared state, TDU and soc_ctrl.
                if index != 0 or count != 1:
                    errors.append(
                        f"{path}: {ip} may be a TITAN only as one leading "
                        "simulation hart at cores[0]"
                    )

        isa = entry.get("isa")
        if not isinstance(isa, str):
            errors.append(f"{path}.isa is required and must be a string")
        elif spec is not None and isa not in spec.isas:
            errors.append(
                f"{path}.isa '{isa}' is not supported by {ip}; valid: {sorted(spec.isas)}"
            )

        if spec is not None:
            for parameter, parameter_spec in spec.parameters.items():
                if parameter in entry:
                    error = parameter_spec.validate(
                        f"{path}.{parameter}", entry[parameter]
                    )
                    if error:
                        errors.append(error)

            # Cross-field capability constraints: the ISA declaration is a
            # contract, not documentation.  Reject settings that would build
            # a different instruction set than the one declared.
            isa_extensions = isa[4:] if isinstance(isa, str) and len(isa) > 4 else ""
            if ip == "fazyrv":
                rvc = entry.get("rvc", "NONE")
                if ("c" in isa_extensions) != (rvc != "NONE"):
                    errors.append(f"{path}.isa and {path}.rvc disagree on compressed ISA")
                if entry.get("conf", "CSR") == "CSR" and entry.get(
                    "rftype", "BRAM_DP_BP"
                ) == "LOGIC":
                    errors.append(f"{path}: FazyRV CONF=CSR cannot use RFTYPE=LOGIC")
            elif ip in {"serv", "qerv"}:
                if ("c" in isa_extensions) != bool(entry.get("compressed", False)):
                    errors.append(
                        f"{path}.isa and {path}.compressed disagree on compressed ISA"
                    )
                if ("m" in isa_extensions) != bool(entry.get("mdu", False)):
                    errors.append(f"{path}.isa and {path}.mdu disagree on M extension")
            elif ip == "picorv32":
                if ("c" in isa_extensions) != bool(entry.get("compressed", False)):
                    errors.append(
                        f"{path}.isa and {path}.compressed disagree on compressed ISA"
                    )
                has_mul = bool(entry.get("mul", False))
                has_div = bool(entry.get("div", False))
                has_muldiv = has_mul and has_div
                if has_mul != has_div:
                    errors.append(
                        f"{path}: standard M requires both mul=true and div=true"
                    )
                if ("m" in isa_extensions) != has_muldiv:
                    errors.append(f"{path}.isa and mul/div parameters disagree on M extension")
            elif ip == "ibex":
                is_rv32e = isa.startswith("rv32e")
                if "rv32e" in entry and is_rv32e != bool(entry["rv32e"]):
                    errors.append(f"{path}.isa and {path}.rv32e disagree on register profile")
            elif ip == "cv32e20":
                is_rv32e = isa.startswith("rv32e")
                has_m = "m" in isa_extensions
                if "rv32e" in entry and is_rv32e != bool(entry["rv32e"]):
                    errors.append(f"{path}.isa and {path}.rv32e disagree on register profile")
                if "rv32m" in entry:
                    mode_has_m = entry["rv32m"] != "RV32MNone"
                    if has_m != mode_has_m:
                        errors.append(f"{path}.isa and {path}.rv32m disagree on M extension")
            elif ip == "snitch" and (
                bool(entry.get("rve", False)) or bool(entry.get("rvm", False))
            ):
                errors.append(
                    f"{path}: current Snitch integration is RV32I-only; RVE/RVM are unavailable"
                )

    mem = soc.get("memory", {})
    if not isinstance(mem, dict):
        errors.append("memory must be a mapping")
        mem = {}
    errors.extend(
        _unknown_keys("memory", mem, frozenset({"sram_kb", "boot_rom_kb"}))
    )
    sram_kb = mem.get("sram_kb", 32)
    if type(sram_kb) is not int or not 8 <= sram_kb <= 512:
        errors.append(f"memory.sram_kb must be an integer from 8 to 512, got {sram_kb!r}")
    elif sram_kb & (sram_kb - 1):
        errors.append(f"memory.sram_kb must be a power of two, got {sram_kb}")
    boot_rom_kb = mem.get("boot_rom_kb", 2)
    if type(boot_rom_kb) is not int or not 1 <= boot_rom_kb <= 64:
        errors.append(
            f"memory.boot_rom_kb must be an integer from 1 to 64, got {boot_rom_kb!r}"
        )
    elif boot_rom_kb & (boot_rom_kb - 1):
        errors.append(f"memory.boot_rom_kb must be a power of two, got {boot_rom_kb}")

    # Resolve software load slots at the schema boundary. Mandatory bundle
    # generation uses these values for linkers and boot-image manifests, so a
    # configuration accepted here must not fail later in software_gen.
    boot_slots: Dict[int, List[Tuple[str, str]]] = {}
    for index, entry in enumerate(cores):
        if not isinstance(entry, dict):
            continue
        ip = entry.get("ip")
        isa = entry.get("isa")
        role = entry.get("role")
        if profile == "soc" and role in {"atlas", "nano"} and "boot_addr" not in entry:
            errors.append(
                f"cores[{index}].boot_addr is required for an AMP worker in profile 'soc'"
            )
        if profile == "soc" and role == "titan" and "boot_addr" in entry:
            errors.append(
                f"cores[{index}].boot_addr must be omitted for a production TITAN; "
                "the reset vector must remain the boot ROM"
            )
        if ip in {"rocket", "boom"} and "boot_addr" not in entry:
            errors.append(
                f"cores[{index}].boot_addr is required for the {ip} translated code window"
            )
        raw_address = entry.get("boot_addr", 0x180)
        try:
            address = raw_address if type(raw_address) is int else int(raw_address, 0)
        except (TypeError, ValueError):
            continue  # ParamSpec already reports the field-level error.
        if type(sram_kb) is int and 8 <= sram_kb <= 512:
            if address < 0 or address >= sram_kb * 1024:
                errors.append(
                    f"cores[{index}].boot_addr 0x{address:08x} must select SRAM "
                    f"[0x00000000, 0x{sram_kb * 1024:08x})"
                )
        if isinstance(isa, str):
            abi = "ilp32e" if isa.startswith("rv32e") else (
                "ilp32" if isa.startswith("rv32") else "lp64"
            )
            boot_slots.setdefault(address, []).append((abi, f"cores[{index}]"))

    if profile == "soc":
        for address, users in boot_slots.items():
            abis = {abi for abi, _ in users}
            if len(abis) > 1:
                errors.append(
                    f"boot image at 0x{address:08x} mixes incompatible ABIs "
                    f"{sorted(abis)}; assign distinct boot_addr values"
                )

    if boot_slots and type(sram_kb) is int and 8 <= sram_kb <= 512:
        last_boot = max(boot_slots)
        shared_base = (last_boot + 0x1000 + 0xFF) & ~0xFF
        slot_addresses = sorted(boot_slots)
        for slot_index, address in enumerate(slot_addresses):
            slot_end = (
                slot_addresses[slot_index + 1]
                if slot_index + 1 < len(slot_addresses)
                else shared_base
            )
            if slot_end - address < MIN_BOOT_IMAGE_BYTES:
                errors.append(
                    f"boot image slot at 0x{address:08x} is only "
                    f"{slot_end - address} bytes; each distinct image needs at "
                    f"least {MIN_BOOT_IMAGE_BYTES} bytes"
                )
        shared_size = max(0x200, ((total_cores * 8 + 0xFF) // 0x100) * 0x100)
        required_end = shared_base + shared_size + 0x400
        if required_end > sram_kb * 1024:
            errors.append(
                "boot images plus shared-control and minimum stack do not fit SRAM: "
                f"need through 0x{required_end:08x}, SRAM ends at "
                f"0x{sram_kb * 1024:08x}"
            )

    bus = soc.get("bus", "obi")
    if not isinstance(bus, str) or bus not in VALID_BUS:
        errors.append(f"bus {bus!r} not in {sorted(VALID_BUS)}")

    bus_opts = soc.get("bus_opts", {})
    if not isinstance(bus_opts, dict):
        errors.append("bus_opts must be a mapping")
        bus_opts = {}
    errors.extend(_unknown_keys("bus_opts", bus_opts, frozenset({"log", "floonoc"})))
    for fabric, allowed in {
        "log": frozenset({"topology", "num_banks"}),
        "floonoc": frozenset({"route_algo", "endpoints"}),
    }.items():
        options = bus_opts.get(fabric, {})
        if not isinstance(options, dict):
            errors.append(f"bus_opts.{fabric} must be a mapping")
            continue
        errors.extend(
            f"bus_opts.{fabric}.{key}: unknown option"
            for key in sorted(set(options) - set(allowed))
        )
    log_options = bus_opts.get("log", {})
    if isinstance(log_options, dict):
        topology = log_options.get("topology", "lic")
        if topology != "lic":
            errors.append(
                "bus_opts.log.topology currently supports only 'lic'; the "
                "standard MOSAIC master count is not a power of two"
            )
        num_banks = log_options.get("num_banks", "auto")
        if num_banks != "auto" and (type(num_banks) is not int or num_banks < 1):
            errors.append("bus_opts.log.num_banks must be 'auto' or an integer >= 1")
        if bus == "log" and total_cores > 0 and type(sram_kb) is int:
            num_masters = (
                2 * total_cores
                + 1
                + IDMA_OBI_PORTS_PER_STREAM * STANDARD_DMA_MASTER_PORTS
            )
            required_banks = 1 << (num_masters - 1).bit_length()
            resolved_banks = required_banks if num_banks == "auto" else num_banks
            if type(resolved_banks) is int and resolved_banks >= 1:
                if resolved_banks > MAX_LOG_BANKS:
                    errors.append(
                        f"bus 'log' needs {required_banks} banks for "
                        f"{num_masters} masters, exceeding the {MAX_LOG_BANKS}-bank backend"
                    )
                if resolved_banks & (resolved_banks - 1):
                    errors.append("bus_opts.log.num_banks must be a power of two")
                if resolved_banks < num_masters:
                    errors.append(
                        f"bus 'log' needs num_banks >= {num_masters} bus masters"
                    )
                if sram_kb % resolved_banks != 0 or sram_kb < resolved_banks:
                    errors.append(
                        f"memory.sram_kb={sram_kb} must be divisible by LOG bank "
                        f"count {resolved_banks} with at least 1 KiB per bank"
                    )
    floo_options = bus_opts.get("floonoc", {})
    if isinstance(floo_options, dict):
        route_algo = floo_options.get("route_algo", "ID")
        if route_algo != "ID":
            errors.append(
                "bus_opts.floonoc.route_algo currently supports only 'ID' "
                "for the compact single-router topology"
            )
        endpoints = floo_options.get("endpoints", "compact")
        if endpoints != "compact":
            errors.append("bus_opts.floonoc.endpoints currently supports only 'compact'")

    scheduler = soc.get("scheduler", {})
    if not isinstance(scheduler, dict):
        errors.append("scheduler must be a mapping")
        scheduler = {}
    errors.extend(_unknown_keys("scheduler", scheduler, frozenset({"tdu", "mode"})))
    tdu = scheduler.get("tdu", False)
    if type(tdu) is not bool:
        errors.append(f"scheduler.tdu must be boolean, got {type(tdu).__name__}")
        tdu_enabled = False
    else:
        tdu_enabled = tdu
    mode = scheduler.get("mode", "static")
    if not isinstance(mode, str) or mode not in VALID_SCHED_MODES:
        errors.append(f"scheduler.mode {mode!r} not in {sorted(VALID_SCHED_MODES)}")
    # The generated PLIC, debug mask, and TDU register ABI all use a maximum
    # of sixteen contexts.  Apply the bound to every topology (including an
    # all-TITAN SMP with the TDU disabled) so schema validation cannot accept
    # a design that a later platform-generator step must reject.
    if total_cores > 16:
        errors.append(
            f"MOSAIC platform services support at most 16 harts, "
            f"configuration has {total_cores}"
        )

    peripherals = soc.get("peripherals", [])
    if not isinstance(peripherals, list):
        errors.append("peripherals must be a list")
        peripherals = []
    seen_peripherals = set()
    for index, peripheral in enumerate(peripherals):
        if not isinstance(peripheral, str) or peripheral not in VALID_PERIPHERALS:
            errors.append(
                f"peripherals[{index}] {peripheral!r} not in {sorted(VALID_PERIPHERALS)}"
            )
        elif peripheral in seen_peripherals:
            errors.append(f"peripherals[{index}] duplicates '{peripheral}'")
        else:
            seen_peripherals.add(peripheral)

    if roles:
        has_worker = any(role != "titan" for role in roles)
        titan_groups = [index for index, role in enumerate(roles) if role == "titan"]
        if profile == "soc":
            if has_worker:
                leading_titan_count = (
                    cores[0].get("count", 0)
                    if titan_groups and titan_groups[0] == 0 and isinstance(cores[0], dict)
                    else 0
                )
                if titan_groups != [0] or leading_titan_count != 1:
                    errors.append(
                        "AMP topology requires exactly one leading TITAN hart at cores[0]"
                    )
                if not tdu_enabled:
                    errors.append(
                        "AMP topology with ATLAS/NANO workers requires scheduler.tdu=true"
                    )
                worker_roles = [role for role in roles if role != "titan"]
                if worker_roles != sorted(
                    worker_roles, key={"atlas": 0, "nano": 1}.get
                ):
                    errors.append("AMP core groups must order ATLAS before NANO workers")
        # All-TITAN SMP is valid with or without the TDU.  Zero-TITAN worker
        # arrangements are reserved for explicit simulation testbenches.
        if profile == "testbench" and titan_groups and titan_groups[0] != 0:
            errors.append("testbench TITAN groups must still begin at cores[0]")
        if (
            profile == "testbench"
            and has_worker
            and total_cores > 1
            and not tdu_enabled
        ):
            errors.append(
                "multi-hart testbench topology with ATLAS/NANO workers requires "
                "scheduler.tdu=true to release dormant workers"
            )

    # Keep physical qualification as a final, orthogonal gate.  This lets the
    # normal schema report field errors while also making any false tapeout
    # claim impossible to miss.
    if isinstance(target, str) and target in VALID_TARGETS:
        errors.extend(target_capability_errors(soc))

    return errors


def expanded_user_peripherals(
    peripherals: List[str], *, multicore: bool = False
) -> FrozenSet[str]:
    """Map public peripheral names to concrete x-heep peripheral blocks."""

    selected = set(MANDATORY_USER_PERIPHERALS)
    if multicore:
        selected.update(MULTICORE_USER_PERIPHERALS)
    for peripheral in peripherals:
        selected.update(PERIPHERAL_EXPANSION[peripheral])
    return frozenset(selected)


def resolved_capabilities(ip: str, params: Mapping[str, Any]) -> FrozenSet[str]:
    """Return capabilities of the concrete parameterized core instance.

    Capability headers and platform masks must describe instantiated RTL, not
    the maximum feature set of the core family.
    """

    capabilities = set(CORE_SPECS[ip].capabilities)
    if ip == "fazyrv" and params.get("conf", "CSR") == "MIN":
        capabilities.discard("timer_interrupt")
    if ip in {"serv", "qerv"} and not bool(params.get("with_csr", True)):
        capabilities.discard("timer_interrupt")
    return frozenset(capabilities)
