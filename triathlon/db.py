"""Lokale SQLite-Datenbank: Verbindung, Schema und kleine Helfer.

Jedes Konto hat eine eigene Datei unter ``data/users/`` (nicht im Git), siehe ``auth.py``.
Welche Datei gerade gilt, legt ``use_database`` für den laufenden Durchlauf fest.
Ohne Auswahl gilt ``data/dashboard.db`` bzw. die Datei aus ``TRI_DB_PATH``
(Demo-Daten und Tests).
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterable, Iterator

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("TRI_DB_PATH", ROOT / "data" / "dashboard.db"))

# Pro Durchlauf (Streamlit startet für jede Sitzung einen eigenen Thread) die Datei
# des angemeldeten Kontos. Ein ContextVar ist pro Thread getrennt – zwei Personen,
# die gleichzeitig angemeldet sind, landen nie in derselben Datei.
_active_path: ContextVar[Path | None] = ContextVar("tri_db_path", default=None)


def use_database(path: Path | None) -> None:
    """Wählt die Datenbank für den aktuellen Durchlauf. ``None`` = Standarddatei."""
    _active_path.set(Path(path) if path else None)


def current_path() -> Path:
    return _active_path.get() or DB_PATH


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

-- Übungsliste aus Hevy (Zwischenspeicher für die Zuordnung eigener Übungen)
CREATE TABLE IF NOT EXISTS hevy_exercise_templates (
    id                    TEXT PRIMARY KEY,       -- Hevy-ID, z. B. "D04AC939"
    title                 TEXT NOT NULL,
    type                  TEXT,
    primary_muscle_group  TEXT,
    equipment             TEXT,
    is_custom             INTEGER NOT NULL DEFAULT 0
);

-- Übungsliste aus wger (Zwischenspeicher für die Zuordnung eigener Übungen)
CREATE TABLE IF NOT EXISTS wger_exercises (
    id       INTEGER PRIMARY KEY,                 -- Übungs-ID in wger
    name     TEXT NOT NULL,                       -- Anzeigename (deutsch, sonst englisch)
    name_de  TEXT,
    name_en  TEXT
);

-- Vom Dashboard in wger angelegte Routinen-Einträge (für Gewichts-Updates)
CREATE TABLE IF NOT EXISTS wger_entries (
    template_id       INTEGER NOT NULL REFERENCES workout_templates(id) ON DELETE CASCADE,
    exercise_id       INTEGER NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
    slot_entry_id     INTEGER NOT NULL,
    reps_config_id    INTEGER,
    weight_config_id  INTEGER,
    PRIMARY KEY (template_id, exercise_id)
);

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
    path = current_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
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


# Spalten, die nach der ersten Version dazugekommen sind. Bestehende Datenbanken
# bekommen sie beim Start automatisch (die Daten bleiben erhalten).
MIGRATIONS: list[tuple[str, str, str]] = [
    ("exercises", "hevy_template_id", "TEXT"),                  # zugeordnete Hevy-Übung
    ("exercises", "from_hevy", "INTEGER NOT NULL DEFAULT 0"),   # 1 = beim Hevy-Import angelegt
    ("workout_templates", "hevy_routine_id", "TEXT"),           # Routine in Hevy zu diesem Plan
    ("strength_sessions", "hevy_id", "TEXT"),                   # Workout-ID in Hevy
    ("exercises", "wger_exercise_id", "INTEGER"),               # zugeordnete wger-Übung
    ("exercises", "from_wger", "INTEGER NOT NULL DEFAULT 0"),   # 1 = beim wger-Import angelegt
    ("workout_templates", "wger_day_id", "INTEGER"),            # Trainingstag in der wger-Routine
    ("strength_sessions", "wger_id", "TEXT"),                   # Einheit in wger (Session-ID)
]


def _migrate(con: sqlite3.Connection) -> None:
    for table, column, declaration in MIGRATIONS:
        columns = {row["name"] for row in con.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_strength_sessions_hevy ON strength_sessions(hevy_id)")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_strength_sessions_wger ON strength_sessions(wger_id)")


def init_db() -> None:
    """Legt fehlende Tabellen an und befüllt Startdaten (Kraftpläne, Lebensmittel)."""
    from triathlon import seed

    with connect() as con:
        con.executescript(SCHEMA)
        _migrate(con)
    seed.seed_defaults()
