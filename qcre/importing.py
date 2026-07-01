"""Import transactions from a bank / credit-card CSV export.

Parses the common shapes of Canadian bank exports — a signed ``Amount`` column, or
separate ``Debit``/``Credit`` (a.k.a. withdrawal/deposit) columns — into a normalized list
of transactions where a **negative amount is money out** (an expense) and a **positive
amount is money in** (income). Each row gets a *suggested* account based on keywords in the
description, which the user confirms/overrides on the review screen before anything is
posted to the books.

This is the first step of document data-extraction: structured CSV first; scanned-PDF/OCR
parsing is a larger follow-on.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

# description keyword -> (account code, human category)
_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("hydro", "energir", "gaz", "gas", "water", "aqueduc", "utilit", "internet",
      "videotron", "bell", "telus"), "5020"),                # Utilities
    (("insurance", "assurance"), "5010"),                     # Insurance
    (("municipal", "ville de", "school tax", "taxe scolaire", "taxes fonci", "property tax"),
     "5000"),                                                 # Property taxes
    (("repair", "plumb", "plomberie", "electric", "reno", "maintenance", "rona",
      "home depot", "quincaill", "hardware"), "5030"),        # Repairs & maintenance
    (("management", "gestion"), "5040"),                      # Management
    (("snow", "deneigement", "landscap", "paysage", "lawn", "gazon"), "5060"),  # Snow/landscape
    (("advert", "kijiji", "publicit", "marketing"), "5070"),  # Advertising
    (("legal", "notaire", "avocat", "lawyer", "comptable", "accountant"), "5080"),  # Prof. fees
    (("bank fee", "frais", "service charge", "monthly fee"), "5090"),  # Bank charges
    (("condo", "copropri", "syndicat"), "5100"),              # Condo fees
    (("mortgage", "hypoth"), "5200"),                         # Mortgage interest (review!)
]

_DATE_FORMATS = ["%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y", "%d-%m-%Y",
                 "%b %d, %Y", "%d %b %Y", "%Y%m%d"]


@dataclass
class ParsedTxn:
    date: str            # ISO date (or the raw string if unparseable)
    description: str
    amount: Decimal      # signed: negative = money out (expense), positive = money in
    suggested_account: str
    suggested_kind: str  # "expense" or "income"

    @property
    def is_inflow(self) -> bool:
        return self.amount > 0


def _parse_date(value: str) -> str:
    value = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return value  # leave as-is; the review screen still shows it


def _parse_amount(value: str, european: bool = False) -> Decimal | None:
    """Parse a money string. ``european`` (semicolon-delimited files) treats comma as the
    decimal separator (``1.234,56``); otherwise comma is a thousands separator (``1,234.56``)."""
    if value is None:
        return None
    v = value.strip().replace("CAD", "").replace("$", "").replace(" ", "")
    if not v:
        return None
    neg = v.startswith("(") and v.endswith(")")
    v = re.sub(r"[()\s]", "", v)
    if european:
        v = v.replace(".", "").replace(",", ".")
    else:
        v = v.replace(",", "")
    if not v or v in ("-", "+"):
        return None
    try:
        amount = Decimal(v)
    except InvalidOperation:
        return None
    return -amount if neg else amount


def suggest(description: str, is_inflow: bool) -> tuple[str, str]:
    """Return (account_code, kind) suggested from the description."""
    if is_inflow:
        return "4000", "income"  # default: residential rent (user can switch to commercial)
    low = description.lower()
    for keywords, code in _KEYWORDS:
        if any(k in low for k in keywords):
            return code, "expense"
    return "5030", "expense"  # default expense: repairs & maintenance


def _find_col(fieldnames: list[str], *needles: str, exclude: set | None = None) -> str | None:
    exclude = exclude or set()
    for i, fn in enumerate(fieldnames):
        if i in exclude:
            continue
        low = fn.lower()
        if any(n in low for n in needles):
            return fn
    return None


def parse_csv(text: str) -> list[ParsedTxn]:
    text = text.lstrip("﻿")  # strip BOM
    # Pick the delimiter by counting candidates in the first non-empty line (comma is
    # ambiguous with decimals, so prefer an explicit ';' or tab when present).
    first_line = next((ln for ln in text.splitlines() if ln.strip()), "")
    counts = {d: first_line.count(d) for d in (";", "\t", ",")}
    delimiter = max(counts, key=lambda d: (counts[d], {";": 2, "\t": 1, ",": 0}[d]))
    if counts[delimiter] == 0:
        delimiter = ","
    european = delimiter == ";"
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if not rows:
        return []

    # Detect a header row by looking for known column keywords.
    header = rows[0]
    has_header = any(
        any(k in cell.lower() for k in ("date", "amount", "montant", "description", "debit",
                                        "credit", "withdrawal", "deposit", "memo"))
        for cell in header
    )
    if has_header:
        fields = header
        data = rows[1:]
        date_i = _index(fields, "date")
        # Exclude the date column so a "Transaction Date" header isn't mistaken for the memo.
        desc_i = _index(fields, "description", "memo", "narration", "details", "libell",
                        "payee", "transaction", exclude={date_i})
        amount_i = _index(fields, "amount", "montant")
        debit_i = _index(fields, "debit", "withdrawal", "retrait")
        credit_i = _index(fields, "credit", "deposit", "depot", "depôt")
    else:
        fields = []
        data = rows
        date_i, desc_i, amount_i, debit_i, credit_i = 0, 1, 2, None, None

    out: list[ParsedTxn] = []
    for r in data:
        def cell(i):
            return r[i] if i is not None and i < len(r) else ""
        raw_date = cell(date_i)
        desc = cell(desc_i).strip() or "(no description)"
        amount = None
        if amount_i is not None:
            amount = _parse_amount(cell(amount_i), european)
        if amount is None and (debit_i is not None or credit_i is not None):
            debit = _parse_amount(cell(debit_i), european) or Decimal(0)
            credit = _parse_amount(cell(credit_i), european) or Decimal(0)
            amount = credit - abs(debit)
        if amount is None or amount == 0:
            continue
        acct, kind = suggest(desc, amount > 0)
        out.append(ParsedTxn(_parse_date(raw_date), desc, amount, acct, kind))
    return out


def _index(fields: list[str], *needles: str, exclude: set | None = None) -> int | None:
    exclude = {i for i in (exclude or set()) if i is not None}
    col = _find_col(fields, *needles, exclude=exclude)
    return fields.index(col) if col is not None else None


# --- PDF statement extraction ----------------------------------------------
# A single money token like 1,234.56 / (1,234.56) / -89,99 / $89.99. It must NOT span
# spaces, otherwise it would swallow a following running-balance column into one number.
_MONEY = r"\(?-?\$?\d[\d.,]*[.,]\d{2}\)?"
_DATE = (
    r"(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}"
    r"|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}"
    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|"
    r"janv|f[ée]vr|mars|avr|mai|juin|juil|ao[uû]t|sept|d[ée]c)[a-zé.]*\s+\d{1,2}(?:,?\s*\d{4})?)"
)
_LINE_RE = re.compile(rf"^\s*({_DATE})\s+(.+?)\s+({_MONEY})(?:\s+{_MONEY})?\s*$", re.IGNORECASE)
_INFLOW_HINTS = ("deposit", "dépôt", "loyer", "rent received", "rental income",
                 "virement re", "paiement re", "transfer in", "interest earned")


def _auto_amount(token: str) -> Decimal | None:
    """Parse a money token, auto-detecting comma-vs-period decimal separator."""
    t = token.strip()
    european = bool(re.search(r",\d{2}\)?$", t)) and not re.search(r"\.\d{2}\)?$", t)
    return _parse_amount(t, european)


def _pdfplumber_text(data: bytes) -> str:
    try:
        import pdfplumber
    except ImportError:  # pragma: no cover
        return ""
    lines: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                lines.append(page.extract_text() or "")
    except Exception:  # pragma: no cover - malformed PDF
        return ""
    return "\n".join(lines)


def ocr_pdf_text(data: bytes, *, max_pages: int = 20, dpi: int = 200) -> str:
    """OCR a scanned/image PDF into text. Returns '' if the OCR stack is unavailable.

    Requires the ``pytesseract`` + ``pdf2image`` Python packages and the ``tesseract-ocr``
    and ``poppler-utils`` system binaries (installed in the Docker image)."""
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
    except ImportError:  # pragma: no cover
        return ""
    try:
        images = convert_from_bytes(data, dpi=dpi, first_page=1, last_page=max_pages)
    except Exception:  # pragma: no cover - poppler missing / bad PDF
        return ""
    out: list[str] = []
    for img in images:
        for lang in ("eng+fra", "eng"):
            try:
                out.append(pytesseract.image_to_string(img, lang=lang))
                break
            except Exception:
                continue
    return "\n".join(out)


def extract_pdf_text(data: bytes) -> str:
    """Extract text from a PDF, falling back to OCR for scanned/image PDFs.

    Text-based PDFs are read directly (fast). If that yields almost nothing — the mark of
    a scanned statement — OCR is attempted and used when it recovers more text."""
    text = _pdfplumber_text(data)
    if len(text.strip()) < 40:  # essentially no embedded text → likely scanned
        ocr = ocr_pdf_text(data)
        if len(ocr.strip()) > len(text.strip()):
            return ocr
    return text


def parse_pdf(data: bytes) -> list[ParsedTxn]:
    """Best-effort extraction of transactions from a text-based PDF statement.

    Statements vary enormously, so this errs toward capturing candidate lines (a date
    followed by a description and a trailing amount) for the user to confirm/edit on the
    review screen. Scanned/image PDFs (no embedded text) will extract little or nothing —
    those need OCR, a separate follow-on.
    """
    text = extract_pdf_text(data)
    out: list[ParsedTxn] = []
    for line in text.splitlines():
        m = _LINE_RE.match(line.strip())
        if not m:
            continue
        raw_date, desc, amt_token = m.group(1), m.group(2).strip(), m.group(3)
        amount = _auto_amount(amt_token)
        if amount is None or amount == 0:
            continue
        low = desc.lower()
        inflow = any(h in low for h in _INFLOW_HINTS)
        amount = abs(amount) if inflow else -abs(amount)
        acct, kind = suggest(desc, inflow)
        out.append(ParsedTxn(_parse_date(raw_date), desc, amount, acct, kind))
    return out


def parse_transactions(filename: str, data: bytes) -> tuple[list[ParsedTxn], str]:
    """Dispatch to the CSV or PDF parser by file extension. Returns (txns, source_kind)."""
    name = (filename or "").lower()
    if name.endswith(".pdf") or data[:5] == b"%PDF-":
        return parse_pdf(data), "pdf"
    text = data.decode("utf-8", errors="replace")
    return parse_csv(text), "csv"
