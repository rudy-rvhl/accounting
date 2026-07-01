"""Render statements (and advisory) to styled HTML, and optionally to PDF.

HTML is always available; PDF requires the optional ``weasyprint`` dependency (installed
with ``pip install qcre[pdf]``). Every rendered document carries the standard disclaimer.
"""

from __future__ import annotations

from qcre import DISCLAIMER
from qcre.cfo.advisory import AdvisoryItem
from qcre.reports.statements import Statement

_CSS = """
:root { --ink:#1f2933; --muted:#6b7280; --rule:#d1d5db; --accent:#0f766e; --bg:#f8fafc; }
* { box-sizing: border-box; }
body { font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
       color: var(--ink); margin: 0; padding: 24px; background: var(--bg); }
.doc { max-width: 880px; margin: 0 auto; }
.statement { background:#fff; border:1px solid var(--rule); border-radius:10px;
             padding: 22px 26px; margin-bottom: 22px; box-shadow:0 1px 2px rgba(0,0,0,.04); }
h1 { font-size: 20px; margin: 0 0 2px; }
h2 { font-size: 16px; margin: 0 0 14px; color: var(--accent); }
.subtitle { color: var(--muted); font-size: 13px; margin-bottom: 14px; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
td { padding: 3px 0; vertical-align: bottom; }
td.amt { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
tr.bold td { font-weight: 700; }
tr.underline td { border-bottom: 1px solid var(--ink); }
tr.section td { padding-top: 8px; }
.neg { color: #b91c1c; }
.disclaimer { font-size: 11px; color: var(--muted); border-top:1px solid var(--rule);
              padding-top: 12px; margin-top: 4px; }
.adv { border-left: 4px solid var(--accent); padding: 10px 14px; margin: 8px 0;
       background:#fff; border-radius: 0 8px 8px 0; }
.adv.critical { border-color:#b91c1c; } .adv.warning { border-color:#d97706; }
.adv.opportunity { border-color:#0f766e; } .adv.info { border-color:#6b7280; }
.adv .tag { font-size:11px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }
.adv .title { font-weight:700; margin:2px 0; }
.adv .impact { font-weight:700; }
"""


def _amount_cell(line) -> str:
    if line.amount is None:
        return ""
    txt = line.amount.format()
    cls = "amt neg" if line.amount.is_negative() else "amt"
    return f'<td class="{cls}">{txt}</td>'


def statement_to_html(st: Statement) -> str:
    rows = []
    for ln in st.lines:
        classes = []
        if ln.bold:
            classes.append("bold")
        if ln.underline:
            classes.append("underline")
        if ln.amount is None:
            classes.append("section")
        pad = ln.indent * 18
        amt = _amount_cell(ln)
        if not amt:
            amt = "<td></td>"
        rows.append(
            f'<tr class="{" ".join(classes)}">'
            f'<td style="padding-left:{pad}px">{ln.label}</td>{amt}</tr>'
        )
    return (
        f'<div class="statement"><h2>{st.title}</h2>'
        f'<div class="subtitle">{st.subtitle}</div>'
        f'<table>{"".join(rows)}</table></div>'
    )


def advisory_to_html(items: list[AdvisoryItem]) -> str:
    if not items:
        return ""
    blocks = ['<div class="statement"><h2>CFO Advisory & Tax Optimization</h2>']
    for it in items:
        impact = f'<div class="impact">Estimated impact: {it.impact.format()}</div>' if it.impact else ""
        blocks.append(
            f'<div class="adv {it.severity.value}"><div class="tag">{it.severity.value} · {it.category}</div>'
            f'<div class="title">{it.title}</div><div>{it.message}</div>{impact}</div>'
        )
    blocks.append("</div>")
    return "".join(blocks)


def render_document(
    title: str,
    statements: list[Statement],
    *,
    advisory: list[AdvisoryItem] | None = None,
    extra_html: str = "",
) -> str:
    body = [f'<div class="doc"><h1>{title}</h1>']
    body.append(extra_html)
    for st in statements:
        body.append(statement_to_html(st))
    if advisory:
        body.append(advisory_to_html(advisory))
    body.append(f'<div class="statement disclaimer">{DISCLAIMER}</div>')
    body.append("</div>")
    return (
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{title}</title><style>{_CSS}</style></head>"
        f"<body>{''.join(body)}</body></html>"
    )


def write_html(path: str, html: str) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return path


def write_pdf(path: str, html: str) -> str:
    """Render *html* to a PDF at *path*. Requires the optional weasyprint dependency."""
    try:
        from weasyprint import HTML
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "PDF export requires weasyprint. Install with: pip install qcre[pdf]"
        ) from exc
    HTML(string=html).write_pdf(path)
    return path
