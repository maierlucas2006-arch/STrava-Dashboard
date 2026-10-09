"""Einstellungen (Profil, Wettkampf, Zugangsdaten) als Schlüssel/Wert in SQLite.

Zugangsdaten können alternativ als Umgebungsvariablen gesetzt werden
(z. B. ``STRAVA_CLIENT_ID``); diese haben dann Vorrang.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from typing import Any

from triathlon import db

DEFAULTS: dict[str, Any] = {
    # Athlet
    "athlete_name": "",
    "weight_kg": 75.0,
    "height_cm": None,
    "birth_year": None,
    "sex": "m",
    "max_hr": None,
    "lthr": None,              # Laktatschwellen-Puls
    "resting_hr": 55,
    "ftp": None,               # Watt
    "threshold_pace": None,    # Sekunden pro km
    "css": None,               # Critical Swim Speed, Sekunden pro 100 m
    "paused_sports": [],       # z. B. ["run"] bei Verletzung
    # Wettkampf
    "race_name": "Nordschwarzwald Triathlon",
    "race_date": "2027-08-15",
    "race_distance": "Langdistanz",
    "race_goal_time": "",
    "target_ctl": None,        # None = Standardwert je Distanz
    # Ernährung
    "pal": 1.4,                # Alltagsaktivität ohne Sport
    "protein_per_kg": 2.0,
    "fat_per_kg": 1.0,
    # Synchronisierung
    "history_days": 365,
    "last_sync": None,
    # Zugänge
    "strava_client_id": "",
    "strava_client_secret": "",
    "strava_tokens": None,
    "strava_api_base": "https://www.strava.com/api/v3",
    "intervals_athlete_id": "0",
    "intervals_api_key": "",
}

ENV_OVERRIDES = {
    "strava_client_id": "STRAVA_CLIENT_ID",
    "strava_client_secret": "STRAVA_CLIENT_SECRET",
    "strava_api_base": "STRAVA_API_BASE",
    "intervals_athlete_id": "INTERVALS_ATHLETE_ID",
    "intervals_api_key": "INTERVALS_API_KEY",
}

RACE_DISTANCES = ["Sprint", "Olympisch", "Mitteldistanz", "Langdistanz"]
DEFAULT_TARGET_CTL = {"Sprint": 50, "Olympisch": 65, "Mitteldistanz": 80, "Langdistanz": 100}


def get(key: str) -> Any:
    env_name = ENV_OVERRIDES.get(key)
    if env_name and os.environ.get(env_name):
        return os.environ[env_name]
    row = db.fetch_one("SELECT value FROM settings WHERE key = ?", (key,))
    if row is None:
        return DEFAULTS.get(key)
    return json.loads(row["value"])


def set(key: str, value: Any) -> None:  # noqa: A001 - bewusst kurz: settings.set(...)
    db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value)),
    )


def set_many(values: dict[str, Any]) -> None:
    for key, value in values.items():
        set(key, value)


@dataclass
class Profile:
    name: str
    weight_kg: float
    height_cm: float | None
    birth_year: int | None
    sex: str
    max_hr: float | None
    lthr_set: float | None
    resting_hr: float
    ftp: float | None
    threshold_pace: float | None
    css: float | None
    paused_sports: list[str]
    race_name: str
    race_date: date | None
    race_distance: str
    race_goal_time: str
    target_ctl_set: float | None
    pal: float
    protein_per_kg: float
    fat_per_kg: float

    @property
    def lthr(self) -> float | None:
        """Schwellenpuls; ohne Eintrag geschätzt als 90 % der maximalen Herzfrequenz."""
        if self.lthr_set:
            return float(self.lthr_set)
        if self.max_hr:
            return round(0.9 * float(self.max_hr))
        return None

    @property
    def target_ctl(self) -> float:
        if self.target_ctl_set:
            return float(self.target_ctl_set)
        return float(DEFAULT_TARGET_CTL.get(self.race_distance, 80))

    def missing_thresholds(self) -> list[str]:
        missing = []
        if not self.ftp:
            missing.append("FTP (Rad)")
        if not self.threshold_pace:
            missing.append("Schwellen-Pace (Laufen)")
        if not self.css:
            missing.append("CSS (Schwimmen)")
        if not self.lthr:
            missing.append("Max-Puls oder Schwellenpuls")
        return missing


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def load_profile() -> Profile:
    g = get
    return Profile(
        name=g("athlete_name") or "",
        weight_kg=float(g("weight_kg") or 75.0),
        height_cm=g("height_cm"),
        birth_year=g("birth_year"),
        sex=g("sex") or "m",
        max_hr=g("max_hr"),
        lthr_set=g("lthr"),
        resting_hr=float(g("resting_hr") or 55),
        ftp=g("ftp"),
        threshold_pace=g("threshold_pace"),
        css=g("css"),
        paused_sports=list(g("paused_sports") or []),
        race_name=g("race_name") or "",
        race_date=_parse_date(g("race_date")),
        race_distance=g("race_distance") or "Langdistanz",
        race_goal_time=g("race_goal_time") or "",
        target_ctl_set=g("target_ctl"),
        pal=float(g("pal") or 1.4),
        protein_per_kg=float(g("protein_per_kg") or 2.0),
        fat_per_kg=float(g("fat_per_kg") or 1.0),
    )
