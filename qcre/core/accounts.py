"""Chart of accounts for a Quebec real-estate company.

The default chart is purpose-built for residential + commercial rental operations held in
a corporation: separate residential/commercial revenue (because GST/QST treatment
differs), GST/QST receivable (ITC/ITR) and payable accounts, building vs land,
accumulated amortization contra accounts, mortgage, and shareholder/dividend equity
accounts. Account codes follow the usual 1000-asset / 2000-liability / 3000-equity /
4000-revenue / 5000-expense convention.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AccountType(str, Enum):
    ASSET = "asset"
    CONTRA_ASSET = "contra_asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"

    @property
    def normal_balance(self) -> str:
        """'debit' or 'credit' — the side that increases this account."""
        if self in (AccountType.ASSET, AccountType.EXPENSE):
            return "debit"
        return "credit"


@dataclass(frozen=True)
class Account:
    code: str
    name: str
    type: AccountType
    parent: str | None = None
    # Tax tags help the tax engine find the right balances without hard-coding codes.
    tags: frozenset[str] = field(default_factory=frozenset)

    @property
    def normal_balance(self) -> str:
        # A contra-asset (e.g. accumulated amortization) normally carries a credit.
        if self.type == AccountType.CONTRA_ASSET:
            return "credit"
        return self.type.normal_balance

    def is_debit_normal(self) -> bool:
        return self.normal_balance == "debit"


class ChartOfAccounts:
    """A lookup of accounts by code, with helpers to query by type and tag."""

    def __init__(self, accounts: list[Account] | None = None) -> None:
        self._by_code: dict[str, Account] = {}
        for acc in accounts or []:
            self.add(acc)

    def add(self, account: Account) -> Account:
        if account.code in self._by_code:
            raise ValueError(f"Duplicate account code: {account.code}")
        self._by_code[account.code] = account
        return account

    def get(self, code: str) -> Account:
        try:
            return self._by_code[code]
        except KeyError:
            raise KeyError(f"Unknown account code: {code}") from None

    def __contains__(self, code: str) -> bool:
        return code in self._by_code

    def __iter__(self):
        return iter(self._by_code.values())

    def by_type(self, *types: AccountType) -> list[Account]:
        return [a for a in self._by_code.values() if a.type in types]

    def by_tag(self, tag: str) -> list[Account]:
        return [a for a in self._by_code.values() if tag in a.tags]


# --- Default real-estate chart of accounts ---------------------------------

_DEFAULT_ACCOUNTS: list[tuple[str, str, AccountType, tuple[str, ...]]] = [
    # Assets ---------------------------------------------------------------
    ("1000", "Petty Cash", AccountType.ASSET, ("cash",)),
    ("1010", "Bank — Operating", AccountType.ASSET, ("cash", "bank")),
    ("1020", "Bank — Trust (security deposits)", AccountType.ASSET, ("cash",)),
    ("1100", "Accounts Receivable — Tenants", AccountType.ASSET, ("ar",)),
    ("1110", "Allowance for Doubtful Accounts", AccountType.CONTRA_ASSET, ()),
    ("1200", "GST Receivable (ITC)", AccountType.ASSET, ("gst_itc",)),
    ("1210", "QST Receivable (ITR)", AccountType.ASSET, ("qst_itr",)),
    ("1300", "Prepaid Insurance & Expenses", AccountType.ASSET, ("prepaid",)),
    ("1400", "Land", AccountType.ASSET, ("land",)),
    ("1500", "Buildings", AccountType.ASSET, ("building", "depreciable")),
    ("1510", "Accumulated Amortization — Buildings", AccountType.CONTRA_ASSET, ("accum_amort",)),
    ("1520", "Building Improvements", AccountType.ASSET, ("building", "depreciable")),
    ("1530", "Accumulated Amortization — Improvements", AccountType.CONTRA_ASSET, ("accum_amort",)),
    ("1600", "Furniture, Appliances & Equipment", AccountType.ASSET, ("equipment", "depreciable")),
    ("1610", "Accumulated Amortization — Equipment", AccountType.CONTRA_ASSET, ("accum_amort",)),
    ("1700", "Investment Property — Fair Value Adj. (IFRS)", AccountType.ASSET, ("fv_adjust",)),
    # Liabilities ----------------------------------------------------------
    ("2000", "Accounts Payable", AccountType.LIABILITY, ("ap",)),
    ("2050", "Accrued Liabilities", AccountType.LIABILITY, ()),
    ("2100", "GST Payable", AccountType.LIABILITY, ("gst_payable",)),
    ("2110", "QST Payable", AccountType.LIABILITY, ("qst_payable",)),
    ("2200", "Security Deposits Held", AccountType.LIABILITY, ("deposits",)),
    ("2300", "Accrued Mortgage Interest", AccountType.LIABILITY, ()),
    ("2400", "Mortgage Payable — Current Portion", AccountType.LIABILITY, ("mortgage",)),
    ("2410", "Mortgage Payable — Long Term", AccountType.LIABILITY, ("mortgage",)),
    ("2500", "Due to Shareholder / Trust", AccountType.LIABILITY, ("shareholder_loan",)),
    ("2600", "Income Taxes Payable", AccountType.LIABILITY, ("tax_payable",)),
    ("2650", "Deferred Income Taxes", AccountType.LIABILITY, ("deferred_tax",)),
    ("2700", "Dividends Payable", AccountType.LIABILITY, ()),
    # Equity ---------------------------------------------------------------
    ("3000", "Common Shares", AccountType.EQUITY, ("share_capital",)),
    ("3100", "Retained Earnings", AccountType.EQUITY, ("retained_earnings",)),
    ("3150", "Current Year Earnings", AccountType.EQUITY, ("current_earnings",)),
    ("3200", "Dividends Declared", AccountType.EQUITY, ("dividends",)),
    ("3300", "Revaluation Surplus (IFRS)", AccountType.EQUITY, ("revaluation",)),
    # Revenue --------------------------------------------------------------
    ("4000", "Rental Revenue — Residential", AccountType.REVENUE, ("rent", "rent_residential", "noi")),
    ("4010", "Rental Revenue — Commercial", AccountType.REVENUE, ("rent", "rent_commercial", "noi")),
    ("4020", "Parking & Storage Revenue", AccountType.REVENUE, ("rent", "noi")),
    ("4030", "Laundry & Other Revenue", AccountType.REVENUE, ("noi",)),
    ("4100", "Gain on Disposal of Property", AccountType.REVENUE, ("gain_disposal",)),
    ("4200", "Fair Value Gain — Investment Property (IFRS)", AccountType.REVENUE, ("fv_gain",)),
    # Operating expenses (all part of NOI unless tagged otherwise) ---------
    ("5000", "Municipal & School Property Taxes", AccountType.EXPENSE, ("opex", "noi")),
    ("5010", "Insurance", AccountType.EXPENSE, ("opex", "noi")),
    ("5020", "Utilities", AccountType.EXPENSE, ("opex", "noi")),
    ("5030", "Repairs & Maintenance", AccountType.EXPENSE, ("opex", "noi")),
    ("5040", "Property Management Fees", AccountType.EXPENSE, ("opex", "noi")),
    ("5050", "Superintendent & Wages", AccountType.EXPENSE, ("opex", "noi", "wages")),
    ("5060", "Snow Removal & Landscaping", AccountType.EXPENSE, ("opex", "noi")),
    ("5070", "Advertising & Leasing", AccountType.EXPENSE, ("opex", "noi")),
    ("5080", "Professional Fees (legal & accounting)", AccountType.EXPENSE, ("opex", "noi")),
    ("5090", "Bank Charges & Administration", AccountType.EXPENSE, ("opex", "noi")),
    ("5100", "Condo / Co-ownership Fees", AccountType.EXPENSE, ("opex", "noi")),
    # Below-the-NOI-line costs --------------------------------------------
    ("5200", "Mortgage Interest", AccountType.EXPENSE, ("interest",)),
    ("5300", "Amortization — Buildings", AccountType.EXPENSE, ("amortization",)),
    ("5310", "Amortization — Improvements", AccountType.EXPENSE, ("amortization",)),
    ("5320", "Amortization — Equipment", AccountType.EXPENSE, ("amortization",)),
    ("5400", "Bad Debt Expense", AccountType.EXPENSE, ("opex",)),
    ("5500", "Loss on Disposal of Property", AccountType.EXPENSE, ("loss_disposal",)),
    ("5900", "Income Tax Expense", AccountType.EXPENSE, ("income_tax",)),
]


def default_chart() -> ChartOfAccounts:
    """Return a fresh real-estate chart of accounts."""
    coa = ChartOfAccounts()
    for code, name, atype, tags in _DEFAULT_ACCOUNTS:
        coa.add(Account(code=code, name=name, type=atype, tags=frozenset(tags)))
    return coa
