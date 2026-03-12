import io
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.transforms as transforms
from matplotlib.patches import Ellipse
import numpy as np

from feelinq.core.emotions import EMOTION_CATALOG
from feelinq.db import timescale

log = logging.getLogger(__name__)

MIN_ENTRIES = 5

# Quadrant colors matching the check-in emoji diagram
_QUADRANT_COLORS = {
    "lp_ha": "#e74c3c",  # 🟥 tense / angry
    "hp_ha": "#f1c40f",  # 🟨 excited / happy
    "lp_la": "#3498db",  # 🟦 sad / bored
    "hp_la": "#2ecc71",  # 🟩 calm / relaxed
}
_QUADRANT_LABELS = {
    "lp_ha": "Tense",
    "hp_ha": "Excited",
    "lp_la": "Sad",
    "hp_la": "Calm",
}


async def generate_all(user_id: str) -> list[tuple[str, bytes]] | None:
    entries = await timescale.query_mood_entries(user_id, range_days=90)
    if len(entries) < MIN_ENTRIES:
        return None

    charts: list[tuple[str, bytes]] = []
    charts.append(("Valence over time", _valence_over_time(entries)))
    charts.append(("Arousal over time", _arousal_over_time(entries)))
    charts.append(("Circumplex scatter", _circumplex_scatter(entries)))
    charts.append(("Quadrant distribution", _quadrant_distribution(entries)))
    charts.append(("Emotion frequency", _emotion_frequency(entries)))
    charts.append(("Time of day", _time_of_day(entries)))
    charts.append(("Weekly heatmap", _weekly_heatmap(entries)))
    return charts


async def generate_weekly(user_id: str) -> tuple[str, bytes] | None:
    entries = await timescale.query_mood_entries(user_id, range_days=7)
    if not entries:
        return None
    return ("Weekly circumplex", _circumplex_scatter(entries))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rolling_stats(
    times: list[datetime],
    values: list[float],
    window_hours: int = 48,
    step_hours: int = 5,
) -> tuple[list[datetime], np.ndarray, np.ndarray]:
    """Compute a rolling mean and std over a time-based window."""
    if not times:
        return [], np.array([]), np.array([])

    t_arr = np.array([t.timestamp() for t in times])
    v_arr = np.array(values)
    window_s = window_hours * 3600

    t_min, t_max = t_arr[0], t_arr[-1]
    step_s = step_hours * 3600
    centers = np.arange(t_min, t_max + step_s, step_s)

    out_times: list[datetime] = []
    out_mean: list[float] = []
    out_std: list[float] = []

    for c in centers:
        mask = (t_arr >= c - window_s / 2) & (t_arr <= c + window_s / 2)
        if mask.sum() < 2:
            continue
        out_times.append(datetime.fromtimestamp(c, tz=timezone.utc))
        out_mean.append(float(v_arr[mask].mean()))
        out_std.append(float(v_arr[mask].std()))

    return out_times, np.array(out_mean), np.array(out_std)


def _confidence_ellipse(
    x: np.ndarray,
    y: np.ndarray,
    ax: plt.Axes,
    n_std: float = 2.0,
    facecolor: str = "none",
    **kwargs,
) -> Ellipse | None:
    """Draw a covariance confidence ellipse. Returns None if not enough data."""
    if len(x) < 3:
        return None

    cov = np.cov(x, y)
    if cov[0, 0] == 0 or cov[1, 1] == 0:
        return None

    pearson = cov[0, 1] / np.sqrt(cov[0, 0] * cov[1, 1])
    ell_radius_x = np.sqrt(1 + pearson)
    ell_radius_y = np.sqrt(1 - pearson)
    ellipse = Ellipse(
        (0, 0),
        width=ell_radius_x * 2,
        height=ell_radius_y * 2,
        facecolor=facecolor,
        **kwargs,
    )

    scale_x = np.sqrt(cov[0, 0]) * n_std
    scale_y = np.sqrt(cov[1, 1]) * n_std
    mean_x = float(np.mean(x))
    mean_y = float(np.mean(y))

    transf = (
        transforms.Affine2D()
        .rotate_deg(45)
        .scale(scale_x, scale_y)
        .translate(mean_x, mean_y)
    )
    ellipse.set_transform(transf + ax.transData)
    return ax.add_patch(ellipse)


def _get_quadrant_key(v: float, a: float) -> str:
    vk = "hp" if v >= 0 else "lp"
    ak = "ha" if a >= 0 else "la"
    return f"{vk}_{ak}"


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def _valence_over_time(entries: list[dict]) -> bytes:
    times = [e["time"] for e in entries]
    vals = [e["mean_valence"] for e in entries]

    fig, ax = plt.subplots(figsize=(8, 3))

    # Raw data points
    ax.scatter(times, vals, s=12, alpha=0.35, color="#4a90d9", edgecolors="none", zorder=2)

    # Rolling average ± std
    rt, rm, rs = _rolling_stats(times, vals)
    if len(rt) > 1:
        ax.plot(rt, rm, linewidth=2, color="#4a90d9", zorder=3)
        ax.fill_between(rt, rm - rs, rm + rs, color="#4a90d9", alpha=0.2, edgecolor="none")

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

    # Raw data points
    ax.scatter(times, vals, s=12, alpha=0.35, color="#d94a4a", edgecolors="none", zorder=2)

    # Rolling average ± std
    rt, rm, rs = _rolling_stats(times, vals)
    if len(rt) > 1:
        ax.plot(rt, rm, linewidth=2, color="#d94a4a", zorder=3)
        ax.fill_between(rt, rm - rs, rm + rs, color="#d94a4a", alpha=0.2, edgecolor="none")

    ax.axhline(0, color="gray", linewidth=0.5, linestyle="--")
    ax.set_ylim(-1.1, 1.1)
    ax.set_ylabel("Arousal")
    ax.set_title("Arousal over time")
    fig.autofmt_xdate()
    fig.tight_layout()
    return _fig_to_bytes(fig)


def _circumplex_scatter(entries: list[dict]) -> bytes:
    vals = np.array([e["mean_valence"] for e in entries])
    aros = np.array([e["mean_arousal"] for e in entries])

    # Split into recent (last 14 days) vs all
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=14)
    recent_mask = np.array([
        (e["time"].replace(tzinfo=timezone.utc) if e["time"].tzinfo is None else e["time"]) >= cutoff
        for e in entries
    ])

    fig, ax = plt.subplots(figsize=(5, 5))

    # All-time 2σ ellipse (grey)
    _confidence_ellipse(
        vals, aros, ax, n_std=2,
        facecolor="lightgray", edgecolor="none", alpha=0.4, label="All time (2σ)",
    )

    # Recent 2σ ellipse (orange)
    if recent_mask.sum() >= 3:
        _confidence_ellipse(
            vals[recent_mask], aros[recent_mask], ax, n_std=2,
            facecolor="orange", edgecolor="none", alpha=0.35, label="Last 2 weeks (2σ)",
        )

    # Scatter points (colored by recency)
    colors = np.linspace(0.3, 1.0, len(entries))
    ax.scatter(vals, aros, c=colors, cmap="Blues", edgecolors="black", linewidth=0.5, s=50, zorder=3)

    # Emotion reference labels
    for e in EMOTION_CATALOG.values():
        if e.key == "neutral":
            continue
        ax.annotate(
            e.key.capitalize(),
            (e.valence, e.arousal),
            fontsize=6, color="gray", alpha=0.7,
            ha="center", va="bottom",
            textcoords="offset points", xytext=(0, 3),
        )

    # Axes and quadrant lines
    ax.axhline(0, color="gray", linewidth=0.5)
    ax.axvline(0, color="gray", linewidth=0.5)
    ax.set_xlim(-1.2, 1.2)
    ax.set_ylim(-1.2, 1.2)
    ax.set_xlabel("Valence (negative → positive)")
    ax.set_ylabel("Arousal (low → high)")
    ax.set_title("Russell Circumplex")
    ax.set_aspect("equal")
    ax.legend(loc="upper left", fontsize=7, framealpha=0.8)
    fig.tight_layout()
    return _fig_to_bytes(fig)


def _quadrant_distribution(entries: list[dict]) -> bytes:
    counts: dict[str, int] = {"hp_ha": 0, "lp_ha": 0, "hp_la": 0, "lp_la": 0}
    for e in entries:
        q = _get_quadrant_key(e["mean_valence"], e["mean_arousal"])
        counts[q] += 1

    total = sum(counts.values()) or 1
    keys = list(_QUADRANT_LABELS.keys())
    labels = [_QUADRANT_LABELS[k] for k in keys]
    sizes = [counts[k] / total * 100 for k in keys]
    bar_colors = [_QUADRANT_COLORS[k] for k in keys]

    fig, ax = plt.subplots(figsize=(5, 3))
    bars = ax.barh(labels[::-1], sizes[::-1], color=bar_colors[::-1])
    for bar, pct in zip(bars, sizes[::-1]):
        ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height() / 2,
                f"{pct:.0f}%", va="center", fontsize=9)
    ax.set_xlim(0, max(sizes) * 1.25 if sizes else 100)
    ax.set_xlabel("% of check-ins")
    ax.set_title("Quadrant distribution")
    ax.xaxis.set_visible(False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
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


def _time_of_day(entries: list[dict]) -> bytes:
    """Average valence and arousal by hour of day."""
    hour_vals: dict[int, list[float]] = {h: [] for h in range(24)}
    hour_aros: dict[int, list[float]] = {h: [] for h in range(24)}

    for e in entries:
        t = e["time"]
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        h = t.hour
        hour_vals[h].append(e["mean_valence"])
        hour_aros[h].append(e["mean_arousal"])

    hours = list(range(24))
    mean_v = [np.mean(hour_vals[h]) if hour_vals[h] else np.nan for h in hours]
    mean_a = [np.mean(hour_aros[h]) if hour_aros[h] else np.nan for h in hours]
    count = [len(hour_vals[h]) for h in hours]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 4), sharex=True)

    # Valence by hour
    ax1.bar(hours, mean_v, color="#4a90d9", alpha=0.7, width=0.8)
    ax1.axhline(0, color="gray", linewidth=0.5, linestyle="--")
    ax1.set_ylim(-1.1, 1.1)
    ax1.set_ylabel("Valence")
    ax1.set_title("Mood by time of day")

    # Arousal by hour
    ax2.bar(hours, mean_a, color="#d94a4a", alpha=0.7, width=0.8)
    ax2.axhline(0, color="gray", linewidth=0.5, linestyle="--")
    ax2.set_ylim(-1.1, 1.1)
    ax2.set_ylabel("Arousal")
    ax2.set_xlabel("Hour of day")
    ax2.set_xticks(range(0, 24, 3))
    ax2.set_xticklabels([f"{h:02d}" for h in range(0, 24, 3)])

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
