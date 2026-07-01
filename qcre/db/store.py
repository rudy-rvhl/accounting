"""Save and load a :class:`qcre.company.Company` to/from a SQLite database.

A database holds a single company (it is wiped and rewritten on save). The ledger is
reconstructed by replaying the stored journal entries, so loading reproduces identical
books and statements.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

from qcre.company import Company
from qcre.core import FiscalYear, Ledger, Money, default_chart
from qcre.core.journal import JournalEntry, JournalLine
from qcre.db.models import (
    Base,
    CompanyRow,
    JournalEntryRow,
    JournalLineRow,
    MortgageRow,
    PropertyRow,
    UnitRow,
)
from qcre.domain.mortgage import Mortgage
from qcre.domain.property import Property, RentalUnit, UnitKind
from qcre.reports.framework import Framework


def _engine(path: str):
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    return eng


def save_company(company: Company, path: str) -> str:
    eng = _engine(path)
    with Session(eng) as s:
        for model in (CompanyRow,):  # cascades clear the rest
            s.execute(delete(model))
        s.commit()

        crow = CompanyRow(
            entity_name=company.entity_name,
            fiscal_year_start=company.fiscal_year.start.isoformat(),
            fiscal_year_end=company.fiscal_year.end.isoformat(),
            framework=company.framework.value,
            trust_created=company.trust_created.isoformat() if company.trust_created else None,
            full_time_employees=company.full_time_employees,
            quebec_paid_hours=str(company.quebec_paid_hours),
            year=company.year,
        )
        s.add(crow)

        for e in company.ledger.entries:
            erow = JournalEntryRow(
                company=crow, date=e.date.isoformat(), description=e.description,
                reference=e.reference, source=e.source, property_id=e.property_id,
            )
            for ln in e.lines:
                erow.lines.append(JournalLineRow(
                    account_code=ln.account_code, debit=str(ln.debit.amount),
                    credit=str(ln.credit.amount), memo=ln.memo, property_id=ln.property_id,
                ))
            s.add(erow)

        for p in company.properties:
            prow = PropertyRow(
                company=crow, property_id=p.property_id, name=p.name, address=p.address,
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
            s.add(prow)

        for m in company.mortgages:
            s.add(MortgageRow(
                company=crow, mortgage_id=m.mortgage_id, property_id=m.property_id,
                principal=str(m.principal.amount), annual_rate=str(m.annual_rate),
                amortization_years=m.amortization_years, start_date=m.start_date.isoformat(),
                payments_per_year=m.payments_per_year, compounding_per_year=m.compounding_per_year,
            ))
        s.commit()
    return path


def company_from_row(crow: CompanyRow) -> Company:
    """Rebuild a :class:`Company` (ledger replayed, properties, mortgages) from ORM rows."""
    ledger = Ledger(default_chart())
    for erow in sorted(crow.entries, key=lambda e: (e.date, e.id)):
        lines = [
            JournalLine(
                account_code=l.account_code, debit=Money(l.debit), credit=Money(l.credit),
                memo=l.memo, property_id=l.property_id,
            )
            for l in erow.lines
        ]
        ledger.post(JournalEntry(
            date=date.fromisoformat(erow.date), description=erow.description,
            lines=lines, reference=erow.reference, source=erow.source,
            property_id=erow.property_id,
        ))

    properties = []
    for prow in crow.properties:
        units = [
            RentalUnit(u.unit_id, UnitKind(u.kind), Decimal(u.square_feet),
                       Money(u.monthly_rent), u.occupied)
            for u in prow.units
        ]
        properties.append(Property(
            property_id=prow.property_id, name=prow.name, address=prow.address,
            purchase_price=Money(prow.purchase_price),
            purchase_date=date.fromisoformat(prow.purchase_date),
            land_value=Money(prow.land_value), building_value=Money(prow.building_value),
            chattels_value=Money(prow.chattels_value), municipal_value=Money(prow.municipal_value),
            in_montreal=prow.in_montreal, building_cca_class=prow.building_cca_class, units=units,
        ))

    mortgages = [
        Mortgage(
            m.mortgage_id, m.property_id, Money(m.principal), Decimal(m.annual_rate),
            m.amortization_years, date.fromisoformat(m.start_date),
            m.payments_per_year, m.compounding_per_year,
        )
        for m in crow.mortgages
    ]

    return Company(
        entity_name=crow.entity_name, ledger=ledger, properties=properties,
        mortgages=mortgages,
        fiscal_year=FiscalYear(date.fromisoformat(crow.fiscal_year_start),
                               date.fromisoformat(crow.fiscal_year_end)),
        framework=Framework(crow.framework),
        trust_created=date.fromisoformat(crow.trust_created) if crow.trust_created else None,
        full_time_employees=crow.full_time_employees,
        quebec_paid_hours=Decimal(crow.quebec_paid_hours), year=crow.year,
    )


def load_company(path: str) -> Company:
    eng = _engine(path)
    with Session(eng) as s:
        crow = s.query(CompanyRow).first()
        if crow is None:
            raise ValueError(f"No company stored in {path}")
        return company_from_row(crow)


def seed(path: str) -> str:
    """Build the demo company and persist it."""
    from qcre.sample import build_sample_company
    return save_company(build_sample_company(), path)
