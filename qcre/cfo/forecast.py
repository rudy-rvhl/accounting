"""Multi-year financial & tax forecast for the corporation.

Projects revenue, NOI, mortgage interest/principal/balance, capital cost allowance (with
the UCC pool rolled forward each year), corporate tax, the RDTOH balance, net income,
after-tax cash flow and DSCR over a chosen horizon. Built on the same tax engine as the
single-year analysis, so the projection is consistent with the books.

Assumptions (rent/expense growth, dividend policy, discount rate) are explicit inputs; the
result is a list of yearly rows plus the present value of the after-tax cash flows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from qcre.cfo.finance import npv
from qcre.company import Company
from qcre.core.accounts import AccountType
from qcre.core.money import Money
from qcre.tax.cca import CCAEngine, CCAPool, apply_rental_loss_restriction
from qcre.tax.corporate import CorporateIncome, CorporateProfile, CorporateTaxEngine
from qcre.tax.rates import RateBook, get_ratebook


@dataclass
class ForecastAssumptions:
    years: int = 5
    rent_growth: Decimal = Decimal("0.025")
    expense_growth: Decimal = Decimal("0.03")
    discount_rate: Decimal = Decimal("0.08")
    annual_taxable_dividends: Money = field(default_factory=Money.zero)


@dataclass(frozen=True)
class ForecastYear:
    year: int
    revenue: Money
    operating_expenses: Money
    noi: Money
    mortgage_interest: Money
    mortgage_principal: Money
    mortgage_balance: Money
    cca: Money
    taxable_income: Money
    corporate_tax: Money
    rdtoh_balance: Money
    net_income: Money
    after_tax_cash_flow: Money
    dscr: Decimal


@dataclass(frozen=True)
class ForecastResult:
    rows: list[ForecastYear]
    pv_after_tax_cash_flow: Money
    assumptions: ForecastAssumptions


def _sum_tag(company: Company, atype: AccountType, tag: str) -> Money:
    fy = company.fiscal_year
    total = Money.zero()
    for a in company.ledger.chart.by_type(atype):
        if tag in a.tags:
            total += company.ledger.balance(a.code, start=fy.start, end=fy.end)
    return total.round(2)


def forecast(
    company: Company,
    assumptions: ForecastAssumptions | None = None,
    ratebook: RateBook | None = None,
) -> ForecastResult:
    a = assumptions or ForecastAssumptions()
    rb = ratebook or get_ratebook(company.year)
    corp_engine = CorporateTaxEngine(rb)
    cca_engine = CCAEngine(rb)
    profile = CorporateProfile(
        full_time_employees=company.full_time_employees,
        quebec_paid_hours=company.quebec_paid_hours,
    )

    base_revenue = _sum_tag(company, AccountType.REVENUE, "noi")
    base_opex = _sum_tag(company, AccountType.EXPENSE, "noi")
    book_amort = _sum_tag(company, AccountType.EXPENSE, "amortization")

    # Per-building CCA pools, seeded from the first-year additions.
    pools: dict[str, tuple[str, Money]] = {}
    for p in company.properties:
        addition = company.ledger.balance(
            "1500", start=company.fiscal_year.start, end=company.fiscal_year.end,
            property_id=p.property_id)
        if addition.is_positive():
            pools[p.property_id] = (p.building_cca_class, addition)

    ucc: dict[str, Money] = {}
    rdtoh = Money.zero()
    rows: list[ForecastYear] = []
    cash_flows: list[Money] = [Money.zero()]

    for t in range(a.years):
        year = company.year + t
        growth_rev = (Decimal(1) + a.rent_growth) ** t
        growth_exp = (Decimal(1) + a.expense_growth) ** t
        revenue = (base_revenue * growth_rev).round(2)
        opex = (base_opex * growth_exp).round(2)
        noi = (revenue - opex).round(2)

        interest = Money.zero()
        principal = Money.zero()
        balance = Money.zero()
        for m in company.mortgages:
            i, pr = m.year_split(year)
            interest += i
            principal += pr
            balance += m.balance_at(year)
        debt_service = (interest + principal).round(2)

        # CCA: half-year on first-year additions, then declining balance on the pool.
        cca_results = []
        for pid, (cls, addition) in pools.items():
            if t == 0:
                res = cca_engine.compute(CCAPool(cls, building_id=pid), additions=addition)
            else:
                res = cca_engine.compute(CCAPool(cls, opening_ucc=ucc[pid], building_id=pid))
            cca_results.append(res)
        before_cca = (noi - interest).round(2)
        cca_results = apply_rental_loss_restriction(cca_results, before_cca)
        for res in cca_results:
            ucc[res.building_id] = res.closing_ucc
        cca = sum((r.cca_claimed for r in cca_results), Money.zero()).round(2)

        taxable = (before_cca - cca).round(2)
        corp = corp_engine.compute(CorporateIncome(rental_income=taxable), profile)
        refund = corp_engine.dividend_refund(a.annual_taxable_dividends, rdtoh + corp.refundable_tax_added_to_rdtoh)
        rdtoh = (rdtoh + corp.refundable_tax_added_to_rdtoh - refund).round(2)

        net_income = (noi - interest - book_amort - corp.total_tax).round(2)
        after_tax_cf = (noi - debt_service - corp.total_tax + refund).round(2)
        dscr = (noi.amount / debt_service.amount) if debt_service.is_positive() else Decimal(0)

        rows.append(ForecastYear(
            year=year, revenue=revenue, operating_expenses=opex, noi=noi,
            mortgage_interest=interest.round(2), mortgage_principal=principal.round(2),
            mortgage_balance=balance.round(2), cca=cca, taxable_income=taxable,
            corporate_tax=corp.total_tax, rdtoh_balance=rdtoh, net_income=net_income,
            after_tax_cash_flow=after_tax_cf, dscr=dscr,
        ))
        cash_flows.append(after_tax_cf)

    pv = npv(a.discount_rate, cash_flows).round(2)
    return ForecastResult(rows=rows, pv_after_tax_cash_flow=pv, assumptions=a)
