"""A session-scoped MCP stdio server over the typed harness registry.

WHAT THIS FIXES
---------------
`oh-my-soc agent --driver claude` used to be a `subprocess.call`: the external
agent received a prompt and then acted with no scope ceiling, no evidence
binding and no completion gate. Every one of those rules existed in
`AgentRunner` and applied to nothing the external drivers did. A prompt asking
for a simulation could end with a physical-design flow, and nothing in the
harness would have objected.

This server puts the same gates in front of an external client. It speaks MCP
over stdio, so Claude Code, Codex, Cursor and oh-my-pi all reach it from one
artifact, and it holds ONE `AgentState` for the life of the process: evidence
recorded by one call is what a later call is gated against.

THE CEILING IS AN INPUT, NOT A NEGOTIATION
------------------------------------------
`--request` is the user's actual request. The ceiling is derived from it with
the same `classify_request_scope` the built-in loop uses, and it is LOCKED
before the client connects. A client cannot widen it, because the only tool
that sets scope refuses any value other than the authorized one.

This is the whole point, so it is worth being blunt: a client that never calls
`request_scope` gets refused on every gated tool, and a client that calls it
with a wider scope gets refused too.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
No shell, no file editor, no "allow all tools" escape. The registry executes
registered harness operations only. Upstream projects reviewed for this work
ship `--dangerously-skip-permissions`, `--yolo` and `danger-full-access`; the
survey concluded WP-1 must not weaken our position for convenience, and it
does not.

PROTOCOL
--------
JSON-RPC 2.0, one message per line, on stdin/stdout — hand-rolled rather than
taking an `mcp` dependency for three methods (`initialize`, `tools/list`,
`tools/call`). stdout carries protocol ONLY; anything human-readable goes to
stderr, because a stray print corrupts the stream.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, TextIO

from .agent_tools import TOOL_SPECS, AgentToolRegistry
from .core import REPO_ROOT, SkillResult

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "oh-my-soc"


@dataclass
class GatedSession:
    """One `AgentState`, one locked ceiling, and the shared gates in front.

    The built-in loop and this server both run tools through `execute`, so a
    refusal here is the same refusal produced in-process — not a second
    implementation that agrees today.
    """

    registry: AgentToolRegistry
    authorized_scope: str
    request: str = ""
    scope_required: bool = True
    state: Any = field(default=None)

    def __post_init__(self) -> None:
        from .agent import AgentState

        if self.state is None:
            repo_root = Path(
                getattr(self.registry, "repo_root", REPO_ROOT)).resolve()
            self.state = AgentState(repo_root=repo_root)
        # Lock the ceiling before any client can speak. `scope_locked` is what
        # makes `request_scope` refuse a widening value.
        self.state.required_scope = self.authorized_scope
        self.state.scope_locked = True
        self.state.user_request = self.request

    def execute(self, name: str, arguments: Mapping[str, Any]) -> SkillResult:
        """Gate, execute, record. The order is the policy."""
        from .gates import gate_precondition

        precondition = gate_precondition(
            self.state, self.registry, self.scope_required, name, arguments)
        if precondition is not None:
            return precondition
        try:
            result = self.registry.execute(name, arguments)
        except Exception as error:                 # noqa: BLE001 - reported
            result = SkillResult(
                ok=False, skill=name,
                summary=f"tool '{name}' rejected the request: {error}",
                errors=[str(error)])
        # Recording happens for failures too: a refused call is evidence about
        # the session, and `observe` is what keeps digests current.
        self.state.observe(name, arguments, result)
        return result

    def completion_error(self) -> Optional[str]:
        return self.state.completion_error()


def _error(request_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id,
            "error": {"code": code, "message": message}}


def _result(request_id: Any, payload: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def _tool_content(result: SkillResult) -> Dict[str, Any]:
    """An MCP tool result carrying the SkillResult verbatim.

    `isError` is set for a refusal so the client cannot read a gate failure as
    success, and the full JSON is included because the errors list is the part
    that tells the model what to do instead.
    """
    return {
        "content": [{"type": "text", "text": result.to_json()}],
        "isError": not result.ok,
    }


class MCPServer:
    """The stdio loop. One session, for the life of the process."""

    def __init__(self, session: GatedSession, *,
                 stdin: Optional[TextIO] = None,
                 stdout: Optional[TextIO] = None):
        self.session = session
        self.stdin = stdin if stdin is not None else sys.stdin
        self.stdout = stdout if stdout is not None else sys.stdout

    # ── protocol ─────────────────────────────────────────────────────
    def handle(self, message: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}

        # A notification has no id and takes no reply, ever. Answering one is
        # a protocol violation that some clients treat as fatal.
        is_notification = "id" not in message

        if method == "initialize":
            return _result(request_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": "0.3.0"},
                # Not decoration: the client should say this to the model, so
                # it knows the ceiling before it wastes a turn on a refusal.
                "instructions": (
                    f"Every MOSAIC action goes through these tools. The "
                    f"authorized outcome scope for this session is "
                    f"'{self.session.authorized_scope}', derived from the "
                    f"user's request and locked — call request_scope with "
                    f"exactly that value first. Tools outside the ceiling are "
                    f"refused, and success requires deterministic evidence."
                ),
            })

        if is_notification:
            return None

        if method == "tools/list":
            return _result(request_id, {
                "tools": [
                    {"name": spec.name,
                     "description": spec.description,
                     "inputSchema": spec.parameters}
                    for spec in TOOL_SPECS
                ]
            })

        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not isinstance(name, str):
                return _error(request_id, -32602, "tools/call needs a name")
            result = self.session.execute(name, arguments)
            return _result(request_id, _tool_content(result))

        if method == "ping":
            return _result(request_id, {})

        return _error(request_id, -32601, f"unknown method {method!r}")

    def serve_forever(self) -> int:
        for line in self.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as error:
                self._send(_error(None, -32700, f"parse error: {error}"))
                continue
            try:
                response = self.handle(message)
            except Exception as error:             # noqa: BLE001 - protocol
                # A crash must not take the session's evidence with it: report
                # and keep serving.
                self._send(_error(message.get("id"), -32603, str(error)))
                continue
            if response is not None:
                self._send(response)
        return 0

    def _send(self, payload: Mapping[str, Any]) -> None:
        self.stdout.write(json.dumps(payload) + "\n")
        self.stdout.flush()


def build_session(request: str, *, repo_root: Path = REPO_ROOT,
                  required_evidence: str = "auto",
                  allow_write: bool = True,
                  allow_execute: bool = True) -> GatedSession:
    """Derive and lock the ceiling exactly as the built-in loop does."""
    from .agent import classify_request_scope

    scope = (classify_request_scope(request)
             if required_evidence == "auto" else required_evidence)
    registry = AgentToolRegistry(
        repo_root=repo_root,
        allow_write=allow_write,
        allow_execute=allow_execute,
        allow_physical=(scope == "physical"),
        allow_integration=(scope in {"integration", "physical"}),
    )
    return GatedSession(registry=registry, authorized_scope=scope,
                        request=request)
