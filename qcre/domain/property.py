"""Real-estate property model.

A :class:`Property` holds its rental units (each tagged residential or commercial, with
floor area used for GST/QST input-tax apportionment), the cost allocation between
non-depreciable **land** and depreciable **building** / **chattels**, and the building's
CCA class. The commercial fraction (by square footage) drives both ITC/ITR recovery and
the residential/commercial split of common revenues and costs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum

from qcre.core.money import Money
from qcre.tax.sales_tax import SupplyType


class UnitKind(str, Enum):
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"

    @property
    def supply_type(self) -> SupplyType:
        # Long-term residential rent is exempt; commercial rent is taxable.
        return SupplyType.EXEMPT if self is UnitKind.RESIDENTIAL else SupplyType.TAXABLE


@dataclass
class RentalUnit:
    unit_id: str
    kind: UnitKind
    square_feet: Decimal
    monthly_rent: Money
    occupied: bool = True


@dataclass
class Property:
    property_id: str
    name: str
    address: str
    purchase_price: Money
    purchase_date: date
    land_value: Money
    building_value: Money
    chattels_value: Money = field(default_factory=Money.zero)
    municipal_value: Money = field(default_factory=Money.zero)
    in_montreal: bool = False
    building_cca_class: str = "1"            # "1" 4%, "1-NR" 6%, "1-PBR" 10%
    units: list[RentalUnit] = field(default_factory=list)

    # -- floor-area helpers --------------------------------------------------
    def square_feet(self, kind: UnitKind | None = None) -> Decimal:
        return sum(
            (u.square_feet for u in self.units if kind is None or u.kind == kind),
            Decimal(0),
        )

    @property
    def total_square_feet(self) -> Decimal:
        return self.square_feet()

    @property
    def commercial_fraction(self) -> Decimal:
        total = self.total_square_feet
        if total <= 0:
            return Decimal(0)
        return self.square_feet(UnitKind.COMMERCIAL) / total

    @property
    def is_mixed_use(self) -> bool:
        return 0 < self.commercial_fraction < 1

    # -- revenue helpers -----------------------------------------------------
    def gross_potential_rent(self, kind: UnitKind | None = None) -> Money:
        """Annualised contractual rent (12 months) for all (or one kind of) units."""
        return sum(
            (u.monthly_rent * 12 for u in self.units if kind is None or u.kind == kind),
            Money.zero(),
        ).round(2)

    def in_place_rent(self, kind: UnitKind | None = None) -> Money:
        """Annualised rent for *occupied* units only."""
        return sum(
            (u.monthly_rent * 12 for u in self.units
             if u.occupied and (kind is None or u.kind == kind)),
            Money.zero(),
        ).round(2)

    @property
    def occupancy_rate(self) -> Decimal:
        if not self.units:
            return Decimal(0)
        occ = sum((u.square_feet for u in self.units if u.occupied), Decimal(0))
        return occ / self.total_square_feet if self.total_square_feet else Decimal(0)

    # -- cost allocation -----------------------------------------------------
    @property
    def depreciable_cost(self) -> Money:
        return (self.building_value + self.chattels_value).round(2)

    def capitalize_acquisition_costs(self, costs: Money) -> dict[str, Money]:
        """Allocate acquisition costs (transfer duty, legal) across land/building/chattels
        in proportion to their values — these costs are capitalised, not expensed."""
        weights = [self.land_value.amount, self.building_value.amount, self.chattels_value.amount]
        land, building, chattels = costs.allocate(weights)
        return {"land": land, "building": building, "chattels": chattels}
