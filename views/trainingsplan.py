import streamlit as st

from triathlon import charts, plan, ui
from triathlon.analysis import build_state
from triathlon.units import WEEKDAYS_LONG, fmt_num

state = build_state()
p = state.profile

st.title("Trainingsplan")
ui.threshold_warning(state)

if not p.race_date:
    st.warning("Trag in den Einstellungen deinen Wettkampf ein – darauf baut die Planung auf.")
    st.stop()

st.markdown(f"**Ziel:** {p.race_name} ({p.race_distance}) am {p.race_date:%d.%m.%Y}"
            + (f" · Zielzeit {p.race_goal_time}" if p.race_goal_time else ""))

# ------------------------------------------------------------------ Phasen
if state.days_to_race is not None and state.days_to_race >= 0:
    blocks = plan.phase_timeline(state.today, p.race_date, p.race_distance)
    cols = st.columns(len(blocks))
    for col, block in zip(cols, blocks):
        current = block["phase"].key == state.phase.key
        with col.container(border=True):
            st.markdown(f"**{'📍 ' if current else ''}{block['phase'].name}**")
            st.caption(f"{block['start']:%d.%m.%y} – {block['end']:%d.%m.%y}")
    st.caption(f"**Aktuell – {state.phase.name}:** {state.phase.focus}")

# ------------------------------------------------------------------ Wochenziele
st.subheader("Diese Woche")
t = state.targets
c1, c2, c3, c4 = st.columns(4)
c1.metric("Ziel-Belastung", f"{t.tss:.0f} TSS", help="Summe aller Einheiten. Ergibt sich aus deiner aktuellen "
          "Fitness und dem gewünschten Anstieg Richtung Ziel-CTL.")
c2.metric("Ca. Trainingszeit", f"{fmt_num(t.hours, 1)} h")
c3.metric("Fitness-Anstieg", f"{'+' if t.ramp >= 0 else '−'}{fmt_num(abs(t.ramp), 1)} CTL",
          help="Gewünschte Veränderung der Fitness (CTL) pro Woche. "
          "Mehr als +8 pro Woche erhöht das Verletzungsrisiko.")
c4.metric("Krafteinheiten", f"{t.strength}")
st.caption(" · ".join(f"{plan.SPORT_LABELS[s]} {fmt_num(h, 1)} h" for s, h in t.sport_hours.items()))

for day_plan in state.week:
    is_today = day_plan.day == state.today
    is_past = day_plan.day < state.today
    with st.container(border=True):
        left, right = st.columns([1, 4])
        with left:
            label = WEEKDAYS_LONG[day_plan.day.weekday()]
            st.markdown(f"**{'📍 ' if is_today else ''}{label}**  \n{day_plan.day:%d.%m.}")
            if day_plan.done:
                st.caption("✅ " + ", ".join(day_plan.done))
        with right:
            sessions = state.recommendation.sessions if is_today else day_plan.sessions
            strength_text = state.recommendation.strength if is_today else day_plan.strength
            if is_past:
                st.caption("Geplant war: " + ", ".join(s.title for s in day_plan.sessions)
                           + (f" + Kraft ({day_plan.strength})" if day_plan.strength else ""))
            else:
                for s in sessions:
                    minutes = f" · {s.minutes} min" if s.minutes else ""
                    st.markdown(f"**{s.icon} {s.title}**{minutes} – {s.detail}")
                if strength_text:
                    st.markdown(f"**🏋️ Kraft:** {strength_text}")
                notes = state.recommendation.notes if is_today else day_plan.notes
                for note in notes:
                    st.caption(f"ℹ️ {note}")
            if is_today and state.recommendation.level != "green":
                st.caption(f"{state.readiness.emoji} Heute an deine Regeneration angepasst.")

# ------------------------------------------------------------------ Prognose
st.subheader("Fitness bis zum Wettkampf")
if state.days_to_race is not None and state.days_to_race > 0:
    projection = plan.ctl_projection(state.ctl, state.today, p.race_date, p.race_distance, p.target_ctl)
    history = state.pmc.tail(120)
    blocks = plan.phase_timeline(state.today, p.race_date, p.race_distance)
    charts.show(charts.projection_chart(history, projection, p.target_ctl, blocks))
    peak, final = projection["ctl"].max(), projection["ctl"].iloc[-1]
    st.caption(f"Wenn du die Wochenziele einhältst, erreichst du vor dem Tapering etwa **CTL {peak:.0f}** "
               f"(Ziel {p.target_ctl:.0f}, anpassbar in den Einstellungen). Im Tapering sinkt die Fitness bewusst "
               f"leicht auf ca. {final:.0f} – dafür stehst du frisch an der Startlinie.")

with st.expander("Wie entsteht der Plan?"):
    st.markdown(
        """
- **Phasen:** Ab 28 Wochen vor dem Rennen Grundlage, ab 16 Wochen Aufbau, ab 6 Wochen Spitze,
  die letzten 1–2 Wochen Tapering. Davor allgemeine Vorbereitung.
- **Wochenumfang:** Aus deiner aktuellen Fitness (CTL) und dem Abstand zur Ziel-CTL wird ein
  sinnvoller Anstieg pro Woche berechnet (max. +2 bis +4 je nach Phase). Daraus folgt die Ziel-Belastung.
- **Wochenstruktur:** Feste Vorlage je Phase (z. B. Samstag lang Rad, Sonntag langer Lauf), die Dauer
  wird auf dein Wochenziel skaliert.
- **Kraft:** Deine Rotation (Brust/Rücken → Arme → Beine) wird auf die Krafttage verteilt.
  Die Anzahl pro Woche sinkt Richtung Wettkampf.
- **Heute:** Je nach Ampel (HRV, Ruhepuls, Schlaf, Form) wird der Plan für heute angepasst –
  bei Gelb wird hart zu locker, bei Rot gibt es Erholung.
        """
    )
