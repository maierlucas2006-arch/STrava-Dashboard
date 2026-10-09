"""Konkrete Einheiten mit Zielwerten (Watt, Pace, Puls) aus deinen Schwellenwerten."""
from __future__ import annotations

from dataclasses import dataclass

from triathlon.settings import Profile
from triathlon.units import fmt_pace

SPORT_ICONS = {
    "swim": "🏊",
    "bike": "🚴",
    "run": "🏃",
    "rest": "😴",
    "recovery": "🧘",
    "race": "🏁",
    "strength": "🏋️",
}

# Renntempo je Distanz: Rad als Anteil der FTP, Laufen als Faktor auf die Schwellen-Pace
RACE_BIKE_IF = {
    "Sprint": (0.95, 1.02),
    "Olympisch": (0.88, 0.95),
    "Mitteldistanz": (0.78, 0.85),
    "Langdistanz": (0.68, 0.75),
}
RACE_RUN_FACTOR = {"Sprint": 0.98, "Olympisch": 1.02, "Mitteldistanz": 1.10, "Langdistanz": 1.22}


@dataclass
class Session:
    sport: str      # swim / bike / run / rest / recovery / race
    kind: str       # easy / hard / long / brick / rest / recovery / race / activation
    minutes: int
    title: str
    detail: str

    @property
    def icon(self) -> str:
        return SPORT_ICONS.get(self.sport, "•")

    @property
    def is_key(self) -> bool:
        """Schlüsseleinheit (hart oder lang)."""
        return self.kind in ("hard", "long", "brick")


class _Targets:
    """Hilfsklasse, die Zielbereiche als Text liefert (oder leer, wenn Werte fehlen)."""

    def __init__(self, p: Profile):
        self.p = p

    def watts(self, lo: float, hi: float) -> str:
        if not self.p.ftp:
            return ""
        return f" ({round(lo * self.p.ftp)}–{round(hi * self.p.ftp)} W)"

    def race_watts(self) -> str:
        lo, hi = RACE_BIKE_IF.get(self.p.race_distance, RACE_BIKE_IF["Langdistanz"])
        return self.watts(lo, hi)

    def hr_below(self, share: float) -> str:
        if not self.p.lthr:
            return ""
        return f", Puls unter {round(share * self.p.lthr)}"

    def pace(self, factor: float) -> str:
        if not self.p.threshold_pace:
            return ""
        return f"{fmt_pace(self.p.threshold_pace * factor)}/km"

    def easy_pace(self) -> str:
        if not self.p.threshold_pace:
            return ""
        tp = self.p.threshold_pace
        return f", ca. {fmt_pace(tp * 1.25)}–{fmt_pace(tp * 1.35)}/km"

    def race_pace(self) -> str:
        factor = RACE_RUN_FACTOR.get(self.p.race_distance, 1.22)
        text = self.pace(factor)
        return f" ({text})" if text else ""

    def threshold_pace(self) -> str:
        text = self.pace(1.0)
        return f" ({text})" if text else ""

    def css(self, plus: float = 0) -> str:
        if not self.p.css:
            return ""
        return f" ({fmt_pace(self.p.css + plus)}/100 m)"

    def swim_distance(self, minutes: int) -> int:
        pace = (self.p.css + 10) if self.p.css else 130  # s/100 m locker
        meters = minutes * 60 / pace * 100 * 0.85        # ~15 % Pausen
        return int(round(meters / 100) * 100)


def describe(sport: str, kind: str, phase: str, minutes: int, profile: Profile) -> Session:
    t = _Targets(profile)
    m = minutes

    if sport == "rest":
        return Session("rest", "rest", 0, "Ruhetag (Ausdauer)",
                       "Erholung: Spaziergang, Mobility oder 15–20 min Dehnen.")
    if sport == "recovery":
        return Session("recovery", "recovery", m, "Aktive Erholung",
                       f"Sehr locker Rad oder Schwimmen{t.hr_below(0.80)}. Alternativ komplett frei.")
    if sport == "race":
        return Session("race", "race", 0, f"Wettkampf: {profile.race_name}",
                       "Viel Erfolg! Halte dich an deinen Pacing- und Verpflegungsplan.")
    if kind == "activation":
        return Session("bike", "activation", 30, "Kurz aktivieren",
                       f"20 min locker Rad mit 3×1 min Renntempo{t.race_watts()}, danach 10 min "
                       "Lauf mit 3 Steigerungen. Material checken, früh schlafen.")

    if sport == "swim":
        dist = t.swim_distance(m)
        if kind == "easy":
            return Session("swim", kind, m, "Schwimmen locker",
                           f"ca. {dist} m: Einschwimmen, 8×50 m Technik (z. B. Abschlag, Faustschwimmen), "
                           f"Rest gleichmäßig locker{t.css(10)}.")
        hard = {
            "prep": "Technik & Tempo: 12×50 m zügig, je 20 s Pause, Fokus Wasserlage und Armzug.",
            "base": f"Hauptteil 10×100 m @ CSS{t.css()}, je 15 s Pause.",
            "build": f"Hauptteil 4×400 m @ CSS + 3 s{t.css(3)}, je 30 s Pause.",
            "peak": "3.000–3.800 m am Stück im Renntempo – wenn möglich Freiwasser mit Neo.",
            "taper": f"Kurz und knackig: 6×100 m Renntempo{t.css(3)}, sonst locker.",
            "recovery": "Locker mit ein paar Steigerungen, nur nach Gefühl.",
        }[phase]
        return Session("swim", kind, m, "Schwimmen Qualität", f"ca. {dist} m. {hard}")

    if sport == "bike":
        if kind == "easy":
            return Session("bike", kind, m, "Rad locker (GA1)",
                           f"Locker im GA1{t.watts(0.56, 0.75)}{t.hr_below(0.85)}, Kadenz 85–95.")
        if kind == "long":
            return Session("bike", kind, m, "Lange Ausfahrt",
                           f"Ruhig im GA1{t.watts(0.56, 0.75)}. Verpflegung üben: 60–90 g "
                           "Kohlenhydrate pro Stunde.")
        if kind == "brick":
            main = {
                "build": f"davon 2×45 min Renntempo{t.race_watts()}",
                "peak": f"Renn-Simulation: große Teile im Renntempo{t.race_watts()}, Rennverpflegung testen",
            }.get(phase, f"ruhig im GA1{t.watts(0.56, 0.75)}")
            return Session("bike", kind, m, "Lange Ausfahrt + Koppellauf",
                           f"Rad, {main}. Direkt danach 20–30 min Koppellauf{t.race_pace()}.")
        hard = {
            "prep": f"3×10 min Sweet Spot{t.watts(0.88, 0.94)}, je 5 min locker dazwischen.",
            "base": f"2×20 min Sweet Spot{t.watts(0.88, 0.94)}, 5 min Pause.",
            "build": f"3×20 min zügig{t.watts(0.80, 0.88)}, je 5 min Pause.",
            "peak": f"2×45 min Renntempo{t.race_watts()} + 10 min an der Schwelle{t.watts(0.95, 1.0)}.",
            "taper": f"3×8 min Renntempo{t.race_watts()}, sonst locker.",
            "recovery": "Locker nach Gefühl, keine Intervalle.",
        }[phase]
        return Session("bike", kind, m, "Rad Qualität", f"Hauptteil: {hard}")

    if sport == "run":
        if kind == "easy":
            return Session("run", kind, m, "Lauf locker",
                           f"Locker{t.hr_below(0.89)}{t.easy_pace()}.")
        if kind == "long":
            extra = f" Die letzten 20 min im Renntempo{t.race_pace()}." if phase == "peak" else ""
            return Session("run", kind, m, "Langer Lauf",
                           f"Ruhig{t.hr_below(0.89)}{t.easy_pace()}.{extra}")
        hard = {
            "prep": "Locker mit 6×20 s Steigerungen und Lauf-ABC (Technik).",
            "base": f"3×8 min an der Schwelle{t.threshold_pace()}, je 2 min Trabpause.",
            "build": f"6×1 km an der Schwelle{t.threshold_pace()}, je 90 s Trabpause.",
            "peak": f"40 min am Stück im Renntempo{t.race_pace()}.",
            "taper": f"4×3 min Renntempo{t.race_pace()}, sonst locker.",
            "recovery": "Locker nach Gefühl.",
        }[phase]
        return Session("run", kind, m, "Lauf Qualität", f"Inkl. Ein-/Auslaufen. {hard}")

    raise ValueError(f"Unbekannte Sportart: {sport}")
