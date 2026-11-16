"""Trainingsgalerie: Schreibweise, Zonen, Zielwerte, Katalog und HTML."""
import re
from datetime import date, timedelta

import pandas as pd
import pytest

from triathlon import library as lib
from triathlon import visual

TH = lib.Thresholds(ftp=250, run_pace=270, css=110)


# --------------------------------------------------------------------------- Schreibweise

def test_parse_repeat_rest_and_note():
    (sport, items), = lib.parse("15min@58, 3x(10min@90[ruhig], 5min@55), 8x50m@85 r15, r60", "run")
    assert sport == "run"
    rep = items[1]
    assert isinstance(rep, lib.Repeat) and rep.count == 3
    assert rep.items[0].note == "ruhig" and rep.items[0].seconds == 600
    swim_rep = items[2]
    assert swim_rep.count == 8 and swim_rep.items[0].meters == 50 and swim_rep.items[1].is_rest
    assert items[3].is_rest and items[3].seconds == 60
    flat = lib.flatten(items)
    assert len(flat) == 1 + 6 + 16 + 1


@pytest.mark.parametrize("text, seconds, meters", [
    ("1:30@80", 90, None), ("45s@120", 45, None), ("2min@70", 120, None),
    ("400m@100", None, 400), ("1.5km@95", None, 1500), ("2km@98", None, 2000),
])
def test_parse_durations(text, seconds, meters):
    step = lib.parse(text, "run")[0][1][0]
    assert (step.seconds, step.meters) == (seconds, meters)


def test_parse_range_and_brick_segments():
    segments = lib.parse("bike: 10min@88-94 | run: 2km@82", "bike")
    assert [s for s, _ in segments] == ["bike", "run"]
    step = segments[0][1][0]
    assert (step.low, step.high, step.pct) == (88, 94, 91)


@pytest.mark.parametrize("bad", [
    "10min", "10min@", "10xx@5", "3x(10min@90", "10min@90 extra", "1:75@80", "0min@50", "10min@0",
    "10min@95-90", "10min@90[offen", "10 Minuten@90", "",
])
def test_parse_rejects_invalid(bad):
    with pytest.raises(lib.WorkoutSyntaxError):
        lib.parse(bad, "run")


def test_bike_requires_time_not_distance():
    with pytest.raises(lib.WorkoutSyntaxError):
        lib.parse("10km@70", "bike")


# --------------------------------------------------------------------------- Zonen & Zielwerte

@pytest.mark.parametrize("sport, pct, expected", [
    ("bike", 55, 1), ("bike", 56, 2), ("bike", 75, 2), ("bike", 90, 3), ("bike", 91, 4), ("bike", 105, 4),
    ("bike", 106, 5), ("bike", 150, 6), ("bike", 151, 7),
    ("run", 77, 1), ("run", 82, 2), ("run", 91, 3), ("run", 100, 4), ("run", 105, 5), ("run", 118, 6),
    ("run", 125, 7), ("swim", 84, 1), ("swim", 90, 2), ("swim", 95, 3), ("swim", 100, 4), ("swim", 105, 5),
    ("swim", 112, 6), ("swim", 125, 7), ("run", 0, 0),
])
def test_zones(sport, pct, expected):
    assert lib.zone(sport, pct) == expected


def test_targets_use_thresholds():
    bike = lib.parse("10min@88-94", "bike")[0][1][0]
    run = lib.parse("1km@100", "run")[0][1][0]
    swim = lib.parse("100m@100", "swim")[0][1][0]
    easy = lib.parse("30min@80", "run")[0][1][0]
    assert TH.target(bike) == "220–235 W"
    assert TH.target(run) == "4:30/km"
    assert TH.target(swim) == "1:50/100 m"
    assert TH.target(easy) == "5:38/km"            # 270 s / 0,8
    assert lib.Thresholds().target(bike) == "88–94 % FTP"
    assert lib.Thresholds().target(run) == "100 % Schwellentempo"


def test_distance_steps_get_time_from_pace():
    step = lib.parse("1km@100", "run")[0][1][0]
    assert TH.seconds(step) == pytest.approx(270)
    faster = lib.parse("1km@108", "run")[0][1][0]
    assert TH.seconds(faster) == pytest.approx(250)
    timed = lib.parse("10min@100", "run")[0][1][0]
    assert TH.meters(timed) == pytest.approx(600 / 270 * 1000)


def test_summary_tss():
    w = lib.Workout("x", "bike", "schwelle", "Test", "60min@100", "", lib.parse("60min@100", "bike"))
    s = w.summary(TH)
    assert s.tss == 100 and s.duration_text == "1:00 h"
    swim = lib.Workout("y", "swim", "schwelle", "Test", "400m@100 r60", "", lib.parse("400m@100 r60", "swim"))
    s = swim.summary(TH)
    assert s.seconds == pytest.approx(440 + 60)
    assert s.tss == round(440 / 3600 * 100)          # Pause zählt nicht
    assert s.distance_text("swim") == "400 m"


@pytest.mark.parametrize("tss, ctl, label", [(20, 60, "leicht"), (60, 60, "mittel"), (100, 60, "fordernd"),
                                             (150, 60, "sehr fordernd"), (40, 0, "fordernd")])
def test_load_label(tss, ctl, label):
    assert lib.load_label(tss, ctl) == label


def test_suitable_categories_follow_readiness():
    assert lib.suitable_categories("green", "base") == ["grundlage", "sweetspot", "schwelle", "technik"]
    assert lib.suitable_categories("yellow", "build") == ["grundlage"]
    assert lib.suitable_categories("red", "peak") == ["regeneration"]
    assert lib.suitable_categories("yellow", "peak") == ["grundlage"]


# --------------------------------------------------------------------------- Katalog

def test_catalog_is_large_and_unique():
    assert len(lib.WORKOUTS) >= 150
    assert len(lib.BY_ID) == len(lib.WORKOUTS)
    for sport in ("bike", "run", "swim"):
        cats = lib.categories_for(sport)
        assert len(cats) >= 9
        for cat in cats:
            assert len(lib.workouts_for(sport, [cat])) >= 3, (sport, cat)


@pytest.mark.parametrize("workout", lib.WORKOUTS, ids=lambda w: w.id)
def test_workout_matches_its_category(workout):
    """Die Kategorie stimmt mit den Zonen überein: die Schlüsselzone kommt vor, und kein Abschnitt
    über einer Minute ist härter als die Kategorie."""
    blocks = workout.blocks(lib.Thresholds())
    assert blocks, workout.id
    minutes = workout.summary(lib.Thresholds()).minutes
    assert 20 <= minutes <= 260, (workout.id, minutes)
    assert workout.description and workout.name
    key = lib.CATEGORIES[workout.category].key_zones
    if key:
        assert set(key) & {b.zone for b in blocks}, workout.id
        too_hard = [b for b in blocks if b.seconds > 60 and b.zone > max(key)]
        assert not too_hard, (workout.id, too_hard[0].step)


def test_filters():
    th = lib.Thresholds()
    short = lib.workouts_for("bike", None, 60, th)
    assert short and all(w.summary(th).minutes <= 60.5 for w in short)
    order = [list(lib.CATEGORIES).index(w.category) for w in lib.workouts_for("run")]
    assert order == sorted(order)
    assert {w.sport for w in lib.workouts_for("brick")} == {"brick"}
    assert lib.workouts_for("bike", []) == []


# --------------------------------------------------------------------------- HTML

FORBIDDEN = re.compile(r"<\s*(svg|script|iframe|object|embed)\b|on\w+\s*=", re.I)


def test_gallery_html_is_plain_html():
    html = visual.gallery_html(lib.WORKOUTS, TH, ctl=55)
    assert not FORBIDDEN.search(html)
    assert html.count('class="tri-card"') == len(lib.WORKOUTS)
    assert html.count("<details>") == len(lib.WORKOUTS)


def test_card_shows_personal_targets_and_escapes_text():
    w = lib.BY_ID["bike-sweet-spot-2x20"]
    html = visual.card_html(w, TH, ctl=60)
    assert "225 W" in html and "TSS" in html and "für dich" in html
    tricky = lib.Workout("t", "run", "grundlage", "<b>X</b>", "30min@80[<i>]", "a & b",
                         lib.parse("30min@80[<i>]", "run"))
    out = visual.card_html(tricky, TH, ctl=60)
    assert "<b>X</b>" not in out and "&lt;b&gt;X&lt;/b&gt;" in out and "&amp;" in out


def test_brick_profile_has_two_segments():
    html = visual.profile_html(lib.BY_ID["brick-koppel-langdistanz"], TH)
    assert html.count('class="tri-prof__seg"') == 2


def test_style_switches_zone_colors():
    light, dark = visual.style_html("light"), visual.style_html("dark")
    assert visual.ZONE_COLORS["light"][4] in light and visual.ZONE_COLORS["dark"][4] in dark
    assert "%" in light and "%%" not in light


def test_recent_days_handles_empty_and_data():
    today = date(2026, 11, 16)
    empty = visual.recent_days_html(pd.DataFrame(), pd.DataFrame(), today)
    assert len(re.findall(r'class="tri-day( tri-day--today)?"', empty)) == 14 and "heute" in empty
    acts = pd.DataFrame({
        "local_date": pd.to_datetime([today - timedelta(days=1), today]),
        "start_date": ["2026-11-15T07:00:00Z", "2026-11-16T07:00:00Z"],
        "group": ["run", "bike"], "sport": ["Laufen", "Rad"], "name": ["Lauf", "Rolle"],
        "moving_time": [3600, 5400], "intensity": [0.82, None], "tss": [60.0, 70.0],
    })
    strength = pd.DataFrame({"date": pd.to_datetime([today]), "duration_min": [None], "template": ["Beine"]})
    html = visual.recent_days_html(acts, strength, today)
    assert "tri-z2" in html and "tri-zs" in html and "Beine" in html
    assert not FORBIDDEN.search(html)
