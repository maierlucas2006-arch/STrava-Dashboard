"""Krafttraining: Rotation, Tagebuch, Progressionsvorschläge, Fortschritt."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from triathlon import db


# --------------------------------------------------------------------------- Pläne & Rotation

def templates() -> list[dict]:
    return db.fetch_all("SELECT * FROM workout_templates ORDER BY position, id")


def template_exercises(template_id: int) -> list[dict]:
    return db.fetch_all(
        """SELECT e.*, te.position, te.target_sets
           FROM template_exercises te JOIN exercises e ON e.id = te.exercise_id
           WHERE te.template_id = ? ORDER BY te.position, e.name""",
        (template_id,),
    )


def all_exercises() -> list[dict]:
    return db.fetch_all("SELECT * FROM exercises ORDER BY name")


def rotation(count: int) -> list[dict]:
    """Die nächsten ``count`` Einheiten der Rotation, beginnend nach der zuletzt
    eingetragenen Einheit."""
    plans = templates()
    if not plans:
        return []
    last = db.fetch_one(
        "SELECT template_id FROM strength_sessions WHERE template_id IS NOT NULL"
        " ORDER BY date DESC, id DESC LIMIT 1"
    )
    ids = [p["id"] for p in plans]
    start = (ids.index(last["template_id"]) + 1) % len(plans) if last and last["template_id"] in ids else 0
    return [plans[(start + i) % len(plans)] for i in range(count)]


# --------------------------------------------------------------------------- Progression

@dataclass
class Suggestion:
    weight: float
    reps: int
    note: str


def e1rm(weight: float | None, reps: float | None) -> float | None:
    """Geschätztes Maximalgewicht (1RM) nach Epley."""
    if not weight or not reps or weight <= 0 or reps <= 0:
        return None
    if reps == 1:
        return float(weight)
    return float(weight) * (1 + reps / 30)


def suggest(rep_min: int, rep_max: int, increment: float, last_sets: list[dict]) -> Suggestion | None:
    """Doppelte Progression: erst Wiederholungen bis zum oberen Ende steigern,
    dann Gewicht erhöhen und wieder unten anfangen."""
    sets = [s for s in last_sets if s.get("reps")]
    if not sets:
        return None
    top_weight = max((s.get("weight") or 0) for s in sets)
    top_sets = [s for s in sets if (s.get("weight") or 0) == top_weight]
    if all(s["reps"] >= rep_max for s in top_sets):
        return Suggestion(top_weight + increment, rep_min,
                          f"Alle Sätze mit {rep_max}+ Wdh. geschafft → {increment:g} kg mehr")
    best = max(s["reps"] for s in top_sets)
    target = min(max(best + 1, rep_min), rep_max)
    return Suggestion(top_weight, target, f"Gleiches Gewicht, Ziel {target} Wdh. pro Satz")


def last_sets(exercise_id: int, before: date | None = None) -> tuple[str | None, list[dict]]:
    """Sätze der letzten Einheit mit dieser Übung (optional vor einem Datum)."""
    params: list = [exercise_id]
    extra = ""
    if before:
        extra = " AND s.date < ?"
        params.append(before.isoformat())
    session = db.fetch_one(
        f"""SELECT s.id, s.date FROM strength_sessions s
            JOIN strength_sets st ON st.session_id = s.id
            WHERE st.exercise_id = ?{extra}
            ORDER BY s.date DESC, s.id DESC LIMIT 1""",
        params,
    )
    if not session:
        return None, []
    sets = db.fetch_all(
        "SELECT set_no, weight, reps, rpe FROM strength_sets WHERE session_id = ? AND exercise_id = ?"
        " ORDER BY set_no",
        (session["id"], exercise_id),
    )
    return session["date"], sets


def describe_sets(sets: list[dict]) -> str:
    """``[{weight: 80, reps: 10}, ...]`` → ``"80 kg × 10, 10, 9"``."""
    if not sets:
        return "–"
    parts: list[str] = []
    current_weight = object()
    for s in sets:
        weight = s.get("weight") or 0
        if weight != current_weight:
            label = f"{weight:g} kg" if weight else "Körpergewicht"
            parts.append(f"{label} × {s.get('reps') or 0}")
            current_weight = weight
        else:
            parts[-1] += f", {s.get('reps') or 0}"
    return " | ".join(parts)


# --------------------------------------------------------------------------- Tagebuch

def save_session(day: date, template_id: int | None, duration_min: int | None, rpe: float | None,
                 notes: str, sets: list[tuple[int, int, float | None, int, float | None]]) -> int:
    """``sets``: (exercise_id, set_no, weight, reps, rpe)."""
    with db.connect() as con:
        cur = con.execute(
            "INSERT INTO strength_sessions (date, template_id, duration_min, rpe, notes) VALUES (?, ?, ?, ?, ?)",
            (day.isoformat(), template_id, duration_min, rpe, notes or None),
        )
        session_id = cur.lastrowid
        con.executemany(
            "INSERT INTO strength_sets (session_id, exercise_id, set_no, weight, reps, rpe)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [(session_id, *s) for s in sets],
        )
    return session_id


def delete_session(session_id: int) -> None:
    db.execute("DELETE FROM strength_sessions WHERE id = ?", (session_id,))


def sessions_df(limit: int | None = None) -> pd.DataFrame:
    sql = """
        SELECT s.id, s.date, COALESCE(t.name, 'Freies Training') AS plan, s.duration_min, s.rpe, s.notes,
               COUNT(st.id) AS saetze,
               COALESCE(SUM(st.weight * st.reps), 0) AS volumen
        FROM strength_sessions s
        LEFT JOIN workout_templates t ON t.id = s.template_id
        LEFT JOIN strength_sets st ON st.session_id = s.id
        GROUP BY s.id ORDER BY s.date DESC, s.id DESC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    return db.query_df(sql)


def session_sets(session_id: int) -> pd.DataFrame:
    return db.query_df(
        """SELECT e.name AS uebung, st.set_no AS satz, st.weight AS gewicht, st.reps AS wdh, st.rpe
           FROM strength_sets st JOIN exercises e ON e.id = st.exercise_id
           WHERE st.session_id = ? ORDER BY st.id""",
        (session_id,),
    )


def exercise_history(exercise_id: int) -> pd.DataFrame:
    """Pro Einheit: bester e1RM, Topgewicht, Volumen."""
    df = db.query_df(
        """SELECT s.date, st.weight, st.reps FROM strength_sets st
           JOIN strength_sessions s ON s.id = st.session_id
           WHERE st.exercise_id = ? AND st.reps > 0 ORDER BY s.date""",
        (exercise_id,),
    )
    if df.empty:
        return pd.DataFrame(columns=["date", "e1rm", "top_weight", "volume", "sets", "best_reps"])
    df["e1rm"] = [e1rm(w, r) for w, r in zip(df["weight"], df["reps"])]
    df["volume"] = df["weight"].fillna(0) * df["reps"]
    out = df.groupby("date").agg(
        e1rm=("e1rm", "max"), top_weight=("weight", "max"), volume=("volume", "sum"),
        sets=("reps", "size"), best_reps=("reps", "max"),
    ).reset_index()
    out["date"] = pd.to_datetime(out["date"])
    return out


def sessions_in_week(day: date) -> int:
    monday = day - timedelta(days=day.weekday())
    row = db.fetch_one(
        "SELECT COUNT(*) AS n FROM strength_sessions WHERE date BETWEEN ? AND ?",
        (monday.isoformat(), (monday + timedelta(days=6)).isoformat()),
    )
    return int(row["n"]) if row else 0


# --------------------------------------------------------------------------- Pläne bearbeiten

def add_exercise(name: str, rep_min: int, rep_max: int, increment: float) -> int:
    existing = db.fetch_one("SELECT id FROM exercises WHERE name = ?", (name.strip(),))
    if existing:
        return existing["id"]
    return db.execute(
        "INSERT INTO exercises (name, rep_min, rep_max, increment_kg) VALUES (?, ?, ?, ?)",
        (name.strip(), rep_min, rep_max, increment),
    )


def update_exercise(exercise_id: int, rep_min: int, rep_max: int, increment: float) -> None:
    db.execute(
        "UPDATE exercises SET rep_min = ?, rep_max = ?, increment_kg = ? WHERE id = ?",
        (rep_min, rep_max, increment, exercise_id),
    )


def set_template_exercises(template_id: int, rows: list[tuple[int, int]]) -> None:
    """Ersetzt die Übungen eines Plans. ``rows``: (exercise_id, target_sets) in Reihenfolge."""
    with db.connect() as con:
        con.execute("DELETE FROM template_exercises WHERE template_id = ?", (template_id,))
        con.executemany(
            "INSERT INTO template_exercises (template_id, exercise_id, position, target_sets) VALUES (?, ?, ?, ?)",
            [(template_id, ex_id, pos, sets) for pos, (ex_id, sets) in enumerate(rows)],
        )


def add_template(name: str, lower_body: bool) -> int:
    row = db.fetch_one("SELECT COALESCE(MAX(position), -1) + 1 AS pos FROM workout_templates")
    return db.execute(
        "INSERT INTO workout_templates (name, position, lower_body) VALUES (?, ?, ?)",
        (name.strip(), row["pos"], int(lower_body)),
    )


def update_template(template_id: int, name: str, position: int, lower_body: bool) -> None:
    db.execute(
        "UPDATE workout_templates SET name = ?, position = ?, lower_body = ? WHERE id = ?",
        (name.strip(), position, int(lower_body), template_id),
    )


def delete_template(template_id: int) -> None:
    db.execute("DELETE FROM workout_templates WHERE id = ?", (template_id,))
