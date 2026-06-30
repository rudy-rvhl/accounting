"""Round-trip persistence and integration-analysis tests."""

import os
import tempfile

from qcre.analysis import tax_position
from qcre.db.store import load_company, save_company
from qcre.sample import build_sample_company


def test_save_and_load_roundtrip_preserves_books():
    co = build_sample_company()
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "co.db")
        save_company(co, path)
        loaded = load_company(path)

    # Same number of entries and identical trial-balance totals.
    assert len(loaded.ledger.entries) == len(co.ledger.entries)
    assert loaded.ledger.is_in_balance()
    orig_tb = co.ledger.trial_balance_totals()
    new_tb = loaded.ledger.trial_balance_totals()
    assert orig_tb == new_tb
    # Domain objects survive.
    assert len(loaded.properties) == 2
    assert len(loaded.mortgages) == 2
    assert loaded.entity_name == co.entity_name


def test_tax_position_classifies_rental_as_sib():
    co = build_sample_company()
    pos = tax_position(co)
    # Demo has 2 employees → rental is a specified investment business.
    assert pos.corporate.rental_is_sib is True
    assert pos.taxable_rental_income.is_positive()
    # CCA should be claimed but capped by the rental-loss restriction (cannot exceed income).
    assert pos.cca_claimed <= pos.rental_income_before_cca
    assert pos.corporate.total_tax.is_positive()
