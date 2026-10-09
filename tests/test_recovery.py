from datetime import date, timedelta

import numpy as np
import pandas as pd

from triathlon import recovery

TODAY = date(2026, 10, 9)


def make_wellness(hrv_last7: float = 70, rhr_today: float = 48, sleep_h: float = 7.5) -> pd.DataFrame:
    days = pd.date_range(end=pd.Timestamp(TODAY), periods=60)
    rng = np.random.default_rng(1)
    hrv = np.exp(rng.normal(np.log(70), 0.08, len(days)))
    hrv[-7:] = hrv_last7
    rhr = np.full(len(days), 48.0)
    rhr[-1] = rhr_today
    return pd.DataFrame({"hrv": hrv, "resting_hr": rhr, "sleep_hours": sleep_h, "sleep_score": 80.0}, index=days)


def test_normal_values_are_green():
    r = recovery.readiness(TODAY, make_wellness(), tsb=-10)
    assert r.level == "green"
    assert r.has_wellness


def test_low_hrv_trend_is_yellow():
    r = recovery.readiness(TODAY, make_wellness(hrv_last7=50), tsb=-10)
    assert r.level == "yellow"
    assert any("HRV-Trend unter" in text for text, _ in r.reasons)


def test_low_hrv_high_rhr_and_fatigue_is_red():
    r = recovery.readiness(TODAY, make_wellness(hrv_last7=45, rhr_today=58), tsb=-35)
    assert r.level == "red"


def test_without_wellness_only_tsb_counts():
    empty = pd.DataFrame(columns=["hrv", "resting_hr", "sleep_hours", "sleep_score"],
                         index=pd.DatetimeIndex([]))
    assert recovery.readiness(TODAY, empty, tsb=-5).level == "green"
    r = recovery.readiness(TODAY, empty, tsb=-35)
    assert r.level == "yellow"
    assert not r.has_wellness


def test_stale_wellness_is_ignored():
    old = make_wellness(hrv_last7=40)
    old.index = old.index - timedelta(days=10)
    r = recovery.readiness(TODAY, old, tsb=0)
    assert r.level == "green"
    assert not r.has_wellness


def test_hrv_status_needs_two_weeks():
    w = make_wellness().tail(10)
    assert recovery.hrv_status(w, TODAY) is None
