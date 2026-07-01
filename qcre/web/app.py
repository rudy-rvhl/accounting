"""FastAPI application exposing the engine as a multi-company browser UI.

Run with::

    uvicorn qcre.web.app:app --reload

Data lives in a SQLite database (``QCRE_DB``, default ``qcre_app.db``) that can hold many
companies; uploaded documents are stored under ``QCRE_UPLOADS`` (default ``qcre_uploads``).
On first run the built-in demo company is seeded so the app is never empty. The active
company is remembered in a cookie and can be switched from the header.

Pages: Dashboard, Companies, Properties (+ add building/unit), Documents (upload with a
type dropdown), Financial Statements, Tax Position, Multi-Year Forecast, CFO Advisory, Tax
Planner, Estate Freeze, T2/CO-17 Schedules, quick transaction entry, and the ledger.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
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
from qcre.db.repo import Repo
from qcre.documents import DOCUMENT_TYPES, is_valid
from qcre.domain.events import Acc, EventBuilder
from qcre.domain.property import UnitKind
from qcre.reports.framework import Framework
from qcre.reports.statements import FinancialStatements
from qcre.tax.optimization import Optimizer
from qcre.tax.rates import get_ratebook
from qcre.tax.transfer_duty import TransferDutyEngine

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
TEMPLATES.env.filters["money"] = lambda m: m.format() if isinstance(m, Money) else m
TEMPLATES.env.filters["pct"] = lambda d: f"{Decimal(d) * 100:.2f}%"

REPO = Repo(
    db_path=os.environ.get("QCRE_DB", "qcre_app.db"),
    uploads_dir=os.environ.get("QCRE_UPLOADS", "qcre_uploads"),
)
REPO.ensure_demo()

app = FastAPI(title="QCRE — Quebec Real-Estate Accounting", version=__version__)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

COOKIE = "qcre_cid"


def active_cid(request: Request) -> int:
    ids = {c.id for c in REPO.list_companies()}
    raw = request.cookies.get(COOKIE)
    if raw and raw.isdigit() and int(raw) in ids:
        return int(raw)
    if ids:
        return min(ids)
    return REPO.ensure_demo()


def get_company(request: Request) -> Company:
    return REPO.get_company(active_cid(request))


def ctx(request: Request, **kw):
    cid = active_cid(request)
    co = REPO.get_company(cid)
    base = {
        "request": request,
        "company": co,
        "company_id": cid,
        "companies": REPO.list_companies(),
        "year": co.year,
        "disclaimer": DISCLAIMER,
        "version": __version__,
        "doc_types": DOCUMENT_TYPES,
    }
    base.update(kw)
    return base


def _render(request: Request, name: str, **kw):
    return TEMPLATES.TemplateResponse(request, name, ctx(request, **kw))


# --- company selection & management ----------------------------------------
@app.get("/companies", response_class=HTMLResponse)
def companies(request: Request):
    return _render(request, "companies.html", active="companies")


@app.post("/companies")
def create_company(
    request: Request,
    entity_name: str = Form(...),
    year: int = Form(2026),
    framework: str = Form("ASPE"),
    trust_created: str = Form(""),
    full_time_employees: int = Form(0),
    quebec_paid_hours: float = Form(0.0),
):
    cid = REPO.create_company(
        entity_name=entity_name.strip() or "New company", year=year,
        framework=framework if framework in ("ASPE", "IFRS") else "ASPE",
        trust_created=trust_created or None, full_time_employees=full_time_employees,
        quebec_paid_hours=str(quebec_paid_hours),
    )
    resp = RedirectResponse(url="/properties", status_code=303)
    resp.set_cookie(COOKIE, str(cid), max_age=31536000)
    return resp


@app.get("/companies/select")
def select_company(request: Request, cid: int):
    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie(COOKIE, str(cid), max_age=31536000)
    return resp


# --- dashboard & analytics (per active company) ----------------------------
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    co = get_company(request)
    if not co.ledger.entries:
        return _render(request, "empty.html", active="dashboard")
    pos = tax_position(co)
    per, agg = portfolio_view(co)
    items = build_advisory(co)
    return _render(request, "dashboard.html", active="dashboard", pos=pos, portfolio=agg,
                   per=per, advisory=items[:4], advisory_count=len(items))


@app.get("/properties", response_class=HTMLResponse)
def properties(request: Request):
    co = get_company(request)
    per, agg = portfolio_view(co) if co.properties else ([], None)
    return _render(request, "properties.html", active="properties", per=per, portfolio=agg)


@app.get("/ledger", response_class=HTMLResponse)
def ledger(request: Request):
    co = get_company(request)
    tb = co.ledger.trial_balance()
    debits, credits = co.ledger.trial_balance_totals()
    entries = sorted(co.ledger.entries, key=lambda e: (e.date, e.id))
    return _render(request, "ledger.html", active="ledger", trial_balance=tb,
                   tb_debits=debits, tb_credits=credits, entries=entries, chart=co.ledger.chart)


@app.get("/statements", response_class=HTMLResponse)
def statements(request: Request, framework: str = "ASPE"):
    co = get_company(request)
    fw = Framework(framework.upper()) if framework.upper() in ("ASPE", "IFRS") else Framework.ASPE
    fs = FinancialStatements(co.ledger, co.fiscal_year, entity_name=co.entity_name, framework=fw)
    return _render(request, "statements.html", active="statements",
                   statements=fs.all_statements(), framework=fw.value)


@app.get("/statements.pdf")
def statements_pdf(request: Request, framework: str = "ASPE"):
    co = get_company(request)
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
    co = get_company(request)
    if not co.ledger.entries:
        return _render(request, "empty.html", active="tax")
    pos = tax_position(co)
    return _render(request, "tax.html", active="tax", pos=pos, corporate=pos.corporate,
                   deemed=deemed_disposition(co))


@app.get("/forecast", response_class=HTMLResponse)
def forecast_page(request: Request, years: int = 5):
    from qcre.cfo.forecast import ForecastAssumptions, forecast
    co = get_company(request)
    if not co.ledger.entries:
        return _render(request, "empty.html", active="forecast")
    res = forecast(co, ForecastAssumptions(years=max(1, min(years, 15))))
    return _render(request, "forecast.html", active="forecast", result=res, rows=res.rows)


@app.get("/advisory", response_class=HTMLResponse)
def advisory(request: Request):
    co = get_company(request)
    items = build_advisory(co) if co.ledger.entries else []
    return _render(request, "advisory.html", active="advisory", advisory=items)


@app.get("/estate-freeze", response_class=HTMLResponse)
def estate_freeze_page(request: Request):
    from qcre.analysis import equity_fair_value, shares_acb
    from qcre.tax.estate_freeze import EstateFreezePlanner
    co = get_company(request)
    if co.trust_created is None or not co.properties:
        return _render(request, "estate_freeze.html", active="estate", freeze=None, plan=None)
    fmv, acb = equity_fair_value(co), shares_acb(co)
    planner = EstateFreezePlanner()
    fr = planner.freeze(fmv, acb, freeze_date=date(co.year, 1, 1))
    plan = planner.deemed_disposition_plan(co.trust_created, fmv, acb, as_of=date(co.year, 6, 30))
    return _render(request, "estate_freeze.html", active="estate", freeze=fr, plan=plan)


@app.get("/schedules", response_class=HTMLResponse)
def schedules_page(request: Request):
    from qcre.reports.tax_schedules import build_tax_schedules
    co = get_company(request)
    if not co.ledger.entries:
        return _render(request, "empty.html", active="schedules")
    return _render(request, "schedules.html", active="schedules",
                   schedules=build_tax_schedules(co))


# --- buildings & units -----------------------------------------------------
@app.get("/properties/new", response_class=HTMLResponse)
def property_new(request: Request):
    return _render(request, "property_new.html", active="properties")


@app.post("/properties")
def add_property(
    request: Request,
    name: str = Form(...),
    address: str = Form(""),
    purchase_price: float = Form(0.0),
    purchase_date: str = Form(...),
    land_value: float = Form(0.0),
    building_value: float = Form(0.0),
    chattels_value: float = Form(0.0),
    municipal_value: float = Form(0.0),
    in_montreal: str = Form("no"),
    building_cca_class: str = Form("1"),
):
    cid = active_cid(request)
    existing = {p.property_id for p in REPO.get_company(cid).properties}
    pid = next(c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" if c not in existing)
    REPO.add_property(
        cid, property_id=pid, name=name.strip() or "Building", address=address,
        purchase_price=str(purchase_price), purchase_date=purchase_date,
        land_value=str(land_value), building_value=str(building_value),
        chattels_value=str(chattels_value), municipal_value=str(municipal_value),
        in_montreal=(in_montreal == "yes"),
        building_cca_class=building_cca_class if building_cca_class in ("1", "1-NR", "1-PBR") else "1",
    )
    return RedirectResponse(url="/properties", status_code=303)


@app.post("/units")
def add_unit(
    request: Request,
    property_id: str = Form(...),
    unit_id: str = Form(...),
    kind: str = Form("residential"),
    square_feet: float = Form(0.0),
    monthly_rent: float = Form(0.0),
):
    cid = active_cid(request)
    REPO.add_unit(
        cid, property_id, unit_id=unit_id,
        kind=kind if kind in ("residential", "commercial") else "residential",
        square_feet=str(square_feet), monthly_rent=str(monthly_rent),
    )
    return RedirectResponse(url="/properties", status_code=303)


# --- quick transaction entry ----------------------------------------------
@app.get("/transactions/new", response_class=HTMLResponse)
def transaction_new(request: Request):
    co = get_company(request)
    expense_accounts = [a for a in co.ledger.chart if a.type.value == "expense" and "noi" in a.tags]
    return _render(request, "transaction_new.html", active="ledger",
                   expense_accounts=expense_accounts)


@app.post("/transactions")
def add_transaction(
    request: Request,
    kind: str = Form(...),                  # "rent" | "expense"
    property_id: str = Form(""),
    amount: float = Form(...),
    on: str = Form(...),
    rent_kind: str = Form("residential"),
    expense_account: str = Form("5030"),
    taxable_input: str = Form("no"),
):
    cid = active_cid(request)
    co = REPO.get_company(cid)
    eb = EventBuilder(get_ratebook(co.year))
    d = date.fromisoformat(on)
    prop = co.property_by_id(property_id)
    frac = prop.commercial_fraction if prop else None
    if kind == "rent":
        entry = eb.rent_invoice(property_id or None, Money(str(amount)),
                                UnitKind(rent_kind), d, to_cash=True)
    else:
        entry = eb.operating_expense(
            property_id or None, expense_account, Money(str(amount)), d,
            commercial_fraction=frac if taxable_input == "yes" else None,
            taxable_input=(taxable_input == "yes"), to_cash=True,
            memo=co.ledger.chart.get(expense_account).name,
        )
    REPO.post_entry(cid, entry)
    return RedirectResponse(url="/ledger", status_code=303)


# --- documents -------------------------------------------------------------
@app.get("/documents", response_class=HTMLResponse)
def documents(request: Request):
    cid = active_cid(request)
    docs = REPO.list_documents(cid)
    return _render(request, "documents.html", active="documents", documents=docs)


@app.post("/documents")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    property_id: str = Form(""),
    period: str = Form(""),
    notes: str = Form(""),
):
    cid = active_cid(request)
    data = await file.read()
    REPO.add_document(
        cid, doc_type=doc_type if is_valid(doc_type) else "other",
        original_filename=file.filename or "upload", data=data,
        content_type=file.content_type or "", property_id=property_id or None,
        period=period, notes=notes,
    )
    return RedirectResponse(url="/documents", status_code=303)


@app.get("/import", response_class=HTMLResponse)
def import_form(request: Request):
    return _render(request, "import.html", active="import")


@app.post("/import/preview", response_class=HTMLResponse)
async def import_preview(
    request: Request,
    file: UploadFile = File(...),
    doc_type: str = Form("bank_statement"),
    property_id: str = Form(""),
):
    from qcre.importing import parse_transactions
    cid = active_cid(request)
    data = await file.read()
    # Always keep the source file in the document library.
    REPO.add_document(
        cid, doc_type=doc_type if is_valid(doc_type) else "bank_statement",
        original_filename=file.filename or "import", data=data,
        content_type=file.content_type or "", property_id=property_id or None,
        notes="imported",
    )
    txns, source = parse_transactions(file.filename or "", data)
    co = REPO.get_company(cid)
    expense_accounts = [a for a in co.ledger.chart if a.type.value == "expense" and "noi" in a.tags]
    income_accounts = [a for a in co.ledger.chart if a.type.value == "revenue" and "rent" in a.tags]
    return _render(request, "import_review.html", active="import", txns=txns, source=source,
                   default_property=property_id, expense_accounts=expense_accounts,
                   income_accounts=income_accounts, filename=file.filename)


@app.post("/import/commit")
async def import_commit(request: Request):
    cid = active_cid(request)
    co = REPO.get_company(cid)
    eb = EventBuilder(get_ratebook(co.year))
    form = await request.form()
    count = int(form.get("row_count", "0"))
    posted = 0
    for i in range(count):
        if form.get(f"include_{i}") != "on":
            continue
        try:
            amount = Money(str(form.get(f"amount_{i}", "0")))
        except Exception:
            continue
        if amount.is_zero():
            continue
        kind = form.get(f"kind_{i}", "expense")
        account = form.get(f"account_{i}", "5030")
        pid = form.get(f"building_{i}", "") or None
        on = form.get(f"date_{i}", "")
        memo = form.get(f"description_{i}", "")[:120]
        try:
            d = date.fromisoformat(on)
        except ValueError:
            d = co.fiscal_year.start
        entry = eb.cash_transaction(pid, account, amount, d, inflow=(kind == "income"), memo=memo)
        REPO.post_entry(cid, entry)
        posted += 1
    return RedirectResponse(url="/ledger", status_code=303)


@app.get("/documents/{doc_id}/download")
def download_document(doc_id: int):
    got = REPO.get_document(doc_id)
    if got is None:
        return Response(status_code=404)
    info, path = got
    return FileResponse(path, filename=info.original_filename,
                        media_type="application/octet-stream")


@app.post("/documents/{doc_id}/delete")
def delete_document(doc_id: int):
    REPO.delete_document(doc_id)
    return RedirectResponse(url="/documents", status_code=303)


# --- planner & reference ---------------------------------------------------
@app.get("/planner", response_class=HTMLResponse)
def planner(request: Request):
    return _render(request, "planner.html", active="planner")


@app.post("/planner/transfer-duty", response_class=HTMLResponse)
def planner_transfer_duty(request: Request, amount: float = Form(...), montreal: str = Form("no")):
    res = TransferDutyEngine().compute(Money(str(amount)), montreal=(montreal == "yes"))
    return TEMPLATES.TemplateResponse(request, "_duty_result.html", {"request": request, "res": res})


@app.post("/planner/salary-dividend", response_class=HTMLResponse)
def planner_salary_dividend(
    request: Request, amount: float = Form(...), other_income: float = Form(0.0),
    income_type: str = Form("investment"),
):
    cmp = Optimizer().salary_vs_dividend(
        Money(str(amount)), income_is_investment=(income_type == "investment"),
        other_personal_income=Money(str(other_income)))
    return TEMPLATES.TemplateResponse(request, "_salary_result.html", {"request": request, "cmp": cmp})


@app.get("/citations", response_class=HTMLResponse)
def citations(request: Request):
    rb = get_ratebook(get_company(request).year)
    return _render(request, "citations.html", active="citations", citations=rb.citations, rb=rb)
