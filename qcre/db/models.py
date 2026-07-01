"""SQLAlchemy ORM models.

Money and rates are stored as text to preserve exact ``Decimal`` precision (never floats).
The general ledger is persisted as journal entries + lines — the ledger is rebuilt by
replaying them, so the stored books are the single source of truth.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, Integer, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CompanyRow(Base):
    __tablename__ = "company"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_name: Mapped[str] = mapped_column(String)
    fiscal_year_start: Mapped[str] = mapped_column(String)
    fiscal_year_end: Mapped[str] = mapped_column(String)
    framework: Mapped[str] = mapped_column(String, default="ASPE")
    trust_created: Mapped[str | None] = mapped_column(String, nullable=True)
    full_time_employees: Mapped[int] = mapped_column(Integer, default=0)
    quebec_paid_hours: Mapped[str] = mapped_column(String, default="0")
    year: Mapped[int] = mapped_column(Integer, default=2026)

    entries: Mapped[list["JournalEntryRow"]] = relationship(
        back_populates="company", cascade="all, delete-orphan")
    properties: Mapped[list["PropertyRow"]] = relationship(
        back_populates="company", cascade="all, delete-orphan")
    mortgages: Mapped[list["MortgageRow"]] = relationship(
        back_populates="company", cascade="all, delete-orphan")
    documents: Mapped[list["DocumentRow"]] = relationship(
        back_populates="company", cascade="all, delete-orphan")


class JournalEntryRow(Base):
    __tablename__ = "journal_entry"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"))
    date: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)
    reference: Mapped[str] = mapped_column(String, default="")
    source: Mapped[str] = mapped_column(String, default="")
    property_id: Mapped[str | None] = mapped_column(String, nullable=True)

    company: Mapped[CompanyRow] = relationship(back_populates="entries")
    lines: Mapped[list["JournalLineRow"]] = relationship(
        back_populates="entry", cascade="all, delete-orphan")


class JournalLineRow(Base):
    __tablename__ = "journal_line"
    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("journal_entry.id"))
    account_code: Mapped[str] = mapped_column(String)
    debit: Mapped[str] = mapped_column(String, default="0")
    credit: Mapped[str] = mapped_column(String, default="0")
    memo: Mapped[str] = mapped_column(String, default="")
    property_id: Mapped[str | None] = mapped_column(String, nullable=True)

    entry: Mapped[JournalEntryRow] = relationship(back_populates="lines")


class PropertyRow(Base):
    __tablename__ = "property"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"))
    property_id: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    address: Mapped[str] = mapped_column(String, default="")
    purchase_price: Mapped[str] = mapped_column(String, default="0")
    purchase_date: Mapped[str] = mapped_column(String)
    land_value: Mapped[str] = mapped_column(String, default="0")
    building_value: Mapped[str] = mapped_column(String, default="0")
    chattels_value: Mapped[str] = mapped_column(String, default="0")
    municipal_value: Mapped[str] = mapped_column(String, default="0")
    in_montreal: Mapped[bool] = mapped_column(Boolean, default=False)
    building_cca_class: Mapped[str] = mapped_column(String, default="1")

    company: Mapped[CompanyRow] = relationship(back_populates="properties")
    units: Mapped[list["UnitRow"]] = relationship(
        back_populates="property", cascade="all, delete-orphan")


class UnitRow(Base):
    __tablename__ = "unit"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_db_id: Mapped[int] = mapped_column(ForeignKey("property.id"))
    unit_id: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    square_feet: Mapped[str] = mapped_column(String, default="0")
    monthly_rent: Mapped[str] = mapped_column(String, default="0")
    occupied: Mapped[bool] = mapped_column(Boolean, default=True)

    property: Mapped[PropertyRow] = relationship(back_populates="units")


class DocumentRow(Base):
    __tablename__ = "document"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"))
    property_id: Mapped[str | None] = mapped_column(String, nullable=True)  # optional building
    doc_type: Mapped[str] = mapped_column(String)                          # e.g. "bank_statement"
    original_filename: Mapped[str] = mapped_column(String)
    stored_path: Mapped[str] = mapped_column(String)
    content_type: Mapped[str] = mapped_column(String, default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    period: Mapped[str] = mapped_column(String, default="")                # e.g. "2026-01"
    notes: Mapped[str] = mapped_column(String, default="")
    uploaded_at: Mapped[str] = mapped_column(String, default="")

    company: Mapped[CompanyRow] = relationship(back_populates="documents")


class MortgageRow(Base):
    __tablename__ = "mortgage"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"))
    mortgage_id: Mapped[str] = mapped_column(String)
    property_id: Mapped[str] = mapped_column(String)
    principal: Mapped[str] = mapped_column(String, default="0")
    annual_rate: Mapped[str] = mapped_column(String, default="0")
    amortization_years: Mapped[int] = mapped_column(Integer, default=25)
    start_date: Mapped[str] = mapped_column(String)
    payments_per_year: Mapped[int] = mapped_column(Integer, default=12)
    compounding_per_year: Mapped[int] = mapped_column(Integer, default=2)

    company: Mapped[CompanyRow] = relationship(back_populates="mortgages")
