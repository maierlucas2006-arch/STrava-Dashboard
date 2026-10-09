from datetime import timedelta

import pandas as pd
import streamlit as st

from triathlon import charts, ui
from triathlon.analysis import build_state
from triathlon.load import GROUP_LABELS
from triathlon.units import fmt_duration, fmt_pace, speed_to_pace

state = build_state()
st.title("Ausdauer")
ui.threshold_warning(state)

acts = state.activities
if acts.empty:
    st.info("Noch keine Aktivitäten – verbinde Strava in den Einstellungen und synchronisiere.")
    st.stop()

periods = {"4 Wochen": 4, "3 Monate": 13, "6 Monate": 26, "12 Monate": 52}
f1, f2 = st.columns([3, 4])
period = f1.segmented_control("Zeitraum", list(periods), default="3 Monate", required=True)
groups = f2.pills("Sportarten", list(GROUP_LABELS), default=["swim", "bike", "run"], selection_mode="multi",
                  format_func=GROUP_LABELS.get)
weeks = periods[period]
start = pd.Timestamp(state.today - timedelta(weeks=weeks))
sel = acts[(acts["local_date"] >= start) & (acts["group"].isin(groups or list(GROUP_LABELS)))]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Einheiten", len(sel))
c2.metric("Zeit", fmt_duration(sel["moving_time"].sum()))
c3.metric("Belastung", f"{sel['tss'].sum():.0f} TSS")
c4.metric("Ø pro Woche", fmt_duration(sel["moving_time"].sum() / weeks))

totals = sel.groupby("group").agg(km=("distance", "sum"), zeit=("moving_time", "sum"), n=("id", "size"))
if not totals.empty:
    st.caption(" · ".join(
        f"{GROUP_LABELS[g]}: {row.km / 1000:.0f} km in {fmt_duration(row.zeit)} ({int(row.n)}×)"
        for g, row in totals.iterrows()
    ))

strength = state.strength_sessions if "strength" in (groups or []) else state.strength_sessions.iloc[0:0]
fig, table = charts.weekly_volume_chart(sel, strength, weeks=weeks, today=state.today)
charts.show(fig)
with st.expander("Wochenumfang als Tabelle"):
    st.dataframe(table, width="stretch")


def _speed_text(row) -> str:
    if row.group == "run":
        return f"{fmt_pace(speed_to_pace(row.average_speed))}/km"
    if row.group == "swim":
        return f"{fmt_pace(speed_to_pace(row.average_speed, 100))}/100 m"
    if row.group == "bike" and row.average_speed:
        return f"{row.average_speed * 3.6:.1f} km/h"
    return "–"


st.subheader("Aktivitäten")
view = sel.sort_values("start_date", ascending=False)
table = pd.DataFrame({
    "Datum": view["local_date"].dt.strftime("%d.%m.%Y"),
    "Name": view["name"],
    "Sport": view["sport"],
    "Dauer": view["moving_time"].map(fmt_duration),
    "Distanz (km)": (view["distance"] / 1000).round(1),
    "Tempo": [_speed_text(r) for r in view.itertuples()],
    "Ø Puls": pd.to_numeric(view["average_heartrate"]).round(0),
    "Watt (NP)": pd.to_numeric(view["weighted_average_watts"]).where(view["device_watts"] == 1).round(0),
    "TSS": view["tss"].round(0),
    "Berechnet über": view["tss_method"],
})
st.dataframe(table, hide_index=True, width="stretch", height=480)
st.caption("TSS = Trainingsbelastung (1 Stunde an der Schwelle = 100). „Schätzung“ heißt: ohne Puls/Watt nur "
           "über die Dauer geschätzt.")
