"""Richtet die Google-Anmeldung ein: schreibt .streamlit/secrets.toml.

In PyCharm: Rechtsklick auf diese Datei → Run 'setup_login'. Dann im Run-Fenster
Client-ID und Clientschlüssel aus der Google Cloud Console einfügen (je Enter).
Den Cookie-Schlüssel erzeugt das Skript selbst.
"""
import json
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / ".streamlit" / "secrets.toml"
REDIRECT = "http://localhost:8501/oauth2callback"
METADATA = "https://accounts.google.com/.well-known/openid-configuration"


def ask(prompt: str) -> str:
    value = input(prompt).strip().strip('"').strip("'")
    if not value:
        sys.exit("Abgebrochen: Es wurde nichts eingegeben.")
    return value


def main() -> None:
    print("Google-Anmeldung einrichten")
    print(f"Weiterleitungs-URI für den Google-Client: {REDIRECT}\n")
    if TARGET.exists():
        answer = input(f"{TARGET.name} gibt es schon. Überschreiben? (j/n): ").strip().lower()
        if answer not in ("j", "ja", "y", "yes"):
            sys.exit("Nichts geändert.")

    client_id = ask("Client-ID einfügen: ")
    if not client_id.endswith(".apps.googleusercontent.com"):
        sys.exit("Das sieht nicht nach einer Google-Client-ID aus (endet auf .apps.googleusercontent.com).")
    client_secret = ask("Clientschlüssel einfügen: ")
    if client_secret == client_id or " " in client_secret:
        sys.exit("Der Clientschlüssel ist ungültig – bitte aus der Google Cloud Console kopieren.")

    TARGET.parent.mkdir(exist_ok=True)
    TARGET.write_text(
        "# Zugangsdaten für die Anmeldung – NICHT ins Git (steht in .gitignore).\n"
        "[auth]\n"
        f"redirect_uri = {json.dumps(REDIRECT)}\n"
        f"cookie_secret = {json.dumps(secrets.token_hex(32))}\n"
        f"client_id = {json.dumps(client_id)}\n"
        f"client_secret = {json.dumps(client_secret)}\n"
        f"server_metadata_url = {json.dumps(METADATA)}\n",
        encoding="utf-8",
    )

    gitignore = ROOT / ".gitignore"
    if ".streamlit/secrets.toml" not in gitignore.read_text(encoding="utf-8"):
        with gitignore.open("a", encoding="utf-8") as f:
            f.write("\n.streamlit/secrets.toml\n")

    print(f"\nGespeichert: {TARGET}")
    print("Jetzt das Dashboard neu starten (rotes Quadrat, dann start.py) und „Mit Google anmelden“ klicken.")


if __name__ == "__main__":
    main()
