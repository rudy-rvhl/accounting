"""Tests for properties, Canadian mortgage amortization, and event journal entries."""

from datetime import date
from decimal import Decimal

from qcre.core import Ledger, Money, default_chart
from qcre.domain.events import Acc, EventBuilder
from qcre.domain.mortgage import Mortgage
from qcre.domain.property import Property, RentalUnit, UnitKind
from qcre.tax.rates import get_ratebook

RB = get_ratebook(2026)


def make_mixed_property() -> Property:
    return Property(
        property_id="P1",
        name="123 Rue Principale",
        address="Montréal, QC",
        purchase_price=Money("1000000"),
        purchase_date=date(2026, 1, 15),
        land_value=Money("300000"),
        building_value=Money("680000"),
        chattels_value=Money("20000"),
        municipal_value=Money("950000"),
        in_montreal=True,
        units=[
            RentalUnit("R1", UnitKind.RESIDENTIAL, Decimal("3000"), Money("2000")),
            RentalUnit("R2", UnitKind.RESIDENTIAL, Decimal("3000"), Money("2100")),
            RentalUnit("C1", UnitKind.COMMERCIAL, Decimal("4000"), Money("6000")),
        ],
    )


# --- Property ---------------------------------------------------------------
def test_property_commercial_fraction_and_mixed_use():
    p = make_mixed_property()
    assert p.total_square_feet == Decimal("10000")
    assert p.commercial_fraction == Decimal("0.4")  # 4000 / 10000
    assert p.is_mixed_use


def test_property_gross_potential_rent_by_kind():
    p = make_mixed_property()
    assert p.gross_potential_rent(UnitKind.RESIDENTIAL) == Money("49200.00")  # (2000+2100)*12
    assert p.gross_potential_rent(UnitKind.COMMERCIAL) == Money("72000.00")   # 6000*12


def test_capitalize_acquisition_costs_allocates_fully():
    p = make_mixed_property()
    alloc = p.capitalize_acquisition_costs(Money("28232.50"))
    assert sum(alloc.values(), Money.zero()) == Money("28232.50")


# --- Mortgage (semi-annual compounding) ------------------------------------
def test_canadian_mortgage_payment_uses_semiannual_compounding():
    m = Mortgage("M1", "P1", Money("500000"), Decimal("0.05"), 25, date(2026, 1, 1))
    pmt = m.payment
    # Known good ~ $2,908/month; strictly less than naive monthly compounding (~$2,923).
    assert Money("2905") < pmt < Money("2912")


def test_mortgage_schedule_amortizes_to_zero():
    m = Mortgage("M1", "P1", Money("200000"), Decimal("0.04"), 5, date(2026, 1, 1))
    sched = m.schedule()
    assert sched[-1].balance.is_zero()
    interest, principal = m.year_split(2026)
    assert (interest + principal).is_positive()


# --- Events post balanced entries ------------------------------------------
def test_residential_rent_invoice_no_tax():
    eb = EventBuilder(RB)
    e = eb.rent_invoice("P1", Money("2000"), UnitKind.RESIDENTIAL, date(2026, 1, 1))
    assert e.is_balanced()
    codes = {ln.account_code for ln in e.lines}
    assert Acc.GST_PAYABLE not in codes  # residential rent is exempt


def test_commercial_rent_invoice_charges_gst_qst():
    eb = EventBuilder(RB)
    e = eb.rent_invoice("P1", Money("6000"), UnitKind.COMMERCIAL, date(2026, 1, 1))
    assert e.is_balanced()
    gst = next(ln for ln in e.lines if ln.account_code == Acc.GST_PAYABLE)
    qst = next(ln for ln in e.lines if ln.account_code == Acc.QST_PAYABLE)
    assert gst.credit == Money("300.00")     # 5%
    assert qst.credit == Money("598.50")     # 9.975%


def test_operating_expense_mixed_use_partial_itc():
    eb = EventBuilder(RB)
    # 40% commercial → only 40% of GST/QST is recoverable; 60% capitalised into expense.
    e = eb.operating_expense(
        "P1", "5030", Money("1000"), date(2026, 1, 1),
        commercial_fraction=Decimal("0.4"),
    )
    assert e.is_balanced()
    itc = next(ln for ln in e.lines if ln.account_code == Acc.GST_ITC)
    assert itc.debit == Money("20.00")        # 1000 * 5% * 40%
    expense_line = next(ln for ln in e.lines if ln.account_code == "5030")
    # expense = 1000 + 60% of (50 + 99.75) = 1000 + 89.85
    assert expense_line.debit == Money("1089.85")


def test_acquisition_posts_and_balances_in_ledger():
    eb = EventBuilder(RB)
    p = make_mixed_property()
    ledger = Ledger(default_chart())
    entry = eb.acquisition(
        p, p.purchase_date,
        transfer_duty=Money("28232.50"), legal_and_other=Money("5000"),
        mortgage_amount=Money("750000"),
    )
    ledger.post(entry)
    assert ledger.is_in_balance()
    # Land + building + chattels = purchase price + capitalised acquisition costs.
    total_assets = (
        ledger.balance(Acc.LAND) + ledger.balance(Acc.BUILDING) + ledger.balance(Acc.EQUIPMENT)
    )
    assert total_assets == Money("1033232.50")  # 1,000,000 + 33,232.50
