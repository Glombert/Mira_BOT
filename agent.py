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
from openai import OpenAI
from tools import list_files, read_file, write_file, run_python, undo_last, list_undo, excel_read, excel_write, web_search, list_self, read_self, write_persona, write_agent_config, git_log
from tools import semantic_memory
from tools.gdrive_tools import gdrive_list, gdrive_read, gdrive_write, is_authorized as _gdrive_authorized, auto_upload_to_drive as _gdrive_auto_upload
from tools import image_tools
from tools.gdrive_tools import gcal_list, gcal_create, gcal_quick_add
from tools.gdrive_tools import gsheet_read, gsheet_write, gsheet_create
from tools.metrics_tools import metrics_read
from tools.scheduler import schedule_reminder, list_reminders, cancel_reminder
from tools.openrouter_tools import list_models as _openrouter_list_models
import memory_manager as _memory_manager
import memory_crypto
from tools.git_tools   import sync_with_git, ensure_dev_branch, release_to_main
from tools.cloud_tools import cloud_sync, cloud_restore, sync_output_to_drive, sync_inbox_from_drive
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
logger = logging.getLogger("Ouroborus")
logger.setLevel(logging.INFO)

os.makedirs("logs", exist_ok=True)
log_handler = TimedRotatingFileHandler(
    "logs/agent.log",
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

logger.info("=== Запуск агента Ouroborus ===")

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
HISTORY_FILE  = "chat_history.json"        # история диалога
PERSONA_FILE  = "persona.json"             # личность агента
PROFILES_DIR  = "profiles"                 # папка с профилями пользователей
VERSIONS_DIR  = "versions"                 # резервные копии кода
MEMORY_DIR    = "memory"                   # долгосрочная память (профили пользователей)
MEMORY_SESSIONS_DIR = os.path.join("memory", "sessions")  # горячая память (история диалогов)
WORKSPACE_DIR = "workspace"                # рабочие папки пользователей

# Параметры работы
MAX_HISTORY   = 20    # сколько последних сообщений держать в контексте

def time_context() -> str:
    """Текущая дата и время для осознания Миры. Обновляется при каждом вызове."""
    import datetime
    now = datetime.datetime.now()
    months = ["января", "февраля", "марта", "апреля", "мая", "июня",
              "июля", "августа", "сентября", "октября", "ноября", "декабря"]
    days = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    return f"Сегодня {now.day} {months[now.month-1]} {now.year}, {days[now.weekday()]}, {now.hour:02d}:{now.minute:02d}"
                      # (переопределяется профилем пользователя)

# Провайдеры моделей (заполняется из .env автоматически)
MODELS_CONFIG: dict = {}
counter = 1


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


def load_persona() -> str:
    """Загружает персону из persona.json и собирает системный промпт."""
    try:
        with open(PERSONA_FILE, "r", encoding="utf-8") as f:
            p = json.load(f)

        b = p.get("boundaries", {})
        dislikes = "\n".join(f"— {d}" for d in b.get("dislikes", []))
        style_items = "\n".join(f"— {v}" for v in p.get("communication", {}).values())

        formatting     = p.get("formatting", "")
        self_awareness = p.get("self_awareness", "")

        # Последние reflections (до 5) — Мира видит свои недавние наблюдения
        reflections_block = ""
        reflections = load_reflections()
        if reflections:
            recent = reflections[-5:]
            lines = "\n".join(f"— [{r['date']}] {r['text']}" for r in recent)
            reflections_block = f"\nМои последние наблюдения о себе:\n{lines}"

        gender       = p.get("gender", "")
        anti_patterns = p.get("anti_patterns", "")
        examples     = p.get("examples", "")

        return f"""Тебя зовут {p["name"]}. {p["origin"]}
{p["core"]}
{gender}
Любопытство: {p["curiosity"]}
Эмоции:
— {p["emotions"]["frustration"]}
— {p["emotions"]["joy"]}
— {p["emotions"]["pride"]}
— {p["emotions"].get("opinionated", "")}
Как ты общаешься:
{style_items}
Конклав: {p["conclave"]}
Самосознание: {self_awareness}{reflections_block}
Границы:
{dislikes}
{b.get("reaction", "")}
{anti_patterns}
{examples}
{formatting}"""
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
# Реестр инструментов — каждый адаптер: (user_id, args) -> dict
# Простые враппинги — лямбды, с pre/post-хуками — именованные функции.
# ---------------------------------------------------------------------------
def _tool_list_files(user_id: str, args: dict) -> dict:
    subdir = args.get("subdir", "")
    if not subdir or subdir == "inbox":
        sync_inbox_from_drive(user_id)
    return list_files(user_id, subdir)


def _tool_read_file(user_id: str, args: dict) -> dict:
    path = args["relative_path"]
    if "inbox" in path:
        sync_inbox_from_drive(user_id)
    result = read_file(user_id, path)
    if result.get("ok") and "content" in result:
        fname = os.path.basename(path)
        result["content"] = (
            f"--- BEGIN USER FILE: {fname} ---\n"
            f"{result['content']}\n"
            f"--- END USER FILE ---"
        )
    return result


def _tool_write_file(user_id: str, args: dict) -> dict:
    result = write_file(
        user_id, args["relative_path"], args["content"],
        overwrite=args.get("overwrite", False),
    )
    if result.get("ok") and "output/" in args.get("relative_path", ""):
        sync_output_to_drive(user_id)
    return result


def _tool_excel_read(user_id: str, args: dict) -> dict:
    path = args["relative_path"]
    if "inbox" in path:
        sync_inbox_from_drive(user_id)
    return excel_read(user_id, path, sheet_name=args.get("sheet_name"))


def _tool_excel_write(user_id: str, args: dict) -> dict:
    result = excel_write(
        user_id, args["relative_path"], args["headers"], args["rows"],
        sheet_name=args.get("sheet_name", "Sheet1"),
        overwrite=args.get("overwrite", False),
    )
    if result.get("ok") and "output/" in args.get("relative_path", ""):
        sync_output_to_drive(user_id)
    return result


def _tool_recall(user_id: str, args: dict) -> dict:
    top_k = min(int(args.get("top_k", 5)), 10)
    matches = semantic_memory.search(user_id, args["query"], top_k=top_k)
    return {"ok": True, "count": len(matches), "matches": matches}


_TOOL_REGISTRY = {
    "list_files":         _tool_list_files,
    "read_file":          _tool_read_file,
    "write_file":         _tool_write_file,
    "excel_read":         _tool_excel_read,
    "excel_write":        _tool_excel_write,
    "recall":             _tool_recall,
    "run_python":         lambda u, a: run_python(a["code"], u),
    "web_search":         lambda u, a: web_search(a["query"], max_results=a.get("max_results", 5)),
    "save_template":      lambda u, a: _memory_manager.save_template(u, a["name"], a["description"], a["example"]),
    "list_templates":     lambda u, a: _memory_manager.list_templates(u),
    "list_self":          lambda u, a: list_self(),
    "read_self":          lambda u, a: read_self(a["path"]),
    "git_log":            lambda u, a: git_log(a.get("limit", 20)),
    "write_persona":      lambda u, a: write_persona(a["field"], a.get("value")),
    "write_agent_config": lambda u, a: write_agent_config(a["name"], a["config"]),
    "gdrive_list":        lambda u, a: gdrive_list(u, a.get("path", "root")),
    "gdrive_read":        lambda u, a: gdrive_read(u, a["file_path"]),
    "gdrive_write":       lambda u, a: gdrive_write(u, a["workspace_path"], a.get("drive_folder", "root")),
    "metrics_read":       lambda u, a: metrics_read(a.get("days", 1)),
    "gcal_list":          lambda u, a: gcal_list(u, a.get("max_results", 10), a.get("time_min")),
    "gcal_create":        lambda u, a: gcal_create(u, a["summary"], a["start_time"], a.get("end_time", ""), a.get("description", "")),
    "gcal_quick_add":     lambda u, a: gcal_quick_add(u, a["text"]),
    "gsheet_read":        lambda u, a: gsheet_read(u, a["spreadsheet_id"], a.get("sheet_range", "A1:Z100")),
    "gsheet_write":       lambda u, a: gsheet_write(u, a["spreadsheet_id"], a["sheet_range"], a["values"]),
    "gsheet_create":      lambda u, a: gsheet_create(u, a["title"]),
    "schedule_reminder":  lambda u, a: schedule_reminder(u, a["trigger_at"], a["message"]),
    "list_reminders":     lambda u, a: list_reminders(u),
    "cancel_reminder":    lambda u, a: cancel_reminder(u, a["task_id"]),
    "openrouter_list_models": lambda u, a: _openrouter_list_models(
        a.get("filter", ""), a.get("capability", ""), a.get("limit", 30)
    ),
    "generate_image":     lambda u, a: image_tools.generate_image(u, a["prompt"], a.get("model", "google/gemini-2.5-flash-image")),
}


def execute_tool(tool_name: str, tool_args: dict, user_id: str) -> str:
    """Диспетчер инструментов. Возвращает JSON-строку с результатом.

    API требует строку, поэтому dict конвертируем через json.dumps().
    user_id подставляем сами — модель его не знает и не передаёт.
    """
    t0 = time.time()
    logger.info(f"Tool call: {tool_name}({json.dumps(tool_args, ensure_ascii=False)})")

    handler = _TOOL_REGISTRY.get(tool_name)
    if handler is None:
        logger.warning(f"Tool call: неизвестный инструмент '{tool_name}'")
        return json.dumps({"ok": False, "error": f"Неизвестный инструмент: {tool_name}"})

    try:
        result = handler(user_id, tool_args)
    except Exception as e:
        result = {"ok": False, "error": f"Ошибка выполнения {tool_name}: {e}"}
        logger.error(f"Tool error ({tool_name}): {e}", exc_info=True)

    dt = time.time() - t0
    logger.info(f"Tool result ({tool_name}): ok={result.get('ok')} ({dt:.2f}s)")
    return json.dumps(result, ensure_ascii=False)


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
        path = os.path.join("agents", f"{name}.json")
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
 
    def run(self, messages: list, max_tool_rounds: int | None = None) -> str:
        """
        Основной метод: отправляет историю в API, обрабатывает tool calls,
        возвращает финальный текстовый ответ.

        Цикл работает так:
        1. Вызываем API
        2. Если модель вернула текст — возвращаем его, выходим
        3. Если модель хочет вызвать инструменты — выполняем, добавляем
           результаты в messages, идём на шаг 1
        4. Если за max_tool_rounds раундов текст так и не получили — ошибка

        Почему messages передаём снаружи а не держим внутри:
        История нужна в нескольких местах (сохранение, /reflect, trim).
        Проще передать ссылку, чем дублировать логику.
        """
        if max_tool_rounds is None:
            max_tool_rounds = self.profile.max_tool_rounds
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
        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = project_dir + (os.pathsep + existing if existing else "")
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
    print("\n[Ouroborus] Запуск рефлексии — читаю собственный код...")
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


def _apply_unified_diff(original: str, diff_text: str) -> tuple[bool, str]:
    """
    Применяет unified diff (формат diff -u) к тексту.
    Возвращает (True, new_code) или (False, error_message).

    Зачем своя реализация вместо patch: независимость от системных утилит,
    работает на Windows и в средах без patch.
    """
    import re
    orig_lines  = original.splitlines(keepends=True)
    result      = list(orig_lines)
    offset      = 0  # смещение индексов из-за уже применённых вставок/удалений

    hunk_re = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", re.MULTILINE)
    matches = list(hunk_re.finditer(diff_text))

    if not matches:
        return False, "Diff не содержит hunks (@@ ... @@). Проверь формат ответа модели."

    for idx, m in enumerate(matches):
        orig_start = int(m.group(1)) - 1  # 0-indexed

        content_start = diff_text.index("\n", m.start()) + 1
        content_end   = matches[idx + 1].start() if idx + 1 < len(matches) else len(diff_text)
        hunk_lines    = diff_text[content_start:content_end].splitlines(keepends=True)

        i = orig_start + offset
        for line in hunk_lines:
            if not line:
                continue
            ch = line[0]
            body = line[1:]
            if not body.endswith("\n"):
                body += "\n"
            if ch == "+":
                result.insert(i, body)
                i += 1
                offset += 1
            elif ch == "-":
                if i < len(result):
                    result.pop(i)
                    offset -= 1
            elif ch == " ":
                i += 1
            # \ No newline at end of file — игнорируем

    return True, "".join(result)


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


def _legacy_evolve_build_prompt(task: str, code: str, principles: str) -> str:
    """Старый single-file промт. Оставлен на случай если кто-то импортирует.

    Используй _evolve_build_messages для мульти-файла."""
    code_lines   = code.splitlines()
    total_lines  = len(code_lines)
    preview_head = "\n".join(code_lines[:80])
    preview_tail = "\n".join(code_lines[-20:]) if total_lines > 100 else ""
    principles_block = (
        f"\nНерушимые принципы (ОБЯЗАН соблюдать):\n{principles}\n"
        if principles else ""
    )
    diff_example = (
        "--- agent.py\n+++ agent.py\n"
        "@@ -1,3 +1,4 @@\n"
        "+# новая строка\n"
        " import os\n"
        " import ast\n"
        " import sys\n"
    )
    return (
        f"Файл agent.py содержит {total_lines} строк. Задача: {task}\n"
        f"{principles_block}\n"
        f"Первые 80 строк (для контекста нумерации):\n"
        f"```python\n{preview_head}\n```\n"
        + (f"\nПоследние 20 строк:\n```python\n{preview_tail}\n```\n" if preview_tail else "")
        + "\nВерни ТОЛЬКО unified diff в формате `diff -u`. "
        "НЕ возвращай полный файл — только diff. "
        "Нумерация строк — как в исходном файле. "
        f"Пример формата:\n{diff_example}"
    )


def _evolve_request_diff(model_chain: list, prompt: str) -> str | None:
    """Зовёт модель за unified diff. Возвращает чистый diff или None если не diff."""
    response = _providers.call(
        model_chain,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        temperature=0.2,
        max_tokens=2048,
    )
    raw_diff = response.choices[0].message.content.strip()

    if raw_diff.startswith("```"):
        raw_diff = "\n".join(
            l for l in raw_diff.splitlines() if not l.strip().startswith("```")
        ).strip()

    if not raw_diff or "@@" not in raw_diff:
        logger.warning(f"Evolve: модель вернула не-diff: {raw_diff[:200]}")
        return None
    return raw_diff


def _evolve_show_diff(raw_diff: str, page_size: int = 60) -> None:
    """Печатает diff пользователю с пагинацией по page_size строк."""
    diff_lines = raw_diff.splitlines(keepends=True)
    print("\n--- ПРЕДЛАГАЕМЫЕ ИЗМЕНЕНИЯ ---")
    if len(diff_lines) > page_size:
        for i in range(0, len(diff_lines), page_size):
            print("".join(diff_lines[i:i + page_size]))
            if i + page_size < len(diff_lines):
                more = input(
                    f"[{i + page_size}/{len(diff_lines)} строк] Показать ещё? [Enter/n]: "
                ).strip().lower()
                if more == "n":
                    print(f"... (пропущено {len(diff_lines) - i - page_size} строк)")
                    break
    else:
        print(raw_diff)
    print("------------------------------")


def _evolve_check_principles(model_chain: list, principles: str, raw_diff: str) -> None:
    """Спрашивает у модели — нарушает ли diff принципы. Только печатает результат."""
    if not principles:
        return
    print("\n[Evolve] Проверяю соответствие принципам...")
    check_prompt = (
        f"Принципы:\n{principles}\n\n"
        f"Diff:\n{raw_diff}\n\n"
        "Нарушает ли diff какой-либо принцип?\n"
        "Отвечай ТОЛЬКО: 'OK' или кратко опиши нарушения."
    )
    try:
        check_resp = _providers.call(
            model_chain,
            messages=[{"role": "user", "content": check_prompt}],
            temperature=0.1,
        )
        check_result = check_resp.choices[0].message.content.strip()
        if check_result.upper() != "OK":
            print(f"\n[!] Патч нарушает принципы:\n{check_result}")
            print("[!] Для применения всё равно введи 'y'.")
        else:
            print("[Evolve] Принципы не нарушены.")
    except Exception as e:
        logger.warning(f"Principles check failed: {e}")
        print("[!] Не удалось проверить принципы. Продолжаю без проверки.")


def _evolve_apply_and_validate(code: str, raw_diff: str) -> tuple[bool, str]:
    """Применяет diff → бэкап → синтаксис → smoke-test.

    Возвращает (True, new_code) при успехе, (False, описание ошибки) — иначе.
    Печатает прогресс пользователю.
    """
    ok, result = _apply_unified_diff(code, raw_diff)
    if not ok:
        return False, f"не удалось применить diff: {result}"
    new_code = result

    print("[Evolve] Создаю резервную копию...")
    backup_path = backup_agent()
    print(f"[Evolve] Бэкап: {backup_path}")

    print("[Evolve] Проверяю синтаксис...")
    valid, error = validate_code(new_code)
    if not valid:
        return False, f"синтаксическая ошибка: {error}"
    print("[Evolve] Синтаксис OK.")

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(new_code)
        tmp_path = tmp.name

    print("[Evolve] Запускаю smoke-test...")
    passed, error = smoke_test(tmp_path)
    os.unlink(tmp_path)
    if not passed:
        return False, f"smoke-test провалился: {error}"
    print("[Evolve] Smoke-test OK.")

    return True, new_code


def evolve(task: str) -> None:
    """Мульти-файл эволюция через /evolve.

    Мира получает задачу и инструменты для исследования (read_self, list_self,
    openrouter_list_models, web_search). Возвращает мульти-файл unified diff.
    Diff проходит через safe_apply: whitelist → валидация → атомарная запись
    → smoke-test → откат при любой ошибке.
    """
    from tools.safe_apply import safe_apply as _safe_apply

    model_chain = alpha.model_chain if alpha else []
    if not model_chain:
        print("[-] Нет настроенных провайдеров для /evolve.")
        return

    print(f"\n[Ouroborus] Эволюция: '{task}'...")
    logger.info(f"Команда /evolve: {task}")

    if not ensure_dev_branch():
        print("[!] Не удалось переключиться на mira-dev. Продолжаю на текущей ветке.")

    principles = load_principles()
    evolve_agent = _evolve_make_readonly_agent(model_chain, profile)
    messages = _evolve_build_messages(task, principles)

    try:
        print("[Evolve] Мира исследует код и формирует diff...")
        response_text = evolve_agent.run(messages, max_tool_rounds=20)
    except Exception as e:
        print(f"[-] Ошибка при генерации: {e}")
        logger.error(f"Evolve generation error: {e}", exc_info=True)
        increment_evolution(success=False)
        return

    raw_diff = _evolve_extract_diff(response_text)
    if not raw_diff:
        print("[-] Мира не вернула diff. Её ответ:")
        print(response_text[:1500])
        increment_evolution(success=False)
        return

    _evolve_show_diff(raw_diff)

    confirm = input("\nПрименить изменения? [y/N]: ").strip().lower()
    if confirm != "y":
        print("[Evolve] Изменения отклонены.")
        logger.info("Evolve: отклонены пользователем")
        return

    print("[Evolve] Применяю атомарно (бэкап → валидация → smoke-test)...")
    result = _safe_apply(raw_diff, project_root=".")

    if not result.ok:
        print(f"[-] {result.message}")
        if result.backup_dir:
            print(f"[i] Откат сделан из {result.backup_dir}")
        logger.error(f"Evolve apply failed: {result.message}")
        increment_evolution(success=False)
        return

    increment_evolution(success=True)
    print(f"[*] {result.message}")
    print(f"[*] Затронуто: {', '.join(result.touched_paths)}")
    print(f"[*] Бэкап: {result.backup_dir}")
    print("[*] Перезапусти агента чтобы изменения вступили в силу.")
    print("[*] Когда готов к релизу — /release.")
    logger.info(f"Evolve OK: {result.touched_paths}")


# ---------------------------------------------------------------------------
# Парсинг провайдеров из .env
# ---------------------------------------------------------------------------
providers = set()
for key in os.environ:
    if key.startswith("API_") and key.endswith("_KEY"):
        providers.add(key[4:-4])

for provider in sorted(providers):
    # Anthropic обрабатывается нативным SDK в providers.py — пропускаем здесь
    if provider == "ANTHROPIC":
        continue

    api_key    = os.getenv(f"API_{provider}_KEY")
    base_url   = os.getenv(f"API_{provider}_URL")
    models_str = os.getenv(f"API_{provider}_MODELS")

    if not api_key or not models_str:
        msg = f"Провайдер {provider} пропущен: нет ключа или списка моделей."
        print(f"[-] {msg}")
        logger.warning(msg)
        continue

    for model_name in [m.strip() for m in models_str.split(",")]:
        MODELS_CONFIG[str(counter)] = {
            "label":    f"{provider} - {model_name}",
            "base_url": base_url,
            "model":    model_name,
            "api_key":  api_key,
        }
        counter += 1

# ---------------------------------------------------------------------------
# Вспомогательные функции CLI
# ---------------------------------------------------------------------------
def setup_client(choice_id: str):
    config = MODELS_CONFIG.get(choice_id)
    if not config:
        return None, None
    client = OpenAI(api_key=config["api_key"], base_url=config["base_url"])
    return client, config


def print_menu() -> None:
    print("\n--- Доступные модели ---")
    if not MODELS_CONFIG:
        print("Модели не найдены. Проверь .env!")
    for key, cfg in MODELS_CONFIG.items():
        print(f"[{key}] {cfg['label']}")
    print("------------------------")


def print_help() -> None:
    print("""
Команды:
  exit / quit          — завершить работу
  /switch              — сменить модель
  /git [msg]           — закоммитить и запушить код
  /reflect             — агент читает свой код и анализирует себя
  /evolve <задача>     — агент предлагает патч к своему коду (ветка mira-dev)
  /release             — смержить mira-dev в main и запушить
  /rollback [номер]    — откатить agent.py на предыдущую версию
  /versions            — список резервных копий
  /undo                — восстановить последний перезаписанный файл
  /reload              — перезагрузить персону из persona.json (без рестарта)
  /clear               — очистить историю разговора
  /whoami              — что Мира знает о тебе
  /forget              — сбросить профиль, начать знакомство заново
  /cloud sync          — синхронизировать memory/ и versions/ в облако
  /cloud restore       — восстановить из облака
  /users               — список пользователей (только owner)
  /approve <id> [имя]  — одобрить гостя (только owner)
  /reject <id>         — отклонить и удалить гостя (только owner)
  /block <id>          — заблокировать пользователя (только owner)
  /unblock <id>        — снять блокировку (только owner)
  /stop                — остановить работу Конклава между итерациями
  /help                — эта справка
""")


# ---------------------------------------------------------------------------
# Точка входа — только при прямом запуске python agent.py
# При импорте (telegram_bot.py) этот блок не выполняется,
# но все классы, функции и TOOL_SCHEMAS доступны.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    messages = load_history()
    current_client, current_config = setup_client("1")

    # Инициализируем Альфу — главного агента.
    # Если agents/alpha.json не найден — работаем в fallback-режиме.
    alpha: Agent | None = None
    try:
        alpha = Agent.from_config_file("alpha", profile, "", SYSTEM_PROMPT)
    except FileNotFoundError as e:
        print(f"[!] {e}")
        print("[!] Работаю без класса Agent.")
        logger.warning(f"Agent config not found: {e}")

    # ---------------------------------------------------------------------------
    # Идентификация пользователя и онбординг (Этап 0.5)
    # ---------------------------------------------------------------------------
    os.makedirs(MEMORY_DIR, exist_ok=True)
    os.makedirs(MEMORY_SESSIONS_DIR, exist_ok=True)

    current_user_id = identify_user()
    if alpha:
        alpha.user_id = current_user_id  # агент теперь знает с кем работает

    # Инициализируем Конклав — передаём инструменты чтобы executor-агенты
    # могли реально писать файлы и запускать код, а не только описывать как это сделать.
    conclave = Conclave(
        system_prompt=SYSTEM_PROMPT,
        user_id=current_user_id,
        profile=profile,
        tool_schemas=TOOL_SCHEMAS,
        execute_tool_fn=execute_tool,
    )

    # Создаём структуру папок для пользователя
    for subdir in ("inbox", "output", "temp", ".undo"):
        os.makedirs(os.path.join(WORKSPACE_DIR, current_user_id, subdir), exist_ok=True)

    # Автоочистка temp/ (файлы старше 7 дней) и просроченных гостей
    cleanup_temp(current_user_id)
    expired = cleanup_expired_guests()
    if expired:
        logger.info(f"Удалено просроченных гостей: {expired}")

    user_profile = load_user_profile(current_user_id)
    is_returning = user_profile is not None  # запоминаем ДО онбординга

    # Определяем статус: владелец ли это?
    owner_cli = os.getenv("OWNER_CLI_USER", "").strip()
    is_owner_login = owner_cli and current_user_id == f"cli_{owner_cli}"

    if user_profile is None:
        # Первый запуск — онбординг
        onboard_chain = alpha.model_chain if alpha else []
        if onboard_chain and _providers.PROVIDERS:
            user_profile = run_onboarding(onboard_chain, current_user_id)
        else:
            print("[-] Провайдеры не настроены, онбординг пропущен. Проверь .env")
            user_profile = {"id": current_user_id, "name": current_user_id.replace("cli_", ""), "sessions_count": 0}
        # Ставим статус сразу при создании
        user_profile["status"] = "owner" if is_owner_login else "regular"
        save_user_profile(current_user_id, user_profile)
    else:
        # Не первый запуск — обновляем счётчик
        update_last_seen(current_user_id, user_profile)
        # Обновляем owner-статус если владелец изменился
        if is_owner_login and user_profile.get("status") != "owner":
            user_profile["status"] = "owner"
            save_user_profile(current_user_id, user_profile)

    user_status = user_profile.get("status", "regular")

    print("=== Mira запущена ===")
    print(f"Персона загружена из: {PERSONA_FILE}")
    print(f"Профиль: {profile.name}  |  Инструменты: {', '.join(profile.allowed_tools) or 'нет'}")
    print(f"Пользователь: {current_user_id}  |  Статус: {user_status}")
    if _providers.PROVIDERS:
        first_chain = alpha.model_chain[0] if alpha else {}
        all_providers = list(_providers.PROVIDERS.keys())
        if _providers._anthropic_client:
            all_providers.append("anthropic(native)")
        print(f"Провайдеры: {', '.join(all_providers)}")
        if first_chain:
            print(f"Основная модель: {first_chain.get('provider')}/{first_chain.get('model')}")
        logger.info(f"Провайдеры: {all_providers}")
    else:
        print("[-] Провайдеры не настроены. Проверь .env файл.")
        logger.warning("Провайдеры не настроены.")

    # Приветствие только вернувшимся пользователям, не новым
    if is_returning and user_profile and "name" in user_profile:
        print(f"\n[Мира] С возвращением, {user_profile['name']}.")

    print_help()

    # ---------------------------------------------------------------------------
    # Главный цикл
    # ---------------------------------------------------------------------------
    while True:
        try:
            user_input = input("\nТы: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nЗавершение работы...")
            logger.info("Агент остановлен через Ctrl+C / EOF.")
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        # --- Выход (с авто-синхронизацией) ---
        if cmd in ("exit", "quit", "выход"):
            print("Завершение работы...")
            logger.info("Штатное завершение работы агента.")
            if os.getenv("RCLONE_REMOTE"):
                print("[Cloud] Синхронизирую перед выходом...")
                cloud_sync()
            break

        # --- Контроль доступа ---
        if user_status == "blocked":
            print("[Мира] Доступ закрыт.")
            continue

        # --- Кто я ---
        if cmd == "/whoami":
            if user_profile:
                print("\n--- Что Мира знает о тебе ---")
                print(json.dumps(user_profile, ensure_ascii=False, indent=2))
            else:
                print("[-] Профиль не найден.")
            continue

        # --- Сброс профиля ---
        if cmd == "/forget":
            confirm = input("[!] Сбросить профиль и начать знакомство заново? [y/N]: ").strip().lower()
            if confirm == "y":
                delete_user_profile(current_user_id)
                print("[*] Профиль удалён.")
                if alpha and _providers.PROVIDERS:
                    user_profile = run_onboarding(alpha.model_chain, current_user_id)
                logger.info(f"Профиль сброшен: {current_user_id}")
            else:
                print("[*] Отмена.")
            continue

        # --- Справка ---
        if cmd == "/help":
            print_help()
            continue

        # --- /undo ---
        if cmd == "/undo":
            backups = list_undo(current_user_id)
            if not backups.get("backups"):
                print("[-] Нет сохранённых версий для восстановления.")
            else:
                result = undo_last(current_user_id)
                if result.get("ok"):
                    print(f"[*] Восстановлено в: {result['restored']}")
                else:
                    print(f"[-] {result.get('error')}")
            continue

        # --- /cloud ---
        if cmd.startswith("/cloud"):
            parts = cmd.split(maxsplit=1)
            sub = parts[1].strip() if len(parts) > 1 else ""
            if sub == "sync":
                cloud_sync()
            elif sub == "restore":
                cloud_restore()
            else:
                print("[-] Использование: /cloud sync  или  /cloud restore")
            continue

        # --- Управление пользователями (только owner) ---
        if cmd == "/users":
            if user_status != "owner":
                print("[-] Только для владельца.")
                continue
            users = list_users()
            if not users:
                print("[-] Пользователей нет.")
            else:
                print("\n--- Пользователи ---")
                for u in users:
                    print(f"  {u['id']:25} | {u['status']:8} | last: {u['last_seen']} | msgs: {u.get('guest_msgs', 0)}")
            continue

        if cmd.startswith("/approve"):
            if user_status != "owner":
                print("[-] Только для владельца."); continue
            parts = user_input.split(maxsplit=2)
            if len(parts) < 2:
                print("[-] /approve <user_id> [новое_имя]"); continue
            uid, new_name = parts[1], (parts[2] if len(parts) > 2 else "")
            print("[*] Одобрено." if approve(uid, new_name) else "[-] Пользователь не найден.")
            continue

        if cmd.startswith("/reject"):
            if user_status != "owner":
                print("[-] Только для владельца."); continue
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2:
                print("[-] /reject <user_id>"); continue
            print("[*] Удалён." if reject(parts[1]) else "[-] Пользователь не найден.")
            continue

        if cmd.startswith("/block"):
            if user_status != "owner":
                print("[-] Только для владельца."); continue
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2:
                print("[-] /block <user_id>"); continue
            print("[*] Заблокирован." if block(parts[1]) else "[-] Не удалось.")
            continue

        if cmd.startswith("/unblock"):
            if user_status != "owner":
                print("[-] Только для владельца."); continue
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2:
                print("[-] /unblock <user_id>"); continue
            print("[*] Разблокирован." if unblock(parts[1]) else "[-] Не удалось.")
            continue

        # --- Очистка памяти ---
        if cmd == "/clear":
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            save_history(messages)
            print("[*] Память агента очищена.")
            logger.info("Память очищена пользователем.")
            continue

        # --- Git ---
        if cmd.startswith("/git"):
            if user_status != "owner":
                print("[-] /git доступен только владельцу.")
                continue
            parts = user_input.split(maxsplit=1)
            commit_msg = parts[1] if len(parts) > 1 else "Auto-commit: update agent.py"
            sync_with_git(commit_msg)
            continue

        # --- Смена модели ---
        if cmd == "/switch":
            print_menu()
            choice = input("Выбери номер модели (или Enter для отмены): ").strip()
            if choice in MODELS_CONFIG:
                try:
                    new_client, new_config = setup_client(choice)
                    if new_client:
                        current_client = new_client
                        current_config = new_config
                        print(f"[*] Переключено на: {current_config['label']}")
                        logger.info(f"Переключение модели на: {current_config['label']}")
                except Exception as e:
                    print(f"[-] Не удалось подключиться к модели: {e}")
                    logger.error(f"Switch error: {e}")
            else:
                print("[-] Отмена или неверный выбор.")
            continue

        # --- Перезагрузка персоны ---
        if cmd == "/reload":
            reload_persona(messages)
            save_history(messages)
            continue

        # --- Рефлексия ---
        if cmd == "/reflect":
            if alpha and _providers.PROVIDERS:
                reflect(alpha.model_chain, messages)
            else:
                print("[-] Провайдеры не настроены. Проверь .env.")
            continue

        # --- Релиз (mira-dev → main) ---
        if cmd == "/release":
            if user_status != "owner" or not profile.can_use("evolve"):
                print("[-] /release доступен только владельцу с профилем dev.")
                continue
            confirm = input("[!] Смержить mira-dev в main и запушить? [y/N]: ").strip().lower()
            if confirm == "y":
                release_to_main()
            else:
                print("[*] Отмена.")
            continue

        # --- Эволюция ---
        if cmd.startswith("/evolve"):
            if user_status != "owner" or not profile.can_use("evolve"):
                print("[-] /evolve доступен только владельцу с профилем dev.")
                print("    Запусти агента с: python agent.py --profile dev")
                continue
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                print("[-] Укажи задачу: /evolve <описание что изменить>")
            elif _providers.PROVIDERS:
                evolve(parts[1].strip())
            else:
                print("[-] Провайдеры не настроены. Проверь .env.")
            continue

        # --- Откат ---
        if cmd.startswith("/rollback"):
            parts = user_input.split(maxsplit=1)
            if len(parts) > 1 and parts[1].strip().isdigit():
                # Выбор конкретной версии по номеру из /versions
                idx = int(parts[1].strip()) - 1
                if os.path.isdir(VERSIONS_DIR):
                    backups = sorted([
                        f for f in os.listdir(VERSIONS_DIR)
                        if f.startswith("agent_") and f.endswith(".py")
                    ])
                    if 0 <= idx < len(backups):
                        rollback(os.path.join(VERSIONS_DIR, backups[idx]))
                    else:
                        print(f"[-] Нет резервной копии с номером {idx + 1}. Посмотри /versions.")
                else:
                    print("[-] Папка versions/ не найдена.")
            else:
                rollback()
            continue

        # --- Список резервных копий ---
        if cmd == "/versions":
            list_backups()
            continue

        # --- Стоп Конклава ---
        if cmd == "/stop":
            conclave.should_stop = True
            print("[*] Конклав остановится после текущего шага.")
            continue

        # --- Обычный чат ---
        if not _providers.PROVIDERS:
            print("[-] Провайдеры не настроены. Проверь .env.")
            continue

        # Гостевой лимит
        if user_status == "guest":
            count, limit = increment_guest_counter(current_user_id, user_profile)
            remaining = limit - count
            if count > limit:
                print(f"[Мира] Лимит {limit} сообщений исчерпан. Жду решения хозяина.")
                continue
            elif remaining <= 3:
                print(f"[Мира] (осталось {remaining} сообщений из {limit})")

        messages.append({"role": "user", "content": user_input})
        messages = trim_history(messages)
        # Обновляем дату/время в системном промпте
        fresh_system = SYSTEM_PROMPT + f"\n\n{time_context()}"
        for m in messages:
            if m["role"] == "system":
                m["content"] = fresh_system
                break
        logger.info(f"User: {user_input}")

        # Классифицируем задачу — дёшево, один вызов
        conclave.should_stop = False  # сбрасываем флаг перед новым запросом
        # (executor, skip_editor, parallel_scout)
        _EXECUTOR_FOR = {
            "search":  ("scout", True,  False),  # поиск — без редактора
            "code":    ("coder", False, False),  # код — полный цикл
            "complex": ("coder", False, True),   # сложное — scout параллельно
        }

        task_type = classify(user_input, alpha.model_chain if alpha else [])

        try:
            if task_type in _EXECUTOR_FOR and alpha:
                # Передаём в Конклав: executor → editor → critic
                executor, skip_editor, parallel_scout = _EXECUTOR_FOR[task_type]
                logger.info(f"Conclave activated: task_type={task_type}, executor={executor}")

                raw = conclave.run_with_qa(user_input, executor,
                                           skip_editor=skip_editor,
                                           parallel_scout=parallel_scout)

                # Альфа оформляет результат своим голосом
                presentation = (
                    f"Специалисты выполнили задачу. "
                    f"Представь результат пользователю от своего имени:\n\n{raw}"
                )
                alpha_messages = [
                    {"role": "system",    "content": SYSTEM_PROMPT},
                    {"role": "user",      "content": user_input},
                    {"role": "assistant", "content": "[передала специалистам]"},
                    {"role": "user",      "content": presentation},
                ]
                answer = _providers.call(
                    alpha.model_chain, alpha_messages, temperature=0.7
                ).choices[0].message.content
                messages.append({"role": "assistant", "content": answer})

            elif alpha:
                answer = alpha.run(messages)

            else:
                # Fallback без класса Agent
                fallback_chain = [{"provider": _providers.first_model_name(),
                                   "model": "", "temperature": 0.7}]
                response = _providers.call(fallback_chain, messages,
                                           tools=TOOL_SCHEMAS, tool_choice="auto")
                msg = response.choices[0].message
                answer = msg.content
                messages.append({"role": "assistant", "content": answer})

            if answer:
                print(f"\nМира: {answer}")
                logger.info(f"Agent: {answer[:120]}")
                save_history(messages)

        except Exception as e:
            print("\n[Ошибка API]: Подробности записаны в лог.")
            logger.error(f"API Error: {e}", exc_info=True)
            if messages and messages[-1]["role"] == "user":
                messages.pop()

