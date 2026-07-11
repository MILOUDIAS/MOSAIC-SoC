"""topo-viz — semantic config checks + interactive topology visualization.

Inspired by soc-topgen-ui (refs/IP_Interconnect_Catalog/soc-topgen-ui): the
reusable ideas are a schema-validated config, semantic checks beyond schema
(address overlap, fabric constraints), and an interactive topology view. Here
both are implemented against mosaic.yaml for all three bus fabrics
(obi / log / floonoc), rendering a SELF-CONTAINED HTML file (inline SVG +
~60 lines of pan/zoom JS, no external resources).

CLI:
    python -m harness topo-viz check  mosaic.yaml
    python -m harness topo-viz render mosaic.yaml -o topology.html [--svg]
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from ..core import SkillResult, validate_config, REPO_ROOT

try:
    import hjson
except ImportError:  # pragma: no cover
    hjson = None

DMA_MASTER_PORTS_DEFAULT = 2  # configs/general.hjson dma.num_master_ports


# ── Config digestion ─────────────────────────────────────────────────


def _load_yaml(path: Path) -> Dict[str, Any]:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _base_windows(base_config: Path) -> List[Dict[str, Any]]:
    """Non-RAM address windows from the base HJSON (authoritative source)."""
    if hjson is None or not base_config.exists():
        # Fallback: the documented x-heep map
        return [
            {"name": "DEBUG", "start": 0x1000_0000, "size": 0x0010_0000},
            {"name": "AO_PERIPHERAL", "start": 0x2000_0000, "size": 0x0010_0000},
            {"name": "PERIPHERAL", "start": 0x3000_0000, "size": 0x0010_0000},
            {"name": "FLASH_MEM", "start": 0x4000_0000, "size": 0x0100_0000},
            {"name": "EXT_SLAVES", "start": 0xF000_0000, "size": 0x0100_0000},
        ]
    cfg = hjson.load(open(base_config))

    def _i(v):
        return int(str(v), 0)

    return [
        {"name": "DEBUG", "start": _i(cfg["debug"]["address"]),
         "size": _i(cfg["debug"]["length"])},
        {"name": "AO_PERIPHERAL", "start": _i(cfg["ao_peripherals"]["address"]),
         "size": _i(cfg["ao_peripherals"]["length"])},
        {"name": "PERIPHERAL", "start": _i(cfg["peripherals"]["address"]),
         "size": _i(cfg["peripherals"]["length"])},
        {"name": "FLASH_MEM", "start": _i(cfg["flash_mem"]["address"]),
         "size": _i(cfg["flash_mem"]["length"])},
        {"name": "EXT_SLAVES", "start": _i(cfg["ext_slaves"]["address"]),
         "size": _i(cfg["ext_slaves"]["length"])},
    ]


def _digest(soc: Dict[str, Any]) -> Dict[str, Any]:
    """Derive the topology quantities every check/render needs."""
    cores = soc.get("cores", [])
    harts = []
    for grp in cores:
        for i in range(int(grp.get("count", 1))):
            harts.append({"ip": grp.get("ip", "?"), "role": grp.get("role", "?")})
    nh = len(harts)
    bus = str(soc.get("bus", "obi")).strip().lower()
    sram_kb = int(soc.get("memory", {}).get("sram_kb", 32))
    dma_ports = DMA_MASTER_PORTS_DEFAULT
    n_masters = 2 * max(1, nh) + 1 + 3 * dma_ports
    opts = soc.get("bus_opts", {}) or {}
    nb = opts.get("log", {}).get("num_banks", "auto")
    if bus == "log":
        num_banks = (1 << (n_masters - 1).bit_length()) if nb == "auto" else int(nb)
    else:
        num_banks = 2  # base config default (code_and_data, 2 banks)
    return {
        "harts": harts,
        "nh": nh,
        "bus": bus,
        "sram_kb": sram_kb,
        "dma_ports": dma_ports,
        "n_masters": n_masters,
        "num_banks": num_banks,
        "bus_opts": opts,
    }


# ── Semantic checks ──────────────────────────────────────────────────


def semantic_checks(soc: Dict[str, Any], base_config: Path) -> List[str]:
    """Checks beyond the mosaic.yaml schema. Returns findings (empty = clean)."""
    findings: List[str] = []
    d = _digest(soc)

    # LOG bank constraint (mirrors XHeep._validate_log_bus)
    if d["bus"] == "log":
        required = 1 << (d["n_masters"] - 1).bit_length()
        nb = d["num_banks"]
        if nb < d["n_masters"] or (nb & (nb - 1)) != 0:
            findings.append(
                f"bus:log needs num_banks >= {d['n_masters']} bus masters and a "
                f"power of two (required >= {required}, got {nb})"
            )
        elif d["sram_kb"] % nb != 0 or d["sram_kb"] // nb < 1:
            findings.append(
                f"bus:log with {nb} banks needs sram_kb divisible by the bank "
                f"count with >= 1 KB per bank (sram_kb={d['sram_kb']})"
            )
        topo = d["bus_opts"].get("log", {}).get("topology", "lic")
        if topo in ("bfly2", "bfly4") and (d["n_masters"] & (d["n_masters"] - 1)) != 0:
            findings.append(
                f"bus_opts.log.topology '{topo}' requires a power-of-two master "
                f"count (got {d['n_masters']}); use 'lic'"
            )

    # bus_opts for fabrics other than the selected one are inert
    for fabric in d["bus_opts"]:
        if fabric not in ("log", "floonoc"):
            findings.append(f"bus_opts.{fabric}: unknown fabric")
        elif fabric != d["bus"]:
            findings.append(
                f"note: bus_opts.{fabric} is inert (selected bus is '{d['bus']}')"
            )

    # Derived address map: RAM window vs the base-config windows
    windows = [{"name": "RAM", "start": 0, "size": d["sram_kb"] * 1024}]
    windows += _base_windows(base_config)
    ordered = sorted(windows, key=lambda w: w["start"])
    for a, b in zip(ordered, ordered[1:]):
        if a["start"] + a["size"] > b["start"]:
            findings.append(
                f"address overlap: {a['name']} "
                f"[{a['start']:#010x}, {a['start'] + a['size']:#010x}) overlaps "
                f"{b['name']} starting at {b['start']:#010x}"
            )

    # Duplicate hart roles sanity: exactly one titan group
    titan_groups = [g for g in soc.get("cores", []) if g.get("role") == "titan"]
    if len(titan_groups) > 1:
        findings.append("more than one core group has role 'titan'")

    return findings


# ── Topology model (columns of nodes + edges) ────────────────────────


def _build_columns(d: Dict[str, Any]) -> Tuple[List[Dict], List[Tuple]]:
    """Return (columns, edges); columns = [{title, nodes:[{label, sub, kind}]}],
    edges = [(col_a, node_a, col_b, node_b)]."""
    masters = []
    for h, hart in enumerate(d["harts"]):
        masters.append({"label": f"hart {h}: {hart['ip']}",
                        "sub": f"{hart['role']} (I+D)", "kind": "master"})
    masters.append({"label": "debug", "sub": "DM master", "kind": "master"})
    masters.append({"label": "iDMA", "sub": f"{d['dma_ports']}x3 ports", "kind": "master"})

    slaves = [{"label": f"SRAM x{d['num_banks']}",
               "sub": f"{d['sram_kb']} KB total", "kind": "mem"}]
    for name in ("DEBUG", "AO_PERIPHERAL", "PERIPHERAL", "FLASH_MEM", "ERROR"):
        slaves.append({"label": name, "sub": "", "kind": "slave"})

    cols: List[Dict] = [{"title": "Masters", "nodes": masters}]
    edges: List[Tuple] = []
    nm = len(masters)

    if d["bus"] == "obi":
        cols.append({"title": "Fabric", "nodes": [
            {"label": "OBI crossbar", "sub": f"xbar_varlat {d['n_masters']}x"
             f"{d['num_banks'] + 5} (NtoM)", "kind": "fabric"}]})
        cols.append({"title": "Slaves", "nodes": slaves})
        for i in range(nm):
            edges.append((0, i, 1, 0))
        for j in range(len(slaves)):
            edges.append((1, 0, 2, j))

    elif d["bus"] == "log":
        topo = d["bus_opts"].get("log", {}).get("topology", "lic").upper()
        cols.append({"title": "Tier demux", "nodes": [
            {"label": "per-master 1-to-2", "sub": "[0, MEM_SIZE) vs rest",
             "kind": "demux"}]})
        cols.append({"title": "Fabric", "nodes": [
            {"label": f"tcdm_interconnect ({topo})",
             "sub": f"{d['n_masters']} -> {d['num_banks']} banks, word-interleaved",
             "kind": "fabric"},
            {"label": "OBI crossbar", "sub": "varlat, non-memory tier",
             "kind": "fabric"}]})
        cols.append({"title": "Slaves", "nodes": slaves})
        for i in range(nm):
            edges.append((0, i, 1, 0))
        edges += [(1, 0, 2, 0), (1, 0, 2, 1)]
        edges.append((2, 0, 3, 0))  # LIC -> banks
        for j in range(1, len(slaves)):
            edges.append((2, 1, 3, j))

    elif d["bus"] == "floonoc":
        merges = [{"label": f"hart {h} I+D merge", "sub": "2-to-1", "kind": "demux"}
                  for h in range(d["nh"])]
        merges.append({"label": "shared merge", "sub": "debug+DMA", "kind": "demux"})
        bridges_in = [{"label": "obi_to_axi", "sub": "32-bit AXI", "kind": "bridge"}
                      for _ in range(d["nh"] + 1)]
        noc = [{"label": "floo_mosaic_noc", "sub":
                f"1 router, {d['nh'] + 3} endpoints (floogen)", "kind": "fabric"}]
        bridges_out = [
            {"label": "axi_to_obi (mem)", "sub": "-> bank demux", "kind": "bridge"},
            {"label": "axi_to_obi (periph)", "sub": "-> 1-to-5 demux", "kind": "bridge"},
        ]
        cols.append({"title": "Merge", "nodes": merges})
        cols.append({"title": "Bridges", "nodes": bridges_in})
        cols.append({"title": "NoC", "nodes": noc})
        cols.append({"title": "Endpoints", "nodes": bridges_out})
        cols.append({"title": "Slaves", "nodes": slaves})
        for h in range(d["nh"]):
            edges.append((0, h, 1, h))
        edges += [(0, d["nh"], 1, d["nh"]), (0, d["nh"] + 1, 1, d["nh"])]
        for m in range(d["nh"] + 1):
            edges.append((1, m, 2, m))
            edges.append((2, m, 3, 0))
        edges += [(3, 0, 4, 0), (3, 0, 4, 1)]
        edges.append((4, 0, 5, 0))
        for j in range(1, len(slaves)):
            edges.append((4, 1, 5, j))

    return cols, edges


# ── SVG / HTML rendering ─────────────────────────────────────────────

KIND_FILL = {
    "master": "var(--c-master)",
    "demux": "var(--c-demux)",
    "bridge": "var(--c-bridge)",
    "fabric": "var(--c-fabric)",
    "mem": "var(--c-mem)",
    "slave": "var(--c-slave)",
}

NODE_W, NODE_H, COL_GAP, ROW_GAP, PAD = 190, 46, 90, 16, 30


def _svg(cols: List[Dict], edges: List[Tuple]) -> Tuple[str, int, int]:
    height = max(len(c["nodes"]) for c in cols) * (NODE_H + ROW_GAP) + 2 * PAD + 20
    width = len(cols) * (NODE_W + COL_GAP) - COL_GAP + 2 * PAD

    def pos(ci: int, ni: int) -> Tuple[float, float]:
        n = len(cols[ci]["nodes"])
        total = n * NODE_H + (n - 1) * ROW_GAP
        y0 = (height - total) / 2
        return (PAD + ci * (NODE_W + COL_GAP), y0 + ni * (NODE_H + ROW_GAP))

    parts = []
    for (ca, na, cb, nb) in edges:
        xa, ya = pos(ca, na)
        xb, yb = pos(cb, nb)
        x1, y1 = xa + NODE_W, ya + NODE_H / 2
        x2, y2 = xb, yb + NODE_H / 2
        mx = (x1 + x2) / 2
        parts.append(
            f'<path class="edge" d="M {x1:.0f} {y1:.0f} C {mx:.0f} {y1:.0f}, '
            f'{mx:.0f} {y2:.0f}, {x2:.0f} {y2:.0f}"/>'
        )
    for ci, col in enumerate(cols):
        x = PAD + ci * (NODE_W + COL_GAP)
        parts.append(
            f'<text class="coltitle" x="{x + NODE_W / 2:.0f}" y="{PAD - 10}">'
            f"{html.escape(col['title'])}</text>"
        )
        for ni, node in enumerate(col["nodes"]):
            _, y = pos(ci, ni)
            fill = KIND_FILL.get(node["kind"], "var(--c-slave)")
            parts.append(
                f'<g><rect x="{x}" y="{y:.0f}" width="{NODE_W}" height="{NODE_H}" '
                f'rx="7" fill="{fill}" class="node"/>'
                f'<text x="{x + NODE_W / 2}" y="{y + 19:.0f}" class="lbl">'
                f"{html.escape(node['label'])}</text>"
                f'<text x="{x + NODE_W / 2}" y="{y + 35:.0f}" class="sub">'
                f"{html.escape(node['sub'])}</text></g>"
            )
    svg = (
        f'<svg id="topo" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg">{"".join(parts)}</svg>'
    )
    return svg, width, height


HTML_TMPL = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title}</title><style>
:root {{ --bg:#ffffff; --fg:#1a1a2e; --edge:#9aa4b2; --c-master:#dbeafe;
  --c-demux:#fef3c7; --c-bridge:#fde2e2; --c-fabric:#dcfce7; --c-mem:#ede9fe;
  --c-slave:#f1f5f9; --line:#cbd5e1; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0f172a; --fg:#e2e8f0;
  --edge:#475569; --c-master:#1e3a5f; --c-demux:#4a3b12; --c-bridge:#4c1d1d;
  --c-fabric:#14432a; --c-mem:#312e5e; --c-slave:#1e293b; --line:#334155; }} }}
body {{ margin:0; font:14px/1.5 system-ui,sans-serif; background:var(--bg);
  color:var(--fg); }}
main {{ max-width:1200px; margin:0 auto; padding:24px; }}
#wrap {{ border:1px solid var(--line); border-radius:10px; overflow:hidden;
  cursor:grab; }}
svg {{ display:block; width:100%; height:auto; }}
.node {{ stroke:var(--line); stroke-width:1; }}
.lbl {{ text-anchor:middle; font-size:12px; font-weight:600; fill:var(--fg); }}
.sub {{ text-anchor:middle; font-size:10px; fill:var(--fg); opacity:.65; }}
.coltitle {{ text-anchor:middle; font-size:12px; font-weight:700;
  fill:var(--fg); opacity:.75; }}
.edge {{ fill:none; stroke:var(--edge); stroke-width:1.2; opacity:.7; }}
table {{ border-collapse:collapse; margin-top:24px; width:100%; }}
th,td {{ border:1px solid var(--line); padding:6px 12px; text-align:left;
  font-size:13px; }}
th {{ background:var(--c-slave); }}
code {{ font-family:ui-monospace,monospace; }}
h1 {{ font-size:20px; }} .meta {{ opacity:.7; font-size:13px; }}
</style></head><body><main>
<h1>{title}</h1>
<p class="meta">{meta}</p>
<div id="wrap">{svg}</div>
<h2>Memory map</h2>
<table><tr><th>Region</th><th>Start</th><th>End</th><th>Size</th></tr>
{memmap}
</table>
</main><script>
(function () {{
  var svg = document.getElementById('topo'), wrap = document.getElementById('wrap');
  var vb = svg.viewBox.baseVal, ow = vb.width, oh = vb.height;
  wrap.addEventListener('wheel', function (e) {{
    e.preventDefault();
    var k = e.deltaY < 0 ? 0.9 : 1.1;
    var nw = Math.min(Math.max(vb.width * k, ow * 0.2), ow * 4);
    var nh = nw * oh / ow;
    vb.x += (vb.width - nw) / 2; vb.y += (vb.height - nh) / 2;
    vb.width = nw; vb.height = nh;
  }}, {{passive: false}});
  var drag = null;
  wrap.addEventListener('mousedown', function (e) {{
    drag = {{x: e.clientX, y: e.clientY}}; wrap.style.cursor = 'grabbing';
  }});
  window.addEventListener('mouseup', function () {{
    drag = null; wrap.style.cursor = 'grab';
  }});
  window.addEventListener('mousemove', function (e) {{
    if (!drag) return;
    var s = vb.width / wrap.clientWidth;
    vb.x -= (e.clientX - drag.x) * s; vb.y -= (e.clientY - drag.y) * s;
    drag = {{x: e.clientX, y: e.clientY}};
  }});
}})();
</script></body></html>
"""


class TopoViz:
    """Semantic checks + topology rendering for mosaic.yaml configs."""

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or REPO_ROOT

    def _load(self, cfg_path: Path):
        raw = _load_yaml(cfg_path)
        soc = raw.get("soc")
        if not soc:
            return None, SkillResult(
                ok=False, skill="topo-viz",
                summary=f"{cfg_path}: missing top-level 'soc' key",
                errors=["missing 'soc'"],
            )
        return soc, None

    def check(self, cfg_path: Path,
              base_config: Optional[Path] = None) -> SkillResult:
        soc, err = self._load(cfg_path)
        if err:
            return err
        base = base_config or (self.repo_root / "configs/general.hjson")
        schema_errors = validate_config({"soc": soc})
        findings = semantic_checks(soc, base)
        hard = schema_errors + [f for f in findings if not f.startswith("note:")]
        notes = [f for f in findings if f.startswith("note:")]
        return SkillResult(
            ok=not hard,
            skill="topo-viz",
            summary=(f"{cfg_path.name}: clean" if not hard else
                     f"{cfg_path.name}: {len(hard)} finding(s)"),
            details={"findings": findings, "schema_errors": schema_errors,
                     "notes": notes},
            errors=hard,
        )

    def render(self, cfg_path: Path, output: Optional[Path] = None,
               svg_only: bool = False,
               base_config: Optional[Path] = None) -> SkillResult:
        soc, err = self._load(cfg_path)
        if err:
            return err
        base = base_config or (self.repo_root / "configs/general.hjson")
        d = _digest(soc)
        cols, edges = _build_columns(d)
        svg, _, _ = _svg(cols, edges)

        windows = [{"name": "RAM", "start": 0, "size": d["sram_kb"] * 1024}]
        windows += _base_windows(base)
        rows = "\n".join(
            f"<tr><td><code>{html.escape(w['name'])}</code></td>"
            f"<td><code>{w['start']:#010x}</code></td>"
            f"<td><code>{w['start'] + w['size']:#010x}</code></td>"
            f"<td>{w['size'] // 1024} KB</td></tr>"
            for w in sorted(windows, key=lambda w: w["start"])
        )
        name = soc.get("name", cfg_path.stem)
        meta = (f"bus: <code>{d['bus']}</code> · {d['nh']} harts · "
                f"{d['n_masters']} bus masters · {d['num_banks']} RAM banks · "
                f"{d['sram_kb']} KB SRAM")
        doc = svg if svg_only else HTML_TMPL.format(
            title=f"MOSAIC-SoC topology — {html.escape(name)}",
            meta=meta, svg=svg, memmap=rows,
        )
        out = output or cfg_path.with_suffix(".svg" if svg_only else ".html")
        Path(out).write_text(doc)
        return SkillResult(
            ok=True, skill="topo-viz",
            summary=f"rendered {d['bus']} topology -> {out}",
            details={"output": str(out), "bus": d["bus"],
                     "columns": [c["title"] for c in cols],
                     "node_count": sum(len(c["nodes"]) for c in cols),
                     "edge_count": len(edges)},
        )
