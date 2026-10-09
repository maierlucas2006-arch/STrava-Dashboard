from datetime import timedelta

import pandas as pd
import streamlit as st

from triathlon import charts, recovery, ui
from triathlon.analysis import build_state
from triathlon.load import GROUP_LABELS
from triathlon.units import fmt_num

state = build_state()
p = state.profile

st.title(f"Hallo {p.name}! 👋" if p.name else "Triathlon Dashboard")
if p.race_date and state.days_to_race is not None and state.days_to_race >= 0:
    st.markdown(
        f"**{p.race_name}** ({p.race_distance}) am {p.race_date:%d.%m.%Y} – noch **{state.days_to_race} Tage** "
        f"({state.days_to_race / 7:.0f} Wochen) · Phase: **{state.phase.name}**"
    )
    st.caption(state.phase.focus)

if state.activities.empty:
    st.info("Noch keine Trainingsdaten. Verbinde Strava in den Einstellungen und klick dann links auf "
            "„Jetzt synchronisieren“.", icon=":material/link:")
    st.page_link("views/einstellungen.py", label="Zu den Einstellungen", icon=":material/settings:")
ui.threshold_warning(state)

left, right = st.columns(2, gap="large")
with left:
    st.subheader("Empfehlung für heute")
    ui.recommendation_card(state.recommendation, state)

with right:
    st.subheader("Dein Zustand")
    c1, c2, c3 = st.columns(3)
    c1.metric("Fitness", f"{state.ctl:.0f}",
              delta=(f"{'+' if state.ramp >= 0 else '-'}{fmt_num(abs(state.ramp), 1)}/Woche"
                     if state.ramp is not None else None),
              help="CTL: langfristige Belastung der letzten ~6 Wochen. Steigt, wenn du regelmäßig trainierst.")
    c2.metric("Ermüdung", f"{state.atl:.0f}", help="ATL: Belastung der letzten ~7 Tage.")
    c3.metric("Form", f"{state.tsb:+.0f}",
              help="TSB = Fitness minus Ermüdung. −10 bis −30 = produktives Training, unter −30 = Überlastungsgefahr, "
                   "über +5 = frisch (gut vor Wettkämpfen).")

    w = state.wellness
    hrv = recovery.hrv_status(w, state.today) or recovery.hrv_status(w, state.today - timedelta(days=1))
    latest = w.iloc[-1] if not w.empty else None
    c4, c5, c6 = st.columns(3)
    c4.metric("HRV Ø 7 Tage", f"{hrv.avg7_ms:.0f} ms" if hrv and hrv.avg7_ms else "–",
              help=(f"Dein Normalbereich: {hrv.low_ms:.0f}–{hrv.high_ms:.0f} ms" if hrv else
                    "Braucht mind. 14 Nächte HRV-Daten von Garmin (über intervals.icu)."))
    c5.metric("Ruhepuls", f"{latest['resting_hr']:.0f}" if latest is not None and pd.notna(latest["resting_hr"])
              else "–")
    has_sleep = latest is not None and pd.notna(latest["sleep_hours"])
    c6.metric("Schlaf", f"{fmt_num(latest['sleep_hours'], 1)} h" if has_sleep else "–")
    if latest is not None:
        st.caption(f"Garmin-Werte vom {latest.name:%d.%m.%Y}")

    st.markdown("**Diese Woche**")
    t = state.targets
    week_tss = state.week_tss()
    st.progress(min(week_tss / t.tss, 1.0) if t.tss else 0.0,
                text=f"Belastung: {week_tss:.0f} von {t.tss:.0f} TSS")
    week_acts = state.week_activities()
    for group in ("swim", "bike", "run"):
        done = float(week_acts.loc[week_acts["group"] == group, "moving_time"].sum()) / 3600 if not week_acts.empty else 0
        goal = t.sport_hours.get(group, 0)
        st.progress(min(done / goal, 1.0) if goal else 0.0,
                    text=f"{GROUP_LABELS[group]}: {fmt_num(done, 1)} von {fmt_num(goal, 1)} h")
    strength_done = len(state.week_strength())
    st.progress(min(strength_done / t.strength, 1.0) if t.strength else 1.0,
                text=f"Kraft: {strength_done} von {t.strength} Einheiten")

st.divider()
col_a, col_b = st.columns(2, gap="large")
with col_a:
    st.subheader("Fitness & Ermüdung")
    if state.pmc["tss"].sum() > 0:
        charts.show(charts.pmc_chart(state.pmc))
        charts.show(charts.tsb_chart(state.pmc))
    else:
        st.caption("Erscheint, sobald Trainingsdaten da sind.")
with col_b:
    st.subheader("Umfang pro Woche")
    fig, table = charts.weekly_volume_chart(state.activities, state.strength_sessions, today=state.today)
    if table.to_numpy().sum() > 0:
        charts.show(fig)
        with st.expander("Daten als Tabelle"):
            st.dataframe(table, width="stretch")
    else:
        st.caption("Erscheint, sobald Trainingsdaten da sind.")
