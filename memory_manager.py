"""
memory_manager.py — долгосрочная память Миры.

Решает главную проблему: окно контекста ограничено 40 сообщениями.
Без этого модуля Мира «забывает» всё что было раньше.

Архитектура памяти:
  1. maybe_summarize() — когда история длинная, сжимает старые сообщения
     в структурированное резюме. Порог: 20 сообщений.
  2. update_user_profile() — извлекает факты о пользователе и его активных
     задачах, дополняет профиль.
  3. get_summary() / save_summary() — резюме хранится в profile[conversation_summary].

Резюме включается в системный промпт при каждой загрузке — Мира помнит
важный контекст из прошлых разговоров.

Структура резюме:
  КТО: кто пользователь, профессия/роль
  ПРОЕКТЫ: активные задачи и проекты
  ПРЕДПОЧТЕНИЯ: стиль общения, что важно
  КЛЮЧЕВЫЕ ФАКТЫ: решения, договорённости, важные моменты
  ТЕКУЩЕЕ: над чем работаем прямо сейчас
"""

import os
import json
import logging
import threading
import providers as _providers

logger = logging.getLogger("Ouroborus")

SUMMARY_TRIGGER    = 20    # сжимаем когда не-системных сообщений больше этого
KEEP_RECENT        = 10    # сколько последних оставляем дословно
SUMMARY_MAX_TOKENS = 900   # токенов на резюме
PROFILE_UPDATE_MIN = 6     # минимум сообщений для обновления профиля


# ---------------------------------------------------------------------------
# Суммаризация
# ---------------------------------------------------------------------------

def maybe_summarize(user_id: str, msgs: list, model_chain: list,
                    load_profile_fn, save_profile_fn) -> list:
    """
    Если история длиннее SUMMARY_TRIGGER — сжимает старые сообщения в резюме.
    Резюме структурированное: кто / проекты / факты / текущее.
    При ошибке возвращает msgs без изменений.
    """
    system_msgs = [m for m in msgs if m["role"] == "system"]
    non_system  = [m for m in msgs if m["role"] != "system"]

    if len(non_system) <= SUMMARY_TRIGGER:
        return msgs

    to_summarize = non_system[:-KEEP_RECENT]
    to_keep      = non_system[-KEEP_RECENT:]

    existing = get_summary(user_id, load_profile_fn)

    dialog_text = "\n".join(
        f"{m['role'].upper()}: {str(m.get('content', ''))[:500]}"
        for m in to_summarize
        if isinstance(m.get("content"), str) and m["role"] in ("user", "assistant")
    )
    if not dialog_text.strip():
        return msgs

    existing_block = f"Текущее резюме:\n{existing}\n\n" if existing else ""

    prompt = (
        "Ты система управления памятью ИИ-ассистента. "
        "Обнови структурированное резюме разговора, добавив новую информацию.\n\n"
        f"{existing_block}"
        f"Новые сообщения:\n{dialog_text}\n\n"
        "Напиши обновлённое резюме СТРОГО в формате (без лишних слов):\n\n"
        "КТО: [имя, кто такой, профессия/роль]\n"
        "ПРОЕКТЫ: [активные задачи и проекты прямо сейчас]\n"
        "ПРЕДПОЧТЕНИЯ: [стиль общения, что важно, что не нравится]\n"
        "КЛЮЧЕВЫЕ ФАКТЫ: [важные решения, договорённости, технические детали]\n"
        "ТЕКУЩЕЕ: [незакрытые вопросы, над чем работаем]\n\n"
        "Максимум 500 слов. Только факты из разговора, не придумывай."
    )

    try:
        response = _providers.call(
            model_chain,
            [{"role": "user", "content": prompt}],
            max_tokens=SUMMARY_MAX_TOKENS,
            temperature=0.2,
        )
        new_summary = response.choices[0].message.content.strip()
        save_summary(user_id, new_summary, load_profile_fn, save_profile_fn)
        logger.info(
            f"memory_manager: резюме обновлено для {user_id} "
            f"({len(to_summarize)} сообщений → {len(new_summary)} символов)"
        )
    except Exception as e:
        logger.warning(f"memory_manager: не удалось обновить резюме: {e}")
        return msgs

    return system_msgs + to_keep


# ---------------------------------------------------------------------------
# Обновление профиля
# ---------------------------------------------------------------------------

def update_user_profile(user_id: str, msgs: list, model_chain: list,
                        load_profile_fn, save_profile_fn) -> None:
    """
    Извлекает факты о пользователе из диалога и дополняет профиль.
    Работает в фоновом потоке.
    """
    non_system = [
        m for m in msgs
        if m["role"] in ("user", "assistant") and isinstance(m.get("content"), str)
    ]
    if len(non_system) < PROFILE_UPDATE_MIN:
        return

    # Берём последние 16 сообщений для анализа
    recent = non_system[-16:]
    dialog = "\n".join(
        f"{m['role'].upper()}: {m['content'][:400]}" for m in recent
    )

    profile = load_profile_fn(user_id)
    if not profile:
        return

    current = json.dumps({
        "name":  profile.get("name", ""),
        "about": profile.get("about", {}),
    }, ensure_ascii=False)

    prompt = (
        f"Из диалога извлеки новые факты о пользователе.\n\n"
        f"Текущий профиль: {current}\n\n"
        f"Диалог:\n{dialog}\n\n"
        "Верни JSON только с новыми или изменившимися данными. "
        "Поля (добавляй только те, о которых есть чёткая информация из диалога):\n"
        "  name — как его зовут\n"
        "  role — профессия / чем занимается\n"
        "  project — главный текущий проект\n"
        "  communication_style — как предпочитает общаться\n"
        "  interests — интересы и темы\n"
        "  important_note — важная персональная заметка\n\n"
        "Если ничего нового нет — верни {}. Только JSON, без пояснений."
    )

    try:
        response = _providers.call(
            model_chain,
            [{"role": "user", "content": prompt}],
            max_tokens=250,
            temperature=0.1,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = "\n".join(l for l in raw.splitlines() if not l.strip().startswith("```"))
        updates = json.loads(raw)
        if not updates:
            return

        changed = False
        # Обновляем имя напрямую
        if "name" in updates and updates["name"] and not profile.get("name"):
            profile["name"] = updates["name"]
            changed = True
            updates.pop("name")

        # Остальное — в about
        if updates:
            about = profile.setdefault("about", {})
            for k, v in updates.items():
                if v and v != about.get(k):
                    about[k] = v
                    changed = True

        if changed:
            save_profile_fn(user_id, profile)
            logger.info(
                f"memory_manager: профиль обновлён для {user_id}: {list(updates.keys())}"
            )
    except Exception as e:
        logger.debug(f"memory_manager: не удалось обновить профиль: {e}")


# ---------------------------------------------------------------------------
# Хранение резюме
# ---------------------------------------------------------------------------

def get_summary(user_id: str, load_profile_fn) -> str:
    """Возвращает накопленное резюме из профиля."""
    profile = load_profile_fn(user_id)
    if not profile:
        return ""
    return profile.get("conversation_summary", "") or ""


def save_summary(user_id: str, summary: str,
                 load_profile_fn, save_profile_fn) -> None:
    """Сохраняет резюме в профиле."""
    profile = load_profile_fn(user_id)
    if not profile:
        return
    profile["conversation_summary"] = summary
    save_profile_fn(user_id, profile)


def get_templates_prompt(user_id: str) -> str:
    """Возвращает текст для системного промпта с шаблонами задач."""
    dir_path = os.path.join("memory", "templates", user_id)
    if not os.path.isdir(dir_path):
        return ""
    templates = []
    for fname in sorted(os.listdir(dir_path)):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(dir_path, fname), encoding="utf-8") as f:
                t = json.load(f)
            templates.append(f"— {t.get('name', '')}: {t.get('description', '')}")
        except Exception:
            pass
    if not templates:
        return ""
    return "Сохранённые шаблоны задач:\n" + "\n".join(templates)


def save_template(user_id: str, name: str, description: str, example: str) -> dict:
    """Сохраняет шаблон повторяющейся задачи."""
    name = name.strip().replace(" ", "_").lower()[:40]
    if not name:
        return {"ok": False, "error": "Имя шаблона не может быть пустым"}
    from datetime import datetime
    template = {
        "name": name,
        "description": description.strip()[:300],
        "example": example.strip()[:300],
        "created_at": datetime.now().strftime("%Y-%m-%d"),
    }
    path = os.path.join("memory", "templates", user_id)
    os.makedirs(path, exist_ok=True)
    fpath = os.path.join(path, f"{name}.json")
    try:
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(template, f, ensure_ascii=False, indent=2)
        logger.info(f"memory_manager: шаблон '{name}' сохранён для {user_id}")
        return {"ok": True, "name": name, "path": fpath}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_templates(user_id: str) -> dict:
    """Возвращает список шаблонов пользователя."""
    dir_path = os.path.join("memory", "templates", user_id)
    templates = []
    if os.path.isdir(dir_path):
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


def run_background(fn, *args) -> None:
    """Запускает функцию в фоновом потоке."""
    threading.Thread(target=fn, args=args, daemon=True).start()
