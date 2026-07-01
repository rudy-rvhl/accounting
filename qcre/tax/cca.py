"""Capital cost allowance (CCA) — the tax depreciation engine.

Encodes (citation 'cca'):

* Declining-balance pools by class (Class 1 building 4%; 6% eligible non-residential;
  10% new purpose-built residential rental; Class 8 20%; Class 50 55%; etc.).
* The **half-year rule**: in the year of acquisition CCA applies to only half of net
  additions (suspended for accelerated-investment-incentive property — AII is phasing out
  and gone after 2027, so the engine uses the half-year rule by default).
* **Recapture** (negative UCC → taxable income) and **terminal loss** (positive UCC with
  no assets left → deductible) on disposition; a disposition reduces the pool by the
  *lesser of* proceeds and original capital cost (the excess is a capital gain — see
  :mod:`qcre.tax.capital`).
* The **rental-loss restriction**: CCA cannot create or increase a loss from renting
  property. :func:`apply_rental_loss_restriction` caps the aggregate claim at net rental
  income before CCA.
* A separate Class 1 pool should be kept for each rental building costing ≥ $50,000; the
  pool carries an optional ``building_id`` so callers can honour this.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from qcre.core.money import Money
from qcre.tax.rates import RateBook, get_ratebook


@dataclass
class CCAPool:
    cca_class: str
    opening_ucc: Money = field(default_factory=Money.zero)
    building_id: str | None = None
    straight_line_life_years: int | None = None  # for Class 13 leasehold improvements


@dataclass(frozen=True)
class CCAResult:
    cca_class: str
    opening_ucc: Money
    additions: Money
    dispositions: Money            # lesser of proceeds and capital cost
    ucc_before_cca: Money
    rate: Decimal
    cca_claimed: Money
    closing_ucc: Money
    recapture: Money               # taxable income (added back)
    terminal_loss: Money           # deductible loss
    building_id: str | None = None

    @property
    def is_building(self) -> bool:
        return self.cca_class.startswith("1")


class CCAEngine:
    def __init__(self, ratebook: RateBook | None = None) -> None:
        self.rb = ratebook or get_ratebook()

    def rate_for(self, cca_class: str) -> Decimal:
        try:
            return self.rb.cca.classes[cca_class].rate
        except KeyError:
            raise KeyError(f"Unknown CCA class: {cca_class}") from None

    def compute(
        self,
        pool: CCAPool,
        *,
        additions: Money = Money.zero(),
        proceeds_of_disposition: Money = Money.zero(),
        capital_cost_of_disposed: Money | None = None,
        class_emptied: bool = False,
        accelerated: bool = False,
        claim_fraction: Decimal = Decimal("1"),
    ) -> CCAResult:
        """Compute one year's CCA for a pool.

        ``claim_fraction`` (0..1) lets a taxpayer claim *less* than the maximum (CCA is
        optional and discretionary) — useful for tax planning and the rental-loss
        restriction. ``proceeds_of_disposition`` reduces the pool by the lesser of
        proceeds and the asset's original capital cost. Set ``class_emptied=True`` when the
        last asset in the class has been disposed of: any positive remaining UCC is then a
        deductible **terminal loss** rather than continuing to depreciate.
        """
        meta = self.rb.cca.classes.get(pool.cca_class)
        rate = meta.rate if meta else self.rate_for(pool.cca_class)

        # Disposition reduces UCC by the lesser of proceeds and original capital cost.
        cost_disposed = (
            capital_cost_of_disposed if capital_cost_of_disposed is not None
            else proceeds_of_disposition
        )
        disposal_reduction = min(proceeds_of_disposition, cost_disposed, key=lambda m: m.amount)

        ucc_before = (pool.opening_ucc + additions - disposal_reduction).round(2)

        recapture = Money.zero()
        terminal_loss = Money.zero()
        cca = Money.zero()
        closing = ucc_before

        if ucc_before.is_negative():
            # Negative pool → recapture into income; pool resets to zero.
            recapture = (-ucc_before).round(2)
            closing = Money.zero()
            return CCAResult(
                pool.cca_class, pool.opening_ucc, additions, disposal_reduction,
                ucc_before, rate, Money.zero(), closing, recapture, terminal_loss,
                pool.building_id,
            )

        if class_emptied and ucc_before.is_positive():
            # Last asset gone but UCC remains → terminal loss (fully deductible).
            terminal_loss = ucc_before.round(2)
            return CCAResult(
                pool.cca_class, pool.opening_ucc, additions, disposal_reduction,
                ucc_before, rate, Money.zero(), Money.zero(), recapture, terminal_loss,
                pool.building_id,
            )

        net_additions = (additions - disposal_reduction)
        if meta and meta.straight_line:
            # Class 13: straight-line over the (remaining) lease term.
            life = pool.straight_line_life_years or 5
            base = ucc_before
            max_cca = (additions / life) if additions.is_positive() else (base / max(life, 1))
            max_cca = min(max_cca, base, key=lambda m: m.amount)
        else:
            half_year_adj = Money.zero()
            if self.rb.cca.half_year_rule and not accelerated and net_additions.is_positive():
                half_year_adj = net_additions * Decimal("0.5")
            cca_base = (ucc_before - half_year_adj)
            if accelerated:
                uplift = Decimal(1) + self.rb.cca.aii_first_year_uplift
                cca_base = ucc_before  # AII suspends the half-year rule
                max_cca = min((cca_base * rate * uplift), ucc_before, key=lambda m: m.amount)
            else:
                max_cca = (cca_base * rate)

        cca = (max_cca * claim_fraction).round(2)
        if cca > ucc_before:
            cca = ucc_before
        closing = (ucc_before - cca).round(2)
        return CCAResult(
            pool.cca_class, pool.opening_ucc, additions, disposal_reduction,
            ucc_before, rate, cca.round(2), closing, recapture, terminal_loss,
            pool.building_id,
        )


def apply_rental_loss_restriction(
    results: list[CCAResult],
    net_rental_income_before_cca: Money,
) -> list[CCAResult]:
    """Cap aggregate CCA so it cannot create/increase a rental loss.

    Recapture is income (it is *not* restricted). If total requested CCA would push net
    rental income below zero, scale the discretionary CCA down pro-rata to exactly use up
    the available income. Returns adjusted results (closing UCC recomputed).
    """
    income_floor = net_rental_income_before_cca
    if income_floor.is_negative():
        income_floor = Money.zero()
    total_cca = sum((r.cca_claimed for r in results), Money.zero())
    if total_cca <= income_floor or total_cca.is_zero():
        return results

    weights = [r.cca_claimed.amount for r in results]
    allowed = income_floor.allocate(weights) if income_floor.is_positive() else [
        Money.zero() for _ in results
    ]
    adjusted: list[CCAResult] = []
    for r, allow in zip(results, allowed):
        capped = min(r.cca_claimed, allow, key=lambda m: m.amount)
        adjusted.append(
            CCAResult(
                r.cca_class, r.opening_ucc, r.additions, r.dispositions,
                r.ucc_before_cca, r.rate, capped.round(2),
                (r.ucc_before_cca - capped).round(2),
                r.recapture, r.terminal_loss, r.building_id,
            )
        )
    return adjusted
