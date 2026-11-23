from datetime import date, timedelta

import streamlit as st

from triathlon import export, ui
from triathlon.analysis import build_state

state = build_state()
ui.page_header("Tageswerte", "Alle Kennzahlen in einer Zeile pro Tag – zum Nachschauen oder als CSV für Excel.")

periods = {"4 Wochen": 28, "3 Monate": 91, "12 Monate": 365, "Alles": None}
period = st.segmented_control("Zeitraum", list(periods), default="4 Wochen", required=True)
days = periods[period or "4 Wochen"]
start = state.today - timedelta(days=days - 1) if days else None
table = export.daily_table(state, start)

if table.empty:
    st.info("Noch keine Daten. Sobald Training, Garmin-Werte, Morgen-Check oder Ernährung da sind, stehen sie hier.",
            icon=":material/table_chart:")
    st.stop()

st.download_button("Als CSV herunterladen", data=export.to_csv(table),
                   file_name=f"tageswerte-{date.today():%Y-%m-%d}.csv", mime="text/csv",
                   icon=":material/download:", on_click="ignore")
shown = table.copy()
shown.index = shown.index.strftime("%d.%m.%Y")
st.dataframe(shown, width="stretch", height=560)
st.caption("Leere Felder = an dem Tag kein Wert. Belastung, Fitness, Ermüdung und Form sind aus der gesamten Historie "
           "berechnet. Die CSV nutzt Semikolon und Dezimalkomma, damit Excel sie direkt richtig öffnet.")
