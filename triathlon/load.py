"""Trainingsbelastung: TSS pro Einheit und Fitness/Ermüdung/Form (CTL/ATL/TSB).

TSS (Training Stress Score) = Stunden × Intensität² × 100, wobei die
Intensität (IF) je nach vorhandenen Daten berechnet wird:

* Rad mit Wattmesser: normierte Leistung / FTP
* Laufen: Tempo / Schwellentempo
* Schwimmen: Tempo / CSS (hier mit Exponent 3, wie beim sTSS üblich)
* sonst über die Herzfrequenz (Ø-Puls / Schwellenpuls)
* ohne Puls eine vorsichtige Schätzung über die Dauer
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Mapping

import pandas as pd

from triathlon import db
from triathlon.settings import Profile

CTL_DAYS = 42
ATL_DAYS = 7

SPORT_GROUPS = {
    "Swim": "swim",
    "Ride": "bike",
    "VirtualRide": "bike",
    "GravelRide": "bike",
    "MountainBikeRide": "bike",
    "EMountainBikeRide": "other",
    "EBikeRide": "other",
    "Velomobile": "bike",
    "Handcycle": "bike",
    "Run": "run",
    "TrailRun": "run",
    "VirtualRun": "run",
    "WeightTraining": "strength",
    "Crossfit": "strength",
}

GROUP_LABELS = {
    "swim": "Schwimmen",
    "bike": "Rad",
    "run": "Laufen",
    "strength": "Kraft",
    "other": "Sonstiges",
}

# Intensität, wenn weder Leistung, Tempo noch Puls vorhanden sind
DEFAULT_IF = {"swim": 0.70, "bike": 0.65, "run": 0.75, "strength": 0.60, "other": 0.55}

MAX_IF = 1.3


def sport_group(sport_type: str | None) -> str:
    return SPORT_GROUPS.get(sport_type or "", "other")


@dataclass
class LoadResult:
    tss: float
    method: str
    intensity: float | None


def _tss(hours: float, intensity: float, exponent: int, method: str) -> LoadResult:
    intensity = min(max(intensity, 0.0), MAX_IF)
    return LoadResult(round(hours * intensity**exponent * 100, 1), method, round(intensity, 2))


def activity_tss(act: Mapping, profile: Profile) -> LoadResult:
    seconds = act.get("moving_time") or 0
    if seconds <= 0:
        return LoadResult(0.0, "keine Dauer", None)
    hours = seconds / 3600
    group = sport_group(act.get("sport_type"))
    speed = act.get("average_speed") or 0
    distance = act.get("distance") or 0
    heartrate = act.get("average_heartrate")
    lthr = profile.lthr

    normalized_power = act.get("weighted_average_watts")
    if group == "bike" and act.get("device_watts") and normalized_power and profile.ftp:
        return _tss(hours, normalized_power / profile.ftp, 2, "Leistung")

    if group == "run" and speed > 0 and profile.threshold_pace:
        climb_per_km = (act.get("elevation_gain") or 0) / max(distance / 1000, 0.1)
        # Bei sehr hügeligen Läufen sagt das Tempo wenig – dann lieber Puls
        if not (heartrate and lthr and climb_per_km > 20):
            return _tss(hours, speed / (1000 / profile.threshold_pace), 2, "Pace")

    if group == "swim" and speed > 0 and profile.css:
        return _tss(hours, speed / (100 / profile.css), 3, "Schwimmtempo")

    if heartrate and lthr:
        return _tss(hours, heartrate / lthr, 2, "Herzfrequenz")

    return _tss(hours, DEFAULT_IF[group], 2, "Schätzung")


def strength_session_tss(duration_min: float | None, rpe: float | None) -> float:
    """Krafttraining über Dauer und subjektive Anstrengung (RPE 1–10)."""
    hours = (duration_min or 60) / 60
    rpe = rpe or 6
    return round(hours * (rpe / 10) ** 2 * 100, 1)


def activities_df(profile: Profile, since: date | None = None) -> pd.DataFrame:
    """Alle Strava-Aktivitäten inkl. berechneter Belastung."""
    sql = "SELECT * FROM activities"
    params: tuple = ()
    if since:
        sql += " WHERE local_date >= ?"
        params = (since.isoformat(),)
    df = db.query_df(sql + " ORDER BY start_date", params)
    if "raw_json" in df.columns:
        df = df.drop(columns=["raw_json"])
    if df.empty:
        for col in ("group", "sport", "tss", "tss_method", "intensity"):
            df[col] = pd.Series(dtype="object")
        df["local_date"] = pd.to_datetime(df["local_date"])
        return df
    results = [activity_tss(row, profile) for row in df.to_dict("records")]
    df["group"] = df["sport_type"].map(sport_group)
    df["sport"] = df["group"].map(GROUP_LABELS)
    df["tss"] = [r.tss for r in results]
    df["tss_method"] = [r.method for r in results]
    df["intensity"] = [r.intensity for r in results]
    df["local_date"] = pd.to_datetime(df["local_date"])
    return df


def strength_df(since: date | None = None) -> pd.DataFrame:
    sql = """
        SELECT s.id, s.date, s.duration_min, s.rpe, s.notes, s.template_id,
               t.name AS template, COALESCE(t.lower_body, 0) AS lower_body
        FROM strength_sessions s
        LEFT JOIN workout_templates t ON t.id = s.template_id
    """
    params: tuple = ()
    if since:
        sql += " WHERE s.date >= ?"
        params = (since.isoformat(),)
    df = db.query_df(sql + " ORDER BY s.date, s.id", params)
    df["date"] = pd.to_datetime(df["date"])
    df["tss"] = [strength_session_tss(d, r) for d, r in zip(df["duration_min"], df["rpe"])]
    return df


def daily_load(acts: pd.DataFrame, strength: pd.DataFrame, start: date, end: date) -> pd.Series:
    """TSS pro Tag. Krafttraining aus dem Tagebuch zählt nur, wenn an dem Tag
    nicht schon eine Strava-Krafteinheit erfasst ist (sonst doppelt)."""
    index = pd.date_range(start, end, freq="D")
    total = pd.Series(0.0, index=index)
    if not acts.empty:
        total = total.add(acts.groupby("local_date")["tss"].sum(), fill_value=0)
    if not strength.empty:
        strava_strength_days = set()
        if not acts.empty:
            strava_strength_days = set(acts.loc[acts["group"] == "strength", "local_date"])
        own = strength[~strength["date"].isin(strava_strength_days)]
        total = total.add(own.groupby("date")["tss"].sum(), fill_value=0)
    return total.reindex(index, fill_value=0.0)


def pmc(daily: pd.Series) -> pd.DataFrame:
    """Performance Management Chart: Fitness (CTL), Ermüdung (ATL), Form (TSB).

    Form für einen Tag = Fitness − Ermüdung vom Vortag (so wie bei TrainingPeaks)."""
    ctl = atl = 0.0
    rows = []
    for day, tss in daily.items():
        tsb = ctl - atl
        ctl += (tss - ctl) / CTL_DAYS
        atl += (tss - atl) / ATL_DAYS
        rows.append((day, tss, ctl, atl, tsb))
    df = pd.DataFrame(rows, columns=["date", "tss", "ctl", "atl", "tsb"]).set_index("date")
    df["ramp"] = df["ctl"] - df["ctl"].shift(7)
    return df
