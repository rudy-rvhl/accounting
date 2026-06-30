"""Domain models and business events for a real-estate company.

These higher-level objects (properties, leases, mortgages) and events (rent billing,
expenses, acquisitions, dispositions) translate real-world activity into the balanced
journal entries the ledger records, applying the correct GST/QST treatment as they go.
"""

from qcre.domain.property import Property, RentalUnit, UnitKind
from qcre.domain.lease import Lease
from qcre.domain.mortgage import Mortgage, AmortizationRow

__all__ = ["Property", "RentalUnit", "UnitKind", "Lease", "Mortgage", "AmortizationRow"]
