from datetime import date

import pandas as pd
import streamlit as st

from triathlon import charts, hevy, strength
from triathlon.units import WEEKDAYS

st.title("Krafttraining")
tab_log, tab_history, tab_progress, tab_plans, tab_hevy = st.tabs(
    ["Training eintragen", "Verlauf", "Fortschritt", "Pläne bearbeiten", "Hevy"]
)

plans = strength.templates()
next_plan = (strength.rotation(1) or [None])[0]

# ------------------------------------------------------------------ Eintragen
with tab_log:
    if hevy.is_configured():
        st.caption("Im Gym trägst du in der Hevy-App ein – hier nur, wenn du etwas nachtragen willst.")
    if not plans:
        st.info("Noch keine Trainingspläne – leg unter „Pläne bearbeiten“ einen an.")
    else:
        st.caption("Rotation: " + " → ".join(p["name"] for p in plans)
                   + ". Vorausgewählt ist das nächste Training nach deinem letzten Eintrag.")
        ids = [p["id"] for p in plans]
        c1, c2 = st.columns(2)
        chosen = c1.selectbox(
            "Training", plans, index=ids.index(next_plan["id"]) if next_plan else 0,
            format_func=lambda p: p["name"] + (" (nächstes in der Rotation)" if next_plan and p["id"] == next_plan["id"] else ""),
        )
        day = c2.date_input("Datum", value=date.today(), format="DD.MM.YYYY")
        exercises = strength.template_exercises(chosen["id"])

        with st.form(f"log_{chosen['id']}_{day}"):
            st.caption("Vorausgefüllt mit dem Vorschlag – trag ein, was du wirklich geschafft hast. "
                       "Zeilen ohne Wiederholungen werden ignoriert.")
            entries = []
            for i in range(0, len(exercises), 2):
                for col, ex in zip(st.columns(2, gap="large"), exercises[i:i + 2]):
                    with col:
                        last_day, last = strength.last_sets(ex["id"], before=day)
                        sug = strength.suggest(ex["rep_min"], ex["rep_max"], ex["increment_kg"], last)
                        head, toggle = st.columns([3, 1])
                        head.markdown(f"**{ex['name']}** · {ex['rep_min']}–{ex['rep_max']} Wdh.")
                        done = toggle.checkbox("gemacht", value=True, key=f"done_{chosen['id']}_{ex['id']}_{day}")
                        if last:
                            hint = (f"Letztes Mal ({date.fromisoformat(last_day):%d.%m.}): "
                                    f"{strength.describe_sets(last)}")
                            if sug:
                                hint += f"  \n**Vorschlag: {sug.weight:g} kg × {sug.reps}** – {sug.note}"
                            st.caption(hint)
                        else:
                            st.caption("Noch keine Einträge – trag ein, was du geschafft hast.")
                        n_sets = ex["target_sets"] or max(len(last), 3)
                        start = pd.DataFrame({
                            "Gewicht (kg)": pd.Series([sug.weight if sug else None] * n_sets, dtype="float"),
                            "Wdh.": pd.Series([sug.reps if sug else None] * n_sets, dtype="float"),
                        })
                        edited = st.data_editor(
                            start, key=f"sets_{chosen['id']}_{ex['id']}_{day}", num_rows="dynamic",
                            hide_index=True,
                            column_config={
                                "Gewicht (kg)": st.column_config.NumberColumn(min_value=0.0, step=0.5,
                                                                              format="%.1f"),
                                "Wdh.": st.column_config.NumberColumn(min_value=0, step=1, format="%d"),
                            },
                        )
                        entries.append((ex, done, edited))

            st.divider()
            c1, c2 = st.columns(2)
            duration = c1.number_input("Dauer (Minuten)", min_value=5, max_value=300, value=60, step=5)
            rpe = c2.slider("Wie anstrengend insgesamt? (RPE 1–10)", 1, 10, 7)
            notes = st.text_input("Notiz (optional)")
            if st.form_submit_button("Training speichern", type="primary", icon=":material/save:"):
                sets = []
                for ex, done, edited in entries:
                    if not done:
                        continue
                    set_no = 0
                    for row in edited.itertuples(index=False):
                        weight, reps = row[0], row[1]
                        if pd.isna(reps) or reps <= 0:
                            continue
                        set_no += 1
                        sets.append((ex["id"], set_no, None if pd.isna(weight) else float(weight), int(reps), None))
                if not sets:
                    st.error("Keine Sätze eingetragen.")
                else:
                    strength.save_session(day, chosen["id"], int(duration), float(rpe), notes, sets)
                    st.toast(f"{chosen['name']} gespeichert – {len(sets)} Sätze. Stark! 💪", icon="✅")
                    st.rerun()

# ------------------------------------------------------------------ Verlauf
with tab_history:
    sessions = strength.sessions_df(limit=40)
    if sessions.empty:
        st.caption("Noch keine Einheiten eingetragen.")
    for row in sessions.itertuples():
        day_of = date.fromisoformat(row.date)
        title = (f"{WEEKDAYS[day_of.weekday()]} {day_of:%d.%m.%Y} · {row.plan} · {row.saetze} Sätze · "
                 f"{row.volumen:,.0f} kg Volumen".replace(",", "."))
        from_hevy = isinstance(row.hevy_id, str) and bool(row.hevy_id)
        if from_hevy:
            title += " · aus Hevy"
        with st.expander(title):
            st.dataframe(strength.session_sets(row.id).drop(columns=["rpe"]), hide_index=True, width="stretch",
                         column_config={"uebung": "Übung", "satz": "Satz", "gewicht": "Gewicht (kg)", "wdh": "Wdh."})
            meta = []
            if pd.notna(row.duration_min) and row.duration_min:
                meta.append(f"Dauer {row.duration_min:.0f} min")
            if pd.notna(row.rpe) and row.rpe:
                meta.append(f"RPE {row.rpe:g}")
            if isinstance(row.notes, str) and row.notes:
                meta.append(row.notes)
            st.caption(" · ".join(meta))
            if from_hevy:
                st.caption("Änderungen bitte in Hevy machen – beim nächsten Sync wird die Einheit überschrieben.")
            if st.button("Einheit löschen", key=f"del_{row.id}", icon=":material/delete:"):
                strength.delete_session(row.id)
                st.rerun()

# ------------------------------------------------------------------ Fortschritt
with tab_progress:
    all_ex = strength.all_exercises()
    histories = {ex["name"]: strength.exercise_history(ex["id"]) for ex in all_ex}
    histories = {name: h for name, h in histories.items() if not h.empty}
    if not histories:
        st.caption("Sobald du Trainings einträgst, siehst du hier deine Entwicklung pro Übung.")
    else:
        history = histories[st.selectbox("Übung", list(histories))]
        c1, c2, c3 = st.columns(3)
        best = history["e1rm"].max()
        c1.metric("Bestes geschätztes Maximum (1RM)", f"{best:.1f} kg" if pd.notna(best) else "–",
                  help="Geschätzt aus Gewicht und Wiederholungen (Epley-Formel).")
        c2.metric("Letztes Topgewicht", f"{history['top_weight'].iloc[-1]:g} kg")
        c3.metric("Einheiten", len(history))
        if history["e1rm"].notna().any():
            charts.show(charts.e1rm_chart(history))
        with st.expander("Als Tabelle"):
            st.dataframe(pd.DataFrame({
                "Datum": history["date"].dt.strftime("%d.%m.%Y"),
                "Topgewicht (kg)": history["top_weight"],
                "Beste Wdh.": history["best_reps"],
                "Sätze": history["sets"],
                "Volumen (kg)": history["volume"].round(0),
                "1RM geschätzt (kg)": history["e1rm"].round(1),
            }), hide_index=True, width="stretch")

# ------------------------------------------------------------------ Pläne
with tab_plans:
    st.caption("Die Rotation läuft in der Reihenfolge der Position. „Unterkörper“ markiert Beintage – "
               "die Empfehlungen legen sie dann nicht direkt vor harte Lauf-/Radeinheiten.")
    exercise_names = {ex["name"]: ex["id"] for ex in strength.all_exercises()}

    for plan in plans:
        with st.expander(f"{plan['position'] + 1}. {plan['name']}"):
            with st.form(f"plan_{plan['id']}"):
                c1, c2, c3 = st.columns([3, 1, 1])
                name = c1.text_input("Name", value=plan["name"])
                position = c2.number_input("Position", min_value=1, value=plan["position"] + 1, step=1)
                lower = c3.checkbox("Unterkörper", value=bool(plan["lower_body"]))
                current = pd.DataFrame(
                    [{"Übung": ex["name"], "Sätze": ex["target_sets"]} for ex in strength.template_exercises(plan["id"])],
                    columns=["Übung", "Sätze"],
                )
                edited = st.data_editor(
                    current, num_rows="dynamic", hide_index=True, key=f"plan_ex_{plan['id']}",
                    column_config={
                        "Übung": st.column_config.SelectboxColumn(options=sorted(exercise_names), required=True),
                        "Sätze": st.column_config.NumberColumn(min_value=1, max_value=10, step=1, default=3),
                    },
                )
                if st.form_submit_button("Plan speichern", icon=":material/save:"):
                    rows = [(exercise_names[r["Übung"]], int(r["Sätze"] or 3))
                            for r in edited.to_dict("records") if r.get("Übung") in exercise_names]
                    strength.update_template(plan["id"], name, int(position) - 1, lower)
                    strength.set_template_exercises(plan["id"], rows)
                    st.toast("Plan gespeichert.", icon="✅")
                    st.rerun()
            if st.button("Plan löschen", key=f"del_plan_{plan['id']}", icon=":material/delete:"):
                strength.delete_template(plan["id"])
                st.rerun()

    st.markdown("**Neuen Plan anlegen**")
    with st.form("new_plan", clear_on_submit=True):
        c1, c2 = st.columns([3, 1])
        new_name = c1.text_input("Name", placeholder="z. B. Ganzkörper")
        new_lower = c2.checkbox("Unterkörper")
        if st.form_submit_button("Anlegen") and new_name.strip():
            strength.add_template(new_name, new_lower)
            st.rerun()

    st.divider()
    st.markdown("**Übungen**")
    st.caption("Wiederholungsbereich und Steigerung steuern die Vorschläge: Schaffst du in allen Sätzen das "
               "obere Ende, schlägt das Dashboard beim nächsten Mal mehr Gewicht vor.")
    library = pd.DataFrame(strength.all_exercises())
    if not library.empty:
        edited_lib = st.data_editor(
            library[["id", "name", "rep_min", "rep_max", "increment_kg"]], hide_index=True, key="exercise_library",
            disabled=["id", "name"],
            column_config={
                "id": None,
                "name": "Übung",
                "rep_min": st.column_config.NumberColumn("Wdh. min", min_value=1, max_value=50, step=1),
                "rep_max": st.column_config.NumberColumn("Wdh. max", min_value=1, max_value=50, step=1),
                "increment_kg": st.column_config.NumberColumn("Steigerung (kg)", min_value=0.0, step=0.5),
            },
        )
        if st.button("Übungen speichern", icon=":material/save:"):
            for r in edited_lib.to_dict("records"):
                strength.update_exercise(int(r["id"]), int(r["rep_min"]), int(r["rep_max"]), float(r["increment_kg"]))
            st.toast("Übungen gespeichert.", icon="✅")
    with st.form("new_exercise", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
        ex_name = c1.text_input("Neue Übung", placeholder="z. B. Face Pulls")
        rep_min = c2.number_input("Wdh. min", 1, 50, 8)
        rep_max = c3.number_input("Wdh. max", 1, 50, 12)
        inc = c4.number_input("Steigerung (kg)", 0.0, 20.0, 2.5, step=0.5)
        if st.form_submit_button("Übung hinzufügen") and ex_name.strip():
            strength.add_exercise(ex_name, int(rep_min), int(rep_max), float(inc))
            st.toast("Übung angelegt – jetzt einem Plan hinzufügen.", icon="✅")
            st.rerun()

# ------------------------------------------------------------------ Hevy
with tab_hevy:
    if not hevy.is_configured():
        st.info("Mit Hevy trägst du im Gym direkt am Handy ein, und das Dashboard holt die Workouts automatisch. "
                "Einrichten unter **Einstellungen → Krafttraining (Hevy)**.", icon=":material/smartphone:")
    else:
        st.caption("Ablauf: **1.** Übungen zuordnen → **2.** Pläne an Hevy senden → **3.** im Gym die Routine in "
                   "Hevy starten → **4.** „Jetzt synchronisieren“. Die Gewichtsvorschläge stehen dann schon in Hevy.")

        # 1. Übungen zuordnen
        st.markdown("**1. Übungen zuordnen**")
        labels = hevy.template_labels()
        if st.button("Übungsliste von Hevy laden", icon=":material/download:",
                     help="Lädt alle Hevy-Übungen und ordnet bekannte Übungen automatisch zu."):
            try:
                with st.spinner("Lade Übungen aus Hevy …"):
                    n = hevy.sync_exercise_templates()
                    mapped = hevy.auto_map_exercises()
                st.toast(f"{n} Hevy-Übungen geladen, {mapped} automatisch zugeordnet.", icon="✅")
                st.rerun()
            except hevy.HevyError as exc:
                st.error(str(exc))
        if not labels:
            st.caption("Noch keine Hevy-Übungen geladen – klick auf „Übungsliste von Hevy laden“.")
        else:
            id_to_label = {template_id: label for label, template_id in labels.items()}
            rows = hevy.mapping_table()
            table = pd.DataFrame({
                "id": [r["id"] for r in rows],
                "Übung": [r["name"] for r in rows],
                "Im Plan": [bool(r["in_plan"]) for r in rows],
                "Hevy-Übung": [id_to_label.get(r["hevy_template_id"]) for r in rows],
            })
            edited_map = st.data_editor(
                table, hide_index=True, key="hevy_mapping", disabled=["Übung", "Im Plan"],
                column_config={
                    "id": None,
                    "Hevy-Übung": st.column_config.SelectboxColumn(options=sorted(labels), required=False),
                },
            )
            if st.button("Zuordnung speichern", icon=":material/save:"):
                chosen_ids = [labels.get(v) if isinstance(v, str) else None for v in edited_map["Hevy-Übung"]]
                used = [c for c in chosen_ids if c]
                doubles = sorted({id_to_label[c] for c in used if used.count(c) > 1})
                if doubles:
                    st.error("Jede Hevy-Übung darf nur einer Übung zugeordnet sein: " + ", ".join(doubles))
                else:
                    for exercise_id, template_id in zip(edited_map["id"], chosen_ids):
                        hevy.set_mapping(int(exercise_id), template_id)
                    st.toast("Zuordnung gespeichert.", icon="✅")
                    st.rerun()

        # 2. Pläne senden
        st.markdown("**2. Pläne an Hevy senden**")
        for plan in plans:
            exercises = strength.template_exercises(plan["id"])
            missing = [ex["name"] for ex in exercises if not ex.get("hevy_template_id")]
            status = "✅ in Hevy" if plan.get("hevy_routine_id") else "⚪ noch nicht gesendet"
            text = f"{status} · **{plan['name']}** · {len(exercises)} Übungen"
            if missing:
                text += f" · ohne Zuordnung: {', '.join(missing)}"
            st.markdown(text)
        if st.button("Pläne an Hevy senden", type="primary", icon=":material/send:", disabled=not plans,
                     help="Legt jeden Plan als Routine in Hevy an bzw. aktualisiert sie – mit den aktuellen "
                          "Gewichtsvorschlägen."):
            with st.spinner("Sende Pläne an Hevy …"):
                results = hevy.push_routines()
            for plan_name, ok, message in results:
                (st.success if ok else st.warning)(f"**{plan_name}:** {message}")

        # 3. Workouts holen
        st.markdown("**3. Workouts aus Hevy holen**")
        st.caption("Passiert auch automatisch über „Jetzt synchronisieren“ in der Seitenleiste.")
        if st.button("Jetzt Workouts laden", icon=":material/sync:"):
            try:
                with st.spinner("Lade Workouts aus Hevy …"):
                    n = hevy.sync_workouts()
                st.toast(f"{n} Workouts aus Hevy geladen.", icon="✅")
                st.rerun()
            except hevy.HevyError as exc:
                st.error(str(exc))
