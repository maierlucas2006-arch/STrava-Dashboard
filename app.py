"""Triathlon-Dashboard – Einstiegspunkt für Streamlit.

Starten: ``start.py`` in PyCharm ausführen (oder ``streamlit run app.py``).
"""
import streamlit as st

from triathlon import db, strava, ui

st.set_page_config(page_title="Triathlon Dashboard", page_icon="🏊", layout="wide")
db.init_db()

# Rückkehr von der Strava-Anmeldung: http://localhost:8501/?state=…&code=…
params = st.query_params
if params.get("state") == strava.OAUTH_STATE:
    if params.get("code"):
        try:
            athlete = strava.exchange_code(params["code"])
            st.session_state["sync_results"] = [
                ("Strava", True, f"Verbunden{' als ' + athlete['firstname'] if athlete.get('firstname') else ''}. "
                                 "Klick auf „Jetzt synchronisieren“.")
            ]
        except strava.StravaError as exc:
            st.session_state["sync_results"] = [("Strava", False, str(exc))]
    else:
        st.session_state["sync_results"] = [("Strava", False, "Anmeldung abgebrochen.")]
    st.query_params.clear()

pages = [
    st.Page("views/uebersicht.py", title="Übersicht", icon=":material/dashboard:", default=True),
    st.Page("views/trainingsplan.py", title="Trainingsplan", icon=":material/event_note:"),
    st.Page("views/ausdauer.py", title="Ausdauer", icon=":material/directions_bike:"),
    st.Page("views/regeneration.py", title="Regeneration", icon=":material/bedtime:"),
    st.Page("views/kraft.py", title="Krafttraining", icon=":material/fitness_center:"),
    st.Page("views/ernaehrung.py", title="Ernährung", icon=":material/restaurant:"),
    st.Page("views/ziele.py", title="Ziele", icon=":material/flag:"),
    st.Page("views/einstellungen.py", title="Einstellungen", icon=":material/settings:"),
]
navigation = st.navigation(pages)
ui.sidebar()
navigation.run()
