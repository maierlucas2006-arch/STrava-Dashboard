from datetime import date

import pandas as pd
import streamlit as st

from triathlon import charts, intervals
from triathlon.analysis import build_state

state = build_state()
w = state.wellness
st.title("Regeneration")

ready = state.readiness
with st.container(border=True):
    st.markdown(f"#### {ready.emoji} Ampel heute: {ready.label}")
    for text, points in ready.reasons:
        icon = "✅" if points == 0 else ("⚠️" if points == -1 else "❗")
        st.markdown(f"{icon} {text}")

if w.empty:
    st.info(
        "Noch keine Garmin-Daten. So kommen Schlaf, Ruhepuls und HRV ins Dashboard:\n\n"
        "1. Kostenloses Konto auf **intervals.icu** anlegen\n"
        "2. Dort unter *Settings → Connections* **Garmin Connect** verbinden\n"
        "3. Unter *Settings → Developer Settings* einen **API-Key** erzeugen\n"
        "4. Den Key hier in den Einstellungen eintragen und synchronisieren",
        icon=":material/watch:",
    )
else:
    col_a, col_b = st.columns(2, gap="large")
    with col_a:
        st.subheader("HRV (Herzfrequenzvariabilität)")
        fig = charts.hrv_chart(w)
        if fig:
            charts.show(fig)
            st.caption("Grauer Bereich = dein persönlicher Normalbereich (60 Tage). Fällt die blaue 7-Tage-Linie "
                       "darunter, ist dein Körper wahrscheinlich noch nicht erholt.")
        else:
            st.caption("Keine HRV-Werte vorhanden.")
    with col_b:
        st.subheader("Ruhepuls")
        fig = charts.line_with_baseline(w["resting_hr"], "Ruhepuls", "bpm", 30, color_key="bike")
        if fig:
            charts.show(fig)
            st.caption("Ein Ruhepuls 5+ Schläge über deinem Schnitt kann auf Ermüdung oder einen Infekt hindeuten.")
        else:
            st.caption("Keine Ruhepuls-Werte vorhanden.")

    col_c, col_d = st.columns(2, gap="large")
    with col_c:
        st.subheader("Schlaf")
        fig = charts.sleep_chart(w)
        if fig:
            charts.show(fig)
        else:
            st.caption("Keine Schlafdaten vorhanden.")
    with col_d:
        st.subheader("Gewicht")
        fig = charts.line_with_baseline(w["weight"], "Gewicht", "kg", 7, color_key="run")
        if fig:
            charts.show(fig)
        else:
            st.caption("Keine Gewichtsdaten vorhanden (z. B. über eine Garmin-Waage oder manuell).")

    with st.expander("Letzte 14 Tage als Tabelle"):
        recent = w.tail(14).sort_index(ascending=False)
        st.dataframe(pd.DataFrame({
            "Datum": recent.index.strftime("%d.%m.%Y"),
            "Ruhepuls": recent["resting_hr"].round(0),
            "HRV (ms)": recent["hrv"].round(0),
            "Schlaf (h)": recent["sleep_hours"].round(1),
            "Schlaf-Score": recent["sleep_score"].round(0),
            "Gewicht (kg)": recent["weight"].round(1),
            "Quelle": recent["source"],
        }), hide_index=True, width="stretch")

with st.expander("Werte manuell eintragen", icon=":material/edit:"):
    st.caption("Falls intervals.icu nicht eingerichtet ist oder ein Wert fehlt. Leere Felder bleiben unverändert.")
    with st.form("manual_wellness", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        day = c1.date_input("Datum", value=date.today(), format="DD.MM.YYYY")
        rhr = c2.number_input("Ruhepuls", min_value=25, max_value=120, value=None, step=1)
        hrv = c3.number_input("HRV (ms, nächtlicher Schnitt)", min_value=5, max_value=250, value=None, step=1)
        c4, c5, c6 = st.columns(3)
        sleep = c4.number_input("Schlaf (Stunden)", min_value=0.0, max_value=16.0, value=None, step=0.25)
        score = c5.number_input("Schlaf-Score", min_value=0, max_value=100, value=None, step=1)
        weight = c6.number_input("Gewicht (kg)", min_value=30.0, max_value=200.0, value=None, step=0.1)
        if st.form_submit_button("Speichern", type="primary"):
            intervals.save_manual(day, rhr, hrv, sleep, score, weight)
            st.toast("Gespeichert.", icon="✅")
            st.rerun()
