"""Alle Datenquellen auf einmal synchronisieren."""
from __future__ import annotations

from datetime import datetime

from triathlon import db, intervals, settings, strava


def sync_all(full: bool = False) -> list[tuple[str, bool, str]]:
    """Gibt (Quelle, erfolgreich, Meldung) je Quelle zurück."""
    results: list[tuple[str, bool, str]] = []

    if strava.is_connected():
        try:
            n = strava.sync_activities(full=full)
            results.append(("Strava", True, f"{n} Aktivitäten geladen"))
        except strava.StravaError as exc:
            results.append(("Strava", False, str(exc)))
    else:
        results.append(("Strava", False, "nicht verbunden"))

    if intervals.is_configured():
        try:
            n = intervals.sync_wellness(full=full)
            results.append(("intervals.icu", True, f"{n} Tage Regenerationsdaten geladen"))
            _update_weight_from_wellness()
        except intervals.IntervalsError as exc:
            results.append(("intervals.icu", False, str(exc)))
    else:
        results.append(("intervals.icu", False, "nicht eingerichtet"))

    if any(ok for _, ok, _ in results):
        settings.set("last_sync", datetime.now().isoformat(timespec="minutes"))
    return results


def _update_weight_from_wellness() -> None:
    row = db.fetch_one("SELECT weight FROM wellness WHERE weight IS NOT NULL ORDER BY date DESC LIMIT 1")
    if row and row["weight"]:
        settings.set("weight_kg", round(float(row["weight"]), 1))
