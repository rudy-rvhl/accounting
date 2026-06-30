"""A realistic demo company used by tests, the CLI and the web UI.

`Gestion Immobilière Lellouche Inc.` is a Quebec CCPC whose shares are held by a family
trust (created 2010). It owns two Montreal buildings — a residential six-plex and a
mixed-use building (ground-floor commercial + apartments) — financed with mortgages. The
builder posts a full 2026 year of activity (acquisitions, rent, operating expenses,
mortgage payments and amortization) so every report and analysis has real data to work
with, and the books balance by construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from qcre.core import FiscalYear, Ledger, Money, default_chart
from qcre.domain.events import Acc, EventBuilder
from qcre.domain.mortgage import Mortgage
from qcre.domain.property import Property, RentalUnit, UnitKind
from qcre.reports.framework import Framework
from qcre.tax.rates import get_ratebook
from qcre.tax.transfer_duty import TransferDutyEngine


@dataclass
class SampleCompany:
    entity_name: str
    ledger: Ledger
    properties: list[Property]
    mortgages: list[Mortgage]
    fiscal_year: FiscalYear
    framework: Framework
    trust_created: date
    full_time_employees: int
    quebec_paid_hours: Decimal
    year: int = 2026
    metadata: dict = field(default_factory=dict)


def _residential_sixplex() -> Property:
    units = [RentalUnit(f"A-{i}", UnitKind.RESIDENTIAL, Decimal("900"), Money("2100"))
             for i in range(1, 7)]
    return Property(
        property_id="A", name="Le Plateau (six-plex)", address="1200 Av. du Mont-Royal E, Montréal",
        purchase_price=Money("1800000"), purchase_date=date(2026, 1, 1),
        land_value=Money("540000"), building_value=Money("1260000"),
        municipal_value=Money("1720000"), in_montreal=True, building_cca_class="1",
        units=units,
    )


def _mixed_use() -> Property:
    units = [
        RentalUnit("C-1", UnitKind.COMMERCIAL, Decimal("4000"), Money("10000")),  # $30/sqft/yr
        RentalUnit("B-1", UnitKind.RESIDENTIAL, Decimal("1000"), Money("1900")),
        RentalUnit("B-2", UnitKind.RESIDENTIAL, Decimal("1000"), Money("1900")),
        RentalUnit("B-3", UnitKind.RESIDENTIAL, Decimal("1000"), Money("1900")),
        RentalUnit("B-4", UnitKind.RESIDENTIAL, Decimal("1000"), Money("1900")),
    ]
    return Property(
        property_id="B", name="Saint-Laurent (mixed-use)", address="6500 Boul. Saint-Laurent, Montréal",
        purchase_price=Money("2400000"), purchase_date=date(2026, 1, 1),
        land_value=Money("720000"), building_value=Money("1640000"), chattels_value=Money("40000"),
        municipal_value=Money("2300000"), in_montreal=True, building_cca_class="1-NR",
        units=units,
    )


def build_sample_company(framework: Framework = Framework.ASPE) -> SampleCompany:
    rb = get_ratebook(2026)
    coa = default_chart()
    ledger = Ledger(coa)
    eb = EventBuilder(rb)
    duty_engine = TransferDutyEngine(rb)
    fy = FiscalYear.calendar(2026)

    prop_a = _residential_sixplex()
    prop_b = _mixed_use()
    properties = [prop_a, prop_b]

    # Mortgages at 60% LTV.
    mort_a = Mortgage("MA", "A", Money("1080000"), Decimal("0.05"), 25, date(2026, 1, 1))
    mort_b = Mortgage("MB", "B", Money("1440000"), Decimal("0.0525"), 25, date(2026, 1, 1))
    mortgages = [mort_a, mort_b]

    from qcre.core.journal import JournalEntry, JournalLine

    # 1) Capitalize the company: shares held by the family trust + a shareholder/trust loan.
    ledger.post(JournalEntry(
        date=date(2026, 1, 1), description="Initial capitalization (family trust)",
        source="capitalization",
        lines=[
            JournalLine(Acc.CASH, debit=Money("1900000"), memo="Funds in"),
            JournalLine("3000", credit=Money("1200000"), memo="Common shares (held by trust)"),
            JournalLine("2500", credit=Money("700000"), memo="Due to shareholder/trust"),
        ],
    ))

    # 2) Acquisitions (transfer duty computed on the Montreal scale, capitalized).
    duty_a = duty_engine.compute(
        duty_engine.taxable_basis(prop_a.purchase_price, prop_a.municipal_value), montreal=True
    ).duty
    duty_b = duty_engine.compute(
        duty_engine.taxable_basis(prop_b.purchase_price, prop_b.municipal_value), montreal=True
    ).duty
    ledger.post(eb.acquisition(prop_a, date(2026, 1, 1), transfer_duty=duty_a,
                               legal_and_other=Money("8000"), mortgage_amount=mort_a.principal))
    ledger.post(eb.acquisition(prop_b, date(2026, 1, 1), transfer_duty=duty_b,
                               legal_and_other=Money("10000"), mortgage_amount=mort_b.principal))

    # 3) Twelve months of rent (collected to cash).
    for month in range(1, 13):
        d = date(2026, month, 1)
        for prop in properties:
            for unit in prop.units:
                ledger.post(eb.rent_invoice(
                    prop.property_id, unit.monthly_rent, unit.kind, d, to_cash=True,
                    memo=f"Rent {unit.unit_id} {d.isoformat()}",
                ))

    # 4) Operating expenses (annual). Tax-exempt inputs: property tax, insurance.
    #    Taxable inputs (utilities, R&M, mgmt, snow): ITC only to the commercial fraction.
    expense_plan = {
        "A": {"5000": ("4900", False), "5010": ("9000", False), "5020": ("14000", True),
              "5030": ("12000", True), "5040": ("9072", True), "5060": ("4000", True)},
        "B": {"5000": ("6400", False), "5010": ("12000", False), "5020": ("18000", True),
              "5030": ("15000", True), "5040": ("12672", True), "5060": ("5000", True)},
    }
    frac = {"A": prop_a.commercial_fraction, "B": prop_b.commercial_fraction}
    for pid, plan in expense_plan.items():
        for acc_code, (amt, taxable) in plan.items():
            ledger.post(eb.operating_expense(
                pid, acc_code, Money(amt), date(2026, 6, 30),
                commercial_fraction=frac[pid] if taxable else None,
                taxable_input=taxable, to_cash=True,
                memo=coa.get(acc_code).name,
            ))

    # 5) Mortgage payments for the year (interest deductible; principal reduces the loan).
    for pid, m in zip(["A", "B"], mortgages):
        interest, principal = m.year_split(2026)
        ledger.post(eb.mortgage_payment(pid, interest, principal, date(2026, 12, 31)))

    # 6) Book amortization (ASPE straight-line: building 2.5%/40yr; chattels 20%).
    for prop in properties:
        building_amort = (prop.building_value * Decimal("0.025")).round(2)
        chattels_amort = (prop.chattels_value * Decimal("0.20")).round(2)
        ledger.post(eb.amortization(
            prop.property_id, date(2026, 12, 31),
            building=building_amort, equipment=chattels_amort,
        ))

    # 7) Income tax expense accrual (computed by the corporate engine elsewhere; accrue here).
    #    Rental income is a specified investment business (no full-time employees) → ~50.17%.
    #    Accrue a representative provision so the statements show a tax line.
    ledger.post(JournalEntry(
        date=date(2026, 12, 31), description="Income tax provision (accrual)",
        source="tax_provision",
        lines=[
            JournalLine("5900", debit=Money("9500"), memo="Income tax expense"),
            JournalLine("2600", credit=Money("9500"), memo="Income taxes payable"),
        ],
    ))

    return SampleCompany(
        entity_name="Gestion Immobilière Lellouche Inc.",
        ledger=ledger, properties=properties, mortgages=mortgages,
        fiscal_year=fy, framework=framework,
        trust_created=date(2010, 6, 1), full_time_employees=2,
        quebec_paid_hours=Decimal("0"),
        metadata={"duty_a": duty_a, "duty_b": duty_b},
    )
