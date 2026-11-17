"""Gemeinsame Bausteine für die Seiten."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from triathlon import auth, db, hevy, intervals, library, settings, strava, strength, visual, wger
from triathlon.analysis import State
from triathlon.sync import sync_all


def sidebar() -> None:
    with st.sidebar:
        st.markdown("### Daten")
        if st.button("Jetzt synchronisieren", icon=":material/sync:", width="stretch",
                     disabled=not (strava.is_connected() or intervals.is_configured() or wger.is_configured()
                                   or hevy.is_configured())):
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


def require_login() -> None:
    """Zeigt die Anmeldeseite, bis jemand angemeldet ist, und wählt dann dessen Datenbank."""
    if auth.demo_mode():
        db.use_database(None)
        return
    if "is_logged_in" not in st.user:
        st.error("Die Anmeldung ist noch nicht eingerichtet: In `.streamlit/secrets.toml` fehlt der Abschnitt "
                 "`[auth]`. Vorlage: `.streamlit/secrets.example.toml` (Anleitung in der README).",
                 icon=":material/lock:")
        st.stop()
    if not st.user.is_logged_in:
        page_header("Triathlon Dashboard",
                    "Training, Erholung und Ernährung an einem Ort. Melde dich an – deine Daten siehst nur du.")
        st.button("Mit Google anmelden", type="primary", icon=":material/login:", on_click=st.login)
        st.stop()
    db.use_database(auth.database_for(st.user.get("iss", ""), st.user.get("sub", "")))


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
