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
import os
import signal
import sys
from pathlib import Path

from .core import SkillResult


# Set by main() from --json: machine mode prints the raw SkillResult JSON
# (consumed by the .omp/tools shim and tests) and exits non-zero on failure.
_JSON_MODE = False
_PROGRESS_JSONL = False


class _StrictArgumentParser(argparse.ArgumentParser):
    """Disable long-option prefix matching in every nested subparser."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("allow_abbrev", False)
        super().__init__(*args, **kwargs)


def _progress(kind: str, message: str, **details):
    if not _PROGRESS_JSONL:
        return
    print(
        json.dumps({"kind": kind, "message": message, "details": details}, default=str),
        file=sys.stderr,
        flush=True,
    )


def _external_agent_command(
    driver: str, binary: str, prompt: str, *, interactive: bool
) -> list[str]:
    """Select a visible external-agent surface without fake slash commands."""

    if driver == "omp":
        return [binary, prompt] if interactive else [binary, "--mode", "json", prompt]
    if driver == "claude":
        return [binary, prompt] if interactive else [binary, "-p", prompt]
    raise ValueError(driver)


def _cancel_handler(_signum, _frame):
    raise KeyboardInterrupt


def _print_result(result: SkillResult, verbose: bool = False):
    """Pretty-print a SkillResult (or raw JSON in --json mode)."""
    if _JSON_MODE:
        print(result.to_json())
        if not result.ok:
            sys.exit(1)
        return
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
    if not result.ok:
        sys.exit(1)


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
            boot_rom_kb=args.boot_rom,
            bus=args.bus,
            tdu=args.tdu,
            sched_mode=args.mode,
            peripherals=peripherals,
            pdk=args.pdk,
            target=args.target,
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

    elif args.config_author_cmd == "wake-demo":
        result = author.wake_demo_config(
            args.core_name,
            output_path=Path(args.output) if args.output else None,
        )
        _print_result(result, verbose=True)


def cmd_flow_runner(args):
    from .skills.flow_runner import FlowRunner
    runner = FlowRunner()

    if args.flow_runner_cmd == "list":
        result = runner.list_flows()
        _print_result(result, verbose=True)

    elif args.flow_runner_cmd == "run":
        if (
            os.environ.get("OH_MY_SOC_AGENT_TOOL") == "1"
            and args.flow_name in {"harden-classic", "harden-chip"}
        ):
            _print_result(
                SkillResult(
                    ok=False,
                    skill="flow-runner",
                    summary="physical flow requires an explicit user-run command",
                    errors=["omp agent-tool origin is not authorized for physical design"],
                ),
                verbose=True,
            )
        output = None
        if _PROGRESS_JSONL:
            output = lambda line: _progress("flow_output", line, flow=args.flow_name)
        elif not _JSON_MODE:
            output = lambda line: print(f"  │ {line}", flush=True)
        _progress("flow_start", f"running {args.flow_name}", flow=args.flow_name)
        result = runner.run(
            args.flow_name,
            config=args.config,
            on_output=output,
        )
        _progress(
            "flow_end",
            result.summary,
            flow=args.flow_name,
            ok=result.ok,
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


def cmd_soc_from_prompt(args):
    from .skills.soc_from_prompt import SocFromPrompt
    sfp = SocFromPrompt()

    if args.soc_from_prompt_cmd == "plan":
        result = sfp.plan(args.text, use_llm=args.llm)
        _print_result(result, verbose=True)

    elif args.soc_from_prompt_cmd == "run":
        result = sfp.run(args.text, execute=args.run, name=args.name,
                         use_llm=args.llm)
        _print_result(result, verbose=True)


def cmd_setup(args):
    from .skills.setup_wizard import SetupWizard
    wiz = SetupWizard()
    if args.setup_cmd == "show":
        _print_result(wiz.show(), verbose=True)
    else:
        result = wiz.configure(
            driver=args.driver, api_kind=args.api_kind, model=args.model,
            base_url=args.base_url, env_key=args.env_key,
            interactive=not args.non_interactive,
        )
        _print_result(result, verbose=True)


def cmd_agent(args):
    """Run the in-process agent loop or hand off to an interactive agent UI."""
    import shutil
    import subprocess
    from datetime import datetime, timezone

    from .agent import AgentRunner
    from .agent_tools import AgentToolRegistry
    from .events import (
        CompositeSink,
        EventStream,
        JsonlJournal,
        JsonlRenderer,
        TerminalRenderer,
    )
    from .llm import create_tool_provider
    from .skills.setup_wizard import load_user_config

    user_config = load_user_config()
    driver = args.driver or user_config.get("driver", "deterministic")
    text = args.text
    if driver in {"claude", "omp"}:
        unsupported = []
        for enabled, flag in (
            (args.dry_run, "--dry-run"),
            (args.name is not None, "--name"),
            (args.max_turns is not None, "--max-turns"),
            (args.allow_physical, "--allow-physical"),
            (args.allow_integration, "--allow-integration"),
            (args.headless, "--headless"),
            (args.events_jsonl, "--events-jsonl"),
            (args.quiet, "--quiet"),
            (args.no_color, "--no-color"),
            (args.no_tool_output, "--no-tool-output"),
            (args.require_evidence != "auto", "--require-evidence"),
        ):
            if enabled:
                unsupported.append(flag)
        if unsupported:
            result = SkillResult(
                ok=False,
                skill="agent",
                summary=f"external driver '{driver}' does not implement harness policy flags",
                errors=[
                    f"unsupported: {', '.join(unsupported)}; use driver=api or deterministic"
                ],
            )
            _print_result(result, verbose=True)
            return
        binary = shutil.which(driver)
        if binary is None:
            result = SkillResult(
                ok=False,
                skill="agent",
                summary=f"configured agent driver '{driver}' is not installed",
                errors=[f"'{driver}' was not found on PATH; run oh-my-soc setup"],
            )
            _print_result(result, verbose=True)
            return
        if _JSON_MODE:
            result = SkillResult(
                ok=False,
                skill="agent",
                summary=f"--json is not the {driver} event protocol",
                errors=[
                    "use --events-jsonl for headless streaming or run the "
                    "driver interactively"
                ],
            )
            _print_result(result, verbose=True)
            return
        if driver == "omp":
            prompt = (
                "Act as the MOSAIC-SoC agent. Read the project .claude/skills cards, "
                "make an explicit plan, use the oh_my_soc tool for every MOSAIC "
                "action, react to each gate result, and do not claim success "
                f"without evidence. User request: {text}"
            )
        else:
            prompt = (
                "Act as the MOSAIC-SoC agent. Read the project .claude/skills cards, "
                "make an explicit plan, invoke python3 -m harness commands as separate "
                "visible Bash tool calls, react to each JSON result, and do not claim "
                f"success without deterministic evidence. User request: {text}"
            )
        interactive = (
            sys.stdin.isatty()
            and sys.stdout.isatty()
        )
        if not interactive:
            result = SkillResult(
                ok=False,
                skill="agent",
                summary=f"external driver '{driver}' requires an interactive TTY",
                errors=["use driver=api for normalized headless JSONL sessions"],
            )
            _print_result(result, verbose=True)
            return
        command = _external_agent_command(
            driver, binary, prompt, interactive=interactive
        )
        print(
            f"Handing off to {driver} {'interactive UI' if interactive else 'event stream'}…",
            flush=True,
        )
        raise SystemExit(subprocess.call(command, cwd=str(Path(__file__).resolve().parents[1])))

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    journal = JsonlJournal(
        Path(__file__).resolve().parents[1]
        / "build"
        / "agent"
        / "sessions"
        / f"{timestamp}.jsonl"
    )
    sinks = [journal]
    if args.events_jsonl:
        sinks.insert(0, JsonlRenderer())
    elif not args.quiet and not _JSON_MODE:
        sinks.insert(
            0,
            TerminalRenderer(
                color=False if args.no_color else None,
                show_output=not args.no_tool_output,
            ),
        )
    events = EventStream(CompositeSink(*sinks))
    provider = None
    if driver == "api":
        api_config = user_config.get("api")
        if not isinstance(api_config, dict):
            result = SkillResult(
                ok=False,
                skill="agent",
                summary="API agent is not configured",
                errors=["run oh-my-soc setup --driver api --api-kind ..."],
            )
            journal.close()
            _print_result(result, verbose=True)
            return
        try:
            provider = create_tool_provider(api_config)
        except Exception as error:
            result = SkillResult(
                ok=False, skill="agent", summary=f"invalid API config: {error}", errors=[str(error)]
            )
            journal.close()
            _print_result(result, verbose=True)
            return
    registry = AgentToolRegistry(
        allow_write=not args.dry_run,
        allow_execute=not args.dry_run,
        allow_physical=args.allow_physical,
        allow_integration=args.allow_integration,
    )
    runner = AgentRunner(
        registry,
        events,
        provider=provider,
        max_turns=args.max_turns or 12,
    )
    try:
        result = runner.run(
            text,
            driver=driver,
            name=args.name,
            dry_run=args.dry_run,
            required_evidence=args.require_evidence,
        )
    finally:
        journal.close()
    result.details.setdefault("agent", {})["journal"] = str(journal.path)
    if _JSON_MODE:
        _print_result(result, verbose=True)
    elif args.events_jsonl:
        if not result.ok:
            raise SystemExit(1)
    elif not result.ok:
        raise SystemExit(1)


def cmd_wrapper_smith(args):
    from .skills.wrapper_smith import WrapperSmith
    ws = WrapperSmith()

    if args.wrapper_smith_cmd == "fetch":
        result = ws.fetch(args.url, name=args.name, subdir=args.subdir)
        _print_result(result, verbose=True)

    elif args.wrapper_smith_cmd == "analyze":
        result = ws.analyze(
            Path(args.rtl), top=args.top,
            out=Path(args.output) if args.output else None,
        )
        _print_result(result, verbose=True)

    elif args.wrapper_smith_cmd == "scaffold":
        if os.environ.get("OH_MY_SOC_AGENT_TOOL") == "1" and args.apply:
            _print_result(
                SkillResult(
                    ok=False,
                    skill="wrapper-smith",
                    summary="wrapper apply requires an explicit user-run command",
                    errors=["omp agent-tool origin may stage and review only"],
                ),
                verbose=True,
            )
        result = ws.scaffold(
            args.core_name,
            analysis=Path(args.from_analysis),
            apply=args.apply,
            vendor_from=Path(args.vendor_from) if args.vendor_from else None,
            family_override=args.family,
        )
        _print_result(result, verbose=True)

    elif args.wrapper_smith_cmd == "families":
        result = ws.families()
        _print_result(result, verbose=True)


def cmd_tb_smith(args):
    from .skills.tb_smith import TbSmith
    ts = TbSmith()

    if args.tb_smith_cmd == "generate":
        result = ts.generate(
            args.core_name,
            boot_addr=int(str(args.boot_addr), 0),
            unified=(True if args.unified else False if args.split else None),
            watchdog_cycles=args.watchdog,
            analysis=Path(args.analysis) if args.analysis else None,
        )
        _print_result(result, verbose=True)

    elif args.tb_smith_cmd == "run":
        result = ts.run(args.core_name, timeout=args.timeout)
        _print_result(result, verbose=True)

    elif args.tb_smith_cmd == "wake-demo":
        result = ts.wake_demo(args.core_name, execute=not args.config_only)
        _print_result(result, verbose=True)


def cmd_tb_matrix(args):
    from .skills.tb_matrix import TbMatrix
    tm = TbMatrix()

    if args.tb_matrix_cmd == "axes":
        result = tm.axes()
        _print_result(result, verbose=True)

    elif args.tb_matrix_cmd == "plan":
        result = tm.plan(tier=args.tier)
        _print_result(result, verbose=True)

    elif args.tb_matrix_cmd == "run":
        result = tm.run(tier=args.tier, limit=args.limit,
                        resume=not args.no_resume)
        _print_result(result, verbose=True)

    elif args.tb_matrix_cmd == "report":
        result = tm.report()
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
    # Convert cooperative tool cancellation (including the omp custom tool's
    # SIGTERM) into Python's normal unwind path so run_cmd can terminate the
    # complete EDA process group rather than orphaning simulator descendants.
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _cancel_handler)
    parser = _StrictArgumentParser(
        prog="oh-my-soc",
        description="Agentic harness for MOSAIC-SoC EDA flows (based on oh-my-pi)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--json", action="store_true",
                        help="Emit the raw SkillResult JSON (machine mode; "
                             "exit code 1 on failure)")
    parser.add_argument(
        "--progress-jsonl",
        action="store_true",
        help="Emit live progress JSON Lines on stderr while --json stays clean",
    )
    subparsers = parser.add_subparsers(dest="skill", help="Skill to use")

    # config-author
    ca = subparsers.add_parser("config-author", help="Generate/validate mosaic.yaml")
    ca_sub = ca.add_subparsers(dest="config_author_cmd", required=True)

    ca_gen = ca_sub.add_parser("generate", help="Generate a config")
    ca_gen.add_argument("--name", default="mosaic_soc", help="SoC name")
    ca_gen.add_argument("--core", action="append", help="Core spec: ip:count:role (repeatable)")
    ca_gen.add_argument("--sram", type=int, default=32, help="SRAM KB")
    ca_gen.add_argument("--boot-rom", type=int, default=2, help="Boot ROM KB")
    ca_gen.add_argument("--bus", choices=("obi", "log", "floonoc"), default="obi")
    ca_gen.add_argument("--pdk", choices=("gf180mcu", "sky130"), default="gf180mcu")
    ca_gen.add_argument(
        "--target", choices=("rtl", "simulation", "tapeout"), default="rtl",
        help="Implementation intent; tapeout activates the strict physical matrix",
    )
    ca_gen.add_argument("--tdu", action="store_true", help="Enable TDU")
    ca_gen.add_argument("--mode", default="static", help="Scheduling mode")
    ca_gen.add_argument("--peripheral", help="Comma-separated peripherals")
    ca_gen.add_argument("--preset", help="Use a named preset")
    ca_gen.add_argument("--output", help="Output path")

    ca_val = ca_sub.add_parser("validate", help="Validate a config file")
    ca_val.add_argument("file", help="Path to mosaic.yaml")

    ca_sub.add_parser("presets", help="List available presets")

    ca_wake = ca_sub.add_parser("wake-demo",
                                help="Emit the canonical 3-hart wake-demo config for a core")
    ca_wake.add_argument("core_name", help="Worker core ip (e.g. picorv32)")
    ca_wake.add_argument("--output", help="Output path (default configs/mosaic_<core>.yaml)")

    # flow-runner
    fr = subparsers.add_parser("flow-runner", help="Run EDA flows")
    fr_sub = fr.add_subparsers(dest="flow_runner_cmd", required=True)

    fr_sub.add_parser("list", help="List available flows")

    fr_run = fr_sub.add_parser("run", help="Run a flow")
    fr_run.add_argument("flow_name", help="Flow to run")
    fr_run.add_argument("--config", help="Config path for mosaic-gen")

    # drc-triage
    dt = subparsers.add_parser("drc-triage", help="Analyze DRC/LVS reports")
    dt_sub = dt.add_subparsers(dest="drc_triage_cmd", required=True)

    dt_analyze = dt_sub.add_parser("analyze", help="Analyze a report file")
    dt_analyze.add_argument("file", help="Report file path")
    dt_analyze.add_argument("--format", help="Report format (magic/klayout/netgen/auto)")

    dt_scan = dt_sub.add_parser("scan", help="Scan a directory for reports")
    dt_scan.add_argument("directory", help="Directory to scan")

    # doc-gen
    dg = subparsers.add_parser("doc-gen", help="Generate documentation")
    dg_sub = dg.add_subparsers(dest="doc_gen_cmd", required=True)

    dg_config = dg_sub.add_parser("config", help="Config summary doc")
    dg_config.add_argument("file", help="Path to mosaic.yaml")

    dg_sub.add_parser("memory-map", help="Memory-map reference doc")

    dg_dash = dg_sub.add_parser("dashboard", help="Dashboard summary")
    dg_dash.add_argument("--file", help="Dashboard path (default: DASHBOARD.md)")

    # wrapper-smith
    ws = subparsers.add_parser(
        "wrapper-smith",
        help="Wrap any open-source core/IP: analyze bus protocol + scaffold SCI integration")
    ws_sub = ws.add_subparsers(dest="wrapper_smith_cmd", required=True)

    ws_fetch = ws_sub.add_parser(
        "fetch", help="Clone + pin a core repo: <url>[@<ref-or-commit>]")
    ws_fetch.add_argument("url", help="Repo URL, optionally @ref or @commit")
    ws_fetch.add_argument("--name", help="Local name (default: repo basename)")
    ws_fetch.add_argument("--subdir",
                          help="RTL subdirectory inside the repo (e.g. hdl)")

    ws_an = ws_sub.add_parser("analyze", help="Parse ports + classify the native bus")
    ws_an.add_argument("rtl", help="RTL file or directory")
    ws_an.add_argument("--top", help="Top module name")
    ws_an.add_argument("-o", "--output", help="Analysis JSON output path")

    ws_sc = ws_sub.add_parser("scaffold",
                              help="Stage wrapper + all integration touchpoints")
    ws_sc.add_argument("core_name", help="Core name (lowercase, e.g. hazard3)")
    ws_sc.add_argument("--from", dest="from_analysis", required=True,
                       help="analysis.json from `analyze`")
    ws_sc.add_argument("--apply", action="store_true",
                       help="Apply to the tree (default: dry-run into build/)")
    ws_sc.add_argument("--vendor-from", help="Copy vendor RTL from this directory")
    ws_sc.add_argument("--family", help="Override the classified family")

    ws_sub.add_parser("families", help="List protocol families")

    # tb-smith
    ts = subparsers.add_parser(
        "tb-smith", help="Generate + run per-core verification (TB + wake demo)")
    ts_sub = ts.add_subparsers(dest="tb_smith_cmd", required=True)

    ts_gen = ts_sub.add_parser("generate", help="Emit tb/sci/<core>/ TB assets")
    ts_gen.add_argument("core_name")
    ts_gen.add_argument("--boot-addr", default="0x180")
    ts_gen.add_argument("--watchdog", type=int, default=200_000)
    ts_gen.add_argument("--unified", action="store_true")
    ts_gen.add_argument("--split", action="store_true")
    ts_gen.add_argument("--analysis", help="wrapper-smith analysis.json")

    ts_run = ts_sub.add_parser("run", help="Run the generated TB")
    ts_run.add_argument("core_name")
    ts_run.add_argument("--timeout", type=int, default=600)

    ts_wd = ts_sub.add_parser("wake-demo", help="Full-SoC wake demo for the core")
    ts_wd.add_argument("core_name")
    ts_wd.add_argument("--config-only", action="store_true",
                       help="Write the config without running the sim")

    # tb-matrix
    tm = subparsers.add_parser(
        "tb-matrix",
        help="Combination-coverage testing of the SoC integration space")
    tm_sub = tm.add_subparsers(dest="tb_matrix_cmd", required=True)

    tm_sub.add_parser("axes", help="Show the registry-derived axes")

    tm_plan = tm_sub.add_parser(
        "plan", help="Enumerate the covering set for a tier (no execution)")
    tm_plan.add_argument("--tier", default="render",
                         choices=["validate", "render", "sim"])

    tm_run = tm_sub.add_parser(
        "run", help="Execute a tier's gate on every planned config")
    tm_run.add_argument("--tier", default="validate",
                        choices=["validate", "render", "sim"])
    tm_run.add_argument("--limit", type=int, default=None,
                        help="Run at most N not-yet-passing configs")
    tm_run.add_argument("--no-resume", action="store_true",
                        help="Re-run configs that already passed")

    tm_sub.add_parser("report", help="Summarize all recorded tier results")

    # soc-from-prompt
    sfp = subparsers.add_parser(
        "soc-from-prompt",
        help="Deterministic natural-language -> SoC pipeline (no LLM needed)")
    sfp_sub = sfp.add_subparsers(dest="soc_from_prompt_cmd", required=True)

    sfp_plan = sfp_sub.add_parser("plan", help="Parse only — show the grammar's reading")
    sfp_plan.add_argument("text", help="The natural-language SoC request")
    sfp_plan.add_argument("--llm", action="store_true",
                          help="Translate intent via the configured api driver "
                               "(oh-my-soc setup); grammar fallback on failure")

    sfp_run = sfp_sub.add_parser("run", help="Write the config (+ --run: verify pipeline)")
    sfp_run.add_argument("text", help="The natural-language SoC request")
    sfp_run.add_argument("--run", action="store_true",
                         help="Execute the gated pipeline (mosaic-gen + wake demo)")
    sfp_run.add_argument("--name", help="SoC/config name override")
    sfp_run.add_argument("--llm", action="store_true",
                         help="Translate intent via the configured api driver")

    # setup (omp-style driver/provider picker)
    st = subparsers.add_parser(
        "setup", help="Choose the intent driver: deterministic | claude | omp | api")
    st_sub = st.add_subparsers(dest="setup_cmd")
    st_sub.add_parser("show", help="Show the current driver config + detection")
    st_cfg = st_sub.add_parser("configure", help="Configure (interactive without flags)")
    for p in (st, st_cfg):
        p.add_argument("--driver", choices=["deterministic", "claude", "omp", "api"])
        p.add_argument(
            "--api-kind",
            choices=["anthropic", "openai", "opencode-go"],
            dest="api_kind",
        )
        p.add_argument("--model", help="Model override (default per provider)")
        p.add_argument("--base-url", dest="base_url",
                       help="API base URL (fixed automatically for opencode-go)")
        p.add_argument("--env-key", dest="env_key",
                       help="Env var holding the API key (never stored)")
        p.add_argument("--non-interactive", action="store_true")

    # agent (dispatch to the configured driver)
    ag = subparsers.add_parser(
        "agent", help="Run a visible model/tool agent or deterministic workflow")
    ag.add_argument("text", help="Natural-language MOSAIC request")
    ag.add_argument(
        "--driver",
        choices=["deterministic", "claude", "omp", "api"],
        help="Override the configured driver for this session",
    )
    ag.add_argument("--name", help="Generated SoC name for deterministic workflow")
    ag.add_argument("--dry-run", action="store_true", help="Read/plan only; deny writes and execution")
    ag.add_argument("--max-turns", type=int, default=None, help="Bound API agent turns (default: 12)")
    ag.add_argument(
        "--require-evidence",
        choices=[
            "auto",
            "analysis",
            "config",
            "rtl",
            "simulation",
            "physical",
            "integration",
            "testbench",
            "documentation",
            "drc",
        ],
        default="auto",
        help="Lock completion/side-effect scope; auto derives a conservative ceiling from the user request",
    )
    ag.add_argument(
        "--allow-physical",
        action="store_true",
        help="Allow an API agent to invoke registered physical flows",
    )
    ag.add_argument(
        "--allow-integration",
        action="store_true",
        help="Allow wrapper-scaffold to apply changes outside its staging area",
    )
    ag.add_argument("--headless", action="store_true", help="Use external-driver headless mode")
    ag.add_argument(
        "--events-jsonl",
        action="store_true",
        help="Emit one normalized agent event per JSON line",
    )
    ag.add_argument("--quiet", action="store_true", help="Write the journal without terminal events")
    ag.add_argument("--no-color", action="store_true")
    ag.add_argument("--no-tool-output", action="store_true", help="Hide live child lines but retain results")

    # topo-viz
    tv = subparsers.add_parser("topo-viz",
                               help="Semantic config checks + topology diagram")
    tv_sub = tv.add_subparsers(dest="topo_viz_cmd", required=True)

    tv_check = tv_sub.add_parser("check", help="Semantic checks on a config")
    tv_check.add_argument("file", help="mosaic.yaml-style config")

    tv_render = tv_sub.add_parser("render", help="Render the topology diagram")
    tv_render.add_argument("file", help="mosaic.yaml-style config")
    tv_render.add_argument("-o", "--output", help="Output file (.html or .svg)")
    tv_render.add_argument("--svg", action="store_true",
                           help="Emit a plain SVG instead of HTML")

    args = parser.parse_args()

    if args.json and getattr(args, "events_jsonl", False):
        parser.error("--json and --events-jsonl are mutually exclusive")

    global _JSON_MODE, _PROGRESS_JSONL
    _JSON_MODE = args.json
    _PROGRESS_JSONL = args.progress_jsonl

    if not args.skill:
        # omp-style first run: bare interactive invocation with no saved
        # config launches the driver picker (never in pipes/CI — TTY only).
        from .skills.setup_wizard import CONFIG_PATH, SetupWizard
        if sys.stdin.isatty() and sys.stdout.isatty() and not CONFIG_PATH.exists():
            print("First run — no driver configured yet.")
            _print_result(SetupWizard().configure(), verbose=False)
            print("\nNow try:  oh-my-soc agent \"an SoC with one cv32e20 "
                  "controller and two picorv32 workers, tdu, a uart\"")
            sys.exit(0)
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
        "soc-from-prompt": cmd_soc_from_prompt,
        "wrapper-smith": cmd_wrapper_smith,
        "tb-smith": cmd_tb_smith,
        "tb-matrix": cmd_tb_matrix,
        "setup": cmd_setup,
        "agent": cmd_agent,
    }

    dispatch[args.skill](args)


if __name__ == "__main__":
    main()
