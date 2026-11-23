"""Datenschutzhinweis, der vor der ersten Nutzung angezeigt wird.

Betreiber, Kontakt und Speicherort kommen aus ``.streamlit/secrets.toml``, Abschnitt ``[app]``
(``operator``, ``contact``, ``location``). Der Text ist eine Vorlage für ein privates bzw.
studentisches Projekt – vor einem öffentlichen Angebot rechtlich prüfen lassen.
"""
from __future__ import annotations


def notice(operator: str | None = None, contact: str | None = None, location: str | None = None) -> str:
    who = operator or "die Person, die dieses Dashboard betreibt"
    reach = f" Kontakt: {contact}." if contact else ""
    where = location or "auf dem Server des Dashboards"
    return f"""
**Wer ist verantwortlich?** {who}.{reach}

**Welche Daten?** Was du verbindest oder einträgst: Trainingseinheiten aus Strava, Schlaf, Ruhepuls,
HRV und Gewicht von Garmin (über intervals.icu), Krafttraining aus wger oder Hevy, dein
Ernährungstagebuch, der Morgen-Check sowie Profilangaben wie Vorname, Gewicht, Größe, Geburtsjahr
und Puls- und Leistungswerte. Dazu kommen die Zugangsschlüssel zu diesen Diensten. Von deinem Google-Konto
wird nur eine Kennung gespeichert, damit deine Daten dir zugeordnet werden – Name und E-Mail werden
nur angezeigt, nicht gespeichert. Ein Teil davon sind **Gesundheitsdaten**.

**Wofür?** Nur für die Auswertungen in diesem Dashboard: Belastung, Erholung, Ernährung und die
Empfehlung für den Tag. Keine Werbung, kein Verkauf, keine Weitergabe.

**Wo?** In einer eigenen Datenbankdatei für dein Konto {where}. Andere Konten haben keinen Zugriff. Daten werden nur dann bei Strava, intervals.icu, wger, Hevy oder Open
Food Facts abgerufen, wenn du den Dienst verbindest bzw. dort suchst; die Anmeldung läuft über Google.

**Wie lange?** Bis du dein Konto löschst. Unter *Einstellungen → Deine Daten* kannst du jederzeit
alles herunterladen und das Konto samt allen Daten endgültig löschen – damit widerrufst du auch
diese Einwilligung. Du hast außerdem das Recht auf Auskunft, Berichtigung und Beschwerde bei einer
Datenschutz-Aufsichtsbehörde.

**Wichtig:** Das Dashboard ist eine Entscheidungshilfe für dein Training. Es ist kein
Medizinprodukt und ersetzt keine ärztliche Beratung.
"""


CONSENT_LABEL = ("Ich willige ausdrücklich ein, dass meine Trainings- und Gesundheitsdaten wie oben beschrieben "
                 "gespeichert und ausgewertet werden.")
