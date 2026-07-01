"""The Company aggregate — the in-memory representation of one real-estate corporation.

Bundles the general ledger with the domain objects (properties, mortgages) and the
tax-relevant facts about the corporation and its family-trust ownership. This is what the
persistence layer saves/loads and what the CLI and web UI operate on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from qcre.core import FiscalYear, Ledger
from qcre.domain.mortgage import Mortgage
from qcre.domain.property import Property
from qcre.reports.framework import Framework


@dataclass
class Company:
    entity_name: str
    ledger: Ledger
    properties: list[Property] = field(default_factory=list)
    mortgages: list[Mortgage] = field(default_factory=list)
    fiscal_year: FiscalYear = field(default_factory=lambda: FiscalYear.calendar(2026))
    framework: Framework = Framework.ASPE
    trust_created: date | None = None
    full_time_employees: int = 0
    quebec_paid_hours: Decimal = Decimal("0")
    year: int = 2026
    metadata: dict = field(default_factory=dict)

    def property_by_id(self, property_id: str) -> Property | None:
        return next((p for p in self.properties if p.property_id == property_id), None)


# Backwards-compatible alias (the demo builder historically returned a "SampleCompany").
SampleCompany = Company
