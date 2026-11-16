"""Trainingsgalerie: Einheiten für Schwimmen, Rad, Laufen und Koppeltraining.

Jede Einheit ist in einer kurzen Schreibweise notiert, z. B.
``15min@58, 3x(10min@90, 5min@55), 10min@50``:

* Dauer ``10min``, ``30s``, ``1:30`` (Minuten:Sekunden) oder Strecke ``400m``, ``2km``
* ``@90`` Intensität in Prozent der Schwelle – Rad: FTP, Laufen: Schwellentempo,
  Schwimmen: CSS-Tempo. Bereiche wie ``@88-94`` sind erlaubt.
* ``3x(…)`` oder ``8x50m@85`` Wiederholungen
* ``r20`` 20 Sekunden Pause (stehend), ``[Text]`` Hinweis zur Ausführung
* Koppeltraining: Abschnitte mit ``|`` trennen, Sportart voranstellen:
  ``bike: 60min@70 | run: 20min@85``

Die Zielwerte (Watt, Pace) werden aus deinen Schwellenwerten im Profil
berechnet. Zonen nach Coggan (Rad), Friel (Laufen, auf Tempo umgerechnet)
und CSS-Bereichen (Schwimmen).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from triathlon.settings import Profile
from triathlon.units import fmt_duration, fmt_pace

SPORTS = {"bike": "Rad", "run": "Laufen", "swim": "Schwimmen", "brick": "Koppel"}

# Ohne eingetragene Schwelle wird mit diesen Werten nur die Dauer geschätzt.
DEFAULT_RUN_PACE = 300.0   # s/km (5:00/km)
DEFAULT_CSS = 120.0        # s/100 m (2:00/100 m)

# --------------------------------------------------------------------------- Zonen

ZONE_NAMES = {0: "Pause", 1: "Regeneration", 2: "Grundlage", 3: "Tempo", 4: "Schwelle",
              5: "VO2max", 6: "Anaerob", 7: "Sprint"}

# Obergrenzen in % der Schwelle für Zone 1–6, darüber Zone 7.
# Rad: Coggan (% FTP). Laufen: Friel-Pace-Zonen, umgerechnet auf % des Schwellentempos.
# Schwimmen: CSS-Bereiche (% des CSS-Tempos).
ZONE_UPPER = {
    "bike": (55, 75, 90, 105, 120, 150),
    "run": (77, 88, 94, 102, 111, 122),
    "swim": (85, 92, 97, 102, 108, 117),
}

# Wie hoch ein Block maximal ausschlägt (% der Schwelle = volle Höhe)
PROFILE_SCALE = {"bike": 150.0, "run": 135.0, "swim": 125.0}


def zone(sport: str, pct: float) -> int:
    if pct <= 0:
        return 0
    for number, upper in enumerate(ZONE_UPPER[sport], start=1):
        if pct <= upper:
            return number
    return 7


# --------------------------------------------------------------------------- Kategorien

@dataclass(frozen=True)
class Category:
    key: str
    name: str
    purpose: str
    key_zones: tuple[int, ...] | None   # Zonen, um die es geht (None = gemischt)


CATEGORIES: dict[str, Category] = {c.key: c for c in [
    Category("regeneration", "Regeneration",
             "Sehr locker. Fördert die Erholung zwischen harten Tagen und zählt kaum als Belastung.", (1,)),
    Category("grundlage", "Grundlage",
             "Das Fundament: ruhige, oft lange Einheiten. Ausdauerprofis trainieren rund 80 % so locker.", (2,)),
    Category("tempo", "Tempo",
             "Zügig, aber kontrolliert, zwischen Grundlage und Schwelle. Nah am Renntempo langer Distanzen.", (3,)),
    Category("sweetspot", "Sweet Spot",
             "Knapp unter der Schwelle (88–94 % FTP): viel Reiz für die Ausdauerleistung bei überschaubarer "
             "Ermüdung.", (3, 4)),
    Category("schwelle", "Schwelle",
             "Rund um die Schwelle. Hebt FTP, Schwellentempo und CSS – längere Intervalle mit kurzen Pausen.", (4,)),
    Category("vo2max", "VO2max",
             "Wenige Minuten hart: steigert die maximale Sauerstoffaufnahme. Höchstens ein- bis zweimal pro "
             "Woche.", (5,)),
    Category("anaerob", "Anaerob",
             "30 Sekunden bis 2 Minuten sehr hart, mit langen Pausen: Laktattoleranz und Tempohärte.", (6,)),
    Category("sprint", "Sprint",
             "Kurze Maximalsprints mit voller Erholung: Schnelligkeit, Kraft und ein sauberer Bewegungsablauf.", (7,)),
    Category("kraft", "Kraftausdauer",
             "Berg, niedrige Trittfrequenz oder Paddles: Kraft direkt in der Sportart aufbauen.", None),
    Category("technik", "Technik",
             "Bewegung verbessern: Drills, Kadenz, Wasserlage. Locker genug, um sauber zu bleiben.", None),
    Category("wettkampf", "Wettkampf",
             "Renntempo und Rennabläufe: Pacing, Verpflegung und Wechsel für deine Distanz.", None),
]}

# Was heute sinnvoll ist: nach Ampel (Regeneration) und Trainingsphase
READINESS_CATEGORIES = {
    "green": None,
    "yellow": ("regeneration", "grundlage", "technik"),
    "red": ("regeneration",),
}
PHASE_FOCUS = {
    "prep": ("grundlage", "technik", "kraft", "sprint"),
    "base": ("grundlage", "sweetspot", "schwelle", "technik"),
    "build": ("schwelle", "vo2max", "wettkampf", "grundlage"),
    "peak": ("wettkampf", "schwelle", "grundlage"),
    "taper": ("wettkampf", "sprint", "regeneration"),
    "recovery": ("regeneration", "technik", "grundlage"),
}


def suitable_categories(level: str, phase_key: str) -> list[str]:
    """Kategorien, die heute passen: Phasenschwerpunkt, begrenzt durch die Ampel."""
    allowed = READINESS_CATEGORIES.get(level)
    focus = PHASE_FOCUS.get(phase_key, PHASE_FOCUS["base"])
    if allowed is None:
        return list(focus)
    picked = [c for c in focus if c in allowed]
    return picked or list(allowed)


# --------------------------------------------------------------------------- Schreibweise

class WorkoutSyntaxError(ValueError):
    pass


@dataclass(frozen=True)
class Step:
    sport: str
    seconds: float | None      # bei Zeitangabe
    meters: float | None       # bei Streckenangabe
    low: float                 # % der Schwelle, 0 = Pause
    high: float
    note: str = ""

    @property
    def pct(self) -> float:
        return (self.low + self.high) / 2

    @property
    def is_rest(self) -> bool:
        return self.high <= 0


@dataclass(frozen=True)
class Repeat:
    count: int
    items: tuple


_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_REPEAT = re.compile(r"(\d+)\s*x")
_REST = re.compile(r"r(\d+)\b")


class _Parser:
    def __init__(self, text: str, sport: str):
        self.s, self.i, self.sport = text, 0, sport

    # -- Hilfen
    def _ws(self) -> None:
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    def _peek(self, token: str) -> bool:
        self._ws()
        return self.s.startswith(token, self.i)

    def _eat(self, token: str) -> None:
        if not self._peek(token):
            self._fail(f"„{token}“ erwartet")
        self.i += len(token)

    def _fail(self, message: str):
        raise WorkoutSyntaxError(f"{message} an Stelle {self.i}: {self.s!r}")

    def _number(self) -> float:
        self._ws()
        m = _NUMBER.match(self.s, self.i)
        if not m:
            self._fail("Zahl erwartet")
        self.i = m.end()
        return float(m.group())

    # -- Grammatik
    def parse(self) -> list:
        items = self._seq()
        self._ws()
        if self.i != len(self.s):
            self._fail("Unerwartetes Zeichen")
        return items

    def _seq(self) -> list:
        items = self._item()
        while self._peek(","):
            self._eat(",")
            items += self._item()
        return items

    def _item(self) -> list:
        self._ws()
        rest = _REST.match(self.s, self.i)
        if rest:
            self.i = rest.end()
            return [self._rest(float(rest.group(1)))]
        rep = _REPEAT.match(self.s, self.i)
        if rep:
            self.i = rep.end()
            count = int(rep.group(1))
            if count < 1:
                self._fail("Wiederholungen müssen mindestens 1 sein")
            if self._peek("("):
                self._eat("(")
                body = self._seq()
                self._eat(")")
            else:
                body = self._step()
            return [Repeat(count, tuple(body))]
        return self._step()

    def _rest(self, seconds: float) -> Step:
        if seconds <= 0:
            self._fail("Pause muss länger als 0 s sein")
        return Step(self.sport, seconds, None, 0.0, 0.0, "Pause")

    def _step(self) -> list:
        seconds, meters = self._duration()
        self._eat("@")
        low = high = self._number()
        if self._peek("-"):
            self._eat("-")
            high = self._number()
        if low <= 0 or high < low:
            self._fail("Intensität muss positiv sein (Bereich: niedrig-hoch)")
        note = ""
        if self._peek("["):
            end = self.s.find("]", self.i)
            if end < 0:
                self._fail("„]“ fehlt")
            note = self.s[self.i + 1:end].strip()
            self.i = end + 1
        steps = [Step(self.sport, seconds, meters, low, high, note)]
        self._ws()
        rest = _REST.match(self.s, self.i)
        if rest:
            self.i = rest.end()
            steps.append(self._rest(float(rest.group(1))))
        return steps

    def _duration(self) -> tuple[float | None, float | None]:
        value = self._number()
        if self.s.startswith(":", self.i):
            self.i += 1
            m = re.compile(r"\d{2}").match(self.s, self.i)
            if not m or int(m.group()) >= 60:
                self._fail("Sekunden im Format m:ss erwartet")
            self.i = m.end()
            seconds = value * 60 + int(m.group())
            return self._positive(seconds), None
        for unit, factor, is_time in (("min", 60, True), ("km", 1000, False), ("m", 1, False), ("s", 1, True)):
            if self.s.startswith(unit, self.i):
                self.i += len(unit)
                amount = self._positive(value * factor)
                return (amount, None) if is_time else (None, amount)
        self._fail("Einheit (min, s, m, km) erwartet")

    def _positive(self, value: float) -> float:
        if value <= 0:
            self._fail("Dauer bzw. Strecke muss größer als 0 sein")
        return value


def parse(notation: str, sport: str) -> list[tuple[str, list]]:
    """Zerlegt die Schreibweise in Abschnitte ``(Sportart, Bausteine)``."""
    segments = []
    for part in notation.split("|"):
        part = part.strip()
        seg_sport = sport
        m = re.match(r"(swim|bike|run)\s*:", part)
        if m:
            seg_sport, part = m.group(1), part[m.end():]
        if seg_sport not in ZONE_UPPER:
            raise WorkoutSyntaxError(f"Koppeltraining braucht je Abschnitt eine Sportart: {notation!r}")
        items = _Parser(part, seg_sport).parse()
        if seg_sport == "bike" and any(step.meters is not None for step in flatten(items)):
            raise WorkoutSyntaxError(f"Rad-Abschnitte bitte mit Zeiten statt Strecken: {notation!r}")
        segments.append((seg_sport, items))
    return segments


def flatten(items: list) -> list[Step]:
    out: list[Step] = []
    for item in items:
        if isinstance(item, Repeat):
            body = flatten(list(item.items))
            for _ in range(item.count):
                out.extend(body)
        else:
            out.append(item)
    return out


# --------------------------------------------------------------------------- Schwellen & Zielwerte

@dataclass(frozen=True)
class Thresholds:
    ftp: float | None = None
    run_pace: float | None = None   # s/km
    css: float | None = None        # s/100 m

    @classmethod
    def from_profile(cls, profile: Profile) -> "Thresholds":
        return cls(profile.ftp or None, profile.threshold_pace or None, profile.css or None)

    def has(self, sport: str) -> bool:
        return bool({"bike": self.ftp, "run": self.run_pace, "swim": self.css}.get(sport))

    def speed(self, sport: str) -> float:
        """m/s an der Schwelle (für Laufen und Schwimmen)."""
        if sport == "run":
            return 1000 / (self.run_pace or DEFAULT_RUN_PACE)
        if sport == "swim":
            return 100 / (self.css or DEFAULT_CSS)
        raise ValueError(sport)

    def seconds(self, step: Step) -> float:
        if step.seconds is not None:
            return step.seconds
        return step.meters / (self.speed(step.sport) * step.pct / 100)

    def meters(self, step: Step) -> float:
        if step.meters is not None:
            return step.meters
        if step.sport == "bike" or step.is_rest:
            return 0.0
        return step.seconds * self.speed(step.sport) * step.pct / 100

    def target(self, step: Step) -> str:
        """Zielwert als Text, z. B. ``238 W``, ``4:41/km`` oder ``1:52/100 m``."""
        if step.is_rest:
            return "Pause"
        lo, hi = step.low / 100, step.high / 100
        if step.sport == "bike":
            if not self.ftp:
                return _range(step.low, step.high, "{:g}") + " % FTP"
            return _range(round(lo * self.ftp), round(hi * self.ftp), "{}") + " W"
        base = self.run_pace if step.sport == "run" else self.css
        unit = "/km" if step.sport == "run" else "/100 m"
        if not base:
            return _range(step.low, step.high, "{:g}") + (" % Schwellentempo" if step.sport == "run" else " % CSS")
        fast, slow = fmt_pace(base / hi), fmt_pace(base / lo)
        return (fast if fast == slow else f"{fast}–{slow}") + unit


def _range(lo, hi, fmt: str) -> str:
    return fmt.format(lo) if lo == hi else f"{fmt.format(lo)}–{fmt.format(hi)}"


def fmt_amount(step: Step) -> str:
    """Dauer oder Strecke so, wie sie notiert wurde."""
    if step.meters is not None:
        if step.meters >= 1000 and step.meters % 100 == 0:
            return f"{step.meters / 1000:g} km".replace(".", ",")
        return f"{step.meters:g} m"
    total = int(round(step.seconds))
    if total < 60:
        return f"{total} s"
    if total % 60 == 0:
        return f"{total // 60} min"
    return f"{total // 60}:{total % 60:02d} min"


# --------------------------------------------------------------------------- Einheiten

@dataclass(frozen=True)
class Block:
    """Ein Abschnitt im Zeitverlauf (für Grafik und Kennzahlen)."""
    step: Step
    seconds: float
    meters: float
    zone: int


@dataclass(frozen=True)
class Workout:
    id: str
    sport: str
    category: str
    name: str
    notation: str
    description: str
    segments: list = field(compare=False, hash=False, repr=False)

    @property
    def category_name(self) -> str:
        return CATEGORIES[self.category].name

    def blocks(self, th: Thresholds) -> list[Block]:
        out = []
        for _, items in self.segments:
            for step in flatten(items):
                out.append(Block(step, th.seconds(step), th.meters(step), zone(step.sport, step.pct)))
        return out

    def summary(self, th: Thresholds) -> "Summary":
        blocks = self.blocks(th)
        seconds = sum(b.seconds for b in blocks)
        tss = 0.0
        meters: dict[str, float] = {}
        for b in blocks:
            if b.step.is_rest:
                continue
            exponent = 3 if b.step.sport == "swim" else 2
            tss += b.seconds / 3600 * (b.step.pct / 100) ** exponent * 100
            if b.step.sport != "bike":
                meters[b.step.sport] = meters.get(b.step.sport, 0.0) + b.meters
        return Summary(seconds, round(tss), meters)


@dataclass(frozen=True)
class Summary:
    seconds: float
    tss: int
    meters: dict

    @property
    def minutes(self) -> float:
        return self.seconds / 60

    @property
    def duration_text(self) -> str:
        return fmt_duration(self.seconds)

    def distance_text(self, sport: str) -> str | None:
        m = self.meters.get(sport)
        if not m:
            return None
        if sport == "swim":
            return f"{round(m / 50) * 50:,.0f} m".replace(",", ".")
        return f"{m / 1000:.1f} km".replace(".", ",")


def load_label(tss: float, ctl: float) -> str:
    """Wie fordernd die Einheit für deinen aktuellen Fitnessstand ist (CTL ≈ Ø Tagesbelastung)."""
    ratio = tss / max(ctl, 30.0)
    if ratio < 0.6:
        return "leicht"
    if ratio < 1.2:
        return "mittel"
    if ratio < 2.0:
        return "fordernd"
    return "sehr fordernd"


def _slug(text: str) -> str:
    text = text.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _build(rows: list[tuple[str, str, str, str, str]]) -> list[Workout]:
    workouts, seen = [], set()
    for sport, category, name, notation, description in rows:
        wid = f"{sport}-{_slug(name)}"
        if wid in seen:
            raise ValueError(f"Doppelte Einheit: {wid}")
        if category not in CATEGORIES:
            raise ValueError(f"Unbekannte Kategorie {category!r} bei {name}")
        seen.add(wid)
        workouts.append(Workout(wid, sport, category, name, notation, description,
                                parse(notation, "bike" if sport == "brick" else sport)))
    return workouts


# --------------------------------------------------------------------------- Katalog

# Aufwärmen mit kurzen Öffnern vor harten Einheiten
B_WU = "10min@55, 3x(1min@95, 1min@55), 4min@60"
R_WU = "15min@78, 4x(20s@112[Steigerung], 40s@72)"
S_WU = "400m@84[Einschwimmen, locker gemischt]"
S_WU2 = "400m@84[Einschwimmen], 4x(50m@92[steigern] r15)"
S_CD = "200m@80[Ausschwimmen]"

_ROWS: list[tuple[str, str, str, str, str]] = [
    # ------------------------------------------------------------------ Rad
    ("bike", "regeneration", "Locker kurbeln", "5min@45, 35min@52, 5min@45",
     "45 Minuten ganz locker, gerne auf der Rolle. Beine lockern, Puls ruhig halten."),
    ("bike", "regeneration", "Spin-out mit hoher Kadenz", "10min@48, 4x(1min@55[Kadenz 100+], 2min@48), 8min@45",
     "Eine halbe Stunde mit kurzen Phasen hoher Trittfrequenz – ohne Druck aufs Pedal."),
    ("bike", "regeneration", "Erholung mit Kadenzspiel",
     "10min@45, 5x(3min@55[Kadenz 95–105], 3min@50), 20min@50",
     "Eine Stunde aktive Erholung: Die Trittfrequenz wechselt, die Belastung nicht."),
    ("bike", "regeneration", "Kaffeerunde", "5min@45, 65min@55, 5min@45",
     "Gemütlich draußen, gerne mit Pause im Café. Nicht von schnelleren Gruppen mitziehen lassen."),

    ("bike", "grundlage", "GA1 90", "10min@55, 70min@68, 10min@55",
     "Klassische Grundlage: 70 Minuten gleichmäßig im GA1."),
    ("bike", "grundlage", "GA1 2 Stunden", "15min@55, 95min@68, 10min@55",
     "Zwei ruhige Stunden. Gleichmäßig treten, regelmäßig trinken."),
    ("bike", "grundlage", "Lange Ausfahrt 3 h", "15min@55, 150min@68[alle 20 min essen und trinken], 15min@55",
     "Fettstoffwechsel und Sitzfleisch. Gute Gelegenheit, 60–90 g Kohlenhydrate pro Stunde zu üben."),
    ("bike", "grundlage", "Lange Ausfahrt 4 h", "15min@55, 210min@67[60–90 g Kohlenhydrate pro Stunde], 15min@55",
     "Die lange Einheit für die Langdistanz. Ruhig bleiben, auch wenn es sich leicht anfühlt."),
    ("bike", "grundlage", "GA1 mit Kadenzwechsel", "10min@55, 5x(8min@68[85 U/min], 3min@68[100+ U/min]), 10min@55",
     "Grundlage mit wechselnder Trittfrequenz – trainiert einen runden, ökonomischen Tritt."),
    ("bike", "grundlage", "Endurance-Progression", "15min@55, 30min@64, 30min@69, 30min@74, 15min@55",
     "Zwei Stunden, alle 30 Minuten ein wenig mehr. Endet am oberen Rand von GA1."),
    ("bike", "grundlage", "GA1 mit Antritten", "15min@55, 6x(9:45@68, 15s@150[Antritt im Sitzen]), 15min@55",
     "Grundlage mit kurzen Antritten, damit die Beine nicht einschlafen."),

    ("bike", "tempo", "Tempo 3x15", "10min@55, 5min@65, 3x(15min@83, 5min@55), 10min@50",
     "Drei zügige Blöcke im oberen Ausdauerbereich. Gut zum Einstieg in strukturiertes Training."),
    ("bike", "tempo", "Tempo 2x30", "10min@55, 5min@65, 2x(30min@80, 5min@55), 10min@50",
     "Lange Tempoblöcke für Mittel- und Langdistanz. Ruhiger Oberkörper, gleichmäßiger Druck."),
    ("bike", "tempo", "Tempo am Stück", "10min@55, 5min@65, 60min@78, 10min@50",
     "Eine Stunde gleichmäßig im Tempobereich – Konzentration und Pacing."),
    ("bike", "tempo", "Tempo-Pyramide",
     "15min@58, 10min@78, 5min@55, 15min@82, 5min@55, 20min@86, 5min@55, 15min@82, 5min@55, 10min@78, 10min@50",
     "Blöcke von 10 bis 20 Minuten, die Spitze in der Mitte. Abwechslungsreich und trotzdem kontrolliert."),
    ("bike", "tempo", "Tempo mit Spitzen", "15min@58, 4x(10min@82, 30s@115, 1:30@82, 4min@55), 10min@50",
     "Tempo mit kurzen Tempowechseln, wie sie draußen an Kuppen und Kreuzungen entstehen."),

    ("bike", "sweetspot", "Sweet Spot 3x10", "15min@58, 3x(10min@90, 5min@55), 10min@50",
     "Der Einstieg in Sweet Spot: kurz genug, um die Intensität sauber zu halten."),
    ("bike", "sweetspot", "Sweet Spot 2x20", "15min@58, 2x(20min@90, 5min@55), 10min@50",
     "Der Klassiker. Zwei lange Blöcke knapp unter der Schwelle."),
    ("bike", "sweetspot", "Sweet Spot 3x15", "15min@58, 3x(15min@91, 5min@55), 10min@50",
     "45 Minuten Sweet Spot in drei Blöcken."),
    ("bike", "sweetspot", "Sweet Spot 4x12", "15min@58, 4x(12min@92, 4min@55), 10min@50",
     "Etwas höher, mit kürzeren Pausen. Fordert die Konzentration."),
    ("bike", "sweetspot", "Sweet Spot 2x30", "15min@58, 2x(30min@89, 8min@55), 10min@50",
     "Eine Stunde Sweet Spot – die Steigerung, wenn 2×20 locker geht."),
    ("bike", "sweetspot", "Sweet Spot 60", "20min@58, 60min@88, 10min@50",
     "Eine Stunde am Stück am unteren Rand des Sweet Spots. Mental anspruchsvoll."),
    ("bike", "sweetspot", "Sweet-Spot-Wellen", "15min@58, 3x(4x(2:30@88, 30s@100), 5min@55), 10min@50",
     "Sweet Spot mit kurzen Wellen bis an die Schwelle – trainiert den Abbau von Laktat unter Last."),

    ("bike", "schwelle", "Schwelle 2x20", f"{B_WU}, 2x(20min@97, 10min@55), 10min@50",
     "Der Standard für die FTP: zweimal 20 Minuten knapp unter der Schwelle."),
    ("bike", "schwelle", "Schwelle 3x12", f"{B_WU}, 3x(12min@100, 6min@55), 10min@50",
     "Genau an der Schwelle, mit großzügigen Pausen."),
    ("bike", "schwelle", "Schwelle 4x8", f"{B_WU}, 4x(8min@102, 4min@55), 10min@50",
     "Kürzere Blöcke knapp über der Schwelle."),
    ("bike", "schwelle", "Over-Under 3x9", f"{B_WU}, 3x(3x(2min@95, 1min@108), 5min@55), 10min@50",
     "Wechsel knapp unter und über der Schwelle – wie bei Tempowechseln im Rennen."),
    ("bike", "schwelle", "Schwelle 30 am Stück", f"{B_WU}, 30min@96, 10min@50",
     "Ein langer Block. Gleichmäßig beginnen, nicht überpacen."),
    ("bike", "schwelle", "Cruise-Intervalle 5x6", f"{B_WU}, 5x(6min@103, 3min@55), 10min@50",
     "Fünf kurze Schwellenblöcke mit kurzen Pausen."),
    ("bike", "schwelle", "Schwellen-Leiter", f"{B_WU}, 8min@100, 4min@55, 10min@98, 5min@55, 12min@96, 10min@50",
     "Die Blöcke werden länger, die Intensität sinkt leicht – endet mit 12 Minuten."),

    ("bike", "vo2max", "VO2max 5x4", f"{B_WU}, 5x(4min@112, 4min@50), 10min@50",
     "Fünfmal vier Minuten hart, gleich lange Pausen. Gleichmäßig über alle Intervalle fahren."),
    ("bike", "vo2max", "VO2max 6x3", f"{B_WU}, 6x(3min@115, 3min@50), 10min@50",
     "Etwas kürzer und höher als 5×4."),
    ("bike", "vo2max", "VO2max 4x5", f"{B_WU}, 4x(5min@110, 5min@50), 10min@50",
     "Längere VO2max-Intervalle am unteren Rand der Zone."),
    ("bike", "vo2max", "30/15 Intervalle", f"{B_WU}, 3x(13x(30s@120, 15s@50), 3min@50), 10min@50",
     "Drei Serien à 13 × 30 s hart, 15 s locker. Die kurzen Pausen halten die Sauerstoffaufnahme lange oben."),
    ("bike", "vo2max", "40/20 Intervalle", f"{B_WU}, 2x(10x(40s@118, 20s@50), 5min@50), 10min@50",
     "Zwei Serien à 10 × 40 s hart, 20 s locker."),
    ("bike", "vo2max", "VO2max-Pyramide",
     f"{B_WU}, 2min@116, 2min@50, 3min@113, 3min@50, 4min@110, 4min@50, 3min@113, 3min@50, 2min@116, 2min@50, 10min@50",
     "2–3–4–3–2 Minuten hart. Die Intensität passt sich der Länge an."),

    ("bike", "anaerob", "Anaerob 8x1", f"{B_WU}, 8x(1min@130, 4min@50), 10min@50",
     "Acht harte Minuten mit langen Pausen. Jede Wiederholung voll, aber gleichmäßig."),
    ("bike", "anaerob", "Anaerob 6x90 s", f"{B_WU}, 6x(1:30@125, 4:30@50), 10min@50",
     "90 Sekunden sehr hart – Laktattoleranz für Attacken und steile Rampen."),
    ("bike", "anaerob", "Anaerob 10x40 s", f"{B_WU}, 10x(40s@140, 2:20@50), 10min@50",
     "Kurz und sehr hart, mit Pausen, die dreimal so lang sind wie die Belastung."),
    ("bike", "anaerob", "Tabata 2x8", f"{B_WU}, 2x(8x(20s@150, 10s@45), 6min@50), 10min@50",
     "Zwei Serien 8 × 20 s hart, 10 s Pause. Kurz, aber brutal."),
    ("bike", "anaerob", "Zwei-Minuten-Leiter", f"{B_WU}, 3x(2min@122, 5min@50), 2x(1min@135, 4min@50), 10min@50",
     "Erst drei Blöcke à 2 Minuten, dann zwei kürzere, härtere."),

    ("bike", "sprint", "Sprints 8x10 s", "20min@60, 8x(10s@200[aus dem Sattel, maximal], 4:50@50), 10min@50",
     "Maximale Sprints mit voller Erholung dazwischen. Qualität vor Menge."),
    ("bike", "sprint", "Sprints aus dem Rollen", "15min@60, 6x(15s@180, 4:45@55), 15min@50",
     "Aus mittlerem Tempo voll antreten, wie bei einem Zielsprint."),
    ("bike", "sprint", "Antritte im Grundlagentempo", "15min@58, 10x(15s@170[Antritt], 5:45@65), 15min@55",
     "Grundlage mit zehn kräftigen Antritten – gut in Phasen ohne viel Intensität."),
    ("bike", "sprint", "Stehende Starts", "15min@60, 6x(8s@220[aus kleinem Gang, fast stehend], 5min@50), 10min@50",
     "Explosive Starts aus fast stehendem Rad. Schult Kraft und Schnelligkeit."),
    ("bike", "sprint", "Sprint-Serien 3x3", "15min@60, 3x(3x(12s@190, 2:48@55), 5min@50), 10min@50",
     "Drei Serien à drei Sprints mit kurzer Pause in der Serie."),

    ("bike", "kraft", "K3 5x6", "15min@58, 5x(6min@82[Kadenz 50–60, Oberkörper ruhig], 4min@55), 10min@50",
     "Kraftausdauer mit niedriger Trittfrequenz. Knie schonen – bei Schmerzen abbrechen."),
    ("bike", "kraft", "K3 4x10", "15min@58, 4x(10min@80[Kadenz 55], 5min@55), 10min@50",
     "Längere K3-Blöcke für Fortgeschrittene."),
    ("bike", "kraft", "K3 3x15", "15min@58, 3x(15min@78[Kadenz 55–60], 5min@55), 10min@50",
     "Drei lange Blöcke bei niedriger Kadenz – nah am Druck auf flachen Langdistanz-Strecken."),
    ("bike", "kraft", "Bergintervalle 6x5", "15min@58, 6x(5min@95[am Anstieg, Kadenz 65–75], 5min@50[abrollen]), 10min@50",
     "Draußen an einem gleichmäßigen Anstieg von etwa fünf Minuten."),
    ("bike", "kraft", "Kraftsprints bergauf", "15min@58, 8x(20s@160[großer Gang, aus niedriger Kadenz], 4:40@55), 10min@50",
     "Am kurzen Hügel aus niedriger Trittfrequenz antreten."),

    ("bike", "technik", "Einbeinig & Kadenz",
     "10min@55, 4x(1min@50[nur linkes Bein], 1min@50[nur rechtes Bein], 1min@55), "
     "5x(1min@60[Kadenz 110+], 2min@55), 18min@65[runder Tritt], 5min@50",
     "Einbeinig treten und hohe Kadenz: deckt tote Punkte im Tritt auf. Am besten auf der Rolle."),
    ("bike", "technik", "Kadenzleiter",
     "10min@55, 3x(2min@60[90 U/min], 2min@60[100 U/min], 2min@60[110 U/min], 1min@60[120 U/min], 2min@55), 8min@50",
     "Die Trittfrequenz steigt in Stufen bei gleicher Leistung. Ruhig auf dem Sattel bleiben."),
    ("bike", "technik", "Aeroposition halten", "10min@55, 4x(12min@72[Aerolenker, Position halten], 3min@60[aufrecht]), 5min@50",
     "Gewöhnt Nacken, Rücken und Hüfte an die Zeitfahrposition – entscheidend auf der Langdistanz."),
    ("bike", "technik", "Pedaltechnik-Mix",
     "10min@55, 3x(30s@60[einbeinig links], 30s@60[einbeinig rechts], 2min@65[runder Tritt]), "
     "6x(30s@70[Kadenz 120], 1:30@55), 10min@50",
     "Kurz und abwechslungsreich: einbeinig, rund treten, hohe Kadenz."),

    ("bike", "wettkampf", "Langdistanz-Tempo 3x30",
     "15min@60, 3x(30min@74[Renntempo, alle 20 min verpflegen], 5min@60), 10min@55",
     "Renntempo der Langdistanz in drei Blöcken. Verpflegung wie im Rennen."),
    ("bike", "wettkampf", "Langdistanz-Tempo 2x60", "20min@60, 2x(60min@72[Renntempo], 10min@60), 10min@55",
     "Zwei Stunden Renntempo. Gleichmäßig fahren, Watt nicht hochtreiben."),
    ("bike", "wettkampf", "Renn-Simulation 4 h",
     "20min@60, 4x(45min@73[Renntempo und Rennverpflegung], 5min@62), 20min@55",
     "Die Generalprobe: Material, Position, Verpflegung und Pacing über vier Stunden."),
    ("bike", "wettkampf", "Steady State 90", "15min@60, 90min@73[gleichmäßig wie im Rennen], 10min@55",
     "90 Minuten am Stück im Renntempo der Langdistanz."),
    ("bike", "wettkampf", "Mitteldistanz-Tempo 3x20", "15min@60, 3x(20min@82, 5min@60), 10min@55",
     "Renntempo der Mitteldistanz in drei Blöcken."),
    ("bike", "wettkampf", "Olympisch-Tempo 4x10", "15min@60, 4x(10min@92, 5min@55), 10min@50",
     "Renntempo der Kurzdistanz: hart, aber über 40 km haltbar."),

    # ------------------------------------------------------------------ Laufen
    ("run", "regeneration", "Regenerationslauf", "30min@72",
     "30 Minuten sehr locker. Lieber zu langsam als zu schnell."),
    ("run", "regeneration", "Lockerer Trab", "5min@68, 30min@74, 5min@68",
     "Ruhiger Trab mit langsamem Ein- und Auslaufen."),
    ("run", "regeneration", "Erholung mit Steigerungen", "25min@74, 4x(15s@115[locker steigern], 45s@68), 5min@70",
     "Locker laufen, am Ende vier kurze, lockere Steigerungen für einen schnellen Schritt."),
    ("run", "regeneration", "Gehen und Laufen", "6x(4min@72, 1min@45[gehen])",
     "Wechsel aus Laufen und Gehen – ideal nach Rennen oder Verletzungspausen."),

    ("run", "grundlage", "Dauerlauf 45", "5min@76, 35min@83, 5min@76",
     "Der Standardlauf im GA1: locker genug, um sich zu unterhalten."),
    ("run", "grundlage", "Dauerlauf 60", "10min@76, 45min@84, 5min@76",
     "Eine Stunde gleichmäßig im Grundlagentempo."),
    ("run", "grundlage", "Langer Lauf 90", "10min@76, 75min@82, 5min@76",
     "Der lange Lauf: Ausdauer und Belastbarkeit von Sehnen und Knochen."),
    ("run", "grundlage", "Langer Lauf 2 h", "10min@76, 100min@81[alle 30 min trinken], 10min@76",
     "Zwei Stunden ruhig. Verpflegung und Laufschuhe für das Rennen testen."),
    ("run", "grundlage", "Dauerlauf mit Steigerungen", "10min@76, 30min@84, 6x(20s@118[Steigerung], 1:40@76), 5min@75",
     "Grundlage mit sechs Steigerungen am Ende – hält den Schritt spritzig."),
    ("run", "grundlage", "Hügeliger Dauerlauf", "10min@76, 40min@83[welliges Profil, Puls gleichmäßig], 10min@76",
     "Durch welliges Gelände, Tempo an den Puls anpassen, nicht an die Uhr."),

    ("run", "tempo", "Tempodauerlauf 3x10", "15min@78, 3x(10min@91, 3min@76), 10min@76",
     "Drei zügige Blöcke im Bereich des Marathontempos."),
    ("run", "tempo", "Marathontempo 2x20", "15min@78, 2x(20min@89, 4min@76), 10min@76",
     "Zwei lange Blöcke im Marathontempo – die Basis für den Lauf der Langdistanz."),
    ("run", "tempo", "Progressionslauf", "15min@78, 15min@83, 15min@87, 10min@92, 5min@76",
     "Jeder Abschnitt etwas schneller, der letzte im Tempobereich."),
    ("run", "tempo", "Tempodauerlauf 30", "15min@78, 30min@92, 10min@76",
     "30 Minuten zügig am Stück. Konzentriert, aber nicht an der Grenze."),
    ("run", "tempo", "Fahrtspiel",
     "12min@78, 2min@93, 2min@78, 3min@91, 2min@78, 4min@90, 2min@78, 3min@91, 2min@78, 2min@93, 2min@78, "
     "1min@100, 8min@76",
     "Tempowechsel nach Gefühl und Gelände, von 1 bis 4 Minuten."),
    ("run", "tempo", "Tempo-Sandwich", "15min@78, 15min@90, 10min@80, 15min@90, 10min@76",
     "Zwei Tempoblöcke mit einem lockeren Abschnitt dazwischen."),
    ("run", "tempo", "Langer Lauf mit Endbeschleunigung", "10min@76, 60min@83, 15min@90[im Tempo nach Hause], 5min@75",
     "Langer Lauf, die letzte Viertelstunde zügig – lernen, müde schnell zu laufen."),

    ("run", "schwelle", "Schwelle 3x8", f"{R_WU}, 3x(8min@99, 2min@75), 10min@76",
     "Drei Blöcke an der Schwelle mit kurzen Trabpausen."),
    ("run", "schwelle", "Schwelle 2x15", f"{R_WU}, 2x(15min@97, 3min@75), 10min@76",
     "Zwei lange Blöcke knapp unter der Schwelle."),
    ("run", "schwelle", "Cruise-Intervalle 6x1 km", f"{R_WU}, 6x(1km@100, 1:30@72), 10min@76",
     "Sechs Kilometer an der Schwelle mit kurzen Pausen."),
    ("run", "schwelle", "Schwelle 4x2 km", f"{R_WU}, 4x(2km@98, 2min@72), 10min@76",
     "Längere Abschnitte knapp unter der Schwelle."),
    ("run", "schwelle", "Schwellenlauf 20", f"{R_WU}, 20min@97, 10min@76",
     "20 Minuten am Stück, so schnell, wie du eine Stunde laufen könntest – etwas langsamer."),
    ("run", "schwelle", "Unterschwelle 5x6", f"{R_WU}, 5x(6min@95, 1min@72), 10min@76",
     "Knapp unter der Schwelle mit sehr kurzen Pausen – viel Schwellenumfang bei wenig Ermüdung."),
    ("run", "schwelle", "Unterschwelle 10x3", f"{R_WU}, 10x(3min@96, 1min@72), 10min@76",
     "Zehn kurze Blöcke unter der Schwelle. Die Kunst ist, nicht zu schnell zu werden."),

    ("run", "vo2max", "5x1000 m", f"{R_WU}, 5x(1km@105[5-km-Renntempo], 2:30@72), 10min@76",
     "Der Klassiker für die VO2max: fünf Kilometer im 5-km-Renntempo."),
    ("run", "vo2max", "6x800 m", f"{R_WU}, 6x(800m@106, 2min@72), 10min@76",
     "Etwas kürzer und schneller als die 1000er."),
    ("run", "vo2max", "VO2max 5x3 min", f"{R_WU}, 5x(3min@106, 2min@72), 10min@76",
     "Nach Zeit statt Strecke – praktisch auf Waldwegen."),
    ("run", "vo2max", "30/30", f"{R_WU}, 2x(10x(30s@110, 30s@75), 4min@72), 10min@76",
     "30 Sekunden schnell, 30 Sekunden locker. Viel Zeit nahe der VO2max ohne lange Blöcke."),
    ("run", "vo2max", "Pyramide 400–1200 m",
     f"{R_WU}, 400m@108, 1:30@72, 800m@106, 2min@72, 1200m@104, 2:30@72, 800m@106, 2min@72, 400m@108, 10min@76",
     "400–800–1200–800–400 m. Das Tempo passt sich der Länge an."),
    ("run", "vo2max", "12x400 m", f"{R_WU}, 12x(400m@108, 1min@70), 10min@76",
     "Zwölf Bahnrunden zügig mit kurzer Trabpause."),

    ("run", "anaerob", "8x200 m", f"{R_WU}, 8x(200m@118, 200m@65[Trabpause]), 10min@76",
     "Schnelle 200er mit Trabpause über die gleiche Strecke."),
    ("run", "anaerob", "6x300 m", f"{R_WU}, 6x(300m@116, 2min@68), 10min@76",
     "Sehr zügig, mit vollständiger Erholung. Locker in Schultern und Armen bleiben."),
    ("run", "anaerob", "10x45 s", f"{R_WU}, 10x(45s@115, 1:45@68), 10min@76",
     "Zehn kurze, harte Abschnitte nach Zeit."),
    ("run", "anaerob", "4x500 m", f"{R_WU}, 4x(500m@113, 3min@68), 10min@76",
     "Längere anaerobe Abschnitte: Laktat aushalten und das Tempo halten."),
    ("run", "anaerob", "Laktat-Leiter",
     f"{R_WU}, 2x(200m@120, 1:30@65, 300m@117, 2min@65, 400m@114, 3min@65), 10min@76",
     "200–300–400 m in zwei Durchgängen, jedes Mal etwas länger."),

    ("run", "sprint", "Steigerungen 8x100 m", "20min@78, 8x(100m@125[bis fast maximal steigern], 100m@65), 5min@75",
     "Acht Steigerungen über 100 Meter. Lockerer Oberkörper, schneller Schritt."),
    ("run", "sprint", "Fliegende 60 m", f"{R_WU}, 6x(60m@140[fliegend, 20 m Anlauf], 2min@60), 10min@76",
     "Mit Anlauf in den Sprint – maximale Geschwindigkeit ohne harte Startphase."),
    ("run", "sprint", "Bergsprints 8x10 s", "15min@78, 8x(10s@140[steiler Hügel, maximal], 2min@50[gehend zurück]), 10min@76",
     "Kurze Sprints am steilen Hügel. Kraft und Schnelligkeit bei geringem Verletzungsrisiko."),
    ("run", "sprint", "Steigerungen nach dem Dauerlauf", "30min@82, 6x(20s@125, 1:10@70), 5min@75",
     "Ein lockerer Dauerlauf mit sechs Steigerungen am Ende."),

    ("run", "kraft", "Bergläufe 8x60 s", "15min@78, 8x(1min@103[bergauf, 5–8 % Steigung], 2min@68[locker bergab]), 10min@76",
     "Kraftausdauer am Hügel. Aufrecht bleiben, Arme aktiv einsetzen."),
    ("run", "kraft", "Lange Berge 5x3", "15min@78, 5x(3min@98[bergauf], 3min@68[bergab traben]), 10min@76",
     "Drei Minuten bergauf: Schwellenreiz mit weniger Stoßbelastung."),
    ("run", "kraft", "Hügel-Fahrtspiel", "15min@78, 10x(1:30@95[Hügel hoch], 2min@75), 10min@76",
     "Welliges Gelände nutzen: jeder Hügel zügig hoch, oben locker weiter."),
    ("run", "kraft", "Rampensprünge 8x30 s", "15min@78, 8x(30s@110[steile Rampe, hohes Knie], 1:30@60), 10min@76",
     "Kurz und kräftig an einer steilen Rampe. Schult Abdruck und Kniehub."),

    ("run", "technik", "Lauf-ABC & Steigerungen",
     "15min@78, 10min@55[Lauf-ABC: Skippings, Anfersen, Hopserlauf], 6x(80m@120[Steigerung], 1min@65), 8min@76",
     "Lauf-ABC für Koordination, danach Steigerungen, um das Gelernte umzusetzen."),
    ("run", "technik", "Schrittfrequenz-Lauf", "10min@78, 6x(3min@84[Schrittfrequenz +5 %], 2min@80[normal]), 5min@76",
     "Gleiches Tempo, kürzere und schnellere Schritte. Hilft gegen Überschreiten."),
    ("run", "technik", "Koordination kurz", "10min@76, 8x(30s@95[kurze, schnelle Schritte], 1:30@72), 9min@75",
     "Kurze, schnelle Schritte mit lockeren Pausen."),
    ("run", "technik", "Lauf-ABC kompakt", "10min@76, 10min@55[ABC-Übungen, je 2 × 20 m], 4x(20s@115, 40s@65), 6min@75",
     "Eine halbe Stunde Technik – passt auch an einen vollen Tag."),

    ("run", "wettkampf", "Langdistanz-Lauftempo 3x15", "15min@76, 3x(15min@82[Renntempo Langdistanz], 3min@76), 10min@76",
     "Das Lauftempo der Langdistanz verinnerlichen – es fühlt sich frisch fast zu langsam an."),
    ("run", "wettkampf", "Langer Lauf mit Rennblöcken", "15min@78, 3x(20min@82[Renntempo], 10min@78), 10min@76",
     "Ein langer Lauf mit einer Stunde im Renntempo."),
    ("run", "wettkampf", "Verpflegung üben", "10min@78, 4x(15min@82[alle 20 min Gel oder Getränk], 5min@78)",
     "Renntempo und Verpflegung im Laufen – wie an den Verpflegungsstellen."),
    ("run", "wettkampf", "Mitteldistanz-Tempo 2x20", "15min@78, 2x(20min@90, 4min@76), 10min@76",
     "Renntempo des Halbmarathons in zwei Blöcken."),
    ("run", "wettkampf", "Olympisch 5x2 km", f"{R_WU}, 5x(2km@99, 2min@72), 10min@76",
     "Zehn Kilometer im Renntempo der Kurzdistanz, in Abschnitte geteilt."),

    # ------------------------------------------------------------------ Schwimmen
    ("swim", "regeneration", "Lockeres Schwimmen 1500",
     "300m@82, 4x(200m@84 r20), 300m@80[Rücken und Brust gemischt], 100m@78",
     "Ganz locker, mit Lagenwechsel. Gut am Tag nach einer harten Einheit."),
    ("swim", "regeneration", "Erholung mit Technik",
     "400m@82, 8x(50m@80[Drills: Abschlag, Faustschwimmen] r15), 6x(100m@84 r20), 400m@83[Pull Buoy]",
     "Locker schwimmen und dabei an der Technik feilen."),
    ("swim", "regeneration", "Pull locker 2000", "300m@82, 4x(300m@84[Pull Buoy] r30), 300m@83, 200m@80",
     "Mit Pull Buoy entspannt Strecke machen – die Beine erholen sich."),

    ("swim", "grundlage", "Grundlage 10x200", f"{S_WU}, 10x(200m@90 r20), {S_CD}",
     "Zehn gleichmäßige 200er: die Basis für Schwimmausdauer."),
    ("swim", "grundlage", "Grundlage 5x400", f"{S_WU}, 5x(400m@90 r30), {S_CD}",
     "Längere Abschnitte, gleichmäßiges Tempo."),
    ("swim", "grundlage", "Lange Strecke 2000", f"{S_WU}, 2000m@89[am Stück, gleichmäßig], 100m@80",
     "Zwei Kilometer am Stück – Rhythmus finden und halten."),
    ("swim", "grundlage", "Grundlagen-Pyramide",
     f"{S_WU}, 100m@91 r15, 200m@90 r20, 300m@90 r20, 400m@89 r30, 300m@90 r20, 200m@90 r20, 100m@91 r15, {S_CD}",
     "100 bis 400 Meter und zurück, alles im Grundlagentempo."),
    ("swim", "grundlage", "Paddles 8x250", f"{S_WU}, 8x(250m@90[mit Paddles] r20), {S_CD}",
     "Grundlage mit Paddles für mehr Zuggefühl."),
    ("swim", "grundlage", "Langdistanz-Ausdauer 3x800", f"{S_WU}, 3x(800m@89 r45), {S_CD}",
     "Drei lange Abschnitte – die Grundlage für 3,8 km im Rennen."),

    ("swim", "tempo", "Tempo 6x300", f"{S_WU}, 4x(50m@88[Technik] r15), 6x(300m@95 r25), {S_CD}",
     "Zügige 300er knapp unter dem CSS-Tempo."),
    ("swim", "tempo", "Tempo 3x600", f"{S_WU}, 3x(600m@95 r40), {S_CD}",
     "Lange Tempoabschnitte mit Fokus auf gleichmäßiges Pacing."),
    ("swim", "tempo", "Tempo-Leiter",
     f"{S_WU}, 4x(50m@88[Technik] r15), 100m@96 r20, 200m@96 r20, 300m@95 r20, 400m@95 r30, 4x(100m@90 r15), {S_CD}",
     "100–200–300–400 m zügig, danach locker ausklingen lassen."),
    ("swim", "tempo", "Tempo 1500 am Stück", f"{S_WU}, 1500m@94, {S_CD}",
     "1500 Meter zügig am Stück – wie eine Kurzdistanz ohne Startgerangel."),

    ("swim", "schwelle", "CSS 10x100", f"{S_WU2}, 10x(100m@100 r15), {S_CD}",
     "Der Klassiker für die Schwelle: zehn 100er im CSS-Tempo."),
    ("swim", "schwelle", "CSS 8x200", f"{S_WU2}, 8x(200m@100 r20), {S_CD}",
     "Längere Abschnitte im CSS-Tempo."),
    ("swim", "schwelle", "CSS 4x400", f"{S_WU2}, 4x(400m@99 r30), {S_CD}",
     "Vier 400er knapp unter CSS – Ausdauer an der Schwelle."),
    ("swim", "schwelle", "CSS 20x100", f"{S_WU2}, 20x(100m@101 r10), {S_CD}",
     "Zwanzig 100er mit nur 10 Sekunden Pause. Nicht zu schnell anfangen."),
    ("swim", "schwelle", "CSS-Pyramide",
     f"{S_WU2}, 100m@101 r10, 200m@100 r15, 300m@100 r20, 400m@99 r25, 300m@100 r20, 200m@100 r15, 100m@101 r10, {S_CD}",
     "100 bis 400 Meter und zurück, alles im CSS-Tempo."),
    ("swim", "schwelle", "Gebrochene 1500", f"{S_WU2}, 3x(5x(100m@100 r10), r60), {S_CD}",
     "1500 Meter in 100er-Abschnitten mit kurzen Pausen."),

    ("swim", "vo2max", "VO2 12x100", f"{S_WU2}, 12x(100m@105 r30), {S_CD}",
     "100er schneller als CSS mit genug Pause, um das Tempo zu halten."),
    ("swim", "vo2max", "VO2 8x150", f"{S_WU2}, 8x(150m@104 r30), {S_CD}",
     "150er etwas über dem CSS-Tempo."),
    ("swim", "vo2max", "VO2 6x200", f"{S_WU2}, 6x(200m@103 r40), {S_CD}",
     "Längere VO2-Abschnitte mit großzügiger Pause."),
    ("swim", "vo2max", "VO2 16x50", f"{S_WU2}, 16x(50m@107 r20), 300m@85, {S_CD}",
     "Viele schnelle 50er mit kurzer Pause."),
    ("swim", "vo2max", "Absteigende 100er",
     f"{S_WU2}, 3x(100m@100 r15, 100m@103 r15, 100m@106 r30, 100m@85 r15), {S_CD}",
     "Drei Durchgänge, jeder 100er schneller als der vorherige."),

    ("swim", "anaerob", "Laktat 8x50", f"{S_WU2}, 8x(50m@112[hart] r45), 300m@82, {S_CD}",
     "Acht harte 50er mit langen Pausen."),
    ("swim", "anaerob", "Laktat 6x75", f"{S_WU2}, 6x(75m@110 r60), 300m@82, {S_CD}",
     "75er hart, eine Minute Pause."),
    ("swim", "anaerob", "Gebrochene 100er", f"{S_WU2}, 6x(4x(25m@115 r10), r60), 300m@82, {S_CD}",
     "100 Meter in vier harte 25er geteilt, sechs Durchgänge."),
    ("swim", "anaerob", "Laktat-Pyramide 25–75", f"{S_WU2}, 3x(25m@116 r20, 50m@113 r30, 75m@110 r45), 300m@82, {S_CD}",
     "25–50–75 m hart, dreimal."),

    ("swim", "sprint", "Sprint 12x25", f"{S_WU2}, 12x(25m@125[maximal] r40), 400m@84, {S_CD}",
     "Kurze Maximalsprints mit voller Erholung."),
    ("swim", "sprint", "Startsprints", f"{S_WU2}, 10x(15m@130[explosiv aus der Wende], 35m@80 r30), {S_CD}",
     "Explosiv aus der Wende, dann locker ausschwimmen."),
    ("swim", "sprint", "Speed-Wellen", f"{S_WU2}, 6x(25m@122[schnell], 25m@85[locker] r30), 300m@84, {S_CD}",
     "25 Meter schnell, 25 Meter locker – Tempowechsel wie beim Rennstart."),
    ("swim", "sprint", "Sprint 8x50 steigernd", f"{S_WU2}, 8x(50m@120[auf 50 m steigern] r45), 300m@84, {S_CD}",
     "50er, die bis zum Sprint gesteigert werden."),

    ("swim", "kraft", "Paddles & Pull", f"{S_WU}, 6x(200m@92[Paddles und Pull Buoy] r20), 4x(100m@96[Paddles] r15), {S_CD}",
     "Kraft im Zug mit Paddles. Schultern achtsam einsetzen."),
    ("swim", "kraft", "Zugkraft mit Band",
     f"{S_WU}, 8x(50m@88[Band um die Knöchel] r30), 6x(100m@95[Paddles] r20), 400m@85[Pull Buoy], {S_CD}",
     "Ohne Beinschlag: Der Armzug muss den Körper allein tragen."),
    ("swim", "kraft", "Kraftausdauer 4x300", f"{S_WU}, 4x(300m@95[Paddles] r30), 4x(50m@100[ohne Hilfsmittel] r20), {S_CD}",
     "300er mit Paddles, danach das Zuggefühl ohne Hilfsmittel übertragen."),

    ("swim", "technik", "Technik 1500",
     "300m@84, 8x(50m@80[Abschlagschwimmen] r15), 8x(50m@80[Faustschwimmen] r15), 4x(100m@88[Fokus Wasserlage] r20)",
     "Zwei klassische Drills, danach die Technik in ganze Lagen übertragen."),
    ("swim", "technik", "Atmung & Lage",
     f"{S_WU}, 6x(50m@80[3er-Atmung, ruhig ausatmen] r15), 6x(50m@80[Seitlage-Beinschlag, 6 Kicks pro Zug] r20), "
     f"6x(100m@88[gleichmäßiger Rhythmus] r20), {S_CD}",
     "Ruhige Atmung und stabile Wasserlage – die Basis für entspanntes Kraulen."),
    ("swim", "technik", "Catch-up & Zugphase",
     f"{S_WU}, 8x(50m@80[Catch-up] r15), 8x(50m@82[Skullen vorne] r20), 4x(150m@88 r20), {S_CD}",
     "Gefühl für den Wasserfassen-Moment am Anfang des Zugs."),
    ("swim", "technik", "Freiwasser-Technik",
     f"{S_WU}, 6x(100m@90[alle 6 Züge nach vorn orientieren] r20), "
     f"4x(150m@92[Wasserschatten: eng hinter einem Partner] r20), 4x(50m@105[Kopf über Wasser] r30), {S_CD}",
     "Orientieren, Wasserschatten und Kopf-hoch-Kraul – im Becken fürs Freiwasser üben."),

    ("swim", "wettkampf", "Langdistanz 3800", "400m@84, 3x(1000m@93[Renntempo Langdistanz] r30), 400m@84",
     "Die volle Distanz im Training, zum größten Teil im Renntempo."),
    ("swim", "wettkampf", "Renntempo 4x500", f"{S_WU}, 4x(500m@96[die ersten 100 m schneller, dann Renntempo] r30), {S_CD}",
     "Schneller Start, dann ins Renntempo finden – wie nach dem Startschuss."),
    ("swim", "wettkampf", "Startsimulation", f"{S_WU}, 4x(50m@115[Startsprint], 200m@95[ins Renntempo finden] r30), 300m@85, {S_CD}",
     "Hart anschwimmen und danach den Rhythmus finden."),
    ("swim", "wettkampf", "Neo-Probe im Freiwasser", "300m@84, 2400m@93[im Neo, alle 6–8 Züge orientieren], 300m@82",
     "Neoprenanzug, Orientierung und Renntempo im See."),

    # ------------------------------------------------------------------ Koppel
    ("brick", "grundlage", "Koppel kurz", "bike: 10min@60, 45min@74, 5min@65 | run: 15min@84",
     "Eine Stunde Rad, danach eine Viertelstunde laufen – gewöhnt die Beine an den Wechsel."),
    ("brick", "grundlage", "Lange Ausfahrt mit Koppellauf",
     "bike: 15min@60, 165min@69[Rennverpflegung testen] | run: 20min@82, 10min@78",
     "Drei Stunden Rad mit kurzem Koppellauf. Verpflegung wie im Rennen."),
    ("brick", "tempo", "Koppel-Wechsel 3x",
     "bike: 15min@60, 20min@85 | run: 10min@90 | bike: 20min@85 | run: 10min@90 | bike: 20min@85 | run: 10min@90",
     "Dreimal Rad und Lauf im Wechsel. Übt schnelle Wechsel und den Laufrhythmus nach dem Rad."),
    ("brick", "schwelle", "Koppel Schwelle", "bike: 15min@60, 3x(8min@100, 4min@55), 5min@60 | run: 10min@96, 10min@78",
     "Schwelle auf dem Rad, danach zehn Minuten zügig laufen."),
    ("brick", "wettkampf", "Koppel Langdistanz",
     "bike: 15min@60, 3x(30min@74[Renntempo], 5min@62) | run: 30min@82[Renntempo Langdistanz]",
     "Renntempo auf dem Rad und direkt danach im Laufen – das Gefühl für die zweite Hälfte des Rennens."),
    ("brick", "wettkampf", "Mitteldistanz-Simulation", "bike: 15min@60, 2x(40min@82, 5min@60) | run: 45min@90",
     "Renntempo der Mitteldistanz auf Rad und Laufstrecke."),
]

WORKOUTS: list[Workout] = _build(_ROWS)
BY_ID: dict[str, Workout] = {w.id: w for w in WORKOUTS}


def workouts_for(sport: str | None = None, categories: list[str] | None = None,
                 max_minutes: float | None = None, th: Thresholds | None = None) -> list[Workout]:
    th = th or Thresholds()
    out = []
    for w in WORKOUTS:
        if sport and w.sport != sport:
            continue
        if categories is not None and w.category not in categories:
            continue
        if max_minutes and w.summary(th).minutes > max_minutes + 0.5:
            continue
        out.append(w)
    order = list(CATEGORIES)
    return sorted(out, key=lambda w: (order.index(w.category), w.summary(th).seconds))


def categories_for(sport: str) -> list[str]:
    present = {w.category for w in WORKOUTS if w.sport == sport}
    return [c for c in CATEGORIES if c in present]


def intensity_label(step: Step) -> str:
    if step.is_rest:
        return ""
    return (f"{step.low:g} %" if step.low == step.high else f"{step.low:g}–{step.high:g} %").replace(".", ",")
