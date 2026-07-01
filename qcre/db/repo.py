"""Multi-company data repository.

Unlike :func:`qcre.db.store.save_company` (which stores a single company by wiping the
database), the ``Repo`` holds **many** companies in one database and supports incremental
edits from the web app: create companies, add buildings/units/mortgages, post journal
entries, and upload/categorize documents. Uploaded files are written under an uploads
directory; only their metadata lives in the database.
"""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from qcre.company import Company
from qcre.core.journal import JournalEntry
from qcre.db.models import (
    Base,
    CompanyRow,
    DocumentRow,
    JournalEntryRow,
    JournalLineRow,
    MortgageRow,
    PropertyRow,
    UnitRow,
)
from qcre.db.store import company_from_row
from qcre.documents import label_for

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str) -> str:
    return _SAFE.sub("_", name).strip("_") or "file"


@dataclass
class CompanySummary:
    id: int
    name: str
    year: int
    property_count: int
    document_count: int


@dataclass
class DocumentInfo:
    id: int
    company_id: int
    property_id: str | None
    doc_type: str
    doc_type_label: str
    original_filename: str
    size_bytes: int
    period: str
    notes: str
    uploaded_at: str


class Repo:
    def __init__(self, db_path: str = "qcre_app.db", uploads_dir: str = "qcre_uploads") -> None:
        self.db_path = db_path
        self.uploads_dir = uploads_dir
        # Ensure the database and uploads directories exist (e.g. a mounted volume path).
        db_dir = os.path.dirname(os.path.abspath(db_path))
        os.makedirs(db_dir, exist_ok=True)
        os.makedirs(uploads_dir, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(self.engine)

    # -- companies ----------------------------------------------------------
    def list_companies(self) -> list[CompanySummary]:
        with Session(self.engine) as s:
            out = []
            for c in s.query(CompanyRow).order_by(CompanyRow.entity_name).all():
                out.append(CompanySummary(
                    id=c.id, name=c.entity_name, year=c.year,
                    property_count=len(c.properties), document_count=len(c.documents),
                ))
            return out

    def count_companies(self) -> int:
        with Session(self.engine) as s:
            return s.scalar(select(func.count()).select_from(CompanyRow)) or 0

    def first_company_id(self) -> int | None:
        with Session(self.engine) as s:
            row = s.query(CompanyRow).order_by(CompanyRow.id).first()
            return row.id if row else None

    def create_company(
        self, *, entity_name: str, year: int = 2026,
        fiscal_year_start: str | None = None, fiscal_year_end: str | None = None,
        framework: str = "ASPE", trust_created: str | None = None,
        full_time_employees: int = 0, quebec_paid_hours: str = "0",
    ) -> int:
        with Session(self.engine) as s:
            crow = CompanyRow(
                entity_name=entity_name, year=year,
                fiscal_year_start=fiscal_year_start or f"{year}-01-01",
                fiscal_year_end=fiscal_year_end or f"{year}-12-31",
                framework=framework, trust_created=trust_created or None,
                full_time_employees=full_time_employees, quebec_paid_hours=str(quebec_paid_hours),
            )
            s.add(crow)
            s.commit()
            return crow.id

    def get_company(self, company_id: int) -> Company:
        with Session(self.engine) as s:
            crow = s.get(CompanyRow, company_id)
            if crow is None:
                raise KeyError(f"No company with id {company_id}")
            return company_from_row(crow)

    def company_name(self, company_id: int) -> str:
        with Session(self.engine) as s:
            crow = s.get(CompanyRow, company_id)
            return crow.entity_name if crow else "?"

    def delete_company(self, company_id: int) -> None:
        with Session(self.engine) as s:
            crow = s.get(CompanyRow, company_id)
            if crow:
                for d in crow.documents:
                    self._remove_file(d.stored_path)
                s.delete(crow)
                s.commit()

    # -- buildings ----------------------------------------------------------
    def add_property(
        self, company_id: int, *, property_id: str, name: str, address: str = "",
        purchase_price: str = "0", purchase_date: str, land_value: str = "0",
        building_value: str = "0", chattels_value: str = "0", municipal_value: str = "0",
        in_montreal: bool = False, building_cca_class: str = "1",
        units: list[dict] | None = None,
    ) -> None:
        with Session(self.engine) as s:
            prow = PropertyRow(
                company_id=company_id, property_id=property_id, name=name, address=address,
                purchase_price=str(purchase_price), purchase_date=purchase_date,
                land_value=str(land_value), building_value=str(building_value),
                chattels_value=str(chattels_value), municipal_value=str(municipal_value),
                in_montreal=in_montreal, building_cca_class=building_cca_class,
            )
            for u in units or []:
                prow.units.append(UnitRow(
                    unit_id=u["unit_id"], kind=u["kind"], square_feet=str(u.get("square_feet", "0")),
                    monthly_rent=str(u.get("monthly_rent", "0")), occupied=bool(u.get("occupied", True)),
                ))
            s.add(prow)
            s.commit()

    def add_unit(
        self, company_id: int, property_id: str, *, unit_id: str, kind: str,
        square_feet: str = "0", monthly_rent: str = "0", occupied: bool = True,
    ) -> bool:
        with Session(self.engine) as s:
            prow = (
                s.query(PropertyRow)
                .filter(PropertyRow.company_id == company_id, PropertyRow.property_id == property_id)
                .first()
            )
            if prow is None:
                return False
            prow.units.append(UnitRow(
                unit_id=unit_id, kind=kind, square_feet=str(square_feet),
                monthly_rent=str(monthly_rent), occupied=occupied,
            ))
            s.commit()
            return True

    def add_mortgage(
        self, company_id: int, *, mortgage_id: str, property_id: str, principal: str,
        annual_rate: str, amortization_years: int, start_date: str,
        payments_per_year: int = 12, compounding_per_year: int = 2,
    ) -> None:
        with Session(self.engine) as s:
            s.add(MortgageRow(
                company_id=company_id, mortgage_id=mortgage_id, property_id=property_id,
                principal=str(principal), annual_rate=str(annual_rate),
                amortization_years=amortization_years, start_date=start_date,
                payments_per_year=payments_per_year, compounding_per_year=compounding_per_year,
            ))
            s.commit()

    # -- transactions -------------------------------------------------------
    def post_entry(self, company_id: int, entry: JournalEntry) -> None:
        with Session(self.engine) as s:
            erow = JournalEntryRow(
                company_id=company_id, date=entry.date.isoformat(),
                description=entry.description, reference=entry.reference, source=entry.source,
                property_id=entry.property_id,
            )
            for ln in entry.lines:
                erow.lines.append(JournalLineRow(
                    account_code=ln.account_code, debit=str(ln.debit.amount),
                    credit=str(ln.credit.amount), memo=ln.memo, property_id=ln.property_id,
                ))
            s.add(erow)
            s.commit()

    # -- documents ----------------------------------------------------------
    def add_document(
        self, company_id: int, *, doc_type: str, original_filename: str, data: bytes,
        content_type: str = "", property_id: str | None = None, period: str = "", notes: str = "",
    ) -> int:
        folder = os.path.join(self.uploads_dir, str(company_id))
        os.makedirs(folder, exist_ok=True)
        stored_name = f"{uuid.uuid4().hex}_{_safe_filename(original_filename)}"
        stored_path = os.path.join(folder, stored_name)
        with open(stored_path, "wb") as fh:
            fh.write(data)
        with Session(self.engine) as s:
            drow = DocumentRow(
                company_id=company_id, property_id=property_id or None, doc_type=doc_type,
                original_filename=original_filename, stored_path=stored_path,
                content_type=content_type, size_bytes=len(data), period=period, notes=notes,
                uploaded_at=datetime.now().isoformat(timespec="seconds"),
            )
            s.add(drow)
            s.commit()
            return drow.id

    def list_documents(self, company_id: int, property_id: str | None = None) -> list[DocumentInfo]:
        with Session(self.engine) as s:
            q = s.query(DocumentRow).filter(DocumentRow.company_id == company_id)
            if property_id:
                q = q.filter(DocumentRow.property_id == property_id)
            docs = q.order_by(DocumentRow.uploaded_at.desc()).all()
            return [self._doc_info(d) for d in docs]

    def get_document(self, doc_id: int) -> tuple[DocumentInfo, str] | None:
        with Session(self.engine) as s:
            d = s.get(DocumentRow, doc_id)
            if d is None:
                return None
            return self._doc_info(d), d.stored_path

    def delete_document(self, doc_id: int) -> None:
        with Session(self.engine) as s:
            d = s.get(DocumentRow, doc_id)
            if d:
                self._remove_file(d.stored_path)
                s.delete(d)
                s.commit()

    @staticmethod
    def _doc_info(d: DocumentRow) -> DocumentInfo:
        return DocumentInfo(
            id=d.id, company_id=d.company_id, property_id=d.property_id, doc_type=d.doc_type,
            doc_type_label=label_for(d.doc_type), original_filename=d.original_filename,
            size_bytes=d.size_bytes, period=d.period, notes=d.notes, uploaded_at=d.uploaded_at,
        )

    @staticmethod
    def _remove_file(path: str) -> None:
        try:
            os.remove(path)
        except OSError:
            pass

    # -- demo seeding -------------------------------------------------------
    def ensure_demo(self) -> int:
        """If the database has no companies, persist the demo company so the app isn't empty."""
        existing = self.first_company_id()
        if existing is not None:
            return existing
        from qcre.db.store import save_company
        from qcre.sample import build_sample_company
        # save_company wipes and writes one company into a *fresh* file — use a temp path,
        # then copy its single company into this multi-company DB.
        co = build_sample_company()
        return self._persist_company_object(co)

    def _persist_company_object(self, co: Company) -> int:
        with Session(self.engine) as s:
            crow = CompanyRow(
                entity_name=co.entity_name,
                fiscal_year_start=co.fiscal_year.start.isoformat(),
                fiscal_year_end=co.fiscal_year.end.isoformat(),
                framework=co.framework.value,
                trust_created=co.trust_created.isoformat() if co.trust_created else None,
                full_time_employees=co.full_time_employees,
                quebec_paid_hours=str(co.quebec_paid_hours), year=co.year,
            )
            for e in co.ledger.entries:
                erow = JournalEntryRow(
                    date=e.date.isoformat(), description=e.description, reference=e.reference,
                    source=e.source, property_id=e.property_id,
                )
                for ln in e.lines:
                    erow.lines.append(JournalLineRow(
                        account_code=ln.account_code, debit=str(ln.debit.amount),
                        credit=str(ln.credit.amount), memo=ln.memo, property_id=ln.property_id,
                    ))
                crow.entries.append(erow)
            for p in co.properties:
                prow = PropertyRow(
                    property_id=p.property_id, name=p.name, address=p.address,
                    purchase_price=str(p.purchase_price.amount),
                    purchase_date=p.purchase_date.isoformat(),
                    land_value=str(p.land_value.amount), building_value=str(p.building_value.amount),
                    chattels_value=str(p.chattels_value.amount),
                    municipal_value=str(p.municipal_value.amount),
                    in_montreal=p.in_montreal, building_cca_class=p.building_cca_class,
                )
                for u in p.units:
                    prow.units.append(UnitRow(
                        unit_id=u.unit_id, kind=u.kind.value, square_feet=str(u.square_feet),
                        monthly_rent=str(u.monthly_rent.amount), occupied=u.occupied,
                    ))
                crow.properties.append(prow)
            for m in co.mortgages:
                crow.mortgages.append(MortgageRow(
                    mortgage_id=m.mortgage_id, property_id=m.property_id,
                    principal=str(m.principal.amount), annual_rate=str(m.annual_rate),
                    amortization_years=m.amortization_years, start_date=m.start_date.isoformat(),
                    payments_per_year=m.payments_per_year, compounding_per_year=m.compounding_per_year,
                ))
            s.add(crow)
            s.commit()
            return crow.id
