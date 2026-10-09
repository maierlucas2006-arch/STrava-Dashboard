"""Ziele: manuelle Ziele und Ziele, deren Stand automatisch aus den Daten kommt."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

from triathlon import db
from triathlon.analysis import State

CATEGORIES = ["Wettkampf", "Leistung", "Training", "Körper", "Ernährung", "Sonstiges"]

METRICS = {
    "manual": ("Manuell (Stand selbst eintragen)", ""),
    "ctl": ("Fitness (CTL)", "CTL"),
    "ftp": ("FTP aus den Einstellungen", "W"),
    "weight": ("Gewicht (Ø 7 Tage)", "kg"),
    "resting_hr": ("Ruhepuls (Ø 7 Tage)", "bpm"),
    "week_swim_km": ("Schwimm-km diese Woche", "km"),
    "week_bike_km": ("Rad-km diese Woche", "km"),
    "week_run_km": ("Lauf-km diese Woche", "km"),
    "week_hours": ("Trainingsstunden diese Woche", "h"),
    "week_strength": ("Krafteinheiten diese Woche", "x"),
}
WEEKLY_METRICS = {"week_swim_km", "week_bike_km", "week_run_km", "week_hours", "week_strength"}


def current_value(metric: str, state: State, manual: float | None = None) -> float | None:
    if metric == "manual":
        return manual
    if metric == "ctl":
        return round(state.ctl, 1)
    if metric == "ftp":
        return state.profile.ftp
    if metric in ("weight", "resting_hr"):
        column = metric
        w = state.wellness
        if w.empty or column not in w:
            return state.profile.weight_kg if metric == "weight" else None
        recent = w.loc[w.index > pd.Timestamp(state.today - timedelta(days=7)), column].dropna()
        return round(float(recent.mean()), 1) if not recent.empty else None
    if metric in WEEKLY_METRICS:
        monday = pd.Timestamp(state.today - timedelta(days=state.today.weekday()))
        acts = state.activities
        week = acts[acts["local_date"] >= monday] if not acts.empty else acts
        if metric == "week_strength":
            own = state.strength_sessions
            return float((own["date"] >= monday).sum())
        if metric == "week_hours":
            return round(float(week["moving_time"].sum()) / 3600, 1) if not week.empty else 0.0
        group = {"week_swim_km": "swim", "week_bike_km": "bike", "week_run_km": "run"}[metric]
        if week.empty:
            return 0.0
        return round(float(week.loc[week["group"] == group, "distance"].sum()) / 1000, 1)
    return None


def progress(metric: str, start: float | None, target: float | None, current: float | None) -> float | None:
    """Fortschritt 0–1. Funktioniert auch für sinkende Ziele (z. B. Gewicht)."""
    if target is None or current is None:
        return None
    if metric in WEEKLY_METRICS or start is None or start == target:
        if target == 0:
            return None
        return max(min(current / target, 1.0), 0.0)
    return max(min((current - start) / (target - start), 1.0), 0.0)


def list_goals(include_done: bool = True) -> list[dict]:
    sql = "SELECT * FROM goals"
    if not include_done:
        sql += " WHERE done = 0"
    return db.fetch_all(sql + " ORDER BY done, deadline IS NULL, deadline, id")


def add_goal(title: str, category: str, metric: str, start_value: float | None, target_value: float | None,
             unit: str, deadline: date | None, notes: str) -> int:
    return db.execute(
        """INSERT INTO goals (title, category, metric, start_value, target_value, current_value, unit, deadline,
                              notes, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (title.strip(), category, metric, start_value, target_value,
         start_value if metric == "manual" else None, unit,
         deadline.isoformat() if deadline else None, notes or None, datetime.now().isoformat()),
    )


def update_manual_value(goal_id: int, value: float) -> None:
    db.execute("UPDATE goals SET current_value = ? WHERE id = ?", (value, goal_id))


def set_done(goal_id: int, done: bool) -> None:
    db.execute("UPDATE goals SET done = ? WHERE id = ?", (int(done), goal_id))


def delete_goal(goal_id: int) -> None:
    db.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
