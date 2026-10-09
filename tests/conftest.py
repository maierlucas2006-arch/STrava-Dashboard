import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from triathlon import db  # noqa: E402


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Frische, leere Datenbank pro Test."""
    path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", path)
    monkeypatch.setenv("TRI_DB_PATH", str(path))
    db.init_db()
    return path
