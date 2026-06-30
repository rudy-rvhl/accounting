"""Property transfer duties — droits de mutation immobilière ("taxe de bienvenue").

Levied by the municipality when an immovable changes hands. The taxable basis is the
**greater of** the sale price, the stated consideration, and the municipal assessment
multiplied by the year's comparative factor. The duty is then computed on progressive
brackets — standard brackets province-wide, with the City of Montreal levying additional
luxury brackets. Common exemptions remove the duty entirely (transfers between spouses,
direct-line relatives, and certain related-corporation/trust roll-overs).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from qcre.core.money import Money
from qcre.tax.rates import RateBook, get_ratebook


class TransferExemption(str, Enum):
    NONE = "none"
    SPOUSE = "spouse"                      # married/civil-union/de-facto (12+ months)
    DIRECT_LINE = "direct_line"            # parent/child/grandparent, etc.
    RELATED_CORPORATION = "related_corp"   # 90%+ control conditions
    NONE_TAXABLE = "taxable"


@dataclass(frozen=True)
class TransferDutyResult:
    basis: Money
    duty: Money
    municipality: str
    exempt: bool
    detail: list[tuple[str, Money]]        # (bracket description, duty in that bracket)


class TransferDutyEngine:
    def __init__(self, ratebook: RateBook | None = None) -> None:
        self.rb = ratebook or get_ratebook()

    @staticmethod
    def taxable_basis(
        sale_price: Money,
        municipal_value: Money,
        comparative_factor: Decimal = Decimal("1"),
        stated_consideration: Money | None = None,
    ) -> Money:
        """Greater of sale price, stated consideration, and municipal value × factor."""
        candidates = [sale_price, municipal_value * comparative_factor]
        if stated_consideration is not None:
            candidates.append(stated_consideration)
        return max(candidates, key=lambda m: m.amount).round(2)

    def compute(
        self,
        basis: Money,
        *,
        montreal: bool = False,
        exemption: TransferExemption = TransferExemption.NONE,
    ) -> TransferDutyResult:
        municipality = "Montréal" if montreal else "Quebec (standard)"
        if exemption not in (TransferExemption.NONE, TransferExemption.NONE_TAXABLE):
            return TransferDutyResult(basis.round(2), Money.zero(), municipality, True, [])

        table = self.rb.transfer_duty.montreal if montreal else self.rb.transfer_duty.standard
        duty = table.tax_on(basis).round(2)

        # Per-bracket breakdown for transparency on the report.
        detail: list[tuple[str, Money]] = []
        lower = Decimal(0)
        for br in table.brackets:
            upper = br.up_to if br.up_to is not None else basis.amount
            slice_amount = min(basis.amount, upper) - lower
            if slice_amount <= 0:
                break
            pct = f"{br.rate * 100:.2f}%"
            label = (
                f"{pct} on {Money(lower).format()}–{Money(upper).format()}"
                if br.up_to is not None
                else f"{pct} on amount over {Money(lower).format()}"
            )
            detail.append((label, (Money(slice_amount) * br.rate).round(2)))
            lower = upper
            if basis.amount <= upper:
                break

        return TransferDutyResult(basis.round(2), duty, municipality, False, detail)
