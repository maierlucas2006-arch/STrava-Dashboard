from datetime import date

import streamlit as st

from triathlon import auth, db, hevy, intervals, settings, strava, ui, wger
from triathlon.settings import DEFAULT_TARGET_CTL, RACE_DISTANCES
from triathlon.units import fmt_pace, parse_pace

ui.page_header("Einstellungen", "Verbindungen, Athletenprofil und Schwellenwerte. Je genauer die Schwellen, desto besser passen Zielwerte und Belastung.")
p = settings.load_profile()

# ------------------------------------------------------------------ Bisherige Daten (vor der Anmeldung)
legacy = auth.legacy_database()
if legacy is not None:
    with st.container(border=True):
        st.markdown("**Bisherige Daten übernehmen**")
        st.caption(f"Auf diesem Rechner liegen noch Daten aus der Zeit vor der Anmeldung (`{legacy.name}`). "
                   "Du kannst sie einmalig in dein Konto übernehmen. Was in deinem Konto bisher steht, wird dabei "
                   "ersetzt; danach sieht kein anderes Konto diese Daten.")
        if st.button("In mein Konto übernehmen", type="primary", icon=":material/move_down:"):
            archived = auth.adopt_legacy_data(db.current_path())
            st.toast(f"Übernommen. Die alte Datei heißt jetzt {archived.name}.", icon="✅")
            st.rerun()

# ------------------------------------------------------------------ Strava
st.subheader("Strava")
if strava.is_connected():
    st.success("Mit Strava verbunden.", icon=":material/check_circle:")
    c1, c2, c3 = st.columns(3)
    if c1.button("Profil übernehmen (Gewicht, FTP)", icon=":material/download:"):
        try:
            updates = strava.import_profile()
            st.toast("Übernommen: " + (", ".join(f"{k} = {v}" for k, v in updates.items()) or "nichts Neues"))
            st.rerun()
        except strava.StravaError as exc:
            st.error(str(exc))
    if c2.button("Gesamte Historie neu laden", icon=":material/history:",
                 help="Lädt alle Aktivitäten des eingestellten Zeitraums neu (dauert etwas länger)."):
        try:
            with st.spinner("Lade Aktivitäten …"):
                n = strava.sync_activities(full=True)
            st.toast(f"{n} Aktivitäten geladen.", icon="✅")
        except strava.StravaError as exc:
            st.error(str(exc))
    if c3.button("Verbindung trennen", icon=":material/link_off:"):
        strava.disconnect()
        st.rerun()
else:
    with st.expander("So richtest du Strava ein (einmalig, 2 Minuten)", expanded=not strava.is_configured()):
        st.markdown(
            """
1. Öffne **[strava.com/settings/api](https://www.strava.com/settings/api)** und leg eine App an:
   - *Application Name:* z. B. „Triathlon Dashboard“
   - *Category:* Training · *Website:* `http://localhost`
   - *Authorization Callback Domain:* **`localhost`**
2. Kopiere **Client ID** und **Client Secret** in die Felder unten und speichere.
3. Klick auf **„Mit Strava verbinden“** und bestätige bei Strava.
            """
        )
    with st.form("strava_keys"):
        c1, c2 = st.columns(2)
        client_id = c1.text_input("Client ID", value=settings.get("strava_client_id") or "")
        client_secret = c2.text_input("Client Secret", value=settings.get("strava_client_secret") or "",
                                      type="password")
        if st.form_submit_button("Speichern"):
            settings.set_many({"strava_client_id": client_id.strip(), "strava_client_secret": client_secret.strip()})
            st.rerun()
    if strava.is_configured():
        st.link_button("Mit Strava verbinden", strava.authorize_url(), type="primary", icon=":material/link:")
        st.caption("Du wirst zu Strava weitergeleitet und landest danach wieder hier.")

# ------------------------------------------------------------------ intervals.icu
st.subheader("Garmin (über intervals.icu)")
with st.expander("So richtest du intervals.icu ein", expanded=not intervals.is_configured()):
    st.markdown(
        """
1. Kostenloses Konto auf **[intervals.icu](https://intervals.icu)** anlegen.
2. In intervals.icu unter **Settings → Connections → Garmin Connect** verbinden und das
   Übertragen der Gesundheitsdaten (Wellness: Schlaf, Ruhepuls, HRV) erlauben.
3. Unter **Settings → Developer Settings** einen **API Key** erzeugen und unten eintragen.
   Die Athleten-ID (z. B. `i123456`) steht ebenfalls dort – `0` funktioniert aber auch.
        """
    )
with st.form("intervals_keys"):
    c1, c2 = st.columns([3, 1])
    api_key = c1.text_input("API Key", value=settings.get("intervals_api_key") or "", type="password")
    athlete_id = c2.text_input("Athleten-ID", value=settings.get("intervals_athlete_id") or "0")
    if st.form_submit_button("Speichern"):
        settings.set_many({"intervals_api_key": api_key.strip(), "intervals_athlete_id": athlete_id.strip() or "0"})
        st.rerun()
if intervals.is_configured() and st.button("Verbindung testen", icon=":material/network_check:"):
    try:
        st.success(f"Verbunden mit: {intervals.test_connection()}")
    except intervals.IntervalsError as exc:
        st.error(str(exc))

# ------------------------------------------------------------------ Krafttraining-App
st.subheader("Krafttraining (wger)")
with st.expander("So richtest du wger ein (kostenlos)", expanded=not wger.is_configured()):
    st.markdown(
        """
1. Konto auf **[wger.de](https://wger.de)** anlegen und die App **wger Workout Manager** installieren
   (iPhone und Android, kostenlos). In der App mit demselben Konto anmelden.
2. Auf **[wger.de/de/user/api-key](https://wger.de/de/user/api-key)** einen **API-Key** erzeugen.
3. Key unten eintragen, speichern und **„Verbindung testen“** klicken.
4. Unter **Krafttraining → wger** deine Übungen zuordnen und die Pläne an wger senden.
   Im Gym in der App den Trainingstag starten und Sätze eintragen – „Jetzt synchronisieren“ holt sie ins Dashboard.
        """
    )
with st.form("wger_keys"):
    c1, c2 = st.columns([3, 2])
    wger_key = c1.text_input("wger API-Key", value=settings.get("wger_api_key") or "", type="password")
    wger_url = c2.text_input("Server", value=settings.get("wger_url") or wger.DEFAULT_URL,
                             help="Nur ändern, wenn du einen eigenen wger-Server betreibst.")
    wger_auto = st.checkbox(
        "Gewichtsvorschläge nach jedem Sync in die Routine schreiben",
        value=bool(settings.get("wger_auto_update_routines")),
        help="Aktualisiert Gewicht und Ziel-Wiederholungen in der Routine, die das Dashboard angelegt hat.",
    )
    if st.form_submit_button("Speichern"):
        settings.set_many({"wger_api_key": wger_key.strip(), "wger_url": wger_url.strip() or wger.DEFAULT_URL,
                           "wger_auto_update_routines": wger_auto})
        st.rerun()
if wger.is_configured():
    c1, c2, c3 = st.columns(3)
    if c1.button("Verbindung testen", key="wger_test", icon=":material/network_check:"):
        try:
            st.success(f"Verbunden mit: {wger.test_connection()}")
        except wger.WgerError as exc:
            st.error(str(exc))
    if c2.button("Einheiten neu laden", key="wger_full", icon=":material/history:"):
        try:
            with st.spinner("Lade Einheiten aus wger …"):
                n = wger.sync_workouts(full=True)
            st.toast(f"{n} Einheiten aus wger geladen.", icon="✅")
        except wger.WgerError as exc:
            st.error(str(exc))
    if c3.button("Verbindung trennen", key="wger_disconnect", icon=":material/link_off:",
                 help="Löscht nur den API-Key. Importierte Einheiten bleiben erhalten."):
        wger.disconnect()
        st.rerun()

with st.expander("Alternativ: Hevy (nur mit Hevy Pro)", expanded=hevy.is_configured()):
    st.markdown(
        "Die Hevy-API gibt es nur mit **Hevy Pro**. Den API-Key erzeugst du auf "
        "**[hevy.com/settings?developer](https://hevy.com/settings?developer)**."
    )
    with st.form("hevy_keys"):
        hevy_key = st.text_input("Hevy API Key", value=settings.get("hevy_api_key") or "", type="password")
        auto_update = st.checkbox(
            "Gesendete Pläne nach jedem Sync aktualisieren",
            value=bool(settings.get("hevy_auto_update_routines")),
            help="Schreibt die neuen Gewichtsvorschläge in deine Hevy-Routinen. Änderungen, die du direkt in Hevy "
                 "an diesen Routinen machst, werden dabei überschrieben.",
        )
        if st.form_submit_button("Speichern"):
            new_key = hevy_key.strip()
            if new_key != (settings.get("hevy_api_key") or ""):
                settings.set("hevy_last_sync", None)  # neues Konto → beim nächsten Sync alles laden
            settings.set_many({"hevy_api_key": new_key, "hevy_auto_update_routines": auto_update})
            st.rerun()
    if hevy.is_configured():
        c1, c2, c3 = st.columns(3)
        if c1.button("Verbindung testen", key="hevy_test", icon=":material/network_check:"):
            try:
                st.success(f"Verbunden mit: {hevy.test_connection()}")
            except hevy.HevyError as exc:
                st.error(str(exc))
        if c2.button("Alle Workouts neu laden", key="hevy_full", icon=":material/history:"):
            try:
                with st.spinner("Lade Workouts aus Hevy …"):
                    n = hevy.sync_workouts(full=True)
                st.toast(f"{n} Workouts aus Hevy geladen.", icon="✅")
            except hevy.HevyError as exc:
                st.error(str(exc))
        if c3.button("Verbindung trennen", key="hevy_disconnect", icon=":material/link_off:",
                     help="Löscht nur den API-Key. Importierte Workouts bleiben erhalten."):
            hevy.disconnect()
            st.rerun()

# ------------------------------------------------------------------ Profil
st.subheader("Athletenprofil & Schwellenwerte")
max_seen = strava.max_heartrate_seen()
with st.form("profile"):
    c1, c2, c3, c4 = st.columns(4)
    weight = c1.number_input("Gewicht (kg)", 30.0, 200.0, float(p.weight_kg), step=0.5, format="%.1f")
    height = c2.number_input("Größe (cm)", 120, 230, value=int(p.height_cm) if p.height_cm else None, step=1)
    birth_year = c3.number_input("Geburtsjahr", 1940, date.today().year - 10,
                                 value=int(p.birth_year) if p.birth_year else None, step=1)
    sex = c4.selectbox("Geschlecht", ["m", "w"], index=0 if p.sex == "m" else 1,
                       format_func=lambda s: "männlich" if s == "m" else "weiblich")

    c1, c2, c3 = st.columns(3)
    max_hr = c1.number_input("Max. Puls", 120, 230, value=int(p.max_hr) if p.max_hr else None, step=1,
                             help=f"Höchster Wert in deinen Strava-Daten: {max_seen:.0f}" if max_seen else None)
    lthr = c2.number_input("Schwellenpuls (LTHR)", 100, 220, value=int(p.lthr_set) if p.lthr_set else None, step=1,
                           help="Puls, den du ca. 60 min durchhalten kannst (z. B. Ø der letzten 20 min eines "
                                "30-min-Vollgas-Laufs). Leer = 90 % vom Max-Puls.")
    resting = c3.number_input("Ruhepuls (Standard)", 30, 100, int(p.resting_hr), step=1)

    c1, c2, c3 = st.columns(3)
    ftp = c1.number_input("FTP Rad (Watt)", 50, 600, value=int(p.ftp) if p.ftp else None, step=5,
                          help="Functional Threshold Power. Wird über „Profil übernehmen“ aus Strava geholt.")
    pace_text = c2.text_input("Schwellen-Pace Laufen (min/km)", value=fmt_pace(p.threshold_pace)
                              if p.threshold_pace else "", placeholder="4:45",
                              help="Tempo, das du ca. 60 min halten kannst – etwas langsamer als dein 10-km-Tempo.")
    css_text = c3.text_input("CSS Schwimmen (min/100 m)", value=fmt_pace(p.css) if p.css else "",
                             placeholder="1:50",
                             help="Critical Swim Speed. Test: 400 m und 200 m Vollgas, "
                                  "CSS = (Zeit400 − Zeit200) / 2 pro 100 m.")
    paused = st.multiselect("Sportart pausieren (z. B. wegen Verletzung)", ["swim", "bike", "run"],
                            default=p.paused_sports, placeholder="keine",
                            format_func={"swim": "Schwimmen", "bike": "Rad", "run": "Laufen"}.get,
                            help="Der Trainingsplan ersetzt diese Sportart dann durch eine Alternative.")
    if st.form_submit_button("Profil speichern", type="primary"):
        try:
            pace = parse_pace(pace_text)
            css = parse_pace(css_text)
        except ValueError as exc:
            st.error(f"{exc} – bitte im Format m:ss eingeben, z. B. 4:45")
        else:
            settings.set_many({
                "weight_kg": weight, "height_cm": height, "birth_year": birth_year, "sex": sex,
                "max_hr": max_hr, "lthr": lthr, "resting_hr": resting, "ftp": ftp,
                "threshold_pace": pace, "css": css, "paused_sports": paused,
            })
            st.toast("Profil gespeichert.", icon="✅")
            st.rerun()

# ------------------------------------------------------------------ Wettkampf
st.subheader("Wettkampf")
with st.form("race"):
    c1, c2, c3 = st.columns([2, 1, 1])
    race_name = c1.text_input("Name", value=p.race_name)
    race_date = c2.date_input("Datum", value=p.race_date, format="DD.MM.YYYY")
    distance = c3.selectbox("Distanz", RACE_DISTANCES, index=RACE_DISTANCES.index(p.race_distance)
                            if p.race_distance in RACE_DISTANCES else 3)
    c1, c2 = st.columns(2)
    goal_time = c1.text_input("Zielzeit (optional)", value=p.race_goal_time, placeholder="z. B. 12:30 h")
    target_ctl = c2.number_input(
        "Ziel-Fitness am Renntag (CTL)", 20, 200, value=int(p.target_ctl_set) if p.target_ctl_set else None,
        step=5, placeholder=f"Standard für {p.race_distance}: {DEFAULT_TARGET_CTL.get(p.race_distance, 80)}",
        help="Leer lassen für den Standardwert der Distanz. Höher = mehr Training nötig.",
    )
    if st.form_submit_button("Wettkampf speichern", type="primary"):
        settings.set_many({
            "race_name": race_name.strip(), "race_date": race_date.isoformat() if race_date else None,
            "race_distance": distance, "race_goal_time": goal_time.strip(), "target_ctl": target_ctl,
        })
        st.toast("Wettkampf gespeichert.", icon="✅")
        st.rerun()

# ------------------------------------------------------------------ Ernährung
st.subheader("Ernährung")
with st.form("nutrition"):
    c1, c2, c3 = st.columns(3)
    pal = c1.number_input("Alltagsaktivität (PAL, ohne Sport)", 1.2, 2.0, float(p.pal), step=0.05,
                          help="1,3–1,4 = Bürojob/Studium, 1,6 = viel auf den Beinen. Sport wird extra addiert.")
    protein = c2.number_input("Eiweiß (g pro kg)", 1.0, 3.0, float(p.protein_per_kg), step=0.1)
    fat = c3.number_input("Fett (g pro kg)", 0.5, 2.0, float(p.fat_per_kg), step=0.1)
    if st.form_submit_button("Speichern"):
        settings.set_many({"pal": pal, "protein_per_kg": protein, "fat_per_kg": fat})
        st.toast("Gespeichert.", icon="✅")
        st.rerun()

# ------------------------------------------------------------------ Erweitert
with st.expander("Erweitert"):
    with st.form("advanced"):
        history_days = st.number_input("Wie viele Tage Historie laden?", 30, 3650,
                                       int(settings.get("history_days") or 365), step=30)
        api_base = st.text_input("Strava-API-Adresse", value=settings.get("strava_api_base"),
                                 help="Strava stellt bis Juni 2027 auf eine neue Adresse um. Nur ändern, wenn "
                                      "Strava das ankündigt.")
        if st.form_submit_button("Speichern"):
            settings.set_many({"history_days": int(history_days), "strava_api_base": api_base.strip()})
            st.rerun()
    st.caption(f"Deine Daten liegen in der Datei `{db.current_path().name}` – nur dein Konto greift darauf zu.")
