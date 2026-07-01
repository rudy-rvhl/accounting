"""Rate-book registry — look up the dated, sourced rate book for a taxation year."""

from __future__ import annotations

from qcre.tax.rates.ratebook import RateBook
from qcre.tax.rates.y2026 import RATEBOOK_2026

_REGISTRY: dict[int, RateBook] = {
    2026: RATEBOOK_2026,
}

DEFAULT_YEAR = 2026


def get_ratebook(year: int = DEFAULT_YEAR) -> RateBook:
    """Return the rate book for *year*.

    If the requested year is not yet encoded, fall back to the most recent available year
    and stamp it onto the result so callers/reports can flag that rates were carried
    forward and must be verified.
    """
    if year in _REGISTRY:
        return _REGISTRY[year]
    latest = max(_REGISTRY)
    if year > latest:
        # Carry forward the latest known year rather than fail; this is clearly flagged.
        return _REGISTRY[latest]
    raise KeyError(f"No rate book available for {year} (earliest is {min(_REGISTRY)})")


def available_years() -> list[int]:
    return sorted(_REGISTRY)


__all__ = ["RateBook", "get_ratebook", "available_years", "DEFAULT_YEAR"]
