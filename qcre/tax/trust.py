"""Family-trust taxation: the 21-year rule and TOSI screening.

Two issues dominate when a family trust owns the shares of a real-estate CCPC:

1. **21-year deemed disposition** (ITA s.104(4), citation 'trust_21yr'): most inter-vivos
   trusts are deemed to dispose of their capital property at fair market value every 21
   years, triggering tax on accrued gains even though nothing was sold. The engine tracks
   the anniversary and sizes the deemed gain so it can be planned for (e.g. roll out to
   beneficiaries before the date).

2. **Tax on split income (TOSI)** (ITA s.120.4, citation 'tosi'): dividends a trust
   distributes to family beneficiaries are taxed at the **top marginal rate** unless an
   exclusion applies. Crucially, the **"excluded shares" exclusion fails for trust-held
   shares** — it requires the individual to own ≥10% of votes *and* value **directly**.
   So income-splitting through a trust usually only works for a beneficiary who is
   **actively engaged ≥20 hours/week** in the business (the "excluded business"
   exclusion) or for an owner's **spouse aged 65+**.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from qcre.core.money import Money
from qcre.tax.capital import CapitalGainResult, CapitalGainsEngine
from qcre.tax.personal import PersonalTaxEngine
from qcre.tax.rates import RateBook, get_ratebook


# --- 21-year deemed disposition --------------------------------------------
@dataclass(frozen=True)
class DeemedDispositionForecast:
    anniversary: date
    years_remaining: int
    fmv: Money
    acb: Money
    result: CapitalGainResult


class TrustEngine:
    def __init__(self, ratebook: RateBook | None = None) -> None:
        self.rb = ratebook or get_ratebook()
        self._cg = CapitalGainsEngine(self.rb)

    def next_deemed_disposition(self, trust_created: date, as_of: date) -> date:
        n = self.rb.trust.deemed_disposition_years
        anniversary = date(trust_created.year + n, trust_created.month, trust_created.day)
        while anniversary < as_of:
            anniversary = date(anniversary.year + n, anniversary.month, anniversary.day)
        return anniversary

    def deemed_disposition_forecast(
        self, trust_created: date, fmv: Money, acb: Money, as_of: date
    ) -> DeemedDispositionForecast:
        anniversary = self.next_deemed_disposition(trust_created, as_of)
        years_remaining = anniversary.year - as_of.year
        result = self._cg.on_disposition(proceeds=fmv, acb=acb)
        return DeemedDispositionForecast(anniversary, years_remaining, fmv, acb, result)


# --- TOSI screening ---------------------------------------------------------
@dataclass
class BeneficiaryFacts:
    name: str
    age: int
    hours_per_week_in_business: Decimal = Decimal("0")  # ≥20 → excluded business
    worked_20h_prior_5yrs: bool = False
    owns_shares_directly_pct: Decimal = Decimal("0")    # ≥10% direct → excluded-shares test
    is_owner_spouse_65plus: bool = False                # owner is related & 65+
    business_is_services: bool = False                  # rental is generally not a services business


@dataclass(frozen=True)
class TOSIResult:
    beneficiary: str
    distribution: Money
    eligible_dividend: bool
    applies: bool
    reason: str
    tax: Money
    effective_rate: Decimal

    @property
    def after_tax(self) -> Money:
        return (self.distribution - self.tax).round(2)


class TOSIScreener:
    def __init__(self, ratebook: RateBook | None = None) -> None:
        self.rb = ratebook or get_ratebook()
        self._personal = PersonalTaxEngine(self.rb)

    def _exclusion(self, f: BeneficiaryFacts) -> str | None:
        """Return the name of the applicable TOSI exclusion, or None if TOSI applies."""
        if f.age < 18:
            return None  # minors: split income essentially always caught
        if f.hours_per_week_in_business >= 20 or f.worked_20h_prior_5yrs:
            return "excluded business (actively engaged ≥20 hrs/week)"
        if f.is_owner_spouse_65plus:
            return "excluded amount — spouse of owner aged 65+"
        if f.owns_shares_directly_pct >= 10 and not f.business_is_services:
            return "excluded shares (≥10% direct ownership)"
        return None

    def screen(
        self, facts: BeneficiaryFacts, distribution: Money, *, eligible: bool = False
    ) -> TOSIResult:
        exclusion = self._exclusion(facts)
        if exclusion is not None:
            # Not split income: taxed at the beneficiary's own marginal rates (estimate as
            # a stand-alone amount at the bottom of their bracket → use personal engine).
            res = self._personal.compute(
                eligible_dividends=distribution if eligible else Money.zero(),
                non_eligible_dividends=Money.zero() if eligible else distribution,
            )
            return TOSIResult(
                facts.name, distribution.round(2), eligible, False,
                f"TOSI does not apply: {exclusion}.", res.total_tax, res.average_rate,
            )

        # TOSI applies → tax the dividend at the top marginal bracket.
        p = self.rb.personal
        top_threshold = Money(p.federal.brackets[-1].up_to or 260000) + Money("1")
        base = self._personal.compute(ordinary_income=top_threshold)
        with_div = self._personal.compute(
            ordinary_income=top_threshold,
            eligible_dividends=distribution if eligible else Money.zero(),
            non_eligible_dividends=Money.zero() if eligible else distribution,
        )
        tax = (with_div.total_tax - base.total_tax).round(2)
        rate = (tax.amount / distribution.amount) if distribution.is_positive() else Decimal(0)
        reason = (
            "TOSI APPLIES — taxed at the top marginal rate. The 'excluded shares' exclusion "
            "is unavailable because the shares are held through the trust (≥10% direct "
            "ownership is required), and no other exclusion (active engagement, 65+ spouse) "
            "was met."
        )
        return TOSIResult(facts.name, distribution.round(2), eligible, True, reason, tax, rate)
