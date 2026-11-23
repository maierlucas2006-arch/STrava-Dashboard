"""Triathlon-Dashboard – Einstiegspunkt für Streamlit.

Starten: ``start.py`` in PyCharm ausführen (oder ``streamlit run app.py``).
"""
import streamlit as st

from triathlon import db, strava, ui

st.set_page_config(page_title="Triathlon Dashboard", page_icon="🏊", layout="wide")
ui.inject_style()
ui.apply_app_secrets()   # zentrale Strava-App aus secrets.toml, falls hinterlegt
ui.require_login()       # Anmeldeseite – danach gilt die Datenbank des angemeldeten Kontos
try:
    db.init_db()
    ui.require_consent()     # beim ersten Mal: Datenschutzhinweis und Einwilligung

    # Rückkehr von der Strava-Anmeldung: <Adresse des Dashboards>/?state=…&code=…
    params = st.query_params
    if params.get("state") == strava.OAUTH_STATE:
        if params.get("code"):
            try:
                athlete = strava.exchange_code(params["code"])
                st.session_state["sync_results"] = [
                    ("Strava", True, f"Verbunden{' als ' + athlete['firstname'] if athlete.get('firstname') else ''}.")
                ]
            except strava.StravaError as exc:
                st.session_state["sync_results"] = [("Strava", False, str(exc))]
        else:
            st.session_state["sync_results"] = [("Strava", False, "Anmeldung abgebrochen.")]
        st.query_params.clear()

    pages = [
        st.Page("views/uebersicht.py", title="Übersicht", icon=":material/dashboard:", default=True),
        st.Page("views/galerie.py", title="Trainingsgalerie", icon=":material/view_quilt:"),
        st.Page("views/ausdauer.py", title="Ausdauer", icon=":material/directions_bike:"),
        st.Page("views/regeneration.py", title="Regeneration", icon=":material/bedtime:"),
        st.Page("views/kraft.py", title="Krafttraining", icon=":material/fitness_center:"),
        st.Page("views/ernaehrung.py", title="Ernährung", icon=":material/restaurant:"),
        st.Page("views/ziele.py", title="Ziele", icon=":material/flag:"),
        st.Page("views/daten.py", title="Tageswerte", icon=":material/table_chart:"),
        st.Page("views/einstellungen.py", title="Einstellungen", icon=":material/settings:"),
    ]
    navigation = st.navigation(pages)
    ui.auto_sync()           # einmal pro Sitzung neue Daten holen, wenn der letzte Abgleich älter ist
    ui.sidebar()
    navigation.run()
finally:
    ui.save_changes()        # geänderte Daten sichern (bei Hostern ohne dauerhaften Speicher)
