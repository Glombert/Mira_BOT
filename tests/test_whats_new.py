"""Тесты для tools/whats_new.py — парсер WHATS_NEW.md и фильтр audience."""

import pytest
from unittest.mock import patch
from tools import whats_new as wn


SAMPLE = """# Что у Миры нового

Какая-то документация, должна игнорироваться.

## 2026-05-30

- [OWNER] **Тех-канал**: отдельный чат для разработчика.
- [ALL] **Селф-тест**: на запуске проверяет ритуалы.
- [ALL] **Длинные сообщения**: разбиваются на чанки
  в Telegram автоматически.

## 2026-05-15

- [ALL] **Aurora-веб**: тот же дизайн, что на мобайле.
- [ALL] **Авто-обновление мобайла**: APK прилетает в приложение.
"""


@pytest.fixture
def md_file(tmp_path):
    f = tmp_path / "WHATS_NEW.md"
    f.write_text(SAMPLE, encoding="utf-8")
    with patch.object(wn, "WHATS_NEW_PATH", str(f)):
        yield str(f)


def test_parse_returns_all_entries(md_file):
    entries = wn._parse()
    assert len(entries) == 5
    # Свежие даты впереди не гарантировано в _parse, проверим присутствие
    audiences = {e["audience"] for e in entries}
    assert audiences == {"OWNER", "ALL"}


def test_multiline_entry_glued(md_file):
    entries = wn._parse()
    chunks = next(e for e in entries if "Длинные" in e["text"])
    # Многострочная запись должна быть склеена
    assert "в Telegram автоматически" in chunks["text"]


def test_audience_all_filters_owner(md_file):
    r = wn.whats_new(audience="all")
    assert r["ok"]
    texts = "\n".join(e["text"] for e in r["entries"])
    assert "Тех-канал" not in texts  # OWNER-only скрыто
    assert "Aurora-веб" in texts
    assert "Селф-тест" in texts


def test_audience_owner_sees_everything(md_file):
    r = wn.whats_new(audience="owner")
    texts = "\n".join(e["text"] for e in r["entries"])
    assert "Тех-канал" in texts
    assert "Aurora-веб" in texts


def test_sorted_newest_first(md_file):
    r = wn.whats_new(audience="all")
    dates = [e["date"] for e in r["entries"]]
    assert dates == sorted(dates, reverse=True)


def test_limit_caps_entries(md_file):
    r = wn.whats_new(audience="owner", limit=2)
    assert len(r["entries"]) == 2


def test_missing_file_returns_empty():
    with patch.object(wn, "WHATS_NEW_PATH", "/nonexistent/path.md"):
        r = wn.whats_new()
        assert r["ok"]
        assert r["entries"] == []
        assert "Пока без свежих" in r["summary"]


def test_latest_since_filters_by_date(md_file, monkeypatch):
    # Подменяем mtime и просим записи с 2026-05-20 → должна остаться только
    # майская секция 30 числа.
    import time
    cutoff = time.mktime((2026, 5, 20, 0, 0, 0, 0, 0, -1))
    entries = wn.latest_entries_since(cutoff, audience="all")
    assert all(e["date"] >= "2026-05-20" for e in entries)
    assert any("Селф-тест" in e["text"] for e in entries)
    assert not any("Aurora-веб" in e["text"] for e in entries)


def test_changelog_mtime_returns_positive(md_file):
    assert wn.changelog_mtime() > 0
