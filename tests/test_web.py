"""Smoke tests for the FastAPI web UI (uses the demo company)."""

from fastapi.testclient import TestClient

from qcre.web.app import app

client = TestClient(app)


def test_pages_render():
    for path in ["/", "/properties", "/statements", "/statements?framework=IFRS",
                 "/tax", "/forecast", "/forecast?years=10", "/estate-freeze",
                 "/advisory", "/planner", "/ledger", "/citations"]:
        r = client.get(path)
        assert r.status_code == 200, path
        assert "Gestion Immobilière Lellouche" in r.text


def test_dashboard_shows_key_numbers():
    r = client.get("/")
    assert "NOI" in r.text
    assert "DSCR" in r.text


def test_transfer_duty_calculator_fragment():
    r = client.post("/planner/transfer-duty", data={"amount": "500000", "montreal": "no"})
    assert r.status_code == 200
    assert "$5,610.50" in r.text  # standard 2026 duty on $500k


def test_salary_vs_dividend_calculator_fragment():
    r = client.post("/planner/salary-dividend",
                    data={"amount": "100000", "other_income": "0", "income_type": "investment"})
    assert r.status_code == 200
    assert "Preferred" in r.text


def test_statements_pdf_download():
    r = client.get("/statements.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"
