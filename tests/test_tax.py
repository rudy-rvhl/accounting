"""Golden tests for the Quebec/Canada tax engine (2026 rate book)."""

from datetime import date
from decimal import Decimal

from qcre.core.money import Money
from qcre.tax.capital import CapitalGainsEngine
from qcre.tax.cca import CCAEngine, CCAPool, apply_rental_loss_restriction
from qcre.tax.corporate import CorporateIncome, CorporateProfile, CorporateTaxEngine
from qcre.tax.personal import PersonalTaxEngine
from qcre.tax.rates import get_ratebook
from qcre.tax.sales_tax import SalesTaxEngine, SupplyType
from qcre.tax.transfer_duty import TransferDutyEngine, TransferExemption
from qcre.tax.trust import BeneficiaryFacts, TOSIScreener, TrustEngine

RB = get_ratebook(2026)


# --- Sales tax (GST/QST) ----------------------------------------------------
def test_commercial_rent_is_taxable():
    eng = SalesTaxEngine(RB)
    tax = eng.tax_on_supply(Money("2000"), SupplyType.TAXABLE)
    assert tax.gst == Money("100.00")          # 5%
    assert tax.qst == Money("199.50")          # 9.975%
    assert tax.total == Money("2299.50")


def test_residential_rent_is_exempt():
    eng = SalesTaxEngine(RB)
    tax = eng.tax_on_supply(Money("2000"), SupplyType.EXEMPT)
    assert tax.gst.is_zero() and tax.qst.is_zero()


def test_mixed_use_itc_apportioned_by_square_footage():
    eng = SalesTaxEngine(RB)
    frac = eng.commercial_use_fraction(Decimal("7000"), Decimal("3000"))  # 70% commercial
    itc, itr = eng.input_credits(Money("100"), Money("199.50"), commercial_fraction=frac)
    assert itc == Money("70.00")
    assert itr == Money("139.65")


def test_no_itc_on_exempt_inputs():
    eng = SalesTaxEngine(RB)
    itc, itr = eng.input_credits(Money("100"), Money("199.50"), supply=SupplyType.EXEMPT)
    assert itc.is_zero() and itr.is_zero()


def test_back_out_tax_round_trips():
    eng = SalesTaxEngine(RB)
    st = eng.back_out_tax(Money("2299.50"))
    assert st.base == Money("2000.00")


# --- Transfer duty (welcome tax) -------------------------------------------
def test_transfer_duty_standard_500k():
    eng = TransferDutyEngine(RB)
    res = eng.compute(Money("500000"))
    # 0.5%*62,900 + 1%*(315,000-62,900) + 1.5%*(500,000-315,000)
    assert res.duty == Money("5610.50")


def test_transfer_duty_montreal_luxury_2M():
    eng = TransferDutyEngine(RB)
    res = eng.compute(Money("2000000"), montreal=True)
    assert res.duty == Money("39825.50")
    assert res.municipality == "Montréal"


def test_transfer_duty_spouse_exemption():
    eng = TransferDutyEngine(RB)
    res = eng.compute(Money("500000"), exemption=TransferExemption.SPOUSE)
    assert res.exempt and res.duty.is_zero()


def test_transfer_duty_basis_uses_greater_of():
    eng = TransferDutyEngine(RB)
    basis = eng.taxable_basis(
        sale_price=Money("400000"),
        municipal_value=Money("450000"),
        comparative_factor=Decimal("1.05"),
    )
    assert basis == Money("472500.00")  # 450,000 * 1.05 beats the price


# --- CCA --------------------------------------------------------------------
def test_cca_building_first_year_half_year_rule():
    eng = CCAEngine(RB)
    res = eng.compute(CCAPool("1"), additions=Money("400000"))
    # (400,000 - half of 400,000) * 4%
    assert res.cca_claimed == Money("8000.00")
    assert res.closing_ucc == Money("392000.00")


def test_cca_purpose_built_rental_10pct():
    eng = CCAEngine(RB)
    res = eng.compute(CCAPool("1-PBR"), additions=Money("400000"))
    assert res.rate == Decimal("0.10")
    assert res.cca_claimed == Money("20000.00")  # (400,000 - 200,000) * 10%


def test_cca_recapture_on_disposition():
    eng = CCAEngine(RB)
    res = eng.compute(
        CCAPool("1", opening_ucc=Money("100000")),
        proceeds_of_disposition=Money("150000"),
        capital_cost_of_disposed=Money("400000"),
    )
    assert res.recapture == Money("50000.00")  # 150k proceeds (<cost) - 100k UCC
    assert res.closing_ucc.is_zero()


def test_cca_terminal_loss():
    eng = CCAEngine(RB)
    res = eng.compute(
        CCAPool("8", opening_ucc=Money("30000")),
        proceeds_of_disposition=Money("5000"),
        capital_cost_of_disposed=Money("40000"),
        class_emptied=True,
    )
    assert res.terminal_loss == Money("25000.00")  # 30k UCC - 5k proceeds
    assert res.closing_ucc.is_zero()


def test_rental_loss_restriction_caps_cca():
    eng = CCAEngine(RB)
    r = eng.compute(CCAPool("1", opening_ucc=Money("500000")))  # wants 20,000 CCA
    assert r.cca_claimed == Money("20000.00")
    capped = apply_rental_loss_restriction([r], net_rental_income_before_cca=Money("12000"))
    assert capped[0].cca_claimed == Money("12000.00")  # cannot create a rental loss


# --- Capital gains ----------------------------------------------------------
def test_capital_gain_inclusion_and_cda():
    eng = CapitalGainsEngine(RB)
    res = eng.on_disposition(proceeds=Money("600000"), acb=Money("400000"), outlays=Money("30000"))
    assert res.gain == Money("170000.00")
    assert res.taxable_capital_gain == Money("85000.00")   # 50% inclusion
    assert res.cda_addition == Money("85000.00")           # non-taxable half to CDA


# --- Corporate tax ----------------------------------------------------------
def test_rental_income_taxed_as_investment_when_sib():
    eng = CorporateTaxEngine(RB)
    res = eng.compute(
        CorporateIncome(rental_income=Money("100000")),
        CorporateProfile(full_time_employees=2),
    )
    assert res.rental_is_sib is True
    assert res.aggregate_investment_income == Money("100000.00")
    assert res.tax_investment == Money("50170.00")          # 50.17%
    assert res.refundable_tax_added_to_rdtoh == Money("30670.00")  # 30.67% to RDTOH


def test_rental_income_active_with_enough_employees_and_hours():
    eng = CorporateTaxEngine(RB)
    res = eng.compute(
        CorporateIncome(rental_income=Money("100000")),
        CorporateProfile(full_time_employees=6, quebec_paid_hours=Decimal("6000")),
    )
    assert res.rental_is_sib is False
    assert res.quebec_sbd_factor == Decimal("1")
    assert res.effective_sbd_rate == Decimal("0.112")
    assert res.tax_sbd == Money("11200.00")                 # 11.2% small business rate


def test_quebec_sbd_denied_without_hours():
    eng = CorporateTaxEngine(RB)
    res = eng.compute(
        CorporateIncome(other_active_income=Money("100000")),
        CorporateProfile(full_time_employees=6, quebec_paid_hours=Decimal("5000")),
    )
    # Federal SBD 9% + Quebec general 11.5% (no Quebec SBD) = 20.5%
    assert res.effective_sbd_rate == Decimal("0.205")
    assert res.tax_sbd == Money("20500.00")


# --- Personal / integration -------------------------------------------------
def test_top_combined_marginal_rate():
    eng = PersonalTaxEngine(RB)
    rate = eng.marginal_rate_ordinary(Money("300000"))
    assert round(rate, 5) == Decimal("0.53305")  # 33%*(1-0.165) + 25.75%


# --- Trust: 21-year rule & TOSI --------------------------------------------
def test_21_year_deemed_disposition_forecast():
    eng = TrustEngine(RB)
    f = eng.deemed_disposition_forecast(
        trust_created=date(2010, 6, 1), fmv=Money("2000000"), acb=Money("500000"),
        as_of=date(2026, 6, 30),
    )
    assert f.anniversary == date(2031, 6, 1)
    assert f.result.taxable_capital_gain == Money("750000.00")  # (2M-500k)*50%


def test_tosi_applies_to_passive_family_beneficiary():
    screener = TOSIScreener(RB)
    res = screener.screen(
        BeneficiaryFacts(name="Adult child", age=30), Money("50000"), eligible=False
    )
    assert res.applies is True
    assert res.effective_rate > Decimal("0.40")  # punitive top-rate taxation


def test_tosi_excluded_for_actively_engaged_beneficiary():
    screener = TOSIScreener(RB)
    res = screener.screen(
        BeneficiaryFacts(name="Active manager", age=35, hours_per_week_in_business=Decimal("40")),
        Money("50000"),
        eligible=False,
    )
    assert res.applies is False
    assert "excluded business" in res.reason


# --- Optimization -----------------------------------------------------------
def test_cost_of_specified_investment_business():
    from qcre.tax.optimization import Optimizer
    opt = Optimizer(RB)
    cmp = opt.cost_of_specified_investment_business(Money("100000"))
    assert cmp.tax_as_investment == Money("50170.00")     # 50.17%
    assert cmp.tax_as_small_business == Money("11200.00")  # 11.2%
    assert cmp.annual_difference == Money("38970.00")


def test_salary_vs_dividend_runs_and_picks_a_route():
    from qcre.tax.optimization import Optimizer
    opt = Optimizer(RB)
    cmp = opt.salary_vs_dividend(Money("100000"), income_is_investment=True)
    assert cmp.preferred in ("salary", "dividend")
    assert cmp.advantage.amount >= 0
    # Both routes should leave the owner with a sensible positive amount.
    assert cmp.salary_net_to_owner.is_positive()
    assert cmp.dividend_net_to_owner.is_positive()


def test_corporate_instalments_quarterly():
    from qcre.tax.optimization import Optimizer
    opt = Optimizer(RB)
    sched = opt.corporate_instalments(Money("40000"), eligible_for_quarterly=True)
    assert len(sched) == 4
    assert sched["Q1"] == Money("10000.00")
