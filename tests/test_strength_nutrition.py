from datetime import date

import pytest

from triathlon import goals, nutrition, settings, strength
from triathlon.units import fmt_pace, parse_pace


def test_double_progression_increases_weight():
    last = [{"weight": 80, "reps": 12}, {"weight": 80, "reps": 12}, {"weight": 80, "reps": 12}]
    s = strength.suggest(8, 12, 2.5, last)
    assert (s.weight, s.reps) == (82.5, 8)


def test_double_progression_adds_reps():
    last = [{"weight": 80, "reps": 10}, {"weight": 80, "reps": 9}]
    s = strength.suggest(8, 12, 2.5, last)
    assert (s.weight, s.reps) == (80, 11)


def test_e1rm():
    assert strength.e1rm(100, 1) == 100
    assert strength.e1rm(100, 10) == pytest.approx(133.33, abs=0.01)
    assert strength.e1rm(0, 10) is None


def test_describe_sets():
    sets = [{"weight": 80, "reps": 10}, {"weight": 80, "reps": 9}, {"weight": 0, "reps": 12}]
    assert strength.describe_sets(sets) == "80 kg × 10, 9 | Körpergewicht × 12"


def test_rotation_follows_last_session(tmp_db):
    plans = strength.templates()
    assert [p["name"] for p in plans] == ["Brust/Rücken", "Arme", "Beine"]
    assert strength.rotation(1)[0]["name"] == "Brust/Rücken"
    ex = strength.template_exercises(plans[2]["id"])[0]
    strength.save_session(date(2026, 10, 1), plans[2]["id"], 60, 8, "", [(ex["id"], 1, 100, 8, None)])
    assert [p["name"] for p in strength.rotation(3)] == ["Brust/Rücken", "Arme", "Beine"]
    strength.save_session(date(2026, 10, 3), plans[0]["id"], 60, 8, "", [])
    assert strength.rotation(1)[0]["name"] == "Arme"
    assert strength.last_sets(ex["id"])[1][0]["weight"] == 100


def test_off_normalize_converts_kilojoules():
    product = {"product_name": "Test", "code": "123", "nutriments": {"energy_100g": 418.4, "proteins_100g": 5}}
    food = nutrition._normalize(product)
    assert food["kcal"] == pytest.approx(100)
    assert food["protein"] == 5
    assert nutrition._normalize({"nutriments": {"energy-kcal_100g": 100}}) is None


def test_nutrition_targets(tmp_db):
    settings.set_many({"weight_kg": 80, "height_cm": 180, "birth_year": 1996, "sex": "m", "pal": 1.4,
                       "protein_per_kg": 2.0, "fat_per_kg": 1.0})
    p = settings.load_profile()
    base, _ = nutrition.base_kcal(p, date(2026, 10, 9))
    assert base == pytest.approx((800 + 1125 - 150 + 5) * 1.4)
    t = nutrition.targets(p, date(2026, 10, 9))
    assert t["protein"] == 160 and t["fat"] == 80
    assert t["carbs"] == pytest.approx((t["kcal"] - 160 * 4 - 80 * 9) / 4)


def test_run_kcal():
    act = {"sport_type": "Run", "moving_time": 3600, "distance": 10000}
    assert nutrition.activity_kcal(act, 70) == pytest.approx(630)


def test_food_log_roundtrip(tmp_db):
    food_id = nutrition.save_food({"name": "Test", "kcal": 200, "protein": 10, "carbs": 20, "fat": 5}, "eigene")
    nutrition.log_food(date(2026, 10, 8), "Frühstück", food_id, 150)
    assert nutrition.copy_meal(date(2026, 10, 8), date(2026, 10, 9), "Frühstück") == 1
    log = nutrition.day_log(date(2026, 10, 9))
    assert log["kcal"].iloc[0] == pytest.approx(300)


def test_goal_progress():
    assert goals.progress("weight", 90, 85, 87.5) == pytest.approx(0.5)
    assert goals.progress("week_run_km", None, 30, 15) == pytest.approx(0.5)
    assert goals.progress("ctl", 60, 100, 120) == 1.0


def test_pace_roundtrip():
    assert parse_pace("4:45") == 285
    assert fmt_pace(285) == "4:45"
    assert parse_pace("") is None
    with pytest.raises(ValueError):
        parse_pace("4:75")
