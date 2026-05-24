"""Тесты timezone-корректности reminders: parse_time, add_reminder, get_due_reminders."""

import pytest
from datetime import datetime, timedelta, timezone
from tools import db


pytestmark = pytest.mark.usefixtures("isolated_cwd")


class TestTimeParseTZ:
    """parse_time возвращает ISO с +00:00."""

    def test_tomorrow_with_time_has_tz(self):
        from tools.time_parse import parse_time
        ok, iso = parse_time("завтра 8:00")
        assert ok
        assert "+00:00" in iso
        assert iso.endswith("+00:00")

    def test_in_hours_has_tz(self):
        from tools.time_parse import parse_time
        ok, iso = parse_time("через 2 часа")
        assert ok
        assert "+00:00" in iso

    def test_date_only_has_tz(self):
        from tools.time_parse import parse_time
        ok, iso = parse_time("2026-12-01")
        assert ok
        assert iso == "2026-12-01T09:00:00+00:00"

    def test_iso_without_tz_gets_moscow(self):
        from tools.time_parse import parse_time
        ok, iso = parse_time("2026-06-15T14:30:00")
        assert ok
        assert "+00:00" in iso


class TestTriggerNormalization:
    """_normalize_trigger добавляет +00:00 к naive строкам."""

    def test_naive_gets_moscow(self):
        result = db._normalize_trigger("2026-05-25T08:30:00")
        assert result == "2026-05-25T08:30:00+00:00"

    def test_already_with_tz_passes_through(self):
        result = db._normalize_trigger("2026-05-25T08:30:00+05:00")
        assert result == "2026-05-25T08:30:00+05:00"

    def test_utc_passes_through(self):
        result = db._normalize_trigger("2026-05-25T05:30:00+00:00")
        assert result == "2026-05-25T05:30:00+00:00"


class TestGetDueRemindersTZ:
    """get_due_reminders корректно сравнивает с UTC-now."""

    def test_msk_0830_is_due_when_utc_is_past_0530(self):
        """08:30 МСК = 05:30 UTC. Если сейчас > 05:30 UTC — запись due."""
        msk = "2020-01-01T08:30:00+00:00"  # давно в прошлом
        db.add_reminder("tg_tz_test", msk, "wake up")
        due = db.get_due_reminders()
        assert len(due) >= 1
        assert any(r["trigger_at"] == msk for r in due)

    def test_future_msk_not_due(self):
        """Завтра 08:30 МСК не должно срабатывать сейчас."""
        now_msk = datetime.now(timezone(timedelta(hours=3)))
        future = (now_msk + timedelta(days=1)).replace(hour=8, minute=30, second=0, microsecond=0)
        future_iso = future.isoformat()
        db.add_reminder("tg_tz_future", future_iso, "future task")
        due = db.get_due_reminders()
        assert not any(r["user_id"] == "tg_tz_future" for r in due)

    def test_old_naive_record_treated_as_msk(self):
        """Старая запись без TZ интерпретируется как МСК и считается due."""
        conn = db.get_conn()
        conn.execute(
            "INSERT INTO reminders (id, user_id, trigger_at, message, status, kind, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("old_naive", "tg_legacy", "2020-01-01T08:30:00", "old", "pending", "reminder", "2020-01-01"),
        )
        due = db.get_due_reminders()
        assert any(r["id"] == "old_naive" for r in due)
