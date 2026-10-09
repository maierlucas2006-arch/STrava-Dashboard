from datetime import date

import pandas as pd
import pytest

from triathlon import load, settings


@pytest.fixture
def profile(tmp_db):
    settings.set_many({"ftp": 300, "threshold_pace": 300.0, "css": 100.0, "max_hr": 200})
    return settings.load_profile()


def test_bike_with_power_meter_at_ftp_is_100_per_hour(profile):
    act = {"sport_type": "Ride", "moving_time": 3600, "weighted_average_watts": 300, "device_watts": 1}
    result = load.activity_tss(act, profile)
    assert result.tss == pytest.approx(100)
    assert result.method == "Leistung"


def test_estimated_power_is_ignored(profile):
    act = {"sport_type": "Ride", "moving_time": 3600, "weighted_average_watts": 300, "device_watts": 0,
           "average_heartrate": 144}
    result = load.activity_tss(act, profile)
    assert result.method == "Herzfrequenz"
    assert result.tss == pytest.approx(64)  # 144 / (0.9 × 200) = 0.8 → 0.8² × 100


def test_run_at_threshold_pace(profile):
    act = {"sport_type": "Run", "moving_time": 3600, "distance": 12000, "average_speed": 1000 / 300}
    assert load.activity_tss(act, profile).tss == pytest.approx(100)


def test_hilly_run_uses_heart_rate(profile):
    act = {"sport_type": "TrailRun", "moving_time": 3600, "distance": 8000, "average_speed": 2.2,
           "elevation_gain": 600, "average_heartrate": 162}
    assert load.activity_tss(act, profile).method == "Herzfrequenz"


def test_swim_uses_cubic_intensity(profile):
    act = {"sport_type": "Swim", "moving_time": 3600, "distance": 2700, "average_speed": 0.9}
    result = load.activity_tss(act, profile)
    assert result.method == "Schwimmtempo"
    assert result.tss == pytest.approx(0.9**3 * 100, abs=0.2)


def test_fallback_without_any_data(tmp_db):
    p = settings.load_profile()
    act = {"sport_type": "Hike", "moving_time": 7200}
    result = load.activity_tss(act, p)
    assert result.method == "Schätzung"
    assert result.tss == pytest.approx(2 * 0.55**2 * 100, abs=0.2)


def test_pmc_converges_to_daily_load():
    daily = pd.Series(100.0, index=pd.date_range("2026-01-01", periods=300))
    df = load.pmc(daily)
    assert df["ctl"].iloc[-1] == pytest.approx(100, abs=1)
    assert df["atl"].iloc[-1] == pytest.approx(100, abs=0.1)
    assert abs(df["tsb"].iloc[-1]) < 1


def test_strength_log_not_double_counted_with_strava_strength():
    day = pd.Timestamp("2026-10-05")
    acts = pd.DataFrame({"local_date": [day], "tss": [40.0], "group": ["strength"]})
    strength = pd.DataFrame({"date": [day, day + pd.Timedelta(days=1)], "tss": [49.0, 49.0]})
    daily = load.daily_load(acts, strength, date(2026, 10, 5), date(2026, 10, 6))
    assert daily.tolist() == [40.0, 49.0]
