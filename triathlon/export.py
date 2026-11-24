"""Daten herausgeben: Tageswerte als CSV und alle eigenen Daten als ZIP.

Die CSV ist für ein deutsches Excel gedacht: Semikolon, Dezimalkomma, UTF-8 mit BOM.
Im ZIP fehlen nur Zugangsschlüssel (Tokens, API-Keys) – die sind kein Inhalt, sondern
Schlüssel zu anderen Diensten.
"""
from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime

import pandas as pd

from triathlon import db, nutrition
from triathlon.analysis import State

SECRET_SETTINGS = {"strava_tokens", "strava_client_secret", "strava_own_client_secret", "intervals_api_key", "hevy_api_key", "wger_api_key"}
REDACTED = "(entfernt)"

DAILY_COLUMNS = {
    "tss": "Belastung (TSS)",
    "ctl": "Fitness (CTL)",
    "atl": "Ermüdung (ATL)",
    "tsb": "Form (TSB)",
    "swim_min": "Schwimmen (min)",
    "bike_min": "Rad (min)",
    "run_min": "Laufen (min)",
    "strength_min": "Kraft (min)",
    "other_min": "Sonstiges (min)",
    "resting_hr": "Ruhepuls",
    "hrv": "HRV (ms)",
    "sleep_hours": "Schlaf (h)",
    "sleep_score": "Schlaf-Score",
    "weight": "Gewicht (kg)",
    "hooper": "Hooper-Index",
    "kcal": "Energie (kcal)",
    "protein": "Eiweiß (g)",
    "carbs": "Kohlenhydrate (g)",
    "fat": "Fett (g)",
    "ea": "Energieverfügbarkeit (kcal/kg FFM)",
}


def daily_table(state: State, start: date | None = None) -> pd.DataFrame:
    """Eine Zeile pro Tag mit allen Kennzahlen, neueste zuerst. Spalten mit Klartext-Namen."""
    end = pd.Timestamp(state.today)
    first = state.pmc.index.min() if not state.pmc.empty else end
    if not state.wellness.empty:
        first = min(first, state.wellness.index.min())
    start_ts = max(pd.Timestamp(start), first) if start else first
    index = pd.date_range(start_ts, end, freq="D")
    df = pd.DataFrame(index=index)

    if not state.pmc.empty:
        df = df.join(state.pmc[["tss", "ctl", "atl", "tsb"]])

    acts = state.activities
    if not acts.empty:
        minutes = acts.groupby(["local_date", "group"])["moving_time"].sum().unstack(fill_value=0) / 60
        for group in ("swim", "bike", "run", "strength", "other"):
            if group in minutes:
                df[f"{group}_min"] = minutes[group]
    sessions = state.strength_sessions
    if not sessions.empty:
        # wie bei der Belastung: Kraft aus dem Tagebuch nur an Tagen ohne Strava-Krafteinheit
        strava_days = set(acts.loc[acts["group"] == "strength", "local_date"]) if not acts.empty else set()
        own = sessions[~sessions["date"].isin(strava_days)].groupby("date")["duration_min"].sum(min_count=1)
        df["strength_min"] = df.get("strength_min", pd.Series(0.0, index=df.index)).fillna(0).add(
            own.reindex(df.index), fill_value=0)

    if not state.wellness.empty:
        df = df.join(state.wellness[["resting_hr", "hrv", "sleep_hours", "sleep_score", "weight"]])
    if not state.hooper.empty:
        df = df.join(state.hooper["index"].rename("hooper"))

    food = nutrition.daily_totals(index.min().date(), end.date())
    if not food.empty:
        df = df.join(food.set_index("date")[["kcal", "protein", "carbs", "fat"]])
        ea = nutrition.energy_availability(state.profile, index.min().date(), end.date())
        if not ea.empty:
            df = df.join(ea.set_index("date")["ea"])

    for minute_col in ("swim_min", "bike_min", "run_min", "strength_min", "other_min"):
        if minute_col in df:
            df[minute_col] = df[minute_col].fillna(0)
    df = df[[c for c in DAILY_COLUMNS if c in df.columns]].astype(float).round(1)
    has_data = (df.fillna(0) != 0).any(axis=1)
    df = df.loc[has_data.idxmax():] if has_data.any() else df.iloc[0:0]   # leere Tage am Anfang weglassen
    df = df.rename(columns=DAILY_COLUMNS).sort_index(ascending=False)
    df.index.name = "Datum"
    return df


def to_csv(df: pd.DataFrame) -> bytes:
    """CSV für deutsches Excel (Semikolon, Dezimalkomma, Datum TT.MM.JJJJ)."""
    out = df.copy()
    if isinstance(out.index, pd.DatetimeIndex):
        out.index = out.index.strftime("%d.%m.%Y")
    return out.to_csv(sep=";", decimal=",", encoding="utf-8-sig").encode("utf-8-sig")


def _tables() -> list[str]:
    rows = db.fetch_all("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    return [r["name"] for r in rows]


def all_data_zip(account: str | None = None) -> bytes:
    """Alle Tabellen der eigenen Datenbank als CSV (Komma, Punkt – maschinenlesbar) in einer ZIP-Datei."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for table in _tables():
            df = db.query_df(f'SELECT * FROM "{table}"')
            if table == "settings":
                df.loc[df["key"].isin(SECRET_SETTINGS), "value"] = json.dumps(REDACTED)
            zf.writestr(f"{table}.csv", df.to_csv(index=False))
        zf.writestr("LIESMICH.txt", (
            "Export aus dem Triathlon Dashboard\n"
            f"Erstellt: {datetime.now():%d.%m.%Y %H:%M}\n"
            + (f"Konto: {account}\n" if account else "")
            + "\nJede Datei ist eine Tabelle der Datenbank (CSV, Komma als Trenner, Punkt als Dezimalzeichen).\n"
            "Zugangsschlüssel zu Strava, intervals.icu, wger und Hevy sind entfernt.\n"
        ))
    return buffer.getvalue()
