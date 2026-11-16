import streamlit as st

from triathlon import library as lib
from triathlon import ui, visual
from triathlon.analysis import build_state

state = build_state()
p = state.profile
th = lib.Thresholds.from_profile(p)

ui.page_header(
    "Trainingsgalerie",
    f"{len(lib.WORKOUTS)} Einheiten für Rad, Laufen, Schwimmen und Koppeltraining. "
    "Such dir aus, was heute passt – Watt und Pace kommen aus deinen Schwellenwerten.",
)

suitable = lib.suitable_categories(state.readiness.level, state.phase.key)
suitable_names = ", ".join(lib.CATEGORIES[c].name for c in suitable)

c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
sport = c1.segmented_control("Sportart", list(lib.SPORTS), default="bike", format_func=lib.SPORTS.get,
                             required=True, key="gallery_sport")
only_today = c2.toggle("Nur, was heute passt", key="gallery_today",
                       help=f"Ampel {state.readiness.label}, Phase „{state.phase.name}“: {suitable_names}.")

available = lib.categories_for(sport)
c3, c4 = st.columns([3, 2], vertical_alignment="bottom")
chosen = c3.pills("Kategorie", available, selection_mode="multi", format_func=lambda c: lib.CATEGORIES[c].name,
                  key=f"gallery_categories_{sport}")
max_minutes = c4.slider("Höchstens", min_value=30, max_value=300, value=300, step=15, format="%d min",
                        key="gallery_max_minutes")

selected = list(chosen) or available
if only_today:
    selected = [c for c in selected if c in suitable]

needed = {"bike": ["bike"], "run": ["run"], "swim": ["swim"], "brick": ["bike", "run"]}[sport]
missing = [s for s in needed if not th.has(s)]
if missing:
    labels = {"bike": "FTP", "run": "Schwellen-Pace", "swim": "CSS"}
    st.info(
        "Ohne " + " und ".join(labels[s] for s in missing) + " zeigen die Karten Prozentwerte statt Watt "
        "bzw. Pace, und Dauern nach Strecke sind geschätzt.",
        icon=":material/tune:",
    )
    st.page_link("views/einstellungen.py", label="Schwellenwerte eintragen", icon=":material/settings:")

workouts = lib.workouts_for(sport, selected, None if max_minutes >= 300 else max_minutes, th) if selected else []

st.html(visual.zone_legend())
if not selected:
    st.info(f"Heute passt laut Ampel und Phase: {suitable_names}. Davon ist in dieser Auswahl nichts dabei – "
            "wähl eine andere Sportart oder schalte „Nur, was heute passt“ aus.", icon=":material/filter_alt_off:")
elif not workouts:
    st.info("Keine Einheit passt zu diesen Filtern. Nimm eine Kategorie dazu oder erhöhe die Dauer.",
            icon=":material/filter_alt_off:")
else:
    st.html(visual.gallery_html(workouts, th, state.ctl))

with st.expander("So liest du die Karten"):
    st.markdown(
        """
- **Blöcke:** Breite = Dauer, Höhe und Farbe = Intensität. Die gestrichelte Linie ist deine Schwelle (100 %).
  Fahr mit der Maus über einen Block, um Dauer und Zielwert zu sehen.
- **Prozent** beziehen sich beim Rad auf die FTP, beim Laufen auf dein Schwellentempo und beim Schwimmen
  auf dein CSS-Tempo. 110 % beim Laufen heißt also: 10 % schneller als an der Schwelle.
- **TSS** schätzt die Belastung (eine Stunde an der Schwelle = 100). **„Für dich“** vergleicht sie mit
  deiner aktuellen Fitness (CTL): „mittel“ entspricht etwa einem normalen Trainingstag.
- **Dauer nach Strecke** (z. B. 6 × 1 km) wird aus deinem Tempo berechnet.

| Zone | Rad (% FTP) | Laufen (% Schwellentempo) | Schwimmen (% CSS-Tempo) |
|---|---|---|---|
| Regeneration | bis 55 | bis 77 | bis 85 |
| Grundlage | 56–75 | 78–88 | 86–92 |
| Tempo | 76–90 | 89–94 | 93–97 |
| Schwelle | 91–105 | 95–102 | 98–102 |
| VO2max | 106–120 | 103–111 | 103–108 |
| Anaerob | 121–150 | 112–122 | 109–117 |
| Sprint | über 150 | über 122 | über 117 |

Rad nach Coggan, Laufen nach den Pace-Zonen von Joe Friel (auf Tempo umgerechnet), Schwimmen nach
gängigen CSS-Bereichen. Rund 80 % des Trainings sollte locker sein – harte Kategorien sparsam einsetzen.
        """
    )
