"""Runnable seed: ``python -m qcre.db.seed [path]`` builds and stores the demo company."""

from __future__ import annotations

import sys

from qcre.db.store import seed

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "qcre.db"
    seed(path)
    print(f"Seeded demo company to {path}")
