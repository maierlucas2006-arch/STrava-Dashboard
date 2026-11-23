"""Regeneration: HRV-Baseline, Ruhepuls, Schlaf, Morgen-Check → Ampel (grün/gelb/rot).

HRV-Logik (angelehnt an HRV4Training/Plews): Die nächtliche HRV (rMSSD) wird
logarithmiert. Normalbereich = 60-Tage-Mittel ± 0,5 Standardabweichungen.
Liegt der 7-Tage-Schnitt darunter, ist der Körper wahrscheinlich nicht
vollständig erholt.

Morgen-Check (Hooper & Mackinnon 1995): Schlafqualität, Müdigkeit, Stress und
Muskelkater je 1–7; die Summe (4–28) heißt Hooper-Index, höher = schlechter.
Auffällig ist ein Tag, der mehr als 1,5 Standardabweichungen über dem eigenen
60-Tage-Schnitt liegt.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from triathlon import db

HRV_BASELINE_DAYS = 60
HRV_MIN_DAYS = 14
RHR_BASELINE_DAYS = 30
MAX_DATA_AGE_DAYS = 1  # Werte von heute oder gestern gelten als aktuell

HOOPER_ITEMS = {
    "sleep_quality": ("Schlafqualität", "1 = sehr gut · 7 = sehr schlecht"),
    "fatigue": ("Müdigkeit", "1 = gar nicht · 7 = extrem"),
    "stress": ("Stress", "1 = gar nicht · 7 = extrem"),
    "soreness": ("Muskelkater", "1 = gar nicht · 7 = extrem"),
}
HOOPER_BASELINE_DAYS = 60
HOOPER_MIN_ENTRIES = 7
HOOPER_SD_LIMIT = 1.5      # Hooper & Mackinnon: auffällig ab 1,5 SD über dem eigenen Schnitt
HOOPER_MIN_SD = 2.0        # eigene Festlegung: sonst löst bei sehr gleichmäßigen Einträgen schon 1 Punkt aus
HOOPER_HIGH = 20           # ohne Baseline (eigene Faustregel): im Schnitt „schlecht“ (5) pro Frage
HOOPER_VERY_HIGH = 24

LEVELS = {
    "green": ("🟢", "Grün"),
    "yellow": ("🟡", "Gelb"),
    "red": ("🔴", "Rot"),
}


def wellness_df() -> pd.DataFrame:
    df = db.query_df(
        "SELECT date, resting_hr, hrv, sleep_secs, sleep_score, weight, steps, source"
        " FROM wellness ORDER BY date"
    )
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df["sleep_hours"] = df["sleep_secs"] / 3600
    return df


def save_hooper(day: date, sleep_quality: int, fatigue: int, stress: int, soreness: int,
                note: str | None = None) -> None:
    values = (sleep_quality, fatigue, stress, soreness)
    if any(v is None or not 1 <= int(v) <= 7 for v in values):
        raise ValueError("Jede Frage braucht einen Wert von 1 bis 7.")
    db.execute(
        "INSERT INTO hooper (date, sleep_quality, fatigue, stress, soreness, note) VALUES (?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(date) DO UPDATE SET sleep_quality = excluded.sleep_quality, fatigue = excluded.fatigue,"
        " stress = excluded.stress, soreness = excluded.soreness, note = excluded.note",
        (day.isoformat(), *(int(v) for v in values), (note or "").strip() or None),
    )


def hooper_df() -> pd.DataFrame:
    """Alle Morgen-Checks, Index = Datum, Spalte ``index`` = Hooper-Index (4–28)."""
    df = db.query_df("SELECT date, sleep_quality, fatigue, stress, soreness, note FROM hooper ORDER BY date")
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df["index"] = df[list(HOOPER_ITEMS)].sum(axis=1)
    return df


@dataclass
class HooperStatus:
    index: int                       # Hooper-Index des Tages
    baseline: float | None           # Schnitt der Vortage (60 Tage), None = zu wenige Einträge
    limit: float | None              # ab hier auffällig
    points: int                      # 0, −1 oder −2 für die Ampel

    @property
    def worse(self) -> bool:
        return self.points < 0


def hooper_status(hdf: pd.DataFrame, day: date) -> HooperStatus | None:
    """Bewertung des Morgen-Checks von ``day``; None, wenn an dem Tag keiner ausgefüllt wurde."""
    end = pd.Timestamp(day)
    if hdf is None or hdf.empty or end not in hdf.index:
        return None
    value = int(hdf.loc[end, "index"])
    history = hdf["index"][(hdf.index < end) & (hdf.index >= end - pd.Timedelta(days=HOOPER_BASELINE_DAYS))]
    if len(history) >= HOOPER_MIN_ENTRIES:
        mean = float(history.mean())
        sd = max(float(history.std(ddof=1)), HOOPER_MIN_SD)
        limit = mean + HOOPER_SD_LIMIT * sd
        points = 0
        if value > limit:
            points = -2 if value >= HOOPER_VERY_HIGH else -1
        return HooperStatus(value, mean, limit, points)
    points = -2 if value >= HOOPER_VERY_HIGH else -1 if value >= HOOPER_HIGH else 0
    return HooperStatus(value, None, None, points)


@dataclass
class HrvStatus:
    baseline_ms: float
    low_ms: float
    high_ms: float
    avg7_ms: float | None
    today_ms: float | None
    today_low: bool  # heutiger Wert < Mittel − 1 SD

    @property
    def trend(self) -> str:
        if self.avg7_ms is None:
            return "unknown"
        if self.avg7_ms < self.low_ms:
            return "low"
        if self.avg7_ms > self.high_ms:
            return "high"
        return "normal"


def hrv_status(wdf: pd.DataFrame, day: date) -> HrvStatus | None:
    if wdf.empty or "hrv" not in wdf:
        return None
    values = wdf["hrv"].dropna()
    values = values[values > 0]
    ln = np.log(values)
    end = pd.Timestamp(day)
    history = ln[(ln.index <= end) & (ln.index > end - pd.Timedelta(days=HRV_BASELINE_DAYS))]
    if len(history) < HRV_MIN_DAYS:
        return None
    mean, sd = history.mean(), history.std(ddof=1)
    last7 = ln[(ln.index <= end) & (ln.index > end - pd.Timedelta(days=7))]
    avg7 = math.exp(last7.mean()) if len(last7) >= 3 else None
    today = ln.get(end)
    return HrvStatus(
        baseline_ms=math.exp(mean),
        low_ms=math.exp(mean - 0.5 * sd),
        high_ms=math.exp(mean + 0.5 * sd),
        avg7_ms=avg7,
        today_ms=math.exp(today) if today is not None else None,
        today_low=bool(today is not None and today < mean - sd),
    )


def resting_hr_delta(wdf: pd.DataFrame, day: date) -> tuple[float, float] | None:
    """(heutiger Ruhepuls, Abweichung vom 30-Tage-Schnitt der Vortage)."""
    if wdf.empty:
        return None
    rhr = wdf["resting_hr"].dropna()
    end = pd.Timestamp(day)
    if end not in rhr.index:
        return None
    history = rhr[(rhr.index < end) & (rhr.index >= end - pd.Timedelta(days=RHR_BASELINE_DAYS))]
    if len(history) < 7:
        return None
    return float(rhr[end]), float(rhr[end] - history.mean())


@dataclass
class Readiness:
    level: str                       # green / yellow / red
    score: int
    reasons: list[tuple[str, int]] = field(default_factory=list)  # (Text, Punkte)
    has_wellness: bool = False

    @property
    def emoji(self) -> str:
        return LEVELS[self.level][0]

    @property
    def label(self) -> str:
        return LEVELS[self.level][1]


def readiness(day: date, wdf: pd.DataFrame, tsb: float | None,
              hooper: pd.DataFrame | None = None) -> Readiness:
    reasons: list[tuple[str, int]] = []
    has_wellness = False

    latest = wdf.index.max() if not wdf.empty else None
    fresh = latest is not None and (pd.Timestamp(day) - latest).days <= MAX_DATA_AGE_DAYS
    # Garmin ordnet Schlaf/Ruhepuls dem Aufwach-Tag zu; fehlt heute, nehmen wir gestern.
    data_day = day if (latest is not None and pd.Timestamp(day) in wdf.index) else day - timedelta(days=1)

    if fresh:
        has_wellness = True
        hrv = hrv_status(wdf, data_day)
        if hrv is None:
            reasons.append(("HRV: noch zu wenig Daten für eine Baseline (mind. 14 Nächte)", 0))
        else:
            if hrv.trend == "low":
                reasons.append((f"HRV-Trend unter deinem Normalbereich (Ø 7 Tage {hrv.avg7_ms:.0f} ms, "
                                f"normal {hrv.low_ms:.0f}–{hrv.high_ms:.0f} ms)", -2))
            elif hrv.trend == "high":
                reasons.append((f"HRV-Trend über dem Normalbereich ({hrv.avg7_ms:.0f} ms)", 0))
            elif hrv.trend == "normal":
                reasons.append((f"HRV im Normalbereich (Ø 7 Tage {hrv.avg7_ms:.0f} ms)", 0))
            if hrv.today_low:
                reasons.append((f"HRV letzte Nacht deutlich niedrig ({hrv.today_ms:.0f} ms)", -1))

        rhr = resting_hr_delta(wdf, data_day)
        if rhr:
            value, delta = rhr
            if delta >= 8:
                reasons.append((f"Ruhepuls deutlich erhöht ({value:.0f}, +{delta:.0f} zum Schnitt)", -2))
            elif delta >= 5:
                reasons.append((f"Ruhepuls erhöht ({value:.0f}, +{delta:.0f} zum Schnitt)", -1))
            else:
                reasons.append((f"Ruhepuls normal ({value:.0f})", 0))

        row = wdf.loc[pd.Timestamp(data_day)] if pd.Timestamp(data_day) in wdf.index else None
        if row is not None:
            sleep_penalty = 0
            hours = row.get("sleep_hours")
            if hours is not None and not pd.isna(hours):
                if hours < 5:
                    sleep_penalty -= 2
                elif hours < 6.5:
                    sleep_penalty -= 1
                text = f"Schlaf {hours:.1f} h"
                score = row.get("sleep_score")
                if score is not None and not pd.isna(score):
                    text += f" (Score {score:.0f})"
                    if score < 50:
                        sleep_penalty -= 1
                sleep_penalty = max(sleep_penalty, -2)
                reasons.append((text + (" – zu wenig" if sleep_penalty < 0 else ""), sleep_penalty))

    check = hooper_status(hooper, day) if hooper is not None else None
    if not fresh:
        reasons.append(("Keine aktuellen Garmin-Daten – Ampel nur nach Trainingsbelastung"
                        + (" und Morgen-Check" if check is not None else ""), 0))

    if check is not None:
        usual = f", üblich {check.baseline:.0f}" if check.baseline is not None else ""
        if check.worse:
            reasons.append((f"Morgen-Check: Befinden schlechter als sonst (Hooper-Index {check.index}{usual})",
                            check.points))
        else:
            reasons.append((f"Morgen-Check: Befinden im üblichen Rahmen (Hooper-Index {check.index}{usual})", 0))

    if tsb is not None:
        if tsb < -30:
            reasons.append((f"Form (TSB) {tsb:.0f}: sehr hohe Ermüdung", -2))
        elif tsb < -20:
            reasons.append((f"Form (TSB) {tsb:.0f}: hohe Ermüdung", -1))
        elif tsb > 15:
            reasons.append((f"Form (TSB) +{tsb:.0f}: sehr frisch", 0))
        else:
            reasons.append((f"Form (TSB) {tsb:+.0f}: im grünen Bereich", 0))

    score = sum(points for _, points in reasons)
    level = "green" if score >= -1 else "yellow" if score >= -3 else "red"
    return Readiness(level=level, score=score, reasons=reasons, has_wellness=has_wellness)
