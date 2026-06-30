"""Estate freeze and 21-year deemed-disposition planning for the family trust.

**Estate freeze** — the parent exchanges their growth (common) shares for fixed-value
preferred shares equal to today's fair market value, on a tax-deferred basis under ITA
s.85 or s.86, while new common shares are issued to the family trust for nominal value.
The effect: the parent's accrued gain is **frozen** at today's value (deferred, not
triggered), and **all future growth accrues to the trust/children** — outside the
parent's estate, multiplying capital gains exemptions and easing the eventual estate tax.

**21-year planning** — under s.104(4) the trust is deemed to dispose of its capital
property at FMV every 21 years. The classic planning choice is:

* **Pay the tax** — recognise the accrued gain in the trust (taxed at the top marginal
  rate, since an inter-vivos trust has no graduated brackets), or
* **Roll the property out to beneficiaries at cost** under s.107(2) before the
  anniversary — no tax now; the beneficiaries inherit the ACB and the gain is deferred
  until they actually sell.

This module quantifies both so the deferral can be weighed against the trade-offs
(beneficiaries must be Canadian-resident; control/creditor-protection considerations).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from qcre.core.money import Money
from qcre.tax.capital import CapitalGainsEngine
from qcre.tax.rates import RateBook, get_ratebook
from qcre.tax.trust import TrustEngine


@dataclass(frozen=True)
class EstateFreezeResult:
    freeze_date: date
    freeze_value: Money            # parent's preferred shares (capped estate value)
    acb: Money
    deferred_gain: Money           # accrued gain rolled over (not triggered now)
    horizon_years: int
    projected_value_at_horizon: Money
    growth_shifted_to_trust: Money     # value moved out of the parent's estate
    estate_tax_deferred_estimate: Money
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DeemedDispositionPlan:
    anniversary: date
    years_remaining: int
    acb: Money
    projected_fmv: Money
    capital_gain: Money
    tax_if_pay: Money              # pay the deemed-disposition tax in the trust
    tax_if_rollout: Money          # roll out to beneficiaries at cost (s.107(2)) → nil now
    tax_deferred_by_rollout: Money
    recommendation: str
    notes: list[str] = field(default_factory=list)


class EstateFreezePlanner:
    def __init__(self, ratebook: RateBook | None = None) -> None:
        self.rb = ratebook or get_ratebook()
        self._cg = CapitalGainsEngine(self.rb)
        self._trust = TrustEngine(self.rb)

    def freeze(
        self,
        current_fmv: Money,
        acb: Money,
        *,
        freeze_date: date,
        annual_growth: Decimal = Decimal("0.04"),
        horizon_years: int = 21,
    ) -> EstateFreezeResult:
        projected = (current_fmv * (Decimal(1) + annual_growth) ** horizon_years).round(2)
        growth_shifted = (projected - current_fmv).round(2)
        deferred_gain = max(Money.zero(), current_fmv - acb, key=lambda m: m.amount).round(2)

        # Tax the parent would otherwise face on the *growth* (50% inclusion at top rate),
        # now shifted to the next generation / trust.
        taxable_growth = (growth_shifted * self.rb.capital_gains.inclusion_rate).round(2)
        estate_tax_deferred = (taxable_growth * self.rb.personal.top_combined_rate).round(2)

        notes = [
            "Freeze done on a tax-deferred basis under ITA s.85 (or s.86 reorganization) — "
            "no capital gain is triggered today; the parent's accrued gain is preserved on "
            "the preferred shares.",
            f"The parent's estate value is capped at {current_fmv.format()}; the estimated "
            f"{growth_shifted.format()} of future growth over {horizon_years} years accrues to "
            f"the trust/children instead.",
            "Consider price-adjustment clauses and ensuring the preferred shares' redemption "
            "value equals FMV to avoid a deemed benefit. Review with a tax advisor.",
        ]
        return EstateFreezeResult(
            freeze_date=freeze_date, freeze_value=current_fmv.round(2), acb=acb.round(2),
            deferred_gain=deferred_gain, horizon_years=horizon_years,
            projected_value_at_horizon=projected, growth_shifted_to_trust=growth_shifted,
            estate_tax_deferred_estimate=estate_tax_deferred, notes=notes,
        )

    def deemed_disposition_plan(
        self,
        trust_created: date,
        current_fmv: Money,
        acb: Money,
        *,
        as_of: date,
        annual_growth: Decimal = Decimal("0.04"),
    ) -> DeemedDispositionPlan:
        anniversary = self._trust.next_deemed_disposition(trust_created, as_of)
        years_remaining = anniversary.year - as_of.year
        projected_fmv = (current_fmv * (Decimal(1) + annual_growth) ** max(years_remaining, 0)).round(2)

        gain = self._cg.on_disposition(proceeds=projected_fmv, acb=acb)
        # Inter-vivos trust: no graduated rates → top marginal rate on the taxable gain.
        tax_if_pay = (gain.taxable_capital_gain * self.rb.personal.top_combined_rate).round(2)
        tax_if_rollout = Money.zero()  # s.107(2) rollout at cost defers the gain

        rec = (
            "ROLL OUT to Canadian-resident beneficiaries at cost (s.107(2)) before the "
            f"anniversary to defer {tax_if_pay.format()} of tax — provided beneficiaries can "
            "hold the property and control/creditor-protection goals still allow it."
            if tax_if_pay.is_positive() else
            "No accrued gain projected — minimal 21-year exposure; revisit as values change."
        )
        notes = [
            f"On {anniversary.isoformat()} ({years_remaining} yr) the trust is deemed to dispose "
            f"of its capital property at FMV (s.104(4)).",
            f"Projected FMV {projected_fmv.format()} vs ACB {acb.format()} → capital gain "
            f"{gain.gain.format()} ({gain.taxable_capital_gain.format()} taxable at 50%).",
            "A rollout deconverts the trust gain into a deferred gain in the beneficiaries' "
            "hands; they inherit the ACB and pay tax only on an eventual sale.",
        ]
        return DeemedDispositionPlan(
            anniversary=anniversary, years_remaining=years_remaining, acb=acb.round(2),
            projected_fmv=projected_fmv, capital_gain=gain.gain,
            tax_if_pay=tax_if_pay, tax_if_rollout=tax_if_rollout,
            tax_deferred_by_rollout=tax_if_pay, recommendation=rec, notes=notes,
        )
