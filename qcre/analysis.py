"""Integration layer: derive the full tax position, KPIs and advisory from a Company.

Shared by the CLI and the web UI so the analysis logic lives in one place. It walks the
ledger to obtain rental income before CCA, runs the CCA engine (respecting the rental-loss
restriction), feeds the result to the corporate tax engine, and assembles the advisory.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from qcre.cfo.advisory import AdvisoryItem, build_advisory
from qcre.cfo.kpis import PropertyKPIs, portfolio_kpis
from qcre.company import Company
from qcre.core.accounts import AccountType
from qcre.core.money import Money
from qcre.domain.property import Property, UnitKind
from qcre.tax.cca import CCAEngine, CCAPool, CCAResult, apply_rental_loss_restriction
from qcre.tax.corporate import CorporateIncome, CorporateProfile, CorporateTaxEngine, CorporateTaxResult
from qcre.tax.rates import RateBook, get_ratebook
from qcre.tax.trust import DeemedDispositionForecast, TrustEngine


@dataclass
class TaxPosition:
    noi: Money
    mortgage_interest: Money
    rental_income_before_cca: Money
    cca_results: list[CCAResult]
    cca_claimed: Money
    taxable_rental_income: Money
    corporate: CorporateTaxResult


def _sum_tagged(company: Company, account_type: AccountType, tag: str, *, property_id=None) -> Money:
    fy = company.fiscal_year
    total = Money.zero()
    for a in company.ledger.chart.by_type(account_type):
        if tag in a.tags:
            total += company.ledger.balance(
                a.code, start=fy.start, end=fy.end, property_id=property_id)
    return total.round(2)


def noi(company: Company, *, property_id: str | None = None) -> Money:
    rev = _sum_tagged(company, AccountType.REVENUE, "noi", property_id=property_id)
    opx = _sum_tagged(company, AccountType.EXPENSE, "noi", property_id=property_id)
    return (rev - opx).round(2)


def mortgage_interest(company: Company, *, property_id: str | None = None) -> Money:
    fy = company.fiscal_year
    return company.ledger.balance("5200", start=fy.start, end=fy.end, property_id=property_id)


def tax_position(company: Company, ratebook: RateBook | None = None) -> TaxPosition:
    rb = ratebook or get_ratebook(company.year)
    cca_engine = CCAEngine(rb)

    total_noi = noi(company)
    interest = mortgage_interest(company)
    before_cca = (total_noi - interest).round(2)

    # First-year CCA on each building (additions = building cost incl. capitalised costs).
    cca_results: list[CCAResult] = []
    for p in company.properties:
        building_addition = company.ledger.balance(
            "1500", start=company.fiscal_year.start, end=company.fiscal_year.end,
            property_id=p.property_id,
        )
        if building_addition.is_positive():
            cca_results.append(cca_engine.compute(
                CCAPool(p.building_cca_class, building_id=p.property_id),
                additions=building_addition,
            ))
    # Respect the rental-loss restriction: CCA cannot create/increase a rental loss.
    cca_results = apply_rental_loss_restriction(cca_results, before_cca)
    cca_total = sum((r.cca_claimed for r in cca_results), Money.zero()).round(2)
    taxable_rental = (before_cca - cca_total).round(2)

    corp = CorporateTaxEngine(rb).compute(
        CorporateIncome(rental_income=taxable_rental),
        CorporateProfile(
            full_time_employees=company.full_time_employees,
            quebec_paid_hours=company.quebec_paid_hours,
        ),
    )
    return TaxPosition(
        noi=total_noi, mortgage_interest=interest, rental_income_before_cca=before_cca,
        cca_results=cca_results, cca_claimed=cca_total,
        taxable_rental_income=taxable_rental, corporate=corp,
    )


def property_kpis(company: Company, prop: Property, ratebook: RateBook | None = None) -> PropertyKPIs:
    fy = company.fiscal_year
    mort = next((m for m in company.mortgages if m.property_id == prop.property_id), None)
    debt_service = (mort.payment * 12).round(2) if mort else Money.zero()
    loan_balance = mort.balance_at(company.year) if mort else Money.zero()
    market_value = prop.municipal_value if prop.municipal_value.is_positive() else prop.purchase_price
    equity = (prop.purchase_price - (mort.principal if mort else Money.zero())).round(2)
    egi = _sum_tagged(company, AccountType.REVENUE, "noi", property_id=prop.property_id)
    opex = _sum_tagged(company, AccountType.EXPENSE, "noi", property_id=prop.property_id)
    return PropertyKPIs(
        noi=noi(company, property_id=prop.property_id),
        market_value=market_value, annual_debt_service=debt_service, loan_balance=loan_balance,
        equity_invested=equity, gross_potential_rent=prop.gross_potential_rent(),
        operating_expenses=opex, effective_gross_income=egi,
    )


def portfolio_view(company: Company, ratebook: RateBook | None = None):
    per = [(p, property_kpis(company, p, ratebook)) for p in company.properties]
    agg = portfolio_kpis([k for _, k in per]) if per else None
    return per, agg


def commercial_taxable_supplies(company: Company) -> Money:
    fy = company.fiscal_year
    return company.ledger.balance("4010", start=fy.start, end=fy.end)


def deemed_disposition(company: Company, ratebook: RateBook | None = None
                       ) -> DeemedDispositionForecast | None:
    if company.trust_created is None:
        return None
    rb = ratebook or get_ratebook(company.year)
    # Use municipal values as a fair-value proxy for the trust's underlying property.
    fmv = sum((p.municipal_value for p in company.properties), Money.zero())
    acb = sum((p.purchase_price for p in company.properties), Money.zero())
    as_of = date(company.year, 6, 30)
    return TrustEngine(rb).deemed_disposition_forecast(company.trust_created, fmv, acb, as_of)


def advisory(company: Company, ratebook: RateBook | None = None) -> list[AdvisoryItem]:
    rb = ratebook or get_ratebook(company.year)
    pos = tax_position(company, rb)
    _, agg = portfolio_view(company, rb)
    return build_advisory(
        corporate=pos.corporate,
        rental_income=pos.taxable_rental_income,
        kpis=agg,
        deemed_disposition=deemed_disposition(company, rb),
        commercial_taxable_supplies=commercial_taxable_supplies(company),
        is_gst_registered=True,
        ratebook=rb,
    )
