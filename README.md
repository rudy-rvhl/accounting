# QCRE — Quebec Real-Estate Accounting, Tax & CFO Engine

A precise, auditable accounting system purpose-built for a **Quebec real-estate company**
— specifically a Canadian-controlled private corporation (**CCPC**) whose shares are held
by a **family trust**, owning **residential (GST/QST-exempt)** and **commercial/mixed-use
(GST/QST-taxable)** rental property.

It keeps double-entry books, encodes Quebec/Canada real-estate tax law, prepares ASPE/IFRS
financial statements, and provides CFO decision-support and tax optimization.

> ## ⚠️ Disclaimer
> This software provides **decision-support only**. It is **NOT** professional tax, legal
> or accounting advice. Tax rules and indexed thresholds change every year. **Verify every
> figure against current CRA and Revenu Québec publications and review with a licensed CPA
> or tax advisor before relying on these results.** Every rate is dated and cited in the
> rate book (`qcre/tax/rates/`) precisely so it can be checked — see the *Rate Book &
> Sources* page in the app or run `qcre citations`.

---

## What it does

| Area | Capability |
|------|-----------|
| **Bookkeeping** | Decimal-precise double-entry ledger, real-estate chart of accounts, trial balance, per-property dimensions |
| **GST/QST** | Taxable vs exempt supplies, **mixed-use ITC/ITR apportionment by square footage**, net remittance, $30k registration test |
| **Income tax** | CCPC tax: small-business vs general vs **investment income**, the **specified-investment-business** test, Quebec **5,500-hour SBD** gate, RDTOH & dividend refund |
| **Depreciation** | Capital cost allowance (Class 1 4%/6%/10%, Class 8/10/13/50), half-year rule, **recapture & terminal loss**, **rental-loss restriction** |
| **Capital & trust** | Capital gains (50% inclusion), Capital Dividend Account, **21-year deemed disposition**, **TOSI** screening on trust distributions |
| **Transfer duty** | Droits de mutation (welcome tax) — standard + **Montréal luxury brackets**, greater-of basis, exemptions |
| **Statements** | Income Statement (with **NOI**), Balance Sheet, Cash Flow, Equity — **ASPE** default, **IFRS (IAS 40 fair value)** toggle; HTML + PDF |
| **CFO** | Cap rate, cash-on-cash, **DSCR**, LTV, GRM, break-even occupancy; acquisition **IRR/NPV** underwriting; after-tax **hold-vs-sell**; ranked **advisory** engine |
| **Forecasting** | Multi-year projection of NOI, CCA (UCC rolled forward), corporate tax, RDTOH, DSCR and after-tax cash flow |
| **Estate planning** | **Estate freeze** (s.85/86) modelling and **21-year deemed-disposition** plan (pay-the-tax vs s.107(2) roll-out) |
| **Returns** | **T2 / CO-17 schedule mapping** — Schedule 1, Schedule 8 (CCA), Schedule 7 (AII), RDTOH continuity, federal/Québec tax split |
| **Interfaces** | Python library, **CLI** (`qcre …`), and a **FastAPI + HTMX web app** |

---

## Install & run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[pdf,dev]"        # engine + PDF export + test tools

pytest                              # run the 65-test suite

# CLI (falls back to a built-in demo company when no --db is given)
qcre seed --db qcre.db              # build & store the demo company
qcre statements --year 2026 --out out/statements.html --pdf out/statements.pdf
qcre tax                            # corporate tax position + SIB/SBD determination
qcre kpis                           # per-property & portfolio KPIs
qcre forecast --years 5             # multi-year NOI/tax/CCA/RDTOH/cash-flow projection
qcre estate-freeze                  # estate freeze + 21-year deemed-disposition plan
qcre schedules                      # T2 / CO-17 return schedules (figures to transcribe)
qcre advisory                       # ranked CFO & tax-optimization recommendations
qcre transfer-duty 1800000 --montreal
qcre citations                      # show the dated, sourced rate book

# Web UI
uvicorn qcre.web.app:app --reload   # then open http://127.0.0.1:8000
#   set QCRE_DB=/path/to.db to use a saved company instead of the demo
```

---

## Key Quebec/Canada rules encoded (2026 rate book)

All values are dated to the **2026 taxation year** and cited in `qcre/tax/rates/y2026.py`.

- **GST 5% + QST 9.975%**; small-supplier registration threshold **$30,000**. Long-term
  **residential rent is exempt** (no tax, no input credit); **commercial rent is taxable**
  (charge tax, claim ITC/ITR). Mixed-use input tax is **prorated by square footage**.
- **Corporate (combined federal + Quebec):** general **26.5%**, small-business **11.2%**,
  CCPC **investment income ≈ 50.17%**. Rental income is a **specified investment business**
  (taxed as investment income, no SBD) unless the corporation has **>5 full-time
  employees**. The **Quebec** SBD also requires the **5,500 paid-hours** test.
- **Capital gains inclusion = 50%** (the proposed 66.67% increase was cancelled in 2025).
  Non-taxable half of a corporate capital gain → **Capital Dividend Account** (tax-free to
  shareholders by election).
- **CCA Class 1 building 4%** (6% eligible non-residential, **10% new purpose-built
  residential rental**); half-year rule; AII phasing out (gone after 2027). **CCA cannot
  create or increase a rental loss.**
- **Transfer duties:** standard 0.5% / 1% / 1.5% at $62,900 / $315,000; **Montréal** adds
  luxury brackets up to 4%. Basis = greater of price, consideration, or assessment × factor.
- **Family trust:** **21-year deemed disposition** at FMV (ITA s.104(4)); **TOSI** taxes
  trust distributions to family at the top marginal rate unless an exclusion applies — and
  the **"excluded shares" exclusion fails for trust-held shares** (≥10% *direct* ownership
  required). Top combined Quebec marginal rate ≈ **53.31%**.

Primary sources: canada.ca (CRA), revenuquebec.ca, quebec.ca / Ville de Montréal, the
Income Tax Act, and 2026 BDO/PwC/TaxTips tax tables.

---

## Architecture

```
qcre/
  core/        Money (Decimal), chart of accounts, double-entry journal/ledger, periods
  domain/      Property, Lease, Mortgage (Canadian semi-annual compounding), events→entries
  tax/
    rates/     dated, cited rate book (y2026.py) + registry
    sales_tax  cca  capital  corporate  transfer_duty  trust  personal  optimization
    estate_freeze
  reports/     ASPE/IFRS statements (Income/Balance Sheet/Cash Flow/Equity) + HTML/PDF;
               T2/CO-17 schedule mapping (tax_schedules.py)
  cfo/         KPIs, acquisition underwriting (IRR/NPV), hold-vs-sell, advisory engine,
               multi-year forecast (forecast.py)
  db/          SQLAlchemy/SQLite store (round-trips the company)
  web/         FastAPI + Jinja2 + HTMX UI (self-contained CSS)
  analysis.py  ties ledger → CCA → corporate tax → KPIs → advisory
  sample.py    realistic demo company (trust-owned CCPC, 2 Montréal buildings)
  cli.py       Typer command-line interface
tests/         65 tests (double-entry invariants + hand-verified golden tax cases)
```

### Maintaining the rate book each year

Tax rates and indexed thresholds change annually. To add a new year:

1. Copy `qcre/tax/rates/y2026.py` → `yXXXX.py`, update every value **and its citation**.
2. Register it in `qcre/tax/rates/__init__.py`.
3. Re-run `pytest` and re-verify the golden cases against the current primary sources.

The engine never silently extrapolates: an unknown future year carries forward the latest
encoded year (and that fact is visible), and every figure is traceable to a source.

---

## Worked examples verified by tests

- Transfer duty on a **$500,000** property (standard) = **$5,610.50**; **$2,000,000** in
  Montréal = **$39,825.50**.
- **$100,000** of rental income with ≤5 employees → investment income taxed at **50.17%**
  (**$50,170**), with **$30,670** added to RDTOH.
- Class 1 building, $400,000 first-year addition (half-year rule) → **$8,000** CCA.
- Top combined Quebec personal marginal rate = **53.305%**.
