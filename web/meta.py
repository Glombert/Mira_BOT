"""web/meta.py — метаданные Миры (версия)."""

from pathlib import Path

_MIRA_VERSION_CACHE = None


def mira_version() -> str:
    """Версия бэкенда Миры. Единый источник — бейдж в README (его бампит
    scripts/release.sh при релизе), чтобы не дублировать версию в коде."""
    global _MIRA_VERSION_CACHE
    if _MIRA_VERSION_CACHE is None:
        ver = ""
        try:
            text = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")
            i = text.find("version-")
            if i != -1:
                tail = text[i + len("version-"):]
                end = tail.find("-brightgreen")
                if end != -1:
                    ver = tail[:end]
        except Exception:
            ver = ""
        _MIRA_VERSION_CACHE = ver or "—"
    return _MIRA_VERSION_CACHE
