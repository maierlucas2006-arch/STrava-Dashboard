"""Anmeldung: Jede Person meldet sich mit ihrem Google-Konto an und bekommt eine eigene Datenbank.

Den Login selbst übernimmt Streamlit (OpenID Connect, ``st.login``) – Passwörter landen
nie im Dashboard. Die Zugangsdaten stehen in ``.streamlit/secrets.toml`` (nicht im Git).
"""
from __future__ import annotations

import hashlib
import os
import shutil
from datetime import date
from pathlib import Path

from triathlon import db

USERS_DIR = db.ROOT / "data" / "users"


def demo_mode() -> bool:
    """Demo (start_demo.py) und Tests setzen TRI_DB_PATH und laufen ohne Anmeldung."""
    return bool(os.environ.get("TRI_DB_PATH"))


def database_for(issuer: str, subject: str) -> Path:
    """Eigene Datei pro Konto. Der Name ist ein Hash der Konto-ID – keine E-Mail im Dateinamen."""
    if not subject:
        raise ValueError("Das Konto hat keine eindeutige Kennung (sub).")
    key = hashlib.sha256(f"{issuer}|{subject}".encode()).hexdigest()[:32]
    return USERS_DIR / f"{key}.db"


def legacy_database() -> Path | None:
    """Die Datenbank aus der Zeit vor der Anmeldung (``data/dashboard.db``), falls noch vorhanden."""
    if demo_mode():
        return None
    legacy = db.ROOT / "data" / "dashboard.db"
    return legacy if legacy.exists() else None


def adopt_legacy_data(target: Path) -> Path:
    """Kopiert die bisherigen Daten in die Datei des angemeldeten Kontos (überschreibt sie) und
    benennt die alte Datei um, damit sie kein anderes Konto übernehmen kann. Gibt den neuen
    Namen der alten Datei zurück."""
    legacy = legacy_database()
    if legacy is None:
        raise FileNotFoundError("Keine bisherigen Daten gefunden.")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(legacy, target)
    archived = legacy.with_name(f"dashboard-uebernommen-{date.today():%Y-%m-%d}.db")
    counter = 1
    while archived.exists():
        counter += 1
        archived = legacy.with_name(f"dashboard-uebernommen-{date.today():%Y-%m-%d}-{counter}.db")
    legacy.rename(archived)
    return archived
