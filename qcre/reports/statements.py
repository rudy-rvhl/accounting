"""Financial statements built from the general ledger.

Produces the four core statements for a real-estate company:

* **Income Statement** with a **Net Operating Income (NOI)** subtotal — the figure real-
  estate investors and lenders care about — before interest and amortization.
* **Balance Sheet** (Statement of Financial Position). Under IFRS, investment property is
  shown at fair value (IAS 40); under ASPE, at cost less accumulated amortization.
* **Statement of Changes in Equity / Retained Earnings**.
* **Cash Flow Statement** (indirect method) that ties exactly to the change in cash via
  the accounting identity ΔCash = ΔLiabilities + ΔEquity − ΔOther assets.

All figures come from posted journal entries, so the statements are always internally
consistent with the books.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from qcre.core.accounts import AccountType
from qcre.core.ledger import Ledger
from qcre.core.money import Money
from qcre.core.period import FiscalYear
from qcre.reports.framework import Framework


@dataclass
class LineItem:
    label: str
    amount: Money | None = None
    indent: int = 0
    bold: bool = False
    underline: bool = False
    code: str | None = None


@dataclass
class Statement:
    title: str
    subtitle: str
    lines: list[LineItem] = field(default_factory=list)

    def add(self, label, amount=None, *, indent=0, bold=False, underline=False, code=None):
        self.lines.append(LineItem(label, amount, indent, bold, underline, code))


class FinancialStatements:
    def __init__(
        self,
        ledger: Ledger,
        fiscal_year: FiscalYear,
        *,
        entity_name: str = "Real-Estate Company Inc.",
        framework: Framework = Framework.ASPE,
        fair_value_adjustment: Money | None = None,
    ) -> None:
        self.ledger = ledger
        self.fy = fiscal_year
        self.entity_name = entity_name
        self.framework = framework
        self.fair_value_adjustment = fair_value_adjustment or Money.zero()

    # -- helpers -------------------------------------------------------------
    def _bal(self, code: str, *, opening: bool = False) -> Money:
        end = self.fy.start if opening else self.fy.end
        end_arg = None if opening else self.fy.end
        if opening:
            # balance strictly before the year start
            return self.ledger.balance(code, end=date(self.fy.start.year - 1, 12, 31))
        return self.ledger.balance(code, end=end_arg)

    def _tag(self, tag: str) -> Money:
        return self.ledger.balances_by_tag(tag, start=self.fy.start, end=self.fy.end)

    def _sum_type_period(self, *types: AccountType) -> Money:
        total = Money.zero()
        for a in self.ledger.chart.by_type(*types):
            total += self.ledger.balance(a.code, start=self.fy.start, end=self.fy.end)
        return total.round(2)

    # -- income statement ----------------------------------------------------
    def income_statement(self) -> Statement:
        st = Statement(
            "Income Statement",
            f"{self.entity_name} — for the year {self.fy.label} ({self.framework.value})",
        )
        revenue_accounts = [
            a for a in self.ledger.chart.by_type(AccountType.REVENUE)
            if "rent" in a.tags or "noi" in a.tags
        ]
        st.add("Revenue", bold=True)
        total_rev = Money.zero()
        for a in revenue_accounts:
            bal = self.ledger.balance(a.code, start=self.fy.start, end=self.fy.end)
            if not bal.is_zero():
                st.add(a.name, bal, indent=1, code=a.code)
                total_rev += bal
        st.add("Total revenue", total_rev.round(2), indent=1, underline=True)

        st.add("Operating expenses", bold=True)
        opex_total = Money.zero()
        for a in self.ledger.chart.by_type(AccountType.EXPENSE):
            if "noi" not in a.tags:
                continue
            bal = self.ledger.balance(a.code, start=self.fy.start, end=self.fy.end)
            if not bal.is_zero():
                st.add(a.name, bal, indent=1, code=a.code)
                opex_total += bal
        st.add("Total operating expenses", opex_total.round(2), indent=1, underline=True)

        noi = (total_rev - opex_total).round(2)
        st.add("Net operating income (NOI)", noi, bold=True, underline=True)

        interest = self._tag("interest")
        amort = self._tag("amortization")
        st.add("Mortgage interest", interest, indent=1, code="5200")
        st.add("Amortization", amort, indent=1, code="5300")

        gains = self._tag("gain_disposal") - self._tag("loss_disposal")
        if self.framework.carries_investment_property_at_fair_value and not self.fair_value_adjustment.is_zero():
            st.add("Fair value gain on investment property (IAS 40)",
                   self.fair_value_adjustment, indent=1)
            gains = gains + self.fair_value_adjustment
        if not gains.is_zero():
            st.add("Gain (loss) on disposal / fair value", gains, indent=1)

        pretax = (noi - interest - amort + gains).round(2)
        st.add("Income before income taxes", pretax, bold=True, underline=True)
        tax = self._tag("income_tax")
        st.add("Income tax expense", tax, indent=1, code="5900")
        st.add("Net income", (pretax - tax).round(2), bold=True, underline=True)
        return st

    def net_income(self) -> Money:
        rev = self._sum_type_period(AccountType.REVENUE)
        exp = self._sum_type_period(AccountType.EXPENSE)
        fv = self.fair_value_adjustment if self.framework.carries_investment_property_at_fair_value else Money.zero()
        return (rev - exp + fv).round(2)

    # -- balance sheet -------------------------------------------------------
    def balance_sheet(self) -> Statement:
        st = Statement(
            "Balance Sheet",
            f"{self.entity_name} — as at {self.fy.end.isoformat()} ({self.framework.value})",
        )
        as_of = self.fy.end

        def bal(code: str) -> Money:
            return self.ledger.balance(code, end=as_of)

        st.add("ASSETS", bold=True)
        st.add("Current assets", bold=True, indent=1)
        current_asset_codes = ["1000", "1010", "1020", "1100", "1200", "1210", "1300"]
        current_assets = Money.zero()
        for code in current_asset_codes:
            b = bal(code)
            if not b.is_zero():
                st.add(self.ledger.chart.get(code).name, b, indent=2, code=code)
                current_assets += b
        st.add("Total current assets", current_assets.round(2), indent=2, underline=True)

        st.add("Property & equipment", bold=True, indent=1)
        land = bal("1400")
        building_gross = bal("1500") + bal("1520")
        building_accum = bal("1510") + bal("1530")
        equip_gross = bal("1600")
        equip_accum = bal("1610")
        fv_adj = self.fair_value_adjustment if self.framework.carries_investment_property_at_fair_value else Money.zero()

        st.add("Land", land, indent=2, code="1400")
        if self.framework.carries_investment_property_at_fair_value:
            building_net = (building_gross + fv_adj).round(2)
            st.add("Buildings (fair value, IAS 40)", building_net, indent=2)
        else:
            st.add("Buildings (at cost)", building_gross, indent=2, code="1500")
            st.add("Less: accumulated amortization", -building_accum, indent=2, code="1510")
            building_net = (building_gross - building_accum).round(2)
            st.add("Buildings (net)", building_net, indent=2, underline=True)
        equip_net = (equip_gross - equip_accum).round(2)
        if not equip_gross.is_zero():
            st.add("Equipment (net)", equip_net, indent=2, code="1600")

        total_ppe = (land + building_net + equip_net).round(2)
        st.add("Total property & equipment", total_ppe, indent=2, underline=True)
        total_assets = (current_assets + total_ppe).round(2)
        st.add("TOTAL ASSETS", total_assets, bold=True, underline=True)

        st.add("LIABILITIES & EQUITY", bold=True)
        st.add("Liabilities", bold=True, indent=1)
        liab_total = Money.zero()
        for a in self.ledger.chart.by_type(AccountType.LIABILITY):
            b = bal(a.code)
            if not b.is_zero():
                st.add(a.name, b, indent=2, code=a.code)
                liab_total += b
        st.add("Total liabilities", liab_total.round(2), indent=2, underline=True)

        st.add("Shareholders' equity", bold=True, indent=1)
        shares = bal("3000")
        retained_open = self.ledger.balance("3100", end=date(self.fy.start.year - 1, 12, 31))
        ni = self.net_income()
        dividends = self.ledger.balance("3200", start=self.fy.start, end=self.fy.end)
        revaluation = bal("3300") if self.framework.carries_investment_property_at_fair_value else Money.zero()
        retained_close = (retained_open + ni - dividends).round(2)
        st.add("Common shares", shares, indent=2, code="3000")
        st.add("Retained earnings", retained_close, indent=2, code="3100")
        if not revaluation.is_zero():
            st.add("Revaluation surplus", revaluation, indent=2, code="3300")
        equity_total = (shares + retained_close + revaluation).round(2)
        st.add("Total shareholders' equity", equity_total, indent=2, underline=True)
        st.add("TOTAL LIABILITIES & EQUITY", (liab_total + equity_total).round(2),
               bold=True, underline=True)
        return st

    # -- statement of changes in equity -------------------------------------
    def equity_statement(self) -> Statement:
        st = Statement(
            "Statement of Changes in Equity",
            f"{self.entity_name} — for the year {self.fy.label}",
        )
        shares = self.ledger.balance("3000", end=self.fy.end)
        retained_open = self.ledger.balance("3100", end=date(self.fy.start.year - 1, 12, 31))
        ni = self.net_income()
        dividends = self.ledger.balance("3200", start=self.fy.start, end=self.fy.end)
        st.add("Common shares", shares, code="3000")
        st.add("Retained earnings, beginning of year", retained_open)
        st.add("Add: net income", ni, indent=1)
        st.add("Less: dividends declared", -dividends, indent=1)
        st.add("Retained earnings, end of year", (retained_open + ni - dividends).round(2),
               bold=True, underline=True)
        return st

    # -- cash flow (indirect) -----------------------------------------------
    def cash_flow(self) -> Statement:
        st = Statement(
            "Cash Flow Statement (indirect method)",
            f"{self.entity_name} — for the year {self.fy.label}",
        )

        def delta(code: str) -> Money:
            return self.ledger.balance(code, start=self.fy.start, end=self.fy.end)

        ni = self.net_income()
        amort = self._tag("amortization")
        st.add("Operating activities", bold=True)
        st.add("Net income", ni, indent=1)
        st.add("Add: amortization (non-cash)", amort, indent=1)
        wc = Money.zero()
        for code, label, sign in [
            ("1100", "Δ accounts receivable", -1),
            ("1200", "Δ GST receivable", -1),
            ("1210", "Δ QST receivable", -1),
            ("1300", "Δ prepaid expenses", -1),
            ("2000", "Δ accounts payable", 1),
            ("2100", "Δ GST payable", 1),
            ("2110", "Δ QST payable", 1),
            ("2200", "Δ security deposits", 1),
            ("2600", "Δ income taxes payable", 1),
        ]:
            d = (delta(code) * sign).round(2)
            if not d.is_zero():
                st.add(label, d, indent=1)
                wc += d
        operating = (ni + amort + wc).round(2)
        st.add("Cash from operating activities", operating, bold=True, underline=True)

        st.add("Investing activities", bold=True)
        invest = Money.zero()
        for code, label in [("1400", "Purchase of land"), ("1500", "Purchase of buildings"),
                            ("1520", "Building improvements"), ("1600", "Purchase of equipment")]:
            d = (-delta(code)).round(2)
            if not d.is_zero():
                st.add(label, d, indent=1)
                invest += d
        st.add("Cash used in investing activities", invest, bold=True, underline=True)

        st.add("Financing activities", bold=True)
        financing = Money.zero()
        for code, label, sign in [
            ("2400", "Δ mortgage (current)", 1),
            ("2410", "Δ mortgage (long-term)", 1),
            ("2500", "Δ shareholder loan", 1),
            ("3000", "Issuance of shares", 1),
            ("3200", "Dividends declared", -1),
        ]:
            d = (delta(code) * sign).round(2)
            if not d.is_zero():
                st.add(label, d, indent=1)
                financing += d
        st.add("Cash from financing activities", financing, bold=True, underline=True)

        net_change = (operating + invest + financing).round(2)
        st.add("Net change in cash", net_change, bold=True, underline=True)
        actual = (delta("1000") + delta("1010") + delta("1020")).round(2)
        st.add("Net change in cash per ledger (check)", actual, indent=1)
        return st

    def all_statements(self) -> list[Statement]:
        return [
            self.income_statement(),
            self.balance_sheet(),
            self.equity_statement(),
            self.cash_flow(),
        ]
