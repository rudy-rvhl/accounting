"""Command-line interface for the Quebec real-estate accounting engine.

    qcre seed                       build and store the demo company
    qcre statements --year 2026     print / export financial statements
    qcre tax                        corporate tax position, CCA, SIB/SBD, advisory
    qcre kpis                       portfolio KPIs
    qcre advisory                   CFO advisory & tax-optimization flags
    qcre transfer-duty 500000       quick welcome-tax calculation
    qcre citations                  show the dated, sourced rate book

Most commands accept ``--db PATH``; if the file does not exist they fall back to the
built-in demo company so the tool is useful immediately.
"""

from __future__ import annotations

import os
from decimal import Decimal

import typer

from qcre import DISCLAIMER, __version__
from qcre.company import Company
from qcre.core.money import Money
from qcre.reports.framework import Framework

app = typer.Typer(add_completion=False, help="Quebec real-estate accounting, tax & CFO engine.")


def _load(db: str | None) -> Company:
    if db and os.path.exists(db):
        from qcre.db.store import load_company
        return load_company(db)
    from qcre.sample import build_sample_company
    return build_sample_company()


def _hr(title: str) -> None:
    typer.echo("\n" + title)
    typer.echo("=" * max(len(title), 60))


def _print_statement(st) -> None:
    _hr(st.title)
    typer.echo(st.subtitle + "\n")
    for ln in st.lines:
        amt = ln.amount.format() if ln.amount is not None else ""
        label = "  " * ln.indent + ln.label
        line = label.ljust(50) + amt.rjust(18)
        typer.echo(typer.style(line, bold=ln.bold))


@app.command()
def version() -> None:
    """Show the version."""
    typer.echo(f"qcre {__version__}")


@app.command()
def seed(db: str = typer.Option("qcre.db", help="Database path to create")) -> None:
    """Build the demo company and store it."""
    from qcre.db.store import seed as do_seed
    do_seed(db)
    typer.echo(f"Seeded demo company → {db}")


@app.command()
def statements(
    db: str = typer.Option(None, help="Company database (defaults to demo)"),
    framework: str = typer.Option("ASPE", help="ASPE or IFRS"),
    out: str = typer.Option(None, help="Write HTML to this path"),
    pdf: str = typer.Option(None, help="Write PDF to this path"),
) -> None:
    """Print the financial statements (and optionally export HTML/PDF)."""
    from qcre.reports.statements import FinancialStatements

    co = _load(db)
    fw = Framework(framework.upper())
    fs = FinancialStatements(co.ledger, co.fiscal_year, entity_name=co.entity_name, framework=fw)
    sts = fs.all_statements()
    for st in sts:
        _print_statement(st)
    if out or pdf:
        from qcre.reports.render import render_document, write_html, write_pdf
        html = render_document(f"{co.entity_name} — {co.fiscal_year.label} Financial Statements", sts)
        if out:
            write_html(out, html)
            typer.echo(f"\nHTML → {out}")
        if pdf:
            write_pdf(pdf, html)
            typer.echo(f"PDF → {pdf}")
    typer.echo("\n" + typer.style(DISCLAIMER, dim=True))


@app.command()
def tax(db: str = typer.Option(None, help="Company database (defaults to demo)")) -> None:
    """Compute the corporate tax position, CCA, SIB/SBD determination and advisory."""
    from qcre.analysis import tax_position

    co = _load(db)
    pos = tax_position(co)
    c = pos.corporate
    _hr(f"Corporate Tax Position — {co.entity_name} ({co.year})")
    rows = [
        ("Net operating income (NOI)", pos.noi),
        ("Less: mortgage interest", -pos.mortgage_interest),
        ("Rental income before CCA", pos.rental_income_before_cca),
        ("Less: capital cost allowance (CCA)", -pos.cca_claimed),
        ("Taxable rental income", pos.taxable_rental_income),
    ]
    for label, amt in rows:
        typer.echo(label.ljust(40) + amt.format().rjust(18))

    _hr("Income characterization")
    typer.echo(f"Rental is a specified investment business: {c.rental_is_sib}")
    typer.echo(f"Aggregate investment income: {c.aggregate_investment_income.format()}")
    typer.echo(f"Quebec SBD factor (5,500-hour test): {c.quebec_sbd_factor:.2f}")
    _hr("Tax")
    for label, amt in c.breakdown:
        if amt.is_positive():
            typer.echo(label.ljust(50) + amt.format().rjust(18))
    typer.echo(typer.style("Total corporate tax".ljust(50) + c.total_tax.format().rjust(18), bold=True))
    typer.echo(f"Refundable portion added to RDTOH: {c.refundable_tax_added_to_rdtoh.format()}")
    for n in c.notes:
        typer.echo("\n• " + n)
    typer.echo("\n" + typer.style(DISCLAIMER, dim=True))


@app.command()
def kpis(db: str = typer.Option(None, help="Company database (defaults to demo)")) -> None:
    """Show per-property and portfolio KPIs."""
    from qcre.analysis import portfolio_view

    co = _load(db)
    per, agg = portfolio_view(co)
    for prop, k in per:
        _hr(f"{prop.name}")
        for key, val in k.as_dict().items():
            typer.echo(f"  {key.ljust(26)} {val}")
    if agg:
        _hr("PORTFOLIO TOTAL")
        for key, val in agg.as_dict().items():
            typer.echo(f"  {key.ljust(26)} {val}")


@app.command()
def advisory(db: str = typer.Option(None, help="Company database (defaults to demo)")) -> None:
    """CFO advisory & tax-optimization recommendations."""
    from qcre.analysis import advisory as build

    co = _load(db)
    items = build(co)
    _hr(f"CFO Advisory — {co.entity_name}")
    colors = {"critical": typer.colors.RED, "warning": typer.colors.YELLOW,
              "opportunity": typer.colors.GREEN, "info": typer.colors.BLUE}
    for it in items:
        tag = typer.style(f"[{it.severity.value.upper()} · {it.category}]",
                          fg=colors.get(it.severity.value))
        typer.echo(f"\n{tag} {typer.style(it.title, bold=True)}")
        typer.echo("  " + it.message)
        if it.impact:
            typer.echo("  " + typer.style(f"Estimated impact: {it.impact.format()}", bold=True))
    typer.echo("\n" + typer.style(DISCLAIMER, dim=True))


@app.command(name="transfer-duty")
def transfer_duty(
    amount: float = typer.Argument(..., help="Taxable basis (price or assessment)"),
    montreal: bool = typer.Option(False, help="Use Montreal's luxury brackets"),
) -> None:
    """Quick property transfer duty (welcome tax) calculation."""
    from qcre.tax.transfer_duty import TransferDutyEngine

    res = TransferDutyEngine().compute(Money(str(amount)), montreal=montreal)
    _hr(f"Transfer duty — {res.municipality}")
    for label, amt in res.detail:
        typer.echo("  " + label.ljust(44) + amt.format().rjust(14))
    typer.echo(typer.style("  Total duty".ljust(46) + res.duty.format().rjust(14), bold=True))


@app.command()
def citations(year: int = typer.Option(2026, help="Taxation year")) -> None:
    """Show the dated, sourced rate book for the year."""
    from qcre.tax.rates import get_ratebook

    rb = get_ratebook(year)
    _hr(f"Rate book {rb.year} — sources")
    for c in rb.citations:
        typer.echo(f"\n• {typer.style(c.topic, bold=True)} ({c.effective})")
        typer.echo(f"  {c.source}")
        typer.echo(f"  {c.url}")
        if c.note:
            typer.echo(f"  {c.note}")
    typer.echo("\n" + typer.style(DISCLAIMER, dim=True))


if __name__ == "__main__":
    app()
