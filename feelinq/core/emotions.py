from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Emotion:
    key: str
    valence: float
    arousal: float


EMOTION_CATALOG: dict[str, Emotion] = {e.key: e for e in [
    # High arousal, positive valence
    Emotion("astonished",  +0.158, +0.890),
    Emotion("excited",     +0.618, +0.757),
    Emotion("happy",       +0.826, +0.526),

    # Low arousal, positive valence
    Emotion("pleased",     +0.771, +0.185),
    Emotion("peaceful",    +0.590, -0.260),
    Emotion("calm",        +0.562, -0.305),
    Emotion("relaxed",     +0.689, -0.453),
    Emotion("sleepy",      +0.279, -0.671),

    # High arousal, negative valence
    Emotion("angry",       -0.523, +0.585),
    Emotion("frustrated",  -0.645, +0.510),
    Emotion("anxious",     -0.450, +0.550),
    Emotion("annoyed",     -0.545, +0.412),
    Emotion("afraid",      -0.340, +0.640),
    Emotion("nervous",     -0.632, +0.269),

    # Low arousal, negative valence
    Emotion("sad",         -0.648, -0.267),
    Emotion("miserable",   -0.696, -0.078),
    Emotion("bored",       -0.664, -0.635),
    Emotion("tired",       +0.043, -0.628),
    Emotion("droopy",      -0.350, -0.800),

    # Neutral
    Emotion("neutral",      0.000,  0.000),
]}

GRID_COLUMNS = 3

MIN_USER_EMOTIONS = 6
MAX_USER_EMOTIONS = 15
MIN_PER_QUADRANT = 1

QUADRANT_LABELS = {
    "hp_ha": "High energy, positive",   # high arousal, positive valence
    "lp_ha": "High energy, negative",   # high arousal, negative valence
    "hp_la": "Low energy, positive",    # low arousal, positive valence
    "lp_la": "Low energy, negative",    # low arousal, negative valence
}


def get_quadrant(e: Emotion) -> str:
    v = "hp" if e.valence >= 0 else "lp"
    a = "ha" if e.arousal >= 0 else "la"
    return f"{v}_{a}"


def emotions_by_quadrant() -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {q: [] for q in QUADRANT_LABELS}
    for e in EMOTION_CATALOG.values():
        groups[get_quadrant(e)].append(e.key)
    return groups


def make_grid(keys: list[str]) -> list[list[str]]:
    return [keys[i:i + GRID_COLUMNS] for i in range(0, len(keys), GRID_COLUMNS)]


def validate_emotion_selection(keys: set[str]) -> str | None:
    """Returns an error reason or None if valid."""
    if len(keys) < MIN_USER_EMOTIONS:
        return "too_few"
    if len(keys) > MAX_USER_EMOTIONS:
        return "too_many"
    counts = {q: 0 for q in QUADRANT_LABELS}
    for k in keys:
        e = EMOTION_CATALOG.get(k)
        if e:
            counts[get_quadrant(e)] += 1
    for q, c in counts.items():
        if c < MIN_PER_QUADRANT:
            return "missing_quadrant"
    return None


def mean_valence_arousal(keys: list[str]) -> tuple[float, float]:
    emotions = [EMOTION_CATALOG[k] for k in keys]
    v = sum(e.valence for e in emotions) / len(emotions)
    a = sum(e.arousal for e in emotions) / len(emotions)
    return round(v, 2), round(a, 2)
