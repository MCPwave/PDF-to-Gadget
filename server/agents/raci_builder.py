"""
@raci_builder  — RACI matrix generator for the PDF-to-Gadget pipeline.

Takes hw_map + driver_info list (from kernel_scout.lookup_drivers) and
produces:
  - raci_html  : color-coded HTML table with Ubuntu Core version analysis
  - raci_csv   : CSV string
  - raci_json  : list of row dicts
  - recommended_uc : "UC22" | "UC24" | "UC26" (lowest risk)
"""
from __future__ import annotations
import csv
import io
import html as html_lib
import re
from typing import List, Dict, Tuple

# ── RACI roles ─────────────────────────────────────────────────────────────────
_R = "BSP Engineer"
_A = "HW Architect"
_I = "PM / Integration"

# ── Ubuntu Core → base kernel version ─────────────────────────────────────────
_UC_KERNELS: dict[str, Tuple[int, int]] = {
    "UC22": (5, 15),   # Ubuntu 22.04 LTS — Linux 5.15 LTS
    "UC24": (6,  8),   # Ubuntu 24.04 LTS — Linux 6.8 LTS
    "UC26": (7,  0),   # Ubuntu 26.04 LTS — Linux 7.0
}

# Risk weight per UC driver status (lower = better)
_UC_RISK = {
    "native":   0,   # driver in-tree for that kernel
    "backport": 2,   # mainline but requires backport patch
    "vendor":   5,   # out-of-tree BSP driver
    "unknown":  8,   # no driver found
}

# ── Status badge colours ───────────────────────────────────────────────────────
_STATUS_COLOR = {
    "mainline": ("#1a4d1a", "#66ff66"),
    "backport": ("#4d3d00", "#ffcc00"),
    "wip":      ("#4d3d00", "#ffcc00"),
    "vendor":   ("#4d1f00", "#ff8800"),
    "unknown":  ("#4d0000", "#ff4444"),
}

# UC cell colours
_UC_CELL = {
    "native":   ("background:#1a3d1a;color:#66ff66", "✅ native"),
    "backport": ("background:#3d3000;color:#ffcc00", "🔧 backport"),
    "vendor":   ("background:#3d1800;color:#ff8800", "📦 vendor"),
    "unknown":  ("background:#3d0000;color:#ff4444", "❓ unknown"),
}

_EFFORT_LABEL = {
    "low":         "🟢 Low",
    "medium":      "🟡 Medium",
    "high":        "🟠 High",
    "investigate": "🔴 Investigate",
}


# ── Version helpers ────────────────────────────────────────────────────────────

def _parse_ver(s: str) -> Tuple[int, int]:
    """'v5.15' or '5.15' or 'v2.6.34' → (5, 15). Unknown → (999, 0)."""
    m = re.search(r"(\d+)\.(\d+)", s or "")
    if not m:
        return (999, 0)
    return (int(m.group(1)), int(m.group(2)))


def _uc_driver_status(driver_status: str, since: str, uc_kernel: Tuple[int, int]) -> str:
    """Return UC-specific availability: native / backport / vendor / unknown."""
    if driver_status in ("vendor", "wip"):
        return "vendor"
    if driver_status == "unknown":
        return "unknown"
    # mainline or backport: check if since <= uc_kernel
    since_ver = _parse_ver(since)
    if since_ver <= uc_kernel:
        return "native"
    return "backport"


# ── Public API ─────────────────────────────────────────────────────────────────

def build(hw_map: dict, drivers: List[Dict]) -> dict:
    board = hw_map.get("board_name") or "Custom Board"
    soc   = hw_map.get("soc") or "Unknown SoC"

    rows        = _build_rows(drivers)
    recommended = _recommend_uc(rows)

    return {
        "raci_html":       _to_html(rows, board, soc, recommended),
        "raci_csv":        _to_csv(rows),
        "raci_json":       rows,
        "recommended_uc":  recommended,
    }


# ── Internal ───────────────────────────────────────────────────────────────────

def _build_rows(drivers: List[Dict]) -> List[Dict]:
    rows = []
    for d in drivers:
        drv_status = d.get("status", "unknown")
        since      = d.get("kernel_since", "unknown")

        # per-UC availability
        uc_status = {
            uc: _uc_driver_status(drv_status, since, kver)
            for uc, kver in _UC_KERNELS.items()
        }

        rows.append({
            "peripheral":    d.get("peripheral_name", d.get("peripheral_id", "")),
            "type":          d.get("peripheral_type", ""),
            "driver_module": d.get("driver_module", "unknown"),
            "kernel_since":  since,
            "kconfig":       d.get("kconfig", ""),
            "source_path":   d.get("source_path", ""),
            "status":        drv_status,
            "effort":        d.get("effort", "investigate"),
            "github_url":    d.get("github_url", ""),
            "github_repo_name": d.get("github_repo_name", ""),
            "github_repo_url": d.get("github_repo_url", ""),
            # UC availability
            "UC22": uc_status["UC22"],
            "UC24": uc_status["UC24"],
            "UC26": uc_status["UC26"],
            # RACI — team roles only
            "R": _R,
            "A": _A,
            "C": "Upstream Team",
            "I": _I,
        })
    return rows


def _recommend_uc(rows: List[Dict]) -> str:
    """Pick UC version with lowest total risk score."""
    if not rows:
        return "UC24"
    scores = {uc: sum(_UC_RISK.get(r[uc], 8) for r in rows) for uc in _UC_KERNELS}
    return min(scores, key=scores.__getitem__)


def _risk_summary(rows: List[Dict], uc: str) -> dict:
    counts: dict[str, int] = {"native": 0, "backport": 0, "vendor": 0, "unknown": 0}
    for r in rows:
        counts[r[uc]] = counts.get(r[uc], 0) + 1
    return counts


def _to_html(rows: List[Dict], board: str, soc: str, recommended: str) -> str:
    if not rows:
        return "<p style='color:#888'>No peripheral data available.</p>"

    # ── Recommendation banner ─────────────────────────────────────────────────
    rec_kernel = ".".join(str(x) for x in _UC_KERNELS[recommended])
    banners = []
    for uc, kver in _UC_KERNELS.items():
        s     = _risk_summary(rows, uc)
        score = sum(_UC_RISK.get(k, 8) * v for k, v in s.items())
        kstr  = ".".join(str(x) for x in kver)
        is_rec = uc == recommended
        bg     = "#1a3d1a" if is_rec else "#1a1a2e"
        border = "2px solid #66ff66" if is_rec else "1px solid #333"
        crown  = " 👑 Recommended" if is_rec else ""
        banners.append(
            f'<div class="uc-card" style="background:{bg};border:{border};">'
            f'<div class="uc-card-title">{uc}{crown}</div>'
            f'<div class="uc-card-sub">Linux {kstr}</div>'
            f'<div class="uc-card-score">Risk score: <strong>{score}</strong></div>'
            f'<div class="uc-card-counts">'
            f'<span style="color:#66ff66">✅ {s["native"]} native</span> &nbsp;'
            f'<span style="color:#ffcc00">🔧 {s["backport"]} backport</span> &nbsp;'
            f'<span style="color:#ff8800">📦 {s["vendor"]} vendor</span> &nbsp;'
            f'<span style="color:#ff4444">❓ {s["unknown"]} unknown</span>'
            f'</div></div>'
        )

    banner_html = (
        f'<div class="uc-banner">'
        f'<div class="uc-banner-label">Ubuntu Core analysis — '
        f'<strong style="color:#66ff66">{recommended}</strong> (Linux {rec_kernel}) '
        f'has lowest risk for this hardware</div>'
        f'<div class="uc-cards">{"".join(banners)}</div>'
        f'</div>'
    )

    # ── Table ─────────────────────────────────────────────────────────────────
    uc_headers = "".join(
        f'<th class="uc-col{" uc-rec" if uc == recommended else ""}" '
        f'title="Ubuntu Core {uc[-2:]}: Linux {"·".join(str(x) for x in kver)}">'
        f'{uc}</th>'
        for uc, kver in _UC_KERNELS.items()
    )

    thead = f"""
    <thead>
      <tr>
        <th>Peripheral</th>
        <th>Type</th>
        <th>Driver Module</th>
        <th>Repo</th>
        <th>Since</th>
        <th>Kconfig</th>
        <th>Status</th>
        <th>Effort</th>
        {uc_headers}
        <th title="Responsible">R</th>
        <th title="Accountable">A</th>
        <th title="Consulted: upstream maintainer">C</th>
        <th title="Informed">I</th>
      </tr>
    </thead>"""

    tbody_rows = []
    for r in rows:
        status   = r["status"]
        effort   = r["effort"]
        bg, fg   = _STATUS_COLOR.get(status, ("#2a2a3a", "#888888"))
        efflabel = _EFFORT_LABEL.get(effort, effort)

        gh = r.get("github_url", "")
        mod_cell = (
            f'<a href="{html_lib.escape(gh)}" target="_blank">'
            f'{html_lib.escape(r["driver_module"])}</a>'
            if gh else html_lib.escape(r["driver_module"])
        )
        repo_url = r.get("github_repo_url", "")
        repo_name = r.get("github_repo_name", "")
        repo_cell = (
            f'<a href="{html_lib.escape(repo_url)}" target="_blank">'
            f'{html_lib.escape(repo_name)}</a>'
            if repo_url else html_lib.escape(repo_name or "—")
        )

        src = r.get("source_path", "")
        src_tip = html_lib.escape(src) if src not in ("N/A", "unknown", "") else ""

        c_full  = html_lib.escape(r["C"])
        c_short = c_full if len(c_full) <= 38 else c_full[:35] + "…"

        # UC cells
        uc_cells = ""
        for uc in _UC_KERNELS:
            us      = r[uc]
            style, label = _UC_CELL.get(us, ("", us))
            extra = ' class="uc-rec"' if uc == recommended else ""
            uc_cells += f'<td style="{style};text-align:center;font-size:11px;"{extra}>{label}</td>'

        tbody_rows.append(f"""
      <tr>
        <td><strong>{html_lib.escape(r['peripheral'])}</strong></td>
        <td><code>{html_lib.escape(r['type'])}</code></td>
        <td>{mod_cell}</td>
        <td>{repo_cell}</td>
        <td>{html_lib.escape(r['kernel_since'])}</td>
        <td><code title="{src_tip}">{html_lib.escape(r['kconfig'])}</code></td>
        <td><span class="raci-badge" style="background:{bg};color:{fg};">{html_lib.escape(status)}</span></td>
        <td>{efflabel}</td>
        {uc_cells}
        <td class="raci-r" title="{html_lib.escape(_R)}">R</td>
        <td class="raci-a" title="{html_lib.escape(_A)}">A</td>
        <td class="raci-c" title="Upstream Team">C</td>
        <td class="raci-i" title="{html_lib.escape(_I)}">I</td>
      </tr>""")

    legend = f"""
    <div class="raci-legend">
      <strong>{html_lib.escape(board)}</strong> · {html_lib.escape(soc)}
      &nbsp;|&nbsp;
      <span style="color:#66ff66">🟢 mainline</span> &nbsp;
      <span style="color:#ffcc00">🟡 backport/wip</span> &nbsp;
      <span style="color:#ff8800">🟠 vendor</span> &nbsp;
      <span style="color:#ff4444">🔴 unknown</span>
      &nbsp;|&nbsp;
      <strong>R</strong>=Responsible &nbsp;
      <strong>A</strong>=Accountable &nbsp;
      <strong>C</strong>=Consulted &nbsp;
      <strong>I</strong>=Informed
    </div>"""

    return f"""
<div class="raci-wrap">
  {banner_html}
  {legend}
  <div class="raci-table-scroll">
    <table class="raci-table">
      {thead}
      <tbody>{''.join(tbody_rows)}
      </tbody>
    </table>
  </div>
</div>"""


def _to_csv(rows: List[Dict]) -> str:
    if not rows:
        return ""
    buf    = io.StringIO()
    fields = ["peripheral", "type", "driver_module", "kernel_since",
              "kconfig", "source_path", "status", "effort",
              "github_repo_name", "github_repo_url",
              "UC22", "UC24", "UC26", "R", "A", "C", "I"]
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()
