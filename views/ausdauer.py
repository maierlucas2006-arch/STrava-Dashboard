from datetime import timedelta

import pandas as pd
import streamlit as st

from triathlon import charts, load, ui
from triathlon.analysis import build_state
from triathlon.load import GROUP_LABELS
from triathlon.units import fmt_duration, fmt_num, fmt_pace, speed_to_pace

state = build_state()
ui.page_header("Ausdauer", "Alle Einheiten aus Strava mit ihrer Belastung.")
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

# ------------------------------------------------------------------ Belastungsstruktur
st.subheader("Abwechslung im Training")
mono, strain = load.monotony_7d(state.pmc["tss"])
weekly = load.weekly_monotony(state.pmc["tss"])
weekly = weekly[weekly.index >= start - pd.Timedelta(days=6)].sort_index(ascending=False)
c1, c2, c3 = st.columns(3)
c1.metric("Monotonie (7 Tage)", fmt_num(mono, 1) if mono is not None else "–",
          help="Ø Tagesbelastung ÷ Streuung der Tagesbelastung (Foster 1998). Über 2 = kaum Wechsel zwischen "
               "harten und leichten Tagen.")
c2.metric("Strain (7 Tage)", f"{strain:.0f}" if strain is not None else "–",
          help="Wochenbelastung × Monotonie. Hohe Belastung bei hoher Monotonie gilt als Risiko für "
               "Überlastung und Infekte.")
typical = weekly["strain"].median() if not weekly.empty and weekly["strain"].notna().any() else None
c3.metric("Strain, typische Woche", f"{typical:.0f}" if typical is not None else "–",
          help="Median der vollständigen Wochen im gewählten Zeitraum – zum Vergleich.")
if mono is not None and mono > load.MONOTONY_LIMIT:
    st.warning("Die letzten 7 Tage waren sehr gleichförmig. Ein klar leichter oder freier Tag bringt wieder "
               "Abwechslung.", icon=":material/swap_vert:")
if not weekly.empty:
    with st.expander("Monotonie und Strain je Woche"):
        st.dataframe(pd.DataFrame({
            "Woche": [f"KW {d.isocalendar().week} ({d:%d.%m.})" for d in weekly.index],
            "Belastung (TSS)": weekly["tss"].round(0),
            "Monotonie": weekly["monotony"].round(2),
            "Strain": weekly["strain"].round(0),
            "Hinweis": ["sehr gleichförmig" if m > load.MONOTONY_LIMIT else ""
                        for m in weekly["monotony"].fillna(0)],
        }), hide_index=True, width="stretch")


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
