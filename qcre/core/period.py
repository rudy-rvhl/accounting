"""Fiscal year / period helpers.

A corporation may have a non-calendar fiscal year-end. ``FiscalYear`` captures the start
and end dates so the ledger and statements can be sliced consistently. Defaults to a
calendar year, which is the common choice for a real-estate holding corporation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class FiscalYear:
    start: date
    end: date

    @classmethod
    def calendar(cls, year: int) -> "FiscalYear":
        return cls(date(year, 1, 1), date(year, 12, 31))

    @classmethod
    def ending(cls, year_end: date) -> "FiscalYear":
        """Fiscal year of length up to one year ending on *year_end*."""
        try:
            start = year_end.replace(year=year_end.year - 1)
        except ValueError:  # Feb 29 -> Mar 1 start
            start = date(year_end.year - 1, 3, 1)
        start = date(start.year, start.month, start.day)
        return cls(start.replace(day=start.day), year_end)

    @property
    def label(self) -> str:
        if (self.start.month, self.start.day) == (1, 1) and (
            self.end.month,
            self.end.day,
        ) == (12, 31):
            return str(self.end.year)
        return f"{self.start.isoformat()} to {self.end.isoformat()}"

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def contains(self, d: date) -> bool:
        return self.start <= d <= self.end
