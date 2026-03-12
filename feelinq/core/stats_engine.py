import io
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from feelinq.db import timescale

log = logging.getLogger(__name__)

MIN_ENTRIES = 5


async def generate_all(user_id: str) -> list[tuple[str, bytes]] | None:
    entries = await timescale.query_mood_entries(user_id, range_days=90)
    if len(entries) < MIN_ENTRIES:
        return None

    charts: list[tuple[str, bytes]] = []
    charts.append(("Valence over time", _valence_over_time(entries)))
    charts.append(("Arousal over time", _arousal_over_time(entries)))
    charts.append(("Circumplex scatter", _circumplex_scatter(entries)))
    charts.append(("Emotion frequency", _emotion_frequency(entries)))
    charts.append(("Weekly heatmap", _weekly_heatmap(entries)))
    return charts


async def generate_weekly(user_id: str) -> tuple[str, bytes] | None:
    entries = await timescale.query_mood_entries(user_id, range_days=7)
    if not entries:
        return None
    return ("Weekly circumplex", _circumplex_scatter(entries))


def _valence_over_time(entries: list[dict]) -> bytes:
    times = [e["time"] for e in entries]
    vals = [e["mean_valence"] for e in entries]
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(times, vals, marker="o", linewidth=1.5, markersize=4, color="#4a90d9")
    ax.axhline(0, color="gray", linewidth=0.5, linestyle="--")
    ax.set_ylim(-1.1, 1.1)
    ax.set_ylabel("Valence")
    ax.set_title("Valence over time")
    fig.autofmt_xdate()
    fig.tight_layout()
    return _fig_to_bytes(fig)


def _arousal_over_time(entries: list[dict]) -> bytes:
    times = [e["time"] for e in entries]
    vals = [e["mean_arousal"] for e in entries]
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(times, vals, marker="o", linewidth=1.5, markersize=4, color="#d94a4a")
    ax.axhline(0, color="gray", linewidth=0.5, linestyle="--")
    ax.set_ylim(-1.1, 1.1)
    ax.set_ylabel("Arousal")
    ax.set_title("Arousal over time")
    fig.autofmt_xdate()
    fig.tight_layout()
    return _fig_to_bytes(fig)


def _circumplex_scatter(entries: list[dict]) -> bytes:
    vals = [e["mean_valence"] for e in entries]
    aros = [e["mean_arousal"] for e in entries]
    # Color by recency: older = lighter, newer = darker
    colors = np.linspace(0.3, 1.0, len(entries))

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.scatter(vals, aros, c=colors, cmap="Blues", edgecolors="black", linewidth=0.5, s=50, zorder=3)
    ax.axhline(0, color="gray", linewidth=0.5)
    ax.axvline(0, color="gray", linewidth=0.5)
    ax.set_xlim(-1.2, 1.2)
    ax.set_ylim(-1.2, 1.2)
    ax.set_xlabel("Valence (negative → positive)")
    ax.set_ylabel("Arousal (low → high)")
    ax.set_title("Russell Circumplex")
    ax.set_aspect("equal")
    # Quadrant labels
    ax.text(0.7, 0.9, "Excited", fontsize=8, color="gray", ha="center")
    ax.text(-0.7, 0.9, "Tense", fontsize=8, color="gray", ha="center")
    ax.text(0.7, -0.9, "Calm", fontsize=8, color="gray", ha="center")
    ax.text(-0.7, -0.9, "Sad", fontsize=8, color="gray", ha="center")
    fig.tight_layout()
    return _fig_to_bytes(fig)


def _emotion_frequency(entries: list[dict]) -> bytes:
    counter: Counter[str] = Counter()
    for e in entries:
        emotions_str = e.get("emotions", "")
        if emotions_str:
            for em in emotions_str.split(","):
                counter[em.strip()] += 1
    if not counter:
        # Return empty chart
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
        fig.tight_layout()
        return _fig_to_bytes(fig)

    top = counter.most_common(10)
    labels = [t[0] for t in top]
    counts = [t[1] for t in top]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.barh(labels[::-1], counts[::-1], color="#4a90d9")
    ax.set_xlabel("Count")
    ax.set_title("Top emotions")
    fig.tight_layout()
    return _fig_to_bytes(fig)


def _weekly_heatmap(entries: list[dict]) -> bytes:
    now = datetime.now(timezone.utc)
    weeks = 8
    valence_grid = np.full((weeks, 7), np.nan)
    arousal_grid = np.full((weeks, 7), np.nan)
    counts = np.zeros((weeks, 7), dtype=int)

    for e in entries:
        t = e["time"]
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        days_ago = (now - t).days
        week_idx = weeks - 1 - (days_ago // 7)
        day_idx = t.weekday()
        if 0 <= week_idx < weeks:
            if np.isnan(valence_grid[week_idx, day_idx]):
                valence_grid[week_idx, day_idx] = 0
                arousal_grid[week_idx, day_idx] = 0
            valence_grid[week_idx, day_idx] += e["mean_valence"]
            arousal_grid[week_idx, day_idx] += e["mean_arousal"]
            counts[week_idx, day_idx] += 1

    with np.errstate(invalid="ignore"):
        mask = counts > 0
        valence_grid[mask] = valence_grid[mask] / counts[mask]
        arousal_grid[mask] = arousal_grid[mask] / counts[mask]

    # Week labels: Monday date of each row
    today_monday = now.date() - timedelta(days=now.weekday())
    week_labels = [
        (today_monday - timedelta(weeks=weeks - 1 - i)).strftime("%-d %b")
        for i in range(weeks)
    ]
    day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    cmap_valence = plt.cm.RdYlGn   # type: ignore[attr-defined]
    cmap_valence.set_bad(color="#e8e8e8")
    cmap_arousal = plt.cm.RdYlBu_r  # type: ignore[attr-defined]
    cmap_arousal.set_bad(color="#e8e8e8")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))

    for ax, grid, cmap, title, label in (
        (ax1, valence_grid, cmap_valence, "Valence\n(negative → positive)", "Valence"),
        (ax2, arousal_grid, cmap_arousal, "Arousal\n(calm → energised)", "Arousal"),
    ):
        im = ax.imshow(grid, cmap=cmap, vmin=-1, vmax=1, aspect="auto")
        ax.set_xticks(range(7))
        ax.set_xticklabels(day_labels)
        ax.set_yticks(range(weeks))
        ax.set_yticklabels(week_labels, fontsize=8)
        ax.set_title(title)
        fig.colorbar(im, ax=ax, shrink=0.8, label=label)

    fig.suptitle("Weekly mood heatmap (last 8 weeks)", fontsize=11, y=1.01)
    fig.tight_layout()
    return _fig_to_bytes(fig)


def _fig_to_bytes(fig: plt.Figure) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
