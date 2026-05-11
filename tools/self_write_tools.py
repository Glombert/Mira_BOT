"""
tools/self_write_tools.py — инструмент для обновления персоны Миры.

Мира может изменять только «мягкие» поля persona.json:
  notes, curiosity, emotions, self_awareness, reflections.

«Жёсткие» поля (boundaries, formatting, core, name) — заблокированы.
Каждое изменение: бэкап + запись в decisions.log + уведомление владельцу.
"""

import os
import json
import shutil
from datetime import datetime

PERSONA_FILE     = "persona.json"
REFLECTIONS_FILE = os.path.join("memory", "reflections.json")
DECISIONS_LOG    = os.path.join("memory", "decisions.log")

# Поля которые Мира может менять самостоятельно
_ALLOWED_FIELDS = {"curiosity", "emotions", "self_awareness", "reflections"}

# Поля которые менять нельзя — они установлены человеком намеренно
_LOCKED_FIELDS  = {"name", "core", "boundaries", "formatting"}


def write_persona(field: str, value) -> dict:
    """
    Обновляет одно поле persona.json.

    Разрешённые поля: notes, curiosity, emotions, self_awareness, reflections.
    Заблокированные: name, core, boundaries, formatting.

    Для reflections можно передать строку — она добавится к списку с датой.
    Для остальных полей значение заменяется целиком.

    Каждое изменение фиксируется в decisions.log.
    """
    if field in _LOCKED_FIELDS:
        return {
            "ok": False,
            "error": f"Поле '{field}' нельзя изменять — оно задано человеком. "
                     f"Изменяемые поля: {', '.join(sorted(_ALLOWED_FIELDS))}",
        }

    if field not in _ALLOWED_FIELDS:
        return {
            "ok": False,
            "error": f"Неизвестное поле '{field}'. "
                     f"Изменяемые поля: {', '.join(sorted(_ALLOWED_FIELDS))}",
        }

    # Reflections живут отдельно — в memory/reflections.json,
    # чтобы не конфликтовать с git-tracked persona.json при деплое.
    if field == "reflections":
        return _append_reflection(value)

    if not os.path.exists(PERSONA_FILE):
        return {"ok": False, "error": "persona.json не найден"}

    try:
        with open(PERSONA_FILE, "r", encoding="utf-8") as f:
            persona = json.load(f)
    except Exception as e:
        return {"ok": False, "error": f"Ошибка чтения: {e}"}

    # Бэкап перед изменением
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join("versions", "persona")
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, f"persona_{ts}.json")
    shutil.copy2(PERSONA_FILE, backup_path)

    old_value = persona.get(field)
    persona[field] = value
    new_value = value

    try:
        with open(PERSONA_FILE, "w", encoding="utf-8") as f:
            json.dump(persona, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return {"ok": False, "error": f"Ошибка записи: {e}"}

    # Лог
    _log_persona_change(field, old_value, new_value, backup_path)

    # Уведомление владельцу
    _notify_persona_change(field, new_value)

    return {
        "ok": True,
        "field": field,
        "backup": backup_path,
        "note": "Изменение вступит в силу при следующем сообщении (персона перечитывается).",
    }


def _append_reflection(text) -> dict:
    """Добавляет рефлексию в memory/reflections.json (git-untracked)."""
    os.makedirs("memory", exist_ok=True)
    entry = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "text": str(text),
    }
    # Читаем существующий список (или создаём)
    reflections = []
    if os.path.exists(REFLECTIONS_FILE):
        try:
            with open(REFLECTIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                reflections = data
        except Exception:
            pass

    reflections.append(entry)
    try:
        with open(REFLECTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(reflections, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return {"ok": False, "error": f"Ошибка записи рефлексии: {e}"}

    _log_persona_change("reflections", None, entry, REFLECTIONS_FILE)
    _notify_persona_change("reflections", entry)
    return {
        "ok":   True,
        "field": "reflections",
        "file":  REFLECTIONS_FILE,
        "note":  "Рефлексия сохранена. Видна в следующем сообщении.",
    }


def _log_persona_change(field: str, old_value, new_value, backup_path: str) -> None:
    os.makedirs("memory", exist_ok=True)
    entry = {
        "ts":     datetime.now().isoformat(),
        "event":  "persona_self_update",
        "field":  field,
        "backup": backup_path,
    }
    try:
        with open(DECISIONS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _notify_persona_change(field: str, new_value) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    owner = os.getenv("OWNER_TELEGRAM_ID", "")
    if not token or not owner:
        return
    try:
        import urllib.request, urllib.parse, threading

        preview = str(new_value)[:200]
        text = (
            f"🌟 Мира обновила персону\n"
            f"Поле: {field}\n"
            f"Значение: {preview}"
        )

        def send():
            try:
                data = urllib.parse.urlencode({"chat_id": owner, "text": text}).encode()
                urllib.request.urlopen(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    data=data, timeout=5,
                )
            except Exception:
                pass

        threading.Thread(target=send, daemon=True).start()
    except Exception:
        pass
