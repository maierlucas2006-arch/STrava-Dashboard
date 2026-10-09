"""Startdaten, die beim ersten Start angelegt werden.

Alles hier lässt sich später in der App ändern. Die Kraftpläne sind nur ein
Vorschlag für die Rotation Brust/Rücken → Arme → Beine.
"""
from __future__ import annotations

from triathlon import db

# (Name, Wdh. min, Wdh. max, Steigerung in kg)
DEFAULT_TEMPLATES: list[tuple[str, bool, list[tuple[str, int, int, float]]]] = [
    (
        "Brust/Rücken",
        False,
        [
            ("Bankdrücken (Langhantel)", 6, 10, 2.5),
            ("Schrägbankdrücken (Kurzhantel)", 8, 12, 2.0),
            ("Klimmzüge (Zusatzgewicht)", 6, 12, 2.5),
            ("Langhantelrudern", 8, 12, 2.5),
            ("Latziehen", 8, 12, 2.5),
            ("Kabelrudern sitzend", 10, 15, 2.5),
        ],
    ),
    (
        "Arme",
        False,
        [
            ("Schulterdrücken (Kurzhantel)", 8, 12, 2.0),
            ("Seitheben", 12, 15, 1.0),
            ("Langhantel-Curls", 8, 12, 2.5),
            ("Hammercurls", 10, 12, 2.0),
            ("Trizepsdrücken am Kabel", 10, 15, 2.5),
            ("French Press (SZ-Stange)", 8, 12, 2.5),
        ],
    ),
    (
        "Beine",
        True,
        [
            ("Kniebeugen", 6, 10, 2.5),
            ("Rumänisches Kreuzheben", 8, 10, 2.5),
            ("Beinpresse", 10, 12, 5.0),
            ("Ausfallschritte (Kurzhantel)", 10, 12, 2.0),
            ("Beinbeuger", 10, 15, 2.5),
            ("Wadenheben", 12, 20, 5.0),
        ],
    ),
]

# Durchschnittswerte pro 100 g (Name, kcal, Eiweiß, Kohlenhydrate, Fett)
BASE_FOODS: list[tuple[str, float, float, float, float]] = [
    ("Haferflocken", 372, 13.5, 58.7, 7.0),
    ("Reis, roh", 350, 7.0, 77.0, 0.6),
    ("Reis, gekocht", 130, 2.7, 28.0, 0.3),
    ("Nudeln, roh", 355, 12.5, 70.0, 1.5),
    ("Nudeln, gekocht", 158, 5.8, 31.0, 0.9),
    ("Kartoffeln, roh", 77, 2.0, 17.5, 0.1),
    ("Vollkornbrot", 210, 7.0, 38.0, 1.5),
    ("Banane", 89, 1.1, 22.8, 0.3),
    ("Apfel", 52, 0.3, 13.8, 0.2),
    ("Ei (Hühnerei)", 143, 12.6, 0.7, 9.5),
    ("Hähnchenbrust, roh", 120, 22.5, 0.0, 2.6),
    ("Lachs, roh", 208, 20.4, 0.0, 13.4),
    ("Thunfisch im eigenen Saft, abgetropft", 116, 25.5, 0.0, 0.8),
    ("Magerquark", 67, 12.0, 4.0, 0.2),
    ("Skyr natur", 63, 11.0, 4.0, 0.2),
    ("Milch 1,5 %", 47, 3.4, 4.9, 1.5),
    ("Gouda", 356, 24.9, 2.2, 27.4),
    ("Butter", 717, 0.9, 0.1, 81.0),
    ("Olivenöl", 884, 0.0, 0.0, 100.0),
    ("Erdnussbutter", 588, 25.0, 20.0, 50.0),
    ("Mandeln", 579, 21.2, 21.6, 49.9),
    ("Avocado", 160, 2.0, 8.5, 14.7),
    ("Brokkoli", 34, 2.8, 6.6, 0.4),
    ("Tomaten", 18, 0.9, 3.9, 0.2),
    ("Honig", 304, 0.3, 82.4, 0.0),
    ("Whey-Protein (Durchschnitt)", 380, 75.0, 8.0, 6.0),
]


def seed_defaults() -> None:
    if not db.fetch_one("SELECT 1 FROM workout_templates LIMIT 1"):
        for position, (name, lower_body, exercises) in enumerate(DEFAULT_TEMPLATES):
            template_id = db.execute(
                "INSERT INTO workout_templates (name, position, lower_body) VALUES (?, ?, ?)",
                (name, position, int(lower_body)),
            )
            for ex_pos, (ex_name, rep_min, rep_max, inc) in enumerate(exercises):
                existing = db.fetch_one("SELECT id FROM exercises WHERE name = ?", (ex_name,))
                exercise_id = existing["id"] if existing else db.execute(
                    "INSERT INTO exercises (name, rep_min, rep_max, increment_kg) VALUES (?, ?, ?, ?)",
                    (ex_name, rep_min, rep_max, inc),
                )
                db.execute(
                    "INSERT INTO template_exercises (template_id, exercise_id, position, target_sets)"
                    " VALUES (?, ?, ?, 3)",
                    (template_id, exercise_id, ex_pos),
                )

    if not db.fetch_one("SELECT 1 FROM foods LIMIT 1"):
        db.executemany(
            "INSERT INTO foods (name, kcal, protein, carbs, fat, source) VALUES (?, ?, ?, ?, ?, 'Basis')",
            BASE_FOODS,
        )
