"""Lease / tenancy model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from qcre.core.money import Money
from qcre.domain.property import UnitKind


@dataclass
class Lease:
    lease_id: str
    property_id: str
    unit_id: str
    tenant: str
    kind: UnitKind
    monthly_rent: Money
    start: date
    end: date | None = None
    deposit: Money | None = None

    @property
    def annual_rent(self) -> Money:
        return (self.monthly_rent * 12).round(2)

    def is_active(self, as_of: date) -> bool:
        if as_of < self.start:
            return False
        return self.end is None or as_of <= self.end
