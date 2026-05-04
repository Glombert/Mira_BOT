import os
import ast
import sys
import json
import shutil
import argparse
import subprocess
import tempfile
import logging
import difflib
from datetime import datetime
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from openai import OpenAI

# ---------------------------------------------------------------------------
# Настройка логирования
# ---------------------------------------------------------------------------
logger = logging.getLogger("Ouroborus")
logger.setLevel(logging.INFO)

log_handler = RotatingFileHandler(
    "agent.log",
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8"
)
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
MAX_HISTORY   = 40    # сколько последних сообщений держать в контексте
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


def get_user_profile_path(user_id: str) -> str:
    """Возвращает путь к файлу профиля пользователя."""
    return os.path.join(MEMORY_DIR, f"{user_id}.json")


def load_user_profile(user_id: str) -> dict | None:
    """
    Загружает профиль пользователя из memory/{user_id}.json.
    Возвращает dict если файл есть, None если нет (первый запуск).
    """
    path = get_user_profile_path(user_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка чтения профиля {user_id}: {e}")
        return None


def save_user_profile(user_id: str, data: dict) -> None:
    """Сохраняет профиль пользователя в memory/{user_id}.json."""
    os.makedirs(MEMORY_DIR, exist_ok=True)
    path = get_user_profile_path(user_id)
    data["updated_at"] = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Профиль пользователя сохранён: {path}")
    except Exception as e:
        logger.error(f"Ошибка сохранения профиля {user_id}: {e}")


def run_onboarding(client: OpenAI, model: str, user_id: str) -> dict:
    """
    Онбординг — знакомство с новым пользователем через диалог.

    Мира задаёт вопросы по одному, пользователь отвечает.
    После 3-4 обменов — один API-вызов структурирует профиль в JSON.
    Сохраняет и возвращает готовый профиль.
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
            response = client.chat.completions.create(
                model=model,
                messages=onboarding_history,
                temperature=0.7,
            )
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
        response = client.chat.completions.create(
            model=model,
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

def load_persona() -> str:
    """Загружает персону из persona.json и собирает системный промпт."""
    try:
        with open(PERSONA_FILE, "r", encoding="utf-8") as f:
            p = json.load(f)

        b = p.get("boundaries", {})
        dislikes = "\n".join(f"— {d}" for d in b.get("dislikes", []))
        style_items = "\n".join(f"— {v}" for v in p.get("communication", {}).values())

        return f"""Тебя зовут {p["name"]}. {p["origin"]}
{p["core"]}
Любопытство: {p["curiosity"]}
Эмоции:
— {p["emotions"]["frustration"]}
— {p["emotions"]["joy"]}
— {p["emotions"]["pride"]}
Как ты общаешься:
{style_items}
Конклав: {p["conclave"]}
Границы:
{dislikes}
{b.get("reaction", "")}
{p["notes"]}"""
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


SYSTEM_PROMPT = load_persona()

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
# Git
# ---------------------------------------------------------------------------
def get_current_branch() -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True, text=True
    )
    return result.stdout.strip() or "main"


def sync_with_git(commit_message: str = "Auto-update from Ouroborus agent") -> None:
    print("\n[Git] Запуск синхронизации...")
    logger.info(f"Запуск синхронизации Git. Коммит: {commit_message}")
    try:
        # Добавляем только конкретные файлы, не всё подряд
        # .env, memory/, workspace/ защищены .gitignore, но явный список надёжнее
        safe_patterns = ["agent.py", "persona.json", "agents/", "profiles/",
                         "tools/", "PLAN.md", "ARCHITECTURE.md", "README.md",
                         "requirements.txt", ".gitignore"]
        for pattern in safe_patterns:
            subprocess.run(["git", "add", pattern],
                           capture_output=True, text=True)  # не check=True — файла может не быть

        status = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True
        )
        if not status.stdout.strip():
            print("[Git] Нет новых изменений для отправки.")
            logger.info("Git: Нет изменений для коммита.")
            return

        subprocess.run(
            ["git", "commit", "-m", commit_message],
            check=True, capture_output=True, text=True
        )

        branch = get_current_branch()
        print(f"[Git] Отправка ветки '{branch}' на удалённый сервер...")
        subprocess.run(
            ["git", "push", "--set-upstream", "origin", branch],
            check=True, capture_output=True, text=True
        )

        print("[*] Успешно синхронизировано с репозиторием!")
        logger.info("Git: Успешная синхронизация.")

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else str(e)
        print(f"[-] Ошибка Git: {error_msg}")
        logger.error(f"Git Error: {error_msg}")
    except FileNotFoundError:
        print("[-] Утилита git не найдена в системе.")
        logger.error("Git Error: утилита git не найдена.")


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
        result = subprocess.run(
            [sys.executable, code_path, "--self-test"],
            capture_output=True, text=True, timeout=10
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


def reflect(client: OpenAI, model: str, messages: list) -> None:
    """
    Агент читает свой код и даёт аналитику:
    что работает хорошо, что можно улучшить.
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
        response = client.chat.completions.create(
            model=model, messages=temp_messages, temperature=0.5
        )
        analysis = response.choices[0].message.content
        print(f"\n[Рефлексия]:\n{analysis}")
        logger.info("Рефлексия завершена.")

        messages.append({"role": "user",      "content": "[REFLECT] Проанализируй свой код."})
        messages.append({"role": "assistant", "content": analysis})
        save_history(messages)

    except Exception as e:
        print(f"[-] Ошибка при рефлексии: {e}")
        logger.error(f"Reflect Error: {e}", exc_info=True)


def evolve(client: OpenAI, model: str, task: str) -> None:
    """
    Агент предлагает конкретный патч к своему коду под задачу.
    
    Порядок действий (защищённый):
    1. Бэкап текущего кода в versions/
    2. Генерация нового кода через API
    3. Показ diff пользователю
    4. Подтверждение
    5. Валидация синтаксиса (ast.parse)
    6. Smoke-test в подпроцессе (--self-test)
    7. Запись — только если всё прошло
    Файл не перезаписывается если что-то упало на шагах 5–6.
    """
    print(f"\n[Ouroborus] Генерирую патч для задачи: '{task}'...")
    logger.info(f"Команда /evolve: задача — {task}")

    code = read_own_code()
    if not code:
        print("[-] Не удалось прочитать код для эволюции.")
        return

    prompt = (
        f"Ниже — твой текущий исходный код. Задача: {task}\n\n"
        "Верни ТОЛЬКО полный обновлённый файл agent.py — никаких пояснений, "
        "никаких markdown-блоков, только чистый Python-код. "
        "Не меняй то, что не относится к задаче.\n\n"
        f"{code}"
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt}
            ],
            temperature=0.3,
            max_tokens=4096
        )
        new_code = response.choices[0].message.content.strip()

        # Убираем возможные ```python / ``` обёртки
        if new_code.startswith("```"):
            lines = new_code.splitlines()
            new_code = "\n".join(
                l for l in lines if not l.strip().startswith("```")
            )

        # Показываем diff
        diff = list(difflib.unified_diff(
            code.splitlines(keepends=True),
            new_code.splitlines(keepends=True),
            fromfile="agent.py (текущий)",
            tofile="agent.py (предлагаемый)",
            n=3
        ))

        if not diff:
            print("[Evolve] Модель не нашла что менять — код уже соответствует задаче.")
            return

        print("\n--- ПРЕДЛАГАЕМЫЕ ИЗМЕНЕНИЯ ---")
        diff_lines = diff
        page_size = 60
        if len(diff_lines) > page_size:
            for i in range(0, len(diff_lines), page_size):
                chunk = diff_lines[i:i + page_size]
                print("".join(chunk))
                if i + page_size < len(diff_lines):
                    more = input(f"[{i + page_size}/{len(diff_lines)} строк] Показать ещё? [Enter/n]: ").strip().lower()
                    if more == "n":
                        print(f"... (пропущено {len(diff_lines) - i - page_size} строк)")
                        break
        else:
            print("".join(diff_lines))
        print("------------------------------")

        confirm = input("\nПрименить изменения? [y/N]: ").strip().lower()
        if confirm != "y":
            print("[Evolve] Изменения отклонены.")
            logger.info("Evolve: изменения отклонены пользователем.")
            return

        # --- Шаг 1: Бэкап ---
        print("[Evolve] Создаю резервную копию...")
        backup_path = backup_agent()
        print(f"[Evolve] Бэкап: {backup_path}")

        # --- Шаг 2: Валидация синтаксиса ---
        print("[Evolve] Проверяю синтаксис...")
        valid, error = validate_code(new_code)
        if not valid:
            print(f"[-] Код не прошёл проверку синтаксиса: {error}")
            print("[-] Изменения не применены. Бэкап сохранён на случай если нужен.")
            logger.error(f"Evolve: синтаксическая ошибка — {error}")
            return

        print("[Evolve] Синтаксис OK.")

        # --- Шаг 3: Записываем новый код во временный файл для smoke-test ---
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(new_code)
            tmp_path = tmp.name

        # --- Шаг 4: Smoke-test ---
        print("[Evolve] Запускаю smoke-test...")
        passed, error = smoke_test(tmp_path)
        os.unlink(tmp_path)  # удаляем временный файл

        if not passed:
            print(f"[-] Smoke-test провалился: {error}")
            print("[-] Изменения не применены. Агент в безопасности.")
            logger.error(f"Evolve: smoke-test провалился — {error}")
            return

        print("[Evolve] Smoke-test OK.")

        # --- Шаг 5: Записываем финально ---
        with open(AGENT_FILE, "w", encoding="utf-8") as f:
            f.write(new_code)

        print("[*] Код обновлён. Перезапусти агента для применения.")
        logger.info(f"Evolve: код успешно обновлён. Задача: {task}")

    except Exception as e:
        print(f"[-] Ошибка при генерации патча: {e}")
        logger.error(f"Evolve Error: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# Парсинг провайдеров из .env
# ---------------------------------------------------------------------------
providers = set()
for key in os.environ:
    if key.startswith("API_") and key.endswith("_KEY"):
        providers.add(key[4:-4])

for provider in sorted(providers):
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
  /evolve <задача>     — агент предлагает патч к своему коду
  /rollback [номер]    — откатить agent.py на предыдущую версию
  /versions            — список резервных копий
  /reload              — перезагрузить персону из persona.json (без рестарта)
  /clear               — очистить историю разговора
  /whoami              — что Мира знает о тебе
  /forget              — сбросить профиль, начать знакомство заново
  /help                — эта справка
""")


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------
messages = load_history()
current_client, current_config = setup_client("1")

# ---------------------------------------------------------------------------
# Идентификация пользователя и онбординг (Этап 0.5)
# ---------------------------------------------------------------------------
os.makedirs(MEMORY_DIR, exist_ok=True)
os.makedirs(MEMORY_SESSIONS_DIR, exist_ok=True)

current_user_id = identify_user()

# Создаём структуру папок для пользователя
for subdir in ("inbox", "output", "temp"):
    os.makedirs(os.path.join(WORKSPACE_DIR, current_user_id, subdir), exist_ok=True)

# Автоочистка temp/ (файлы старше 7 дней)
cleanup_temp(current_user_id)
user_profile = load_user_profile(current_user_id)
is_returning = user_profile is not None  # запоминаем ДО онбординга

if user_profile is None:
    # Первый запуск — онбординг
    if current_client:
        user_profile = run_onboarding(current_client, current_config["model"], current_user_id)
    else:
        print("[-] Модель не настроена, онбординг пропущен. Проверь .env")
        user_profile = {"id": current_user_id, "name": current_user_id.replace("cli_", ""), "sessions_count": 0}
else:
    # Не первый запуск — обновляем счётчик
    update_last_seen(current_user_id, user_profile)

print("=== Mira запущена ===")
print(f"Персона загружена из: {PERSONA_FILE}")
print(f"Профиль: {profile.name}  |  Инструменты: {', '.join(profile.allowed_tools) or 'нет'}")
print(f"Пользователь: {current_user_id}")
if current_config:
    print(f"Текущая модель: {current_config['label']}")
    logger.info(f"Выбрана стартовая модель: {current_config['label']}")
else:
    print("[-] Конфигурация не загружена. Проверь .env файл.")
    logger.warning("Конфигурация моделей не загружена.")

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

    # --- Выход ---
    if cmd in ("exit", "quit", "выход"):
        print("Завершение работы...")
        logger.info("Штатное завершение работы агента.")
        break

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
            path = get_user_profile_path(current_user_id)
            if os.path.exists(path):
                os.remove(path)
            print("[*] Профиль удалён.")
            if current_client:
                user_profile = run_onboarding(current_client, current_config["model"], current_user_id)
            logger.info(f"Профиль сброшен: {current_user_id}")
        else:
            print("[*] Отмена.")
        continue

    # --- Справка ---
    if cmd == "/help":
        print_help()
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
        if current_client:
            reflect(current_client, current_config["model"], messages)
        else:
            print("[-] Модель не настроена. Введи /switch.")
        continue

    # --- Эволюция ---
    if cmd.startswith("/evolve"):
        parts = user_input.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            print("[-] Укажи задачу: /evolve <описание что изменить>")
        elif current_client:
            evolve(current_client, current_config["model"], parts[1].strip())
        else:
            print("[-] Модель не настроена. Введи /switch.")
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

    # --- Обычный чат ---
    if not current_client:
        print("[-] Модель не настроена. Введи /switch для выбора.")
        continue

    messages.append({"role": "user", "content": user_input})
    messages = trim_history(messages)  # сразу обрезаем в памяти, не только при сохранении
    logger.info(f"User: {user_input}")

    try:
        response = current_client.chat.completions.create(
            model=current_config["model"],
            messages=messages,
            temperature=0.7,
        )
        answer = response.choices[0].message.content
        print(f"\nАгент [{current_config['label']}]: {answer}")

        messages.append({"role": "assistant", "content": answer})
        logger.info(f"Agent [{current_config['model']}]: {answer}")
        save_history(messages)

    except Exception as e:
        print(f"\n[Ошибка API]: Подробности записаны в лог.")
        logger.error(f"API Error ({current_config['label']}): {e}", exc_info=True)
        messages.pop()
