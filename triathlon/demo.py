"""Erzeugt erfundene Beispieldaten, um das Dashboard ohne Strava/Garmin auszuprobieren.

Wird von ``start_demo.py`` genutzt und schreibt in eine eigene Datenbank
(``data/demo.db``) – deine echten Daten bleiben unberührt.
"""
from __future__ import annotations

import json
import math
import random
from datetime import date, datetime, time, timedelta, timezone

from triathlon import db, settings, strength

DAYS = 200


def _activity(i: int, day: date, sport: str, minutes: int, rnd: random.Random) -> tuple:
    seconds = minutes * 60
    hr = rnd.uniform(128, 150)
    watts = np = kj = None
    device = 0
    if sport == "Ride":
        speed = rnd.uniform(7.0, 8.4)
        np = rnd.uniform(200, 250)
        watts = np * 0.93
        kj = watts * seconds / 1000
        device = 1
        elevation = minutes * rnd.uniform(4, 12)
    elif sport == "Run":
        speed = rnd.uniform(2.8, 3.3)
        elevation = minutes * rnd.uniform(0.5, 2)
    else:
        speed = rnd.uniform(0.75, 0.9)
        elevation = 0
        hr = rnd.uniform(120, 140)
    start = datetime.combine(day, time(17, 0), tzinfo=timezone.utc)
    names = {"Ride": "Radausfahrt", "Run": "Lauf", "Swim": "Schwimmen"}
    return (
        i, names[sport], sport, start.isoformat().replace("+00:00", "Z"), day.isoformat(), seconds, seconds,
        speed * seconds, elevation, speed, hr, hr + 25, watts, np, kj, device, 0, json.dumps({}),
    )


def build_demo(today: date | None = None, seed: int = 7) -> None:
    today = today or date.today()
    rnd = random.Random(seed)
    db.init_db()

    settings.set_many({
        "athlete_name": "Demo", "weight_kg": 82.0, "height_cm": 184, "birth_year": 1998, "max_hr": 198,
        "ftp": 280, "threshold_pace": 285.0, "css": 110.0,
        "race_name": "Demo-Triathlon", "race_date": (today + timedelta(days=300)).isoformat(),
        "race_distance": "Langdistanz",
    })

    week_pattern = {0: [("Swim", 50)], 1: [("Run", 50)], 2: [("Ride", 90)], 3: [("Swim", 45), ("Run", 40)],
                    5: [("Ride", 180)], 6: [("Run", 80)]}
    acts = []
    act_id = 1
    for offset in range(DAYS, 0, -1):
        day = today - timedelta(days=offset)
        for sport, minutes in week_pattern.get(day.weekday(), []):
            if rnd.random() < 0.85:
                acts.append(_activity(act_id, day, sport, int(minutes * rnd.uniform(0.8, 1.2)), rnd))
                act_id += 1
    from triathlon.strava import UPSERT_SQL
    db.executemany(UPSERT_SQL, acts)

    wellness = []
    for offset in range(DAYS, -1, -1):
        day = today - timedelta(days=offset)
        tired = 1 if offset < 4 else 0  # die letzten Tage etwas müde → zeigt die Ampel
        hrv = math.exp(rnd.gauss(math.log(68), 0.12)) * (0.8 if tired else 1)
        wellness.append((day.isoformat(), round(rnd.gauss(48, 2) + 4 * tired), round(hrv, 1),
                         rnd.uniform(6.2, 8.4) * 3600, rnd.randint(60, 92), round(82 + rnd.gauss(0, 0.4), 1),
                         rnd.randint(6000, 14000)))
    db.executemany(
        "INSERT OR REPLACE INTO wellness (date, resting_hr, hrv, sleep_secs, sleep_score, weight, steps, source)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, 'demo')",
        wellness,
    )

    plans = strength.templates()
    base_weights: dict[int, float] = {}
    session_no = 0
    for offset in range(DAYS, 0, -1):
        day = today - timedelta(days=offset)
        if day.weekday() not in (0, 2, 4):
            continue
        plan = plans[session_no % len(plans)]
        progress = session_no // len(plans)
        sets = []
        for ex in strength.template_exercises(plan["id"]):
            base = base_weights.setdefault(ex["id"], rnd.choice([20, 30, 40, 50, 60]))
            weight = base + ex["increment_kg"] * (progress // 3)
            reps = ex["rep_min"] + progress % 3 * 2
            for n in range(1, (ex["target_sets"] or 3) + 1):
                sets.append((ex["id"], n, weight, min(reps, ex["rep_max"]), None))
        strength.save_session(day, plan["id"], 60, 7, "", sets)
        session_no += 1

    foods = {f["name"]: f["id"] for f in db.fetch_all("SELECT id, name FROM foods")}
    meals = [("Frühstück", "Haferflocken", 100), ("Frühstück", "Milch 1,5 %", 250), ("Frühstück", "Banane", 120),
             ("Mittagessen", "Nudeln, roh", 150), ("Mittagessen", "Hähnchenbrust, roh", 200),
             ("Abendessen", "Vollkornbrot", 150), ("Abendessen", "Magerquark", 250), ("Snacks", "Mandeln", 30)]
    for offset in range(13, -1, -1):
        day = today - timedelta(days=offset)
        for meal, name, grams in meals:
            db.execute("INSERT INTO food_log (date, meal, food_id, grams) VALUES (?, ?, ?, ?)",
                       (day.isoformat(), meal, foods[name], grams * rnd.uniform(0.8, 1.3)))
