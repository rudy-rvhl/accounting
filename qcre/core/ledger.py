"""General ledger: posts balanced journal entries and reports balances.

The ledger holds the chart of accounts and the list of posted entries, and computes
account balances (optionally filtered by date range or property), the trial balance, and
a per-account general-ledger listing. Balances are returned with the account's natural
sign (debit-normal accounts positive on a net debit, credit-normal positive on a net
credit) so revenue/expense/asset numbers read naturally on statements.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from qcre.core.accounts import ChartOfAccounts
from qcre.core.journal import JournalEntry
from qcre.core.money import Money


@dataclass
class TrialBalanceRow:
    code: str
    name: str
    debit: Money
    credit: Money


class Ledger:
    def __init__(self, chart: ChartOfAccounts) -> None:
        self.chart = chart
        self.entries: list[JournalEntry] = []

    # -- posting -------------------------------------------------------------
    def post(self, entry: JournalEntry) -> JournalEntry:
        for line in entry.lines:
            if line.account_code not in self.chart:
                raise KeyError(
                    f"Entry {entry.id} posts to unknown account {line.account_code}"
                )
        if not entry.is_balanced():
            raise ValueError(f"Refusing to post unbalanced entry {entry.id}")
        self.entries.append(entry)
        return entry

    def post_all(self, entries: list[JournalEntry]) -> None:
        for e in entries:
            self.post(e)

    # -- queries -------------------------------------------------------------
    def _filtered_lines(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
        property_id: str | None = None,
    ):
        for entry in self.entries:
            if start and entry.date < start:
                continue
            if end and entry.date > end:
                continue
            for line in entry.lines:
                if property_id is not None:
                    line_prop = line.property_id or entry.property_id
                    if line_prop != property_id:
                        continue
                yield line

    def balance(
        self,
        code: str,
        *,
        start: date | None = None,
        end: date | None = None,
        property_id: str | None = None,
    ) -> Money:
        """Net balance of one account in the account's natural (positive) direction."""
        account = self.chart.get(code)
        net = Money.zero()
        for line in self._filtered_lines(start=start, end=end, property_id=property_id):
            if line.account_code == code:
                net += line.signed  # debit positive, credit negative
        return (net if account.is_debit_normal() else -net).round(2)

    def balances_by_tag(
        self, tag: str, *, start: date | None = None, end: date | None = None,
        property_id: str | None = None,
    ) -> Money:
        """Sum of natural balances of all accounts carrying *tag*."""
        total = Money.zero()
        for account in self.chart.by_tag(tag):
            total += self.balance(
                account.code, start=start, end=end, property_id=property_id
            )
        return total.round(2)

    def trial_balance(
        self, *, start: date | None = None, end: date | None = None
    ) -> list[TrialBalanceRow]:
        net_by_code: dict[str, Money] = defaultdict(Money.zero)
        for line in self._filtered_lines(start=start, end=end):
            net_by_code[line.account_code] += line.signed
        rows: list[TrialBalanceRow] = []
        for account in self.chart:
            net = net_by_code.get(account.code, Money.zero()).round(2)
            if net.is_zero():
                continue
            if net.is_positive():
                rows.append(TrialBalanceRow(account.code, account.name, net, Money.zero()))
            else:
                rows.append(TrialBalanceRow(account.code, account.name, Money.zero(), -net))
        return rows

    def trial_balance_totals(
        self, *, start: date | None = None, end: date | None = None
    ) -> tuple[Money, Money]:
        rows = self.trial_balance(start=start, end=end)
        debits = sum((r.debit for r in rows), Money.zero())
        credits = sum((r.credit for r in rows), Money.zero())
        return debits.round(2), credits.round(2)

    def is_in_balance(self, *, start: date | None = None, end: date | None = None) -> bool:
        debits, credits = self.trial_balance_totals(start=start, end=end)
        return (debits - credits).round(2).is_zero()
