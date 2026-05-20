"""Тесты для tools/rituals.py — загрузка, парсинг важности, фильтр."""

import json
import os
import pytest
from tools.rituals import load_rituals, parse_importance, should_notify


class TestLoadRituals:
    def test_loads_all_rituals(self):
        rituals = load_rituals()
        names = {r["name"] for r in rituals}
        assert "self_review" in names
        assert "server_health" in names
        assert "weekly_summary" in names
        assert len(rituals) >= 3

    def test_every_ritual_has_required_fields(self):
        for r in load_rituals():
            assert "name" in r
            assert "schedule" in r
            assert "prompt" in r
            assert "agent" in r
            assert "notify_threshold" in r


class TestParseImportance:
    def test_parses_major(self):
        assert parse_importance("blah #IMPORTANCE: MAJOR blah") == "MAJOR"

    def test_parses_minor(self):
        assert parse_importance("text #IMPORTANCE: MINOR") == "MINOR"

    def test_parses_critical(self):
        assert parse_importance("#IMPORTANCE: CRITICAL\nrest") == "CRITICAL"

    def test_parses_none(self):
        assert parse_importance("#IMPORTANCE: NONE") == "NONE"

    def test_case_insensitive(self):
        assert parse_importance("#importance: major done") == "MAJOR"

    def test_no_marker_returns_none(self):
        assert parse_importance("обычный ответ без маркера") == "NONE"

    def test_empty_string(self):
        assert parse_importance("") == "NONE"


class TestShouldNotify:
    def test_major_meets_major_threshold(self):
        assert should_notify("MAJOR", "MAJOR") is True

    def test_minor_below_major_threshold(self):
        assert should_notify("MINOR", "MAJOR") is False

    def test_critical_above_all(self):
        assert should_notify("CRITICAL", "NONE") is True

    def test_major_above_minor(self):
        assert should_notify("MAJOR", "MINOR") is True

    def test_none_never_notifies(self):
        assert should_notify("NONE", "NONE") is True  # NONE >= NONE
        assert should_notify("NONE", "MINOR") is False
