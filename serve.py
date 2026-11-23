"""Startet das Dashboard auf einem Hoster (z. B. Railway, Render) – Startbefehl: ``python serve.py``.

Die Zugangsdaten kommen dort nicht aus einer Datei, sondern aus Umgebungsvariablen, die du im
Dashboard des Hosters einträgst. Daraus schreibt dieses Skript beim Start `.streamlit/secrets.toml`:

    APP_URL               https://dein-dashboard.up.railway.app   (Adresse des Dashboards)
    GOOGLE_CLIENT_ID      ….apps.googleusercontent.com
    GOOGLE_CLIENT_SECRET  Google-Clientschlüssel
    COOKIE_SECRET         Zufallswert (python -c "import secrets; print(secrets.token_hex(32))")
    STRAVA_CLIENT_ID      optional: deine Strava-App für alle Konten
    STRAVA_CLIENT_SECRET  optional
    APP_OPERATOR          optional: dein Name für den Datenschutzhinweis
    APP_CONTACT           optional: deine E-Mail
    TRI_DATA_DIR          Ordner auf dem dauerhaften Speicher (Volume), z. B. /data

Den Port gibt der Hoster über ``PORT`` vor. Lokal weiter ``start.py`` benutzen.
"""
from __future__ import annotations

import json
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SECRETS_FILE = ROOT / ".streamlit" / "secrets.toml"
METADATA = "https://accounts.google.com/.well-known/openid-configuration"


def _q(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def build_secrets(env: dict) -> str | None:
    """secrets.toml aus Umgebungsvariablen – None, wenn die Google-Angaben fehlen."""
    url = (env.get("APP_URL") or "").strip().rstrip("/")
    client_id = (env.get("GOOGLE_CLIENT_ID") or "").strip()
    client_secret = (env.get("GOOGLE_CLIENT_SECRET") or "").strip()
    if not (url and client_id and client_secret):
        return None
    cookie = (env.get("COOKIE_SECRET") or "").strip() or secrets.token_hex(32)
    lines = [
        "# Beim Start aus Umgebungsvariablen erzeugt (serve.py) – nicht von Hand ändern.",
        "[auth]",
        f"redirect_uri = {_q(url + '/oauth2callback')}",
        f"cookie_secret = {_q(cookie)}",
        f"client_id = {_q(client_id)}",
        f"client_secret = {_q(client_secret)}",
        f"server_metadata_url = {_q(METADATA)}",
    ]
    operator = (env.get("APP_OPERATOR") or "").strip()
    contact = (env.get("APP_CONTACT") or "").strip()
    if operator or contact:
        lines.append("\n[app]")
        if operator:
            lines.append(f"operator = {_q(operator)}")
        if contact:
            lines.append(f"contact = {_q(contact)}")
    return "\n".join(lines) + "\n"


def prepare(env: dict) -> list[str]:
    """Schreibt secrets.toml und ergänzt die Strava-Weiterleitung. Gibt Hinweise fürs Log zurück."""
    notes = []
    content = build_secrets(env)
    if content:
        SECRETS_FILE.parent.mkdir(exist_ok=True)
        SECRETS_FILE.write_text(content, encoding="utf-8")
        notes.append("secrets.toml aus Umgebungsvariablen geschrieben.")
        if not (env.get("COOKIE_SECRET") or "").strip():
            notes.append("COOKIE_SECRET fehlt – nach jedem Neustart müssen sich alle neu anmelden.")
    elif not SECRETS_FILE.exists():
        notes.append("APP_URL, GOOGLE_CLIENT_ID oder GOOGLE_CLIENT_SECRET fehlen – die Anmeldung ist nicht eingerichtet.")
    url = (env.get("APP_URL") or "").strip().rstrip("/")
    if url and env.get("STRAVA_CLIENT_ID") and not env.get("STRAVA_REDIRECT_URI"):
        os.environ["STRAVA_REDIRECT_URI"] = url + "/"
    if not env.get("TRI_DATA_DIR"):
        notes.append("TRI_DATA_DIR fehlt – die Konten liegen im Programmordner und können bei einem Neustart "
                     "verloren gehen. Volume einhängen und TRI_DATA_DIR auf dessen Pfad setzen.")
    if env.get("TRI_DB_PATH"):
        notes.append("TRI_DB_PATH ist gesetzt – das schaltet den Demo-Modus ohne Anmeldung ein. Bitte entfernen.")
    return notes


if __name__ == "__main__":
    for note in prepare(dict(os.environ)):
        print(f"[serve.py] {note}", flush=True)
    from streamlit.web import cli

    sys.argv = ["streamlit", "run", str(ROOT / "app.py"),
                "--server.port", os.environ.get("PORT", "8501"), "--server.address", "0.0.0.0",
                "--server.headless", "true", "--browser.gatherUsageStats", "false"]
    sys.exit(cli.main())
