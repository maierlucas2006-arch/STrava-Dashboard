from datetime import date

import streamlit as st

from triathlon import goals
from triathlon.analysis import build_state

state = build_state()
p = state.profile
st.title("Ziele")

# ------------------------------------------------------------------ Hauptwettkampf
if p.race_date:
    with st.container(border=True):
        days = state.days_to_race
        st.markdown(f"### 🏁 {p.race_name}")
        st.markdown(f"{p.race_distance} · {p.race_date:%d.%m.%Y}"
                    + (f" · noch **{days} Tage**" if days is not None and days >= 0 else "")
                    + (f" · Zielzeit **{p.race_goal_time}**" if p.race_goal_time else ""))
        st.caption("Wettkampf und Zielzeit änderst du in den Einstellungen.")


def goal_card(goal: dict) -> None:
    metric = goal["metric"]
    current = goals.current_value(metric, state, goal["current_value"])
    prog = goals.progress(metric, goal["start_value"], goal["target_value"], current)
    unit = goal["unit"] or goals.METRICS.get(metric, ("", ""))[1]
    with st.container(border=True):
        head, actions = st.columns([5, 2])
        with head:
            st.markdown(f"**{goal['title']}**")
            meta = [goal["category"] or ""]
            if goal["deadline"]:
                deadline = date.fromisoformat(goal["deadline"])
                remaining = (deadline - state.today).days
                meta.append(f"bis {deadline:%d.%m.%Y}" + (f" (noch {remaining} Tage)" if remaining >= 0 else " (abgelaufen)"))
            if metric != "manual":
                meta.append(f"automatisch: {goals.METRICS[metric][0]}")
            st.caption(" · ".join(m for m in meta if m))
            if goal["target_value"] is not None:
                current_text = f"{current:g}" if current is not None else "–"
                st.progress(prog or 0.0, text=f"{current_text} / {goal['target_value']:g} {unit}".strip())
            if goal["notes"]:
                st.caption(goal["notes"])
        with actions:
            if metric == "manual" and goal["target_value"] is not None and not goal["done"]:
                new_value = st.number_input("Aktueller Stand", value=float(current or 0.0),
                                            key=f"cur_{goal['id']}", label_visibility="collapsed")
                if new_value != (current or 0.0):
                    goals.update_manual_value(goal["id"], new_value)
                    st.rerun()
            if not goal["done"]:
                if st.button("Erreicht", key=f"done_{goal['id']}", icon=":material/check:"):
                    goals.set_done(goal["id"], True)
                    st.balloons()
                    st.rerun()
            elif st.button("Wieder öffnen", key=f"open_{goal['id']}"):
                goals.set_done(goal["id"], False)
                st.rerun()
            if st.button("Löschen", key=f"delete_{goal['id']}", icon=":material/delete:", type="tertiary"):
                goals.delete_goal(goal["id"])
                st.rerun()


all_goals = goals.list_goals()
open_goals = [g for g in all_goals if not g["done"]]
done_goals = [g for g in all_goals if g["done"]]

st.subheader("Offene Ziele")
if not all_goals:
    st.caption("Noch keine Ziele. Leg unten welche an – oder starte mit ein paar Vorschlägen:")
    if st.button("Vorschläge übernehmen", icon=":material/auto_awesome:"):
        goals.add_goal(f"Fitness (CTL) auf {p.target_ctl:.0f} bringen", "Training", "ctl", round(state.ctl),
                       p.target_ctl, "CTL", p.race_date, "Ziel-CTL für den Wettkampf (siehe Trainingsplan).")
        goals.add_goal("3 Krafteinheiten pro Woche", "Training", "week_strength", None, 3, "x", None, "")
        goals.add_goal("Laufumfang auf 30 km pro Woche", "Training", "week_run_km", None, 30, "km", None,
                       "Langsam steigern – max. ca. 10 % pro Woche.")
        st.rerun()
for goal in open_goals:
    goal_card(goal)

if done_goals:
    with st.expander(f"Erreichte Ziele ({len(done_goals)})"):
        for goal in done_goals:
            goal_card(goal)

# ------------------------------------------------------------------ Neues Ziel
st.subheader("Neues Ziel")
metric = st.selectbox("Wie wird der Fortschritt gemessen?", list(goals.METRICS),
                      format_func=lambda m: goals.METRICS[m][0])
current_auto = goals.current_value(metric, state) if metric != "manual" else None
if current_auto is not None:
    st.caption(f"Aktueller Wert: {current_auto:g} {goals.METRICS[metric][1]}")
with st.form("new_goal", clear_on_submit=True):
    title = st.text_input("Ziel", placeholder="z. B. 10 km unter 45 Minuten")
    c1, c2, c3 = st.columns(3)
    category = c1.selectbox("Kategorie", goals.CATEGORIES)
    target = c2.number_input("Zielwert (optional)", value=None, step=1.0)
    unit = c3.text_input("Einheit", value=goals.METRICS[metric][1])
    c4, c5 = st.columns(2)
    start_value = c4.number_input("Startwert", value=current_auto, step=1.0,
                                  help="Für den Fortschrittsbalken. Bei Wochenzielen egal.")
    deadline = c5.date_input("Bis wann? (optional)", value=None, format="DD.MM.YYYY")
    notes = st.text_input("Notiz (optional)")
    if st.form_submit_button("Ziel anlegen", type="primary") and title.strip():
        goals.add_goal(title, category, metric, start_value, target, unit, deadline, notes)
        st.rerun()
