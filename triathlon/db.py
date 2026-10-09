"""Lokale SQLite-Datenbank: Verbindung, Schema und kleine Helfer.

Alle Daten liegen in ``data/dashboard.db`` (nicht im Git). Über die
Umgebungsvariable ``TRI_DB_PATH`` lässt sich eine andere Datei nutzen,
z. B. für Demo-Daten oder Tests.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("TRI_DB_PATH", ROOT / "data" / "dashboard.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activities (
    id                     INTEGER PRIMARY KEY,   -- Strava-ID
    name                   TEXT,
    sport_type             TEXT,
    start_date             TEXT,                  -- UTC, ISO 8601
    local_date             TEXT,                  -- YYYY-MM-DD (Ortszeit)
    moving_time            INTEGER,               -- Sekunden
    elapsed_time           INTEGER,
    distance               REAL,                  -- Meter
    elevation_gain         REAL,
    average_speed          REAL,                  -- m/s
    average_heartrate      REAL,
    max_heartrate          REAL,
    average_watts          REAL,
    weighted_average_watts REAL,
    kilojoules             REAL,
    device_watts           INTEGER,
    trainer                INTEGER,
    raw_json               TEXT
);
CREATE INDEX IF NOT EXISTS idx_activities_date ON activities(local_date);

CREATE TABLE IF NOT EXISTS wellness (
    date         TEXT PRIMARY KEY,                -- YYYY-MM-DD
    resting_hr   REAL,
    hrv          REAL,                            -- rMSSD in ms
    sleep_secs   REAL,
    sleep_score  REAL,
    weight       REAL,
    steps        REAL,
    source       TEXT,
    raw_json     TEXT
);

CREATE TABLE IF NOT EXISTS exercises (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,
    rep_min       INTEGER NOT NULL DEFAULT 8,
    rep_max       INTEGER NOT NULL DEFAULT 12,
    increment_kg  REAL NOT NULL DEFAULT 2.5
);

CREATE TABLE IF NOT EXISTS workout_templates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    position    INTEGER NOT NULL,                 -- Reihenfolge in der Rotation
    lower_body  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS template_exercises (
    template_id  INTEGER NOT NULL REFERENCES workout_templates(id) ON DELETE CASCADE,
    exercise_id  INTEGER NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
    position     INTEGER NOT NULL,
    target_sets  INTEGER NOT NULL DEFAULT 3,
    PRIMARY KEY (template_id, exercise_id)
);

CREATE TABLE IF NOT EXISTS strength_sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    date          TEXT NOT NULL,
    template_id   INTEGER REFERENCES workout_templates(id) ON DELETE SET NULL,
    duration_min  INTEGER,
    rpe           REAL,
    notes         TEXT
);

CREATE TABLE IF NOT EXISTS strength_sets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER NOT NULL REFERENCES strength_sessions(id) ON DELETE CASCADE,
    exercise_id  INTEGER NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
    set_no       INTEGER NOT NULL,
    weight       REAL,
    reps         INTEGER,
    rpe          REAL
);

CREATE TABLE IF NOT EXISTS foods (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    brand      TEXT,
    barcode    TEXT UNIQUE,
    kcal       REAL NOT NULL,                     -- alle Nährwerte pro 100 g
    protein    REAL NOT NULL,
    carbs      REAL NOT NULL,
    fat        REAL NOT NULL,
    source     TEXT,
    last_used  TEXT
);

CREATE TABLE IF NOT EXISTS food_log (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    date     TEXT NOT NULL,
    meal     TEXT NOT NULL,
    food_id  INTEGER NOT NULL REFERENCES foods(id) ON DELETE CASCADE,
    grams    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_food_log_date ON food_log(date);

CREATE TABLE IF NOT EXISTS goals (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    title          TEXT NOT NULL,
    category       TEXT,
    metric         TEXT NOT NULL DEFAULT 'manual',
    start_value    REAL,
    target_value   REAL,
    current_value  REAL,                          -- nur für manuelle Ziele
    unit           TEXT,
    deadline       TEXT,
    done           INTEGER NOT NULL DEFAULT 0,
    notes          TEXT,
    created        TEXT NOT NULL
);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    """Führt eine Anweisung aus und gibt die ID der neuen Zeile zurück."""
    with connect() as con:
        cur = con.execute(sql, tuple(params))
        return cur.lastrowid


def executemany(sql: str, rows: Iterable[Iterable[Any]]) -> None:
    with connect() as con:
        con.executemany(sql, [tuple(r) for r in rows])


def fetch_all(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    with connect() as con:
        return [dict(r) for r in con.execute(sql, tuple(params)).fetchall()]


def fetch_one(sql: str, params: Iterable[Any] = ()) -> dict | None:
    with connect() as con:
        row = con.execute(sql, tuple(params)).fetchone()
        return dict(row) if row else None


def query_df(sql: str, params: Iterable[Any] = ()) -> pd.DataFrame:
    with connect() as con:
        return pd.read_sql_query(sql, con, params=tuple(params))


def init_db() -> None:
    """Legt fehlende Tabellen an und befüllt Startdaten (Kraftpläne, Lebensmittel)."""
    from triathlon import seed

    with connect() as con:
        con.executescript(SCHEMA)
    seed.seed_defaults()
