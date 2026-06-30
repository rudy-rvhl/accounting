"""Accounting framework selection.

The engine is framework-agnostic at its core. The default is **ASPE** (CPA Canada
Handbook Part II), under which real estate is carried at **cost less accumulated
amortization** — the norm for private Quebec real-estate companies. Selecting **IFRS**
enables the IAS 40 **fair-value model**: investment property is carried at fair value with
revaluation gains/losses recognised in profit or loss (no amortization).
"""

from __future__ import annotations

from enum import Enum


class Framework(str, Enum):
    ASPE = "ASPE"
    IFRS = "IFRS"

    @property
    def carries_investment_property_at_fair_value(self) -> bool:
        return self is Framework.IFRS

    @property
    def label(self) -> str:
        if self is Framework.ASPE:
            return "ASPE (cost model — CPA Canada Handbook Part II)"
        return "IFRS (IAS 40 fair-value model)"
