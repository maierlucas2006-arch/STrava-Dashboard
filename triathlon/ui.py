"""Gemeinsame Bausteine für die Seiten."""
from __future__ import annotations

import streamlit as st

from triathlon import intervals, settings, strava
from triathlon.analysis import State
from triathlon.plan import Recommendation
from triathlon.recovery import LEVELS
from triathlon.sync import sync_all


def sidebar() -> None:
    with st.sidebar:
        st.markdown("### Daten")
        if st.button("Jetzt synchronisieren", icon=":material/sync:", width="stretch",
                     disabled=not (strava.is_connected() or intervals.is_configured())):
            with st.spinner("Lade Daten von Strava und intervals.icu …"):
                results = sync_all()
            st.session_state["sync_results"] = results
            st.rerun()
        for source, ok, message in st.session_state.pop("sync_results", []):
            (st.success if ok else st.warning)(f"**{source}:** {message}")
        last = settings.get("last_sync")
        st.caption(f"Zuletzt: {last.replace('T', ' ')}" if last else "Noch nie synchronisiert")
        st.caption(
            f"Strava: {'✅ verbunden' if strava.is_connected() else '⚪ nicht verbunden'}  \n"
            f"intervals.icu: {'✅ eingerichtet' if intervals.is_configured() else '⚪ nicht eingerichtet'}"
        )


def recommendation_card(rec: Recommendation, state: State, show_reasons: bool = True) -> None:
    emoji, label = LEVELS[rec.level]
    with st.container(border=True):
        st.markdown(f"#### {emoji} {rec.headline}")
        for s in rec.sessions:
            minutes = f" · {s.minutes} min" if s.minutes else ""
            st.markdown(f"**{s.icon} {s.title}**{minutes}  \n{s.detail}")
        if rec.strength:
            st.markdown(f"**🏋️ Kraft:** {rec.strength}")
        for note in rec.notes:
            st.caption(f"ℹ️ {note}")
        if show_reasons:
            with st.expander(f"Warum {label}?"):
                for text, points in state.readiness.reasons:
                    icon = "✅" if points == 0 else ("⚠️" if points == -1 else "❗")
                    st.markdown(f"{icon} {text}")
                st.caption("Grün = alles im Rahmen · Gelb = ein Warnsignal · Rot = mehrere Warnsignale. "
                           "Das ist eine Entscheidungshilfe – dein Körpergefühl zählt mit.")


def threshold_warning(state: State) -> None:
    missing = state.profile.missing_thresholds()
    if missing:
        st.info(
            "Für genauere Belastungswerte und Trainingsbereiche fehlen noch: **" + ", ".join(missing)
            + "** → in den Einstellungen eintragen.",
            icon=":material/tune:",
        )
