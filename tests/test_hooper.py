"""Morgen-Check nach Hooper: Speichern, Bewertung gegen die eigene Baseline, Einfluss auf die Ampel."""
from datetime import date, timedelta

import pandas as pd
import pytest

from triathlon import recovery

TODAY = date(2026, 11, 23)


def make_hooper(today_items=(3, 3, 3, 3), days=30, usual=(3, 3, 3, 3)) -> pd.DataFrame:
    rows = []
    for offset in range(days, 0, -1):
        wiggle = 1 if offset % 3 == 0 else 0
        rows.append((pd.Timestamp(TODAY - timedelta(days=offset)), *(v + wiggle for v in usual)))
    rows.append((pd.Timestamp(TODAY), *today_items))
    df = pd.DataFrame(rows, columns=["date", *recovery.HOOPER_ITEMS]).set_index("date")
    df["index"] = df[list(recovery.HOOPER_ITEMS)].sum(axis=1)
    return df


def test_save_and_load(tmp_db):
    recovery.save_hooper(TODAY, 2, 3, 4, 5, note="  ")
    recovery.save_hooper(TODAY, 3, 3, 3, 3)          # gleicher Tag → überschreiben
    df = recovery.hooper_df()
    assert len(df) == 1
    assert df.loc[pd.Timestamp(TODAY), "index"] == 12


@pytest.mark.parametrize("bad", [0, 8, None])
def test_values_must_be_1_to_7(tmp_db, bad):
    with pytest.raises(ValueError):
        recovery.save_hooper(TODAY, bad, 3, 3, 3)


def test_usual_day_is_fine():
    status = recovery.hooper_status(make_hooper(), TODAY)
    assert status.index == 12
    assert status.baseline == pytest.approx(13, abs=0.5)
    assert status.points == 0


def test_much_worse_than_usual_counts():
    status = recovery.hooper_status(make_hooper(today_items=(5, 5, 5, 5)), TODAY)
    assert status.worse and status.points == -1


def test_very_high_index_counts_double():
    status = recovery.hooper_status(make_hooper(today_items=(6, 6, 6, 7)), TODAY)
    assert status.points == -2


def test_without_baseline_only_high_values_count():
    few = make_hooper(days=3, today_items=(4, 4, 4, 4))
    assert recovery.hooper_status(few, TODAY).baseline is None
    assert recovery.hooper_status(few, TODAY).points == 0
    high = make_hooper(days=3, today_items=(5, 5, 5, 5))
    assert recovery.hooper_status(high, TODAY).points == -1


def test_no_entry_today():
    df = make_hooper().drop(pd.Timestamp(TODAY))
    assert recovery.hooper_status(df, TODAY) is None
    assert recovery.hooper_status(pd.DataFrame(), TODAY) is None


def test_morning_check_moves_the_traffic_light():
    empty = pd.DataFrame(columns=["hrv", "resting_hr", "sleep_hours", "sleep_score"], index=pd.DatetimeIndex([]))
    calm = recovery.readiness(TODAY, empty, tsb=-22, hooper=make_hooper())
    assert calm.level == "green"
    assert any("Morgen-Check: Befinden im üblichen Rahmen" in text for text, _ in calm.reasons)
    assert any("und Morgen-Check" in text for text, _ in calm.reasons)
    tired = recovery.readiness(TODAY, empty, tsb=-22, hooper=make_hooper(today_items=(5, 5, 5, 5)))
    assert tired.level == "yellow"
    assert any("schlechter als sonst" in text and points == -1 for text, points in tired.reasons)
