"""HTML-Bausteine (für ``st.html``): Intensitätsprofile, Galerie-Karten, Seitenköpfe.

``st.html`` lässt nur HTML ohne SVG und JavaScript zu. Alles hier besteht deshalb aus
einfachen ``div``/``span``-Elementen mit Inline-Größen; die Optik kommt aus ``STYLE``.
Neutrale Farben leiten sich von der Textfarbe des Themes ab (``currentColor``) und
passen so automatisch zu hell und dunkel.
"""
from __future__ import annotations

from datetime import date, timedelta
from html import escape

import pandas as pd

from triathlon import library as lib
from triathlon.units import WEEKDAYS, fmt_duration

# Zonenfarben, geprüft auf Farbsehschwäche und Kontrast (dataviz-Validator) –
# getrennt für helle und dunkle Fläche. Höhe der Blöcke kodiert die Intensität zusätzlich.
ZONE_COLORS = {
    "light": {1: "#40B1B7", 2: "#3072C1", 3: "#259F56", 4: "#D3AD1B", 5: "#E06D00", 6: "#BF2374", 7: "#7444B4"},
    "dark": {1: "#18A7A1", 2: "#306DC4", 3: "#008935", 4: "#A89620", 5: "#CD5800", 6: "#BF2A82", 7: "#8968D4"},
}
ACCENT = {"light": "#2D5A47", "dark": "#8CC2A8"}
STATUS = {"green": ("#2E8B57", "Grün"), "yellow": ("#C99A06", "Gelb"), "red": ("#C0392B", "Rot")}

SERIF = '"Newsreader", "Iowan Old Style", Georgia, serif'

STYLE = """
:root {
  --tri-serif: %(serif)s;
  --tri-muted: color-mix(in srgb, currentColor 70%%, transparent);
  --tri-faint: color-mix(in srgb, currentColor 45%%, transparent);
  --tri-line: color-mix(in srgb, currentColor 13%%, transparent);
  --tri-line-strong: color-mix(in srgb, currentColor 30%%, transparent);
  --tri-tint: color-mix(in srgb, currentColor 3%%, transparent);
  --tri-z0: color-mix(in srgb, currentColor 22%%, transparent);
}

/* Grundgerüst */
[data-testid="stMainBlockContainer"] { max-width: 1240px; }
[data-testid="stMetricValue"] {
  font-family: var(--tri-serif); font-weight: 500; letter-spacing: -0.01em;
  font-variant-numeric: lining-nums tabular-nums;
}
[data-testid="stMetricLabel"] p { font-size: 0.82rem; }

/* Seitenkopf */
.tri-head { margin: 0 0 1.4rem; }
.tri-head h1 {
  font-family: var(--tri-serif); font-weight: 500; font-size: clamp(2.2rem, 2.2vw + 1.4rem, 3.1rem);
  line-height: 1.04; letter-spacing: -0.02em; margin: 0 0 0.45rem; padding: 0;
}
.tri-head p { margin: 0; max-width: 62ch; font-size: 1.04rem; line-height: 1.5; color: var(--tri-muted); }

/* Zonen */
.tri-z0 { background: var(--tri-z0); }
.tri-z1 { background: var(--tri-zc1); } .tri-z2 { background: var(--tri-zc2); }
.tri-z3 { background: var(--tri-zc3); } .tri-z4 { background: var(--tri-zc4); }
.tri-z5 { background: var(--tri-zc5); } .tri-z6 { background: var(--tri-zc6); }
.tri-z7 { background: var(--tri-zc7); } .tri-zs { background: var(--tri-z0); }

.tri-legend { display: flex; flex-wrap: wrap; gap: 0.35rem 1.1rem; font-size: 0.8rem; color: var(--tri-muted);
  margin: 0.2rem 0 0.4rem; }
.tri-legend span { display: inline-flex; align-items: center; gap: 0.4rem; }
.tri-legend i { width: 0.7rem; height: 0.7rem; border-radius: 2px; display: inline-block; }

/* Intensitätsprofil */
.tri-prof { position: relative; height: 72px; border-bottom: 1px solid var(--tri-line-strong); }
.tri-prof__bars { display: flex; align-items: flex-end; height: 100%%; }
.tri-prof__bars > span { flex-basis: 0; border-radius: 2px 2px 0 0; }
.tri-prof__seg { display: flex; align-items: flex-end; height: 100%%; flex-basis: 0; }
.tri-prof__switch { align-self: stretch; width: 0; border-left: 1px dashed var(--tri-line-strong); }
.tri-prof__line { position: absolute; left: 0; right: 0; border-top: 1px dashed var(--tri-line-strong);
  pointer-events: none; }

/* Galerie */
.tri-section { margin: 2.2rem 0 0; }
.tri-section:first-child { margin-top: 0.6rem; }
.tri-section__head { display: flex; align-items: baseline; gap: 0.8rem; flex-wrap: wrap; margin-bottom: 0.2rem; }
.tri-section h3 { font-family: var(--tri-serif); font-weight: 500; font-size: 1.7rem; letter-spacing: -0.01em;
  margin: 0; padding: 0; line-height: 1.15; }
.tri-section__count { font-size: 0.85rem; color: var(--tri-faint); font-variant-numeric: tabular-nums; }
.tri-section > p { margin: 0 0 0.9rem; max-width: 70ch; color: var(--tri-muted); font-size: 0.93rem; line-height: 1.5; }
.tri-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(265px, 1fr)); gap: 14px; }

.tri-card { border: 1px solid var(--tri-line); border-radius: 10px; background: var(--tri-tint);
  display: flex; flex-direction: column; min-width: 0; }
.tri-card__prof { padding: 14px 14px 0; }
.tri-card__body { padding: 10px 14px 12px; display: flex; flex-direction: column; gap: 0.35rem; flex: 1; }
.tri-card__top { display: flex; justify-content: space-between; align-items: baseline; gap: 0.6rem; }
.tri-card__title { font-size: 1rem; font-weight: 600; line-height: 1.3; margin: 0; padding: 0; }
.tri-card__dur { font-family: var(--tri-serif); font-size: 1.3rem; white-space: nowrap;
  font-variant-numeric: lining-nums tabular-nums; }
.tri-card__meta { display: flex; flex-wrap: wrap; gap: 0.25rem 0.9rem; font-size: 0.8rem; color: var(--tri-muted);
  font-variant-numeric: tabular-nums; margin: 0; }
.tri-card__meta b { font-weight: 600; color: inherit; }
.tri-card__desc { font-size: 0.86rem; line-height: 1.45; color: var(--tri-muted); margin: 0; }
.tri-card details { margin-top: auto; padding-top: 0.3rem; }
.tri-card summary { cursor: pointer; font-size: 0.82rem; font-weight: 600; padding: 0.2rem 0; }
.tri-card summary:focus-visible { outline: 2px solid currentColor; outline-offset: 2px; border-radius: 3px; }

.tri-steps, .tri-steps ol { list-style: none; margin: 0; padding: 0; }
.tri-steps li { margin: 0; }
.tri-steps { margin-top: 0.35rem; font-size: 0.8rem; font-variant-numeric: tabular-nums; }
.tri-steps li.tri-st { display: grid; grid-template-columns: 4.4rem 0.6rem 1fr auto; gap: 0 0.5rem;
  align-items: baseline; padding: 0.22rem 0; border-bottom: 1px solid var(--tri-line); }
.tri-st i { width: 0.6rem; height: 0.6rem; border-radius: 2px; display: inline-block; align-self: center; }
.tri-st b { font-weight: 600; }
.tri-st em { font-style: normal; color: var(--tri-faint); }
.tri-st small { grid-column: 3 / -1; color: var(--tri-muted); font-size: 0.76rem; line-height: 1.35; }
.tri-rep { padding: 0.3rem 0 0.1rem; }
.tri-rep > span { font-weight: 600; font-size: 0.8rem; }
.tri-rep > ol { margin: 0.15rem 0 0 0.3rem !important; padding-left: 0.6rem !important;
  border-left: 2px solid var(--tri-line-strong); }
.tri-seglabel { font-weight: 600; margin: 0.5rem 0 0.1rem; font-size: 0.8rem; }

/* Letzte Tage (Übersicht) */
.tri-days { display: grid; grid-template-columns: repeat(14, minmax(0, 1fr)); gap: 6px; }
.tri-day__bars { height: 74px; display: flex; align-items: flex-end; gap: 2px;
  border-bottom: 1px solid var(--tri-line-strong); }
.tri-day__bars > span { flex-basis: 0; border-radius: 2px 2px 0 0; min-width: 2px; }
.tri-day__rest { width: 100%%; height: 2px; background: var(--tri-line); }
.tri-day__label { font-size: 0.72rem; color: var(--tri-muted); text-align: center; margin-top: 0.3rem;
  line-height: 1.2; font-variant-numeric: tabular-nums; }
.tri-day--today .tri-day__label { color: inherit; font-weight: 600; }
.tri-days__note { font-size: 0.8rem; color: var(--tri-muted); margin: 0.5rem 0 0; }

/* Phasen bis zum Wettkampf */
.tri-phases { display: flex; gap: 3px; margin: 0.4rem 0 0.2rem; }
.tri-phase { flex-basis: 0; min-width: 0; padding: 0.55rem 0.6rem; border-radius: 6px; background: var(--tri-tint);
  border: 1px solid var(--tri-line); }
.tri-phase b { display: block; font-size: 0.85rem; font-weight: 600; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; }
.tri-phase span { font-size: 0.74rem; color: var(--tri-muted); white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; display: block; font-variant-numeric: tabular-nums; }
.tri-phase--now { border-color: var(--tri-accent); box-shadow: inset 0 0 0 1px var(--tri-accent); }

/* Ampel */
.tri-status { display: flex; align-items: center; gap: 0.6rem; margin: 0 0 0.3rem; }
.tri-status i { width: 0.85rem; height: 0.85rem; border-radius: 50%%; flex: none; }
.tri-status h3 { font-family: var(--tri-serif); font-weight: 500; font-size: 1.55rem; margin: 0; padding: 0;
  line-height: 1.2; }
.tri-status + p { margin: 0 0 0.2rem; color: var(--tri-muted); font-size: 0.93rem; }

@media (max-width: 640px) {
  .tri-days { gap: 3px; }
  .tri-day__label { font-size: 0.64rem; }
  .tri-phases { flex-direction: column; }
  .tri-phase { flex: none !important; }
}
@media (prefers-reduced-motion: reduce) { * { scroll-behavior: auto !important; } }
"""


def style_html(theme_type: str | None) -> str:
    mode = "dark" if theme_type == "dark" else "light"
    zones = "".join(f"--tri-zc{z}: {c};" for z, c in ZONE_COLORS[mode].items())
    css = STYLE % {"serif": SERIF}
    return f"<style>:root {{ {zones} --tri-accent: {ACCENT[mode]}; }}\n{css}</style>"


def page_header(title: str, lead: str | None = None) -> str:
    lead_html = f"<p>{escape(lead)}</p>" if lead else ""
    return f'<header class="tri-head"><h1>{escape(title)}</h1>{lead_html}</header>'


def zone_legend() -> str:
    items = "".join(f'<span><i class="tri-z{z}"></i>{escape(lib.ZONE_NAMES[z])}</span>' for z in range(1, 8))
    return f'<div class="tri-legend" aria-label="Farblegende der Intensitätszonen">{items}</div>'


# --------------------------------------------------------------------------- Workout-Profil

def _height(sport: str, pct: float) -> float:
    if pct <= 0:
        return 5.0
    return max(min(pct / lib.PROFILE_SCALE[sport] * 100, 100.0), 8.0)


def _block_title(block: lib.Block, th: lib.Thresholds) -> str:
    step = block.step
    parts = [lib.fmt_amount(step) if step.meters is None else f"{lib.fmt_amount(step)} (≈ {fmt_duration(block.seconds)})"]
    if step.is_rest:
        parts.append("Pause")
    else:
        parts += [f"{lib.intensity_label(step)} · {th.target(step)}", lib.ZONE_NAMES[block.zone]]
    if step.note and not step.is_rest:
        parts.append(step.note)
    return " · ".join(parts)


def profile_html(workout: lib.Workout, th: lib.Thresholds) -> str:
    """Blöcke mit Breite = Dauer, Höhe = Intensität, Farbe = Zone."""
    blocks = workout.blocks(th)
    n = len(blocks)
    gap = 2 if n <= 45 else 1 if n <= 100 else 0
    min_w = 2 if n <= 70 else 1
    segments: list[tuple[str, list[lib.Block]]] = []
    for b in blocks:
        if not segments or segments[-1][0] != b.step.sport:
            segments.append((b.step.sport, []))
        segments[-1][1].append(b)

    def spans(items: list[lib.Block]) -> str:
        out = []
        for b in items:
            out.append(
                f'<span class="tri-z{b.zone}" style="flex-grow:{b.seconds:.1f};min-width:{min_w}px;'
                f'height:{_height(b.step.sport, b.step.pct):.1f}%" title="{escape(_block_title(b, th))}"></span>'
            )
        return "".join(out)

    total = sum(b.seconds for b in blocks) or 1
    if len(segments) == 1:
        sport = segments[0][0]
        bars = f'<div class="tri-prof__bars" style="gap:{gap}px">{spans(blocks)}</div>'
        line = f'<div class="tri-prof__line" style="bottom:{100 / lib.PROFILE_SCALE[sport] * 100:.1f}%"></div>'
    else:
        inner = '<i class="tri-prof__switch" title="Wechsel"></i>'.join(
            f'<div class="tri-prof__seg" style="flex-grow:{sum(b.seconds for b in items) / total * 1000:.1f};'
            f'gap:{gap}px" title="{escape(lib.SPORTS[sport])}">{spans(items)}</div>'
            for sport, items in segments
        )
        bars = f'<div class="tri-prof__bars" style="gap:4px">{inner}</div>'
        line = ""
    summary = workout.summary(th)
    label = f"Intensitätsprofil {workout.name}, {summary.duration_text}"
    return f'<div class="tri-prof" role="img" aria-label="{escape(label)}">{line}{bars}</div>'


# --------------------------------------------------------------------------- Ablauf (Details)

def _step_li(step: lib.Step, th: lib.Thresholds) -> str:
    z = lib.zone(step.sport, step.pct)
    if step.is_rest:
        return (f'<li class="tri-st"><span>{escape(lib.fmt_amount(step))}</span><i class="tri-z0"></i>'
                f'<em>Pause</em><span></span></li>')
    note = f"<small>{escape(step.note)}</small>" if step.note else ""
    return (f'<li class="tri-st"><span>{escape(lib.fmt_amount(step))}</span><i class="tri-z{z}"></i>'
            f'<b>{escape(th.target(step))}</b><em>{escape(lib.intensity_label(step))}</em>{note}</li>')


def _items_html(items: list, th: lib.Thresholds) -> str:
    out = []
    for item in items:
        if isinstance(item, lib.Repeat):
            out.append(f'<li class="tri-rep"><span>{item.count} ×</span><ol>{_items_html(list(item.items), th)}</ol></li>')
        else:
            out.append(_step_li(item, th))
    return "".join(out)


def steps_html(workout: lib.Workout, th: lib.Thresholds) -> str:
    if len(workout.segments) == 1:
        return f'<ol class="tri-steps">{_items_html(workout.segments[0][1], th)}</ol>'
    parts = []
    for sport, items in workout.segments:
        parts.append(f'<div class="tri-seglabel">{escape(lib.SPORTS[sport])}</div>'
                     f'<ol class="tri-steps">{_items_html(items, th)}</ol>')
    return "".join(parts)


# --------------------------------------------------------------------------- Karte & Galerie

def card_html(workout: lib.Workout, th: lib.Thresholds, ctl: float) -> str:
    s = workout.summary(th)
    meta = [f"<span><b>{s.tss}</b> TSS</span>"]
    for sport in ("swim", "run"):
        dist = s.distance_text(sport)
        if dist:
            prefix = "" if workout.sport == sport else f"{lib.SPORTS[sport]} "
            meta.append(f"<span>{escape(prefix)}{'≈ ' if sport == 'run' else ''}{escape(dist)}</span>")
    meta.append(f"<span>{escape(lib.load_label(s.tss, ctl))} für dich</span>")
    return (
        f'<article class="tri-card" id="{escape(workout.id)}">'
        f'<div class="tri-card__prof">{profile_html(workout, th)}</div>'
        f'<div class="tri-card__body">'
        f'<div class="tri-card__top"><h4 class="tri-card__title">{escape(workout.name)}</h4>'
        f'<span class="tri-card__dur">{escape(s.duration_text)}</span></div>'
        f'<p class="tri-card__meta">{"".join(meta)}</p>'
        f'<p class="tri-card__desc">{escape(workout.description)}</p>'
        f'<details><summary>Ablauf und Zielwerte</summary>{steps_html(workout, th)}</details>'
        f'</div></article>'
    )


def gallery_html(workouts: list[lib.Workout], th: lib.Thresholds, ctl: float) -> str:
    sections = []
    for key, category in lib.CATEGORIES.items():
        items = [w for w in workouts if w.category == key]
        if not items:
            continue
        count = f"{len(items)} {'Einheit' if len(items) == 1 else 'Einheiten'}"
        cards = "".join(card_html(w, th, ctl) for w in items)
        sections.append(
            f'<section class="tri-section"><div class="tri-section__head"><h3>{escape(category.name)}</h3>'
            f'<span class="tri-section__count">{count}</span></div>'
            f'<p>{escape(category.purpose)}</p><div class="tri-grid">{cards}</div></section>'
        )
    return "".join(sections)


# --------------------------------------------------------------------------- Übersicht: letzte Tage

def recent_days_html(acts: pd.DataFrame, strength: pd.DataFrame, today: date, days: int = 14) -> str:
    """Pro Tag die Einheiten als Blöcke: Breite = Dauer, Höhe und Farbe = Intensität."""
    start = today - timedelta(days=days - 1)
    per_day: dict[date, list[tuple[str, float, int, float, str]]] = {start + timedelta(d): [] for d in range(days)}
    if not acts.empty:
        sel = acts[(acts["local_date"] >= pd.Timestamp(start)) & (acts["local_date"] <= pd.Timestamp(today))]
        for row in sel.sort_values("start_date").itertuples():
            group = row.group if row.group in lib.ZONE_UPPER else None
            intensity = getattr(row, "intensity", None)
            pct = float(intensity) * 100 if intensity is not None and pd.notna(intensity) else 0.0
            z = lib.zone(group, pct) if group and pct > 0 else 0
            height = _height(group, pct) if group and pct > 0 else 30.0
            tip = (f"{row.sport}: {row.name} · {fmt_duration(row.moving_time)}"
                   + (f" · IF {pct / 100:.2f}".replace(".", ",") if pct else "")
                   + f" · {row.tss:.0f} TSS")
            per_day[row.local_date.date()].append((f"tri-z{z}", float(row.moving_time or 0), z, height, tip))
    if not strength.empty:
        sel = strength[(strength["date"] >= pd.Timestamp(start)) & (strength["date"] <= pd.Timestamp(today))]
        for row in sel.itertuples():
            minutes = row.duration_min if pd.notna(row.duration_min) and row.duration_min else 60
            per_day[row.date.date()].append(("tri-zs", float(minutes) * 60, 0, 28.0,
                                             f"Kraft: {row.template or 'freies Training'} · {minutes:.0f} min"))

    longest = max((sum(i[1] for i in items) for items in per_day.values()), default=0) or 1
    cols = []
    for day, items in per_day.items():
        if items:
            total = sum(i[1] for i in items)
            width = max(total / longest * 100, 22)
            bars = "".join(
                f'<span class="{cls}" style="flex-grow:{secs:.0f};height:{height:.0f}%" title="{escape(tip)}"></span>'
                for cls, secs, _, height, tip in items
            )
            inner = f'<div style="display:flex;align-items:flex-end;gap:2px;height:100%;width:{width:.0f}%">{bars}</div>'
        else:
            inner = '<div class="tri-day__rest" title="Kein Training"></div>'
        today_cls = " tri-day--today" if day == today else ""
        label = "heute" if day == today else f"{WEEKDAYS[day.weekday()]}<br>{day.day}."
        cols.append(f'<div class="tri-day{today_cls}"><div class="tri-day__bars" style="justify-content:center">'
                    f'{inner}</div><div class="tri-day__label">{label}</div></div>')
    return f'<div class="tri-days" role="img" aria-label="Training der letzten {days} Tage">{"".join(cols)}</div>'


# --------------------------------------------------------------------------- Phasen & Ampel

def phases_html(blocks: list[dict], current_key: str) -> str:
    parts = []
    for b in blocks:
        days = (b["end"] - b["start"]).days + 1
        now = " tri-phase--now" if b["phase"].key == current_key else ""
        parts.append(
            f'<div class="tri-phase{now}" style="flex-grow:{max(days, 21)}" '
            f'title="{escape(b["phase"].name)}: {b["start"]:%d.%m.%Y} – {b["end"]:%d.%m.%Y}">'
            f'<b>{escape(b["phase"].name)}</b><span>{b["start"]:%d.%m.} – {b["end"]:%d.%m.%y}</span></div>'
        )
    return f'<div class="tri-phases">{"".join(parts)}</div>'


def status_html(level: str, headline: str, lead: str | None = None) -> str:
    color, label = STATUS[level]
    lead_html = f"<p>{escape(lead)}</p>" if lead else ""
    return (f'<div class="tri-status"><i style="background:{color}" aria-label="Ampel {label}"></i>'
            f'<h3>{escape(headline)}</h3></div>{lead_html}')
