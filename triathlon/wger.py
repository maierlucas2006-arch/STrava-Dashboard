"""wger-Anbindung fürs Krafttraining – kostenlos und Open Source (https://wger.de).

Ablauf:
1. Eigene Übungen einmalig wger-Übungen zuordnen.
2. Pläne als Routine an wger schicken – mit Gewichts- und Wiederholungsvorschlägen
   der doppelten Progression (``strength.suggest``).
3. Im Gym in der wger-App (iPhone/Android) den Trainingstag starten und Sätze eintragen.
4. Beim Synchronisieren holt das Dashboard die Sätze und speichert sie in denselben
   Tabellen wie das Krafttagebuch. Verlauf, Fortschritt, Rotation und Belastung
   funktionieren dadurch ohne Extra-Code. Danach bekommt die Routine neue Vorschläge.

Zugang über den persönlichen API-Key (wger.de → Profil → API-Key), Header ``Authorization: Token …``.
"""
from __future__ import annotations

import difflib
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterator

import requests

from triathlon import db, settings, strength

DEFAULT_URL = "https://wger.de"
TIMEOUT = 30
PAGE_LIMIT = 999            # Höchstwert der wger-API pro Seite
MAX_PAGES = 200
LANG_DE, LANG_EN = 1, 2
REP_UNITS = {1, 2, 7}       # Wiederholungen, bis Muskelversagen, max. Wiederholungen
WEIGHT_UNIT_LB = 2
LB_TO_KG = 0.45359237
ROUTINE_NAME = "Triathlon-Kraft"
ROUTINE_DAYS = 119          # wger erlaubt höchstens 120 Tage pro Routine
REST_SECONDS = 90
MAX_SESSION_MINUTES = 300   # längere Sessions wurden vermutlich nicht beendet

# Vorschläge für die Startübungen (seed.py) → mögliche Namen in wger (deutsch oder englisch).
# Genommen wird der erste Name, den es in der wger-Übungsliste gibt; der Rest wird
# über ähnliche Namen gesucht oder in der Tabelle selbst zugeordnet.
DEFAULT_NAMES: dict[str, list[str]] = {
    "Bankdrücken (Langhantel)": ["Bankdrücken", "Bankdrücken LH", "Bench Press"],
    "Schrägbankdrücken (Kurzhantel)": ["Schrägbankdrücken Kurzhantel", "Schrägbankdrücken KH",
                                       "Incline Dumbbell Press", "Incline Bench Press - Dumbbell"],
    "Klimmzüge (Zusatzgewicht)": ["Klimmzüge", "Klimmzug", "Pull-ups", "Pull Ups", "Chin-ups"],
    "Langhantelrudern": ["Langhantelrudern", "Rudern vorgebeugt", "Bent Over Rowing", "Barbell Row"],
    "Latziehen": ["Latziehen", "Latzug", "Lat Pulldown", "Lat Pull Down"],
    "Kabelrudern sitzend": ["Rudern am Kabel", "Kabelrudern", "Seated Cable Row", "Seated Row"],
    "Schulterdrücken (Kurzhantel)": ["Schulterdrücken Kurzhantel", "Schulterdrücken", "Shoulder Press, Dumbbells",
                                     "Dumbbell Shoulder Press"],
    "Seitheben": ["Seitheben", "Seitheben Kurzhantel", "Lateral Raises"],
    "Langhantel-Curls": ["Bizepscurls mit der Langhantel", "Langhantelcurls", "Bizeps Curls Langhantel",
                         "Biceps Curls With Barbell", "Barbell Curl"],
    "Hammercurls": ["Hammercurls", "Hammer Curls"],
    "Trizepsdrücken am Kabel": ["Trizepsdrücken", "Trizepsdrücken am Kabel", "Triceps Pushdown",
                                "Triceps Pushdown Rope"],
    "French Press (SZ-Stange)": ["French Press", "French Press (Skull Crusher) SZ-bar", "Skull Crusher",
                                 "French Press (skullcrusher) SZ-bar"],
    "Kniebeugen": ["Kniebeuge", "Kniebeugen", "Squats", "Barbell Squat"],
    "Rumänisches Kreuzheben": ["Rumänisches Kreuzheben", "Romanian Deadlift"],
    "Beinpresse": ["Beinpresse", "Leg Press"],
    "Ausfallschritte (Kurzhantel)": ["Ausfallschritte", "Ausfallschritte Kurzhantel", "Dumbbell Lunges",
                                     "Lunges"],
    "Beinbeuger": ["Beinbeuger", "Beinbeuger liegend", "Leg Curls (laying)", "Leg Curl", "Lying Leg Curl"],
    "Wadenheben": ["Wadenheben", "Wadenheben stehend", "Standing Calf Raises", "Calf Raises"],
}


class WgerError(Exception):
    pass


class WgerNotFound(WgerError):
    pass


# --------------------------------------------------------------------------- HTTP

def is_configured() -> bool:
    return bool(settings.get("wger_api_key"))


def base_url() -> str:
    return (settings.get("wger_url") or DEFAULT_URL).strip().rstrip("/") or DEFAULT_URL


def _request(method: str, path: str, params: dict | None = None, body: dict | None = None) -> Any:
    key = (settings.get("wger_api_key") or "").strip()
    if not key:
        raise WgerError("Kein wger-API-Key eingetragen.")
    url = f"{base_url()}/api/v2/{path.lstrip('/')}"
    try:
        response = requests.request(
            method, url, params=params, json=body, timeout=TIMEOUT,
            headers={"Authorization": f"Token {key}", "Accept": "application/json"},
        )
    except requests.RequestException as exc:
        raise WgerError(f"wger nicht erreichbar: {exc}") from exc

    status = response.status_code
    if status in (200, 201, 204):
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {}
    text = (response.text or "")[:300]
    if status in (401, 403):
        raise WgerError("wger lehnt den Zugriff ab – bitte den API-Key in den Einstellungen prüfen.")
    if status == 404:
        raise WgerNotFound(f"Nicht gefunden: {path}")
    if status == 429:
        raise WgerError("Zu viele Anfragen an wger – bitte eine Minute warten und erneut versuchen.")
    if status == 400:
        raise WgerError(f"wger hat die Anfrage abgelehnt: {text}")
    raise WgerError(f"wger-Fehler {status}: {text}")


def _paginate(path: str, params: dict | None = None) -> Iterator[dict]:
    """Geht alle Seiten einer Liste durch (``limit``/``offset``, Antwort mit ``results`` und ``next``)."""
    offset = 0
    for _ in range(MAX_PAGES):
        data = _request("GET", path, params={**(params or {}), "limit": PAGE_LIMIT, "offset": offset})
        results = data.get("results") if isinstance(data, dict) else None
        if not results:
            return
        yield from results
        if not data.get("next"):
            return
        offset += len(results)
    raise WgerError(f"Zu viele Seiten bei {path} – Abgleich abgebrochen.")


def test_connection() -> str:
    profile = _request("GET", "userprofile/")
    return (profile.get("username") if isinstance(profile, dict) else None) or "OK"


def _number(value: Any) -> float | None:
    """wger liefert Dezimalzahlen als Text (``"82.50"``)."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _local_date(moment: datetime) -> date:
    return moment.astimezone().date()


# --------------------------------------------------------------------------- Übungsliste & Zuordnung

def _norm(text: str) -> str:
    text = (text or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(a, b)
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _store_catalog(names: dict[int, dict[str, str]]) -> None:
    rows = []
    for ex_id, n in names.items():
        de, en = n.get("de"), n.get("en")
        rows.append((ex_id, de or en, de, en))
    if rows:
        db.executemany(
            "INSERT INTO wger_exercises (id, name, name_de, name_en) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET name = excluded.name,"
            " name_de = COALESCE(excluded.name_de, wger_exercises.name_de),"
            " name_en = COALESCE(excluded.name_en, wger_exercises.name_en)",
            rows,
        )


def sync_exercise_catalog() -> int:
    """Lädt alle wger-Übungen mit deutschem und englischem Namen in den Zwischenspeicher."""
    names: dict[int, dict[str, str]] = {}
    for lang, code in ((LANG_DE, "de"), (LANG_EN, "en")):
        for t in _paginate("exercise-translation/", {"language": lang}):
            ex_id, name = t.get("exercise"), (t.get("name") or "").strip()
            if ex_id and name:
                names.setdefault(int(ex_id), {}).setdefault(code, name)
    _store_catalog(names)
    return len(names)


def _fetch_exercise_name(ex_id: int) -> None:
    """Name einer einzelnen Übung nachladen (z. B. wenn sie noch nicht in der Liste ist)."""
    found: dict[str, str] = {}
    for t in _paginate("exercise-translation/", {"exercise": ex_id}):
        name = (t.get("name") or "").strip()
        if not name:
            continue
        code = {LANG_DE: "de", LANG_EN: "en"}.get(t.get("language"), "xx")
        found.setdefault(code, name)
    if not found:
        found["de"] = f"wger-Übung {ex_id}"
    if "de" not in found and "en" not in found:
        found["en"] = next(iter(found.values()))
    _store_catalog({ex_id: found})


def exercise_catalog() -> list[dict]:
    return db.fetch_all("SELECT * FROM wger_exercises ORDER BY name, id")


def exercise_labels() -> dict[str, int]:
    """Anzeigename → wger-ID, eindeutig (doppelte Namen bekommen die ID als Zusatz)."""
    labels: dict[str, int] = {}
    for row in exercise_catalog():
        label = row["name"]
        if row["name_de"] and row["name_en"] and row["name_en"] != row["name_de"]:
            label = f"{row['name_de']} ({row['name_en']})"
        if label in labels:
            label = f"{label} [{row['id']}]"
        labels[label] = row["id"]
    return labels


def auto_map_exercises() -> int:
    """Ordnet eigene Übungen ohne Zuordnung zu: erst exakter Name (auch Vorschlagsliste),
    dann sehr ähnlicher Name. Bestehende Zuordnungen bleiben unverändert."""
    index: dict[str, int] = {}
    for row in exercise_catalog():
        for name in (row["name_de"], row["name_en"]):
            if name:
                index.setdefault(_norm(name), row["id"])
    if not index:
        return 0
    used = {r["wger_exercise_id"] for r in
            db.fetch_all("SELECT wger_exercise_id FROM exercises WHERE wger_exercise_id IS NOT NULL")}
    mapped = 0
    for ex in db.fetch_all("SELECT id, name FROM exercises WHERE wger_exercise_id IS NULL"
                           " AND from_wger = 0 AND from_hevy = 0"):
        target = None
        for candidate in [ex["name"], *DEFAULT_NAMES.get(ex["name"], [])]:
            target = index.get(_norm(candidate))
            if target:
                break
        if not target:
            close = difflib.get_close_matches(_norm(ex["name"]), list(index), n=1, cutoff=0.88)
            target = index[close[0]] if close else None
        if target and target not in used:
            set_mapping(ex["id"], target)
            used.add(target)
            mapped += 1
    return mapped


def set_mapping(exercise_id: int, wger_id: int | None) -> None:
    """Ordnet eine eigene Übung einer wger-Übung zu (``None`` = Zuordnung entfernen).

    Gab es für diese wger-Übung schon eine beim Import angelegte Übung, werden deren
    Sätze übernommen – so entsteht kein doppelter Verlauf."""
    with db.connect() as con:
        con.execute("UPDATE exercises SET wger_exercise_id = ? WHERE id = ?", (wger_id, exercise_id))
        if wger_id is None:
            return
        others = con.execute(
            "SELECT id, from_wger FROM exercises WHERE wger_exercise_id = ? AND id != ?", (wger_id, exercise_id)
        ).fetchall()
        for other in others:
            if not other["from_wger"]:
                continue  # eigene Übung – nicht anfassen
            con.execute("UPDATE strength_sets SET exercise_id = ? WHERE exercise_id = ?", (exercise_id, other["id"]))
            in_plan = con.execute("SELECT 1 FROM template_exercises WHERE exercise_id = ? LIMIT 1",
                                  (other["id"],)).fetchone()
            if in_plan:
                con.execute("UPDATE exercises SET wger_exercise_id = NULL WHERE id = ?", (other["id"],))
            else:
                con.execute("DELETE FROM exercises WHERE id = ?", (other["id"],))


def mapping_table() -> list[dict]:
    """Eigene Übungen (nicht aus einer App importiert) mit ihrer Zuordnung."""
    return db.fetch_all(
        """SELECT e.id, e.name, e.wger_exercise_id,
                  EXISTS(SELECT 1 FROM template_exercises te WHERE te.exercise_id = e.id) AS in_plan
           FROM exercises e
           WHERE e.from_wger = 0 AND e.from_hevy = 0 ORDER BY in_plan DESC, e.name"""
    )


# --------------------------------------------------------------------------- Einheiten importieren

def _exercise_id(con: sqlite3.Connection, wger_id: int) -> int:
    """Passende Übung im Dashboard finden – oder neu anlegen."""
    row = con.execute("SELECT id FROM exercises WHERE wger_exercise_id = ? ORDER BY from_wger, id LIMIT 1",
                      (wger_id,)).fetchone()
    if row:
        return row["id"]
    cat = con.execute("SELECT name FROM wger_exercises WHERE id = ?", (wger_id,)).fetchone()
    name = (cat["name"] if cat else None) or f"wger-Übung {wger_id}"
    row = con.execute("SELECT id, wger_exercise_id FROM exercises WHERE lower(name) = lower(?) ORDER BY id LIMIT 1",
                      (name,)).fetchone()
    if row:
        if not row["wger_exercise_id"]:
            con.execute("UPDATE exercises SET wger_exercise_id = ? WHERE id = ?", (wger_id, row["id"]))
        return row["id"]
    try:
        return con.execute(
            "INSERT INTO exercises (name, rep_min, rep_max, increment_kg, wger_exercise_id, from_wger)"
            " VALUES (?, 8, 12, 2.5, ?, 1)",
            (name, wger_id),
        ).lastrowid
    except sqlite3.IntegrityError:  # gleicher Name in anderer Schreibweise
        return con.execute("SELECT id FROM exercises WHERE name = ?", (name,)).fetchone()["id"]


def _plan_id(con: sqlite3.Connection, day_id: Any, day_names: dict) -> int | None:
    if day_id is None:
        return None
    row = con.execute("SELECT id FROM workout_templates WHERE wger_day_id = ?", (day_id,)).fetchone()
    if row:
        return row["id"]
    name = (day_names.get(day_id) or "").strip().casefold()
    if name:
        for plan in con.execute("SELECT id, name FROM workout_templates ORDER BY position, id"):
            if plan["name"].strip().casefold() == name:
                return plan["id"]
    return None


def _sets_of(con: sqlite3.Connection, logs: list[dict]) -> list[tuple[int, int, float | None, int, float | None]]:
    """wger-Sätze → (exercise_id, set_no, weight, reps, rpe). Sätze auf Zeit oder Strecke werden
    nicht übernommen, Pfund in kg umgerechnet, RIR in RPE (10 − RIR)."""
    rows: list[tuple[int, int, float | None, int, float | None]] = []
    counters: dict[int, int] = {}
    for log in logs:
        unit = log.get("repetitions_unit")
        if unit is not None and int(unit) not in REP_UNITS:
            continue
        reps = _number(log.get("repetitions"))
        if reps is None or reps <= 0 or not log.get("exercise"):
            continue
        weight = _number(log.get("weight"))
        if weight is not None and log.get("weight_unit") == WEIGHT_UNIT_LB:
            weight = round(weight * LB_TO_KG, 2)
        rir = _number(log.get("rir"))
        rpe = round(10 - rir, 1) if rir is not None else None
        exercise_id = _exercise_id(con, int(log["exercise"]))
        counters[exercise_id] = counters.get(exercise_id, 0) + 1
        rows.append((exercise_id, counters[exercise_id], weight, int(round(reps)), rpe))
    return rows


def _store_group(key: str, logs: list[dict], session: dict | None, day_names: dict) -> bool:
    logs = sorted(logs, key=lambda l: (str(l.get("date") or ""), str(l.get("id") or "")))
    start = _parse_time(session.get("datetime_start")) if session else None
    start = start or _parse_time(logs[0].get("date"))
    if start is None:
        return False
    end = _parse_time(session.get("datetime_end")) if session else None
    duration = None
    if end and end > start:
        minutes = round((end - start).total_seconds() / 60)
        duration = minutes if minutes <= MAX_SESSION_MINUTES else None
    notes = ((session or {}).get("notes") or "").strip() or None

    with db.connect() as con:
        sets = _sets_of(con, logs)
        if not sets:
            return False
        plan_id = _plan_id(con, (session or {}).get("day"), day_names)
        existing = con.execute("SELECT id FROM strength_sessions WHERE wger_id = ?", (key,)).fetchone()
        if existing:
            session_id = existing["id"]
            con.execute(
                "UPDATE strength_sessions SET date = ?, template_id = COALESCE(?, template_id), duration_min = ?,"
                " notes = ? WHERE id = ?",
                (_local_date(start).isoformat(), plan_id, duration, notes, session_id),
            )
            con.execute("DELETE FROM strength_sets WHERE session_id = ?", (session_id,))
        else:
            session_id = con.execute(
                "INSERT INTO strength_sessions (date, template_id, duration_min, rpe, notes, wger_id)"
                " VALUES (?, ?, ?, NULL, ?, ?)",
                (_local_date(start).isoformat(), plan_id, duration, notes, key),
            ).lastrowid
        con.executemany(
            "INSERT INTO strength_sets (session_id, exercise_id, set_no, weight, reps, rpe) VALUES (?, ?, ?, ?, ?, ?)",
            [(session_id, *s) for s in sets],
        )
    return True


def sync_workouts(full: bool = False) -> int:
    """Holt alle Sätze im Historienzeitraum aus wger und gleicht die Einheiten ab
    (neu, geändert, gelöscht). ``full`` ist für die gleiche Bedienung wie bei Hevy da –
    wger wird immer vollständig für den Zeitraum abgeglichen."""
    days_back = int(settings.get("history_days") or 365)
    since = date.today() - timedelta(days=days_back)
    logs = list(_paginate("workoutlog/", {"date__gte": since.isoformat(), "ordering": "date"}))
    sessions = {str(s["id"]): s for s in _paginate("workoutsession/", {}) if s.get("id")}
    day_names = {d["id"]: d.get("name") or "" for d in _paginate("day/", {}) if d.get("id") is not None}

    def missing() -> set[int]:
        known = {r["id"] for r in db.fetch_all("SELECT id FROM wger_exercises")}
        mapped = {r["wger_exercise_id"] for r in
                  db.fetch_all("SELECT wger_exercise_id FROM exercises WHERE wger_exercise_id IS NOT NULL")}
        return {int(l["exercise"]) for l in logs if l.get("exercise")} - known - mapped

    if missing() and not db.fetch_one("SELECT 1 FROM wger_exercises LIMIT 1"):
        sync_exercise_catalog()  # zwei Anfragen statt einer pro Übung
    for ex_id in sorted(missing()):
        _fetch_exercise_name(ex_id)

    groups: dict[str, list[dict]] = {}
    for log in logs:
        moment = _parse_time(log.get("date"))
        if moment is None:
            continue
        key = str(log["session"]) if log.get("session") else f"d:{_local_date(moment)}:{log.get('routine') or ''}"
        groups.setdefault(key, []).append(log)

    stored = set()
    for key, items in groups.items():
        if _store_group(key, items, sessions.get(key), day_names):
            stored.add(key)

    # In wger gelöschte Einheiten auch hier entfernen (nur im abgeglichenen Zeitraum)
    for row in db.fetch_all("SELECT id, wger_id FROM strength_sessions WHERE wger_id IS NOT NULL AND date >= ?",
                            (since.isoformat(),)):
        if row["wger_id"] not in stored:
            db.execute("DELETE FROM strength_sessions WHERE id = ?", (row["id"],))
    settings.set("wger_last_sync", datetime.now().isoformat(timespec="minutes"))
    return len(stored)


# --------------------------------------------------------------------------- Pläne als Routine senden

def _suggestion(ex: dict) -> strength.Suggestion | None:
    _, last = strength.last_sets(ex["id"])
    return strength.suggest(ex["rep_min"], ex["rep_max"], ex["increment_kg"], last)


def _config(kind: str, slot_entry_id: int, value: float) -> int:
    created = _request("POST", f"{kind}/", body={"slot_entry": slot_entry_id, "iteration": 1, "value": value})
    return created["id"]


def _forget_routine() -> None:
    with db.connect() as con:
        con.execute("DELETE FROM wger_entries")
        con.execute("UPDATE workout_templates SET wger_day_id = NULL")
    settings.set_many({"wger_routine_id": None, "wger_routine_end": None})


def routine_status() -> str | None:
    """Kurzer Hinweis zur gesendeten Routine (oder ``None``, wenn es keine gibt)."""
    if not settings.get("wger_routine_id"):
        return None
    end = settings.get("wger_routine_end")
    if end and date.fromisoformat(end) - date.today() <= timedelta(days=7):
        return f"Die Routine in wger läuft am {date.fromisoformat(end):%d.%m.%Y} ab – bitte neu senden."
    return f"Routine „{ROUTINE_NAME}“ ist in wger angelegt" + (
        f" (gültig bis {date.fromisoformat(end):%d.%m.%Y})." if end else ".")


def push_routines() -> list[tuple[str, bool, str]]:
    """Legt alle Pläne als eine Routine mit einem Trainingstag je Plan in wger an.
    Eine früher gesendete Routine wird vorher gelöscht (die eingetragenen Sätze bleiben in wger)."""
    plans = strength.templates()
    content = []
    for plan in plans:
        exercises = strength.template_exercises(plan["id"])
        content.append((plan, [e for e in exercises if e.get("wger_exercise_id")],
                        [e["name"] for e in exercises if not e.get("wger_exercise_id")]))
    if not any(mapped for _, mapped, _ in content):
        return [("wger", False, "Keine Übung ist einer wger-Übung zugeordnet.")]

    old = settings.get("wger_routine_id")
    if old:
        try:
            _request("DELETE", f"routine/{old}/")
        except WgerNotFound:
            pass
    _forget_routine()

    start = date.today()
    end = start + timedelta(days=ROUTINE_DAYS)
    routine = _request("POST", "routine/", body={
        "name": ROUTINE_NAME,
        "description": "Vom Triathlon-Dashboard erstellt. Gewichte werden nach jedem Abgleich aktualisiert.",
        "start": start.isoformat(), "end": end.isoformat(), "fit_in_week": False,
    })
    settings.set_many({"wger_routine_id": routine["id"], "wger_routine_end": end.isoformat()})

    results = []
    order = 0
    for plan, mapped, unmapped in content:
        hint = f" Ohne Zuordnung übersprungen: {', '.join(unmapped)}." if unmapped else ""
        if not mapped:
            results.append((plan["name"], False, "Keine Übung ist einer wger-Übung zugeordnet." + hint))
            continue
        order += 1
        day = _request("POST", "day/", body={
            "routine": routine["id"], "order": order, "name": plan["name"][:20], "description": "",
            "is_rest": False, "need_logs_to_advance": True, "type": "custom",
        })
        db.execute("UPDATE workout_templates SET wger_day_id = ? WHERE id = ?", (day["id"], plan["id"]))
        for position, ex in enumerate(mapped, start=1):
            sug = _suggestion(ex)
            slot = _request("POST", "slot/", body={"day": day["id"], "order": position})
            entry = _request("POST", "slot-entry/", body={
                "slot": slot["id"], "exercise": ex["wger_exercise_id"], "order": 1,
                "comment": f"Ziel {ex['rep_min']}–{ex['rep_max']} Wdh."[:100],
            })
            _config("sets-config", entry["id"], int(ex["target_sets"] or 3))
            _config("rest-config", entry["id"], REST_SECONDS)
            reps_id = _config("repetitions-config", entry["id"], sug.reps if sug else ex["rep_min"])
            weight_id = _config("weight-config", entry["id"], sug.weight) if sug and sug.weight else None
            db.execute(
                "INSERT OR REPLACE INTO wger_entries (template_id, exercise_id, slot_entry_id, reps_config_id,"
                " weight_config_id) VALUES (?, ?, ?, ?, ?)",
                (plan["id"], ex["id"], entry["id"], reps_id, weight_id),
            )
        count = f"{len(mapped)} {'Übung' if len(mapped) == 1 else 'Übungen'}"
        results.append((plan["name"], True, f"als Trainingstag mit {count} angelegt." + hint))
    return results


def update_suggestions() -> list[str]:
    """Schreibt die aktuellen Gewichts- und Wiederholungsvorschläge in die gesendete Routine.
    Gibt Hinweise zurück (leer = alles in Ordnung)."""
    if not settings.get("wger_routine_id"):
        return []
    rows = db.fetch_all(
        """SELECT w.*, e.id AS ex_id, e.rep_min, e.rep_max, e.increment_kg
           FROM wger_entries w JOIN exercises e ON e.id = w.exercise_id"""
    )
    try:
        for row in rows:
            sug = _suggestion({"id": row["ex_id"], "rep_min": row["rep_min"], "rep_max": row["rep_max"],
                               "increment_kg": row["increment_kg"]})
            reps = sug.reps if sug else row["rep_min"]
            if row["reps_config_id"]:
                _request("PATCH", f"repetitions-config/{row['reps_config_id']}/", body={"value": reps})
            if sug and sug.weight:
                if row["weight_config_id"]:
                    _request("PATCH", f"weight-config/{row['weight_config_id']}/", body={"value": sug.weight})
                else:
                    new_id = _config("weight-config", row["slot_entry_id"], sug.weight)
                    db.execute("UPDATE wger_entries SET weight_config_id = ? WHERE template_id = ? AND exercise_id = ?",
                               (new_id, row["template_id"], row["exercise_id"]))
    except WgerNotFound:
        _forget_routine()
        return ["Die Routine wurde in wger gelöscht oder geändert – bitte die Pläne neu senden."]
    status = routine_status()
    return [status] if status and "läuft" in status else []


def disconnect() -> None:
    """API-Key löschen. Importierte Einheiten bleiben erhalten."""
    settings.set_many({"wger_api_key": "", "wger_last_sync": None})
    _forget_routine()
