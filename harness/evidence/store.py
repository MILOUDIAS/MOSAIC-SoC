"""A content-addressed evidence store, keyed on everything that produced it.

ROADMAP M2: "immutable content-addressed evidence store", plus the two
invalidation criteria -- "changing config, RTL, firmware, workload, SDC/UPF,
PDK views, or tool image invalidates the correct descendants" and "changing a
parser or FlowSpec invalidates dependent evidence".

THE IDEA, WHICH IS SMALLER THAN IT SOUNDS
-----------------------------------------
Invalidation is not a mechanism here. The key IS the digest of the inputs, so
asking "is my evidence still valid?" is asking "does a record exist under the
key today's inputs produce?" -- and if any input moved, it does not. There is
no cache to sweep and no dependency graph to walk, which is the point: a graph
that has to be maintained is a graph that drifts.

WHAT COUNTS AS AN INPUT
-----------------------
Six things, each read from a real artefact rather than asserted:

  rtl_bundle    the content-addressed FuseSoC bundle the RTL came from,
                recovered from the run's own VERILOG_FILES paths
  config_digest the hardening config, MINUS the resolved file list -- those
                are absolute paths that differ per machine and are already
                covered by rtl_bundle. Including them would make evidence
                un-shareable between two checkouts of the same commit.
  pdk           `gf180mcuD` today. GF180 is the first target, not the only
                one; IHP, SkyWater, FreePDK and ASAP are planned, and a
                measurement carries no meaning without the process it was
                taken on.
  std_cell      the library within that PDK, which changes cell areas and
                every timing number
  tool          librelane version plus the flake lock's narHash -- the version
                string alone does not identify a build
  parser        a digest of the modules that READ the run. M2 asks for this
                explicitly, and it is the one input nobody thinks of: fixing a
                parser bug changes what the numbers mean while every other
                input stays put.

WHAT IT DELIBERATELY DOES NOT HASH
----------------------------------
The PDK views themselves. GF180's clone is 1.2 GB and hashing it on every
lookup would make the store slower than the parse it protects. The PDK name
and standard-cell library are recorded instead, which catches a PDK swap but
not an in-place edit of a PDK file. That is a real gap and it is stated here
rather than papered over: if PDK views start being patched locally, this needs
a digest of the specific views a run consumed.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# The modules whose behaviour decides what a metric MEANS. Narrow on purpose:
# hashing the whole package would invalidate every record when a docstring
# changed, and an invalidation nobody believes is one everybody overrides.
PARSER_MODULES: Tuple[str, ...] = (
    "harness/evidence/metric.py",
    "harness/evidence/librelane.py",
    "harness/evidence/signoff.py",
    "harness/physical/report.py",
)

# Keys excluded from the config digest: machine-specific absolute paths that
# the RTL bundle digest already covers.
_VOLATILE_CONFIG_KEYS = frozenset({
    "VERILOG_FILES", "VERILOG_INCLUDE_DIRS", "PDK_ROOT", "MAGIC_PDK_SETUP",
    "STD_CELL_LIBRARY_OPT",
})

_BUNDLE = re.compile(r"/build/mosaic/([A-Za-z0-9_]+-[0-9a-f]{12})/")


class EvidenceConflict(Exception):
    """A key already holds different content. Evidence is immutable."""


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parser_digest(repo_root: Path) -> str:
    """Digest of the modules that interpret a run.

    Missing modules are recorded as absent rather than skipped: a parser that
    disappeared is a change, and silently producing the same digest would
    reuse evidence derived by code that no longer exists.
    """
    parts = []
    for relative in PARSER_MODULES:
        path = repo_root / relative
        if path.is_file():
            parts.append(f"{relative}:{_sha256_text(path.read_text())}")
        else:
            parts.append(f"{relative}:ABSENT")
    return _sha256_text("\n".join(parts))


def tool_digest(librelane_version: Optional[str], flake_lock: Optional[Path]) -> str:
    """Version string plus the flake lock's hash for librelane.

    The version alone does not identify a build -- two 3.0.0 images from
    different nixpkgs are different tools with different results.
    """
    parts = [f"librelane:{librelane_version or 'unknown'}"]
    if flake_lock and flake_lock.is_file():
        try:
            nodes = json.loads(flake_lock.read_text()).get("nodes", {})
        except json.JSONDecodeError:
            nodes = {}
        for name, node in sorted(nodes.items()):
            locked = node.get("locked") or {}
            stamp = locked.get("narHash") or locked.get("rev")
            if stamp and "librelane" in name.lower():
                parts.append(f"{name}:{stamp}")
    return _sha256_text("|".join(parts))


def config_digest(resolved: Dict[str, Any]) -> str:
    """Digest of a resolved config, minus machine-specific paths."""
    stripped = {k: v for k, v in resolved.items()
                if k not in _VOLATILE_CONFIG_KEYS}
    return _sha256_text(json.dumps(stripped, sort_keys=True, default=str))


def bundle_from_config(resolved: Dict[str, Any]) -> Optional[str]:
    """The RTL bundle a run consumed, from its own source paths."""
    for path in resolved.get("VERILOG_FILES") or []:
        match = _BUNDLE.search(str(path))
        if match:
            return match.group(1)
    return None


@dataclass(frozen=True)
class EvidenceInputs:
    """Everything that decides what a run's numbers mean."""

    rtl_bundle: Optional[str]
    config_digest: str
    pdk: Optional[str]
    std_cell_library: Optional[str]
    tool: str
    parser: str

    def key(self) -> str:
        return _sha256_text(json.dumps(asdict(self), sort_keys=True))

    @classmethod
    def from_run(cls, run_dir: Path, *, repo_root: Path,
                 flake_lock: Optional[Path] = None) -> Optional["EvidenceInputs"]:
        resolved_path = run_dir / "resolved.json"
        if not resolved_path.is_file():
            return None
        resolved = json.loads(resolved_path.read_text())
        meta = resolved.get("meta") or {}
        if flake_lock is None:
            flake_lock = repo_root / "flow/librelane/flake.lock"
        return cls(
            rtl_bundle=bundle_from_config(resolved),
            config_digest=config_digest(resolved),
            pdk=resolved.get("PDK"),
            std_cell_library=resolved.get("STD_CELL_LIBRARY"),
            tool=tool_digest(meta.get("librelane_version"), flake_lock),
            parser=parser_digest(repo_root),
        )


@dataclass(frozen=True)
class EvidenceRecord:
    """One immutable measurement set, addressed by its inputs."""

    inputs: EvidenceInputs
    design: Optional[str]
    run_dir: str
    summary: Dict[str, Any] = field(default_factory=dict)
    # Supplied by the caller, never generated here: a timestamp inside the
    # record would be fine, but one inside the KEY would make the store
    # non-deterministic and defeat the whole design.
    recorded_at: Optional[str] = None

    @property
    def key(self) -> str:
        return self.inputs.key()

    def to_json(self) -> str:
        return json.dumps(
            {"key": self.key, "inputs": asdict(self.inputs),
             "design": self.design, "run_dir": self.run_dir,
             "summary": self.summary, "recorded_at": self.recorded_at},
            indent=2, sort_keys=True, default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceRecord":
        return cls(
            inputs=EvidenceInputs(**data["inputs"]),
            design=data.get("design"),
            run_dir=data.get("run_dir", ""),
            summary=data.get("summary") or {},
            recorded_at=data.get("recorded_at"),
        )


class EvidenceStore:
    """Immutable, content-addressed, on disk.

    `build/evidence/<first two hex>/<key>.json`. Sharded because a flat
    directory of thousands of files is slow to list on some filesystems, and
    listing is what `find` does.
    """

    def __init__(self, root: Path):
        self.root = Path(root)

    def path_for(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def put(self, record: EvidenceRecord) -> Path:
        """Write, or confirm an identical record already exists.

        Re-recording identical evidence is a no-op, not an error: two runs
        legitimately produce the same key when nothing changed. Writing
        DIFFERENT content under the same key is a contradiction -- the inputs
        claim to determine the output and here they did not -- so it raises.
        """
        target = self.path_for(record.key)
        payload = record.to_json()
        if target.is_file():
            existing = target.read_text()
            if json.loads(existing) == json.loads(payload):
                return target
            raise EvidenceConflict(
                f"{record.key[:12]} already holds different evidence. The same "
                "inputs produced two different results, so at least one input "
                "is not being captured. Do not overwrite -- find the missing "
                f"input. Stored: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload)
        return target

    def get(self, key: str) -> Optional[EvidenceRecord]:
        path = self.path_for(key)
        if not path.is_file():
            return None
        return EvidenceRecord.from_dict(json.loads(path.read_text()))

    def lookup(self, inputs: EvidenceInputs) -> Optional[EvidenceRecord]:
        """Evidence for exactly these inputs, or None.

        None is the answer to "has anything changed?" -- there is no separate
        staleness check, because a changed input produces a different key.
        """
        return self.get(inputs.key())

    def records(self) -> Iterable[EvidenceRecord]:
        if not self.root.is_dir():
            return
        for path in sorted(self.root.glob("*/*.json")):
            try:
                yield EvidenceRecord.from_dict(json.loads(path.read_text()))
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

    def find(self, **criteria: Any) -> List[EvidenceRecord]:
        """Records whose inputs match every given field.

        `store.find(pdk="gf180mcuD")` answers "what would a PDK swap
        invalidate", which is M2's descendant question asked the practical way
        round.
        """
        out = []
        for record in self.records():
            values = asdict(record.inputs)
            if all(values.get(k) == v for k, v in criteria.items()):
                out.append(record)
        return out

    def invalidated_by(self, **changed: Any) -> List[EvidenceRecord]:
        """Records that depended on an input which has now changed.

        Same as `find`, named for the question being asked. Every record
        matching the OLD value is invalid once that input moves.
        """
        return self.find(**changed)
