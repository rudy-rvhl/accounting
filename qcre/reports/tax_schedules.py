"""Map the engine's outputs onto federal T2 and Quebec CO-17 return schedules.

Produces the figures, organised by schedule and line reference, ready to transcribe onto
the corporate returns:

* **T2 Schedule 1** — reconciliation from accounting net income to *net income for tax
  purposes* (add back amortization and the income-tax provision; deduct CCA).
* **T2 Schedule 8** — capital cost allowance by class (UCC, additions, CCA, closing UCC).
* **T2 Schedule 7** — aggregate investment income vs active business income.
* **RDTOH continuity** — opening, refundable tax added, dividend refund, closing.
* **T2 (federal)** and **CO-17 (Quebec)** tax summaries with the federal/Quebec split.

These are computation aids with indicative line references — **not** a NETFILE/transmission
file, and not a substitute for certified tax software or a CPA's review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from qcre.analysis import TaxPosition, tax_position
from qcre.company import Company
from qcre.core.accounts import AccountType
from qcre.core.money import Money
from qcre.reports.statements import FinancialStatements
from qcre.tax.rates import RateBook, get_ratebook


@dataclass
class ScheduleLine:
    ref: str
    label: str
    amount: Money | None = None
    bold: bool = False


@dataclass
class TaxSchedule:
    form: str            # "T2 (Federal)" or "CO-17 (Québec)"
    name: str
    lines: list[ScheduleLine] = field(default_factory=list)

    def add(self, ref, label, amount=None, *, bold=False):
        self.lines.append(ScheduleLine(ref, label, amount, bold))


def _book_net_income_and_components(company: Company) -> tuple[Money, Money, Money]:
    fs = FinancialStatements(company.ledger, company.fiscal_year, entity_name=company.entity_name)
    net_income = fs.net_income()
    fy = company.fiscal_year

    def tag(atype, t):
        return sum((company.ledger.balance(a.code, start=fy.start, end=fy.end)
                    for a in company.ledger.chart.by_type(atype) if t in a.tags), Money.zero())

    amortization = tag(AccountType.EXPENSE, "amortization")
    income_tax_expense = tag(AccountType.EXPENSE, "income_tax")
    return net_income.round(2), amortization.round(2), income_tax_expense.round(2)


def build_tax_schedules(company: Company, ratebook: RateBook | None = None) -> list[TaxSchedule]:
    rb = ratebook or get_ratebook(company.year)
    c = rb.corporate
    pos: TaxPosition = tax_position(company, rb)
    corp = pos.corporate
    net_income, amortization, tax_expense = _book_net_income_and_components(company)

    schedules: list[TaxSchedule] = []

    # --- T2 Schedule 1 — net income for tax purposes -----------------------
    s1 = TaxSchedule("T2 (Federal)", "Schedule 1 — Net income (loss) for income tax purposes")
    s1.add("A", "Net income (loss) per financial statements", net_income)
    s1.add("L101", "Add: provision for income taxes", tax_expense)
    s1.add("L104", "Add: amortization of tangible assets (book)", amortization)
    s1.add("L403", "Deduct: capital cost allowance (Schedule 8)", (-pos.cca_claimed).round(2))
    net_for_tax = (net_income + tax_expense + amortization - pos.cca_claimed).round(2)
    s1.add("L300", "Net income for income tax purposes", net_for_tax, bold=True)
    schedules.append(s1)

    # --- T2 Schedule 8 — capital cost allowance ----------------------------
    s8 = TaxSchedule("T2 (Federal)", "Schedule 8 — Capital cost allowance (CCA)")
    for r in pos.cca_results:
        s8.add(f"Class {r.cca_class}", f"{r.building_id}: UCC + additions {r.additions.format()}, "
               f"rate {r.rate*100:.0f}%", None)
        s8.add("", "  CCA claimed", r.cca_claimed)
        s8.add("", "  Closing UCC", r.closing_ucc)
    s8.add("Total", "Total CCA (to Schedule 1, line 403)", pos.cca_claimed, bold=True)
    schedules.append(s8)

    # --- T2 Schedule 7 — investment vs active business income --------------
    s7 = TaxSchedule("T2 (Federal)", "Schedule 7 — Aggregate investment income & active business income")
    s7.add("", "Net income for tax purposes", net_for_tax)
    s7.add("L092", "Aggregate investment income (incl. rental as SIB)", corp.aggregate_investment_income)
    s7.add("", "Active business income (SBD-eligible)", corp.sbd_income)
    s7.add("", "General active business income", corp.general_active_income)
    s7.add("", f"Rental characterized as specified investment business: {corp.rental_is_sib}", None)
    schedules.append(s7)

    # --- RDTOH continuity --------------------------------------------------
    rd = TaxSchedule("T2 (Federal)", "Refundable dividend tax on hand (RDTOH) continuity")
    rd.add("", "Opening balance", Money.zero())
    rd.add("", f"Refundable tax on investment income ({c.rdtoh_refundable_rate*100:.2f}% of AII) + Part IV",
           corp.refundable_tax_added_to_rdtoh)
    rd.add("", "Dividend refund on taxable dividends paid", Money.zero())
    rd.add("", "Closing balance", corp.refundable_tax_added_to_rdtoh, bold=True)
    schedules.append(rd)

    # --- federal / Quebec tax split ----------------------------------------
    quebec_rate_on_sbd = (corp.effective_sbd_rate - c.federal_sbd)
    fed_tax = (corp.sbd_income * c.federal_sbd + corp.general_active_income * c.federal_general
               + corp.aggregate_investment_income * c.federal_investment + corp.part_iv_tax).round(2)
    qc_tax = (corp.sbd_income * quebec_rate_on_sbd + corp.general_active_income * c.quebec_general
              + corp.aggregate_investment_income * c.quebec_investment).round(2)

    t2 = TaxSchedule("T2 (Federal)", "T2 — Federal tax summary")
    t2.add("L300", "Net income for tax purposes", net_for_tax)
    t2.add("L360", "Taxable income", net_for_tax)
    t2.add("", f"Federal tax on investment income ({c.federal_investment*100:.2f}%)",
           (corp.aggregate_investment_income * c.federal_investment).round(2))
    if corp.sbd_income.is_positive():
        t2.add("L430", f"Small business deduction applied (federal {c.federal_sbd*100:.0f}%)",
               (corp.sbd_income * c.federal_sbd).round(2))
    t2.add("L700", "Part IV tax on portfolio dividends", corp.part_iv_tax)
    t2.add("", "Federal tax payable (before dividend refund)", fed_tax, bold=True)
    schedules.append(t2)

    co17 = TaxSchedule("CO-17 (Québec)", "CO-17 — Québec tax summary")
    co17.add("L300", "Net income for tax purposes (same base as federal)", net_for_tax)
    co17.add("", f"Québec tax on investment income ({c.quebec_investment*100:.2f}%)",
             (corp.aggregate_investment_income * c.quebec_investment).round(2))
    if corp.sbd_income.is_positive():
        co17.add("", f"Québec small business rate {quebec_rate_on_sbd*100:.2f}% "
                 f"(5,500-hour factor {corp.quebec_sbd_factor:.2f})",
                 (corp.sbd_income * quebec_rate_on_sbd).round(2))
    co17.add("", "Québec tax payable", qc_tax, bold=True)
    schedules.append(co17)

    return schedules
