"""Erzeugt die Secrets für Streamlit Community Cloud – zum Einfügen unter
*App → Settings → Secrets* (bzw. beim Deployen unter *Advanced settings*).

In PyCharm: Rechtsklick auf diese Datei → Run 'cloud_secrets'.
Übernimmt Google- und Strava-Werte aus deiner lokalen `.streamlit/secrets.toml`, fragt die
App-Adresse und die Backblaze-Schlüssel ab und schreibt alles nach
`.streamlit/cloud-secrets.toml` (nicht im Git). Den Inhalt dieser Datei kopierst du zu Streamlit.
"""
import json
import secrets
import sys
import tomllib
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
LOCAL = ROOT / ".streamlit" / "secrets.toml"
TARGET = ROOT / ".streamlit" / "cloud-secrets.toml"
METADATA = "https://accounts.google.com/.well-known/openid-configuration"
LOCATION = "bei Streamlit Community Cloud (Server in den USA), gesichert bei Backblaze B2 (EU)"


def q(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def build(local: dict, url: str, storage: dict, cookie: str, strava: dict | None = None,
          app: dict | None = None) -> str:
    """Secrets-Text für die Cloud. ``local`` = Inhalt der lokalen secrets.toml."""
    url = url.rstrip("/")
    auth = local["auth"]
    lines = [
        "[auth]",
        f"redirect_uri = {q(url + '/oauth2callback')}",
        f"cookie_secret = {q(cookie)}",
        f"client_id = {q(auth['client_id'])}",
        f"client_secret = {q(auth['client_secret'])}",
        f"server_metadata_url = {q(auth.get('server_metadata_url') or METADATA)}",
        "",
        "[storage]",
        f"endpoint_url = {q(storage['endpoint_url'])}",
        f"bucket = {q(storage['bucket'])}",
        f"key_id = {q(storage['key_id'])}",
        f"application_key = {q(storage['application_key'])}",
    ]
    strava = strava if strava is not None else local.get("strava", {})
    if strava.get("client_id") and strava.get("client_secret"):
        lines += ["", "[strava]", f"client_id = {q(strava['client_id'])}",
                  f"client_secret = {q(strava['client_secret'])}", f"redirect_uri = {q(url + '/')}"]
    app = {**local.get("app", {}), **(app or {})}
    lines += ["", "[app]"]
    for key in ("operator", "contact"):
        if app.get(key):
            lines.append(f"{key} = {q(app[key])}")
    lines.append(f"location = {q(app.get('location') or LOCATION)}")
    return "\n".join(lines) + "\n"


def ask(prompt: str, current: str | None = None, required: bool = True) -> str:
    hint = f" [Enter = {current}]" if current else ""
    value = input(f"{prompt}{hint}: ").strip().strip('"').strip("'")
    if value:
        return value
    if current:
        return current
    if required:
        sys.exit("Abgebrochen: Es wurde nichts eingegeben.")
    return ""


def main() -> None:
    if not LOCAL.exists():
        sys.exit("Zuerst setup_login.py ausführen – es fehlt .streamlit/secrets.toml.")
    local = tomllib.loads(LOCAL.read_text(encoding="utf-8"))
    if not local.get("auth", {}).get("client_id"):
        sys.exit("In .streamlit/secrets.toml fehlt der Abschnitt [auth] – zuerst setup_login.py ausführen.")

    print("Secrets für Streamlit Community Cloud erzeugen\n")
    url = ask("App-Adresse, z. B. https://tri-dashboard.streamlit.app").rstrip("/")
    host = urlparse(url).hostname
    if urlparse(url).scheme != "https" or not host:
        sys.exit("Die Adresse muss mit https:// beginnen.")

    print("\nBackblaze B2 (Bucket-Seite und Application Keys):")
    storage = {
        "endpoint_url": ask("S3-Endpoint, z. B. s3.eu-central-003.backblazeb2.com"),
        "bucket": ask("Bucket-Name"),
        "key_id": ask("keyID"),
        "application_key": ask("applicationKey"),
    }
    if not storage["endpoint_url"].startswith("https://"):
        storage["endpoint_url"] = "https://" + storage["endpoint_url"]

    strava = dict(local.get("strava", {}))
    if not strava.get("client_id"):
        print("\nOptional: deine Strava-App für alle (Enter = überspringen; steht auf strava.com/settings/api)")
        client_id = ask("Strava Client ID", required=False)
        if client_id:
            strava = {"client_id": client_id, "client_secret": ask("Strava Client Secret")}

    app = dict(local.get("app", {}))
    if not app.get("operator"):
        print("\nFür den Datenschutzhinweis (Enter = überspringen):")
        app["operator"] = ask("Dein Name", required=False)
        app["contact"] = ask("Deine E-Mail", required=False)

    TARGET.write_text(build(local, url, storage, secrets.token_hex(32), strava, app), encoding="utf-8")
    gitignore = ROOT / ".gitignore"
    if gitignore.exists() and ".streamlit/cloud-secrets.toml" not in gitignore.read_text(encoding="utf-8"):
        with gitignore.open("a", encoding="utf-8") as f:
            f.write("\n.streamlit/cloud-secrets.toml\n")

    print(f"\nGespeichert: {TARGET}")
    print("1. Datei in PyCharm öffnen, alles markieren (Strg+A), kopieren und bei Streamlit unter Secrets einfügen.")
    print(f"2. Google Cloud → Clients → Weiterleitungs-URI hinzufügen: {url}/oauth2callback")
    if strava.get("client_id"):
        print(f"3. strava.com/settings/api → Authorization Callback Domain: {host}")


if __name__ == "__main__":
    main()
