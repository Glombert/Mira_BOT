"""tools/time_parse.py — простой парсер русскоязычных временных выражений.

Поддерживает форматы:
  "завтра 8:00"    → завтра в указанное время
  "через 2 часа"   → через N часов от now
  "через 30 минут" → через N минут
  "2026-06-01T09:00:00" → ISO (pass-through)
  "2026-06-01"     → дата + 09:00
  "в пятницу 14:00" → ближайшая пятница
"""

from datetime import datetime, timedelta

WEEKDAYS = {
    "понедельник": 0, "вторник": 1, "среда": 2,
    "четверг": 3, "пятница": 4, "суббота": 5, "воскресенье": 6,
}
WEEKDAY_RU = [
    "понедельник", "вторник", "среда", "четверг",
    "пятница", "суббота", "воскресенье",
]


def parse_time(raw: str) -> tuple[bool, str]:
    """Парсит строку времени. Возвращает (ok, iso_or_error).

    ok=True  → "2026-06-01T09:00:00"
    ok=False → "не понял время, попробуй формат: завтра 8:00 ..."
    """
    text = raw.strip().lower()
    now = datetime.now()

    # ISO pass-through
    if "T" in text and len(text) >= 16:
        try:
            datetime.fromisoformat(text)
            return True, text
        except ValueError:
            pass

    # Дата без времени: 2026-06-01
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        try:
            datetime.strptime(text, "%Y-%m-%d")
            return True, text + "T09:00:00"
        except ValueError:
            pass

    hour = 9
    minute = 0
    time_str = ""
    # Извлекаем время если есть (чч:мм)
    import re
    tm = re.search(r"(\d{1,2}):(\d{2})", text)
    if tm:
        hour = int(tm.group(1))
        minute = int(tm.group(2))
        time_str = f"{hour:02d}:{minute:02d}"

    # "через N часов"
    m = re.search(r"через\s+(\d+)\s+час", text)
    if m and time_str:
        # "через 2 часа 8:00" не имеет смысла — игнорируем
        pass
    if m and not time_str:
        target = now + timedelta(hours=int(m.group(1)))
        return True, target.strftime("%Y-%m-%dT%H:%M:%S")

    # "через N минут"
    m = re.search(r"через\s+(\d+)\s+минут", text)
    if m and not time_str:
        target = now + timedelta(minutes=int(m.group(1)))
        return True, target.strftime("%Y-%m-%dT%H:%M:%S")

    # "завтра [чч:мм]"
    if "завтра" in text:
        target = now + timedelta(days=1)
        return True, target.strftime(f"%Y-%m-%dT{hour:02d}:{minute:02d}:00")

    # "послезавтра [чч:мм]"
    if "послезавтра" in text:
        target = now + timedelta(days=2)
        return True, target.strftime(f"%Y-%m-%dT{hour:02d}:{minute:02d}:00")

    # "в <день недели> [чч:мм]"
    for day_name, day_num in WEEKDAYS.items():
        if day_name in text:
            days_ahead = (day_num - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7  # сегодня → следующая неделя
            target = now + timedelta(days=days_ahead)
            return True, target.strftime(f"%Y-%m-%dT{hour:02d}:{minute:02d}:00")

    # "сегодня [чч:мм]"
    if "сегодня" in text or not any(k in text for k in ("завтра", "через", "послезавтра")):
        if time_str:
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return True, target.strftime("%Y-%m-%dT%H:%M:%S")

    return False, f"не понял время, попробуй формат: завтра 8:00 ... или 2026-06-01T09:00:00 (получил: {raw!r})"


def extract_time_and_rest(text: str) -> tuple[bool, str, str]:
    """Извлекает time-фразу из начала строки. Возвращает (ok, iso, remainder).

    Перебирает префиксы из 1, 2, 3, 4 слов, ищет ПОСЛЕДНИЙ ok-префикс.
    Остаток — промпт для задачи.

    Форматы на входе:
      \"завтра 8:00 проверь календарь\"
      \"через 2 часа сделай отчёт\"
      \"в пятницу 14:00 напомни про звонок\"
      \"сегодня 15:30 отзвонить Андрею\"
    """
    text = text.strip()
    if not text:
        return False, "пустая строка", ""

    words = text.split()
    best_iso = ""
    best_end = 0  # конец time-фразы в исходной строке

    for n in range(1, min(len(words) + 1, 5)):
        candidate = " ".join(words[:n])
        ok_p, iso_or_err = parse_time(candidate)
        if ok_p:
            # Найти эту фразу в исходном тексте и взять позицию после неё
            idx = text.find(candidate)
            if idx != -1:
                best_iso = iso_or_err
                best_end = idx + len(candidate)

    if not best_iso:
        return False, f"не понял время в начале строки, попробуй: завтра 8:00 твоя задача ... (получил: {text[:60]!r})", ""

    remainder = text[best_end:].strip()
    if not remainder:
        return False, "после времени не указана задача (что сделать?)", ""

    return True, best_iso, remainder
