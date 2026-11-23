"""Energieverfügbarkeit, Datenexport, Konto löschen, zentrale Strava-App und automatischer Abgleich."""
import io
import json
import zipfile
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from triathlon import auth, db, demo, export, nutrition, settings, strava
from triathlon.analysis import build_state
from triathlon.sync import sync_due

TODAY = date(2026, 11, 23)


# --------------------------------------------------------------------------- Energieverfügbarkeit

def test_fat_free_mass_uses_body_fat_or_estimate(tmp_db):
    settings.set_many({"weight_kg": 80.0, "sex": "m"})
    ffm, estimated = nutrition.fat_free_mass(settings.load_profile())
    assert estimated and ffm == pytest.approx(80 * 0.85)
    settings.set("body_fat_pct", 12.0)
    ffm, estimated = nutrition.fat_free_mass(settings.load_profile())
    assert not estimated and ffm == pytest.approx(80 * 0.88)


def test_energy_availability_per_day(tmp_db):
    settings.set_many({"weight_kg": 70.0, "body_fat_pct": 10.0})   # FFM 63 kg
    food = nutrition.save_food({"name": "Reis", "kcal": 350, "protein": 7, "carbs": 77, "fat": 1}, "eigene")
    nutrition.log_food(TODAY, "Mittagessen", food, 900)            # 3150 kcal
    db.execute("INSERT INTO activities (id, sport_type, local_date, moving_time, distance) VALUES (1, 'Run', ?, 3600, 12000)",
               (TODAY.isoformat(),))
    ea = nutrition.energy_availability(settings.load_profile(), TODAY, TODAY)
    training = 70 * 12 - 70 * 1                                     # Laufen: kg × km − Grundumsatz
    assert ea["training"].iloc[0] == pytest.approx(training)
    assert ea["ea"].iloc[0] == pytest.approx((3150 - training) / 63)


def test_ea_levels_and_average():
    assert nutrition.ea_level(25) == "low"
    assert nutrition.ea_level(30) == "reduced"
    assert nutrition.ea_level(45) == "ok"
    days = pd.to_datetime([TODAY - timedelta(days=d) for d in (0, 1, 2, 3)])
    ea = pd.DataFrame({"date": days, "ea": [5.0, 30.0, 40.0, 50.0]})
    assert nutrition.ea_average(ea, TODAY) == pytest.approx(40)      # heute zählt nicht mit
    assert nutrition.ea_average(ea.iloc[:3], TODAY) is None          # nur 2 Tage vor heute


# --------------------------------------------------------------------------- Export

def test_daily_table_and_csv(tmp_db):
    demo.build_demo(TODAY)
    state = build_state(TODAY)
    table = export.daily_table(state, TODAY - timedelta(days=6))
    assert len(table) == 7
    assert table.index[0] == pd.Timestamp(TODAY)                     # neueste zuerst
    for column in ("Belastung (TSS)", "Fitness (CTL)", "HRV (ms)", "Hooper-Index", "Energie (kcal)",
                   "Energieverfügbarkeit (kcal/kg FFM)"):
        assert column in table.columns
    text = export.to_csv(table).decode("utf-8-sig")
    header, first = text.splitlines()[:2]
    assert header.startswith("Datum;Belastung (TSS);")
    assert first.startswith(f"{TODAY:%d.%m.%Y};")
    assert "," in first and "." not in first.split(";", 1)[1]        # Dezimalkomma


def test_daily_table_skips_empty_history(tmp_db):
    state = build_state(TODAY)
    assert export.daily_table(state).empty


def test_zip_contains_all_tables_without_secrets(tmp_db):
    settings.set_many({"strava_tokens": {"access_token": "geheim"}, "wger_api_key": "geheim2", "athlete_name": "Tom"})
    data = export.all_data_zip("tom@example.org")
    zf = zipfile.ZipFile(io.BytesIO(data))
    names = zf.namelist()
    assert {"settings.csv", "activities.csv", "hooper.csv", "LIESMICH.txt"} <= set(names)
    settings_csv = zf.read("settings.csv").decode()
    assert "geheim" not in settings_csv
    assert "Tom" in settings_csv
    assert json.dumps(export.REDACTED) in pd.read_csv(io.BytesIO(zf.read("settings.csv")))["value"].tolist()
    assert "tom@example.org" in zf.read("LIESMICH.txt").decode()


# --------------------------------------------------------------------------- Konto löschen

def test_delete_account_removes_the_file(tmp_path, monkeypatch):
    monkeypatch.delenv("TRI_DB_PATH", raising=False)
    path = tmp_path / "users" / "abc.db"
    db.use_database(path)
    try:
        db.init_db()
        assert not auth.has_own_data()                               # nur vorbefüllte Tabellen
        db.execute("INSERT INTO hooper (date, sleep_quality, fatigue, stress, soreness) VALUES ('2026-11-23', 3, 3, 3, 3)")
        assert auth.has_own_data()
        auth.delete_account(path)
        assert not path.exists()
    finally:
        db.use_database(None)


def test_delete_is_refused_in_demo(tmp_db):
    with pytest.raises(PermissionError):
        auth.delete_account(tmp_db)
    assert tmp_db.exists()


def test_data_dir_can_be_moved(monkeypatch, tmp_path):
    import importlib
    monkeypatch.setenv("TRI_DATA_DIR", str(tmp_path / "volume"))
    reloaded = importlib.reload(auth)
    try:
        assert reloaded.USERS_DIR == tmp_path / "volume" / "users"
    finally:
        monkeypatch.delenv("TRI_DATA_DIR")
        importlib.reload(auth)


# --------------------------------------------------------------------------- Strava zentral

def test_central_strava_app(tmp_db, monkeypatch):
    monkeypatch.delenv("STRAVA_CLIENT_ID", raising=False)
    monkeypatch.delenv("STRAVA_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("STRAVA_REDIRECT_URI", raising=False)
    assert not strava.app_managed()
    assert strava.redirect_uri() == "http://localhost:8501/"
    monkeypatch.setenv("STRAVA_CLIENT_ID", "4711")
    monkeypatch.setenv("STRAVA_CLIENT_SECRET", "s3cret")
    monkeypatch.setenv("STRAVA_REDIRECT_URI", "https://tri.example.org/")
    assert strava.app_managed() and strava.is_configured()
    url = strava.authorize_url()
    assert "client_id=4711" in url and "redirect_uri=https%3A%2F%2Ftri.example.org%2F" in url


def test_disconnect_also_deauthorizes(tmp_db, monkeypatch):
    calls = []
    monkeypatch.setattr(strava.requests, "post", lambda url, data, timeout: calls.append((url, data)))
    settings.set("strava_tokens", {"access_token": "tok", "refresh_token": "r", "expires_at": 9_999_999_999})
    strava.disconnect()
    assert calls == [(strava.DEAUTHORIZE_URL, {"access_token": "tok"})]
    assert settings.get("strava_tokens") is None


# --------------------------------------------------------------------------- Automatischer Abgleich

def test_sync_due():
    now = datetime(2026, 11, 23, 12, 0)
    assert sync_due(None, now)
    assert sync_due("kaputt", now)
    assert not sync_due((now - timedelta(hours=1)).isoformat(timespec="minutes"), now)
    assert sync_due((now - timedelta(hours=3)).isoformat(timespec="minutes"), now)
