# Triathlon Dashboard

Persönliches Dashboard, das dein Triathlon-Training steuert – läuft lokal auf deinem PC.

| Bereich | Was es macht |
|---|---|
| **Übersicht** | Die letzten 14 Tage als Intensitätsprofil, Ampel mit passenden Kategorien für heute, Fitness/Ermüdung/Form, HRV, Ruhepuls, Schlaf, Wochenfortschritt |
| **Trainingsgalerie** | 162 Einheiten für Rad, Laufen, Schwimmen und Koppeltraining in 11 Kategorien (Regeneration bis Sprint), jede mit Intensitätsprofil und deinen Zielwerten (Watt, Pace, CSS) |
| **Ausdauer** | Alle Strava-Aktivitäten mit Trainingsbelastung (TSS), Umfang pro Woche |
| **Regeneration** | HRV mit persönlichem Normalbereich, Ruhepuls, Schlaf, Gewicht (Garmin über intervals.icu) |
| **Krafttraining** | Rotation (Brust/Rücken → Arme → Beine), Vorschläge fürs nächste Gewicht, Fortschritt – im Gym per wger-App am Handy |
| **Ernährung** | Kalorien & Makros, Lebensmittel-Suche (Open Food Facts), Ziele passen sich ans Training an |
| **Ziele** | Phasen bis zum Wettkampf mit Fitness-Prognose, eigene Ziele, teils automatisch gemessen (z. B. Fitness, Lauf-km pro Woche, Gewicht) |

Alle Daten liegen nur bei dir in `data/dashboard.db`.

---

## 1. Einrichten in PyCharm (einmalig)

1. **Projekt holen:** PyCharm → *File → New → Project from Version Control* →
   URL `https://github.com/maierlucas2006-arch/STrava-Dashboard` → *Clone*.
   Danach unten rechts den Branch `claude/triathlon-dashboard-project-ypvsg3` auswählen
   (bzw. `main`, sobald er gemergt ist).
2. **Python-Umgebung:** PyCharm fragt meistens von selbst, ob es eine virtuelle Umgebung anlegen und
   `requirements.txt` installieren soll → **OK**.
   Falls nicht: unten auf *Terminal* klicken und eingeben:
   ```
   pip install -r requirements.txt
   ```
3. **Starten:** Rechtsklick auf **`start.py`** → **Run 'start'**.
   Der Browser öffnet sich auf <http://localhost:8501>. Beenden: rotes Quadrat in PyCharm.

> Erst mal nur anschauen? Rechtsklick auf **`start_demo.py`** → *Run*. Das startet das Dashboard mit
> erfundenen Beispieldaten (eigene Datenbank, deine echten Daten bleiben unberührt).

## 2. Strava verbinden

1. Auf [strava.com/settings/api](https://www.strava.com/settings/api) eine App anlegen:
   - Application Name: z. B. *Triathlon Dashboard*
   - Category: *Training*, Website: `http://localhost`
   - **Authorization Callback Domain: `localhost`**
2. Im Dashboard unter **Einstellungen → Strava** die *Client ID* und das *Client Secret* eintragen → Speichern.
3. **„Mit Strava verbinden“** klicken und bei Strava bestätigen.
4. Links auf **„Jetzt synchronisieren“** klicken. Beim ersten Mal wird das letzte Jahr geladen.
5. Unter Einstellungen **„Profil übernehmen“** holt Gewicht und FTP aus Strava.

Hinweis: Seit Juni 2026 setzt Strava für den API-Zugang ein aktives Abo voraus (hast du).

## 3. Garmin verbinden (über intervals.icu)

Garmin hat keine offizielle Schnittstelle für Privatpersonen. Der stabile Weg führt über intervals.icu:

1. Kostenloses Konto auf [intervals.icu](https://intervals.icu) anlegen.
2. Dort *Settings → Connections → Garmin Connect* verbinden und die Gesundheitsdaten (Wellness) erlauben.
3. *Settings → Developer Settings* → **API Key** erzeugen.
4. Im Dashboard unter **Einstellungen → Garmin** den Key eintragen → *Verbindung testen* → synchronisieren.

Die HRV-Ampel braucht mindestens 14 Nächte Daten, bevor sie deinen Normalbereich kennt.

## 4. Krafttraining mit wger (Handy im Gym, kostenlos)

Im Gym trägst du Gewicht und Wiederholungen in der kostenlosen Open-Source-App **wger** ein
(iPhone und Android), das Dashboard holt die Sätze automatisch.

1. Konto auf [wger.de](https://wger.de) anlegen, App *wger Workout Manager* installieren und anmelden.
2. Auf [wger.de/de/user/api-key](https://wger.de/de/user/api-key) einen **API-Key** erzeugen.
3. Im Dashboard unter **Einstellungen → Krafttraining (wger)** eintragen → *Verbindung testen*.
4. **Krafttraining → wger:** *Übungsliste von wger laden* (ordnet bekannte Übungen automatisch zu),
   fehlende Zuordnungen in der Tabelle auswählen → *Zuordnung speichern*.
5. **Pläne an wger senden:** Es entsteht die Routine „Triathlon-Kraft“ mit einem Trainingstag je Plan,
   inklusive Sätzen, Ziel-Wiederholungen, Gewichtsvorschlag und 90 s Pause. Der nächste Tag kommt erst,
   wenn der aktuelle eingetragen ist – wie die Rotation im Dashboard.
6. Im Gym in der App den Trainingstag starten und Sätze eintragen. Danach links **„Jetzt synchronisieren“**:
   Verlauf, Fortschritt, Rotation und Belastung werden aktualisiert, die Routine bekommt neue Vorschläge.

Sätze auf Zeit oder Strecke werden nicht übernommen, Pfund werden in kg umgerechnet. Eine wger-Routine
gilt höchstens 120 Tage; das Dashboard erinnert rechtzeitig daran, die Pläne neu zu senden.

Mit **Hevy Pro** geht dasselbe auch mit Hevy (Einstellungen → „Alternativ: Hevy“).

## 5. Schwellenwerte eintragen (wichtig für gute Empfehlungen)

Unter **Einstellungen → Athletenprofil**:

| Wert | Wofür | Wie ermitteln |
|---|---|---|
| FTP (Watt) | Rad-Belastung & Wattbereiche | aus Strava übernehmen oder FTP-Test |
| Max. Puls / Schwellenpuls | Puls-Bereiche, Belastung ohne Watt | höchster gemessener Wert / 30-min-Test |
| Schwellen-Pace (min/km) | Lauf-Belastung & Pace-Bereiche | Tempo, das du ~60 min halten kannst |
| CSS (min/100 m) | Schwimm-Belastung & Tempi | 400 m + 200 m Test: (Zeit400 − Zeit200) / 2 |
| Größe, Geburtsjahr | Kalorienbedarf | – |

Verletzt? Unter *Sportart pausieren* z. B. Laufen auswählen – der Plan ersetzt es dann durch Rad oder Schwimmen.

## Trainingsgalerie

Jede Einheit ist als kurze Formel notiert (`triathlon/library.py`), z. B. `15min@58, 2x(20min@90, 5min@55), 10min@50`:
Dauer oder Strecke, `@` Prozent der Schwelle (Rad: FTP, Laufen: Schwellentempo, Schwimmen: CSS),
`3x(…)` Wiederholungen, `r20` Pause, `[…]` Hinweis. Daraus entstehen Blockgrafik, Zielwerte, Dauer und TSS.
Neue Einheiten: eine Zeile in `_ROWS` ergänzen – die Tests prüfen automatisch, ob Formel und Kategorie zusammenpassen.

| Zone | Rad (% FTP, Coggan) | Laufen (% Schwellentempo, Friel) | Schwimmen (% CSS-Tempo) |
|---|---|---|---|
| Regeneration | bis 55 | bis 77 | bis 85 |
| Grundlage | 56–75 | 78–88 | 86–92 |
| Tempo | 76–90 | 89–94 | 93–97 |
| Schwelle | 91–105 | 95–102 | 98–102 |
| VO2max | 106–120 | 103–111 | 103–108 |
| Anaerob | 121–150 | 112–122 | 109–117 |
| Sprint | über 150 | über 122 | über 117 |

## Design

Theme in `.streamlit/config.toml` (hell und dunkel, Schriften Newsreader und Archivo von Google Fonts),
Feinschliff und Galerie-Bausteine in `triathlon/visual.py`. Die Zonenfarben sind auf Farbsehschwäche geprüft.

## Wie die Empfehlungen entstehen

- **Belastung (TSS)** pro Einheit aus Watt (nur echter Wattmesser), Pace, Schwimmtempo oder Puls.
- **Fitness (CTL)** = Schnitt der letzten ~6 Wochen, **Ermüdung (ATL)** = letzte ~7 Tage,
  **Form (TSB)** = Fitness − Ermüdung.
- **Ampel:** HRV-Trend gegen deinen 60-Tage-Normalbereich, Ruhepuls gegen deinen 30-Tage-Schnitt,
  Schlaf und Form. Gelb = nur Regeneration, Grundlage und Technik, Rot = Regeneration.
- **Phasen:** Vorbereitung → Grundlage → Aufbau → Spitze → Tapering, rückwärts vom Wettkampf. Jede Phase hat
  Schwerpunkt-Kategorien in der Galerie; die Ampel grenzt sie für heute ein („Nur, was heute passt“).
- **Wochenziel:** Belastung so, dass deine Fitness kontrolliert Richtung Ziel-CTL steigt.

Das Dashboard ist eine Entscheidungshilfe und ersetzt keinen Trainer oder Arzt.

## Für Entwickler

```
pip install -r requirements-dev.txt
pytest
```

Aufbau: `app.py` (Einstieg/Navigation), `views/` (Seiten), `triathlon/` (Logik: `load.py` Belastung,
`recovery.py` Ampel, `plan.py` Periodisierung, `library.py` Trainingsgalerie, `strava.py`/`intervals.py`/`wger.py`/`hevy.py` Datenquellen).
