"""Bündelt alle Daten für einen Stichtag: Belastung, Regeneration, Phase, Plan."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from triathlon import load, plan, recovery, settings, strength
from triathlon.settings import Profile

HISTORY_FOR_PMC_DAYS = 400


@dataclass
class State:
    today: date
    profile: Profile
    activities: pd.DataFrame
    strength_sessions: pd.DataFrame
    pmc: pd.DataFrame
    wellness: pd.DataFrame
    readiness: recovery.Readiness
    phase: plan.Phase
    targets: plan.WeekTargets
    week: list[plan.DayPlan]
    recommendation: plan.Recommendation

    @property
    def ctl(self) -> float:
        return float(self.pmc["ctl"].iloc[-1]) if not self.pmc.empty else 0.0

    @property
    def atl(self) -> float:
        return float(self.pmc["atl"].iloc[-1]) if not self.pmc.empty else 0.0

    @property
    def tsb(self) -> float:
        return float(self.pmc["tsb"].iloc[-1]) if not self.pmc.empty else 0.0

    @property
    def ramp(self) -> float | None:
        if self.pmc.empty or pd.isna(self.pmc["ramp"].iloc[-1]):
            return None
        return float(self.pmc["ramp"].iloc[-1])

    @property
    def days_to_race(self) -> int | None:
        if not self.profile.race_date:
            return None
        return (self.profile.race_date - self.today).days

    def week_activities(self, day: date | None = None) -> pd.DataFrame:
        day = day or self.today
        monday = pd.Timestamp(day - timedelta(days=day.weekday()))
        acts = self.activities
        if acts.empty:
            return acts
        return acts[(acts["local_date"] >= monday) & (acts["local_date"] < monday + pd.Timedelta(days=7))]

    def week_strength(self, day: date | None = None) -> pd.DataFrame:
        day = day or self.today
        monday = pd.Timestamp(day - timedelta(days=day.weekday()))
        s = self.strength_sessions
        return s[(s["date"] >= monday) & (s["date"] < monday + pd.Timedelta(days=7))]

    def week_tss(self) -> float:
        monday = pd.Timestamp(self.today - timedelta(days=self.today.weekday()))
        return float(self.pmc.loc[self.pmc.index >= monday, "tss"].sum()) if not self.pmc.empty else 0.0


def _done_by_day(acts: pd.DataFrame, strength_sessions: pd.DataFrame) -> dict[date, list[str]]:
    from triathlon.units import fmt_duration

    done: dict[date, list[str]] = {}
    for row in acts.itertuples():
        done.setdefault(row.local_date.date(), []).append(f"{row.sport} {fmt_duration(row.moving_time)}")
    for row in strength_sessions.itertuples():
        done.setdefault(row.date.date(), []).append(f"Kraft ({row.template or 'frei'})")
    return done


def build_state(today: date | None = None) -> State:
    today = today or date.today()
    profile = settings.load_profile()
    since = today - timedelta(days=HISTORY_FOR_PMC_DAYS)

    acts = load.activities_df(profile, since)
    acts = acts[acts["local_date"] <= pd.Timestamp(today)] if not acts.empty else acts
    strength_sessions = load.strength_df(since)
    strength_sessions = strength_sessions[strength_sessions["date"] <= pd.Timestamp(today)]

    first_day = since
    if not acts.empty:
        first_day = max(min(first_day, acts["local_date"].min().date()), since)
    daily = load.daily_load(acts, strength_sessions, first_day, today)
    pmc_df = load.pmc(daily)

    wellness = recovery.wellness_df()
    tsb_today = float(pmc_df["tsb"].iloc[-1]) if not pmc_df.empty else None
    ready = recovery.readiness(today, wellness, tsb_today)

    phase = plan.phase_for(today, profile.race_date, profile.race_distance)
    ctl_now = float(pmc_df["ctl"].iloc[-1]) if not pmc_df.empty else 0.0
    targets = plan.weekly_targets(
        ctl_now, phase, plan.weeks_until_taper(today, profile.race_date, profile.race_distance), profile.target_ctl,
    )

    monday = pd.Timestamp(today - timedelta(days=today.weekday()))
    week_acts = acts[acts["local_date"] >= monday] if not acts.empty else acts
    week_strength = strength_sessions[strength_sessions["date"] >= monday]
    week = plan.week_plan(
        today, profile, phase, targets,
        rotation=strength.rotation(max(targets.strength, 1)),
        strength_done=len(week_strength),
        done_by_day=_done_by_day(week_acts, week_strength),
        strength_done_today=bool((week_strength["date"] == pd.Timestamp(today)).any()),
    )
    today_plan = week[today.weekday()]

    yesterday = pd.Timestamp(today - timedelta(days=1))
    yesterday_tss = float(pmc_df.loc[yesterday, "tss"]) if yesterday in pmc_df.index else 0.0
    ramp = pmc_df["ramp"].iloc[-1] if not pmc_df.empty else None
    rec = plan.daily_recommendation(
        today_plan, ready, phase, profile, ctl_now,
        None if ramp is None or pd.isna(ramp) else float(ramp), yesterday_tss,
    )

    return State(today, profile, acts, strength_sessions, pmc_df, wellness, ready, phase, targets, week, rec)
