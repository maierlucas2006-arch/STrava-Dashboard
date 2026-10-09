"""intervals.icu-Anbindung für Garmin-Regenerationsdaten (Schlaf, Ruhepuls, HRV).

Garmin Connect → intervals.icu (offizielle Verbindung, kostenlos) → Dashboard.
Zugriff über den persönlichen API-Key (intervals.icu → Settings → Developer Settings).
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import requests

from triathlon import db, settings

BASE_URL = "https://intervals.icu/api/v1"


class IntervalsError(Exception):
    pass


def is_configured() -> bool:
    return bool(settings.get("intervals_api_key"))


def _athlete_id() -> str:
    return (settings.get("intervals_athlete_id") or "0").strip() or "0"


def _get(path: str, params: dict | None = None):
    key = settings.get("intervals_api_key")
    if not key:
        raise IntervalsError("Kein intervals.icu-API-Key eingetragen.")
    try:
        response = requests.get(f"{BASE_URL}{path}", params=params or {}, auth=("API_KEY", key), timeout=30)
    except requests.RequestException as exc:
        raise IntervalsError(f"intervals.icu nicht erreichbar: {exc}") from exc
    if response.status_code in (401, 403):
        raise IntervalsError("intervals.icu lehnt den Zugriff ab – API-Key und Athleten-ID prüfen.")
    if response.status_code != 200:
        raise IntervalsError(f"intervals.icu-Fehler {response.status_code}: {response.text[:200]}")
    return response.json()


def test_connection() -> str:
    athlete = _get(f"/athlete/{_athlete_id()}")
    return athlete.get("name") or athlete.get("id") or "OK"


UPSERT_SQL = """
INSERT INTO wellness (date, resting_hr, hrv, sleep_secs, sleep_score, weight, steps, source, raw_json)
VALUES (?, ?, ?, ?, ?, ?, ?, 'intervals.icu', ?)
ON CONFLICT(date) DO UPDATE SET
    resting_hr  = COALESCE(excluded.resting_hr, wellness.resting_hr),
    hrv         = COALESCE(excluded.hrv, wellness.hrv),
    sleep_secs  = COALESCE(excluded.sleep_secs, wellness.sleep_secs),
    sleep_score = COALESCE(excluded.sleep_score, wellness.sleep_score),
    weight      = COALESCE(excluded.weight, wellness.weight),
    steps       = COALESCE(excluded.steps, wellness.steps),
    source      = excluded.source,
    raw_json    = excluded.raw_json
"""


def sync_wellness(full: bool = False) -> int:
    latest = db.fetch_one("SELECT MAX(date) AS d FROM wellness WHERE source = 'intervals.icu'")
    today = date.today()
    if full or not latest or not latest["d"]:
        oldest = today - timedelta(days=int(settings.get("history_days") or 365))
    else:
        oldest = date.fromisoformat(latest["d"]) - timedelta(days=7)
    records = _get(f"/athlete/{_athlete_id()}/wellness",
                   {"oldest": oldest.isoformat(), "newest": today.isoformat()})
    rows = []
    for r in records:
        day = str(r.get("id") or "")[:10]
        if not day:
            continue
        rows.append((day, r.get("restingHR"), r.get("hrv"), r.get("sleepSecs"), r.get("sleepScore"),
                     r.get("weight"), r.get("steps"), json.dumps(r)))
    db.executemany(UPSERT_SQL, rows)
    return len(rows)


def save_manual(day: date, resting_hr: float | None, hrv: float | None, sleep_hours: float | None,
                sleep_score: float | None, weight: float | None) -> None:
    """Manueller Eintrag, falls intervals.icu (noch) nicht eingerichtet ist."""
    db.execute(
        """INSERT INTO wellness (date, resting_hr, hrv, sleep_secs, sleep_score, weight, source)
           VALUES (?, ?, ?, ?, ?, ?, 'manuell')
           ON CONFLICT(date) DO UPDATE SET
               resting_hr = COALESCE(excluded.resting_hr, wellness.resting_hr),
               hrv = COALESCE(excluded.hrv, wellness.hrv),
               sleep_secs = COALESCE(excluded.sleep_secs, wellness.sleep_secs),
               sleep_score = COALESCE(excluded.sleep_score, wellness.sleep_score),
               weight = COALESCE(excluded.weight, wellness.weight)""",
        (day.isoformat(), resting_hr, hrv, sleep_hours * 3600 if sleep_hours else None, sleep_score, weight),
    )
