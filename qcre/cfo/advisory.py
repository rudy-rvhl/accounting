"""Advisory engine — turns tax and KPI signals into actionable CFO recommendations.

Aggregates the outputs of the tax engine and the KPI module into a ranked list of
flags: the cost of specified-investment-business treatment, TOSI exposure on planned
distributions, the 21-year trust horizon, CDA payout opportunities, GST/QST registration,
and financing-risk thresholds (DSCR, LTV, break-even occupancy).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from qcre.cfo.kpis import PropertyKPIs
from qcre.core.money import Money
from qcre.tax.corporate import CorporateTaxResult
from qcre.tax.optimization import Optimizer
from qcre.tax.rates import RateBook, get_ratebook
from qcre.tax.trust import DeemedDispositionForecast, TOSIResult


class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    OPPORTUNITY = "opportunity"
    INFO = "info"

    @property
    def rank(self) -> int:
        return {"critical": 0, "warning": 1, "opportunity": 2, "info": 3}[self.value]


@dataclass(frozen=True)
class AdvisoryItem:
    severity: Severity
    category: str
    title: str
    message: str
    impact: Money | None = None


def build_advisory(
    *,
    corporate: CorporateTaxResult | None = None,
    rental_income: Money | None = None,
    kpis: PropertyKPIs | None = None,
    tosi_results: list[TOSIResult] | None = None,
    deemed_disposition: DeemedDispositionForecast | None = None,
    cda_balance: Money | None = None,
    commercial_taxable_supplies: Money | None = None,
    is_gst_registered: bool | None = None,
    ratebook: RateBook | None = None,
) -> list[AdvisoryItem]:
    rb = ratebook or get_ratebook()
    items: list[AdvisoryItem] = []

    # --- Structure / income characterization ---
    if corporate is not None and corporate.rental_is_sib and rental_income and rental_income.is_positive():
        cost = Optimizer(rb).cost_of_specified_investment_business(rental_income)
        items.append(AdvisoryItem(
            Severity.WARNING, "Structure",
            "Rental income taxed at the high investment rate (specified investment business)",
            f"With ≤5 full-time employees, rental profit is investment income taxed at "
            f"≈{rb.corporate.combined_investment*100:.2f}% instead of the {rb.corporate.combined_sbd*100:.1f}% "
            f"small-business rate. The {rb.corporate.rdtoh_refundable_rate*100:.2f}% refundable portion "
            f"is only recovered when taxable dividends are paid. Evaluate whether active-business "
            f"treatment (>5 full-time employees) is achievable and worth the added payroll.",
            impact=cost.annual_difference,
        ))

    if corporate is not None and corporate.quebec_sbd_factor < 1 and corporate.sbd_income.is_positive():
        items.append(AdvisoryItem(
            Severity.WARNING, "Structure",
            "Quebec small business deduction reduced (5,500-hour test)",
            f"The corporation does not meet the 5,500 paid-hours test, so the Quebec portion of "
            f"the small business deduction is reduced (factor {corporate.quebec_sbd_factor:.2f}). "
            f"Effective small-business rate {corporate.effective_sbd_rate*100:.2f}%.",
        ))

    # --- TOSI on distributions ---
    for t in tosi_results or []:
        if t.applies:
            items.append(AdvisoryItem(
                Severity.WARNING, "Tax",
                f"TOSI applies to distribution to {t.beneficiary}",
                f"The {t.distribution.format()} dividend routed through the trust is taxed at the "
                f"top marginal rate (≈{t.effective_rate*100:.1f}%) because the 'excluded shares' "
                f"exclusion fails for trust-held shares. Income-splitting works only for "
                f"beneficiaries actively engaged ≥20 hrs/week or an owner's spouse aged 65+.",
                impact=t.tax,
            ))

    # --- 21-year deemed disposition ---
    if deemed_disposition is not None:
        sev = Severity.CRITICAL if deemed_disposition.years_remaining <= 3 else (
            Severity.WARNING if deemed_disposition.years_remaining <= 7 else Severity.INFO)
        items.append(AdvisoryItem(
            sev, "Structure",
            f"Trust 21-year deemed disposition in {deemed_disposition.years_remaining} year(s)",
            f"On {deemed_disposition.anniversary.isoformat()} the trust is deemed to dispose of its "
            f"capital property at fair value, triggering tax on the accrued gain. Plan ahead — e.g. "
            f"roll property out to beneficiaries at cost before the date.",
            impact=deemed_disposition.result.taxable_capital_gain,
        ))

    # --- CDA payout opportunity ---
    if cda_balance is not None and cda_balance.is_positive():
        items.append(AdvisoryItem(
            Severity.OPPORTUNITY, "Tax",
            "Capital Dividend Account balance available",
            f"A capital dividend election lets you pay {cda_balance.format()} to shareholders "
            f"completely tax-free. File Form T2054 before paying the dividend.",
            impact=cda_balance,
        ))

    # --- GST/QST registration ---
    if commercial_taxable_supplies is not None and is_gst_registered is False:
        if commercial_taxable_supplies > rb.sales_tax.registration_threshold:
            items.append(AdvisoryItem(
                Severity.CRITICAL, "Compliance",
                "GST/QST registration required",
                f"Taxable (commercial) supplies of {commercial_taxable_supplies.format()} exceed the "
                f"{rb.sales_tax.registration_threshold.format()} small-supplier threshold. You must "
                f"register, charge GST/QST on commercial rent, and you may then claim ITCs/ITRs.",
            ))

    # --- Financing risk (KPIs) ---
    if kpis is not None:
        if kpis.annual_debt_service.is_positive() and kpis.dscr < Decimal("1.2"):
            items.append(AdvisoryItem(
                Severity.WARNING, "Financing",
                f"Debt-service coverage is tight (DSCR {kpis.dscr:.2f}x)",
                "Lenders typically require DSCR ≥ 1.20x for multi-residential / commercial. NOI "
                "leaves little cushion above debt service — refinancing or rate increases are a risk.",
            ))
        if kpis.ltv > Decimal("0.75"):
            items.append(AdvisoryItem(
                Severity.WARNING, "Financing",
                f"High loan-to-value ({kpis.ltv*100:.0f}%)",
                "LTV above ~75% limits refinancing flexibility and raises risk if values soften.",
            ))
        if kpis.break_even_occupancy > Decimal("0.85"):
            items.append(AdvisoryItem(
                Severity.WARNING, "Operations",
                f"High break-even occupancy ({kpis.break_even_occupancy*100:.0f}%)",
                "Little vacancy cushion before the property stops covering costs and debt service.",
            ))

    items.sort(key=lambda i: i.severity.rank)
    return items
