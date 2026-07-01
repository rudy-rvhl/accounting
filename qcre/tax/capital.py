"""Capital gains, adjusted cost base, and the Capital Dividend Account (CDA).

On a disposition the **capital gain** is proceeds − adjusted cost base (ACB) − outlays
(selling costs). For 2025/2026 the **inclusion rate is 50%** (the proposed increase to
66.67% was cancelled). For a corporation, the **non-taxable half of a net capital gain is
added to the Capital Dividend Account**, from which tax-free capital dividends can be paid
to shareholders — a cornerstone of real-estate tax planning.

A building disposition typically has *two* tax consequences handled together by the
domain layer: CCA **recapture** up to original cost (ordinary income, see
:mod:`qcre.tax.cca`) and a **capital gain** on any proceeds above original cost. Land has
no CCA, so only a capital gain/loss arises.
"""

from __future__ import annotations

from dataclasses import dataclass

from qcre.core.money import Money
from qcre.tax.rates import RateBook, get_ratebook


@dataclass(frozen=True)
class CapitalGainResult:
    proceeds: Money
    outlays: Money
    acb: Money
    gain: Money               # positive = capital gain, negative = capital loss
    taxable_capital_gain: Money
    allowable_capital_loss: Money
    cda_addition: Money       # non-taxable half added to the corporation's CDA

    @property
    def is_gain(self) -> bool:
        return self.gain.is_positive()


class CapitalGainsEngine:
    def __init__(self, ratebook: RateBook | None = None) -> None:
        self.rb = ratebook or get_ratebook()

    @property
    def inclusion_rate(self):
        return self.rb.capital_gains.inclusion_rate

    def on_disposition(
        self,
        proceeds: Money,
        acb: Money,
        outlays: Money = Money.zero(),
    ) -> CapitalGainResult:
        gain = (proceeds - outlays - acb).round(2)
        rate = self.inclusion_rate
        if gain.is_positive():
            taxable = (gain * rate).round(2)
            non_taxable = (gain - taxable).round(2)
            return CapitalGainResult(
                proceeds.round(2), outlays.round(2), acb.round(2), gain,
                taxable, Money.zero(), non_taxable,
            )
        loss = (-gain).round(2)
        allowable = (loss * rate).round(2)
        # A capital loss reduces the CDA by the non-taxable portion of the loss.
        cda_reduction = (loss - allowable).round(2)
        return CapitalGainResult(
            proceeds.round(2), outlays.round(2), acb.round(2), gain,
            Money.zero(), allowable, (-cda_reduction).round(2),
        )

    @staticmethod
    def adjusted_cost_base(
        purchase_price: Money,
        acquisition_costs: Money = Money.zero(),
        capital_improvements: Money = Money.zero(),
    ) -> Money:
        """ACB = purchase price + acquisition costs (incl. transfer duty, legal) + capex."""
        return (purchase_price + acquisition_costs + capital_improvements).round(2)
