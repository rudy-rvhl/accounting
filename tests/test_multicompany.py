"""Tests for multi-company management, building/unit entry, transactions, and documents."""

from fastapi.testclient import TestClient

from qcre.web.app import app


def _client():
    # Isolate cookies per test so the active-company selection doesn't leak.
    return TestClient(app)


def test_companies_page_lists_demo():
    c = _client()
    r = c.get("/companies")
    assert r.status_code == 200
    assert "Lellouche" in r.text  # demo company seeded


def test_create_company_then_build_it_up():
    c = _client()
    # Create a fresh company (redirect sets the active-company cookie).
    r = c.post("/companies", data={
        "entity_name": "Test Realty Inc.", "year": "2026", "framework": "ASPE",
        "trust_created": "", "full_time_employees": "0", "quebec_paid_hours": "0",
    })
    assert r.status_code == 200  # followed redirect to /properties
    assert "Test Realty Inc." in r.text

    # New company has no data → dashboard shows the empty-state call to action.
    r = c.get("/")
    assert "has no data yet" in r.text

    # Add a building.
    r = c.post("/properties", data={
        "name": "Test Duplex", "address": "Montréal", "purchase_price": "600000",
        "purchase_date": "2026-01-01", "land_value": "200000", "building_value": "400000",
        "chattels_value": "0", "municipal_value": "580000", "in_montreal": "yes",
        "building_cca_class": "1",
    })
    assert r.status_code == 200
    assert "Test Duplex" in r.text

    # Add a unit to it.
    r = c.get("/properties")
    assert "Test Duplex" in r.text
    r = c.post("/units", data={
        "property_id": "A", "unit_id": "1", "kind": "residential",
        "square_feet": "800", "monthly_rent": "1500",
    })
    assert r.status_code == 200

    # Record rent income → dashboard now populates.
    r = c.post("/transactions", data={
        "kind": "rent", "property_id": "A", "amount": "1500", "on": "2026-01-01",
        "rent_kind": "residential", "expense_account": "5030", "taxable_input": "no",
    })
    assert r.status_code == 200
    r = c.get("/")
    assert "has no data yet" not in r.text  # dashboard renders with data now


def test_document_upload_download_and_delete():
    c = _client()
    c.post("/companies", data={"entity_name": "Docs Co.", "year": "2026", "framework": "ASPE",
                               "trust_created": "", "full_time_employees": "0", "quebec_paid_hours": "0"})
    # Upload a categorized document.
    r = c.post(
        "/documents",
        files={"file": ("rbc-jan.pdf", b"%PDF-1.4 fake bank statement", "application/pdf")},
        data={"doc_type": "bank_statement", "property_id": "", "period": "2026-01", "notes": "operating"},
    )
    assert r.status_code == 200
    assert "rbc-jan.pdf" in r.text
    assert "Bank statement" in r.text  # dropdown label rendered

    # Find the document link and download it.
    import re
    m = re.search(r"/documents/(\d+)/download", r.text)
    assert m
    doc_id = m.group(1)
    dl = c.get(f"/documents/{doc_id}/download")
    assert dl.status_code == 200
    assert dl.content == b"%PDF-1.4 fake bank statement"

    # Delete it.
    r = c.post(f"/documents/{doc_id}/delete")
    assert r.status_code == 200
    assert "rbc-jan.pdf" not in r.text


def test_invalid_doc_type_falls_back_to_other():
    c = _client()
    c.post("/companies", data={"entity_name": "Fallback Co.", "year": "2026", "framework": "ASPE",
                               "trust_created": "", "full_time_employees": "0", "quebec_paid_hours": "0"})
    r = c.post("/documents",
               files={"file": ("x.txt", b"hello", "text/plain")},
               data={"doc_type": "not_a_real_type", "property_id": "", "period": "", "notes": ""})
    assert r.status_code == 200
    assert "Other" in r.text
