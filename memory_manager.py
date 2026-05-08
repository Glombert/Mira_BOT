"""
memory_manager.py — долгосрочная память Миры.

Решает главную проблему: окно контекста ограничено 40 сообщениями.
Без этого модуля Мира «забывает» всё что было раньше.

Что делает:
  1. maybe_summarize() — когда история длинная, сжимает старые сообщения
     в текстовое резюме и сохраняет в профиле. Сессия остаётся компактной.
  2. update_user_profile() — извлекает новые факты о пользователе из диалога
     и дополняет его профиль (имя, чем занимается, предпочтения).
  3. get_summary() / save_summary() — хранит резюме в поле profile[summary].

Резюме включается в системный промпт при каждой загрузке сессии — Мира
помнит важное из прошлых разговоров даже если сами сообщения уже вытеснены.
"""

import os
import json
import logging
import threading
import providers as _providers

logger = logging.getLogger("Ouroborus")

SUMMARY_TRIGGER = 30   # сжимаем когда не-системных сообщений больше этого
KEEP_RECENT     = 15   # сколько последних сообщений оставляем дословно
SUMMARY_MAX_TOKENS = 500


# ---------------------------------------------------------------------------
# Публичные функции
# ---------------------------------------------------------------------------

def maybe_summarize(user_id: str, msgs: list, model_chain: list,
                    load_profile_fn, save_profile_fn) -> list:
    """
    Проверяет нужна ли суммаризация и выполняет её при необходимости.

    Если история длиннее SUMMARY_TRIGGER:
      - берёт старые сообщения
      - вызывает LLM чтобы обновить накопленное резюме
      - сохраняет резюме в профиле
      - возвращает укороченную историю (только свежие сообщения)

    Если история короче порога — возвращает msgs без изменений.
    """
    system_msgs  = [m for m in msgs if m["role"] == "system"]
    non_system   = [m for m in msgs if m["role"] != "system"]

    if len(non_system) <= SUMMARY_TRIGGER:
        return msgs

    to_summarize = non_system[:-KEEP_RECENT]
    to_keep      = non_system[-KEEP_RECENT:]

    existing = get_summary(user_id, load_profile_fn)

    dialog_text = "\n".join(
        f"{m['role'].upper()}: {str(m.get('content', ''))[:400]}"
        for m in to_summarize
        if isinstance(m.get("content"), str) and m["role"] in ("user", "assistant")
    )
    if not dialog_text.strip():
        return msgs

    prompt = (
        f"Обнови краткое резюме разговора новой информацией.\n\n"
        f"Текущее резюме:\n{existing or 'Нет'}\n\n"
        f"Новые сообщения:\n{dialog_text}\n\n"
        "Напиши ТОЛЬКО обновлённое резюме (не более 250 слов). "
        "Сохраняй: кто пользователь, над чем работает, важные предпочтения, ключевые факты. "
        "Не добавляй оформление, просто текст."
    )

    try:
        response = _providers.call(
            model_chain,
            [{"role": "user", "content": prompt}],
            max_tokens=SUMMARY_MAX_TOKENS,
            temperature=0.3,
        )
        new_summary = response.choices[0].message.content.strip()
        save_summary(user_id, new_summary, load_profile_fn, save_profile_fn)
        logger.info(f"memory_manager: резюме обновлено для {user_id} "
                    f"({len(to_summarize)} сообщений свёрнуто)")
    except Exception as e:
        logger.warning(f"memory_manager: не удалось обновить резюме: {e}")
        return msgs  # при ошибке не трогаем историю

    return system_msgs + to_keep


def update_user_profile(user_id: str, msgs: list, model_chain: list,
                        load_profile_fn, save_profile_fn) -> None:
    """
    Извлекает факты о пользователе из последних сообщений и дополняет профиль.
    Вызывается в фоновом потоке — не блокирует ответ.

    Обновляет только поля about, preferences, domain — не трогает служебные.
    """
    non_system = [
        m for m in msgs
        if m["role"] in ("user", "assistant") and isinstance(m.get("content"), str)
    ]
    if len(non_system) < 4:
        return  # слишком мало для извлечения фактов

    recent = non_system[-10:]
    dialog = "\n".join(f"{m['role'].upper()}: {m['content'][:300]}" for m in recent)

    profile = load_profile_fn(user_id)
    if not profile:
        return

    current_about = json.dumps(profile.get("about", {}), ensure_ascii=False)

    prompt = (
        f"Из диалога извлеки новые факты о пользователе.\n\n"
        f"Текущие данные профиля: {current_about}\n\n"
        f"Диалог:\n{dialog}\n\n"
        "Верни JSON только с теми полями которые стоит обновить или добавить. "
        "Допустимые поля: role (профессия), project (над чем работает), "
        "communication_style (как предпочитает общаться), interests (интересы), "
        "location (где находится). "
        "Если новых данных нет — верни пустой JSON: {}\n"
        "Только JSON, без пояснений."
    )

    try:
        response = _providers.call(
            model_chain,
            [{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.1,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = "\n".join(l for l in raw.splitlines() if not l.strip().startswith("```"))
        updates = json.loads(raw)
        if updates:
            about = profile.setdefault("about", {})
            about.update(updates)
            save_profile_fn(user_id, profile)
            logger.info(f"memory_manager: профиль обновлён для {user_id}: {list(updates.keys())}")
    except Exception as e:
        logger.debug(f"memory_manager: не удалось обновить профиль: {e}")


def get_summary(user_id: str, load_profile_fn) -> str:
    """Возвращает накопленное резюме из профиля пользователя."""
    profile = load_profile_fn(user_id)
    if not profile:
        return ""
    return profile.get("conversation_summary", "") or ""


def save_summary(user_id: str, summary: str,
                 load_profile_fn, save_profile_fn) -> None:
    """Сохраняет резюме в профиле пользователя."""
    profile = load_profile_fn(user_id)
    if not profile:
        return
    profile["conversation_summary"] = summary
    save_profile_fn(user_id, profile)


def run_background(fn, *args) -> None:
    """Запускает функцию в фоновом потоке."""
    threading.Thread(target=fn, args=args, daemon=True).start()


# ---------------------------------------------------------------------------
# Шаблоны задач
# ---------------------------------------------------------------------------

TEMPLATES_DIR = os.path.join("memory", "templates")


def _templates_path(user_id: str) -> str:
    path = os.path.join(TEMPLATES_DIR, user_id)
    os.makedirs(path, exist_ok=True)
    return path


def save_template(user_id: str, name: str, description: str, example: str) -> dict:
    """
    Сохраняет шаблон повторяющейся задачи.

    name        — короткое имя (slug), например "перевод_текста"
    description — что делает этот шаблон
    example     — типичный запрос пользователя для этой задачи
    """
    name = name.strip().replace(" ", "_").lower()[:40]
    if not name:
        return {"ok": False, "error": "Имя шаблона не может быть пустым"}

    template = {
        "name":        name,
        "description": description.strip()[:300],
        "example":     example.strip()[:300],
        "created_at":  __import__("datetime").datetime.now().strftime("%Y-%m-%d"),
    }
    path = os.path.join(_templates_path(user_id), f"{name}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(template, f, ensure_ascii=False, indent=2)
        logger.info(f"memory_manager: шаблон '{name}' сохранён для {user_id}")
        return {"ok": True, "name": name, "path": path}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_templates(user_id: str) -> dict:
    """Возвращает список шаблонов пользователя."""
    dir_path = _templates_path(user_id)
    templates = []
    for fname in sorted(os.listdir(dir_path)):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(dir_path, fname), encoding="utf-8") as f:
                t = json.load(f)
            templates.append({
                "name":        t.get("name", fname[:-5]),
                "description": t.get("description", ""),
                "example":     t.get("example", ""),
            })
        except Exception:
            pass
    return {"ok": True, "templates": templates, "count": len(templates)}


def get_templates_prompt(user_id: str) -> str:
    """
    Возвращает текст для системного промпта с шаблонами пользователя.
    Пустая строка если шаблонов нет.
    """
    result = list_templates(user_id)
    templates = result.get("templates", [])
    if not templates:
        return ""
    lines = [f"— {t['name']}: {t['description']}" for t in templates]
    return "Сохранённые шаблоны задач пользователя:\n" + "\n".join(lines)
