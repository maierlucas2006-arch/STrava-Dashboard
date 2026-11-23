# Triathlon Dashboard

Dashboard, das Triathlon-Training steuert – lokal auf deinem PC oder online für mehrere Personen.

| Bereich | Was es macht |
|---|---|
| **Übersicht** | Morgen-Check (4 Fragen), Ampel mit passenden Kategorien für heute, die letzten 14 Tage als Intensitätsprofil, Fitness/Ermüdung/Form, HRV, Ruhepuls, Schlaf, Wochenfortschritt |
| **Trainingsgalerie** | 162 Einheiten für Rad, Laufen, Schwimmen und Koppeltraining in 11 Kategorien (Regeneration bis Sprint), jede mit Intensitätsprofil und deinen Zielwerten (Watt, Pace, CSS) |
| **Ausdauer** | Alle Strava-Aktivitäten mit Trainingsbelastung (TSS), Umfang pro Woche, Monotonie und Strain |
| **Regeneration** | HRV mit persönlichem Normalbereich, Ruhepuls, Schlaf, Gewicht (Garmin über intervals.icu), Verlauf des Morgen-Checks |
| **Krafttraining** | Rotation (Brust/Rücken → Arme → Beine), Vorschläge fürs nächste Gewicht, Fortschritt – im Gym per wger-App am Handy |
| **Ernährung** | Kalorien & Makros, Lebensmittel-Suche (Open Food Facts), Ziele passen sich ans Training an, Energieverfügbarkeit |
| **Ziele** | Phasen bis zum Wettkampf mit Fitness-Prognose, eigene Ziele, teils automatisch gemessen (z. B. Fitness, Lauf-km pro Woche, Gewicht) |
| **Tageswerte** | Alle Kennzahlen in einer Zeile pro Tag, als CSV für Excel |
| **Einstellungen** | Verbindungen, Profil, Schwellen – und unter *Deine Daten*: alles herunterladen (ZIP), Datenschutzhinweis, Konto löschen |

Jede Person meldet sich mit ihrem Google-Konto an und arbeitet mit ihren eigenen Daten (eine Datei pro Konto unter `data/users/`). Passwörter speichert das Dashboard nicht. Vor der ersten Nutzung erscheint ein Datenschutzhinweis mit Einwilligung; beim Öffnen holt das Dashboard neue Daten automatisch, wenn der letzte Abgleich mehr als 3 Stunden her ist.

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

## Anmeldung einrichten (einmalig, ca. 10 Minuten)

Den Login übernimmt Streamlit (`st.login`, OpenID Connect) mit Google-Konten.

1. **Google Cloud:** Auf [console.cloud.google.com](https://console.cloud.google.com) ein Projekt anlegen.
   Unter *Google Auth Platform → Branding* auf **Get started** klicken, App-Name und E-Mail eintragen,
   Zielgruppe **Extern**.
2. **Testnutzer:** Unter *Zielgruppe (Audience) → Testnutzer* die eigene Google-Adresse eintragen. Solange die
   App im Test ist, können sich nur eingetragene Testnutzer anmelden; für alle öffnest du sie mit
   „App veröffentlichen“.
3. **Client:** Unter *Clients → Client erstellen* den Typ **Webanwendung** wählen, als autorisierte
   Weiterleitungs-URI `http://localhost:8501/oauth2callback` eintragen und **Client-ID** und
   **Clientschlüssel** kopieren (der Schlüssel wird nur einmal angezeigt).
4. **Secrets:** Am einfachsten Rechtsklick auf **`setup_login.py`** → *Run*: Adresse mit Enter bestätigen,
   Client-ID und Clientschlüssel einfügen, optional deine Strava-Schlüssel und deinen Namen für den
   Datenschutzhinweis. Das Skript schreibt `.streamlit/secrets.toml` samt Cookie-Schlüssel und behält beim
   erneuten Start alles, was du mit Enter bestätigst. Alternativ
   `.streamlit/secrets.example.toml` nach `.streamlit/secrets.toml` kopieren und die Werte eintragen. Den `cookie_secret` erzeugst du im Terminal mit
   `python -c "import secrets; print(secrets.token_hex(32))"`. `secrets.toml` steht in `.gitignore` und
   landet nie im Git.
5. `pip install -r requirements.txt` (neu: `streamlit[auth]` mit Authlib und httpx), dann `start.py` starten und
   **Mit Google anmelden**.
6. **Bisherige Daten:** Lagen schon Daten in `data/dashboard.db`, erscheint nach der Anmeldung unter
   *Einstellungen* der Knopf **In mein Konto übernehmen** – einmal klicken, fertig.

`start_demo.py` und die Tests laufen ohne Anmeldung.

Fürs Online-Stellen siehe [Online stellen](#online-stellen-deployment).

## 2. Strava verbinden

**Zentral für alle (empfohlen, sobald mehrere Personen das Dashboard nutzen):** Deine Strava-Schlüssel
einmal mit `setup_login.py` in `secrets.toml` hinterlegen (Abschnitt `[strava]`). Dann sieht jede Person unter
*Einstellungen → Strava* nur noch **„Mit Strava verbinden“**. Eine neue Strava-App lässt nur dich selbst zu;
unter strava.com/settings/api kannst du sie ohne Prüfung auf bis zu 10 Personen erweitern, für mehr braucht es
eine Prüfung durch Strava.

**Nur für dich:**

1. Auf [strava.com/settings/api](https://www.strava.com/settings/api) eine App anlegen:
   - Application Name: z. B. *Triathlon Dashboard*
   - Category: *Training*, Website: `http://localhost`
   - **Authorization Callback Domain: `localhost`**
2. Im Dashboard unter **Einstellungen → Strava** die *Client ID* und das *Client Secret* eintragen → Speichern.
3. **„Mit Strava verbinden“** klicken und bei Strava bestätigen.
4. Die Daten kommen automatisch (oder links **„Jetzt synchronisieren“**). Beim ersten Mal wird das letzte Jahr geladen.
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
| Körperfett (%) | Energieverfügbarkeit (fettfreie Masse) | Körperfettwaage, Caliper; leer = Schätzwert |

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
  Schlaf, Form und der Morgen-Check. Gelb = nur Regeneration, Grundlage und Technik, Rot = Regeneration.
- **Morgen-Check (Hooper & Mackinnon 1995):** Schlafqualität, Müdigkeit, Stress und Muskelkater je 1–7, die Summe
  ist der Hooper-Index (4–28). Auffällig ist ein Tag mehr als 1,5 Standardabweichungen über deinem 60-Tage-Schnitt.
- **Monotonie und Strain (Foster 1998):** Ø Tagesbelastung ÷ Streuung über 7 Tage; über 2 kommt ein Hinweis,
  harte und leichte Tage abzuwechseln. Strain = Wochenbelastung × Monotonie.
- **Energieverfügbarkeit (Loucks 2011, IOC-Konsens 2023):** (Gegessen − Trainingsverbrauch) ÷ fettfreie Masse;
  unter 30 kcal/kg niedrig, 30–45 reduziert, ab 45 ausreichend.
- **Phasen:** Vorbereitung → Grundlage → Aufbau → Spitze → Tapering, rückwärts vom Wettkampf. Jede Phase hat
  Schwerpunkt-Kategorien in der Galerie; die Ampel grenzt sie für heute ein („Nur, was heute passt“).
- **Wochenziel:** Belastung so, dass deine Fitness kontrolliert Richtung Ziel-CTL steigt.

Das Dashboard ist eine Entscheidungshilfe und ersetzt keinen Trainer oder Arzt.

## Für Entwickler

```
pip install -r requirements-dev.txt
pytest
```

Aufbau: `app.py` (Einstieg/Navigation), `views/` (Seiten), `triathlon/` (Logik: `load.py` Belastung und Monotonie,
`recovery.py` Ampel und Morgen-Check, `nutrition.py` Ernährung und Energieverfügbarkeit, `plan.py` Periodisierung,
`library.py` Trainingsgalerie, `auth.py` Konten, `storage.py` Sicherung beim Hoster, `export.py` Datenexport, `privacy.py` Datenschutzhinweis,
`strava.py`/`intervals.py`/`wger.py`/`hevy.py` Datenquellen), `serve.py` (Start beim Hoster), `deploy/` (Server-Vorlagen).

## Online stellen (Deployment)

Jedes Konto ist eine SQLite-Datei. Der Hoster muss sie also dauerhaft behalten – oder das Dashboard sichert sie
nach jeder Änderung in einen Cloud-Speicher und holt sie beim nächsten Start zurück (`triathlon/storage.py`).

### Weg A: kostenlos – Streamlit Community Cloud + Backblaze B2

Streamlit Community Cloud betreibt das Dashboard, Backblaze B2 (bis 10 GB kostenlos, ohne Kreditkarte) sichert
die Konten. Grenzen: Nach 12 Stunden ohne Besuch schläft die App ein und wacht per Knopf wieder auf, die Server
stehen in den USA, und es gibt rund 1 GB Arbeitsspeicher.

1. **Backblaze:** Konto auf [backblaze.com](https://www.backblaze.com/sign-up/cloud-storage) anlegen (Region
   *EU Central*). *Buckets → Create a Bucket:* privat. Unter *Lifecycle Settings* **„Keep only the last version of
   the file“** wählen, sonst sammelt sich jede Sicherung an. *Application Keys → Add a New Application Key:* nur
   für diesen Bucket, *Read and Write*. Notieren: `keyID`, `applicationKey` und den **S3-Endpoint** des Buckets.
2. **Streamlit:** Auf [share.streamlit.io](https://share.streamlit.io) mit GitHub anmelden → *Create app* →
   Repo `STrava-Dashboard`, Branch, Datei `app.py`, eine App-Adresse wählen (z. B. `tri-dashboard.streamlit.app`).
   Unter *Advanced settings* Python 3.12 oder neuer und diese **Secrets** einfügen:

   ```toml
   [auth]
   redirect_uri = "https://tri-dashboard.streamlit.app/oauth2callback"
   cookie_secret = "ZUFALLSWERT"   # python -c "import secrets; print(secrets.token_hex(32))"
   client_id = "….apps.googleusercontent.com"
   client_secret = "GOOGLE-CLIENTSCHLÜSSEL"
   server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

   [storage]
   endpoint_url = "https://s3.eu-central-003.backblazeb2.com"   # S3-Endpoint aus Schritt 1
   bucket = "BUCKET-NAME"
   key_id = "KEY-ID"
   application_key = "APPLICATION-KEY"

   [strava]   # optional: deine Strava-App für alle
   client_id = "12345"
   client_secret = "STRAVA-SECRET"
   redirect_uri = "https://tri-dashboard.streamlit.app/"

   [app]      # optional: für den Datenschutzhinweis
   operator = "Vorname Nachname"
   contact = "name@example.org"
   location = "bei Streamlit Community Cloud (Server in den USA), gesichert bei Backblaze B2 (EU)"
   ```
3. **Google Cloud → Clients:** Weiterleitungs-URI `https://tri-dashboard.streamlit.app/oauth2callback` hinzufügen.
4. **Strava → strava.com/settings/api:** *Authorization Callback Domain* `tri-dashboard.streamlit.app`, Kapazität
   auf bis zu 10 Personen erweitern.
5. *Deploy* – danach die Adresse öffnen und **Mit Google anmelden**. Jeder Push auf den Branch wird automatisch
   übernommen.

### Weg B: Railway (ca. 5 $ im Monat, dauerhaftes Volume)

Railway baut das Dashboard direkt aus dem GitHub-Repo und gibt ihm eine HTTPS-Adresse. Für ein dauerhaftes
Volume brauchst du den Hobby-Plan.

1. Auf [railway.com](https://railway.com) mit GitHub anmelden, **New Project → Deploy from GitHub repo** →
   `STrava-Dashboard`. Unter *Settings → Source* den Branch wählen (`claude/triathlon-dashboard-project-ypvsg3`
   oder `main`, sobald gemergt).
2. *Settings → Deploy → Custom Start Command:* `python serve.py`
3. **Volume:** Rechtsklick auf den Dienst → *Attach Volume* → Mount Path `/data`.
4. *Settings → Networking → Generate Domain* – das ist die Adresse, z. B. `https://tri-dashboard.up.railway.app`.
5. **Variables** eintragen (Werte aus deiner lokalen `.streamlit/secrets.toml` bzw. Google/Strava):

   | Variable | Wert |
   |---|---|
   | `APP_URL` | die Adresse aus Schritt 4 |
   | `GOOGLE_CLIENT_ID` | Client-ID aus der Google Cloud Console |
   | `GOOGLE_CLIENT_SECRET` | Clientschlüssel (am besten ein neu erzeugter) |
   | `COOKIE_SECRET` | Zufallswert: `python -c "import secrets; print(secrets.token_hex(32))"` |
   | `TRI_DATA_DIR` | `/data` |
   | `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET` | optional: deine Strava-App für alle |
   | `APP_OPERATOR`, `APP_CONTACT` | optional: Name und E-Mail für den Datenschutzhinweis |

6. **Google Cloud → Clients:** Weiterleitungs-URI `<APP_URL>/oauth2callback` hinzufügen (die für localhost bleibt).
   **Zielgruppe:** Testnutzer eintragen oder *App veröffentlichen* (siehe unten).
7. **Strava → strava.com/settings/api:** *Authorization Callback Domain* = die Domain ohne `https://`, und die
   Kapazität auf bis zu 10 Personen erweitern.
8. Railway baut neu (*Deploy*). Adresse öffnen → **Mit Google anmelden**. Im Log zeigt `serve.py`, falls etwas fehlt.

**Updates:** Jeder Push auf den gewählten Branch wird automatisch neu gebaut; die Konten auf dem Volume bleiben.

### Weg C: eigener Linux-Server

Ein kleiner Linux-Server (Ubuntu) mit eigener Domain. Mehr Handarbeit, dafür volle Kontrolle. Die Vorlagen in
`deploy/` gehen von diesem Weg aus:

1. **Domain:** eine (Sub-)Domain, z. B. `tri.deine-domain.de`, per DNS-Eintrag auf den Server zeigen lassen.
2. **Programm:** Benutzer anlegen (`sudo useradd --system --create-home tri`), das Repo nach
   `/opt/triathlon-dashboard` klonen, dort `python3 -m venv .venv` und `.venv/bin/pip install -r requirements.txt`.
   Datenordner anlegen und dem Benutzer geben: `sudo mkdir /var/lib/triathlon-dashboard` und
   `sudo chown tri /var/lib/triathlon-dashboard` (ebenso `/opt/triathlon-dashboard`).
3. **Secrets:** im Projektordner `.venv/bin/python setup_login.py` starten und als Adresse
   `https://tri.deine-domain.de` eingeben. Das Skript zeigt dir, was du bei Google und Strava eintragen musst:
   - **Google Cloud → Clients:** Weiterleitungs-URI `https://tri.deine-domain.de/oauth2callback` hinzufügen.
     War der Clientschlüssel je irgendwo sichtbar (z. B. auf einem Screenshot), vorher einen **neuen** erzeugen
     und den alten löschen.
   - **Strava → strava.com/settings/api:** *Authorization Callback Domain* = `tri.deine-domain.de`, und unter
     *Athlete Capacity* auf bis zu 10 Personen erweitern.
4. **Dienst:** `deploy/triathlon-dashboard.service` nach `/etc/systemd/system/` kopieren, Benutzer und Pfade
   prüfen, dann `sudo systemctl enable --now triathlon-dashboard`. Streamlit läuft damit nur intern auf Port 8501.
5. **HTTPS:** [Caddy](https://caddyserver.com) installieren, `deploy/Caddyfile` mit deiner Domain nach
   `/etc/caddy/Caddyfile`, `sudo systemctl reload caddy`. Caddy holt das Zertifikat selbst.
6. **Sicherung:** `deploy/backup.py` täglich per cron laufen lassen (Befehl steht oben in der Datei).

**Update einspielen:** im Projektordner `git pull`, `.venv/bin/pip install -r requirements.txt`,
`sudo systemctl restart triathlon-dashboard`. Die Konten liegen in `TRI_DATA_DIR` und bleiben unberührt.

### Für alle Wege

- **Google-App veröffentlichen:** Unter *Google Auth Platform → Zielgruppe* auf *App veröffentlichen*, sonst kommen
  nur eingetragene Testnutzer rein. Für die reine Anmeldung (Name, E-Mail) verlangt Google keine Prüfung; App-Name
  und Logo zeigt Google aber erst nach einer Markenprüfung an.
- **Rechtliches:** Sobald andere Personen ihre Gesundheitsdaten eintragen, brauchst du ein Impressum und eine
  geprüfte Datenschutzerklärung. Der Hinweis in `triathlon/privacy.py` ist eine Vorlage, keine Rechtsberatung.
  Den eigenen Kreis (Freunde, Kurs) klein halten, bis das geklärt ist.
