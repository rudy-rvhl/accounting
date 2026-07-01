"""Business events → balanced journal entries.

Each builder returns one or more :class:`JournalEntry` objects ready to post. The GST/QST
treatment is applied here so the books are correct by construction:

* Residential rent (exempt) records revenue only; commercial rent (taxable) also records
  GST/QST payable.
* On expenses, only the **commercial-use share** of GST/QST is recorded as a recoverable
  ITC/ITR; the residential (exempt) share is capitalised into the expense as a real cost.
* Acquisition costs (transfer duty, legal) are **capitalised** into land/building/chattels.

Account codes refer to :func:`qcre.core.accounts.default_chart`.
"""

from __future__ import annotations

from datetime import date

from qcre.core.journal import JournalEntry, JournalLine
from qcre.core.money import Money
from qcre.domain.property import Property, UnitKind
from qcre.tax.rates import RateBook, get_ratebook
from qcre.tax.sales_tax import SalesTaxEngine, SupplyType


# Account-code constants (default chart) -------------------------------------
class Acc:
    CASH = "1010"
    AR = "1100"
    GST_ITC = "1200"
    QST_ITR = "1210"
    LAND = "1400"
    BUILDING = "1500"
    ACCUM_AMORT_BLDG = "1510"
    EQUIPMENT = "1600"
    ACCUM_AMORT_EQUIP = "1610"
    AP = "2000"
    GST_PAYABLE = "2100"
    QST_PAYABLE = "2110"
    MORTGAGE_LT = "2410"
    RENT_RESIDENTIAL = "4000"
    RENT_COMMERCIAL = "4010"
    GAIN_DISPOSAL = "4100"
    MORTGAGE_INTEREST = "5200"
    AMORT_BUILDING = "5300"
    AMORT_EQUIP = "5320"
    LOSS_DISPOSAL = "5500"


class EventBuilder:
    def __init__(self, ratebook: RateBook | None = None) -> None:
        self.rb = ratebook or get_ratebook()
        self.sales_tax = SalesTaxEngine(self.rb)

    # -- rent billing --------------------------------------------------------
    def rent_invoice(
        self,
        property_id: str,
        amount: Money,
        kind: UnitKind,
        on: date,
        *,
        to_cash: bool = False,
        memo: str = "Monthly rent",
    ) -> JournalEntry:
        supply = kind.supply_type
        tax = self.sales_tax.tax_on_supply(amount, supply)
        revenue_acc = Acc.RENT_RESIDENTIAL if kind is UnitKind.RESIDENTIAL else Acc.RENT_COMMERCIAL
        debit_acc = Acc.CASH if to_cash else Acc.AR

        lines = [
            JournalLine(debit_acc, debit=tax.total, memo=memo),
            JournalLine(revenue_acc, credit=amount, memo=memo),
        ]
        if tax.gst.is_positive():
            lines.append(JournalLine(Acc.GST_PAYABLE, credit=tax.gst, memo="GST on rent"))
        if tax.qst.is_positive():
            lines.append(JournalLine(Acc.QST_PAYABLE, credit=tax.qst, memo="QST on rent"))

        return JournalEntry(
            date=on, description=f"{memo} ({kind.value})", lines=lines,
            source="rent_invoice", property_id=property_id,
        )

    # -- operating expense with mixed-use ITC/ITR ---------------------------
    def operating_expense(
        self,
        property_id: str,
        expense_account: str,
        amount_before_tax: Money,
        on: date,
        *,
        commercial_fraction=None,
        taxable_input: bool = True,
        to_cash: bool = False,
        memo: str = "Operating expense",
    ) -> JournalEntry:
        """Record an expense. GST/QST is recoverable only to the commercial-use fraction;
        the rest is capitalised into the expense (a real cost of the exempt activity)."""
        gst = (amount_before_tax * self.rb.sales_tax.gst).round(2) if taxable_input else Money.zero()
        qst = (amount_before_tax * self.rb.sales_tax.qst).round(2) if taxable_input else Money.zero()
        itc, itr = self.sales_tax.input_credits(
            gst, qst,
            supply=SupplyType.TAXABLE if taxable_input else SupplyType.EXEMPT,
            commercial_fraction=commercial_fraction,
        )
        non_recoverable = (gst - itc) + (qst - itr)
        expense_total = (amount_before_tax + non_recoverable).round(2)
        credit_acc = Acc.CASH if to_cash else Acc.AP

        lines = [JournalLine(expense_account, debit=expense_total, memo=memo)]
        if itc.is_positive():
            lines.append(JournalLine(Acc.GST_ITC, debit=itc, memo="ITC (recoverable GST)"))
        if itr.is_positive():
            lines.append(JournalLine(Acc.QST_ITR, debit=itr, memo="ITR (recoverable QST)"))
        lines.append(JournalLine(credit_acc, credit=(amount_before_tax + gst + qst).round(2), memo=memo))

        return JournalEntry(
            date=on, description=memo, lines=lines,
            source="operating_expense", property_id=property_id,
        )

    # -- property acquisition -----------------------------------------------
    def acquisition(
        self,
        prop: Property,
        on: date,
        *,
        transfer_duty: Money = Money.zero(),
        legal_and_other: Money = Money.zero(),
        mortgage_amount: Money = Money.zero(),
    ) -> JournalEntry:
        costs = (transfer_duty + legal_and_other).round(2)
        cap = prop.capitalize_acquisition_costs(costs) if costs.is_positive() else {
            "land": Money.zero(), "building": Money.zero(), "chattels": Money.zero()
        }
        land = (prop.land_value + cap["land"]).round(2)
        building = (prop.building_value + cap["building"]).round(2)
        chattels = (prop.chattels_value + cap["chattels"]).round(2)
        total_cost = (land + building + chattels).round(2)
        cash_down = (total_cost - mortgage_amount).round(2)

        lines = [JournalLine(Acc.LAND, debit=land, memo="Land (incl. capitalised costs)")]
        if building.is_positive():
            lines.append(JournalLine(Acc.BUILDING, debit=building, memo="Building"))
        if chattels.is_positive():
            lines.append(JournalLine(Acc.EQUIPMENT, debit=chattels, memo="Chattels"))
        if mortgage_amount.is_positive():
            lines.append(JournalLine(Acc.MORTGAGE_LT, credit=mortgage_amount, memo="Mortgage financing"))
        if cash_down.is_positive():
            lines.append(JournalLine(Acc.CASH, credit=cash_down, memo="Down payment"))
        elif cash_down.is_negative():
            lines.append(JournalLine(Acc.CASH, debit=-cash_down, memo="Excess financing to cash"))

        return JournalEntry(
            date=on, description=f"Acquisition of {prop.name}", lines=lines,
            source="acquisition", property_id=prop.property_id,
        )

    # -- mortgage payment ----------------------------------------------------
    def mortgage_payment(
        self, property_id: str, interest: Money, principal: Money, on: date,
        memo: str = "Mortgage payment",
    ) -> JournalEntry:
        return JournalEntry(
            date=on, description=memo, source="mortgage_payment", property_id=property_id,
            lines=[
                JournalLine(Acc.MORTGAGE_INTEREST, debit=interest, memo="Interest portion"),
                JournalLine(Acc.MORTGAGE_LT, debit=principal, memo="Principal repayment"),
                JournalLine(Acc.CASH, credit=(interest + principal).round(2), memo=memo),
            ],
        )

    # -- amortization (book depreciation) -----------------------------------
    def amortization(
        self, property_id: str, on: date,
        building: Money = Money.zero(), equipment: Money = Money.zero(),
    ) -> JournalEntry:
        lines: list[JournalLine] = []
        if building.is_positive():
            lines += [
                JournalLine(Acc.AMORT_BUILDING, debit=building, memo="Building amortization"),
                JournalLine(Acc.ACCUM_AMORT_BLDG, credit=building, memo="Accum. amort. — building"),
            ]
        if equipment.is_positive():
            lines += [
                JournalLine(Acc.AMORT_EQUIP, debit=equipment, memo="Equipment amortization"),
                JournalLine(Acc.ACCUM_AMORT_EQUIP, credit=equipment, memo="Accum. amort. — equipment"),
            ]
        if not lines:
            raise ValueError("amortization() needs a positive building or equipment amount")
        return JournalEntry(
            date=on, description="Amortization expense", lines=lines,
            source="amortization", property_id=property_id,
        )

    # -- capital improvement (capitalised, not expensed) --------------------
    def capital_improvement(
        self, property_id: str, amount: Money, on: date, *, to_cash: bool = True,
        memo: str = "Capital improvement",
    ) -> JournalEntry:
        credit_acc = Acc.CASH if to_cash else Acc.AP
        return JournalEntry(
            date=on, description=memo, source="capital_improvement", property_id=property_id,
            lines=[
                JournalLine(Acc.BUILDING, debit=amount, memo=memo),
                JournalLine(credit_acc, credit=amount, memo=memo),
            ],
        )
