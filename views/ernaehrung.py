from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from triathlon import charts, nutrition, settings

profile = settings.load_profile()
lookup_barcode = st.cache_data(ttl=3600, show_spinner="Suche Produkt …")(nutrition.lookup_barcode)
st.title("Ernährung")

c1, c2 = st.columns([1, 3])
day = c1.date_input("Tag", value=date.today(), format="DD.MM.YYYY")

targets = nutrition.targets(profile, day)
log = nutrition.day_log(day)
totals = log[["kcal", "protein", "carbs", "fat"]].sum() if not log.empty else pd.Series(
    {"kcal": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0})

# ------------------------------------------------------------------ Tagesziel
cols = st.columns(4)
for col, (key, label, unit) in zip(cols, [("kcal", "Kalorien", "kcal"), ("protein", "Eiweiß", "g"),
                                         ("carbs", "Kohlenhydrate", "g"), ("fat", "Fett", "g")]):
    eaten, goal = float(totals[key]), float(targets[key])
    col.metric(f"{label} · Ziel {goal:.0f} {unit}", f"{eaten:.0f} {unit}",
               delta=f"noch {goal - eaten:.0f} {unit}" if goal > eaten else f"{eaten - goal:.0f} {unit} drüber",
               delta_color="off")
    col.progress(min(eaten / goal, 1.0) if goal else 0.0)
st.caption(f"Ziel = Grundbedarf {targets['base']:.0f} kcal ({targets['base_note']}) + Training "
           f"{targets['training']:.0f} kcal. Eiweiß {profile.protein_per_kg:g} g/kg, Fett {profile.fat_per_kg:g} g/kg, "
           "Rest Kohlenhydrate – an harten Tagen steigen also automatisch die Kohlenhydrate.")

# ------------------------------------------------------------------ Hinzufügen
hour = datetime.now().hour
default_meal = 0 if hour < 10 else 1 if hour < 15 else 2 if hour < 21 else 3


def add_controls(key: str, food_id_getter) -> None:
    a, b, c = st.columns([2, 1, 1])
    meal = a.selectbox("Mahlzeit", nutrition.MEALS, index=default_meal, key=f"meal_{key}")
    grams = b.number_input("Menge (g)", min_value=1, max_value=3000, value=100, step=10, key=f"g_{key}")
    c.write("")
    if c.button("Hinzufügen", key=f"add_{key}", type="primary", icon=":material/add:"):
        food_id = food_id_getter()
        if food_id:
            nutrition.log_food(day, meal, food_id, grams)
            st.toast("Eingetragen.", icon="✅")
            st.rerun()


st.subheader("Essen eintragen")
tab_own, tab_online, tab_barcode, tab_new = st.tabs(
    ["Meine Lebensmittel", "Online suchen", "Barcode", "Neues Lebensmittel"]
)

with tab_own:
    query = st.text_input("Suchen", key="own_query", placeholder="z. B. Haferflocken")
    foods = nutrition.local_foods(query)
    if foods:
        food = st.selectbox("Lebensmittel (zuletzt benutzte zuerst)", foods, format_func=nutrition.food_label)
        add_controls("own", lambda: food["id"])
    else:
        st.caption("Nichts gefunden – probier „Online suchen“ oder leg es unter „Neues Lebensmittel“ an.")

with tab_online:
    st.caption("Durchsucht die freie Datenbank Open Food Facts (gut für verpackte Produkte).")
    with st.form("off_search"):
        q = st.text_input("Produkt", placeholder="z. B. Skyr Arla")
        if st.form_submit_button("Suchen", icon=":material/search:") and q.strip():
            try:
                st.session_state["off_results"] = nutrition.search_off(q)
            except nutrition.FoodApiError as exc:
                st.error(str(exc))
    results = st.session_state.get("off_results")
    if results:
        hit = st.selectbox("Treffer", results, format_func=lambda f: (
            f"{nutrition.food_label(f)} · E {f['protein']:g} / KH {f['carbs']:g} / F {f['fat']:g}"))
        add_controls("online", lambda: nutrition.save_food(hit, "Open Food Facts"))
    elif results == []:
        st.caption("Keine Treffer mit Nährwerten gefunden.")

with tab_barcode:
    st.caption("Die Nummer unter dem Strichcode eintippen (EAN, meist 13 Ziffern).")
    code = st.text_input("Barcode", key="barcode")
    if code.strip():
        try:
            product = lookup_barcode(code.strip())
        except nutrition.FoodApiError as exc:
            product = None
            st.error(str(exc))
        if product:
            st.markdown(f"**{nutrition.food_label(product)}** · Eiweiß {product['protein']:g} g · "
                        f"KH {product['carbs']:g} g · Fett {product['fat']:g} g (pro 100 g)")
            add_controls("barcode", lambda: nutrition.save_food(product, "Open Food Facts"))
        else:
            st.caption("Produkt nicht gefunden – leg es unter „Neues Lebensmittel“ an.")

with tab_new:
    with st.form("new_food", clear_on_submit=True):
        a, b = st.columns(2)
        name = a.text_input("Name")
        brand = b.text_input("Marke (optional)")
        st.caption("Nährwerte pro 100 g (stehen auf der Packung)")
        k, p_, c_, f_ = st.columns(4)
        kcal = k.number_input("kcal", 0.0, 1000.0, 0.0)
        protein = p_.number_input("Eiweiß (g)", 0.0, 100.0, 0.0)
        carbs = c_.number_input("Kohlenhydrate (g)", 0.0, 100.0, 0.0)
        fat = f_.number_input("Fett (g)", 0.0, 100.0, 0.0)
        if st.form_submit_button("Speichern") and name.strip():
            nutrition.save_food({"name": name.strip(), "brand": brand.strip() or None, "kcal": kcal,
                                 "protein": protein, "carbs": carbs, "fat": fat}, "eigene")
            st.toast(f"{name} gespeichert – jetzt unter „Meine Lebensmittel“.", icon="✅")

# ------------------------------------------------------------------ Tagebuch
st.subheader(f"Tagebuch {day:%d.%m.%Y}")
for meal in nutrition.MEALS:
    entries = log[log["meal"] == meal] if not log.empty else log
    kcal_meal = entries["kcal"].sum() if not entries.empty else 0
    with st.container(border=True):
        st.markdown(f"**{meal}** · {kcal_meal:.0f} kcal")
        if entries.empty:
            if st.button("Wie gestern übernehmen", key=f"copy_{meal}", icon=":material/content_copy:"):
                n = nutrition.copy_meal(day - timedelta(days=1), day, meal)
                st.toast(f"{n} Einträge übernommen." if n else "Gestern war hier nichts eingetragen.")
                st.rerun()
        for row in entries.itertuples():
            a, b = st.columns([6, 1])
            brand = f" ({row.brand})" if row.brand else ""
            a.markdown(f"{row.name}{brand} · {row.grams:.0f} g · {row.kcal:.0f} kcal · "
                       f"E {row.protein:.0f} g / KH {row.carbs:.0f} g / F {row.fat:.0f} g")
            if b.button("Löschen", key=f"del_food_{row.id}", icon=":material/delete:", type="tertiary"):
                nutrition.delete_entry(row.id)
                st.rerun()

# ------------------------------------------------------------------ Verlauf
st.subheader("Letzte 14 Tage")
start = day - timedelta(days=13)
history = nutrition.daily_totals(start, day)
if history.empty:
    st.caption("Noch keine Einträge.")
else:
    target_series = pd.Series(
        {pd.Timestamp(d): nutrition.targets(profile, d)["kcal"]
         for d in (start + timedelta(days=i) for i in range(14))}
    )
    charts.show(charts.kcal_chart(history, target_series))
