"""Gemeinsame Bausteine für die Seiten."""
from __future__ import annotations

import os
from datetime import date, datetime

import pandas as pd
import streamlit as st

from triathlon import (auth, db, hevy, intervals, library, privacy, recovery, settings, storage, strava, strength,
                       visual, wger)
from triathlon.analysis import State
from triathlon.settings import RACE_DISTANCES
from triathlon.sync import sync_all, sync_due

# Zentrale Strava-App aus secrets.toml → Umgebungsvariablen, die settings.get bevorzugt
APP_SECRETS_ENV = {"client_id": "STRAVA_CLIENT_ID", "client_secret": "STRAVA_CLIENT_SECRET",
                   "redirect_uri": "STRAVA_REDIRECT_URI"}


def _secrets_section(name: str) -> dict:
    try:
        section = st.secrets.get(name)
    except Exception:  # keine secrets.toml (Demo, Tests)
        return {}
    return dict(section) if section else {}


def apply_app_secrets() -> None:
    """Liest ``[strava]`` und ``[storage]`` aus secrets.toml: die Strava-App des Betreibers für alle
    Konten und – bei Hostern ohne dauerhaften Speicher – die Sicherung der Konten."""
    for key, env in APP_SECRETS_ENV.items():
        value = _secrets_section("strava").get(key)
        if value:
            os.environ[env] = str(value).strip()
    storage.configure(_secrets_section("storage"))


def app_info() -> dict:
    """Betreiber und Kontakt aus ``[app]`` in secrets.toml (für den Datenschutzhinweis)."""
    return _secrets_section("app")


def _any_source() -> bool:
    return strava.is_connected() or intervals.is_configured() or wger.is_configured() or hevy.is_configured()


def auto_sync() -> None:
    """Einmal pro Sitzung: neue Daten holen, wenn der letzte Abgleich ein paar Stunden her ist."""
    if st.session_state.get("auto_sync_checked") or auth.demo_mode():
        return
    st.session_state["auto_sync_checked"] = True
    if _any_source() and sync_due(settings.get("last_sync"), datetime.now()):
        with st.spinner("Lade neue Daten …"):
            results = sync_all()
        st.session_state["sync_results"] = st.session_state.get("sync_results", []) + results


def sidebar() -> None:
    with st.sidebar:
        st.markdown("### Daten")
        if st.button("Jetzt synchronisieren", icon=":material/sync:", width="stretch", disabled=not _any_source()):
            with st.spinner("Lade Daten …"):
                results = sync_all()
            st.session_state["sync_results"] = results
            st.rerun()
        for source, ok, message in st.session_state.pop("sync_results", []):
            (st.success if ok else st.warning)(f"**{source}:** {message}")
        last = settings.get("last_sync")
        st.caption(f"Zuletzt: {last.replace('T', ' ')}" if last else "Noch nie synchronisiert")
        st.caption(
            f"Strava: {'✅ verbunden' if strava.is_connected() else '⚪ nicht verbunden'}  \n"
            f"intervals.icu: {'✅ eingerichtet' if intervals.is_configured() else '⚪ nicht eingerichtet'}  \n"
            f"wger: {'✅ eingerichtet' if wger.is_configured() else '⚪ nicht eingerichtet'}"
            + ("  \nHevy: ✅ eingerichtet" if hevy.is_configured() else "")
        )
        if not auth.demo_mode() and st.user.get("is_logged_in"):
            st.divider()
            st.caption(f"Angemeldet als {st.user.get('email') or st.user.get('name') or 'Konto'}")
            if st.button("Abmelden", icon=":material/logout:", width="stretch"):
                st.logout()


def inject_style() -> None:
    """Schriften, Zonenfarben und Feinschliff – einmal pro Lauf in app.py."""
    try:
        theme_type = st.context.theme.type
    except Exception:  # außerhalb von Streamlit (Tests)
        theme_type = None
    st.html(visual.style_html(theme_type))


PRIVACY_PAGE = "datenschutz"   # öffentlich erreichbar unter <Adresse>/?seite=datenschutz


def privacy_page() -> None:
    """Datenschutzhinweis ohne Anmeldung – Google verlangt dafür eine öffentliche Adresse."""
    if st.query_params.get("seite") != PRIVACY_PAGE:
        return
    info = app_info()
    page_header("Datenschutzhinweis", "Was mit deinen Daten im Triathlon Dashboard passiert.")
    with st.container(border=True):
        st.markdown(privacy.notice(info.get("operator"), info.get("contact"), info.get("location")))
    if st.button("Zur Anmeldung", icon=":material/login:"):
        st.query_params.clear()
        st.rerun()
    st.stop()


def require_login() -> None:
    """Zeigt die Anmeldeseite, bis jemand angemeldet ist, und wählt dann dessen Datenbank."""
    privacy_page()
    if auth.demo_mode():
        db.use_database(None)
        return
    if "is_logged_in" not in st.user:
        st.error("Die Anmeldung ist noch nicht eingerichtet: In `.streamlit/secrets.toml` fehlt der Abschnitt "
                 "`[auth]`. In PyCharm `setup_login.py` ausführen und Client-ID und Clientschlüssel von Google einfügen, "
                 "dann das Dashboard neu starten.",
                 icon=":material/lock:")
        st.stop()
    if not st.user.is_logged_in:
        page_header("Triathlon Dashboard",
                    "Training, Erholung und Ernährung an einem Ort. Melde dich an – deine Daten siehst nur du.")
        st.button("Mit Google anmelden", type="primary", icon=":material/login:", on_click=st.login)
        st.caption(f"[Datenschutzhinweis](?seite={PRIVACY_PAGE})")
        st.stop()
    path = auth.database_for(st.user.get("iss", ""), st.user.get("sub", ""))
    try:
        storage.restore(path)
    except storage.StorageError as exc:
        st.error(f"{exc} Bitte die Seite in einer Minute neu laden.", icon=":material/cloud_off:")
        st.stop()
    db.use_database(path)


def save_changes() -> None:
    """Am Ende jedes Seitenaufrufs: geänderte Konto-Datei sichern (nur wenn ``[storage]`` eingerichtet ist)."""
    if auth.demo_mode():
        return
    try:
        storage.flush(db.current_path())
    except storage.StorageError as exc:
        st.toast(f"{exc} Deine letzte Änderung ist noch nicht gesichert.", icon="⚠️")


def require_consent() -> None:
    """Vor der ersten Nutzung: Datenschutzhinweis und ausdrückliche Einwilligung (Gesundheitsdaten)."""
    if auth.demo_mode() or settings.get("privacy_consent"):
        return
    info = app_info()
    page_header("Bevor es losgeht", "Kurz und vollständig: was mit deinen Daten passiert.")
    with st.container(border=True):
        st.markdown(privacy.notice(info.get("operator"), info.get("contact"), info.get("location")))
    agreed = st.checkbox(privacy.CONSENT_LABEL)
    c1, c2 = st.columns(2)
    if c1.button("Einverstanden, weiter", type="primary", icon=":material/check:", disabled=not agreed) and agreed:
        settings.set("privacy_consent", datetime.now().isoformat(timespec="seconds"))
        st.rerun()
    if c2.button("Nicht einverstanden – abmelden", icon=":material/logout:"):
        if not auth.has_own_data():
            auth.delete_account(db.current_path())   # die gerade angelegte, leere Datei wieder entfernen
        st.logout()
    st.stop()


GOAL_RACE, GOAL_NONE = "Auf einen Wettkampf", "Ohne bestimmten Wettkampf"
SEX_LABELS = {"m": "männlich", "w": "weiblich"}


def _login_first_name() -> str:
    """Vorname aus dem Google-Konto als Vorschlag (wird erst gespeichert, wenn die Person bestätigt)."""
    try:
        given = st.user.get("given_name") or (st.user.get("name") or "").split(" ")[0]
    except Exception:  # noqa: BLE001 – ohne Anmeldung (lokal/Demo) gibt es kein st.user
        given = ""
    return str(given or "")


def require_setup() -> None:
    """Beim ersten Mal: Name, eigenes Ziel und Körperdaten – nichts davon ist für andere vorbelegt."""
    if auth.demo_mode() or settings.get("setup_done"):
        return
    p = settings.load_profile()
    today = date.today()
    page_header("Willkommen!", "Drei kurze Angaben, damit das Dashboard zu dir passt. "
                               "Alles lässt sich später in den Einstellungen ändern.")
    race_known = bool(p.race_date and p.race_date >= today)
    goal = st.segmented_control(
        "**Worauf trainierst du hin?**", [GOAL_RACE, GOAL_NONE], key="setup_goal",
        default=GOAL_NONE if settings.is_set("race_date") and not race_known else GOAL_RACE,
    )
    with st.form("setup"):
        name = st.text_input("Dein Vorname", value=p.name or _login_first_name(), max_chars=40)
        race_name, race_date, distance, goal_time = "", None, p.race_distance, ""
        if goal == GOAL_RACE:
            st.markdown("**Dein Wettkampf**")
            c1, c2 = st.columns([3, 2])
            race_name = c1.text_input("Name des Wettkampfs", value=p.race_name, placeholder="z. B. Challenge Roth")
            race_date = c2.date_input("Datum", value=p.race_date if race_known else None, min_value=today,
                                      format="DD.MM.YYYY")
            c3, c4 = st.columns(2)
            distance = c3.selectbox("Distanz", RACE_DISTANCES, index=RACE_DISTANCES.index(p.race_distance)
                                    if p.race_distance in RACE_DISTANCES else 1)
            goal_time = c4.text_input("Zielzeit (optional)", value=p.race_goal_time, placeholder="z. B. 5:30 h")
        st.markdown("**Ein paar Körperdaten** – für Kalorienbedarf und Energieverfügbarkeit")
        c1, c2, c3, c4 = st.columns(4)
        sex = c1.selectbox("Geschlecht", list(SEX_LABELS), index=list(SEX_LABELS).index(p.sex)
                           if settings.is_set("sex") and p.sex in SEX_LABELS else 0, format_func=SEX_LABELS.get)
        weight = c2.number_input("Gewicht (kg)", 30.0, 250.0, step=0.5,
                                 value=float(p.weight_kg) if settings.is_set("weight_kg") else None)
        height = c3.number_input("Größe (cm, optional)", 120, 230, value=int(p.height_cm) if p.height_cm else None)
        birth_year = c4.number_input("Geburtsjahr (optional)", 1930, today.year - 10,
                                     value=int(p.birth_year) if p.birth_year else None)
        submitted = st.form_submit_button("Speichern und loslegen", type="primary", icon=":material/arrow_forward:")
    st.caption("FTP, Schwellen-Pace und CSS trägst du später in den Einstellungen ein oder übernimmst sie aus Strava.")
    if submitted:
        missing = []
        if not (name or "").strip():
            missing.append("deinen Vornamen")
        if goal is None:
            missing.append("ob du auf einen Wettkampf hin trainierst")
        if goal == GOAL_RACE and not (race_name or "").strip():
            missing.append("den Namen des Wettkampfs")
        if goal == GOAL_RACE and not race_date:
            missing.append("das Datum des Wettkampfs")
        if not weight:
            missing.append("dein Gewicht")
        if missing:
            st.error("Bitte noch eintragen: " + ", ".join(missing) + ".", icon=":material/edit:")
        else:
            settings.set_many({
                "athlete_name": name.strip(), "sex": sex, "weight_kg": float(weight),
                "height_cm": int(height) if height else None, "birth_year": int(birth_year) if birth_year else None,
                "race_name": race_name.strip() if goal == GOAL_RACE else "",
                "race_date": race_date.isoformat() if goal == GOAL_RACE and race_date else None,
                "race_distance": distance, "race_goal_time": goal_time.strip() if goal == GOAL_RACE else "",
                "setup_done": datetime.now().isoformat(timespec="seconds"),
            })
            st.rerun()
    st.stop()


def morning_check_form(day: date, key: str, existing: dict | None = None) -> None:
    """Die vier Fragen nach Hooper, je 1–7 antippen."""
    with st.form(f"hooper_{key}", border=False):
        values = {}
        for item, (label, scale) in recovery.HOOPER_ITEMS.items():
            values[item] = st.segmented_control(
                f"**{label}** – {scale}", list(range(1, 8)),
                default=int(existing[item]) if existing else None, key=f"hooper_{key}_{item}",
            )
        if st.form_submit_button("Speichern", type="primary", icon=":material/check:"):
            if any(v is None for v in values.values()):
                st.error("Bitte bei allen vier Fragen einen Wert antippen.")
            else:
                recovery.save_hooper(day, **values)
                st.toast("Morgen-Check gespeichert.", icon="✅")
                st.rerun()


def morning_check(state: State) -> None:
    """Morgen-Check für heute – offen, solange er fehlt, danach eingeklappt."""
    today = pd.Timestamp(state.today)
    h = state.hooper
    if not h.empty and today in h.index:
        row = h.loc[today]
        with st.expander(f"Morgen-Check erledigt: Hooper-Index {int(row['index'])} von 28", icon=":material/check:"):
            morning_check_form(state.today, "edit", row.to_dict())
    else:
        with st.container(border=True):
            st.markdown("**Morgen-Check** · vier Fragen, zählt für die Ampel")
            morning_check_form(state.today, "today")


def page_header(title: str, lead: str | None = None) -> None:
    st.html(visual.page_header(title, lead))


TODAY_TEXT = {
    "green": ("Grünes Licht", "Deine Werte liegen im Normalbereich – auch harte Einheiten passen heute."),
    "yellow": ("Heute lieber locker", "Ein Warnsignal: Harte Intervalle besser auf einen anderen Tag legen."),
    "red": ("Heute Erholung", "Mehrere Warnsignale: Lass harte und lange Einheiten heute weg."),
}


def today_card(state: State) -> None:
    """Ampel, passende Kategorien aus der Galerie und die nächste Krafteinheit."""
    ready = state.readiness
    headline, lead = TODAY_TEXT[ready.level]
    suitable = library.suitable_categories(ready.level, state.phase.key)
    with st.container(border=True):
        st.html(visual.status_html(ready.level, headline, lead))
        st.markdown("**Passt heute:** " + ", ".join(library.CATEGORIES[c].name for c in suitable))
        st.caption(f"Schwerpunkt der Phase „{state.phase.name}“, begrenzt durch die Ampel.")

        done_today = bool((state.strength_sessions["date"] == pd.Timestamp(state.today)).any()) \
            if not state.strength_sessions.empty else False
        upcoming = strength.rotation(1)
        if done_today:
            st.markdown("**Kraft:** heute schon erledigt.")
        elif upcoming:
            name = upcoming[0]["name"]
            text = {
                "green": f"{name} ist als Nächstes dran.",
                "yellow": f"{name} geht, aber mit einem Satz weniger pro Übung.",
                "red": f"Heute aussetzen – {name} kommt beim nächsten Mal.",
            }[ready.level]
            st.markdown(f"**Kraft:** {text}")

        st.page_link("views/galerie.py", label="Training aussuchen", icon=":material/view_quilt:")
        with st.expander(f"Warum {ready.label}?"):
            for text, points in ready.reasons:
                icon = "✅" if points == 0 else ("⚠️" if points == -1 else "❗")
                st.markdown(f"{icon} {text}")
            st.caption("Grün = alles im Rahmen, Gelb = ein Warnsignal, Rot = mehrere Warnsignale. "
                       "Das ist eine Entscheidungshilfe – dein Körpergefühl zählt mit.")


def threshold_warning(state: State) -> None:
    missing = state.profile.missing_thresholds()
    if missing:
        st.info(
            "Für genauere Belastungswerte und Trainingsbereiche fehlen noch: **" + ", ".join(missing)
            + "** → in den Einstellungen eintragen.",
            icon=":material/tune:",
        )
