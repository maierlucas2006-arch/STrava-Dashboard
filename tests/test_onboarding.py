"""Neue Konten starten ohne fremde Vorgaben, und jede Person kann ihre eigene Strava-App nutzen."""
from types import SimpleNamespace

from triathlon import settings, strava


# --------------------------------------------------------------------------- Neutrale Startwerte

def test_new_account_has_no_race_or_name(tmp_db):
    p = settings.load_profile()
    assert p.name == ""
    assert p.race_name == "" and p.race_date is None
    assert not settings.get("setup_done")
    assert not settings.is_set("race_date") and not settings.is_set("weight_kg")


def test_is_set_tracks_own_values(tmp_db):
    settings.set("weight_kg", 68.5)
    settings.set("race_date", None)          # bewusst „kein Wettkampf“
    assert settings.is_set("weight_kg") and settings.is_set("race_date")
    assert settings.load_profile().weight_kg == 68.5
    assert settings.load_profile().race_date is None


# --------------------------------------------------------------------------- Eigene Strava-App

def _central(monkeypatch):
    monkeypatch.setenv("STRAVA_CLIENT_ID", "4711")
    monkeypatch.setenv("STRAVA_CLIENT_SECRET", "zentral")
    monkeypatch.setenv("STRAVA_REDIRECT_URI", "https://tri.example.org/")


def test_own_app_takes_precedence_over_central(tmp_db, monkeypatch):
    _central(monkeypatch)
    assert strava.credentials() == ("4711", "zentral") and not strava.uses_own_app()
    strava.save_own_app(" 999 ", " eigen ")
    assert strava.uses_own_app() and strava.credentials() == ("999", "eigen")
    assert "client_id=999" in strava.authorize_url()
    strava.save_own_app("", "")
    assert strava.credentials() == ("4711", "zentral")


def test_switching_app_drops_old_tokens(tmp_db, monkeypatch):
    _central(monkeypatch)
    calls = []
    monkeypatch.setattr(strava.requests, "post", lambda url, data, timeout: calls.append(url))
    settings.set("strava_tokens", {"access_token": "tok", "refresh_token": "r", "expires_at": 9_999_999_999})
    strava.save_own_app("999", "eigen")
    assert settings.get("strava_tokens") is None and calls == [strava.DEAUTHORIZE_URL]


def test_saving_same_app_keeps_connection(tmp_db, monkeypatch):
    monkeypatch.delenv("STRAVA_CLIENT_ID", raising=False)
    monkeypatch.delenv("STRAVA_CLIENT_SECRET", raising=False)
    strava.save_own_app("999", "eigen")
    settings.set("strava_tokens", {"access_token": "tok", "refresh_token": "r", "expires_at": 9_999_999_999})
    strava.save_own_app("999", "eigen")
    assert settings.get("strava_tokens") is not None


def test_callback_domain_follows_redirect_uri(monkeypatch):
    monkeypatch.setenv("STRAVA_REDIRECT_URI", "https://tri.example.org/")
    assert strava.callback_domain() == "tri.example.org"
    monkeypatch.delenv("STRAVA_REDIRECT_URI")
    assert strava.callback_domain() == "localhost"


def test_full_strava_app_gives_clear_message(tmp_db, monkeypatch):
    _central(monkeypatch)
    response = SimpleNamespace(status_code=403, text='{"message":"Limit of connected athletes exceeded"}')
    monkeypatch.setattr(strava.requests, "post", lambda *a, **k: response)
    try:
        strava.exchange_code("abc")
    except strava.StravaError as exc:
        assert "eigene Strava-App" in str(exc)
    else:
        raise AssertionError("StravaError erwartet")
