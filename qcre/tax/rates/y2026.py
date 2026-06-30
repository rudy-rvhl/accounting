"""2026 taxation-year rate book for Quebec real estate.

Every value below is dated to the 2026 taxation year and carries a citation. Tax law and
indexed thresholds change every year — treat this as a starting point to be verified
against the primary sources cited, and reviewed with a CPA/tax advisor.

To add another year, copy this file to ``yXXXX.py``, update the values and citations, and
register it in ``qcre/tax/rates/__init__.py``.
"""

from __future__ import annotations

from decimal import Decimal

from qcre.core.money import Money
from qcre.tax.rates.ratebook import (
    Bracket,
    BracketTable,
    CCAClass,
    CCARates,
    CapitalGainsRates,
    Citation,
    CorporateRates,
    DividendParams,
    PersonalRates,
    RateBook,
    SalesTaxRates,
    TransferDutyRates,
    TrustParams,
)

D = Decimal


def _build() -> RateBook:
    sales_tax = SalesTaxRates(
        gst=D("0.05"),
        qst=D("0.09975"),
        registration_threshold=Money("30000"),
    )

    corporate = CorporateRates(
        combined_sbd=D("0.112"),
        combined_general=D("0.265"),
        combined_investment=D("0.5017"),
        federal_sbd=D("0.09"),
        federal_general=D("0.15"),
        federal_investment=D("0.3867"),   # 38% base − 10% abatement + 10.67% ART (no GRR)
        quebec_sbd=D("0.022"),             # reduced from 3.2% for years beginning after 2026-04-29
        quebec_general=D("0.115"),
        quebec_investment=D("0.115"),
        sbd_business_limit=Money("500000"),
        taxable_capital_lower=Money("10000000"),
        taxable_capital_upper=Money("50000000"),
        quebec_sbd_hours_full=D("5500"),
        quebec_sbd_hours_floor=D("5000"),
        sib_max_full_time_employees=5,
        rdtoh_refundable_rate=D("0.3067"),
        part_iv_rate=D("0.3833"),
        dividend_refund_rate=D("0.3833"),
        cda_inclusion=D("0.5"),
    )

    capital_gains = CapitalGainsRates(
        inclusion_rate=D("0.5"),               # 66.67% increase was cancelled in 2025
        lifetime_exemption_qsbc=Money("1250000"),
    )

    dividends = DividendParams(
        eligible_gross_up=D("0.38"),
        non_eligible_gross_up=D("0.15"),
        federal_dtc_eligible=D("0.150198"),
        federal_dtc_non_eligible=D("0.090301"),
        quebec_dtc_eligible=D("0.117"),
        quebec_dtc_non_eligible=D("0.0342"),
    )

    personal = PersonalRates(
        federal=BracketTable((
            Bracket(D("58523"), D("0.14")),
            Bracket(D("117045"), D("0.205")),
            Bracket(D("181440"), D("0.26")),
            Bracket(D("258482"), D("0.29")),
            Bracket(None, D("0.33")),
        )),
        quebec=BracketTable((
            Bracket(D("51780"), D("0.14")),
            Bracket(D("103545"), D("0.19")),
            Bracket(D("126000"), D("0.24")),
            Bracket(None, D("0.2575")),
        )),
        quebec_abatement=D("0.165"),
        federal_bpa=Money("16564"),            # 2026 indexed estimate — verify
        quebec_bpa=Money("18571"),             # verify 2026 indexation
        federal_lowest_rate=D("0.14"),
        quebec_lowest_rate=D("0.14"),
        top_combined_rate=D("0.5331"),         # 33%*(1-0.165) + 25.75%
    )

    transfer_duty = TransferDutyRates(
        standard=BracketTable((
            Bracket(D("62900"), D("0.005")),
            Bracket(D("315000"), D("0.01")),
            Bracket(None, D("0.015")),
        )),
        montreal=BracketTable((
            Bracket(D("62900"), D("0.005")),
            Bracket(D("315000"), D("0.01")),
            Bracket(D("552300"), D("0.015")),
            Bracket(D("1104700"), D("0.02")),
            Bracket(D("2136500"), D("0.025")),
            Bracket(D("3113000"), D("0.035")),
            Bracket(None, D("0.04")),
        )),
        note="Basis = greater of sale price, stated consideration, or municipal value × "
        "comparative factor. Montreal sets its own luxury brackets by by-law; thresholds "
        "are indexed annually — verify for the year/municipality of the transaction.",
    )

    trust = TrustParams(
        deemed_disposition_years=21,
        taxed_at_top_rate=True,
        tosi_top_rate=D("0.5331"),
    )

    cca = CCARates(
        classes={
            "1": CCAClass("1", D("0.04"), "Building — residential rental (default)"),
            "1-NR": CCAClass("1-NR", D("0.06"), "Building — eligible non-residential (+2% allowance)"),
            "1-PBR": CCAClass("1-PBR", D("0.10"), "New purpose-built residential rental (eligible)"),
            "8": CCAClass("8", D("0.20"), "Furniture, appliances, equipment"),
            "10": CCAClass("10", D("0.30"), "Vehicles & general equipment"),
            "10.1": CCAClass("10.1", D("0.30"), "Passenger vehicle (cost-capped)"),
            "13": CCAClass("13", D("0"), "Leasehold improvements", straight_line=True),
            "14.1": CCAClass("14.1", D("0.05"), "Goodwill & intangibles"),
            "50": CCAClass("50", D("0.55"), "Computer hardware & systems software"),
        },
        half_year_rule=True,
        aii_first_year_uplift=D("0"),  # AII phasing out (gone after 2027); engine defaults to half-year
        rental_loss_restriction=True,
    )

    citations = (
        Citation("gst_qst", "Revenu Québec — Basic Rules for the GST/HST and QST",
                 "https://www.revenuquebec.ca/en/businesses/consumption-taxes/gsthst-and-qst/",
                 "2026", "GST 5% + QST 9.975%; $30,000 small-supplier threshold."),
        Citation("residential_exempt", "Revenu Québec IN-261 — GST/QST and Residential Property",
                 "https://www.revenuquebec.ca/", "2026",
                 "Long-term residential rent is exempt; commercial rent is taxable; ITC/ITR "
                 "prorated for mixed-use (square-footage method preferred)."),
        Citation("corporate_rates", "CRA / Revenu Québec; BDO/PwC 2026 corporate tax tables",
                 "https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/corporations/corporation-tax-rates.html",
                 "2026", "Combined SBD 11.2%, general 26.5%, CCPC investment income ≈ 50.17%."),
        Citation("quebec_sbd_hours", "Revenu Québec — Small Business Deduction (paid-hours test)",
                 "https://www.revenuquebec.ca/", "2026",
                 "Quebec SBD requires ≥5,500 paid hours (full), prorated 5,000–5,500, none below "
                 "5,000 (unless primary/manufacturing). Quebec SBD rate reduced to 2.2%."),
        Citation("sib", "Income Tax Act s.125(7) — specified investment business",
                 "https://laws-lois.justice.gc.ca/eng/acts/i-3.3/", "2026",
                 "Rental income is investment income (not ABI, no SBD) unless the corp employs "
                 ">5 full-time employees in the business."),
        Citation("capital_gains", "Dept. of Finance — capital gains inclusion rate (increase cancelled)",
                 "https://www.canada.ca/en/department-finance/", "2026",
                 "Inclusion rate remains 50%; proposed 66.67% increase cancelled in 2025."),
        Citation("rdtoh", "Income Tax Act s.129 — refundable dividend tax on hand",
                 "https://laws-lois.justice.gc.ca/eng/acts/i-3.3/", "2026",
                 "30.67% of aggregate investment income refundable; Part IV 38.33%; dividend "
                 "refund 38.33% of taxable dividends paid."),
        Citation("transfer_duty", "Quebec — Act respecting duties on transfers of immovables (D-15.1); Ville de Montréal",
                 "https://www.quebec.ca/gouvernement/gestion-municipale/finances-fiscalite-municipales/fiscalite/droits-mutations-immobilieres",
                 "2026", "Standard 0.5%/1%/1.5% at $62,900/$315,000; Montreal luxury brackets to 4%."),
        Citation("cca", "CRA — Capital cost allowance classes & rates; AII phase-out",
                 "https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/sole-proprietorships-partnerships/report-business-income-expenses/claiming-capital-cost-allowance/classes.html",
                 "2026", "Class 1 building 4% (6% non-residential, 10% new purpose-built rental); "
                 "half-year rule; AII phasing out, gone after 2027; CCA can't create a rental loss."),
        Citation("trust_21yr", "Income Tax Act s.104(4) — 21-year deemed disposition",
                 "https://laws-lois.justice.gc.ca/eng/acts/i-3.3/", "2026",
                 "Most inter-vivos trusts have a deemed disposition of capital property at FMV "
                 "every 21 years."),
        Citation("tosi", "Income Tax Act s.120.4 — tax on split income",
                 "https://www.canada.ca/en/revenue-agency/programs/about-canada-revenue-agency-cra/federal-government-budgets/income-sprinkling.html",
                 "2026", "Split income taxed at top marginal rate; 'excluded shares' exception "
                 "requires ≥10% direct ownership (fails for trust-held shares)."),
        Citation("personal_rates", "CRA & Revenu Québec 2026 personal tax brackets; 16.5% Quebec abatement",
                 "https://www.revenuquebec.ca/en/citizens/income-tax-return/completing-your-income-tax-return/income-tax-rates/",
                 "2026", "Federal 14/20.5/26/29/33%; Quebec 14/19/24/25.75%; top combined ≈ 53.31%."),
        Citation("dividends", "CRA & Revenu Québec — dividend gross-up and tax credits",
                 "https://www.taxtips.ca/qctax/dividend-tax-credit.htm", "2026",
                 "Gross-up 38% eligible / 15% non-eligible; federal DTC 15.0198% / 9.0301%; "
                 "Quebec DTC 11.70% / 3.42%."),
    )

    return RateBook(
        year=2026,
        sales_tax=sales_tax,
        corporate=corporate,
        capital_gains=capital_gains,
        dividends=dividends,
        personal=personal,
        transfer_duty=transfer_duty,
        trust=trust,
        cca=cca,
        citations=citations,
    )


RATEBOOK_2026 = _build()
