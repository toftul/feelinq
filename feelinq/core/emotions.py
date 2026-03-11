from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Emotion:
    key: str
    valence: float
    arousal: float


EMOTION_CATALOG: dict[str, Emotion] = {e.key: e for e in [
    # High arousal, positive valence
    Emotion("excited",     +0.8, +0.8),
    Emotion("elated",      +0.7, +0.6),
    Emotion("enthusiastic",+0.6, +0.7),
    Emotion("happy",       +0.8, +0.2),

    # Low arousal, positive valence
    Emotion("content",     +0.6, -0.3),
    Emotion("relaxed",     +0.5, -0.7),
    Emotion("calm",        +0.3, -0.6),
    Emotion("peaceful",    +0.4, -0.5),

    # High arousal, negative valence
    Emotion("angry",       -0.8, +0.8),
    Emotion("anxious",     -0.5, +0.7),
    Emotion("stressed",    -0.6, +0.6),
    Emotion("frustrated",  -0.7, +0.5),

    # Low arousal, negative valence
    Emotion("sad",         -0.7, -0.4),
    Emotion("bored",       -0.3, -0.7),
    Emotion("tired",       -0.2, -0.8),
    Emotion("lonely",      -0.6, -0.3),

    # Neutral
    Emotion("neutral",      0.0,  0.0),
    Emotion("surprised",   +0.1, +0.8),
]}

# Grid layout for the emotion picker keyboard (3 columns)
# Arranged: top rows = high arousal, bottom rows = low arousal
# Left = positive valence, right = negative valence
EMOTION_GRID: list[list[str]] = [
    ["excited",      "elated",    "angry"],
    ["enthusiastic", "surprised", "anxious"],
    ["happy",        "stressed",  "frustrated"],
    ["content",      "lonely",    "sad"],
    ["peaceful",     "bored",     "tired"],
    ["relaxed",      "calm",      "neutral"],
]


def mean_valence_arousal(keys: list[str]) -> tuple[float, float]:
    emotions = [EMOTION_CATALOG[k] for k in keys]
    v = sum(e.valence for e in emotions) / len(emotions)
    a = sum(e.arousal for e in emotions) / len(emotions)
    return round(v, 2), round(a, 2)
