"""Physical-target honesty gates must be strict without narrowing RTL generation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePath
import subprocess
import sys

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.append(str(REPO_ROOT / "util" / "xheep_gen"))

import mosaic_config
from harness.core import validate_config
from harness.skills.config_author import ConfigAuthor


def _soc() -> dict:
    return {
        "soc": {
            "name": "physical_contract",
            "pdk": "gf180mcu",
            "profile": "soc",
            "target": "tapeout",
            "cores": [
                {"ip": "cv32e20", "isa": "rv32emc", "count": 1, "role": "titan"},
                {
                    "ip": "fazyrv", "isa": "rv32i", "chunksize": 8,
                    "count": 2, "role": "atlas", "boot_addr": 0x1000,
                },
                {
                    "ip": "serv", "isa": "rv32i", "count": 4,
                    "role": "nano", "boot_addr": 0x2000,
                },
            ],
            "memory": {"sram_kb": 32, "boot_rom_kb": 2},
            "bus": "obi",
            "scheduler": {"tdu": True, "mode": "dynamic"},
            "peripherals": ["uart", "gpio", "timer", "spi"],
        }
    }


def test_qualified_tapeout_matrix_and_parser_target(tmp_path):
    raw = _soc()
    assert validate_config(raw) == []
    path = tmp_path / "mosaic.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    parsed = mosaic_config.parse_yaml(PurePath(path))
    assert parsed.target == "tapeout"


@pytest.mark.parametrize(
    "mutate,needle",
    [
        (lambda s: s.update({"pdk": "sky130"}), "qualified only for pdk"),
        (lambda s: s.update({"bus": "log"}), "qualified only for bus"),
        (lambda s: s.update({"bus": "floonoc"}), "qualified only for bus"),
        (lambda s: s["memory"].update({"sram_kb": 64}), "sram_kb=32"),
        (lambda s: s["memory"].update({"boot_rom_kb": 4}), "boot_rom_kb=2"),
        (lambda s: s.update({"profile": "testbench"}), "requires soc.profile: soc"),
        (lambda s: s["cores"][1].update({"count": 1}), "canonical PoC topology"),
        (lambda s: s["scheduler"].update({"mode": "static"}), "mode='dynamic'"),
        (lambda s: s.update({"peripherals": ["uart"]}), "uart/gpio/timer/spi"),
    ],
)
def test_tapeout_rejects_unqualified_physical_combinations(mutate, needle):
    raw = _soc()
    mutate(raw["soc"])
    assert any(needle in error for error in validate_config(raw))


def test_log_floonoc_sky130_and_other_memory_remain_rtl_usable():
    variants = []
    for update in (
        {"pdk": "sky130"},
        {"bus": "log"},
        {"bus": "floonoc"},
        {"memory": {"sram_kb": 64, "boot_rom_kb": 4}},
    ):
        raw = _soc()
        raw["soc"]["target"] = "rtl"
        raw["soc"].update(update)
        variants.append(raw)
    for raw in variants:
        assert validate_config(raw) == [], raw


def test_sim_only_core_is_explicitly_scoped_away_from_tapeout():
    raw = _soc()
    raw["soc"]["profile"] = "testbench"
    raw["soc"]["cores"] = [
        {"ip": "cva6", "isa": "rv32imc", "count": 1, "role": "titan"}
    ]
    errors = validate_config(raw)
    assert any("simulation-only" in error and "soc.target: tapeout" in error for error in errors)

    raw["soc"]["target"] = "simulation"
    assert validate_config(raw) == []


def test_config_author_labels_only_the_qualified_poc_as_tapeout(tmp_path):
    author = ConfigAuthor(repo_root=tmp_path)
    poc = author.generate(name="poc", preset="poc", output_path=tmp_path / "poc.yaml")
    minimal = author.generate(
        name="minimal", preset="minimal", output_path=tmp_path / "minimal.yaml"
    )
    assert poc.ok, poc.errors
    assert minimal.ok, minimal.errors
    assert poc.details["config"]["soc"]["target"] == "tapeout"
    assert minimal.details["config"]["soc"]["target"] == "rtl"


def _hashed(path: Path, relative: str) -> dict:
    return {"path": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _bundle(tmp_path: Path, *, placeholder: bool = False) -> Path:
    bundle = tmp_path / "physical"
    sram = bundle / "sram"
    sram.mkdir(parents=True)
    flat = bundle / "design.v"
    flat.write_text(
        "module core_v_mini_mcu(input logic clk_i);\n"
        + "\n".join(f"wire generated_net_{index} = clk_i;" for index in range(2500))
        + "\nendmodule\n"
    )
    bound = bundle / "mosaic_soc_core.sv"
    if placeholder:
        bound.write_text(
            "module mosaic_soc_core; // x_heep_system i_soc();\n"
            + ("// placeholder padding\n" * 32)
            + "endmodule\n"
        )
    else:
        bound.write_text(
            "module mosaic_soc_core(input logic clk_i, input logic rst_ni);\n"
            "logic [31:0] gpio_in, gpio_out, gpio_oe;\n"
            "x_heep_system i_soc(.clk_i(clk_i), .rst_ni(rst_ni));\n"
            + ("assign gpio_in = gpio_out & gpio_oe;\n" * 16)
            + "endmodule\n"
        )
    gds = sram / "mosaic_sram.gds"
    # Minimal structurally complete GDSII macro with one boundary.
    def gds_record(record_type: int, data_type: int = 0, payload: bytes = b"") -> bytes:
        if len(payload) & 1:
            payload += b"\0"
        return (4 + len(payload)).to_bytes(2, "big") + bytes(
            (record_type, data_type)
        ) + payload

    gds.write_bytes(
        gds_record(0x00, 2, b"\x02\x58")
        + gds_record(0x01, 2, bytes(24))
        + gds_record(0x02, 6, b"MOSAIC")
        + gds_record(0x03, 5, bytes(16))
        + gds_record(0x05, 2, bytes(24))
        + gds_record(0x06, 6, b"mosaic_sram")
        + gds_record(0x08)
        + gds_record(0x0D, 2, b"\0\1")
        + gds_record(0x0E, 2, b"\0\0")
        + gds_record(0x10, 3, bytes(40))
        + gds_record(0x11)
        + gds_record(0x07)
        + gds_record(0x04)
    )
    lef = sram / "mosaic_sram.lef"
    lef.write_text("MACRO mosaic_sram\nEND mosaic_sram\n")
    lib = sram / "mosaic_sram.lib"
    lib.write_text("library(x) { cell (mosaic_sram) { } }\n")
    verilog = sram / "mosaic_sram.v"
    verilog.write_text("module mosaic_sram; endmodule\n")
    build_key = "physical-contract-0123456789ab"
    manifest = bundle / "manifest.json"
    physical_files = {
        "flattened_rtl": flat,
        "bound_core_rtl": bound,
        "sram_gds": gds,
        "sram_lef": lef,
        "sram_lib": lib,
        "sram_verilog": verilog,
    }
    manifest.write_text(json.dumps({
        "schema_version": 2,
        "build_key": build_key,
        "resolved": {
            "target": "tapeout",
            "profile": "soc",
            "pdk": "gf180mcu",
            "bus": "obi",
            "cores": [
                {
                    "ip": "cv32e20", "isa": "rv32emc", "role": "titan",
                    "count": 1, "params": {},
                },
                {
                    "ip": "fazyrv", "isa": "rv32i", "role": "atlas",
                    "count": 2,
                    "params": {"chunksize": 8, "boot_addr": 0x1000},
                },
                {
                    "ip": "serv", "isa": "rv32i", "role": "nano",
                    "count": 4, "params": {"boot_addr": 0x2000},
                },
            ],
            "memory": {"declared_sram_kb": 32, "declared_boot_rom_kb": 2},
            "scheduler": {"tdu": True, "mode": "dynamic"},
            "declared_peripherals": ["uart", "gpio", "timer", "spi"],
        },
        "physical_attestation": {
            "build_key": build_key,
            **{
                f"{name}_sha256": hashlib.sha256(path.read_bytes()).hexdigest()
                for name, path in physical_files.items()
            },
        },
    }))
    files = {
        "manifest": (manifest, "manifest.json"),
        "flattened_rtl": (flat, "design.v"),
        "bound_core_rtl": (bound, "mosaic_soc_core.sv"),
        "sram_gds": (gds, "sram/mosaic_sram.gds"),
        "sram_lef": (lef, "sram/mosaic_sram.lef"),
        "sram_lib": (lib, "sram/mosaic_sram.lib"),
        "sram_verilog": (verilog, "sram/mosaic_sram.v"),
    }
    descriptor = {
        "schema_version": 1,
        "build_key": build_key,
        "artifacts": {name: _hashed(path, relative) for name, (path, relative) in files.items()},
    }
    (bundle / "physical_bundle.json").write_text(json.dumps(descriptor, indent=2))
    return bundle


def _preflight(bundle: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "flow/librelane/scripts/preflight.py"),
         "--bundle", str(bundle), "--mode", "chip", *extra],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_physical_bundle_preflight_accepts_hashed_bound_inputs(tmp_path):
    result = _preflight(_bundle(tmp_path), "--emit-shell")
    assert result.returncode == 0, result.stderr
    assert "MOSAIC_BOUND_SOC_RTL" in result.stdout
    assert "MOSAIC_SRAM_GDS" in result.stdout


def test_physical_bundle_preflight_rejects_placeholder_and_stale_hash(tmp_path):
    placeholder = _preflight(_bundle(tmp_path, placeholder=True))
    assert placeholder.returncode == 2
    assert "does not instantiate x_heep_system" in placeholder.stderr

    bundle = _bundle(tmp_path / "stale")
    (bundle / "design.v").write_text("module changed; endmodule\n")
    stale = _preflight(bundle)
    assert stale.returncode == 2
    assert "hash mismatch" in stale.stderr


def test_librelane_makefile_fails_fast_without_bundle():
    result = subprocess.run(
        ["make", "-C", str(REPO_ROOT / "flow/librelane"), "preflight-chip"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "set PHYSICAL_BUNDLE" in result.stdout + result.stderr
