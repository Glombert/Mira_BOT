"""tools/time_parse.py — парсер русскоязычных временных выражений.

Две функции:
- parse_time(text)  — СТРОГИЙ парсер: вся строка должна быть time-фразой,
                      иначе ok=False. Используется тестами и как
                      низкоуровневый строительный блок.
- extract_time_and_rest(text) — извлекает time-фразу из НАЧАЛА строки,
                                остаток отдаёт как promt. Используется
                                /task — пользователь пишет «завтра 8:00
                                проверь календарь».

Поддерживаемые формы:
  ISO:           "2026-06-15T14:30:00"
  дата:          "2026-12-01"           → дата + 09:00
  «завтра 8:00»  / «завтра в 8:00»     → завтра, время указано
  «завтра»                              → завтра 09:00 (без времени → default)
  «послезавтра 9:00»                    → послезавтра, время указано
  «через 2 часа»                        → now + 2 часа
  «через 30 минут»                      → now + 30 минут
  «в пятницу 14:00» / «пятница 14:00»  → ближайшая пятница 14:00
  «сегодня 15:30»                       → сегодня 15:30
"""

import re
from datetime import datetime, timedelta

WEEKDAYS = {
    "понедельник": 0, "вторник": 1, "среда": 2, "среду": 2,
    "четверг": 3, "пятница": 4, "пятницу": 4, "суббота": 5, "субботу": 5,
    "воскресенье": 6,
}

_ISO_RE       = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$")
_DATE_RE      = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HHMM_RE      = re.compile(r"^(\d{1,2}):(\d{2})$")
_REL_HOURS    = re.compile(r"^через\s+(\d+)\s+час(?:а|ов)?$", re.IGNORECASE)
_REL_MINUTES  = re.compile(r"^через\s+(\d+)\s+минут[уы]?$", re.IGNORECASE)

# Слова-метки дня: префикс time-фразы. Поиск через word-boundary,
# чтобы «послезавтра» не матчилось как «завтра».
_DAY_WORDS = ("сегодня", "завтра", "послезавтра")


def _maybe_time_suffix(text: str) -> tuple[int, int] | None:
    """Извлекает trailing «8:00» / «в 8:00» из конца строки. Возвращает (h, m) или None."""
    m = re.search(r"(?:^|\s)(?:в\s+)?(\d{1,2}):(\d{2})$", text)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2))
        if 0 <= h < 24 and 0 <= mi < 60:
            return h, mi
    return None


def parse_time(raw: str) -> tuple[bool, str]:
    """Строгий парсер. Вся строка должна быть time-фразой целиком."""
    text = raw.strip()
    if not text:
        return False, "пустая строка"

    # ISO pass-through (без .lower()!)
    if _ISO_RE.match(text):
        try:
            datetime.fromisoformat(text)
            return True, text
        except ValueError:
            pass

    # Дата YYYY-MM-DD
    if _DATE_RE.match(text):
        try:
            datetime.strptime(text, "%Y-%m-%d")
            return True, text + "T09:00:00"
        except ValueError:
            pass

    text_lo = text.lower()
    now = datetime.now()

    # «через N часов»
    m = _REL_HOURS.match(text_lo)
    if m:
        return True, (now + timedelta(hours=int(m.group(1)))).strftime("%Y-%m-%dT%H:%M:%S")

    # «через N минут»
    m = _REL_MINUTES.match(text_lo)
    if m:
        return True, (now + timedelta(minutes=int(m.group(1)))).strftime("%Y-%m-%dT%H:%M:%S")

    # «послезавтра [в] [hh:mm]»
    m = re.match(r"^послезавтра(?:\s+в)?(?:\s+(\d{1,2}):(\d{2}))?$", text_lo)
    if m:
        h = int(m.group(1)) if m.group(1) else 9
        mi = int(m.group(2)) if m.group(2) else 0
        target = now + timedelta(days=2)
        return True, target.strftime(f"%Y-%m-%dT{h:02d}:{mi:02d}:00")

    # «завтра [в] [hh:mm]»
    m = re.match(r"^завтра(?:\s+в)?(?:\s+(\d{1,2}):(\d{2}))?$", text_lo)
    if m:
        h = int(m.group(1)) if m.group(1) else 9
        mi = int(m.group(2)) if m.group(2) else 0
        target = now + timedelta(days=1)
        return True, target.strftime(f"%Y-%m-%dT{h:02d}:{mi:02d}:00")

    # «сегодня [в] hh:mm»  (без времени — нет смысла, отбрасываем)
    m = re.match(r"^сегодня(?:\s+в)?\s+(\d{1,2}):(\d{2})$", text_lo)
    if m:
        h = int(m.group(1)); mi = int(m.group(2))
        target = now.replace(hour=h, minute=mi, second=0, microsecond=0)
        return True, target.strftime("%Y-%m-%dT%H:%M:%S")

    # «[в] <день недели> [hh:mm]»
    for day_name, day_num in WEEKDAYS.items():
        # «в пятницу 14:00» / «пятница 14:00» / «пятницу 14:00»
        pat = rf"^(?:в\s+)?{day_name}(?:\s+(\d{{1,2}}):(\d{{2}}))?$"
        m = re.match(pat, text_lo)
        if m:
            h = int(m.group(1)) if m.group(1) else 9
            mi = int(m.group(2)) if m.group(2) else 0
            days_ahead = (day_num - now.weekday()) % 7 or 7  # сегодня этот день → след. неделя
            target = now + timedelta(days=days_ahead)
            return True, target.strftime(f"%Y-%m-%dT{h:02d}:{mi:02d}:00")

    return False, f"не понял время, попробуй формат: завтра 8:00 ... или 2026-06-01T09:00:00 (получил: {raw!r})"


def extract_time_and_rest(text: str) -> tuple[bool, str, str]:
    """Извлекает time-фразу из начала строки. Возвращает (ok, iso, remainder).

    Берёт САМЫЙ ДЛИННЫЙ префикс из 1..6 слов, который parse_time принимает,
    и оставляет НЕпустой остаток. Так «завтра 8:00 проверь календарь»
    отдаст iso=завтра 08:00 и remainder=«проверь календарь», а не
    iso=завтра 09:00 (одно слово «завтра») с лишней «8:00» в остатке.
    """
    text = text.strip()
    if not text:
        return False, "пустая строка", ""

    words = text.split()
    # Берём САМЫЙ ДЛИННЫЙ префикс, который parse_time принимает.
    # Если у него пустой остаток — значит строка целиком time-фраза
    # без задачи, отказ. Иначе iso + remainder.
    longest_iso = ""
    longest_remainder = ""
    found = False

    for n in range(1, min(len(words) + 1, 7)):
        candidate = " ".join(words[:n])
        ok_p, iso_or_err = parse_time(candidate)
        if not ok_p:
            continue
        longest_iso = iso_or_err
        longest_remainder = " ".join(words[n:]).strip()
        found = True

    if not found:
        return False, f"не понял время в начале строки, попробуй: завтра 8:00 твоя задача ... (получил: {text[:60]!r})", ""
    if not longest_remainder:
        return False, "после времени не указана задача (что сделать?)", ""

    return True, longest_iso, longest_remainder
