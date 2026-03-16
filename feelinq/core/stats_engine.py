import calendar as cal
import io
import logging
from collections import Counter
from datetime import date, datetime, timedelta, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.transforms as transforms
from matplotlib.patches import Ellipse, Polygon
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
    # charts.append(("Emotion frequency", _emotion_frequency(entries)))
    # charts.append(("Time of day", _time_of_day(entries)))

    # Year calendar uses a full year of data
    year_entries = await timescale.query_mood_entries(user_id, range_days=365)
    charts.append(("Year calendar", _year_calendar_valence(year_entries)))
    charts.append(("Energy calendar", _year_calendar_arousal(year_entries)))
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

    # All-time ellipse
    _confidence_ellipse(
        vals, aros, ax, n_std=2,
        facecolor="lightgray", edgecolor="none", alpha=0.2,
        label=r"All time (2$\sigma$)",
    )

    # Recent ellipses (orange, stacked sigma bands)
    if recent_mask.sum() >= 3:
        _confidence_ellipse(
            vals[recent_mask], aros[recent_mask], ax, n_std=2,
            facecolor="orange", edgecolor="none", alpha=0.15,
            label=r"Last 2 weeks (2$\sigma$)",
        )

    # Scatter points
    ax.scatter(
        vals, aros, c="k", s=20, alpha=0.2,
        edgecolors="none", zorder=3,
    )

    # Emotion reference labels
    for e in EMOTION_CATALOG.values():
        if e.key == "neutral":
            continue
        ax.annotate(
            e.key.capitalize(),
            (e.valence, e.arousal),
            fontsize=6, color="gray", alpha=0.7,
            ha="center", va="bottom",
            textcoords="offset points", xytext=(0, 10),
        )

    # Axes
    ax.set_xlim(-1.2, 1.2)
    ax.set_ylim(-1.2, 1.2)
    ax.set_xticks([-1, 0, 1])
    ax.set_xticklabels(["Negative", "Neutral", "Positive"])
    ax.set_yticks([-1, 0, 1])
    ax.set_yticklabels(["Weak", "Neutral", "Strong"])
    ax.set_xlabel("Valence", fontweight="bold")
    ax.set_ylabel("Arousal", fontweight="bold")
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

    keys = list(_QUADRANT_LABELS.keys())
    labels = [_QUADRANT_LABELS[k] for k in keys]
    sizes = [counts[k] for k in keys]
    colors = [_QUADRANT_COLORS[k] for k in keys]

    fig, ax = plt.subplots(figsize=(5, 5))
    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=labels,
        colors=colors,
        autopct="%1.0f%%",
        startangle=90,
        pctdistance=0.75,
        wedgeprops=dict(edgecolor="white", linewidth=2),
    )
    for t in autotexts:
        t.set_fontsize(10)
        t.set_fontweight("bold")
    ax.set_title("Quadrant distribution")
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
    labels = [t[0].capitalize() for t in top]
    counts = [t[1] for t in top]
    # Color each bar by its quadrant
    bar_colors = []
    for t in top:
        em = EMOTION_CATALOG.get(t[0])
        if em:
            bar_colors.append(_QUADRANT_COLORS[_get_quadrant_key(em.valence, em.arousal)])
        else:
            bar_colors.append("#4a90d9")

    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(labels, counts, color=bar_colors, edgecolor="white", linewidth=0.5)
    # Value labels on top of bars
    for bar, c in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                str(c), ha="center", va="bottom", fontsize=9, fontweight="medium")
    ax.set_ylabel("Count")
    ax.set_title("Top emotions")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.xticks(rotation=35, ha="right")
    fig.tight_layout()
    return _fig_to_bytes(fig)


# def _time_of_day(entries: list[dict]) -> bytes:
#     """Average valence and arousal by hour of day."""
#     hour_vals: dict[int, list[float]] = {h: [] for h in range(24)}
#     hour_aros: dict[int, list[float]] = {h: [] for h in range(24)}

#     for e in entries:
#         t = e["time"]
#         if t.tzinfo is None:
#             t = t.replace(tzinfo=timezone.utc)
#         h = t.hour
#         hour_vals[h].append(e["mean_valence"])
#         hour_aros[h].append(e["mean_arousal"])

#     hours = list(range(24))
#     mean_v = [np.mean(hour_vals[h]) if hour_vals[h] else np.nan for h in hours]
#     mean_a = [np.mean(hour_aros[h]) if hour_aros[h] else np.nan for h in hours]
#     count = [len(hour_vals[h]) for h in hours]

#     fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 4), sharex=True)

#     # Valence by hour
#     ax1.bar(hours, mean_v, color="#4a90d9", alpha=0.7, width=0.8)
#     ax1.axhline(0, color="gray", linewidth=0.5, linestyle="--")
#     ax1.set_ylim(-1.1, 1.1)
#     ax1.set_ylabel("Valence")
#     ax1.set_title("Mood by time of day")

#     # Arousal by hour
#     ax2.bar(hours, mean_a, color="#d94a4a", alpha=0.7, width=0.8)
#     ax2.axhline(0, color="gray", linewidth=0.5, linestyle="--")
#     ax2.set_ylim(-1.1, 1.1)
#     ax2.set_ylabel("Arousal")
#     ax2.set_xlabel("Hour of day")
#     ax2.set_xticks(range(0, 24, 3))
#     ax2.set_xticklabels([f"{h:02d}" for h in range(0, 24, 3)])

#     fig.tight_layout()
#     return _fig_to_bytes(fig)



def _year_calendar_valence(entries: list[dict]) -> bytes:
    return _year_calendar_generic(
        entries,
        field="mean_valence",
        cmap=plt.cm.RdYlGn.copy(),  # type: ignore[attr-defined]
        title="Mood Calendar",
        cbar_labels=["Very negative", "Negative", "Neutral", "Positive", "Very positive"],
        summary_label="positive",
    )


def _year_calendar_arousal(entries: list[dict]) -> bytes:
    return _year_calendar_generic(
        entries,
        field="mean_arousal",
        cmap=plt.cm.PiYG_r.copy(),  # type: ignore[attr-defined]
        title="Energy Calendar",
        cbar_labels=["Very calm", "Calm", "Neutral", "Energised", "Very energised"],
        summary_label="high energy",
    )


def _year_calendar_generic(
    entries: list[dict],
    *,
    field: str,
    cmap: plt.cm.ScalarMappable,
    title: str,
    cbar_labels: list[str],
    summary_label: str,
) -> bytes:
    """Last-12-months calendar heatmap for a given numeric field."""
    # Aggregate field by date
    day_data: dict[date, list[float]] = {}
    for e in entries:
        t = e["time"]
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        d = t.date()
        day_data.setdefault(d, []).append(e[field])

    day_avg = {d: float(np.mean(vals)) for d, vals in day_data.items()}

    # Last 12 months (oldest first)
    now = datetime.now(timezone.utc)
    months_list: list[tuple[int, int]] = []
    for i in range(11, -1, -1):
        total = now.year * 12 + (now.month - 1) - i
        months_list.append((total // 12, total % 12 + 1))

    month_names = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    days_header = ["M", "T", "W", "T", "F", "S", "S"]

    cmap.set_bad(color="#E8E8E8")

    fig, axes = plt.subplots(3, 4, figsize=(14.85, 10.5))

    for idx, ax in enumerate(axes.flat):
        yr, mo = months_list[idx]
        _, num_days = cal.monthrange(yr, mo)

        # Build calendar matrix for this month
        empty = np.full((6, 7), np.nan)
        day_nums = np.copy(empty)
        day_vals = np.copy(empty)

        row = 0
        for day in range(1, num_days + 1):
            d = date(yr, mo, day)
            col = d.weekday()
            day_nums[row, col] = day
            if d in day_avg:
                day_vals[row, col] = day_avg[d]
            if col == 6:
                row += 1

        # Summary: % of days with data that had value >= 0
        month_vals = [day_avg[date(yr, mo, d)]
                      for d in range(1, num_days + 1)
                      if date(yr, mo, d) in day_avg]

        ax.imshow(day_vals, cmap=cmap, vmin=-1, vmax=1, aspect="auto")

        ax.set_title(f"{month_names[mo - 1]} {yr}", fontsize=11, fontweight="bold")

        if month_vals:
            pct = sum(1 for v in month_vals if v >= 0) / len(month_vals) * 100
            ax.text(
                0.5, +0.05, f"{pct:.0f}% {summary_label}",
                ha="center", va="top", transform=ax.transAxes,
                fontsize=8, color="#555555", style="italic",
            )

        ax.set_xticks(np.arange(len(days_header)))
        ax.set_xticklabels(days_header, fontsize=9, fontweight="bold", color="#555555")
        ax.set_yticklabels([])

        ax.tick_params(axis="both", which="both", length=0)
        ax.xaxis.tick_top()

        ax.set_xticks(np.arange(-0.5, 6, 1), minor=True)
        ax.set_yticks(np.arange(-0.5, 5, 1), minor=True)
        ax.grid(which="minor", color="w", linestyle="-", linewidth=2.1)

        for edge in ["left", "right", "bottom", "top"]:
            ax.spines[edge].set_color("#FFFFFF")

        for w in range(6):
            for d in range(7):
                day_num = day_nums[w, d]

                # Non-calendar-day cell: white patch
                if np.isnan(day_num):
                    patch_coords = (
                        (d - 0.5, w - 0.5),
                        (d - 0.5, w + 0.5),
                        (d + 0.5, w + 0.5),
                        (d + 0.5, w - 0.5),
                    )
                    ax.add_artist(Polygon(patch_coords, fc="#FFFFFF"))
                    continue

                # Day number in top-right corner
                ax.text(
                    d + 0.45, w - 0.31, f"{day_num:0.0f}",
                    ha="right", va="center",
                    fontsize=6, color="#003333", alpha=0.8,
                )

                # White triangle behind day number for readability
                patch_coords = (
                    (d - 0.1, w - 0.5),
                    (d + 0.5, w - 0.5),
                    (d + 0.5, w + 0.1),
                )
                ax.add_artist(Polygon(patch_coords, fc="w", alpha=0.7))

    fig.suptitle(title, fontsize=16, fontweight="bold",
                 x=0.04, ha="left")

    # Colorbar: 25% of plot width, top-right next to title
    cbar_ax = fig.add_axes([0.71, 0.97, 0.25, 0.015])
    sm = plt.cm.ScalarMappable(
        cmap=cmap, norm=plt.Normalize(vmin=-1, vmax=1),
    )
    sm.set_array([])
    cb = fig.colorbar(sm, cax=cbar_ax, orientation="horizontal")
    cb.set_ticks([-1, -0.5, 0, 0.5, 1])
    cb.set_ticklabels(cbar_labels)
    cb.ax.tick_params(labelsize=8, length=0)

    plt.subplots_adjust(left=0.04, right=0.96, top=0.88, bottom=0.04, hspace=0.4)
    return _fig_to_bytes(fig)


def generate_circumplex_reference() -> bytes:
    """Static circumplex map with all emotions from EMOTION_CATALOG.

    Used by the /theory command to illustrate the model.
    """
    fig, ax = plt.subplots(figsize=(6, 6))

    # Colored quadrant backgrounds
    quad_bounds = {
        "lp_ha": (-1.2, 0, 0, 1.2),   # xmin, xmax, ymin, ymax
        "hp_ha": (0, 1.2, 0, 1.2),
        "lp_la": (-1.2, 0, -1.2, 0),
        "hp_la": (0, 1.2, -1.2, 0),
    }
    for q, (x0, x1, y0, y1) in quad_bounds.items():
        ax.fill_between(
            [x0, x1], y0, y1,
            color=_QUADRANT_COLORS[q], alpha=0.10, zorder=0,
        )

    # Plot emotion dots and labels
    for e in EMOTION_CATALOG.values():
        if e.key == "neutral":
            ax.plot(e.valence, e.arousal, "o", color="gray", markersize=6, zorder=3)
            ax.annotate(
                e.key.capitalize(), (e.valence, e.arousal),
                fontsize=8, color="gray",
                ha="center", va="bottom",
                textcoords="offset points", xytext=(0, 6),
            )
            continue
        q = _get_quadrant_key(e.valence, e.arousal)
        ax.plot(e.valence, e.arousal, "o", color=_QUADRANT_COLORS[q], markersize=7, zorder=3)
        ax.annotate(
            e.key.capitalize(), (e.valence, e.arousal),
            fontsize=8, fontweight="medium", color=_QUADRANT_COLORS[q],
            ha="center", va="bottom",
            textcoords="offset points", xytext=(0, 6),
        )

    # Axis arrows through origin
    arrow_kw = dict(
        arrowstyle="->,head_width=0.3,head_length=0.2",
        color="black", lw=1.2,
    )
    ax.annotate("", xy=(1.25, 0), xytext=(-1.25, 0),
                arrowprops=arrow_kw, annotation_clip=False)
    ax.annotate("", xy=(0, 1.25), xytext=(0, -1.25),
                arrowprops=arrow_kw, annotation_clip=False)

    # Axis labels at arrow tips
    ax.text(1.28, -0.06, "Pleasant", fontsize=10, ha="left", va="top")
    ax.text(-1.28, -0.06, "Unpleasant", fontsize=10, ha="right", va="top")
    ax.text(0.04, 1.28, "High energy", fontsize=10, ha="left", va="bottom")
    ax.text(0.04, -1.28, "Low energy", fontsize=10, ha="left", va="top")

    ax.set_xlim(-1.45, 1.45)
    ax.set_ylim(-1.45, 1.45)
    ax.set_aspect("equal")

    # Remove default axes (we have arrows instead)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])

    ax.set_title("Russell Circumplex Model of Affect", fontsize=12, pad=16)
    fig.tight_layout()
    return _fig_to_bytes(fig)


def _fig_to_bytes(fig: plt.Figure) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
