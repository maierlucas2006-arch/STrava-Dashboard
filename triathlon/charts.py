"""Diagramme (Plotly). Farben: feste Reihenfolge je Sportart, geprüft auf
Farbenblindheit (dataviz-Palette), mit eigenen Tönen für den Dark Mode."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from triathlon.load import GROUP_LABELS

LIGHT = {
    "swim": "#2a78d6", "bike": "#eb6834", "run": "#1baf7a", "strength": "#eda100", "other": "#898781",
    "muted": "#898781", "grid": "#e1e0d9", "band": "rgba(137,135,129,0.18)",
    "positive": "#2a78d6", "negative": "#e34948",
}
DARK = {
    "swim": "#3987e5", "bike": "#d95926", "run": "#199e70", "strength": "#c98500", "other": "#898781",
    "muted": "#898781", "grid": "#2c2c2a", "band": "rgba(195,194,183,0.14)",
    "positive": "#3987e5", "negative": "#e66767",
}
GROUP_ORDER = ["swim", "bike", "run", "strength", "other"]


def colors() -> dict:
    try:
        return DARK if st.context.theme.type == "dark" else LIGHT
    except Exception:  # außerhalb von Streamlit (Tests)
        return LIGHT


def _layout(fig: go.Figure, height: int = 320, yaxis_title: str | None = None) -> go.Figure:
    c = colors()
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=36, b=8),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title=None,
                    traceorder="normal"),
        hovermode="x unified",
        barcornerradius=4,
        bargap=0.25,
        separators=",.",
    )
    fig.update_xaxes(showgrid=False, tickformat="%d.%m.", hoverformat="%d.%m.%Y")
    fig.update_yaxes(gridcolor=c["grid"], gridwidth=1, zeroline=False, title=yaxis_title)
    return fig


def show(fig: go.Figure) -> None:
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def pmc_chart(pmc: pd.DataFrame, days: int = 120) -> go.Figure:
    c = colors()
    df = pmc.tail(days)
    fig = go.Figure()
    fig.add_scatter(x=df.index, y=df["ctl"].round(1), name="Fitness (CTL)", mode="lines",
                    line=dict(color=c["swim"], width=2))
    fig.add_scatter(x=df.index, y=df["atl"].round(1), name="Ermüdung (ATL)", mode="lines",
                    line=dict(color=c["bike"], width=2))
    return _layout(fig, 300, "TSS pro Tag")


def tsb_chart(pmc: pd.DataFrame, days: int = 120) -> go.Figure:
    c = colors()
    df = pmc.tail(days)
    bar_colors = [c["positive"] if v >= 0 else c["negative"] for v in df["tsb"]]
    fig = go.Figure(go.Bar(x=df.index, y=df["tsb"].round(1), marker_color=bar_colors, name="Form (TSB)"))
    fig.update_layout(showlegend=False, bargap=0.15)
    return _layout(fig, 200, "Form (TSB)")


def weekly_volume_chart(acts: pd.DataFrame, strength: pd.DataFrame, weeks: int = 12,
                        today: date | None = None) -> tuple[go.Figure, pd.DataFrame]:
    """Gestapelte Stunden pro Woche und Sportart. Gibt auch die Tabelle zurück."""
    c = colors()
    today = today or date.today()
    monday = today - timedelta(days=today.weekday())
    start = pd.Timestamp(monday - timedelta(weeks=weeks - 1))
    index = pd.date_range(start, periods=weeks, freq="7D")

    hours = pd.DataFrame(0.0, index=index, columns=GROUP_ORDER)
    if not acts.empty:
        a = acts[acts["local_date"] >= start].copy()
        a["week"] = a["local_date"] - pd.to_timedelta(a["local_date"].dt.weekday, unit="D")
        grouped = a.groupby(["week", "group"])["moving_time"].sum().unstack(fill_value=0) / 3600
        hours = hours.add(grouped.reindex(index=index, columns=GROUP_ORDER, fill_value=0), fill_value=0)
    if not strength.empty:
        s = strength[strength["date"] >= start].copy()
        if not acts.empty:  # Strava-Krafteinheiten nicht doppelt zählen
            strava_days = set(acts.loc[acts["group"] == "strength", "local_date"])
            s = s[~s["date"].isin(strava_days)]
        s["week"] = s["date"] - pd.to_timedelta(s["date"].dt.weekday, unit="D")
        own = s.groupby("week")["duration_min"].sum() / 60
        hours["strength"] = hours["strength"].add(own.reindex(index, fill_value=0), fill_value=0)

    fig = go.Figure()
    for group in GROUP_ORDER:
        if hours[group].sum() == 0:
            continue
        fig.add_bar(x=index, y=hours[group].round(2), name=GROUP_LABELS[group], marker_color=c[group],
                    marker_line=dict(width=0), hovertemplate="%{y:.1f} h")
    fig.update_layout(barmode="stack")
    fig = _layout(fig, 320, "Stunden")
    fig.update_xaxes(tickformat="KW %V", dtick=7 * 24 * 3600 * 1000, hoverformat="KW %V (ab %d.%m.)")
    table = hours.round(1).rename(columns=GROUP_LABELS)
    table.index = [f"KW {d.isocalendar().week} ({d:%d.%m.})" for d in index]
    return fig, table


def hrv_chart(wellness: pd.DataFrame, days: int = 90) -> go.Figure | None:
    c = colors()
    hrv = wellness["hrv"].dropna() if not wellness.empty else pd.Series(dtype=float)
    hrv = hrv[hrv > 0]
    if hrv.empty:
        return None
    full = hrv.asfreq("D")
    ln = np.log(full)
    mean = ln.rolling(60, min_periods=14).mean()
    sd = ln.rolling(60, min_periods=14).std()
    avg7 = np.exp(ln.rolling(7, min_periods=3).mean())
    start = full.index.max() - pd.Timedelta(days=days)
    sel = full.index >= start

    fig = go.Figure()
    upper = np.exp(mean + 0.5 * sd)[sel]
    lower = np.exp(mean - 0.5 * sd)[sel]
    fig.add_scatter(x=upper.index, y=upper.round(1), mode="lines", line=dict(width=0), showlegend=False,
                    hoverinfo="skip")
    fig.add_scatter(x=lower.index, y=lower.round(1), mode="lines", line=dict(width=0), fill="tonexty",
                    fillcolor=c["band"], name="Normalbereich", hoverinfo="skip")
    fig.add_scatter(x=full.index[sel], y=full[sel], mode="markers", name="HRV pro Nacht",
                    marker=dict(color=c["muted"], size=8), hovertemplate="%{y:.0f} ms")
    fig.add_scatter(x=avg7.index[sel], y=avg7[sel].round(1), mode="lines", name="Ø 7 Tage",
                    line=dict(color=c["swim"], width=2), hovertemplate="%{y:.0f} ms")
    return _layout(fig, 300, "HRV (ms)")


def line_with_baseline(series: pd.Series, name: str, unit: str, baseline_days: int, days: int = 90,
                       color_key: str = "swim") -> go.Figure | None:
    c = colors()
    s = series.dropna()
    if s.empty:
        return None
    full = s.asfreq("D")
    baseline = full.rolling(baseline_days, min_periods=7).mean()
    start = full.index.max() - pd.Timedelta(days=days)
    sel = full.index >= start
    fig = go.Figure()
    fig.add_scatter(x=baseline.index[sel], y=baseline[sel].round(1), mode="lines",
                    name=f"Ø {baseline_days} Tage", line=dict(color=c["muted"], width=2))
    fig.add_scatter(x=full.index[sel], y=full[sel], mode="lines+markers", name=name, connectgaps=False,
                    line=dict(color=c[color_key], width=2), marker=dict(size=8))
    return _layout(fig, 260, unit)


def sleep_chart(wellness: pd.DataFrame, days: int = 60) -> go.Figure | None:
    c = colors()
    hours = wellness["sleep_hours"].dropna() if not wellness.empty else pd.Series(dtype=float)
    if hours.empty:
        return None
    hours = hours[hours.index >= hours.index.max() - pd.Timedelta(days=days)]
    fig = go.Figure(go.Bar(x=hours.index, y=hours.round(2), marker_color=c["swim"], name="Schlaf",
                           hovertemplate="%{y:.1f} h"))
    fig.add_hline(y=7, line=dict(color=c["muted"], width=1),
                  annotation_text="7 h", annotation_position="top left")
    fig.update_layout(showlegend=False)
    return _layout(fig, 260, "Stunden")


def e1rm_chart(history: pd.DataFrame) -> go.Figure:
    c = colors()
    fig = go.Figure()
    fig.add_scatter(x=history["date"], y=history["e1rm"].round(1), mode="lines+markers",
                    name="Geschätztes Maximum (1RM)", line=dict(color=c["swim"], width=2), marker=dict(size=8))
    fig.add_scatter(x=history["date"], y=history["top_weight"], mode="lines+markers", name="Topgewicht",
                    line=dict(color=c["bike"], width=2), marker=dict(size=8))
    return _layout(fig, 300, "kg")


def kcal_chart(totals: pd.DataFrame, targets: pd.Series) -> go.Figure:
    c = colors()
    fig = go.Figure()
    fig.add_bar(x=totals["date"], y=totals["kcal"].round(0), name="Gegessen", marker_color=c["swim"],
                hovertemplate="%{y:.0f} kcal")
    fig.add_scatter(x=targets.index, y=targets.round(0), mode="markers", name="Ziel",
                    marker=dict(color=c["bike"], size=10, symbol="line-ew-open", line=dict(width=3)),
                    hovertemplate="%{y:.0f} kcal")
    return _layout(fig, 280, "kcal")


def projection_chart(history: pd.DataFrame, projection: pd.DataFrame, target: float,
                     phases: list[dict]) -> go.Figure:
    c = colors()
    fig = go.Figure()
    for i, block in enumerate(phases):
        if i % 2 == 0:
            fig.add_vrect(x0=block["start"], x1=block["end"] + timedelta(days=1), fillcolor=c["band"],
                          line_width=0, layer="below")
        fig.add_annotation(x=block["start"] + (block["end"] - block["start"]) / 2, y=1.0, yref="paper",
                           text=block["phase"].name, showarrow=False, yanchor="bottom",
                           font=dict(size=11, color=c["muted"]))
    fig.add_scatter(x=history.index, y=history["ctl"].round(1), mode="lines", name="Fitness bisher",
                    line=dict(color=c["swim"], width=2))
    fig.add_scatter(x=projection["date"], y=projection["ctl"].round(1), mode="lines+markers",
                    name="Erwarteter Verlauf", line=dict(color=c["bike"], width=2), marker=dict(size=8),
                    customdata=projection["phase"], hovertemplate="%{y:.0f} CTL (%{customdata})")
    fig.add_hline(y=target, line=dict(color=c["muted"], width=1),
                  annotation_text=f"Ziel-CTL {target:.0f}", annotation_position="bottom right")
    fig = _layout(fig, 340, "Fitness (CTL)")
    fig.update_layout(margin=dict(t=60))
    fig.update_xaxes(tickformat="%m/%Y")
    return fig
