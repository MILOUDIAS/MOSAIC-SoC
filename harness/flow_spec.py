"""Typed flow declarations: effect, cost, scope and approval, with no default.

ROADMAP M2, last exit criterion: "every flow declares effect, cost, required
scope, and approval with no default."

THE DEFECT THIS CLOSES
----------------------
`harness/gates.py` is fail-closed for TOOLS -- a tool missing from the scope
table is refused with "fail-closed tool authorization". For FLOWS it was
fail-OPEN, and it decided authorization by reading the flow's NAME:

    if flow in AgentToolRegistry.PHYSICAL_FLOWS:
        flow_scopes = {"physical"}
    elif flow.startswith("tb-") or flow in {"verilator-run", "pytest"}:
        flow_scopes = {"testbench", "simulation", "integration", "physical"}
    else:
        flow_scopes = {"rtl", "simulation", "integration", "physical"}

So a new flow got rtl-level authorization silently, and a simulation flow that
happened not to start with `tb-` got a wider scope than it should. Adding a
flow without deciding what may run it SUCCEEDED. "No default" means that has
to be impossible, and here it is an import-time error.

WHY EACH FIELD
--------------
`effect` -- read, write or execute. The same vocabulary `AgentToolSpec` uses,
so a flow and a tool can be reasoned about together.

`cost` -- what running it spends. Not a timeout, which is a limit: this is the
expectation, and it is the difference between a driver running something and
asking first. Measured, not guessed: `harden-classic` is HOURS because the runs
in this project took 2 h 19 m to 11 h.

`scopes` -- the request scopes that may run it, stated rather than inferred
from a prefix.

`approval` -- whether scope alone is insufficient. Physical flows consume hours
of compute and produce tapeout candidates; a correct scope is necessary and
not sufficient for those.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, FrozenSet, Mapping

# Every request scope the policy classifier can derive. A flow declaring a
# scope outside this set is a typo, and typos in an authorization table are
# how a flow becomes unreachable or over-permitted.
REQUEST_SCOPES: FrozenSet[str] = frozenset({
    "analysis", "config", "rtl", "simulation", "physical",
    "integration", "testbench", "documentation", "drc",
})


class Effect(Enum):
    """What running the flow does to the tree. Matches AgentToolSpec."""

    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"


class Cost(Enum):
    """What it spends. An expectation, unlike `timeout`, which is a limit."""

    SECONDS = "seconds"
    MINUTES = "minutes"
    HOURS = "hours"


class FlowSpecError(ValueError):
    """A flow that does not declare its policy. Raised at import."""


REQUIRED_FIELDS = ("effect", "cost", "scopes", "approval")


@dataclass(frozen=True)
class FlowSpec:
    """One flow's policy, separate from how it is executed."""

    name: str
    description: str
    effect: Effect
    cost: Cost
    scopes: FrozenSet[str]
    approval: bool

    def permits(self, scope: str) -> bool:
        return scope in self.scopes

    @classmethod
    def from_mapping(cls, name: str, entry: Mapping[str, Any]) -> "FlowSpec":
        missing = [f for f in REQUIRED_FIELDS if f not in entry]
        if missing:
            raise FlowSpecError(
                f"flow {name!r} does not declare {missing}. Every flow states "
                "its effect, cost, scopes and approval explicitly -- there is "
                "no default, because a flow whose authorization nobody chose "
                "used to inherit one from its name prefix")

        try:
            effect = Effect(entry["effect"])
        except ValueError:
            raise FlowSpecError(
                f"flow {name!r}: effect {entry['effect']!r} is not one of "
                f"{[e.value for e in Effect]}") from None
        try:
            cost = Cost(entry["cost"])
        except ValueError:
            raise FlowSpecError(
                f"flow {name!r}: cost {entry['cost']!r} is not one of "
                f"{[c.value for c in Cost]}") from None

        scopes = frozenset(entry["scopes"])
        if not scopes:
            raise FlowSpecError(
                f"flow {name!r} declares no scopes, so nothing could ever run "
                "it. Delete it or say who may")
        unknown = scopes - REQUEST_SCOPES
        if unknown:
            raise FlowSpecError(
                f"flow {name!r} declares unknown scope(s) {sorted(unknown)}; "
                f"valid scopes are {sorted(REQUEST_SCOPES)}")

        approval = entry["approval"]
        if not isinstance(approval, bool):
            raise FlowSpecError(
                f"flow {name!r}: approval must be a bool, got {approval!r}")

        return cls(name=name, description=str(entry.get("description", "")),
                   effect=effect, cost=cost, scopes=scopes, approval=approval)


def build_specs(flows: Mapping[str, Mapping[str, Any]]) -> Dict[str, FlowSpec]:
    """Type every flow, or refuse the whole table.

    All-or-nothing on purpose: a partially typed table invites the same
    fallback this module exists to delete.
    """
    return {name: FlowSpec.from_mapping(name, entry)
            for name, entry in flows.items()}
