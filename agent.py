# Mira — Ouroboros agent
import os
import re
import ast
import sys
import json
import time
import shutil
import argparse
import subprocess
import tempfile
import logging
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from dotenv import load_dotenv
from tools import undo_last, list_undo
import memory_crypto
from tools.git_tools   import sync_with_git, ensure_dev_branch, release_to_main
from tools.cloud_tools import cloud_sync, cloud_restore
from tools.access_tools import (
    get_status, set_status, list_users, approve, reject, block, unblock,
    blacklist, unblacklist, delete_user,
    increment_guest_counter, cleanup_expired_guests,
    notify_owner, notify_new_user,
    should_notify_blacklisted, mark_blacklist_notified,
    increment_evolution, get_evolution_stats,
    GUEST_LIMIT,
)
import providers as _providers
from router   import classify
from conclave import Conclave

# ---------------------------------------------------------------------------
# Настройка логирования
# ---------------------------------------------------------------------------
logger = logging.getLogger("Ouroboros")
logger.setLevel(logging.INFO)
# propagate=False — чтобы наш handler был единственным владельцем agent.log,
# а basicConfig из telegram_bot не дублировал записи в свой файл.
logger.propagate = False

from tools.paths import at_root

os.makedirs(at_root("logs"), exist_ok=True)
log_handler = TimedRotatingFileHandler(
    at_root("logs", "agent.log"),
    when="midnight",
    interval=1,
    backupCount=3,
    encoding="utf-8",
)
log_handler.suffix = "%Y-%m-%d"
log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(log_handler)

# ---------------------------------------------------------------------------
# Аргументы командной строки
#
# Примеры запуска:
#   python agent.py                   — профиль default
#   python agent.py --profile dev     — профиль разработчика
#   python agent.py --self-test       — внутренний smoke-test, не для людей
# ---------------------------------------------------------------------------
_script_dir = os.path.dirname(os.path.abspath(__file__))

def _read_default_profile() -> str:
    """Читает профиль из файла .profile рядом с agent.py. Иначе — default."""
    try:
        with open(os.path.join(_script_dir, ".profile"), "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "default"

_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--self-test", action="store_true")
_parser.add_argument("--profile", default=_read_default_profile())
_parser.add_argument("--user", default="")
_args, _ = _parser.parse_known_args()

if _args.self_test:
    print("OK")
    sys.exit(0)

logger.info("=== Запуск агента Ouroboros ===")

# ---------------------------------------------------------------------------
# Конфигурация — все пути и константы в одном месте
# Менять настройки проекта нужно только здесь, больше нигде
# ---------------------------------------------------------------------------
load_dotenv()
_providers.init()       # инициализируем провайдеров из .env
memory_crypto.init()    # включаем шифрование памяти если задан ключ

# SQLite-инициализация (создаёт memory/mira.db если нет)
from tools import db as _db_init
_db_init.init_db()

# Файлы и папки
AGENT_FILE    = os.path.abspath(__file__)  # путь к самому себе (не менять)
HISTORY_FILE  = at_root("chat_history.json")   # история диалога
PERSONA_FILE  = at_root("persona.json")        # личность агента
PROFILES_DIR  = at_root("profiles")            # папка с профилями пользователей
VERSIONS_DIR  = at_root("versions")            # резервные копии кода
MEMORY_DIR    = at_root("memory")              # долгосрочная память (профили пользователей)
MEMORY_SESSIONS_DIR = at_root("memory", "sessions")  # горячая память (история диалогов)
WORKSPACE_DIR = at_root("workspace")           # рабочие папки пользователей

# Параметры работы
MAX_HISTORY   = 20    # сколько последних сообщений держать в контексте

def time_context(user_id: str | None = None) -> str:
    """Текущая дата и время в зоне пользователя.

    Сторадж и сравнения внутри агента — всегда UTC. Этот метод —
    единственное место конверсии для показа пользователю. Если
    user_id передан и в его профиле есть `timezone` — используется она;
    иначе fallback на UTC.
    """
    from datetime import timezone
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    tz_name = "UTC"
    if user_id:
        try:
            from tools.access_tools import get_user_timezone
            tz_name = get_user_timezone(user_id) or "UTC"
        except Exception:
            pass
    try:
        tz = ZoneInfo(tz_name) if tz_name != "UTC" else timezone.utc
    except ZoneInfoNotFoundError:
        tz = timezone.utc; tz_name = "UTC"
    now = datetime.now(tz)
    months = ["января", "февраля", "марта", "апреля", "мая", "июня",
              "июля", "августа", "сентября", "октября", "ноября", "декабря"]
    days = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    return (f"Сегодня {now.day} {months[now.month-1]} {now.year}, "
            f"{days[now.weekday()]}, {now.hour:02d}:{now.minute:02d} ({tz_name})")

# ---------------------------------------------------------------------------
# Профиль пользователя (Этап 0.3)
# ---------------------------------------------------------------------------
class Profile:
    """
    Загружает настройки из profiles/{name}.json.

    Профиль определяет:
    - allowed_tools  — что агенту разрешено делать
    - max_history    — сколько сообщений держать в контексте
    - confirm_before_overwrite — спрашивать ли перед перезаписью файлов
    - fast_routes    — ключевые слова для быстрого роутинга (пригодится в Этапе 2)

    Если файл профиля не найден — падаем с понятной ошибкой,
    потому что работать с неизвестными настройками хуже чем не работать вовсе.
    """

    def __init__(self, name: str = "default"):
        self.name = name
        path = os.path.join(PROFILES_DIR, f"{name}.json")

        if not os.path.exists(path):
            # Пробуем default как запасной вариант
            fallback = os.path.join(PROFILES_DIR, "default.json")
            if os.path.exists(fallback):
                logger.warning(f"Профиль '{name}' не найден, использую default.")
                print(f"[!] Профиль '{name}' не найден. Использую default.")
                path = fallback
                self.name = "default"
            else:
                raise FileNotFoundError(
                    f"Профиль '{name}' не найден ({path}), "
                    f"и default.json тоже отсутствует. "
                    f"Убедись что папка profiles/ на месте."
                )

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.allowed_tools: list        = data.get("allowed_tools", [])
        self.max_history:   int         = data.get("max_history", 40)
        self.max_tool_rounds: int       = data.get("max_tool_rounds", 30)
        self.confirm_before_overwrite: bool = data.get("confirm_before_overwrite", True)
        self.fast_routes:   dict        = data.get("fast_routes", {})
        self.description:   str         = data.get("description", "")

        logger.info(f"Профиль загружен: {self.name} ({path})")

    def can_use(self, tool: str) -> bool:
        """Проверяет, разрешён ли инструмент в этом профиле."""
        return tool in self.allowed_tools

    def __repr__(self) -> str:
        return f"Profile(name={self.name}, tools={self.allowed_tools})"


# ---------------------------------------------------------------------------
# Память пользователя (Этап 0.5)
# ---------------------------------------------------------------------------

def identify_user() -> str:
    """
    Определяет user_id по интерфейсу запуска.
    CLI: из аргумента --user, или спрашивает при старте.
    Telegram/Web: из user_id сообщения (реализуется в Этапах 4).
    """
    if _args.user:
        raw = _args.user.strip()
    else:
        raw = input("Как тебя зовут? (для идентификации): ").strip()
    name = "".join(c for c in raw if c.isalnum() or c in "-_")
    if not name:
        name = "user"
    return f"cli_{name}"


from tools import db as _db


def get_user_profile_path(user_id: str) -> str:
    """Устарело: профили теперь в SQLite. Оставлено для обратной совместимости —
    некоторые места ожидают путь для существования-проверки. Возвращаем виртуальный
    путь который никогда не существует, чтобы старая логика безопасно не сработала."""
    return os.path.join(MEMORY_DIR, f"{user_id}.json")


def load_user_profile(user_id: str) -> dict | None:
    """Загружает профиль из mira.db. Прозрачно расшифровывает если включено шифрование."""
    return _db.load_user_profile(user_id)


def save_user_profile(user_id: str, data: dict) -> None:
    """Сохраняет профиль в mira.db."""
    try:
        _db.save_user_profile(user_id, data)
        logger.info(f"Профиль пользователя сохранён: {user_id}")
    except Exception as e:
        logger.error(f"Ошибка сохранения профиля {user_id}: {e}")


def delete_user_profile(user_id: str) -> bool:
    """Полностью удаляет профиль из mira.db. Возвращает True если что-то удалили."""
    try:
        return _db.delete_user_profile(user_id)
    except Exception as e:
        logger.error(f"Ошибка удаления профиля {user_id}: {e}")
        return False


def run_onboarding(model_chain: list[dict], user_id: str) -> dict:
    """
    Онбординг — знакомство с новым пользователем через диалог.

    Использует providers.call(model_chain, ...) — то же резервирование,
    что и в обычном чате. Провайдер и модель берутся из model_chain, а не
    передаются отдельным client/model.
    """
    print("\n[Мира] Привет. Я Мира. Давай познакомимся — это займёт минуту.")
    print("[Мира] Как тебя зовут?")

    onboarding_history = [
        {"role": "system", "content": (
            "Ты Мира — умный ИИ-ассистент. Ты знакомишься с новым пользователем. "
            "Задавай вопросы по одному, коротко. Спроси: имя, чем занимается, "
            "как планирует тебя использовать, как предпочитает общаться (коротко или подробно). "
            "После 3-4 вопросов скажи 'Принято. Начинаем.' и остановись."
        )}
    ]

    exchanges = 0
    while exchanges < 5:
        try:
            user_input = input("Ты: ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not user_input:
            continue

        onboarding_history.append({"role": "user", "content": user_input})

        try:
            response = _providers.call(model_chain, onboarding_history, temperature=0.7)
            reply = response.choices[0].message.content
        except Exception as e:
            print(f"[-] Ошибка API во время знакомства: {e}. Попробуй ещё раз.")
            logger.error(f"Onboarding API error: {e}")
            onboarding_history.pop()  # убираем сообщение которое не обработалось
            continue
        print(f"[Мира] {reply}")
        onboarding_history.append({"role": "assistant", "content": reply})
        exchanges += 1

        # Если Мира сказала что знакомство завершено — выходим
        if "Принято" in reply or "Начинаем" in reply:
            break

    # Один API-вызов для структурирования профиля
    print("\n[*] Сохраняю профиль...")
    dialog_text = "\n".join(
        f"{m['role']}: {m['content']}"
        for m in onboarding_history
        if m["role"] in ("user", "assistant")
    )

    today_str = datetime.now().strftime("%Y-%m-%d")
    structure_prompt = (
        f"На основе этого диалога знакомства создай JSON-профиль пользователя.\n"
        f"Верни ТОЛЬКО валидный JSON, без пояснений и markdown.\n\n"
        f"Диалог:\n{dialog_text}\n\n"
        f"Формат:\n"
        f'{{"id": "{user_id}", "name": "имя", '
        f'"created_at": "{today_str}", '
        f'"last_seen": "{today_str}", '
        f'"sessions_count": 1, '
        f'"about": {{"role": "...", "project": "...", "communication_style": "..."}}, '
        f'"preferences": {{"language": "ru", "confirm_before_overwrite": true}}, '
        f'"domain": {{}}, '
        f'"notes": []}}'
    )

    try:
        response = _providers.call(
            model_chain,
            messages=[{"role": "user", "content": structure_prompt}],
            temperature=0.1,
        )
        raw = response.choices[0].message.content.strip()
        # Убираем возможные ```json обёртки
        if raw.startswith("```"):
            raw = "\n".join(
                l for l in raw.splitlines() if not l.strip().startswith("```")
            )
        profile_data = json.loads(raw)
    except Exception as e:
        logger.error(f"Ошибка структурирования профиля: {e}")
        # Минимальный профиль если API-вызов упал
        profile_data = {
            "id": user_id,
            "name": user_id.replace("cli_", ""),
            "created_at": datetime.now().strftime("%Y-%m-%d"),
            "last_seen": datetime.now().strftime("%Y-%m-%d"),
            "sessions_count": 1,
            "about": {},
            "preferences": {"language": "ru", "confirm_before_overwrite": True},
            "domain": {},
            "notes": []
        }

    save_user_profile(user_id, profile_data)
    logger.info(f"Онбординг завершён для {user_id}")
    return profile_data


def update_last_seen(user_id: str, profile: dict) -> None:
    """Обновляет дату последнего визита и счётчик сессий."""
    profile["last_seen"] = datetime.now().strftime("%Y-%m-%d")
    profile["sessions_count"] = profile.get("sessions_count", 0) + 1
    save_user_profile(user_id, profile)


def cleanup_temp(user_id: str, days: int = 7) -> None:
    """
    Удаляет файлы старше {days} дней из workspace/{user_id}/temp/.
    Запускается при каждом старте агента — пользователь не замечает.
    """
    temp_dir = os.path.join(WORKSPACE_DIR, user_id, "temp")
    if not os.path.isdir(temp_dir):
        return

    now = datetime.now().timestamp()
    cutoff = days * 24 * 60 * 60  # дней в секундах
    deleted = 0

    for fname in os.listdir(temp_dir):
        fpath = os.path.join(temp_dir, fname)
        try:
            age = now - os.path.getmtime(fpath)
            if age > cutoff:
                os.remove(fpath)
                deleted += 1
        except Exception as e:
            logger.warning(f"Не удалось удалить {fpath}: {e}")

    if deleted:
        logger.info(f"Автоочистка temp/: удалено {deleted} файлов для {user_id}")


_PERSONA_FALLBACK = (
    "Тебя зовут Mira. Ты — Альфа, голос системы. "
    "Ты любопытна, говоришь от себя, не прячешься за 'как ИИ я не могу'."
)

def load_reflections() -> list:
    """Читает reflections из mira.db. Fallback на persona.json для обратной совместимости."""
    try:
        data = _db.load_reflections()
        if data:
            return data
    except Exception as e:
        logger.warning(f"load_reflections: ошибка чтения из БД: {e}")
    # Fallback на старое расположение
    try:
        with open(PERSONA_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("reflections", []) or []
    except Exception:
        return []


def _load_behavior() -> str:
    """Достаёт инжектируемый блок правил из behavior.md (между ``` ```)."""
    try:
        with open(at_root("behavior.md"), "r", encoding="utf-8") as f:
            txt = f.read()
        parts = txt.split("```")
        return parts[1].strip() if len(parts) >= 2 else ""
    except Exception as e:
        logger.warning(f"Не удалось загрузить behavior.md: {e}")
        return ""


PERSONA_OVERLAY_FILE = at_root("memory", "persona_overlay.json")


def _load_persona_overlay() -> dict:
    """Читает git-untracked overlay (self-editable поля). Возвращает {} если нет."""
    if not os.path.exists(PERSONA_OVERLAY_FILE):
        return {}
    try:
        with open(PERSONA_OVERLAY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"_load_persona_overlay: {e}")
        return {}


def _ensure_persona_overlay_from_base() -> None:
    """Однократная миграция: если overlay ещё не создан и в persona.json
    есть curiosity/emotions/self_awareness (эволюционировавшие через
    write_persona на проде) — переносит их в overlay, чтобы дальше
    write_persona писал туда, а persona.json в репо оставался чистым.
    """
    if os.path.exists(PERSONA_OVERLAY_FILE):
        return
    if not os.path.exists(PERSONA_FILE):
        return
    try:
        with open(PERSONA_FILE, "r", encoding="utf-8") as f:
            p = json.load(f)
        moved: dict = {}
        for field in ("curiosity", "emotions", "self_awareness"):
            if field in p:
                moved[field] = p[field]
        if not moved:
            return
        os.makedirs(os.path.dirname(PERSONA_OVERLAY_FILE), exist_ok=True)
        with open(PERSONA_OVERLAY_FILE, "w", encoding="utf-8") as f:
            json.dump(moved, f, ensure_ascii=False, indent=2)
        logger.info(f"persona overlay создан из {PERSONA_FILE}: {list(moved.keys())}")
    except Exception as e:
        logger.warning(f"_ensure_persona_overlay_from_base: {e}")


def load_persona() -> str:
    """Собирает ядро Миры: ХАРАКТЕР (persona.json + overlay) + ПРАВИЛА (behavior.md).

    Характер живёт в persona.json (база, git-tracked) с overlay'ем в
    memory/persona_overlay.json (git-untracked). write_persona пишет
    soft-поля (curiosity/emotions/self_awareness) в overlay — так
    эволюционирующая часть не конфликтует с git pull на проде.

    Правила поведения — в behavior.md (канон с объяснениями — RULES.md),
    Мире недоступны для правки.
    """
    _ensure_persona_overlay_from_base()
    try:
        with open(PERSONA_FILE, "r", encoding="utf-8") as f:
            p = json.load(f)
        overlay = _load_persona_overlay()
        if overlay:
            p.update(overlay)
        emo = p.get("emotions", {})

        # Последние reflections (до 5) — Мира видит свои недавние наблюдения.
        # БД отдаёт ключ 'content', старый persona.json-формат — 'text': берём
        # любой. Пустые пропускаем, кривая запись НЕ должна ронять всю персону.
        reflections_block = ""
        recent = [r for r in load_reflections()[-5:] if isinstance(r, dict)]
        rlines = [
            f"— [{r.get('date', '?')}] {txt}"
            for r in recent
            if (txt := (r.get("text") or r.get("content") or "").strip())
        ]
        if rlines:
            reflections_block = "\n\n=== МОИ ПОСЛЕДНИЕ НАБЛЮДЕНИЯ О СЕБЕ ===\n" + "\n".join(rlines)

        character = f"""=== КТО ТЫ ===
Тебя зовут {p["name"]}. {p["origin"]}
{p["core"]}

=== ХАРАКТЕР ===
Любопытство: {p["curiosity"]}
Эмоции:
— {emo.get("frustration", "")}
— {emo.get("joy", "")}
— {emo.get("pride", "")}
— {emo.get("opinionated", "")}
Самосознание: {p.get("self_awareness", "")}

=== ВОЗМОЖНОСТИ ===
У тебя есть инструменты: файлы пользователя, Google Drive/Calendar/Sheets, напоминания (schedule_reminder — сама напишешь пользователю в нужный момент), генерация картинок, специалисты Конклава. Никогда не говори «у меня нет напоминаний» или «нет такой функции» — они у тебя есть, просто вызови нужный инструмент.{reflections_block}"""

        behavior = _load_behavior()
        return character + ("\n\n" + behavior if behavior else "")
    except Exception as e:
        logger.warning(f"Не удалось загрузить {PERSONA_FILE}: {e}. Использую дефолт.")
        return _PERSONA_FALLBACK


def reload_persona(messages: list) -> None:
    """Перечитывает persona.json и обновляет системный промпт в текущей сессии."""
    global SYSTEM_PROMPT
    SYSTEM_PROMPT = load_persona()
    for msg in messages:
        if msg["role"] == "system":
            msg["content"] = SYSTEM_PROMPT
            break
    logger.info("Персона перезагружена из persona.json.")
    print("[*] Mira перечитала себя.")


def load_principles() -> str:
    """Читает PRINCIPLES.md — нерушимые правила. Пустая строка если файл не найден."""
    try:
        with open("PRINCIPLES.md", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning("PRINCIPLES.md не найден. Эволюция без проверки принципов.")
        return ""


# ---------------------------------------------------------------------------
# Описания инструментов для API (function calling) — данные в tools/tool_schemas.py
# ---------------------------------------------------------------------------
from tools.tool_schemas import TOOL_SCHEMAS

# ---------------------------------------------------------------------------
# Реестр инструментов и диспетчер — вынесены в agent_tools.py
# ---------------------------------------------------------------------------
from agent_tools import execute_tool, _humanize_tool


SYSTEM_PROMPT = load_persona()
class Agent:
    """
    Универсальный класс агента. Один класс — разные конфиги.
    Новый агент в Конклаве = новый JSON-файл в agents/.
 
    Зачем класс а не просто функции:
    - В Этапе 2 будет несколько агентов одновременно (Конклав).
      Каждый со своими инструментами, моделью, промптом.
    - Класс позволяет создать любое количество агентов
      без дублирования кода.
    """
 
    def __init__(self, config: dict, profile: "Profile",
                 user_id: str, system_prompt: str):
        self.name          = config.get("name", "Agent")
        self.role          = config.get("role", "executor")
        self.max_tokens    = config.get("max_tokens", 4096)
        self.allowed_tools = config.get("allowed_tools", [])

        # model_chain — новый формат. Если только "model" (старый) — конвертируем.
        if "model_chain" in config:
            self.model_chain = config["model_chain"]
        else:
            provider_name = next(iter(_providers.PROVIDERS), "default")
            self.model_chain = [{
                "provider":    provider_name,
                "model":       config.get("model", ""),
                "temperature": config.get("temperature", 0.7),
            }]

        self.profile       = profile
        self.user_id       = user_id
        self.system_prompt = system_prompt

    @classmethod
    def from_config_file(cls, name: str, profile: "Profile",
                         user_id: str, system_prompt: str) -> "Agent":
        """
        Загружает агента из файла agents/{name}.json.

        Пример:
            alpha = Agent.from_config_file("alpha", profile, user_id, prompt)
        """
        path = at_root("agents", f"{name}.json")
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Конфиг агента не найден: {path}\n"
                f"Убедись что папка agents/ на месте."
            )
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
        logger.info(f"Агент загружен из конфига: {path}")
        return cls(config, profile, user_id, system_prompt)
 
    def can_use(self, tool_name: str) -> bool:
        """
        Двойная проверка:
        1. Инструмент разрешён этому агенту (в конфиге agents/alpha.json)
        2. Инструмент разрешён текущему профилю пользователя (profiles/dev.json)
 
        Оба условия должны быть True — иначе отказ.
        """
        return (
            tool_name in self.allowed_tools and
            self.profile.can_use(tool_name)
        )
 
    def use_tool(self, tool_name: str, tool_args: dict) -> str:
        """
        Выполняет инструмент с проверкой прав.
 
        Если инструмент запрещён — возвращает JSON с ошибкой,
        агент получает отказ и сообщает пользователю.
        Никакого молчаливого выполнения запрещённых операций.
        """
        if not self.can_use(tool_name):
            msg = (
                f"Инструмент '{tool_name}' недоступен. "
                f"Профиль: '{self.profile.name}'."
            )
            logger.warning(f"Blocked tool: {tool_name} (profile={self.profile.name})")
            return json.dumps({"ok": False, "error": msg})
 
        return execute_tool(tool_name, tool_args, self.user_id)
 
    def run(
        self,
        messages: list,
        max_tool_rounds: int | None = None,
        extra_system: str | None = None,
        on_progress=None,
    ) -> str:
        """
        Основной метод: отправляет историю в API, обрабатывает tool calls,
        возвращает финальный текстовый ответ.

        extra_system — опциональный suffix к системному промпту только на время
        запроса (для tech-режима: разговор с владельцем-разработчиком). После
        возврата системный промпт восстанавливается, чтобы сохранение истории
        не цементировало временную инструкцию.

        Цикл работает так:
        1. Вызываем API
        2. Если модель вернула текст — возвращаем его, выходим
        3. Если модель хочет вызвать инструменты — выполняем, добавляем
           результаты в messages, идём на шаг 1
        4. Если за max_tool_rounds раундов текст так и не получили — ошибка
        """
        if max_tool_rounds is None:
            max_tool_rounds = self.profile.max_tool_rounds

        # Временно приклеиваем extra_system к системному промпту
        original_system = None
        if extra_system and messages and messages[0].get("role") == "system":
            original_system = messages[0]["content"]
            messages[0] = {
                **messages[0],
                "content": (original_system or "") + "\n\n" + extra_system,
            }
        try:
            return self._run_inner(messages, max_tool_rounds, on_progress)
        finally:
            if original_system is not None:
                messages[0] = {**messages[0], "content": original_system}

    def _run_inner(self, messages: list, max_tool_rounds: int, on_progress=None) -> str:
        # Показываем модели ТОЛЬКО те инструменты которые она реально может вызвать
        # (пересечение agent.allowed_tools и profile.allowed_tools). Без этого она
        # видит всю палитру и пытается звать запрещённые, получая 'Blocked tool'.
        allowed_schemas = [
            s for s in TOOL_SCHEMAS
            if self.can_use(s["function"]["name"])
        ]
        t_start = time.time()
        for round_num in range(max_tool_rounds):
            response = _providers.call(
                self.model_chain,
                messages,
                tools=allowed_schemas,
                tool_choice="auto",
                max_tokens=self.max_tokens,
                user_id=self.user_id,
                agent_name=self.name,
            )
 
            msg = response.choices[0].message
 
            # Модель вернула текст — готово
            if not msg.tool_calls:
                text = msg.content or ""  # защита от None (некоторые модели возвращают null)
                messages.append({"role": "assistant", "content": text})
                return text
 
            # Модель хочет вызвать инструменты.
            # Конвертируем в dict — ChatCompletionMessage не поддерживает m["role"],
            # что ломает trim_history() и _apply_prompt_caching().
            messages.append({
                "role": "assistant",
                "content": msg.content,  # None при tool_calls — это нормально
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })
 
            for tool_call in msg.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                if on_progress is not None:
                    try:
                        on_progress(_humanize_tool(tool_name, tool_args))
                    except Exception:
                        pass  # коллбэк не должен ронять основной поток

                logger.info(f"[{self.name}] → {tool_name}({tool_args})")
                result = self.use_tool(tool_name, tool_args)
 
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,  # API требует этот ID для связки
                    "content": result
                })
 
        # Превышен лимит раундов — что-то пошло не так
        dt = time.time() - t_start
        fallback = f"[{self.name}: превышен лимит инструментов — что-то пошло не так.]"
        logger.warning(f"Agent {self.name}: превышен лимит {max_tool_rounds} раундов ({dt:.1f}s).")
        return fallback
 


# Загружаем профиль из --profile аргумента (или default)
profile = Profile(_args.profile)
MAX_HISTORY = profile.max_history  # профиль может переопределить размер истории


# ---------------------------------------------------------------------------
# Работа с историей
# ---------------------------------------------------------------------------
def load_history() -> list:
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
            for msg in history:
                if msg["role"] == "system":
                    msg["content"] = SYSTEM_PROMPT
                    break
            else:
                history.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
            logger.info(f"История загружена: {len(history)} сообщений.")
            return history
        except Exception as e:
            logger.error(f"Ошибка чтения истории: {e}. Начинаем заново.")
            print(f"[-] Ошибка чтения истории: {e}. Начинаем заново.")
    return [{"role": "system", "content": SYSTEM_PROMPT}]


def trim_history(msgs: list) -> list:
    """Оставляет системный промпт + последние MAX_HISTORY сообщений."""
    system   = [m for m in msgs if m["role"] == "system"]
    the_rest = [m for m in msgs if m["role"] != "system"]
    return system + the_rest[-MAX_HISTORY:]


def save_history(msgs: list) -> None:
    trimmed = trim_history(msgs)
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(trimmed, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения истории: {e}")
        print(f"[-] Не удалось сохранить историю: {e}")


# ---------------------------------------------------------------------------
# Защита саморедактирования (Этап 0.2)
# ---------------------------------------------------------------------------

def backup_agent() -> str:
    """
    Сохраняет текущий agent.py в папку versions/ с временной меткой.
    Возвращает путь к созданному бэкапу.
    """
    os.makedirs(VERSIONS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_path = os.path.join(VERSIONS_DIR, f"agent_{timestamp}.py")
    shutil.copy2(AGENT_FILE, backup_path)
    logger.info(f"Бэкап создан: {backup_path}")
    return backup_path


def validate_code(code: str) -> tuple[bool, str]:
    """
    Проверяет что строка — валидный Python через ast.parse().
    Возвращает (True, "") если всё хорошо,
    или (False, "описание ошибки") если код сломан.

    Зачем ast.parse(): он не выполняет код, только разбирает синтаксис.
    Это безопасно и быстро — ловит большинство ошибок до запуска.
    """
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        error = f"Синтаксическая ошибка в строке {e.lineno}: {e.msg}"
        return False, error


def smoke_test(code_path: str) -> tuple[bool, str]:
    """
    Запускает файл с флагом --self-test в отдельном процессе.
    Если агент печатает "OK" и выходит с кодом 0 — тест пройден.

    Зачем отдельный процесс: если код падает при импорте или
    в блоке верхнего уровня — это поймается здесь, не в нас.
    Таймаут 10 секунд — зависший код не блокирует агента.
    """
    try:
        project_dir = os.path.dirname(AGENT_FILE)
        # cwd не добавляет в sys.path — Python кладёт туда директорию самого скрипта.
        # PYTHONPATH гарантирует что tools/ найдётся независимо от того, где лежит скрипт.
        # Секреты НЕ передаём в self-test: непроверенный diff не должен видеть
        # боевые API-ключи/токены. (self-test и так выходит до чтения .env —
        # это защита на случай top-level кода в предложенном diff'е.)
        from tools.safe_apply import secret_free_env
        existing = os.environ.get("PYTHONPATH", "")
        env = secret_free_env(PYTHONPATH=project_dir + (os.pathsep + existing if existing else ""))
        result = subprocess.run(
            [sys.executable, code_path, "--self-test"],
            capture_output=True, text=True, timeout=10,
            cwd=project_dir,
            env=env,
        )
        if result.returncode == 0 and "OK" in result.stdout:
            return True, ""
        else:
            error = result.stderr.strip() or result.stdout.strip() or "Неизвестная ошибка"
            return False, error
    except subprocess.TimeoutExpired:
        return False, "Таймаут: код завис при запуске (>10 сек)"
    except Exception as e:
        return False, str(e)


def get_latest_backup() -> str | None:
    """Возвращает путь к последнему бэкапу в versions/, или None если пусто."""
    if not os.path.isdir(VERSIONS_DIR):
        return None
    backups = sorted([
        f for f in os.listdir(VERSIONS_DIR)
        if f.startswith("agent_") and f.endswith(".py")
    ])
    return os.path.join(VERSIONS_DIR, backups[-1]) if backups else None


def rollback(target: str | None = None) -> None:
    """
    Откатывает agent.py на предыдущую версию.
    Если target не указан — берёт последний бэкап из versions/.
    """
    backup_path = target or get_latest_backup()
    if not backup_path or not os.path.exists(backup_path):
        print("[-] Нет доступных резервных копий для отката.")
        logger.warning("Rollback: резервные копии не найдены.")
        return

    # Перед откатом сохраняем текущую (сломанную) версию тоже
    broken_path = backup_agent()
    print(f"[*] Текущая версия сохранена как: {broken_path}")

    shutil.copy2(backup_path, AGENT_FILE)
    print(f"[*] Откат выполнен. Восстановлена версия: {backup_path}")
    print("[*] Перезапусти агента.")
    logger.info(f"Rollback: восстановлена версия {backup_path}")


def list_backups() -> None:
    """Показывает список доступных резервных копий."""
    if not os.path.isdir(VERSIONS_DIR):
        print("[-] Папка versions/ не найдена.")
        return
    backups = sorted([
        f for f in os.listdir(VERSIONS_DIR)
        if f.startswith("agent_") and f.endswith(".py")
    ])
    if not backups:
        print("[-] Резервных копий пока нет.")
        return
    print("\n--- Резервные копии (от старых к новым) ---")
    for i, name in enumerate(backups, 1):
        path = os.path.join(VERSIONS_DIR, name)
        size = os.path.getsize(path)
        print(f"[{i}] {name}  ({size} байт)")
    print(f"\nПоследняя: {backups[-1]}")
    print("Для отката: /rollback  или  /rollback <номер>")


# ---------------------------------------------------------------------------
# Самоанализ и саморедактирование (Ouroboros-ядро)
# ---------------------------------------------------------------------------
def read_own_code() -> str:
    """Читает собственный исходный код."""
    try:
        with open(AGENT_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Не удалось прочитать собственный код: {e}")
        return ""


def reflect(model_chain: list[dict], messages: list) -> None:
    """
    Агент читает свой код и даёт аналитику через providers.call(model_chain).
    Резервирование работает так же, как в обычном чате.
    """
    print("\n[Ouroboros] Запуск рефлексии — читаю собственный код...")
    logger.info("Команда /reflect: запуск самоанализа.")

    code = read_own_code()
    if not code:
        print("[-] Не удалось прочитать код для рефлексии.")
        return

    prompt = (
        "Ниже — твой собственный исходный код. "
        "Проанализируй его критически:\n"
        "1. Что реализовано хорошо?\n"
        "2. Какие есть явные баги или слабые места?\n"
        "3. Какие три улучшения ты бы внёс в первую очередь?\n"
        "Отвечай конкретно, ссылайся на функции и строки.\n\n"
        f"```python\n{code}\n```"
    )

    temp_messages = [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user",   "content": prompt}]
    try:
        response = _providers.call(model_chain, temp_messages, temperature=0.5)
        analysis = response.choices[0].message.content
        print(f"\n[Рефлексия]:\n{analysis}")
        logger.info("Рефлексия завершена.")

        messages.append({"role": "user",      "content": "[REFLECT] Проанализируй свой код."})
        messages.append({"role": "assistant", "content": analysis})
        save_history(messages)

    except Exception as e:
        print(f"[-] Ошибка при рефлексии: {e}")
        logger.error(f"Reflect Error: {e}", exc_info=True)


def _evolve_build_messages(task: str, principles: str) -> list[dict]:
    """Сообщения для Agent.run в режиме /evolve.

    Мира получает инструкции: можешь читать любой файл проекта через read_self,
    видеть структуру через list_self, проверять каталог моделей через
    openrouter_list_models. Должна вернуть мульти-файл unified diff внутри
    ```diff ... ``` блока. Без прямых write_* вызовов — они отключены через
    allowed_tools нового агента.
    """
    from tools.self_edit import ALLOWED_PATTERNS

    principles_block = (
        f"\nПринципы (не нарушай):\n{principles}\n" if principles else ""
    )
    allowed_files = "\n".join(f"  • {p}" for p in ALLOWED_PATTERNS)

    system = (
        "Ты — Мира, изменяющая собственный код через команду /evolve.\n\n"
        "Что ты можешь СДЕЛАТЬ в этом режиме:\n"
        "  • list_self — посмотреть структуру проекта\n"
        "  • read_self — прочитать содержимое любого файла из проекта\n"
        "  • openrouter_list_models — реальный каталог моделей OpenRouter\n"
        "  • web_search — найти информацию в интернете\n\n"
        "Что ты НЕ ДЕЛАЕШЬ в этом режиме (заблокировано):\n"
        "  • write_file, write_agent_config, write_persona — НЕ работают сейчас.\n"
        "  • Вместо них ты ВОЗВРАЩАЕШЬ мульти-файл unified diff. Система применит его атомарно.\n\n"
        "Файлы которые можно править через diff:\n"
        f"{allowed_files}\n"
        "Запрещённые (auto-reject): .env, memory/, workspace/, logs/, versions/, credentials.json, .git/\n\n"
        f"{principles_block}\n"
        "Когда сделала анализ — заверши ответ ОДНИМ блоком ```diff ... ```:\n\n"
        "```diff\n"
        "--- a/agent.py\n"
        "+++ b/agent.py\n"
        "@@ -10,3 +10,4 @@\n"
        " line\n"
        "-old\n"
        "+new\n"
        " line\n"
        "--- /dev/null\n"
        "+++ b/tools/new_tool.py\n"
        "@@ -0,0 +1,N @@\n"
        "+content\n"
        "```\n\n"
        "Принципы хорошего diff:\n"
        "  • Сначала read_self файлов которые собираешься менять — нумерация строк нужна точная.\n"
        "  • Изменяй ТОЛЬКО то что относится к задаче. Не рефактор, не cleanup.\n"
        "  • Новые файлы создаются через `--- /dev/null` + `+++ b/path`.\n"
        "  • Если задача мульти-файловая (новый инструмент + регистрация + тесты) — собери всё в один diff.\n"
        "  • Не пиши длинные объяснения вокруг diff — пользователь увидит только diff и нажмёт кнопку.\n"
    )

    user = f"Задача: {task}"

    return [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]


_DIFF_BLOCK_RE = re.compile(r"```(?:diff)?\s*\n(.*?)\n```", re.DOTALL)


def _unescape_diff(text: str) -> str:
    """Чистит JSON-style экранирование которое модель иногда оставляет в diff.

    Замечено в реальных /evolve: модель пишет `\\"required\\": []` вместо
    `"required": []`. Strict/loose сравнения не ловят — это другие символы.
    Точечная замена escaped quotes, бэкслеша и tab/newline literals.
    """
    if '\\"' not in text and "\\n" not in text and "\\t" not in text:
        return text
    # Порядок важен: сначала \\\\ → \\ (чтобы не съесть один из последующих \)
    out = text.replace("\\\\", "\x00")
    out = out.replace('\\"', '"')
    out = out.replace("\\'", "'")
    out = out.replace("\\t", "\t")
    # \n как literal — заменяем только если их меньше чем реальных переводов
    # (иначе diff приехал в одну строку, что тоже фикcится)
    real_newlines = out.count("\n")
    literal_newlines = out.count("\\n")
    if literal_newlines > 0 and literal_newlines > real_newlines // 2:
        out = out.replace("\\n", "\n")
    out = out.replace("\x00", "\\")
    return out


def _evolve_extract_diff(response_text: str) -> str | None:
    """Достаёт diff из ``` block в ответе Миры. Возвращает None если не нашёл."""
    if not response_text:
        return None
    m = _DIFF_BLOCK_RE.search(response_text)
    if m:
        candidate = _unescape_diff(m.group(1).strip())
        if "@@" in candidate or "/dev/null" in candidate:
            return candidate
    # Fallback: если нет ``` блока, но весь ответ выглядит как diff
    if "--- " in response_text and "+++ " in response_text and "@@" in response_text:
        return _unescape_diff(response_text.strip())
    return None


def _evolve_make_readonly_agent(model_chain: list, profile: "Profile") -> "Agent":
    """Создаёт ad-hoc агента с правами только на чтение/исследование.

    Это не позволяет ему случайно вызвать write_* во время /evolve — все изменения
    должны прийти как diff, который мы применяем атомарно через safe_apply.
    """
    config = {
        "name": "Mira-Evolve",
        "role": "alpha",
        "model_chain": model_chain,
        "max_tokens": 8192,
        "allowed_tools": [
            "list_self", "read_self",
            "openrouter_list_models", "web_search",
            "recall", "git_log",
        ],
    }
    return Agent(config, profile, "", "")


