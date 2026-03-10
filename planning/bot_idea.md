# Feelinq bot

A bot for tracking your mood and emotional state over time. It periodically asks "how was your day?", collects emotion tags, stores everything in InfluxDB, and lets you view stats and trends overtime.

## How it works

1. The bot sends you a reminder at a random time within your configured window.
2. You pick one or more emotions from a predefined list.
3. Your entry is saved. Over time, bot can show you plots of your mood history, emotion distribution on the Russell map, and valence/arousal trends.


## Emotion theory

It seems that our brain have two independent neurophysiological systems, thus any attempt to represent an emotional states ends up to be two deminetional [[Colibazzi, T. et al (2010)](https://doi.org/10.1037/a0018484); [Posner, J. et al. (2009)](https://doi.org/10.1037/h0077714)]. In this bot emotions are placed on the **Russell circumplex model of affect** [(Russell, 1980)](https://doi.org/10.1037/h0077714). The model represents emotional states in a 2D space:

- **Valence** (x-axis): how pleasant or unpleasant the emotion feels, from -1 (very negative) to +1 (very positive).
- **Arousal** (y-axis): how activated or deactivated you are, from -1 (very calm/sleepy) to +1 (very energized).

For example: *Excited* sits high-valence + high-arousal; *Relaxed* is high-valence + low-arousal; *Angry* is low-valence + high-arousal; *Bored* is low-valence + low-arousal.

When you select multiple emotions in one session, the bot stores their mean valence and arousal, giving a single point on the circumplex that represents your overall affective state for that entry.
