"""Double-entry journal entries.

A :class:`JournalEntry` is a dated, balanced set of debit/credit lines. Entries are
validated on construction so an unbalanced entry can never be posted — the foundation of
trustworthy books. Each line touches one account and carries either a debit *or* a credit
(never both).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from itertools import count

from qcre.core.money import Money

_entry_ids = count(1)


@dataclass(frozen=True)
class JournalLine:
    account_code: str
    debit: Money = field(default_factory=Money.zero)
    credit: Money = field(default_factory=Money.zero)
    memo: str = ""
    # Optional dimension for per-property reporting.
    property_id: str | None = None

    def __post_init__(self) -> None:
        if self.debit.is_negative() or self.credit.is_negative():
            raise ValueError("Journal line debit/credit must be non-negative")
        if not self.debit.is_zero() and not self.credit.is_zero():
            raise ValueError("A journal line cannot have both a debit and a credit")
        if self.debit.is_zero() and self.credit.is_zero():
            raise ValueError("A journal line must have a non-zero debit or credit")

    @property
    def signed(self) -> Money:
        """Debit positive, credit negative — used to assert entries balance to zero."""
        return self.debit - self.credit


@dataclass
class JournalEntry:
    date: date
    description: str
    lines: list[JournalLine]
    reference: str = ""
    source: str = ""  # e.g. "rent_invoice", "acquisition", "cca" — provenance for audit
    property_id: str | None = None
    id: int = field(default_factory=lambda: next(_entry_ids))

    def __post_init__(self) -> None:
        if len(self.lines) < 2:
            raise ValueError("A journal entry needs at least two lines")
        if not self.is_balanced():
            raise ValueError(
                f"Journal entry {self.id} is out of balance by {self.imbalance()}: "
                f"debits {self.total_debits()} vs credits {self.total_credits()}"
            )

    def total_debits(self) -> Money:
        return sum((ln.debit for ln in self.lines), Money.zero())

    def total_credits(self) -> Money:
        return sum((ln.credit for ln in self.lines), Money.zero())

    def imbalance(self) -> Money:
        return (self.total_debits() - self.total_credits()).round(2)

    def is_balanced(self) -> bool:
        return self.imbalance().is_zero()
