"""Hevy-Anbindung: Import, Zuordnung und Routinen – mit einer nachgebauten Hevy-API (kein Internet nötig)."""
from datetime import date

import pandas as pd
import pytest

from triathlon import db, hevy, load, settings, strength


def workout(wid, start="2026-11-02T16:00:00Z", end="2026-11-02T17:05:00Z", routine_id=None, title="Brust/Rücken",
            exercises=None):
    return {"id": wid, "title": title, "routine_id": routine_id, "description": "Gutes Training",
            "start_time": start, "end_time": end, "exercises": exercises or []}


def exercise(template_id, title, sets, index=0):
    return {"index": index, "title": title, "exercise_template_id": template_id, "superset_id": None,
            "sets": [{"index": i, **s} for i, s in enumerate(sets)]}


class FakeHevy:
    """Antwortet wie die Hevy-API und merkt sich alle Anfragen."""

    def __init__(self):
        self.workouts: list[dict] = []
        self.events: list[dict] = []
        self.templates: list[dict] = []
        self.routines: dict[str, dict] = {}
        self.calls: list[tuple[str, str, dict | None, dict | None]] = []
        self.post_response = "object"

    def __call__(self, method, path, params=None, body=None):
        self.calls.append((method, path, params, body))
        params = params or {}
        if method == "GET" and path in ("/workouts", "/workouts/events", "/exercise_templates", "/routines"):
            items = {"/workouts": self.workouts, "/workouts/events": self.events,
                     "/exercise_templates": self.templates, "/routines": list(self.routines.values())}[path]
            key = {"/workouts": "workouts", "/workouts/events": "events",
                   "/exercise_templates": "exercise_templates", "/routines": "routines"}[path]
            size, page = params["pageSize"], params["page"]
            pages = max(1, -(-len(items) // size))
            if page > pages:
                raise hevy.HevyNotFound(path)
            return {"page": page, "page_count": pages, key: items[(page - 1) * size: page * size]}
        if method == "POST" and path == "/routines":
            rid = f"r{len(self.routines) + 1}"
            self.routines[rid] = {"id": rid, "title": body["routine"]["title"], "created_at": "2026-11-10T10:00:00Z"}
            routine = {"id": rid, "title": body["routine"]["title"]}
            return {"routine": [routine]} if self.post_response == "list" else {"routine": routine}
        if method == "PUT" and path.startswith("/routines/"):
            rid = path.rsplit("/", 1)[1]
            if rid not in self.routines:
                raise hevy.HevyNotFound(path)
            return {"routine": {"id": rid}}
        if method == "GET" and path == "/user/info":
            return {"data": {"name": "Tom", "is_pro": True}}
        raise AssertionError(f"Unerwartete Anfrage {method} {path}")


@pytest.fixture
def api(tmp_db, monkeypatch):
    fake = FakeHevy()
    monkeypatch.setattr(hevy, "_request", fake)
    settings.set("hevy_api_key", "test-key")
    return fake


def plan_id(name):
    return next(p["id"] for p in strength.templates() if p["name"] == name)


def exercise_id(name):
    return db.fetch_one("SELECT id FROM exercises WHERE name = ?", (name,))["id"]


# --------------------------------------------------------------------------- Datenbank

def test_migration_adds_columns_and_is_repeatable(tmp_db):
    db.init_db()  # zweiter Start darf nichts kaputt machen
    for table, column, _ in db.MIGRATIONS:
        cols = {r["name"] for r in db.fetch_all(f"PRAGMA table_info({table})")}
        assert column in cols


def test_migration_upgrades_old_database(tmp_path, monkeypatch):
    path = tmp_path / "alt.db"
    monkeypatch.setattr(db, "DB_PATH", path)
    with db.connect() as con:  # Datenbank im Zustand der ersten Version, mit einer Einheit
        con.executescript(db.SCHEMA)
        con.execute("INSERT INTO strength_sessions (date, duration_min, rpe) VALUES ('2026-10-01', 60, 7)")
    db.init_db()
    assert db.fetch_one("SELECT hevy_id FROM strength_sessions")["hevy_id"] is None
    assert len(strength.sessions_df()) == 1


# --------------------------------------------------------------------------- Import

def test_full_import_maps_plan_exercises_and_skips_warmups(api):
    bench = exercise_id("Bankdrücken (Langhantel)")
    hevy.set_mapping(bench, "BENCH")
    db.execute("UPDATE workout_templates SET hevy_routine_id = 'r-brust' WHERE id = ?", (plan_id("Brust/Rücken"),))
    api.workouts = [workout("w1", routine_id="r-brust", exercises=[
        exercise("BENCH", "Bench Press (Barbell)", [
            {"type": "warmup", "weight_kg": 40, "reps": 10},
            {"type": "normal", "weight_kg": 80, "reps": 10, "rpe": 8},
            {"type": "failure", "weight_kg": 80, "reps": 9.0},
        ]),
        exercise("FACE", "Face Pull (Cable)", [{"type": "normal", "weight_kg": 20, "reps": 15}], index=1),
        exercise("PLANK", "Plank", [{"type": "normal", "weight_kg": None, "reps": None, "duration_seconds": 60}],
                 index=2),
    ])]

    assert hevy.sync_workouts() == 1
    session = db.fetch_one("SELECT * FROM strength_sessions WHERE hevy_id = 'w1'")
    assert session["date"] == "2026-11-02"
    assert session["duration_min"] == 65
    assert session["template_id"] == plan_id("Brust/Rücken")
    assert session["notes"] == "Gutes Training"

    _, sets = strength.last_sets(bench)
    assert [(s["weight"], s["reps"]) for s in sets] == [(80, 10), (80, 9)]  # ohne Aufwärmsatz
    assert sets[0]["rpe"] == 8
    face = db.fetch_one("SELECT * FROM exercises WHERE name = 'Face Pull (Cable)'")
    assert face["from_hevy"] == 1 and face["hevy_template_id"] == "FACE"
    assert db.fetch_one("SELECT 1 FROM exercises WHERE name = 'Plank'") is None  # nur Zeit, keine Wdh.
    assert strength.rotation(1)[0]["name"] == "Arme"  # Rotation läuft mit Hevy-Workouts weiter
    assert settings.get("hevy_last_sync")


def test_plan_is_found_by_title_without_routine(api):
    api.workouts = [workout("w1", title="beine", exercises=[
        exercise("SQ", "Squat (Barbell)", [{"type": "normal", "weight_kg": 100, "reps": 5}])])]
    hevy.sync_workouts()
    assert db.fetch_one("SELECT template_id FROM strength_sessions")["template_id"] == plan_id("Beine")


def test_resync_updates_instead_of_duplicating(api):
    api.workouts = [workout("w1", exercises=[
        exercise("SQ", "Squat (Barbell)", [{"type": "normal", "weight_kg": 100, "reps": 5}])])]
    hevy.sync_workouts(full=True)
    api.workouts[0]["exercises"][0]["sets"][0]["reps"] = 6
    hevy.sync_workouts(full=True)
    assert len(strength.sessions_df()) == 1
    assert db.fetch_all("SELECT reps FROM strength_sets") == [{"reps": 6}]


def test_full_import_removes_workouts_deleted_in_hevy(api):
    api.workouts = [workout("w1"), workout("w2", start="2026-11-04T16:00:00Z", end="2026-11-04T17:00:00Z")]
    hevy.sync_workouts(full=True)
    api.workouts = api.workouts[:1]
    hevy.sync_workouts(full=True)
    assert [r["hevy_id"] for r in db.fetch_all("SELECT hevy_id FROM strength_sessions")] == ["w1"]


def test_incremental_sync_uses_events(api):
    api.workouts = [workout("w1"), workout("w2", start="2026-11-04T16:00:00Z", end="2026-11-04T17:00:00Z")]
    hevy.sync_workouts()
    since = settings.get("hevy_last_sync")
    api.events = [
        {"type": "deleted", "id": "w1", "deleted_at": "2026-11-05T10:00:00Z"},
        {"type": "updated", "workout": workout("w3", start="2026-11-06T16:00:00Z", end="2026-11-06T17:00:00Z")},
    ]
    assert hevy.sync_workouts() == 1
    assert {r["hevy_id"] for r in db.fetch_all("SELECT hevy_id FROM strength_sessions")} == {"w2", "w3"}
    event_calls = [c for c in api.calls if c[1] == "/workouts/events"]
    assert event_calls and event_calls[0][2]["since"] == since


def test_pagination_reads_all_pages(api):
    api.workouts = [workout(f"w{i}", start=f"2026-10-{i + 1:02d}T16:00:00Z", end=f"2026-10-{i + 1:02d}T17:00:00Z")
                    for i in range(23)]
    assert hevy.sync_workouts() == 23
    assert [c[2]["page"] for c in api.calls if c[1] == "/workouts"] == [1, 2, 3]


def test_empty_hevy_account(api):
    assert hevy.sync_workouts() == 0
    assert strength.sessions_df().empty


def test_hevy_session_without_rpe_counts_as_load(api):
    api.workouts = [workout("w1")]
    hevy.sync_workouts()
    df = load.strength_df()
    assert df["tss"].notna().all() and df["tss"].iloc[0] > 0


@pytest.mark.parametrize("duration, rpe, expected", [
    (None, None, 36.0), (float("nan"), float("nan"), 36.0), (60, 7, 49.0), (0, 0, 36.0)])
def test_strength_tss_handles_missing_values(duration, rpe, expected):
    assert load.strength_session_tss(duration, rpe) == expected


# --------------------------------------------------------------------------- Zuordnung

def test_auto_mapping_and_merging_imported_exercise(api):
    api.workouts = [workout("w1", exercises=[
        exercise("BENCH", "Bench Press (Barbell)", [{"type": "normal", "weight_kg": 80, "reps": 10}])])]
    hevy.sync_workouts()  # noch keine Zuordnung → Übung wird mit Hevy-Namen angelegt
    imported = exercise_id("Bench Press (Barbell)")

    api.templates = [{"id": "BENCH", "title": "Bench Press (Barbell)", "is_custom": False},
                     {"id": "SQ", "title": "Squat (Barbell)", "is_custom": False},
                     {"id": "MY", "title": "Squat (Barbell)", "is_custom": True}]
    assert hevy.sync_exercise_templates() == 3
    assert hevy.auto_map_exercises() == 2  # Bankdrücken + Kniebeugen
    bench = exercise_id("Bankdrücken (Langhantel)")
    assert db.fetch_one("SELECT hevy_template_id FROM exercises WHERE id = ?", (bench,))["hevy_template_id"] == "BENCH"
    # Verlauf der importierten Übung wurde übernommen, die doppelte Übung ist weg
    assert strength.last_sets(bench)[1][0]["weight"] == 80
    assert db.fetch_one("SELECT 1 FROM exercises WHERE id = ?", (imported,)) is None
    assert "Squat (Barbell) (eigene)" in hevy.template_labels()

    hevy.set_mapping(bench, None)
    assert db.fetch_one("SELECT hevy_template_id FROM exercises WHERE id = ?", (bench,))["hevy_template_id"] is None


# --------------------------------------------------------------------------- Routinen

def test_push_routine_creates_then_updates_with_suggestion(api):
    bench = exercise_id("Bankdrücken (Langhantel)")
    hevy.set_mapping(bench, "BENCH")
    brust = plan_id("Brust/Rücken")
    strength.save_session(date(2026, 11, 2), brust, 60, 7, "", [(bench, 1, 80, 10, None), (bench, 2, 80, 9, None)])
    plan = next(p for p in strength.templates() if p["id"] == brust)

    ok, message = hevy.push_routine(plan)
    assert ok and "angelegt" in message and "Latziehen" in message  # nicht zugeordnet → Hinweis
    method, path, _, body = api.calls[-1]
    assert (method, path) == ("POST", "/routines")
    routine = body["routine"]
    assert routine["title"] == "Brust/Rücken" and routine["folder_id"] is None
    assert len(routine["exercises"]) == 1
    ex = routine["exercises"][0]
    assert ex["exercise_template_id"] == "BENCH" and len(ex["sets"]) == 3
    assert ex["sets"][0] == {"type": "normal", "weight_kg": 80, "reps": 10, "distance_meters": None,
                             "duration_seconds": None, "custom_metric": None, "rep_range": None}
    assert db.fetch_one("SELECT hevy_routine_id FROM workout_templates WHERE id = ?", (brust,))["hevy_routine_id"] == "r1"

    plan = next(p for p in strength.templates() if p["id"] == brust)
    ok, message = hevy.push_routine(plan)
    method, path, _, body = api.calls[-1]
    assert ok and (method, path) == ("PUT", "/routines/r1")
    assert "folder_id" not in body["routine"]
    assert "rep_range" not in body["routine"]["exercises"][0]["sets"][0]


def test_push_recreates_routine_deleted_in_hevy_and_accepts_list_response(api):
    api.post_response = "list"
    hevy.set_mapping(exercise_id("Kniebeugen"), "SQ")
    beine = plan_id("Beine")
    db.execute("UPDATE workout_templates SET hevy_routine_id = 'weg' WHERE id = ?", (beine,))
    plan = next(p for p in strength.templates() if p["id"] == beine)
    ok, _ = hevy.push_routine(plan)
    assert ok
    assert [c[0] for c in api.calls[-2:]] == ["PUT", "POST"]
    assert "rep_range" in api.calls[-1][3]["routine"]["exercises"][0]["sets"][0]
    assert db.fetch_one("SELECT hevy_routine_id FROM workout_templates WHERE id = ?", (beine,))["hevy_routine_id"] == "r1"


def test_push_without_any_mapping_is_skipped(api):
    results = hevy.push_routines()
    assert all(not ok for _, ok, _ in results)
    assert not [c for c in api.calls if c[0] in ("POST", "PUT")]


def test_only_linked_plans_are_updated_after_sync(api):
    hevy.set_mapping(exercise_id("Kniebeugen"), "SQ")
    assert hevy.push_routines(only_linked=True) == []
    hevy.push_routine(next(p for p in strength.templates() if p["name"] == "Beine"))
    assert [name for name, ok, _ in hevy.push_routines(only_linked=True)] == ["Beine"]


def test_sync_all_includes_hevy(api):
    from triathlon.sync import sync_all

    api.workouts = [workout("w1")]
    results = sync_all()
    assert ("Hevy", True, "1 Krafteinheiten geladen") in results


# --------------------------------------------------------------------------- HTTP-Fehler

class FakeResponse:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text
        self.content = b"x" if payload is not None else b""

    def json(self):
        return self._payload


@pytest.mark.parametrize("status, text, expected", [
    (401, "", "API-Key ab"),
    (403, '{"error":"routine-limit-exceeded"}', "höchstens 4 Routinen"),
    (403, "forbidden", "Hevy Pro"),
    (429, "", "Zu viele Anfragen"),
    (500, "boom", "Hevy-Fehler 500"),
])
def test_http_errors_become_readable_messages(tmp_db, monkeypatch, status, text, expected):
    settings.set("hevy_api_key", "k")
    monkeypatch.setattr(hevy.requests, "request", lambda *a, **kw: FakeResponse(status, None, text))
    with pytest.raises(hevy.HevyError, match=expected):
        hevy.test_connection()


def test_request_sends_api_key_header(tmp_db, monkeypatch):
    settings.set("hevy_api_key", " abc ")
    seen = {}

    def fake(method, url, **kwargs):
        seen.update(method=method, url=url, **kwargs)
        return FakeResponse(200, {"data": {"name": "Tom", "is_pro": True}})

    monkeypatch.setattr(hevy.requests, "request", fake)
    assert hevy.test_connection() == "Tom"
    assert seen["url"] == "https://api.hevyapp.com/v1/user/info"
    assert seen["headers"]["api-key"] == "abc"


def test_404_is_not_found_error(tmp_db, monkeypatch):
    settings.set("hevy_api_key", "k")
    monkeypatch.setattr(hevy.requests, "request", lambda *a, **kw: FakeResponse(404, None, ""))
    with pytest.raises(hevy.HevyNotFound):
        hevy._request("GET", "/workouts")


def test_missing_key(tmp_db):
    assert not hevy.is_configured()
    with pytest.raises(hevy.HevyError, match="Kein Hevy-API-Key"):
        hevy.test_connection()


def test_local_date_converts_utc_to_local_time():
    assert hevy._local_date("2026-11-02T12:00:00Z") == date(2026, 11, 2)
    assert hevy._local_date("2026-11-02T12:00:00.123+00:00") == date(2026, 11, 2)
    assert hevy._local_date(None) is None
    assert hevy._local_date("kaputt") is None


def test_sessions_df_has_hevy_column(tmp_db):
    df = strength.sessions_df()
    assert "hevy_id" in df.columns
    assert isinstance(df, pd.DataFrame)
