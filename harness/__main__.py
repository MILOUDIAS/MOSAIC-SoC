#!/usr/bin/env python3
"""oh-my-soc — CLI entry point for the MOSAIC-SoC agentic harness.

Based on oh-my-pi, adapted for MOSAIC-SoC EDA flows.

Usage:
    python -m harness <skill> <command> [args...]
    python -m harness config-author generate --name my_soc ...
    python -m harness config-author validate configs/mosaic.yaml
    python -m harness config-author presets
    python -m harness flow-runner list
    python -m harness flow-runner run mosaic-gen
    python -m harness drc-triage analyze report.rpt
    python -m harness drc-triage scan build/reports/
    python -m harness doc-gen config mosaic.yaml
    python -m harness doc-gen memory-map
    python -m harness doc-gen dashboard
"""

import argparse
import json
import sys
from pathlib import Path

from .core import SkillResult


def _print_result(result: SkillResult, verbose: bool = False):
    """Pretty-print a SkillResult."""
    status = "OK" if result.ok else "FAIL"
    print(f"[{status}] {result.summary}")
    if result.errors:
        for e in result.errors:
            print(f"  ERROR: {e}")
    if verbose and result.details:
        # Print markdown if available
        md = result.details.get("markdown")
        if md:
            print()
            print(md)
        else:
            print(json.dumps(result.details, indent=2, default=str))


def cmd_config_author(args):
    from .skills.config_author import ConfigAuthor
    author = ConfigAuthor()

    if args.config_author_cmd == "generate":
        cores = []
        if args.core:
            for c in args.core:
                parts = c.split(":")
                if len(parts) >= 3:
                    cores.append({"ip": parts[0], "count": int(parts[1]), "role": parts[2]})
                elif len(parts) == 2:
                    cores.append({"ip": parts[0], "count": int(parts[1]), "role": "nano"})
                else:
                    cores.append({"ip": parts[0], "count": 1, "role": "nano"})

        peripherals = args.peripheral.split(",") if args.peripheral else []

        result = author.generate(
            name=args.name,
            cores=cores if cores else None,
            sram_kb=args.sram,
            tdu=args.tdu,
            sched_mode=args.mode,
            peripherals=peripherals,
            preset=args.preset,
            output_path=Path(args.output) if args.output else None,
        )
        _print_result(result, verbose=True)

    elif args.config_author_cmd == "validate":
        result = author.validate_file(Path(args.file))
        _print_result(result, verbose=True)

    elif args.config_author_cmd == "presets":
        result = author.list_presets()
        _print_result(result, verbose=True)


def cmd_flow_runner(args):
    from .skills.flow_runner import FlowRunner
    runner = FlowRunner()

    if args.flow_runner_cmd == "list":
        result = runner.list_flows()
        _print_result(result, verbose=True)

    elif args.flow_runner_cmd == "run":
        result = runner.run(
            args.flow_name,
            config=args.config,
        )
        _print_result(result, verbose=True)


def cmd_drc_triage(args):
    from .skills.drc_triage import DRCTriage
    triage = DRCTriage()

    if args.drc_triage_cmd == "analyze":
        result = triage.analyze_file(Path(args.file), fmt=args.format)
        _print_result(result, verbose=True)

    elif args.drc_triage_cmd == "scan":
        result = triage.triage_directory(Path(args.directory))
        _print_result(result, verbose=True)


def cmd_doc_gen(args):
    from .skills.doc_gen import DocGen
    docgen = DocGen()

    if args.doc_gen_cmd == "config":
        result = docgen.config_summary(Path(args.file))
        _print_result(result, verbose=True)

    elif args.doc_gen_cmd == "memory-map":
        result = docgen.memory_map()
        _print_result(result, verbose=True)

    elif args.doc_gen_cmd == "dashboard":
        result = docgen.dashboard_summary(
            Path(args.file) if args.file else None
        )
        _print_result(result, verbose=True)


def cmd_topo_viz(args):
    from .skills.topo_viz import TopoViz
    viz = TopoViz()

    if args.topo_viz_cmd == "check":
        result = viz.check(Path(args.file))
        _print_result(result, verbose=True)

    elif args.topo_viz_cmd == "render":
        result = viz.render(
            Path(args.file),
            output=Path(args.output) if args.output else None,
            svg_only=args.svg,
        )
        _print_result(result, verbose=True)


def main():
    parser = argparse.ArgumentParser(
        prog="oh-my-soc",
        description="Agentic harness for MOSAIC-SoC EDA flows (based on oh-my-pi)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    subparsers = parser.add_subparsers(dest="skill", help="Skill to use")

    # config-author
    ca = subparsers.add_parser("config-author", help="Generate/validate mosaic.yaml")
    ca_sub = ca.add_subparsers(dest="config_author_cmd")

    ca_gen = ca_sub.add_parser("generate", help="Generate a config")
    ca_gen.add_argument("--name", default="mosaic_soc", help="SoC name")
    ca_gen.add_argument("--core", action="append", help="Core spec: ip:count:role (repeatable)")
    ca_gen.add_argument("--sram", type=int, default=32, help="SRAM KB")
    ca_gen.add_argument("--tdu", action="store_true", help="Enable TDU")
    ca_gen.add_argument("--mode", default="static", help="Scheduling mode")
    ca_gen.add_argument("--peripheral", help="Comma-separated peripherals")
    ca_gen.add_argument("--preset", help="Use a named preset")
    ca_gen.add_argument("--output", help="Output path")

    ca_val = ca_sub.add_parser("validate", help="Validate a config file")
    ca_val.add_argument("file", help="Path to mosaic.yaml")

    ca_sub.add_parser("presets", help="List available presets")

    # flow-runner
    fr = subparsers.add_parser("flow-runner", help="Run EDA flows")
    fr_sub = fr.add_subparsers(dest="flow_runner_cmd")

    fr_sub.add_parser("list", help="List available flows")

    fr_run = fr_sub.add_parser("run", help="Run a flow")
    fr_run.add_argument("flow_name", help="Flow to run")
    fr_run.add_argument("--config", help="Config path for mosaic-gen")

    # drc-triage
    dt = subparsers.add_parser("drc-triage", help="Analyze DRC/LVS reports")
    dt_sub = dt.add_subparsers(dest="drc_triage_cmd")

    dt_analyze = dt_sub.add_parser("analyze", help="Analyze a report file")
    dt_analyze.add_argument("file", help="Report file path")
    dt_analyze.add_argument("--format", help="Report format (magic/klayout/netgen/auto)")

    dt_scan = dt_sub.add_parser("scan", help="Scan a directory for reports")
    dt_scan.add_argument("directory", help="Directory to scan")

    # doc-gen
    dg = subparsers.add_parser("doc-gen", help="Generate documentation")
    dg_sub = dg.add_subparsers(dest="doc_gen_cmd")

    dg_config = dg_sub.add_parser("config", help="Config summary doc")
    dg_config.add_argument("file", help="Path to mosaic.yaml")

    dg_sub.add_parser("memory-map", help="Memory-map reference doc")

    dg_dash = dg_sub.add_parser("dashboard", help="Dashboard summary")
    dg_dash.add_argument("--file", help="Dashboard path (default: DASHBOARD.md)")

    # topo-viz
    tv = subparsers.add_parser("topo-viz",
                               help="Semantic config checks + topology diagram")
    tv_sub = tv.add_subparsers(dest="topo_viz_cmd")

    tv_check = tv_sub.add_parser("check", help="Semantic checks on a config")
    tv_check.add_argument("file", help="mosaic.yaml-style config")

    tv_render = tv_sub.add_parser("render", help="Render the topology diagram")
    tv_render.add_argument("file", help="mosaic.yaml-style config")
    tv_render.add_argument("-o", "--output", help="Output file (.html or .svg)")
    tv_render.add_argument("--svg", action="store_true",
                           help="Emit a plain SVG instead of HTML")

    args = parser.parse_args()

    if not args.skill:
        parser.print_help()
        sys.exit(1)

    # Set up logging
    import logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(name)s: %(message)s",
    )

    dispatch = {
        "config-author": cmd_config_author,
        "flow-runner": cmd_flow_runner,
        "drc-triage": cmd_drc_triage,
        "doc-gen": cmd_doc_gen,
        "topo-viz": cmd_topo_viz,
    }

    dispatch[args.skill](args)


if __name__ == "__main__":
    main()
