"""Formatieren und Einlesen von Zeiten, Pace und Zahlen (deutsche Schreibweise)."""
from __future__ import annotations

import math

WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
WEEKDAYS_LONG = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


def fmt_pace(seconds: float | None) -> str:
    """Sekunden (pro km oder pro 100 m) als ``m:ss``."""
    if seconds is None or not math.isfinite(seconds) or seconds <= 0:
        return "–"
    total = int(round(seconds))
    return f"{total // 60}:{total % 60:02d}"


def parse_pace(text: str) -> float | None:
    """``"4:45"`` → 285 Sekunden. Leerer Text → ``None``."""
    text = (text or "").strip()
    if not text:
        return None
    parts = text.replace(".", ":").split(":")
    if len(parts) == 1:
        return float(parts[0]) * 60
    if len(parts) != 2:
        raise ValueError(f"Ungültiges Format: {text!r} (erwartet m:ss)")
    minutes, seconds = int(parts[0]), int(parts[1])
    if not 0 <= seconds < 60:
        raise ValueError(f"Ungültige Sekunden: {text!r}")
    return float(minutes * 60 + seconds)


def fmt_duration(seconds: float | None) -> str:
    """Sekunden als ``1:23 h`` bzw. ``45 min``."""
    if seconds is None or not math.isfinite(seconds):
        return "–"
    minutes = int(round(seconds / 60))
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60}:{minutes % 60:02d} h"


def fmt_num(value: float | None, digits: int = 0, unit: str = "") -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "–"
    text = f"{value:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} {unit}".strip()


def speed_to_pace(speed_ms: float | None, per_m: float = 1000) -> float | None:
    """m/s → Sekunden pro ``per_m`` Meter."""
    if not speed_ms or speed_ms <= 0:
        return None
    return per_m / speed_ms
