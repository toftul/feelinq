import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_locales: dict[str, dict[str, str]] = {}


def load_locales(locales_dir: Path | None = None) -> None:
    if locales_dir is None:
        locales_dir = Path(__file__).resolve().parent.parent / "locales"
    for f in locales_dir.glob("*.json"):
        _locales[f.stem] = json.loads(f.read_text("utf-8"))
        log.info("Loaded locale: %s (%d keys)", f.stem, len(_locales[f.stem]))
    if not _locales:
        raise RuntimeError(f"No locale files found in {locales_dir}")
    # Verify all locales have the same keys as English
    en_keys = set(_locales.get("en", {}).keys())
    for lang, data in _locales.items():
        missing = en_keys - set(data.keys())
        if missing:
            log.warning("Locale '%s' missing keys: %s", lang, missing)


def t(lang: str, key: str, **kwargs: object) -> str:
    locale = _locales.get(lang, _locales.get("en", {}))
    template = locale.get(key) or _locales["en"][key]
    return template.format(**kwargs) if kwargs else template


def available_languages() -> list[str]:
    return sorted(_locales.keys())
