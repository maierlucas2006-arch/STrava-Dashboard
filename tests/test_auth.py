"""Anmeldung: Jedes Konto bekommt eine eigene Datenbank, Daten bleiben getrennt."""
import threading

import pytest

from triathlon import auth, db, settings

GOOGLE = "https://accounts.google.com"


def test_each_account_gets_its_own_file():
    anna, ben = auth.database_for(GOOGLE, "111"), auth.database_for(GOOGLE, "222")
    assert anna != ben
    assert anna == auth.database_for(GOOGLE, "111")          # immer dieselbe Datei
    assert anna.parent == auth.USERS_DIR and anna.suffix == ".db"
    assert "111" not in anna.name                             # keine Konto-ID im Dateinamen


def test_account_without_id_is_rejected():
    with pytest.raises(ValueError):
        auth.database_for(GOOGLE, "")


def test_data_is_separated(tmp_path):
    try:
        db.use_database(tmp_path / "anna.db")
        db.init_db()
        settings.set("athlete_name", "Anna")
        db.use_database(tmp_path / "ben.db")
        db.init_db()
        assert settings.get("athlete_name") == ""
        db.use_database(tmp_path / "anna.db")
        assert settings.get("athlete_name") == "Anna"
    finally:
        db.use_database(None)


def test_parallel_sessions_do_not_mix(tmp_path):
    """Streamlit führt jede Sitzung in einem eigenen Thread aus."""
    seen, barrier = {}, threading.Barrier(2)

    def session(name):
        db.use_database(tmp_path / f"{name}.db")
        db.init_db()
        settings.set("athlete_name", name)
        barrier.wait()                                        # beide sind jetzt gleichzeitig aktiv
        seen[name] = settings.get("athlete_name")

    threads = [threading.Thread(target=session, args=(n,)) for n in ("Anna", "Ben")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert seen == {"Anna": "Anna", "Ben": "Ben"}


def test_demo_mode(monkeypatch):
    monkeypatch.setenv("TRI_DB_PATH", "demo.db")
    assert auth.demo_mode()
    monkeypatch.delenv("TRI_DB_PATH")
    assert not auth.demo_mode()


def test_adopt_legacy_data(tmp_path, monkeypatch):
    monkeypatch.delenv("TRI_DB_PATH", raising=False)
    monkeypatch.setattr(db, "ROOT", tmp_path)
    assert auth.legacy_database() is None
    legacy = tmp_path / "data" / "dashboard.db"
    try:
        db.use_database(legacy)
        db.init_db()
        settings.set("athlete_name", "Tom")
        target = tmp_path / "data" / "users" / "konto.db"
        db.use_database(target)
        db.init_db()
        archived = auth.adopt_legacy_data(target)
        assert settings.get("athlete_name") == "Tom"
        assert not legacy.exists() and archived.exists()
        assert auth.legacy_database() is None                 # kein zweites Konto kann übernehmen
    finally:
        db.use_database(None)


def test_no_legacy_in_demo(monkeypatch):
    monkeypatch.setenv("TRI_DB_PATH", "demo.db")
    assert auth.legacy_database() is None
