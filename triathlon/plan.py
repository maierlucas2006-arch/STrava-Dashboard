"""Periodisierung bis zum Wettkampf, Wochenstruktur und Tagesempfehlung."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from triathlon.recovery import Readiness
from triathlon.settings import Profile
from triathlon.workouts import Session, describe


@dataclass(frozen=True)
class Phase:
    key: str
    name: str
    focus: str
    max_ramp: float              # max. Fitness-Anstieg (CTL) pro Woche
    strength_per_week: int
    split: dict[str, float]      # Zeitanteile Schwimmen/Rad/Laufen


PHASES = {
    "prep": Phase("prep", "Allgemeine Vorbereitung",
                  "Kraft aufbauen, Schwimmtechnik verbessern, lockere Ausdauer, Laufumfang behutsam steigern.",
                  2, 4, {"swim": 0.25, "bike": 0.45, "run": 0.30}),
    "base": Phase("base", "Grundlage",
                  "Umfang aufbauen: viel lockeres GA1, eine Qualitätseinheit pro Sportart.",
                  4, 3, {"swim": 0.20, "bike": 0.50, "run": 0.30}),
    "build": Phase("build", "Aufbau",
                   "Wettkampfspezifisch: Renntempo, Koppeltraining, lange Einheiten.",
                   4, 2, {"swim": 0.17, "bike": 0.53, "run": 0.30}),
    "peak": Phase("peak", "Spitze",
                  "Längste Einheiten und Renn-Simulationen, Verpflegung testen.",
                  2, 1, {"swim": 0.15, "bike": 0.55, "run": 0.30}),
    "taper": Phase("taper", "Tapering",
                   "Umfang deutlich runter, kurze Intensitäten halten – frisch an die Startlinie.",
                   -4, 1, {"swim": 0.20, "bike": 0.50, "run": 0.30}),
    "recovery": Phase("recovery", "Regeneration",
                      "Nach dem Wettkampf: locker, Spaß, Körper erholen lassen.",
                      -5, 2, {"swim": 0.30, "bike": 0.40, "run": 0.30}),
}

TAPER_WEEKS = {"Sprint": 1, "Olympisch": 1, "Mitteldistanz": 2, "Langdistanz": 2}
TSS_PER_HOUR = 55  # grober Schnitt bei überwiegend lockerem Training

# Wochenstruktur je Phase: Mo..So, jeweils Liste (Sportart, Art) +
# Krafttage in Prioritätsreihenfolge (0 = Montag)
WEEK_TEMPLATES: dict[str, tuple[list[list[tuple[str, str]]], list[int]]] = {
    "prep": (
        [[("swim", "easy")], [("run", "easy")], [("bike", "hard")], [("swim", "hard")],
         [("rest", "rest")], [("bike", "long")], [("run", "easy")]],
        [0, 1, 3, 6, 4],
    ),
    "base": (
        [[("swim", "hard")], [("run", "hard")], [("bike", "easy"), ("swim", "easy")], [("run", "easy")],
         [("rest", "rest")], [("bike", "long")], [("run", "long")]],
        [0, 2, 4, 3],
    ),
    "build": (
        [[("swim", "hard")], [("bike", "hard")], [("run", "hard"), ("swim", "easy")], [("bike", "easy")],
         [("rest", "rest")], [("bike", "brick")], [("run", "long")]],
        [0, 3, 4],
    ),
    "peak": (
        [[("rest", "rest")], [("bike", "hard"), ("run", "easy")], [("swim", "hard")], [("run", "hard")],
         [("swim", "easy")], [("bike", "brick")], [("run", "long")]],
        [2, 0],
    ),
    "taper": (
        [[("rest", "rest")], [("swim", "hard"), ("run", "easy")], [("bike", "hard")], [("run", "easy")],
         [("swim", "easy")], [("bike", "easy")], [("run", "easy")]],
        [1],
    ),
    "recovery": (
        [[("rest", "rest")], [("swim", "easy")], [("bike", "easy")], [("rest", "rest")],
         [("run", "easy")], [("bike", "easy")], [("rest", "rest")]],
        [1, 4],
    ),
}

# Grunddauer in Minuten je Phase/Sportart/Art – wird auf das Wochenziel skaliert
DURATIONS = {
    "prep": {"swim": {"easy": 40, "hard": 45}, "bike": {"easy": 75, "hard": 75, "long": 120, "brick": 120},
             "run": {"easy": 35, "hard": 40, "long": 60}},
    "base": {"swim": {"easy": 50, "hard": 55}, "bike": {"easy": 90, "hard": 90, "long": 180, "brick": 180},
             "run": {"easy": 45, "hard": 50, "long": 80}},
    "build": {"swim": {"easy": 55, "hard": 60}, "bike": {"easy": 90, "hard": 120, "long": 240, "brick": 240},
              "run": {"easy": 50, "hard": 60, "long": 100}},
    "peak": {"swim": {"easy": 50, "hard": 70}, "bike": {"easy": 75, "hard": 150, "long": 300, "brick": 300},
             "run": {"easy": 45, "hard": 60, "long": 130}},
    "taper": {"swim": {"easy": 35, "hard": 40}, "bike": {"easy": 60, "hard": 60, "long": 90, "brick": 90},
              "run": {"easy": 30, "hard": 35, "long": 45}},
    "recovery": {"swim": {"easy": 30, "hard": 30}, "bike": {"easy": 60, "hard": 60, "long": 90, "brick": 90},
                 "run": {"easy": 30, "hard": 30, "long": 40}},
}

SPORT_LABELS = {"swim": "Schwimmen", "bike": "Rad", "run": "Laufen"}


# --------------------------------------------------------------------------- Phasen

def phase_for(day: date, race_date: date | None, distance: str = "Langdistanz") -> Phase:
    if race_date is None:
        return PHASES["base"]
    days = (race_date - day).days
    if days < 0:
        return PHASES["recovery"] if days >= -21 else PHASES["prep"]
    weeks = days / 7
    if weeks <= TAPER_WEEKS.get(distance, 2):
        return PHASES["taper"]
    if weeks <= 6:
        return PHASES["peak"]
    if weeks <= 16:
        return PHASES["build"]
    if weeks <= 28:
        return PHASES["base"]
    return PHASES["prep"]


def phase_timeline(today: date, race_date: date, distance: str) -> list[dict]:
    """Zusammenhängende Phasen von heute bis zum Wettkampf."""
    blocks: list[dict] = []
    day = today
    while day <= race_date:
        phase = phase_for(day, race_date, distance)
        if blocks and blocks[-1]["phase"].key == phase.key:
            blocks[-1]["end"] = day
        else:
            blocks.append({"phase": phase, "start": day, "end": day})
        day += timedelta(days=1)
    return blocks


def weeks_until_taper(day: date, race_date: date | None, distance: str) -> float:
    if race_date is None:
        return 12.0
    taper_start = race_date - timedelta(weeks=TAPER_WEEKS.get(distance, 2))
    return max((taper_start - day).days / 7, 1.0)


# --------------------------------------------------------------------------- Wochenziele

@dataclass
class WeekTargets:
    ramp: float
    tss: float
    hours: float
    sport_hours: dict[str, float]
    strength: int


def weekly_targets(ctl: float, phase: Phase, weeks_to_taper: float, target_ctl: float) -> WeekTargets:
    """Wochen-TSS, damit die Fitness (CTL) Richtung Ziel-CTL steigt.

    Faustregel: Ø Tages-TSS = CTL + 6 × gewünschter Anstieg pro Woche."""
    if phase.key in ("taper", "recovery"):
        ramp = phase.max_ramp
    else:
        needed = (target_ctl - ctl) / max(weeks_to_taper, 1)
        ramp = min(max(needed, -5.0), phase.max_ramp)
    tss = max(7 * (ctl + 6 * ramp), 0.0)
    hours = tss / TSS_PER_HOUR
    sport_hours = {sport: hours * share for sport, share in phase.split.items()}
    return WeekTargets(round(ramp, 1), round(tss), round(hours, 1), sport_hours, phase.strength_per_week)


def ctl_projection(ctl_now: float, today: date, race_date: date, distance: str,
                   target_ctl: float) -> pd.DataFrame:
    """Erwarteter Fitnessverlauf, wenn die Wochenziele eingehalten werden."""
    rows = [(today, ctl_now, phase_for(today, race_date, distance).name)]
    day, ctl = today, ctl_now
    while day < race_date:
        phase = phase_for(day, race_date, distance)
        targets = weekly_targets(ctl, phase, weeks_until_taper(day, race_date, distance), target_ctl)
        ctl = max(ctl + targets.ramp, 0.0)
        day = min(day + timedelta(days=7), race_date)
        rows.append((day, ctl, phase.name))
    return pd.DataFrame(rows, columns=["date", "ctl", "phase"])


# --------------------------------------------------------------------------- Wochenplan

@dataclass
class DayPlan:
    day: date
    sessions: list[Session]
    strength: str | None = None
    strength_lower: bool = False
    notes: list[str] = field(default_factory=list)
    done: list[str] = field(default_factory=list)


def _replace_paused(sport: str, paused: list[str]) -> str | None:
    if sport not in paused:
        return sport
    for alternative in ("bike", "swim", "run"):
        if alternative not in paused:
            return alternative
    return None


def week_plan(
    today: date,
    profile: Profile,
    phase: Phase,
    targets: WeekTargets,
    rotation: list[dict],
    strength_done: int,
    done_by_day: dict[date, list[str]] | None = None,
    strength_done_today: bool = False,
) -> list[DayPlan]:
    """Plan für die Woche (Mo–So), in der ``today`` liegt.

    ``rotation``: die nächsten Krafteinheiten deiner Rotation (dicts mit
    ``name`` und ``lower_body``), ``strength_done``: Krafteinheiten, die
    diese Woche schon erledigt sind (inkl. heute)."""
    done_by_day = done_by_day or {}
    monday = today - timedelta(days=today.weekday())
    layout, strength_priority = WEEK_TEMPLATES[phase.key]
    base = DURATIONS[phase.key]

    template_minutes = sum(base.get(s, {}).get(k, 0) for day in layout for s, k in day)
    factor = 1.0
    if template_minutes:
        factor = min(max(targets.hours * 60 / template_minutes, 0.5), 1.5)

    race = profile.race_date
    race_in_week = race is not None and monday <= race <= monday + timedelta(days=6)

    days: list[DayPlan] = []
    for offset, planned in enumerate(layout):
        day = monday + timedelta(days=offset)
        notes: list[str] = []
        sessions: list[Session] = []
        if race_in_week and day == race:
            sessions = [describe("race", "race", phase.key, 0, profile)]
        elif race_in_week and day == race - timedelta(days=1):
            sessions = [describe("bike", "activation", phase.key, 30, profile)]
        elif race_in_week and day > race:
            sessions = [describe("rest", "rest", phase.key, 0, profile)]
        else:
            for sport, kind in planned:
                if sport == "rest":
                    sessions.append(describe("rest", "rest", phase.key, 0, profile))
                    continue
                actual = _replace_paused(sport, profile.paused_sports)
                if actual is None:
                    continue
                minutes = base[sport].get(kind, base[sport]["easy"])
                if actual != sport:
                    notes.append(f"{SPORT_LABELS[sport]} pausiert → Alternative {SPORT_LABELS[actual]}")
                    if kind in ("long", "brick"):
                        kind = "easy"
                minutes = int(round(minutes * factor / 5) * 5)
                sessions.append(describe(actual, kind, phase.key, minutes, profile))
            if not sessions:
                sessions = [describe("rest", "rest", phase.key, 0, profile)]
        days.append(DayPlan(day=day, sessions=sessions, notes=notes, done=done_by_day.get(day, [])))

    # Krafteinheiten auf die verbleibenden Krafttage verteilen
    remaining = max(targets.strength - strength_done, 0)
    first_free = today.weekday() + (1 if strength_done_today else 0)
    candidates = [d for d in strength_priority if d >= first_free]
    if race_in_week:
        candidates = [d for d in candidates if monday + timedelta(days=d) <= race - timedelta(days=3)]
    chosen = sorted(candidates[:remaining])
    for slot, workout in zip(chosen, rotation):
        days[slot].strength = workout["name"]
        days[slot].strength_lower = bool(workout.get("lower_body"))

    for i, plan in enumerate(days[:-1]):
        if plan.strength_lower:
            key_tomorrow = [s for s in days[i + 1].sessions if s.is_key]
            if key_tomorrow:
                plan.notes.append(f"Tipp: Beintag nicht zu hart – morgen steht „{key_tomorrow[0].title}“ an.")
    return days


# --------------------------------------------------------------------------- Tagesempfehlung

@dataclass
class Recommendation:
    level: str
    headline: str
    sessions: list[Session]
    strength: str | None
    notes: list[str]


def daily_recommendation(
    plan: DayPlan,
    ready: Readiness,
    phase: Phase,
    profile: Profile,
    ctl: float,
    ramp: float | None,
    yesterday_tss: float,
) -> Recommendation:
    notes: list[str] = []
    if plan.done:
        notes.append("Heute schon erledigt: " + ", ".join(plan.done))
    notes.extend(plan.notes)

    sessions = list(plan.sessions)
    has_training = any(s.sport not in ("rest", "race") for s in sessions)
    strength_text = None

    if ready.level == "red":
        if has_training:
            sessions = [describe("recovery", "recovery", phase.key, 30, profile)]
            notes.append("Geplant war: " + ", ".join(s.title for s in plan.sessions))
        headline = "Rot – heute hat Erholung Vorrang" if has_training else "Rot – gut, dass heute Ruhetag ist"
        if plan.strength:
            strength_text = f"Heute kein Krafttraining – {plan.strength} verschiebt sich auf morgen."
    elif ready.level == "yellow":
        adjusted = []
        for s in sessions:
            if s.is_key:
                minutes = int(round(s.minutes * 0.75 / 5) * 5)
                adjusted.append(describe(s.sport, "easy", phase.key, minutes, profile))
                notes.append(f"Geplant war „{s.title}“ – heute locker statt hart/lang.")
            else:
                adjusted.append(s)
        sessions = adjusted
        headline = "Gelb – heute lieber locker" if has_training else "Gelb – gut, dass heute Ruhetag ist"
        if plan.strength:
            strength_text = (f"{plan.strength}: ja, aber 1 Satz weniger pro Übung und nicht bis zum "
                             "Muskelversagen.")
    else:
        headline = "Grünes Licht – Training wie geplant" if has_training else "Ruhetag laut Plan – genieß ihn"
        if plan.strength:
            strength_text = f"{plan.strength} (nächste Einheit deiner Rotation)"

    if plan.strength and plan.strength_lower and ready.level != "red" and any(s.is_key for s in sessions):
        notes.append("Beintraining nach der Ausdauereinheit machen (mind. 6 h Abstand) "
                     "oder auf einen lockeren Tag schieben.")
    if ready.level == "green" and yesterday_tss > max(150.0, 2 * ctl) and any(s.is_key for s in sessions):
        notes.append(f"Gestern war eine sehr große Einheit (TSS {yesterday_tss:.0f}) – hör heute auf deinen Körper.")
    if ramp is not None and ramp > 8:
        notes.append(f"Deine Fitness steigt sehr schnell (+{ramp:.0f} CTL pro Woche) – das erhöht das "
                     "Verletzungsrisiko. Lieber etwas rausnehmen.")

    return Recommendation(ready.level, headline, sessions, strength_text, notes)
