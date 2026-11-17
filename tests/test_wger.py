"""wger-Anbindung: Übungsliste, Zuordnung, Import und Routinen – mit nachgebauter wger-API."""
import itertools
from datetime import date, timedelta

import pytest

from triathlon import db, settings, strength, wger

TODAY = date.today()


def iso(day: date, hour: int = 17, minute: int = 0) -> str:
    return f"{day.isoformat()}T{hour:02d}:{minute:02d}:00+01:00"


class FakeWger:
    """Antwortet wie die wger-API (limit/offset-Seiten, Dezimalzahlen als Text) und merkt sich Anfragen."""

    def __init__(self):
        self.translations: list[dict] = []
        self.logs: list[dict] = []
        self.sessions: list[dict] = []
        self.days: list[dict] = []
        self.calls: list[tuple] = []
        self.objects: dict[str, dict] = {}
        self.next_id = 100

    def _page(self, items, params):
        limit, offset = params["limit"], params["offset"]
        page = items[offset:offset + limit]
        more = offset + limit < len(items)
        return {"count": len(items), "next": "more" if more else None, "previous": None, "results": page}

    def __call__(self, method, path, params=None, body=None):
        self.calls.append((method, path, params, body))
        params = params or {}
        if method == "GET":
            if path == "userprofile/":
                return {"username": "tom"}
            if path == "exercise-translation/":
                items = self.translations
                if "language" in params:
                    items = [t for t in items if t["language"] == params["language"]]
                if "exercise" in params:
                    items = [t for t in items if t["exercise"] == params["exercise"]]
                return self._page(items, params)
            if path == "workoutlog/":
                since = params.get("date__gte", "0000")
                return self._page([l for l in self.logs if l["date"][:10] >= since], params)
            if path == "workoutsession/":
                return self._page(self.sessions, params)
            if path == "day/":
                return self._page(self.days, params)
        if method == "POST":
            kind = path.rstrip("/")
            self.next_id += 1
            obj = {"id": self.next_id, **body}
            self.objects[f"{kind}/{self.next_id}"] = obj
            return obj
        if method == "PATCH":
            key = path.rstrip("/")
            if key not in self.objects:
                raise wger.WgerNotFound(path)
            self.objects[key].update(body)
            return self.objects[key]
        if method == "DELETE":
            key = path.rstrip("/")
            if key not in self.objects:
                raise wger.WgerNotFound(path)
            del self.objects[key]
            return {}
        raise AssertionError(f"Unerwartete Anfrage {method} {path}")

    def created(self, kind: str) -> list[dict]:
        return [o for k, o in self.objects.items() if k.startswith(kind + "/")]


@pytest.fixture
def api(tmp_db, monkeypatch):
    fake = FakeWger()
    monkeypatch.setattr(wger, "_request", fake)
    settings.set("wger_api_key", "test-key")
    return fake


def ex_id(name: str) -> int:
    return db.fetch_one("SELECT id FROM exercises WHERE name = ?", (name,))["id"]


def plan_id(name: str) -> int:
    return next(p["id"] for p in strength.templates() if p["name"] == name)


_IDS = itertools.count(1)


def log(exercise, reps, weight, day=TODAY - timedelta(days=1), session="s1", **extra):
    return {"id": f"log-{next(_IDS):04d}", "date": iso(day), "session": session,
            "routine": None, "exercise": exercise, "repetitions_unit": 1, "repetitions": f"{reps}.00",
            "weight_unit": 1, "weight": None if weight is None else f"{weight}.00", "rir": None, **extra}


CATALOG = [
    {"exercise": 1, "language": 1, "name": "Bankdrücken"}, {"exercise": 1, "language": 2, "name": "Bench Press"},
    {"exercise": 2, "language": 2, "name": "Squats"},
    {"exercise": 3, "language": 1, "name": "Latziehen"},
    {"exercise": 4, "language": 1, "name": "Wadenheben stehend"},
    {"exercise": 9, "language": 2, "name": "Face Pull"},
]


# --------------------------------------------------------------------------- Datenbank & Übungen

def test_migration_adds_wger_columns(tmp_db):
    db.init_db()
    cols = {r["name"] for r in db.fetch_all("PRAGMA table_info(strength_sessions)")}
    assert "wger_id" in cols
    assert {"wger_exercise_id", "from_wger"} <= {r["name"] for r in db.fetch_all("PRAGMA table_info(exercises)")}


def test_catalog_prefers_german_and_reads_all_pages(api, monkeypatch):
    monkeypatch.setattr(wger, "PAGE_LIMIT", 2)
    api.translations = CATALOG
    assert wger.sync_exercise_catalog() == 5
    rows = {r["id"]: r for r in wger.exercise_catalog()}
    assert rows[1]["name"] == "Bankdrücken" and rows[1]["name_en"] == "Bench Press"
    assert rows[2]["name"] == "Squats"
    labels = wger.exercise_labels()
    assert labels["Bankdrücken (Bench Press)"] == 1 and labels["Squats"] == 2


def test_auto_mapping_uses_names_and_suggestions(api):
    api.translations = CATALOG
    wger.sync_exercise_catalog()
    assert wger.auto_map_exercises() == 4
    mapping = {r["name"]: r["wger_exercise_id"] for r in wger.mapping_table()}
    assert mapping["Bankdrücken (Langhantel)"] == 1      # Vorschlagsliste, deutsch
    assert mapping["Kniebeugen"] == 2                     # Vorschlagsliste, englisch
    assert mapping["Latziehen"] == 3                      # gleicher Name
    assert mapping["Wadenheben"] == 4                     # Vorschlagsliste
    assert mapping["Seitheben"] is None
    assert wger.auto_map_exercises() == 0                 # nichts doppelt


# --------------------------------------------------------------------------- Import

def test_import_session_with_plan_units_and_rir(api):
    api.translations = CATALOG
    wger.sync_exercise_catalog()
    wger.set_mapping(ex_id("Bankdrücken (Langhantel)"), 1)
    day = TODAY - timedelta(days=1)
    api.days = [{"id": 7, "name": "brust/rücken"}]
    api.sessions = [{"id": "s1", "day": 7, "notes": "gut", "datetime_start": iso(day, 17, 0),
                     "datetime_end": iso(day, 18, 5)}]
    api.logs = [
        log(1, 10, 80, rir="2.0"), log(1, 9, 80),
        log(9, 15, 44, weight_unit=2),                     # Pfund, unbekannte Übung
        log(2, 60, None, repetitions_unit=3),              # Sekunden → nicht übernehmen
        log(1, 0, 80),                                     # 0 Wiederholungen → nicht übernehmen
    ]
    assert wger.sync_workouts() == 1
    session = db.fetch_one("SELECT * FROM strength_sessions WHERE wger_id = 's1'")
    assert session["date"] == day.isoformat()
    assert session["duration_min"] == 65 and session["notes"] == "gut"
    assert session["template_id"] == plan_id("Brust/Rücken")
    _, sets = strength.last_sets(ex_id("Bankdrücken (Langhantel)"))
    assert [(s["weight"], s["reps"], s["rpe"]) for s in sets] == [(80, 10, 8.0), (80, 9, None)]
    face = db.fetch_one("SELECT * FROM exercises WHERE name = 'Face Pull'")
    assert face["from_wger"] == 1 and face["wger_exercise_id"] == 9
    assert db.fetch_one("SELECT weight FROM strength_sets WHERE exercise_id = ?", (face["id"],))["weight"] == \
        pytest.approx(19.96, abs=0.01)
    assert strength.rotation(1)[0]["name"] == "Arme"     # Rotation läuft mit wger-Einheiten weiter


def test_resync_updates_groups_without_session_and_removes_deleted(api):
    api.translations = CATALOG
    d1, d2 = TODAY - timedelta(days=3), TODAY - timedelta(days=1)
    api.logs = [log(2, 5, 100, day=d1, session=None), log(2, 5, 100, day=d2, session="s2")]
    api.sessions = [{"id": "s2", "day": None, "notes": None, "datetime_start": iso(d2, 7),
                     "datetime_end": iso(d2, 23)}]                       # 16 h: Session nicht beendet
    assert wger.sync_workouts() == 2
    assert db.fetch_one("SELECT duration_min FROM strength_sessions WHERE wger_id = 's2'")["duration_min"] is None
    assert db.fetch_one("SELECT 1 FROM strength_sessions WHERE wger_id LIKE 'd:%'")
    api.logs[1]["repetitions"] = "6.00"
    wger.sync_workouts()
    assert len(strength.sessions_df()) == 2
    api.logs = api.logs[1:]
    wger.sync_workouts()
    assert [r["wger_id"] for r in db.fetch_all("SELECT wger_id FROM strength_sessions")] == ["s2"]
    assert db.fetch_all("SELECT reps FROM strength_sets") == [{"reps": 6}]


def test_old_logs_outside_history_are_kept(api):
    old = TODAY - timedelta(days=500)
    strength.save_session(old, None, 60, 7, "", [])
    db.execute("UPDATE strength_sessions SET wger_id = 'alt'")
    wger.sync_workouts()
    assert db.fetch_one("SELECT 1 FROM strength_sessions WHERE wger_id = 'alt'")


def test_empty_account(api):
    assert wger.sync_workouts() == 0
    assert strength.sessions_df().empty


# --------------------------------------------------------------------------- Routinen

def test_push_creates_routine_with_suggestions_and_replaces_old(api):
    bench, squat = ex_id("Bankdrücken (Langhantel)"), ex_id("Kniebeugen")
    wger.set_mapping(bench, 1)
    wger.set_mapping(squat, 2)
    strength.save_session(TODAY - timedelta(days=2), plan_id("Brust/Rücken"), 60, 7, "",
                          [(bench, 1, 80, 10, None), (bench, 2, 80, 10, None), (bench, 3, 80, 10, None)])
    results = wger.push_routines()
    assert [ok for _, ok, _ in results] == [True, False, True]          # Arme ohne Zuordnung
    routine = api.created("routine")[0]
    assert routine["name"] == "Triathlon-Kraft"
    assert date.fromisoformat(routine["end"]) - date.fromisoformat(routine["start"]) == timedelta(days=119)
    days = api.created("day")
    assert [d["name"] for d in days] == ["Brust/Rücken", "Beine"]
    assert all(d["need_logs_to_advance"] for d in days) and [d["order"] for d in days] == [1, 2]
    entries = api.created("slot-entry")
    assert {e["exercise"] for e in entries} == {1, 2}
    weights = {c["slot_entry"]: c["value"] for c in api.created("weight-config")}
    bench_entry = next(e for e in entries if e["exercise"] == 1)
    assert weights == {bench_entry["id"]: 82.5}                         # 3 × 10 geschafft → +2,5 kg
    assert {c["value"] for c in api.created("sets-config")} == {3}
    assert all(c["iteration"] == 1 for c in api.created("repetitions-config"))
    assert settings.get("wger_routine_id") == routine["id"]
    assert db.fetch_one("SELECT wger_day_id FROM workout_templates WHERE id = ?",
                        (plan_id("Beine"),))["wger_day_id"] == days[1]["id"]

    wger.push_routines()
    deletes = [c for c in api.calls if c[0] == "DELETE"]
    assert deletes == [("DELETE", f"routine/{routine['id']}/", None, None)]
    assert len(api.created("routine")) == 1


def test_push_without_mapping(api):
    assert wger.push_routines() == [("wger", False, "Keine Übung ist einer wger-Übung zugeordnet.")]
    assert not [c for c in api.calls if c[0] == "POST"]


def test_update_suggestions_patches_and_handles_deleted_routine(api):
    bench = ex_id("Bankdrücken (Langhantel)")
    wger.set_mapping(bench, 1)
    wger.push_routines()
    assert not api.created("weight-config")                              # noch kein Verlauf → kein Gewicht
    strength.save_session(TODAY, plan_id("Brust/Rücken"), 60, 7, "", [(bench, 1, 70, 8, None)])
    assert wger.update_suggestions() == []
    assert [c["value"] for c in api.created("weight-config")] == [70]
    assert [c["value"] for c in api.created("repetitions-config")] == [9]
    for key in [k for k in api.objects if k.startswith("repetitions-config/")]:
        del api.objects[key]
    notes = wger.update_suggestions()
    assert notes and "neu senden" in notes[0]
    assert settings.get("wger_routine_id") is None
    assert not db.fetch_all("SELECT * FROM wger_entries")


def test_sync_all_includes_wger(api):
    from triathlon.sync import sync_all

    api.logs = [log(2, 5, 100)]
    assert ("wger", True, "1 Krafteinheiten geladen") in sync_all()


# --------------------------------------------------------------------------- HTTP

class FakeResponse:
    def __init__(self, status, payload=None, text=""):
        self.status_code, self._payload, self.text = status, payload, text
        self.content = b"x" if payload is not None else b""

    def json(self):
        return self._payload


@pytest.mark.parametrize("status, expected", [(401, "API-Key"), (403, "API-Key"), (400, "abgelehnt"),
                                              (429, "Zu viele"), (500, "wger-Fehler 500")])
def test_http_errors(tmp_db, monkeypatch, status, expected):
    settings.set("wger_api_key", "k")
    monkeypatch.setattr(wger.requests, "request", lambda *a, **kw: FakeResponse(status, None, "x"))
    with pytest.raises(wger.WgerError, match=expected):
        wger.test_connection()


def test_request_uses_token_header_and_server(tmp_db, monkeypatch):
    settings.set_many({"wger_api_key": " abc ", "wger_url": "https://fit.example.org/"})
    seen = {}

    def fake(method, url, **kwargs):
        seen.update(method=method, url=url, **kwargs)
        return FakeResponse(200, {"username": "tom"})

    monkeypatch.setattr(wger.requests, "request", fake)
    assert wger.test_connection() == "tom"
    assert seen["url"] == "https://fit.example.org/api/v2/userprofile/"
    assert seen["headers"]["Authorization"] == "Token abc"


def test_404_and_missing_key(tmp_db, monkeypatch):
    with pytest.raises(wger.WgerError, match="Kein wger-API-Key"):
        wger.test_connection()
    settings.set("wger_api_key", "k")
    monkeypatch.setattr(wger.requests, "request", lambda *a, **kw: FakeResponse(404, None, ""))
    with pytest.raises(wger.WgerNotFound):
        wger._request("GET", "routine/1/")
