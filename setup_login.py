"""Richtet .streamlit/secrets.toml ein: Google-Anmeldung, optional die zentrale Strava-App
und Betreiber-Angaben für den Datenschutzhinweis.

Lokal: In PyCharm Rechtsklick auf diese Datei → Run 'setup_login'.
Auf dem Server: ``python setup_login.py`` im Projektordner.

Werte, die schon in secrets.toml stehen, bleiben erhalten, wenn du nur Enter drückst –
du kannst das Skript also gefahrlos erneut starten (z. B. für einen neuen Google-Clientschlüssel
oder die Online-Adresse).
"""
import json
import secrets
import sys
import tomllib
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / ".streamlit" / "secrets.toml"
LOCAL = "http://localhost:8501"
METADATA = "https://accounts.google.com/.well-known/openid-configuration"


def ask(prompt: str, current: str | None = None, required: bool = True, hidden: bool = False) -> str:
    hint = f" [Enter = {'behalten' if hidden else current}]" if current else ""
    value = input(f"{prompt}{hint}: ").strip().strip('"').strip("'")
    if value:
        return value
    if current:
        return current
    if required:
        sys.exit("Abgebrochen: Es wurde nichts eingegeben.")
    return ""


def yes(prompt: str) -> bool:
    return input(f"{prompt} (j/n) [n]: ").strip().lower() in ("j", "ja", "y", "yes")


def toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def section(name: str, values: dict) -> str:
    lines = [f"[{name}]"]
    lines += [f"{key} = {toml_value(value)}" for key, value in values.items()
              if value not in (None, "") and not isinstance(value, dict)]
    return "\n".join(lines) + "\n"


def main() -> None:
    existing = tomllib.loads(TARGET.read_text(encoding="utf-8")) if TARGET.exists() else {}
    auth = existing.get("auth", {})
    strava = existing.get("strava", {})
    app = existing.get("app", {})

    print("Anmeldung einrichten (Enter übernimmt den Wert in eckigen Klammern)\n")
    current_base = str(auth.get("redirect_uri", f"{LOCAL}/oauth2callback")).removesuffix("/oauth2callback")
    base = ask("Adresse des Dashboards – lokal http://localhost:8501, online z. B. https://tri.deine-domain.de",
               current_base).rstrip("/")
    parsed = urlparse(base)
    local = parsed.hostname in ("localhost", "127.0.0.1")
    if parsed.scheme not in ("http", "https") or not parsed.hostname or (not local and parsed.scheme != "https"):
        sys.exit("Die Adresse muss mit https:// beginnen (lokal: http://localhost:8501).")
    redirect = f"{base}/oauth2callback"
    print(f"\n→ In der Google Cloud Console beim OAuth-Client als Weiterleitungs-URI eintragen:\n   {redirect}\n")

    client_id = ask("Google Client-ID", auth.get("client_id"))
    if not client_id.endswith(".apps.googleusercontent.com"):
        sys.exit("Das sieht nicht nach einer Google-Client-ID aus (endet auf .apps.googleusercontent.com).")
    client_secret = ask("Google Clientschlüssel", auth.get("client_secret"), hidden=True)
    if client_secret == client_id or " " in client_secret:
        sys.exit("Der Clientschlüssel ist ungültig – bitte aus der Google Cloud Console kopieren.")

    print("\nStrava zentral: Mit deiner Strava-App muss niemand sonst eigene Strava-Schlüssel anlegen.")
    if strava.get("client_id"):
        print(f"Hinterlegt ist die Strava-App mit Client-ID {strava['client_id']}.")
        change = yes("Strava-Schlüssel ändern?")
    else:
        change = yes("Strava-Client-ID und -Secret jetzt eintragen?")
    if change:
        strava = {
            "client_id": ask("Strava Client ID", strava.get("client_id")),
            "client_secret": ask("Strava Client Secret", strava.get("client_secret"), hidden=True),
        }
    if strava.get("client_id"):
        strava["redirect_uri"] = f"{base}/"
        print(f"→ Bei Strava (strava.com/settings/api) als Authorization Callback Domain eintragen: {parsed.hostname}")

    print("\nFür den Datenschutzhinweis (leer lassen = allgemeiner Text):")
    operator = ask("Betreiber (dein Name)", app.get("operator"), required=False)
    contact = ask("Kontakt (E-Mail)", app.get("contact"), required=False)

    parts = [
        "# Zugangsdaten – NICHT ins Git (steht in .gitignore). Neu erzeugen: python setup_login.py\n",
        section("auth", {
            "redirect_uri": redirect,
            "cookie_secret": auth.get("cookie_secret") or secrets.token_hex(32),
            "client_id": client_id,
            "client_secret": client_secret,
            "server_metadata_url": auth.get("server_metadata_url") or METADATA,
        }),
    ]
    if strava.get("client_id"):
        parts.append(section("strava", strava))
    if operator or contact:
        parts.append(section("app", {"operator": operator, "contact": contact}))
    for name, values in existing.items():           # sonstige eigene Abschnitte unverändert übernehmen
        if name not in ("auth", "strava", "app") and isinstance(values, dict):
            parts.append(section(name, values))

    TARGET.parent.mkdir(exist_ok=True)
    TARGET.write_text("\n".join(parts), encoding="utf-8")

    gitignore = ROOT / ".gitignore"
    if gitignore.exists() and ".streamlit/secrets.toml" not in gitignore.read_text(encoding="utf-8"):
        with gitignore.open("a", encoding="utf-8") as f:
            f.write("\n.streamlit/secrets.toml\n")

    print(f"\nGespeichert: {TARGET}")
    print("Jetzt das Dashboard neu starten und „Mit Google anmelden“ klicken.")


if __name__ == "__main__":
    main()
