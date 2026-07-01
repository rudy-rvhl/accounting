"""qcre — Quebec real-estate accounting, tax and CFO decision engine.

A precise, auditable engine for a Quebec real-estate company (a CCPC held by a family
trust) that keeps double-entry books, computes Quebec/Canada real-estate taxes, prepares
ASPE/IFRS financial statements, and supports CFO decisions and tax optimization.

IMPORTANT — this software is decision-support only. It is **not** professional tax,
legal or accounting advice. Tax rules and rates change; every figure must be verified
against current CRA / Revenu Québec publications and reviewed with a licensed CPA or
tax advisor before you rely on it. See README.md and qcre.tax.rates for the dated,
sourced rate book.
"""

__version__ = "0.1.0"

DISCLAIMER = (
    "This software provides decision-support only and is NOT professional tax, legal or "
    "accounting advice. Tax rules and rates change frequently. Verify every figure against "
    "current CRA and Revenu Québec publications and consult a licensed CPA or tax advisor "
    "before relying on these results."
)
