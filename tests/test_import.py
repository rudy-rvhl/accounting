"""Tests for CSV/PDF transaction extraction and the import web flow."""

from decimal import Decimal

from fastapi.testclient import TestClient

from qcre.importing import parse_csv, parse_pdf, parse_transactions
from qcre.web.app import app


# --- parser unit tests ------------------------------------------------------
def test_csv_signed_amount_and_categories():
    txns = parse_csv(
        "Date,Description,Amount\n"
        "2026-01-05,HYDRO QUEBEC PAYMENT,-142.50\n"
        "2026-01-07,LOYER APT 3 DEPOT,1500.00\n"
        "2026-01-15,ASSURANCE INTACT,-310.00\n"
    )
    assert len(txns) == 3
    assert txns[0].amount == Decimal("-142.50") and txns[0].suggested_account == "5020"  # utilities
    assert txns[1].amount == Decimal("1500.00") and txns[1].suggested_kind == "income"
    assert txns[2].suggested_account == "5010"  # insurance


def test_csv_semicolon_european_decimals_and_debit_credit():
    txns = parse_csv(
        "Transaction Date;Details;Withdrawal;Deposit\n"
        "01/20/2026;Gestion XYZ management fee;250,00;\n"
        "01/22/2026;Loyer commercial deposit;;3.450,00\n"
    )
    assert txns[0].amount == Decimal("-250.00")
    assert txns[0].description == "Gestion XYZ management fee"   # not the date column
    assert txns[0].suggested_account == "5040"                  # management
    assert txns[1].amount == Decimal("3450.00") and txns[1].suggested_kind == "income"


def test_pdf_extraction_from_text_pdf():
    from weasyprint import HTML
    rows = "".join(
        f"<div>{d} &nbsp; {desc} &nbsp; {amt} &nbsp; {bal}</div>"
        for d, desc, amt, bal in [
            ("2026-01-05", "HYDRO QUEBEC PAYMENT", "142.50", "8,700.00"),
            ("2026-01-07", "LOYER APT 3 DEPOT", "1,500.00", "10,200.00"),
            ("2026-01-15", "ASSURANCE INTACT PREMIUM", "310.00", "9,800.01"),
        ]
    )
    pdf = HTML(string=f'<body style="font-family:monospace">{rows}</body>').write_pdf()
    txns, source = parse_transactions("statement.pdf", pdf)
    assert source == "pdf"
    assert len(txns) == 3
    assert txns[0].amount == Decimal("-142.50")           # first amount, not the balance
    assert txns[1].suggested_kind == "income"             # loyer/depot
    assert txns[2].suggested_account == "5010"            # insurance


def test_pdf_does_not_misread_home_depot_as_income():
    from weasyprint import HTML
    pdf = HTML(string='<body style="font-family:monospace">'
               '<div>2026-01-12 HOME DEPOT #7021 89.99 100.00</div></body>').write_pdf()
    txns, _ = parse_transactions("s.pdf", pdf)
    assert txns and txns[0].suggested_kind == "expense"   # "depot" no longer an inflow hint


# --- web flow ---------------------------------------------------------------
def test_import_csv_flow_posts_entries():
    c = TestClient(app)
    c.post("/companies", data={"entity_name": "Import Co.", "year": "2026", "framework": "ASPE",
                               "trust_created": "", "full_time_employees": "0", "quebec_paid_hours": "0"})
    csv = ("Date,Description,Amount\n"
           "2026-01-05,HYDRO QUEBEC,-142.50\n"
           "2026-01-07,RENT DEPOSIT,1500.00\n")
    r = c.post("/import/preview",
               files={"file": ("bank.csv", csv.encode(), "text/csv")},
               data={"doc_type": "bank_statement", "property_id": ""})
    assert r.status_code == 200
    assert "HYDRO QUEBEC" in r.text and "row_count" in r.text

    # Commit both rows.
    r = c.post("/import/commit", data={
        "row_count": "2",
        "include_0": "on", "date_0": "2026-01-05", "description_0": "HYDRO QUEBEC",
        "amount_0": "142.50", "kind_0": "expense", "account_0": "5020", "building_0": "",
        "include_1": "on", "date_1": "2026-01-07", "description_1": "RENT DEPOSIT",
        "amount_1": "1500.00", "kind_1": "income", "account_1": "4000", "building_1": "",
    })
    assert r.status_code == 200
    # The imported document was retained and entries now appear in the ledger.
    assert "bank.csv" in c.get("/documents").text
    ledger = c.get("/ledger").text
    assert "HYDRO QUEBEC" in ledger and "RENT DEPOSIT" in ledger
