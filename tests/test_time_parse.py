"""Тесты для tools/time_parse.py — парсер русскоязычных временных выражений."""

import pytest
from datetime import datetime, timedelta, timezone
from tools.time_parse import parse_time, extract_time_and_rest

# parse_time с user_tz="UTC" считает «сегодня/завтра» по UTC, а хранит в UTC.
# Поэтому ожидаемую дату в тестах берём тоже по UTC, иначе на машине в зоне
# впереди UTC (напр. +10) тесты падают на стыке суток.


# ---------------------------------------------------------------------------
# parse_time — базовые форматы
# ---------------------------------------------------------------------------

def test_iso_pass_through():
    ok, iso = parse_time("2026-06-15T14:30:00")
    assert ok
    assert iso == "2026-06-15T14:30:00+00:00"


def test_date_only_adds_default_time():
    ok, iso = parse_time("2026-12-01")
    assert ok
    assert iso == "2026-12-01T09:00:00+00:00"


def test_tomorrow_with_time():
    ok, iso = parse_time("завтра 8:00")
    assert ok
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    assert iso == f"{tomorrow}T08:00:00+00:00"


def test_tomorrow_default_time():
    ok, iso = parse_time("завтра")
    assert ok
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    assert iso == f"{tomorrow}T09:00:00+00:00"


def test_in_n_hours():
    ok, iso = parse_time("через 3 часа")
    assert ok
    expected = (datetime.now() + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S")


def test_in_n_minutes():
    ok, iso = parse_time("через 15 минут")
    assert ok
    expected = (datetime.now() + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%S")


def test_today_with_time():
    ok, iso = parse_time("сегодня 15:30")
    assert ok
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert iso == f"{today}T15:30:00+00:00"


def test_weekday_with_time():
    ok, iso = parse_time("в пятницу 14:00")
    assert ok
    assert "T14:00:00" in iso


def test_garbage_rejected():
    ok, err = parse_time("какая-то ерунда")
    assert not ok
    assert "не понял" in err


# ---------------------------------------------------------------------------
# extract_time_and_rest — отделение времени от промпта
# ---------------------------------------------------------------------------

def test_extract_tomorrow_with_time_and_prompt():
    ok, iso, rest = extract_time_and_rest("завтра 8:00 проверь календарь")
    assert ok
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    assert iso == f"{tomorrow}T08:00:00+00:00"
    assert rest == "проверь календарь"


def test_extract_in_hours_with_prompt():
    ok, iso, rest = extract_time_and_rest("через 2 часа сделай отчёт")
    assert ok
    assert rest == "сделай отчёт"


def test_extract_weekday_with_prompt():
    ok, iso, rest = extract_time_and_rest("в пятницу 14:00 напомни про звонок")
    assert ok
    assert "T14:00:00" in iso
    assert rest == "напомни про звонок"


def test_extract_today_with_prompt():
    ok, iso, rest = extract_time_and_rest("сегодня 15:30 отзвонить Андрею")
    assert ok
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert iso == f"{today}T15:30:00+00:00"
    assert rest == "отзвонить Андрею"


def test_extract_morrow_after_with_prompt():
    ok, iso, rest = extract_time_and_rest("послезавтра 9:00 собрать статистику")
    assert ok
    after_tomorrow = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%d")
    assert iso == f"{after_tomorrow}T09:00:00+00:00"
    assert rest == "собрать статистику"


def test_extract_no_prompt_rejected():
    ok, _, _ = extract_time_and_rest("завтра 8:00")
    assert not ok  # нет задачи


def test_extract_empty_rejected():
    ok, err, rest = extract_time_and_rest("")
    assert not ok
    assert rest == ""


def test_extract_garbage_rejected():
    ok, err, rest = extract_time_and_rest("бла-бла-бла какая-то задача")
    assert not ok
    assert rest == ""
