"""Hevy-Anbindung fürs Krafttraining (offizielle Hevy-API, braucht Hevy Pro).

Ablauf:
1. Pläne aus dem Dashboard werden als Routinen an Hevy geschickt – mit den
   Gewichtsvorschlägen der doppelten Progression (``strength.suggest``).
2. Im Gym trägst du Gewicht und Wiederholungen in der Hevy-App ein.
3. Beim Synchronisieren holt das Dashboard die Workouts und speichert sie in
   denselben Tabellen wie das manuelle Krafttagebuch. Verlauf, Fortschritt,
   Rotation und Belastung funktionieren dadurch ohne Extra-Code.

Der API-Key steht in Hevy unter Settings → Developer (https://hevy.com/settings?developer).
Dokumentation: https://api.hevyapp.com/docs/
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterator

import requests

from triathlon import db, settings, strength

BASE_URL = "https://api.hevyapp.com/v1"
TIMEOUT = 30
MAX_PAGES = 500           # Schutz gegen Endlosschleifen
REST_SECONDS = 90         # Pausentimer in Hevy
ROUTINE_NOTE = "Vom Triathlon-Dashboard erstellt – wird beim nächsten Senden überschrieben."

# Vorschläge für die Startübungen (seed.py) → mögliche Hevy-Namen. Der erste Name,
# den es in deiner Hevy-Übungsliste gibt, wird genommen. Alles andere ordnest du
# auf der Seite „Krafttraining → Hevy“ selbst zu.
DEFAULT_MAPPING: dict[str, list[str]] = {
    "Bankdrücken (Langhantel)": ["Bench Press (Barbell)"],
    "Schrägbankdrücken (Kurzhantel)": ["Incline Bench Press (Dumbbell)"],
    "Klimmzüge (Zusatzgewicht)": ["Pull Up (Weighted)", "Pull Up"],
    "Langhantelrudern": ["Bent Over Row (Barbell)"],
    "Latziehen": ["Lat Pulldown (Cable)", "Lat Pulldown (Machine)"],
    "Kabelrudern sitzend": ["Seated Cable Row - V Grip (Cable)", "Seated Cable Row - Bar Grip", "Seated Row (Machine)"],
    "Schulterdrücken (Kurzhantel)": ["Shoulder Press (Dumbbell)", "Seated Shoulder Press (Dumbbell)"],
    "Seitheben": ["Lateral Raise (Dumbbell)"],
    "Langhantel-Curls": ["Bicep Curl (Barbell)"],
    "Hammercurls": ["Hammer Curl (Dumbbell)"],
    "Trizepsdrücken am Kabel": ["Triceps Pushdown", "Triceps Rope Pushdown"],
    "French Press (SZ-Stange)": ["Skullcrusher (Barbell)", "Skullcrusher (Dumbbell)"],
    "Kniebeugen": ["Squat (Barbell)"],
    "Rumänisches Kreuzheben": ["Romanian Deadlift (Barbell)"],
    "Beinpresse": ["Leg Press (Machine)"],
    "Ausfallschritte (Kurzhantel)": ["Lunge (Dumbbell)", "Walking Lunge (Dumbbell)"],
    "Beinbeuger": ["Seated Leg Curl (Machine)", "Lying Leg Curl (Machine)"],
    "Wadenheben": ["Standing Calf Raise (Machine)", "Calf Press (Machine)", "Seated Calf Raise"],
}


class HevyError(Exception):
    pass


class HevyNotFound(HevyError):
    pass


# --------------------------------------------------------------------------- HTTP

def is_configured() -> bool:
    return bool(settings.get("hevy_api_key"))


def _request(method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict:
    key = (settings.get("hevy_api_key") or "").strip()
    if not key:
        raise HevyError("Kein Hevy-API-Key eingetragen.")
    try:
        response = requests.request(
            method, f"{BASE_URL}{path}", params=params, json=body, timeout=TIMEOUT,
            headers={"api-key": key, "accept": "application/json"},
        )
    except requests.RequestException as exc:
        raise HevyError(f"Hevy nicht erreichbar: {exc}") from exc

    status = response.status_code
    if status in (200, 201, 204):
        if not response.content:
            return {}
        try:
            data = response.json()
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {"data": data}
    text = (response.text or "")[:300]
    if status == 401:
        raise HevyError("Hevy lehnt den API-Key ab – bitte in den Einstellungen prüfen.")
    if status == 403:
        if "routine-limit" in text:
            raise HevyError("Hevy-Limit erreicht: Gratis-Konten dürfen höchstens 4 Routinen haben.")
        raise HevyError("Hevy verweigert den Zugriff. Die Hevy-API funktioniert nur mit Hevy Pro – "
                        f"Abo und API-Key prüfen. ({text})")
    if status == 404:
        raise HevyNotFound(f"Nicht gefunden: {path}")
    if status == 429:
        raise HevyError("Zu viele Anfragen an Hevy – bitte eine Minute warten und erneut versuchen.")
    raise HevyError(f"Hevy-Fehler {status}: {text}")


def _paginate(path: str, key: str, page_size: int, params: dict | None = None) -> Iterator[dict]:
    """Geht alle Seiten einer Liste durch (Hevy liefert höchstens 10 bzw. 100 Einträge pro Seite)."""
    for page in range(1, MAX_PAGES + 1):
        try:
            data = _request("GET", path, params={**(params or {}), "page": page, "pageSize": page_size})
        except HevyNotFound:
            return  # Seite hinter dem Ende oder noch gar keine Einträge
        yield from data.get(key) or []
        if page >= int(data.get("page_count") or 1):
            return
    raise HevyError(f"Zu viele Seiten bei {path} – Abgleich abgebrochen.")


def test_connection() -> str:
    info = _request("GET", "/user/info").get("data") or {}
    name = info.get("name") or info.get("username") or "OK"
    if info.get("is_pro") is False:
        return f"{name} (Achtung: laut Hevy kein Pro-Abo aktiv)"
    return name


# --------------------------------------------------------------------------- Übungen zuordnen

def sync_exercise_templates() -> int:
    """Lädt die komplette Hevy-Übungsliste (inkl. eigener Übungen) in den Zwischenspeicher."""
    rows = []
    for t in _paginate("/exercise_templates", "exercise_templates", 100):
        if not t.get("id") or not t.get("title"):
            continue
        rows.append((t["id"], t["title"], t.get("type"), t.get("primary_muscle_group"),
                     t.get("equipment"), int(bool(t.get("is_custom")))))
    if rows:
        db.executemany(
            "INSERT INTO hevy_exercise_templates (id, title, type, primary_muscle_group, equipment, is_custom)"
            " VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET title = excluded.title, type = excluded.type,"
            " primary_muscle_group = excluded.primary_muscle_group, equipment = excluded.equipment,"
            " is_custom = excluded.is_custom",
            rows,
        )
    return len(rows)


def exercise_templates() -> list[dict]:
    return db.fetch_all("SELECT * FROM hevy_exercise_templates ORDER BY title, is_custom, id")


def template_labels() -> dict[str, str]:
    """Anzeigename → Hevy-ID, eindeutig (doppelte Namen bekommen einen Zusatz)."""
    labels: dict[str, str] = {}
    for t in exercise_templates():
        label = t["title"] + (" (eigene)" if t["is_custom"] else "")
        if label in labels:
            label = f"{label} [{t['id']}]"
        labels[label] = t["id"]
    return labels


def auto_map_exercises() -> int:
    """Ordnet eigene Übungen ohne Zuordnung automatisch zu (gleicher Name oder Vorschlagsliste)."""
    by_title: dict[str, str] = {}
    for t in exercise_templates():
        by_title.setdefault(t["title"].strip().lower(), t["id"])
    if not by_title:
        return 0
    mapped = 0
    for ex in db.fetch_all("SELECT id, name FROM exercises WHERE hevy_template_id IS NULL AND from_hevy = 0"):
        candidates = [ex["name"], *DEFAULT_MAPPING.get(ex["name"], [])]
        for title in candidates:
            template_id = by_title.get(title.strip().lower())
            if template_id:
                set_mapping(ex["id"], template_id)
                mapped += 1
                break
    return mapped


def set_mapping(exercise_id: int, template_id: str | None) -> None:
    """Ordnet eine eigene Übung einer Hevy-Übung zu (``None`` = Zuordnung entfernen).

    Gab es für diese Hevy-Übung schon eine beim Import automatisch angelegte Übung,
    werden deren Sätze übernommen – so entsteht kein doppelter Verlauf."""
    with db.connect() as con:
        con.execute("UPDATE exercises SET hevy_template_id = ? WHERE id = ?", (template_id, exercise_id))
        if not template_id:
            return
        others = con.execute(
            "SELECT id, from_hevy FROM exercises WHERE hevy_template_id = ? AND id != ?",
            (template_id, exercise_id),
        ).fetchall()
        for other in others:
            if not other["from_hevy"]:
                continue  # eigene Übung des Nutzers – nicht anfassen
            con.execute("UPDATE strength_sets SET exercise_id = ? WHERE exercise_id = ?", (exercise_id, other["id"]))
            in_plan = con.execute("SELECT 1 FROM template_exercises WHERE exercise_id = ? LIMIT 1",
                                  (other["id"],)).fetchone()
            if in_plan:
                con.execute("UPDATE exercises SET hevy_template_id = NULL WHERE id = ?", (other["id"],))
            else:
                con.execute("DELETE FROM exercises WHERE id = ?", (other["id"],))


def mapping_table() -> list[dict]:
    """Eigene Übungen (nicht aus Hevy importiert) mit ihrer Zuordnung."""
    return db.fetch_all(
        """SELECT e.id, e.name, e.hevy_template_id, t.title AS hevy_title,
                  EXISTS(SELECT 1 FROM template_exercises te WHERE te.exercise_id = e.id) AS in_plan
           FROM exercises e LEFT JOIN hevy_exercise_templates t ON t.id = e.hevy_template_id
           WHERE e.from_hevy = 0 ORDER BY in_plan DESC, e.name"""
    )


# --------------------------------------------------------------------------- Workouts importieren

def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _local_date(value: str | None) -> date | None:
    parsed = _parse_time(value)
    return parsed.astimezone().date() if parsed else None


def _exercise_id(con: sqlite3.Connection, template_id: str | None, title: str) -> int:
    """Passende Übung im Dashboard finden – oder neu anlegen."""
    title = (title or "Unbekannte Übung").strip()
    if template_id:
        row = con.execute("SELECT id FROM exercises WHERE hevy_template_id = ? ORDER BY from_hevy, id LIMIT 1",
                          (template_id,)).fetchone()
        if row:
            return row["id"]
    row = con.execute("SELECT id, hevy_template_id FROM exercises WHERE lower(name) = lower(?) ORDER BY id LIMIT 1",
                      (title,)).fetchone()
    if row:
        if template_id and not row["hevy_template_id"]:
            con.execute("UPDATE exercises SET hevy_template_id = ? WHERE id = ?", (template_id, row["id"]))
        return row["id"]
    try:
        cur = con.execute(
            "INSERT INTO exercises (name, rep_min, rep_max, increment_kg, hevy_template_id, from_hevy)"
            " VALUES (?, 8, 12, 2.5, ?, 1)",
            (title, template_id),
        )
        return cur.lastrowid
    except sqlite3.IntegrityError:  # gleicher Name mit anderer Schreibweise (z. B. Umlaute)
        return con.execute("SELECT id FROM exercises WHERE name = ?", (title,)).fetchone()["id"]


def _plan_id(con: sqlite3.Connection, routine_id: str | None, title: str | None) -> int | None:
    """Welcher Dashboard-Plan gehört zu diesem Workout? Erst über die Routine, dann über den Namen."""
    if routine_id:
        row = con.execute("SELECT id FROM workout_templates WHERE hevy_routine_id = ?", (routine_id,)).fetchone()
        if row:
            return row["id"]
    if title:
        row = con.execute("SELECT id FROM workout_templates WHERE lower(name) = lower(?)",
                          (title.strip(),)).fetchone()
        if row:
            return row["id"]
    return None


def _sets_of(con: sqlite3.Connection, workout: dict) -> list[tuple[int, int, float | None, int, float | None]]:
    """Hevy-Übungen → (exercise_id, set_no, weight, reps, rpe). Aufwärmsätze und Sätze ohne
    Wiederholungen (z. B. Plank auf Zeit, Cardio) werden nicht übernommen."""
    rows = []
    exercises = sorted(workout.get("exercises") or [], key=lambda e: e.get("index") or 0)
    for ex in exercises:
        valid = []
        for s in sorted(ex.get("sets") or [], key=lambda s: s.get("index") or 0):
            reps = s.get("reps")
            if s.get("type") == "warmup" or reps is None or reps <= 0:
                continue
            valid.append(s)
        if not valid:
            continue
        exercise_id = _exercise_id(con, ex.get("exercise_template_id"), ex.get("title") or "")
        start = 1 + max((r[1] for r in rows if r[0] == exercise_id), default=0)  # Übung doppelt im Workout
        for n, s in enumerate(valid):
            weight = s.get("weight_kg")
            rows.append((exercise_id, start + n, float(weight) if weight is not None else None,
                         int(round(s["reps"])), float(s["rpe"]) if s.get("rpe") is not None else None))
    return rows


def store_workout(workout: dict) -> bool:
    """Speichert ein Hevy-Workout (neu oder aktualisiert). Gibt False zurück, wenn es unbrauchbar ist."""
    hevy_id = workout.get("id")
    day = _local_date(workout.get("start_time"))
    if not hevy_id or not day:
        return False
    start, end = _parse_time(workout.get("start_time")), _parse_time(workout.get("end_time"))
    duration = round((end - start).total_seconds() / 60) if start and end and end > start else None
    notes = (workout.get("description") or "").strip() or None

    with db.connect() as con:
        plan_id = _plan_id(con, workout.get("routine_id"), workout.get("title"))
        sets = _sets_of(con, workout)
        existing = con.execute("SELECT id FROM strength_sessions WHERE hevy_id = ?", (hevy_id,)).fetchone()
        if existing:
            session_id = existing["id"]
            con.execute(
                "UPDATE strength_sessions SET date = ?, template_id = ?, duration_min = ?, notes = ? WHERE id = ?",
                (day.isoformat(), plan_id, duration, notes, session_id),
            )
            con.execute("DELETE FROM strength_sets WHERE session_id = ?", (session_id,))
        else:
            session_id = con.execute(
                "INSERT INTO strength_sessions (date, template_id, duration_min, rpe, notes, hevy_id)"
                " VALUES (?, ?, ?, NULL, ?, ?)",
                (day.isoformat(), plan_id, duration, notes, hevy_id),
            ).lastrowid
        con.executemany(
            "INSERT INTO strength_sets (session_id, exercise_id, set_no, weight, reps, rpe) VALUES (?, ?, ?, ?, ?, ?)",
            [(session_id, *s) for s in sets],
        )
    return True


def delete_workout(hevy_id: str) -> None:
    db.execute("DELETE FROM strength_sessions WHERE hevy_id = ?", (hevy_id,))


def _utc_stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sync_workouts(full: bool = False) -> int:
    """Holt Workouts aus Hevy. Beim ersten Mal (oder ``full``) alle, danach nur Änderungen
    und Löschungen seit dem letzten Abgleich. Gibt die Zahl der gespeicherten Workouts zurück."""
    started = datetime.now(timezone.utc)
    since = None if full else settings.get("hevy_last_sync")
    stored = 0
    if since:
        for event in _paginate("/workouts/events", "events", 10, {"since": since}):
            if event.get("type") == "deleted" and event.get("id"):
                delete_workout(event["id"])
            elif event.get("type") == "updated" and event.get("workout"):
                stored += store_workout(event["workout"])
    else:
        seen: set[str] = set()
        for workout in _paginate("/workouts", "workouts", 10):
            if store_workout(workout):
                stored += 1
                seen.add(workout["id"])
        # In Hevy gelöschte Workouts auch hier entfernen
        for row in db.fetch_all("SELECT hevy_id FROM strength_sessions WHERE hevy_id IS NOT NULL"):
            if row["hevy_id"] not in seen:
                delete_workout(row["hevy_id"])
    # 5 Minuten Puffer: Workouts, die genau während des Abgleichs gespeichert werden, nicht verpassen
    settings.set("hevy_last_sync", _utc_stamp(started - timedelta(minutes=5)))
    return stored


# --------------------------------------------------------------------------- Pläne als Routinen senden

def _routine_exercises(plan_id: int, for_update: bool) -> tuple[list[dict], list[str]]:
    """Übungen eines Plans im Hevy-Format, mit Gewichtsvorschlag. Gibt auch die
    Namen der Übungen ohne Hevy-Zuordnung zurück."""
    exercises, unmapped = [], []
    for ex in strength.template_exercises(plan_id):
        if not ex.get("hevy_template_id"):
            unmapped.append(ex["name"])
            continue
        _, last = strength.last_sets(ex["id"])
        sug = strength.suggest(ex["rep_min"], ex["rep_max"], ex["increment_kg"], last)
        target = f"Ziel {ex['rep_min']}–{ex['rep_max']} Wdh."
        note = (f"{target} · Vorschlag {sug.weight:g} kg × {sug.reps} ({sug.note})" if sug
                else f"{target} · Noch kein Verlauf – Gewicht selbst wählen.")
        one_set: dict[str, Any] = {
            "type": "normal",
            "weight_kg": sug.weight if sug and sug.weight else None,
            "reps": sug.reps if sug else ex["rep_min"],
            "distance_meters": None,
            "duration_seconds": None,
            "custom_metric": None,
        }
        if not for_update:
            one_set["rep_range"] = None
        exercises.append({
            "exercise_template_id": ex["hevy_template_id"],
            "superset_id": None,
            "rest_seconds": REST_SECONDS,
            "notes": note,
            "sets": [dict(one_set) for _ in range(int(ex["target_sets"] or 3))],
        })
    return exercises, unmapped


def _routine_id_from(response: dict) -> str | None:
    routine = response.get("routine")
    if isinstance(routine, list):
        routine = routine[0] if routine else None
    if isinstance(routine, dict) and routine.get("id"):
        return str(routine["id"])
    return None


def _find_routine_by_title(title: str) -> str | None:
    matches = [r for r in _paginate("/routines", "routines", 10) if (r.get("title") or "").strip() == title.strip()]
    if not matches:
        return None
    matches.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return matches[0].get("id")


def push_routine(plan: dict) -> tuple[bool, str]:
    """Legt den Plan in Hevy als Routine an oder aktualisiert ihn."""
    routine_id = plan.get("hevy_routine_id")
    exercises, unmapped = _routine_exercises(plan["id"], for_update=bool(routine_id))
    hint = f" Ohne Hevy-Zuordnung übersprungen: {', '.join(unmapped)}." if unmapped else ""
    if not exercises:
        return False, "Keine Übung ist einer Hevy-Übung zugeordnet." + hint

    if routine_id:
        body = {"routine": {"title": plan["name"], "notes": ROUTINE_NOTE, "exercises": exercises}}
        try:
            _request("PUT", f"/routines/{routine_id}", body=body)
            return True, "aktualisiert." + hint
        except HevyNotFound:
            routine_id = None  # in Hevy gelöscht → neu anlegen
            exercises, _ = _routine_exercises(plan["id"], for_update=False)

    body = {"routine": {"title": plan["name"], "folder_id": None, "notes": ROUTINE_NOTE, "exercises": exercises}}
    response = _request("POST", "/routines", body=body)
    new_id = _routine_id_from(response) or _find_routine_by_title(plan["name"])
    if not new_id:
        return True, "in Hevy angelegt, aber die Routine-ID kam nicht zurück – Routine in Hevy prüfen." + hint
    db.execute("UPDATE workout_templates SET hevy_routine_id = ? WHERE id = ?", (new_id, plan["id"]))
    return True, "in Hevy angelegt." + hint


def push_routines(only_linked: bool = False) -> list[tuple[str, bool, str]]:
    """Alle Pläne senden. ``only_linked``: nur Pläne, die schon einmal gesendet wurden."""
    results = []
    for plan in strength.templates():
        if only_linked and not plan.get("hevy_routine_id"):
            continue
        try:
            ok, message = push_routine(plan)
        except HevyError as exc:
            ok, message = False, str(exc)
        results.append((plan["name"], ok, message))
    return results


def disconnect() -> None:
    """API-Key löschen. Importierte Workouts bleiben erhalten."""
    settings.set_many({"hevy_api_key": "", "hevy_last_sync": None})
