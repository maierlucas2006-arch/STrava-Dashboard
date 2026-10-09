from datetime import date, timedelta

import pytest

from triathlon import plan, settings
from triathlon.recovery import Readiness

RACE = date(2027, 8, 15)


@pytest.mark.parametrize("days_before, expected", [
    (310, "prep"), (150, "base"), (70, "build"), (30, "peak"), (10, "taper"), (0, "taper"), (-10, "recovery"),
    (-40, "prep"),
])
def test_phase_for_long_distance(days_before, expected):
    assert plan.phase_for(RACE - timedelta(days=days_before), RACE, "Langdistanz").key == expected


def test_weekly_targets_ramp_is_capped_by_phase():
    t = plan.weekly_targets(50, plan.PHASES["base"], weeks_to_taper=20, target_ctl=100)
    assert t.ramp == 2.5
    assert t.tss == 7 * (50 + 6 * 2.5)
    t = plan.weekly_targets(30, plan.PHASES["prep"], weeks_to_taper=20, target_ctl=100)
    assert t.ramp == 2  # Vorbereitung: max. +2


def test_high_fitness_in_offseason_reduces_load():
    t = plan.weekly_targets(120, plan.PHASES["prep"], weeks_to_taper=40, target_ctl=100)
    assert t.ramp < 0


def test_projection_ends_near_target():
    proj = plan.ctl_projection(60, RACE - timedelta(days=300), RACE, "Langdistanz", 100)
    assert proj["ctl"].max() == pytest.approx(100, abs=5)
    assert proj["ctl"].iloc[-1] < proj["ctl"].max()  # Tapering


@pytest.fixture
def profile(tmp_db):
    settings.set_many({"ftp": 300, "threshold_pace": 290.0, "css": 110.0, "max_hr": 200,
                       "race_date": RACE.isoformat()})
    return settings.load_profile()


ROTATION = [{"name": "Brust/Rücken", "lower_body": 0}, {"name": "Arme", "lower_body": 0},
            {"name": "Beine", "lower_body": 1}]


def test_week_plan_distributes_rotation(profile):
    monday = date(2026, 10, 5)
    phase = plan.PHASES["base"]
    targets = plan.weekly_targets(60, phase, 20, 100)
    week = plan.week_plan(monday, profile, phase, targets, ROTATION, strength_done=0)
    assert [d.strength for d in week if d.strength] == ["Brust/Rücken", "Arme", "Beine"]
    assert len(week) == 7
    assert any(s.kind == "long" for s in week[5].sessions)  # Samstag lange Ausfahrt


def test_week_plan_respects_done_sessions(profile):
    thursday = date(2026, 10, 8)
    phase = plan.PHASES["base"]
    targets = plan.weekly_targets(60, phase, 20, 100)
    week = plan.week_plan(thursday, profile, phase, targets, ROTATION, strength_done=2)
    assert [d.strength for d in week if d.strength] == ["Brust/Rücken"]


def test_race_week(profile):
    phase = plan.phase_for(RACE, RACE, "Langdistanz")
    targets = plan.weekly_targets(100, phase, 1, 100)
    week = plan.week_plan(RACE - timedelta(days=6), profile, phase, targets, ROTATION, strength_done=0)
    assert week[6].sessions[0].sport == "race"
    assert week[5].sessions[0].kind == "activation"


def test_paused_run_is_replaced(profile):
    settings.set("paused_sports", ["run"])
    p = settings.load_profile()
    phase = plan.PHASES["base"]
    week = plan.week_plan(date(2026, 10, 5), p, phase, plan.weekly_targets(60, phase, 20, 100), ROTATION, 0)
    assert all(s.sport != "run" for d in week for s in d.sessions)


def _readiness(level):
    return Readiness(level=level, score=0, reasons=[])


def test_yellow_turns_hard_into_easy(profile):
    phase = plan.PHASES["base"]
    week = plan.week_plan(date(2026, 10, 5), profile, phase, plan.weekly_targets(60, phase, 20, 100),
                          ROTATION, 0)
    tuesday = week[1]  # Lauf Qualität
    assert any(s.kind == "hard" for s in tuesday.sessions)
    rec = plan.daily_recommendation(tuesday, _readiness("yellow"), phase, profile, 60, 3, 50)
    assert all(not s.is_key for s in rec.sessions)


def test_red_means_recovery_and_no_strength(profile):
    phase = plan.PHASES["base"]
    week = plan.week_plan(date(2026, 10, 5), profile, phase, plan.weekly_targets(60, phase, 20, 100),
                          ROTATION, 0)
    rec = plan.daily_recommendation(week[0], _readiness("red"), phase, profile, 60, 3, 50)
    assert rec.sessions[0].sport == "recovery"
    assert "kein Krafttraining" in rec.strength
