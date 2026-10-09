"""Ernährungstagebuch: Lebensmittel (Open Food Facts + eigene), Tagesziele."""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import requests

from triathlon import db
from triathlon.load import sport_group
from triathlon.settings import Profile

MEALS = ["Frühstück", "Mittagessen", "Abendessen", "Snacks"]
OFF_SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"
OFF_PRODUCT_URL = "https://world.openfoodfacts.org/api/v2/product/{code}"
OFF_FIELDS = "code,product_name,product_name_de,brands,nutriments"
HEADERS = {"User-Agent": "TriathlonDashboard/1.0 (privates Trainingstagebuch)"}

# MET-Werte für den Kalorienverbrauch, wenn Strava keine Arbeit (kJ) liefert
MET_BY_SPORT = {"Hike": 6.0, "Walk": 3.5, "StairStepper": 9.0, "Rowing": 7.0, "Yoga": 2.5}
MET_BY_GROUP = {"swim": 8.0, "bike": 7.5, "strength": 5.0, "other": 5.0}


class FoodApiError(Exception):
    pass


# --------------------------------------------------------------------------- Open Food Facts

def _normalize(product: dict) -> dict | None:
    nutriments = product.get("nutriments") or {}
    kcal = nutriments.get("energy-kcal_100g")
    if kcal is None and nutriments.get("energy_100g") is not None:
        kcal = float(nutriments["energy_100g"]) / 4.184
    name = (product.get("product_name_de") or product.get("product_name") or "").strip()
    if kcal is None or not name:
        return None
    return {
        "name": name,
        "brand": (product.get("brands") or "").split(",")[0].strip() or None,
        "barcode": product.get("code") or None,
        "kcal": round(float(kcal), 1),
        "protein": round(float(nutriments.get("proteins_100g") or 0), 1),
        "carbs": round(float(nutriments.get("carbohydrates_100g") or 0), 1),
        "fat": round(float(nutriments.get("fat_100g") or 0), 1),
    }


def search_off(query: str, limit: int = 20) -> list[dict]:
    try:
        response = requests.get(
            OFF_SEARCH_URL,
            params={"search_terms": query, "search_simple": 1, "action": "process", "json": 1,
                    "page_size": limit, "fields": OFF_FIELDS, "lc": "de", "cc": "de"},
            headers=HEADERS, timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise FoodApiError(f"Open Food Facts nicht erreichbar: {exc}") from exc
    products = response.json().get("products", [])
    return [p for p in (_normalize(prod) for prod in products) if p]


def lookup_barcode(code: str) -> dict | None:
    try:
        response = requests.get(OFF_PRODUCT_URL.format(code=code.strip()), params={"fields": OFF_FIELDS},
                                headers=HEADERS, timeout=20)
    except requests.RequestException as exc:
        raise FoodApiError(f"Open Food Facts nicht erreichbar: {exc}") from exc
    if response.status_code == 404:
        return None
    response.raise_for_status()
    data = response.json()
    if data.get("status") != 1:
        return None
    product = data.get("product", {})
    product.setdefault("code", code.strip())
    return _normalize(product)


# --------------------------------------------------------------------------- Lebensmittel

def save_food(food: dict, source: str) -> int:
    """Speichert ein Lebensmittel lokal (bei bekanntem Barcode wird es aktualisiert)."""
    if food.get("barcode"):
        existing = db.fetch_one("SELECT id FROM foods WHERE barcode = ?", (food["barcode"],))
        if existing:
            db.execute(
                "UPDATE foods SET name = ?, brand = ?, kcal = ?, protein = ?, carbs = ?, fat = ? WHERE id = ?",
                (food["name"], food.get("brand"), food["kcal"], food["protein"], food["carbs"], food["fat"],
                 existing["id"]),
            )
            return existing["id"]
    return db.execute(
        "INSERT INTO foods (name, brand, barcode, kcal, protein, carbs, fat, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (food["name"], food.get("brand"), food.get("barcode"), food["kcal"], food["protein"], food["carbs"],
         food["fat"], source),
    )


def local_foods(search: str = "") -> list[dict]:
    pattern = f"%{search.strip()}%"
    return db.fetch_all(
        "SELECT * FROM foods WHERE name LIKE ? OR COALESCE(brand, '') LIKE ?"
        " ORDER BY last_used IS NULL, last_used DESC, name",
        (pattern, pattern),
    )


def food_label(food: dict) -> str:
    brand = f" ({food['brand']})" if food.get("brand") else ""
    return f"{food['name']}{brand} – {food['kcal']:.0f} kcal/100 g"


# --------------------------------------------------------------------------- Tagebuch

def log_food(day: date, meal: str, food_id: int, grams: float) -> None:
    db.execute("INSERT INTO food_log (date, meal, food_id, grams) VALUES (?, ?, ?, ?)",
               (day.isoformat(), meal, food_id, grams))
    db.execute("UPDATE foods SET last_used = ? WHERE id = ?", (datetime.now().isoformat(), food_id))


def delete_entry(entry_id: int) -> None:
    db.execute("DELETE FROM food_log WHERE id = ?", (entry_id,))


def copy_meal(source_day: date, target_day: date, meal: str) -> int:
    rows = db.fetch_all("SELECT food_id, grams FROM food_log WHERE date = ? AND meal = ?",
                        (source_day.isoformat(), meal))
    db.executemany("INSERT INTO food_log (date, meal, food_id, grams) VALUES (?, ?, ?, ?)",
                   [(target_day.isoformat(), meal, r["food_id"], r["grams"]) for r in rows])
    return len(rows)


def day_log(day: date) -> pd.DataFrame:
    return db.query_df(
        """SELECT l.id, l.meal, f.name, f.brand, l.grams,
                  f.kcal * l.grams / 100 AS kcal, f.protein * l.grams / 100 AS protein,
                  f.carbs * l.grams / 100 AS carbs, f.fat * l.grams / 100 AS fat
           FROM food_log l JOIN foods f ON f.id = l.food_id
           WHERE l.date = ? ORDER BY l.id""",
        (day.isoformat(),),
    )


def daily_totals(start: date, end: date) -> pd.DataFrame:
    df = db.query_df(
        """SELECT l.date, SUM(f.kcal * l.grams / 100) AS kcal, SUM(f.protein * l.grams / 100) AS protein,
                  SUM(f.carbs * l.grams / 100) AS carbs, SUM(f.fat * l.grams / 100) AS fat
           FROM food_log l JOIN foods f ON f.id = l.food_id
           WHERE l.date BETWEEN ? AND ? GROUP BY l.date ORDER BY l.date""",
        (start.isoformat(), end.isoformat()),
    )
    df["date"] = pd.to_datetime(df["date"])
    return df


# --------------------------------------------------------------------------- Ziele

def base_kcal(profile: Profile, today: date) -> tuple[float, str]:
    """Grundbedarf ohne Sport: Mifflin-St-Jeor × PAL."""
    if profile.height_cm and profile.birth_year:
        age = today.year - int(profile.birth_year)
        bmr = 10 * profile.weight_kg + 6.25 * float(profile.height_cm) - 5 * age
        bmr += 5 if profile.sex == "m" else -161
        return bmr * profile.pal, f"Grundumsatz {bmr:.0f} kcal × PAL {profile.pal:g}"
    return 2400.0, "Schätzwert – trag Größe und Geburtsjahr in den Einstellungen ein"


def activity_kcal(act: dict, weight_kg: float) -> float:
    """Zusätzlicher Verbrauch einer Einheit (ohne den Grundumsatz in der Zeit)."""
    hours = (act.get("moving_time") or 0) / 3600
    resting = weight_kg * hours  # ~1 kcal pro kg und Stunde
    group = sport_group(act.get("sport_type"))
    if group == "bike" and act.get("kilojoules"):
        return max(float(act["kilojoules"]) - resting, 0.0)
    if group == "run" and act.get("distance"):
        return max(weight_kg * act["distance"] / 1000 - resting, 0.0)
    met = MET_BY_SPORT.get(act.get("sport_type") or "", MET_BY_GROUP.get(group, 5.0))
    return max((met - 1) * weight_kg * hours, 0.0)


def training_kcal(day: date, weight_kg: float) -> float:
    acts = db.fetch_all(
        "SELECT sport_type, moving_time, distance, kilojoules FROM activities WHERE local_date = ?",
        (day.isoformat(),),
    )
    total = sum(activity_kcal(a, weight_kg) for a in acts)
    if not any(sport_group(a["sport_type"]) == "strength" for a in acts):
        for s in db.fetch_all("SELECT duration_min FROM strength_sessions WHERE date = ?", (day.isoformat(),)):
            total += (MET_BY_GROUP["strength"] - 1) * weight_kg * (s["duration_min"] or 60) / 60
    return total


def targets(profile: Profile, day: date) -> dict:
    base, base_note = base_kcal(profile, day)
    training = training_kcal(day, profile.weight_kg)
    kcal = base + training
    protein = profile.protein_per_kg * profile.weight_kg
    fat = profile.fat_per_kg * profile.weight_kg
    carbs = max((kcal - protein * 4 - fat * 9) / 4, 0)
    return {"kcal": kcal, "protein": protein, "carbs": carbs, "fat": fat,
            "base": base, "base_note": base_note, "training": training}
