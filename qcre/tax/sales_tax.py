"""GST/QST engine for Quebec real estate.

Key rules encoded (see citations 'gst_qst', 'residential_exempt'):

* **Residential long-term rent is an EXEMPT supply** — no GST/QST is charged and no input
  tax credit/refund (ITC/ITR) may be claimed on the related inputs.
* **Commercial rent is a TAXABLE supply** — charge GST 5% + QST 9.975% and claim ITCs/ITRs
  on related inputs.
* **Mixed-use buildings**: input tax on common costs is apportioned to the commercial
  (taxable) portion, normally by **square footage**. Only the commercial share is
  recoverable.
* QST is charged on the amount *excluding* GST (the taxes are not compounded since 2013).
* Small-supplier registration threshold: $30,000 of taxable supplies.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from qcre.core.money import Money
from qcre.tax.rates import RateBook, get_ratebook


class SupplyType(str, Enum):
    TAXABLE = "taxable"        # commercial rent, parking/storage billed separately, short-term
    EXEMPT = "exempt"          # long-term residential rent
    ZERO_RATED = "zero_rated"  # taxed at 0%, ITC/ITR still claimable (rare in real estate)

    @property
    def charges_tax(self) -> bool:
        return self is SupplyType.TAXABLE

    @property
    def allows_input_credits(self) -> bool:
        return self in (SupplyType.TAXABLE, SupplyType.ZERO_RATED)


@dataclass(frozen=True)
class SalesTax:
    base: Money
    gst: Money
    qst: Money

    @property
    def total_tax(self) -> Money:
        return (self.gst + self.qst).round(2)

    @property
    def total(self) -> Money:
        return (self.base + self.gst + self.qst).round(2)


@dataclass(frozen=True)
class NetRemittance:
    gst_collected: Money
    qst_collected: Money
    itc: Money            # recoverable GST on inputs
    itr: Money            # recoverable QST on inputs
    gst_net: Money
    qst_net: Money

    @property
    def total_remittance(self) -> Money:
        return (self.gst_net + self.qst_net).round(2)


class SalesTaxEngine:
    def __init__(self, ratebook: RateBook | None = None) -> None:
        self.rb = ratebook or get_ratebook()

    # -- tax on a supply -----------------------------------------------------
    def tax_on_supply(self, amount: Money, supply: SupplyType) -> SalesTax:
        """GST/QST to charge on a supply of *amount* (tax-exclusive)."""
        st = self.rb.sales_tax
        if not supply.charges_tax:
            return SalesTax(base=amount.round(2), gst=Money.zero(), qst=Money.zero())
        gst = (amount * st.gst).round(2)
        qst = (amount * st.qst).round(2)
        return SalesTax(base=amount.round(2), gst=gst, qst=qst)

    def back_out_tax(self, tax_included: Money) -> SalesTax:
        """Split a tax-*included* total into base + GST + QST."""
        st = self.rb.sales_tax
        factor = Decimal(1) + st.gst + st.qst
        base = (tax_included / factor)
        gst = (base * st.gst).round(2)
        qst = (base * st.qst).round(2)
        return SalesTax(base=base.round(2), gst=gst, qst=qst)

    # -- input tax credits / refunds (ITC / ITR) ----------------------------
    @staticmethod
    def commercial_use_fraction(commercial_sqft: Decimal, residential_sqft: Decimal) -> Decimal:
        total = commercial_sqft + residential_sqft
        if total <= 0:
            return Decimal(0)
        return commercial_sqft / total

    def input_credits(
        self,
        gst_paid: Money,
        qst_paid: Money,
        *,
        supply: SupplyType = SupplyType.TAXABLE,
        commercial_fraction: Decimal | None = None,
    ) -> tuple[Money, Money]:
        """Recoverable (ITC, ITR) on an input.

        * Inputs used in an exempt activity (residential rent) → nothing recoverable.
        * Inputs used in a taxable activity → fully recoverable.
        * Common/mixed-use inputs → recoverable only to the *commercial_fraction*.
        """
        if not supply.allows_input_credits:
            return Money.zero(), Money.zero()
        frac = Decimal(1) if commercial_fraction is None else commercial_fraction
        return (gst_paid * frac).round(2), (qst_paid * frac).round(2)

    # -- net tax to remit ----------------------------------------------------
    def net_remittance(
        self,
        gst_collected: Money,
        qst_collected: Money,
        itc: Money,
        itr: Money,
    ) -> NetRemittance:
        gst_net = (gst_collected - itc).round(2)
        qst_net = (qst_collected - itr).round(2)
        return NetRemittance(
            gst_collected=gst_collected.round(2),
            qst_collected=qst_collected.round(2),
            itc=itc.round(2),
            itr=itr.round(2),
            gst_net=gst_net,
            qst_net=qst_net,
        )

    def must_register(self, taxable_supplies_12mo: Money) -> bool:
        """True if taxable supplies exceed the small-supplier threshold ($30,000)."""
        return taxable_supplies_12mo > self.rb.sales_tax.registration_threshold
