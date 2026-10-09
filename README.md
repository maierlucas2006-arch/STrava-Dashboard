# Triathlon Dashboard

Persönliches Dashboard, das dein Triathlon-Training steuert – läuft lokal auf deinem PC.

| Bereich | Was es macht |
|---|---|
| **Übersicht** | Tagesempfehlung mit Ampel, Fitness/Ermüdung/Form, HRV, Ruhepuls, Schlaf, Wochenfortschritt |
| **Trainingsplan** | Phasen bis zum Wettkampf, Wochenplan mit konkreten Einheiten (Watt, Pace, Puls), Fitness-Prognose |
| **Ausdauer** | Alle Strava-Aktivitäten mit Trainingsbelastung (TSS), Umfang pro Woche |
| **Regeneration** | HRV mit persönlichem Normalbereich, Ruhepuls, Schlaf, Gewicht (Garmin über intervals.icu) |
| **Krafttraining** | Tagebuch mit Rotation (Brust/Rücken → Arme → Beine), Vorschläge fürs nächste Gewicht, Fortschritt |
| **Ernährung** | Kalorien & Makros, Lebensmittel-Suche (Open Food Facts), Ziele passen sich ans Training an |
| **Ziele** | Eigene Ziele, teils automatisch gemessen (z. B. Fitness, Lauf-km pro Woche, Gewicht) |

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

## 4. Schwellenwerte eintragen (wichtig für gute Empfehlungen)

Unter **Einstellungen → Athletenprofil**:

| Wert | Wofür | Wie ermitteln |
|---|---|---|
| FTP (Watt) | Rad-Belastung & Wattbereiche | aus Strava übernehmen oder FTP-Test |
| Max. Puls / Schwellenpuls | Puls-Bereiche, Belastung ohne Watt | höchster gemessener Wert / 30-min-Test |
| Schwellen-Pace (min/km) | Lauf-Belastung & Pace-Bereiche | Tempo, das du ~60 min halten kannst |
| CSS (min/100 m) | Schwimm-Belastung & Tempi | 400 m + 200 m Test: (Zeit400 − Zeit200) / 2 |
| Größe, Geburtsjahr | Kalorienbedarf | – |

Verletzt? Unter *Sportart pausieren* z. B. Laufen auswählen – der Plan ersetzt es dann durch Rad oder Schwimmen.

## Wie die Empfehlungen entstehen

- **Belastung (TSS)** pro Einheit aus Watt (nur echter Wattmesser), Pace, Schwimmtempo oder Puls.
- **Fitness (CTL)** = Schnitt der letzten ~6 Wochen, **Ermüdung (ATL)** = letzte ~7 Tage,
  **Form (TSB)** = Fitness − Ermüdung.
- **Ampel:** HRV-Trend gegen deinen 60-Tage-Normalbereich, Ruhepuls gegen deinen 30-Tage-Schnitt,
  Schlaf und Form. Gelb = harte Einheiten werden locker, Rot = Erholung.
- **Plan:** Phasen (Vorbereitung → Grundlage → Aufbau → Spitze → Tapering) rückwärts vom Wettkampf,
  Wochenumfang so, dass deine Fitness kontrolliert Richtung Ziel-CTL steigt.

Das Dashboard ist eine Entscheidungshilfe und ersetzt keinen Trainer oder Arzt.

## Für Entwickler

```
pip install -r requirements-dev.txt
pytest
```

Aufbau: `app.py` (Einstieg/Navigation), `views/` (Seiten), `triathlon/` (Logik: `load.py` Belastung,
`recovery.py` Ampel, `plan.py` Periodisierung & Empfehlung, `strava.py`/`intervals.py` Datenquellen).
