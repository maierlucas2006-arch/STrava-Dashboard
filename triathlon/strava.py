"""Strava-Anbindung (offizielle API, OAuth2).

Ablauf: In den Einstellungen Client-ID und Client-Secret deiner Strava-App
eintragen → „Mit Strava verbinden“ → Strava leitet zurück auf
http://localhost:8501/?code=… → das Dashboard tauscht den Code gegen Tokens.
"""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

from triathlon import db, settings

AUTH_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
SCOPES = "read,activity:read_all,profile:read_all"
REDIRECT_URI = os.environ.get("STRAVA_REDIRECT_URI", "http://localhost:8501/")
OAUTH_STATE = "triathlon-dashboard"
PAGE_SIZE = 200


class StravaError(Exception):
    pass


def is_configured() -> bool:
    return bool(settings.get("strava_client_id") and settings.get("strava_client_secret"))


def is_connected() -> bool:
    return bool(settings.get("strava_tokens"))


def authorize_url() -> str:
    params = {
        "client_id": settings.get("strava_client_id"),
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "approval_prompt": "auto",
        "scope": SCOPES,
        "state": OAUTH_STATE,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def _token_request(data: dict) -> dict:
    payload = {
        "client_id": settings.get("strava_client_id"),
        "client_secret": settings.get("strava_client_secret"),
        **data,
    }
    try:
        response = requests.post(TOKEN_URL, data=payload, timeout=30)
    except requests.RequestException as exc:
        raise StravaError(f"Strava nicht erreichbar: {exc}") from exc
    if response.status_code != 200:
        raise StravaError(f"Strava-Anmeldung fehlgeschlagen ({response.status_code}): {response.text[:200]}")
    tokens = response.json()
    settings.set("strava_tokens", {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "expires_at": tokens["expires_at"],
    })
    return tokens


def exchange_code(code: str) -> dict:
    """Tauscht den Code aus der Weiterleitung gegen Tokens und merkt sich den Namen."""
    tokens = _token_request({"code": code, "grant_type": "authorization_code"})
    athlete = tokens.get("athlete") or {}
    if athlete.get("firstname"):
        settings.set("athlete_name", athlete["firstname"])
    return athlete


def disconnect() -> None:
    settings.set("strava_tokens", None)


def _access_token() -> str:
    tokens = settings.get("strava_tokens")
    if not tokens:
        raise StravaError("Nicht mit Strava verbunden – bitte in den Einstellungen verbinden.")
    if tokens["expires_at"] < time.time() + 60:
        tokens = _token_request({"refresh_token": tokens["refresh_token"], "grant_type": "refresh_token"})
    return tokens["access_token"]


def _get(path: str, params: dict | None = None):
    base = (settings.get("strava_api_base") or "https://www.strava.com/api/v3").rstrip("/")
    try:
        response = requests.get(f"{base}{path}", params=params or {},
                                headers={"Authorization": f"Bearer {_access_token()}"}, timeout=30)
    except requests.RequestException as exc:
        raise StravaError(f"Strava nicht erreichbar: {exc}") from exc
    if response.status_code == 429:
        raise StravaError("Strava-Abfragelimit erreicht – bitte in 15 Minuten noch einmal synchronisieren.")
    if response.status_code == 401:
        raise StravaError("Strava-Zugriff abgelaufen oder entzogen – bitte in den Einstellungen neu verbinden.")
    if response.status_code != 200:
        raise StravaError(f"Strava-Fehler {response.status_code}: {response.text[:200]}")
    return response.json()


def import_profile() -> dict:
    """Übernimmt Name, Gewicht und FTP aus dem Strava-Profil."""
    athlete = _get("/athlete")
    updates = {}
    if athlete.get("firstname"):
        updates["athlete_name"] = athlete["firstname"]
    if athlete.get("weight"):
        updates["weight_kg"] = round(float(athlete["weight"]), 1)
    if athlete.get("ftp"):
        updates["ftp"] = int(athlete["ftp"])
    settings.set_many(updates)
    return updates


def max_heartrate_seen(days: int = 365) -> float | None:
    since = (date.today() - timedelta(days=days)).isoformat()
    row = db.fetch_one("SELECT MAX(max_heartrate) AS hr FROM activities WHERE local_date >= ?", (since,))
    return row["hr"] if row and row["hr"] else None


def _activity_row(a: dict) -> tuple:
    return (
        a["id"],
        a.get("name"),
        a.get("sport_type") or a.get("type"),
        a.get("start_date"),
        (a.get("start_date_local") or a.get("start_date") or "")[:10],
        a.get("moving_time"),
        a.get("elapsed_time"),
        a.get("distance"),
        a.get("total_elevation_gain"),
        a.get("average_speed"),
        a.get("average_heartrate"),
        a.get("max_heartrate"),
        a.get("average_watts"),
        a.get("weighted_average_watts"),
        a.get("kilojoules"),
        int(bool(a.get("device_watts"))),
        int(bool(a.get("trainer"))),
        json.dumps(a),
    )


UPSERT_SQL = """
INSERT INTO activities (id, name, sport_type, start_date, local_date, moving_time, elapsed_time, distance,
    elevation_gain, average_speed, average_heartrate, max_heartrate, average_watts, weighted_average_watts,
    kilojoules, device_watts, trainer, raw_json)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    name = excluded.name, sport_type = excluded.sport_type, start_date = excluded.start_date,
    local_date = excluded.local_date, moving_time = excluded.moving_time, elapsed_time = excluded.elapsed_time,
    distance = excluded.distance, elevation_gain = excluded.elevation_gain,
    average_speed = excluded.average_speed, average_heartrate = excluded.average_heartrate,
    max_heartrate = excluded.max_heartrate, average_watts = excluded.average_watts,
    weighted_average_watts = excluded.weighted_average_watts, kilojoules = excluded.kilojoules,
    device_watts = excluded.device_watts, trainer = excluded.trainer, raw_json = excluded.raw_json
"""


def sync_activities(full: bool = False) -> int:
    """Lädt neue Aktivitäten (die letzten 3 Tage immer erneut, falls nachträglich
    bearbeitet). ``full=True`` lädt den kompletten Zeitraum aus den Einstellungen."""
    latest = db.fetch_one("SELECT MAX(start_date) AS d FROM activities")
    if full or not latest or not latest["d"]:
        start = datetime.now(timezone.utc) - timedelta(days=int(settings.get("history_days") or 365))
    else:
        start = datetime.fromisoformat(latest["d"].replace("Z", "+00:00")) - timedelta(days=3)

    count = 0
    page = 1
    while True:
        batch = _get("/athlete/activities",
                     {"after": int(start.timestamp()), "per_page": PAGE_SIZE, "page": page})
        if not batch:
            break
        db.executemany(UPSERT_SQL, [_activity_row(a) for a in batch])
        count += len(batch)
        if len(batch) < PAGE_SIZE:
            break
        page += 1
    return count
