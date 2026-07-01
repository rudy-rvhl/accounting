"""Document categories for uploaded source documents.

The dropdown shown on the upload form comes from this list, so adding a category here is
all that is needed to make it selectable.
"""

from __future__ import annotations

# (value, human label) — value is stored; label is shown in the dropdown.
DOCUMENT_TYPES: list[tuple[str, str]] = [
    ("bank_statement", "Bank statement"),
    ("credit_card_statement", "Credit card statement"),
    ("utility_bill", "Utility bill (hydro, gas, water)"),
    ("property_tax_bill", "Property tax bill (municipal/school)"),
    ("insurance", "Insurance document"),
    ("mortgage_statement", "Mortgage statement"),
    ("lease", "Lease / rental agreement"),
    ("invoice", "Invoice / bill"),
    ("receipt", "Receipt"),
    ("repair_maintenance", "Repair & maintenance"),
    ("management_fee", "Property management"),
    ("payroll", "Payroll / wages"),
    ("gst_qst", "GST/QST filing"),
    ("financial_statement", "Financial statement"),
    ("tax_return", "Tax return / assessment (T2, CO-17)"),
    ("legal", "Legal document (notary, deed)"),
    ("purchase_sale", "Purchase / sale document"),
    ("other", "Other"),
]

_LABELS = dict(DOCUMENT_TYPES)


def label_for(value: str) -> str:
    return _LABELS.get(value, value.replace("_", " ").title())


def is_valid(value: str) -> bool:
    return value in _LABELS
