"""FastAPI application exposing the engine as a browser UI.

Run with::

    uvicorn qcre.web.app:app --reload

Set ``QCRE_DB`` to point at a saved company database; otherwise the built-in demo
company is used. Pages: Dashboard, Properties, Ledger, Statements, Tax Planner, Advisory,
plus interactive (HTMX) calculators for transfer duty and salary-vs-dividend.
"""

from __future__ import annotations

import os
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from qcre import DISCLAIMER, __version__
from qcre.analysis import (
    advisory as build_advisory,
    deemed_disposition,
    portfolio_view,
    tax_position,
)
from qcre.company import Company
from qcre.core.money import Money
from qcre.reports.framework import Framework
from qcre.reports.statements import FinancialStatements
from qcre.tax.optimization import Optimizer
from qcre.tax.rates import get_ratebook
from qcre.tax.transfer_duty import TransferDutyEngine

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
TEMPLATES.env.filters["money"] = lambda m: m.format() if isinstance(m, Money) else m
TEMPLATES.env.filters["pct"] = lambda d: f"{Decimal(d) * 100:.2f}%"

app = FastAPI(title="QCRE — Quebec Real-Estate Accounting", version=__version__)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


@lru_cache(maxsize=1)
def get_company() -> Company:
    db = os.environ.get("QCRE_DB")
    if db and os.path.exists(db):
        from qcre.db.store import load_company
        return load_company(db)
    from qcre.sample import build_sample_company
    return build_sample_company()


def ctx(request: Request, **kw):
    co = get_company()
    base = {
        "request": request,
        "company": co,
        "year": co.year,
        "disclaimer": DISCLAIMER,
        "version": __version__,
    }
    base.update(kw)
    return base


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    co = get_company()
    pos = tax_position(co)
    per, agg = portfolio_view(co)
    items = build_advisory(co)
    return TEMPLATES.TemplateResponse(request, "dashboard.html", ctx(
        request, active="dashboard", pos=pos, portfolio=agg, per=per,
        advisory=items[:4], advisory_count=len(items),
    ))


@app.get("/properties", response_class=HTMLResponse)
def properties(request: Request):
    co = get_company()
    per, agg = portfolio_view(co)
    return TEMPLATES.TemplateResponse(request, "properties.html", ctx(
        request, active="properties", per=per, portfolio=agg))


@app.get("/ledger", response_class=HTMLResponse)
def ledger(request: Request):
    co = get_company()
    tb = co.ledger.trial_balance()
    debits, credits = co.ledger.trial_balance_totals()
    entries = sorted(co.ledger.entries, key=lambda e: (e.date, e.id))
    return TEMPLATES.TemplateResponse(request, "ledger.html", ctx(
        request, active="ledger", trial_balance=tb, tb_debits=debits, tb_credits=credits,
        entries=entries, chart=co.ledger.chart))


@app.get("/statements", response_class=HTMLResponse)
def statements(request: Request, framework: str = "ASPE"):
    co = get_company()
    fw = Framework(framework.upper()) if framework.upper() in ("ASPE", "IFRS") else Framework.ASPE
    fs = FinancialStatements(co.ledger, co.fiscal_year, entity_name=co.entity_name, framework=fw)
    return TEMPLATES.TemplateResponse(request, "statements.html", ctx(
        request, active="statements", statements=fs.all_statements(), framework=fw.value))


@app.get("/statements.pdf")
def statements_pdf(framework: str = "ASPE"):
    co = get_company()
    fw = Framework(framework.upper()) if framework.upper() in ("ASPE", "IFRS") else Framework.ASPE
    fs = FinancialStatements(co.ledger, co.fiscal_year, entity_name=co.entity_name, framework=fw)
    from qcre.reports.render import render_document, write_pdf
    html = render_document(f"{co.entity_name} — {co.fiscal_year.label} Financial Statements",
                           fs.all_statements())
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
        write_pdf(fh.name, html)
        data = Path(fh.name).read_bytes()
    return Response(content=data, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename=statements_{co.fiscal_year.label}.pdf"})


@app.get("/tax", response_class=HTMLResponse)
def tax(request: Request):
    co = get_company()
    pos = tax_position(co)
    ddf = deemed_disposition(co)
    return TEMPLATES.TemplateResponse(request, "tax.html", ctx(
        request, active="tax", pos=pos, corporate=pos.corporate, deemed=ddf))


@app.get("/advisory", response_class=HTMLResponse)
def advisory(request: Request):
    co = get_company()
    items = build_advisory(co)
    return TEMPLATES.TemplateResponse(request, "advisory.html", ctx(
        request, active="advisory", advisory=items))


@app.get("/forecast", response_class=HTMLResponse)
def forecast_page(request: Request, years: int = 5):
    from qcre.cfo.forecast import ForecastAssumptions, forecast
    co = get_company()
    res = forecast(co, ForecastAssumptions(years=max(1, min(years, 15))))
    return TEMPLATES.TemplateResponse(request, "forecast.html", ctx(
        request, active="forecast", result=res, rows=res.rows))


@app.get("/estate-freeze", response_class=HTMLResponse)
def estate_freeze_page(request: Request):
    from datetime import date as _date

    from qcre.analysis import equity_fair_value, shares_acb
    from qcre.tax.estate_freeze import EstateFreezePlanner

    co = get_company()
    if co.trust_created is None:
        return TEMPLATES.TemplateResponse(request, "estate_freeze.html", ctx(
            request, active="estate", freeze=None, plan=None))
    fmv, acb = equity_fair_value(co), shares_acb(co)
    planner = EstateFreezePlanner()
    fr = planner.freeze(fmv, acb, freeze_date=_date(co.year, 1, 1))
    plan = planner.deemed_disposition_plan(co.trust_created, fmv, acb, as_of=_date(co.year, 6, 30))
    return TEMPLATES.TemplateResponse(request, "estate_freeze.html", ctx(
        request, active="estate", freeze=fr, plan=plan))


@app.get("/planner", response_class=HTMLResponse)
def planner(request: Request):
    return TEMPLATES.TemplateResponse(request, "planner.html", ctx(request, active="planner"))


@app.post("/planner/transfer-duty", response_class=HTMLResponse)
def planner_transfer_duty(request: Request, amount: float = Form(...), montreal: str = Form("no")):
    res = TransferDutyEngine().compute(Money(str(amount)), montreal=(montreal == "yes"))
    return TEMPLATES.TemplateResponse(request, "_duty_result.html", {"request": request, "res": res})


@app.post("/planner/salary-dividend", response_class=HTMLResponse)
def planner_salary_dividend(
    request: Request,
    amount: float = Form(...),
    other_income: float = Form(0.0),
    income_type: str = Form("investment"),
):
    cmp = Optimizer().salary_vs_dividend(
        Money(str(amount)),
        income_is_investment=(income_type == "investment"),
        other_personal_income=Money(str(other_income)),
    )
    return TEMPLATES.TemplateResponse(request, "_salary_result.html", {"request": request, "cmp": cmp})


@app.get("/schedules", response_class=HTMLResponse)
def schedules_page(request: Request):
    from qcre.reports.tax_schedules import build_tax_schedules
    co = get_company()
    return TEMPLATES.TemplateResponse(request, "schedules.html", ctx(
        request, active="schedules", schedules=build_tax_schedules(co)))


@app.get("/citations", response_class=HTMLResponse)
def citations(request: Request):
    rb = get_ratebook(get_company().year)
    return TEMPLATES.TemplateResponse(request, "citations.html", ctx(
        request, active="citations", citations=rb.citations, rb=rb))
