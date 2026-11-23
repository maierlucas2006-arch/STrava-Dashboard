"""serve.py: secrets.toml aus Umgebungsvariablen für den Betrieb beim Hoster."""
import os
import tomllib

import serve

ENV = {"APP_URL": "https://tri.up.railway.app/", "GOOGLE_CLIENT_ID": "123.apps.googleusercontent.com",
       "GOOGLE_CLIENT_SECRET": "GOCSPX-abc", "COOKIE_SECRET": "c00k1e", "APP_OPERATOR": "Tom Geiger",
       "TRI_DATA_DIR": "/data"}


def test_build_secrets():
    data = tomllib.loads(serve.build_secrets(ENV))
    assert data["auth"]["redirect_uri"] == "https://tri.up.railway.app/oauth2callback"
    assert data["auth"]["client_id"] == "123.apps.googleusercontent.com"
    assert data["auth"]["cookie_secret"] == "c00k1e"
    assert data["app"] == {"operator": "Tom Geiger"}


def test_missing_google_values_write_nothing():
    assert serve.build_secrets({"APP_URL": "https://x.example"}) is None


def test_prepare_writes_file_and_strava_redirect(tmp_path, monkeypatch):
    monkeypatch.setattr(serve, "SECRETS_FILE", tmp_path / ".streamlit" / "secrets.toml")
    monkeypatch.delenv("STRAVA_REDIRECT_URI", raising=False)
    notes = serve.prepare({**ENV, "STRAVA_CLIENT_ID": "4711", "COOKIE_SECRET": ""})
    assert serve.SECRETS_FILE.exists()
    assert os.environ["STRAVA_REDIRECT_URI"] == "https://tri.up.railway.app/"
    assert any("COOKIE_SECRET" in n for n in notes)
    monkeypatch.delenv("STRAVA_REDIRECT_URI")


def test_prepare_warns_without_volume_and_in_demo_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(serve, "SECRETS_FILE", tmp_path / "secrets.toml")
    notes = serve.prepare({"TRI_DB_PATH": "x.db"})
    assert any("Anmeldung ist nicht eingerichtet" in n for n in notes)
    assert any("TRI_DATA_DIR" in n for n in notes)
    assert any("Demo-Modus" in n for n in notes)
