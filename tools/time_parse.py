"""tools/time_parse.py — парсер русскоязычных временных выражений.

Архитектура: storage — всегда UTC. Юзер пишет «завтра 8:00» имея в виду
СВОЁ локальное время; парсер интерпретирует фразу в зоне пользователя
(user_tz, IANA-имя), возвращает ISO в UTC.

Две функции:
- parse_time(text, user_tz='UTC')           — строгий парсер
- extract_time_and_rest(text, user_tz='UTC') — отделяет time-фразу от promt
"""

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


WEEKDAYS = {
    "понедельник": 0, "вторник": 1, "среда": 2, "среду": 2,
    "четверг": 3, "пятница": 4, "пятницу": 4, "суббота": 5, "субботу": 5,
    "воскресенье": 6,
}

_ISO_RE       = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:[+\-]\d{2}:\d{2}|Z)?$")
_DATE_RE      = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_REL_HOURS    = re.compile(r"^через\s+(\d+)\s+час(?:а|ов)?$", re.IGNORECASE)
_REL_MINUTES  = re.compile(r"^через\s+(\d+)\s+минут[уы]?$", re.IGNORECASE)


def _tz(name: str):
    """Безопасно превращает IANA-имя в tzinfo. Fallback UTC."""
    if not name or name.upper() == "UTC":
        return timezone.utc
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return timezone.utc


def _utc_iso(dt: datetime) -> str:
    """datetime → ISO в UTC."""
    if dt.tzinfo is None:
        # niave интерпретируем как UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def parse_time(raw: str, user_tz: str = "UTC") -> tuple[bool, str]:
    """Строгий парсер. Возвращает (ok, iso_in_UTC_or_error).

    Все «голые» времена («завтра 8:00») интерпретируются в зоне user_tz.
    Результат всегда возвращается в UTC.
    """
    text = raw.strip()
    if not text:
        return False, "пустая строка"

    tz = _tz(user_tz)

    # ISO pass-through (без .lower()!)
    if _ISO_RE.match(text):
        try:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz)
            return True, _utc_iso(dt)
        except ValueError:
            pass

    # Дата YYYY-MM-DD → 09:00 в user_tz
    if _DATE_RE.match(text):
        try:
            dt = datetime.strptime(text, "%Y-%m-%d").replace(hour=9, minute=0, tzinfo=tz)
            return True, _utc_iso(dt)
        except ValueError:
            pass

    text_lo = text.lower()
    # now в зоне пользователя — относительные термины («завтра» и т.п.)
    # считаются от «локального» дня пользователя, не сервера.
    now = datetime.now(tz)

    # «через N часов»  — UTC-нейтрально, зона не нужна
    m = _REL_HOURS.match(text_lo)
    if m:
        return True, _utc_iso(now + timedelta(hours=int(m.group(1))))

    # «через N минут»
    m = _REL_MINUTES.match(text_lo)
    if m:
        return True, _utc_iso(now + timedelta(minutes=int(m.group(1))))

    # «послезавтра [в] [hh:mm]»
    m = re.match(r"^послезавтра(?:\s+в)?(?:\s+(\d{1,2}):(\d{2}))?$", text_lo)
    if m:
        h = int(m.group(1)) if m.group(1) else 9
        mi = int(m.group(2)) if m.group(2) else 0
        target = (now + timedelta(days=2)).replace(hour=h, minute=mi, second=0, microsecond=0)
        return True, _utc_iso(target)

    # «завтра [в] [hh:mm]»
    m = re.match(r"^завтра(?:\s+в)?(?:\s+(\d{1,2}):(\d{2}))?$", text_lo)
    if m:
        h = int(m.group(1)) if m.group(1) else 9
        mi = int(m.group(2)) if m.group(2) else 0
        target = (now + timedelta(days=1)).replace(hour=h, minute=mi, second=0, microsecond=0)
        return True, _utc_iso(target)

    # «сегодня [в] hh:mm»
    m = re.match(r"^сегодня(?:\s+в)?\s+(\d{1,2}):(\d{2})$", text_lo)
    if m:
        h = int(m.group(1)); mi = int(m.group(2))
        target = now.replace(hour=h, minute=mi, second=0, microsecond=0)
        return True, _utc_iso(target)

    # «[в] <день недели> [hh:mm]»
    for day_name, day_num in WEEKDAYS.items():
        pat = rf"^(?:в\s+)?{day_name}(?:\s+(\d{{1,2}}):(\d{{2}}))?$"
        m = re.match(pat, text_lo)
        if m:
            h = int(m.group(1)) if m.group(1) else 9
            mi = int(m.group(2)) if m.group(2) else 0
            days_ahead = (day_num - now.weekday()) % 7 or 7
            target = (now + timedelta(days=days_ahead)).replace(
                hour=h, minute=mi, second=0, microsecond=0)
            return True, _utc_iso(target)

    return False, (f"не понял время, попробуй: завтра 8:00 ... или 2026-06-01T09:00:00 "
                   f"(получил: {raw!r})")


def extract_time_and_rest(text: str, user_tz: str = "UTC") -> tuple[bool, str, str]:
    """Извлекает time-фразу из начала строки. Возвращает (ok, iso_in_UTC, remainder).

    Берёт САМЫЙ ДЛИННЫЙ префикс из 1..6 слов, который parse_time принимает,
    при условии что после него остаётся непустая «задача».
    """
    text = text.strip()
    if not text:
        return False, "пустая строка", ""

    words = text.split()
    longest_iso = ""
    longest_remainder = ""
    found = False

    for n in range(1, min(len(words) + 1, 7)):
        candidate = " ".join(words[:n])
        ok_p, iso_or_err = parse_time(candidate, user_tz)
        if not ok_p:
            continue
        longest_iso = iso_or_err
        longest_remainder = " ".join(words[n:]).strip()
        found = True

    if not found:
        return False, (f"не понял время в начале строки, попробуй: завтра 8:00 твоя задача ... "
                       f"(получил: {text[:60]!r})"), ""
    if not longest_remainder:
        return False, "после времени не указана задача (что сделать?)", ""

    return True, longest_iso, longest_remainder
