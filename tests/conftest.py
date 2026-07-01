"""Pytest setup: isolate the web app's database/uploads to a temp dir.

The web module creates its ``Repo`` at import time from ``QCRE_DB`` / ``QCRE_UPLOADS``.
Setting these before any test module imports the app keeps test data out of the repo.
"""

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="qcre_test_")
os.environ.setdefault("QCRE_DB", os.path.join(_tmp, "test.db"))
os.environ.setdefault("QCRE_UPLOADS", os.path.join(_tmp, "uploads"))
