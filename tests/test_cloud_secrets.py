"""cloud_secrets.py: Secrets für Streamlit Community Cloud aus der lokalen secrets.toml."""
import tomllib

import cloud_secrets

LOCAL = {"auth": {"redirect_uri": "http://localhost:8501/oauth2callback", "cookie_secret": "lokal",
                  "client_id": "123.apps.googleusercontent.com", "client_secret": "GOCSPX-x",
                  "server_metadata_url": cloud_secrets.METADATA},
         "strava": {"client_id": "4711", "client_secret": "s", "redirect_uri": "http://localhost:8501/"}}
STORAGE = {"endpoint_url": "https://s3.eu-central-003.backblazeb2.com", "bucket": "tri", "key_id": "k",
           "application_key": "a"}


def test_build_replaces_local_addresses():
    data = tomllib.loads(cloud_secrets.build(LOCAL, "https://tri.streamlit.app/", STORAGE, "neu"))
    assert data["auth"]["redirect_uri"] == "https://tri.streamlit.app/oauth2callback"
    assert data["auth"]["cookie_secret"] == "neu"
    assert data["auth"]["client_id"] == "123.apps.googleusercontent.com"
    assert data["strava"]["redirect_uri"] == "https://tri.streamlit.app/"
    assert data["storage"] == STORAGE
    assert "USA" in data["app"]["location"]


def test_build_without_strava_and_with_operator():
    local = {"auth": LOCAL["auth"]}
    data = tomllib.loads(cloud_secrets.build(local, "https://x.streamlit.app", STORAGE, "c", strava={},
                                             app={"operator": "Tom Geiger"}))
    assert "strava" not in data
    assert data["app"]["operator"] == "Tom Geiger"
