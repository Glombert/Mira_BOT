"""
tools/git_tools.py — инструменты для работы с Git.

Вынесены из agent.py в Этапе 1.1 чтобы уменьшить размер ядра.
Вызываются через команду /git внутри главного цикла.

Что умеет:
- get_current_branch()  — определить текущую ветку
- sync_with_git()       — добавить безопасные файлы, сделать коммит и пуш
- ensure_dev_branch()   — переключиться на mira-dev (создать если нет)
- release_to_main()     — смержить mira-dev в main и запушить
"""

import subprocess
import logging

logger = logging.getLogger("Ouroborus")

# Файлы и папки которые безопасно добавлять в git.
# .env, memory/, workspace/ защищены .gitignore,
# но явный список надёжнее — не попадём лишнего случайно.
SAFE_GIT_PATTERNS = [
    "agent.py", "persona.json", "agents/", "profiles/",
    "tools/", "PLAN.md", "ARCHITECTURE.md", "README.md",
    "requirements.txt", ".gitignore"
]


def get_current_branch() -> str:
    """Возвращает имя текущей ветки. Если не удалось — 'main'."""
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True, text=True
    )
    return result.stdout.strip() or "main"


def sync_with_git(commit_message: str = "Auto-update from Ouroborus agent") -> None:
    """
    Добавляет безопасные файлы, создаёт коммит и пушит в текущую ветку.

    Аргументы:
        commit_message — сообщение коммита. По умолчанию автоматическое.

    Не падает если нет изменений — просто сообщает об этом.
    """
    print("\n[Git] Запуск синхронизации...")
    logger.info(f"Запуск синхронизации Git. Коммит: {commit_message}")

    try:
        # Добавляем только конкретные файлы из белого списка
        for pattern in SAFE_GIT_PATTERNS:
            subprocess.run(
                ["git", "add", pattern],
                capture_output=True, text=True
                # не check=True — файла может не быть, это нормально
            )

        # Проверяем есть ли вообще что коммитить
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True
        )
        if not status.stdout.strip():
            print("[Git] Нет новых изменений для отправки.")
            logger.info("Git: Нет изменений для коммита.")
            return

        # Коммит
        subprocess.run(
            ["git", "commit", "-m", commit_message],
            check=True, capture_output=True, text=True
        )

        # Пуш в текущую ветку
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


DEV_BRANCH = "mira-dev"


def ensure_dev_branch() -> bool:
    """
    Переключается на mira-dev. Создаёт ветку если её нет.
    Возвращает True если успешно, False при ошибке.

    /evolve вызывает эту функцию до генерации патча — чтобы
    изменения кода никогда не попадали напрямую в main.
    """
    try:
        current = get_current_branch()
        if current == DEV_BRANCH:
            return True

        # Проверяем существует ли ветка локально
        result = subprocess.run(
            ["git", "branch", "--list", DEV_BRANCH],
            capture_output=True, text=True
        )
        branch_exists = bool(result.stdout.strip())

        if branch_exists:
            subprocess.run(
                ["git", "checkout", DEV_BRANCH],
                check=True, capture_output=True, text=True
            )
        else:
            # Создаём ветку от текущего HEAD
            subprocess.run(
                ["git", "checkout", "-b", DEV_BRANCH],
                check=True, capture_output=True, text=True
            )
            subprocess.run(
                ["git", "push", "--set-upstream", "origin", DEV_BRANCH],
                capture_output=True, text=True
                # не check=True — remote может не быть, не критично
            )
            print(f"[Git] Создана ветка '{DEV_BRANCH}'.")

        logger.info(f"Git: переключились на '{DEV_BRANCH}'.")
        return True

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else str(e)
        print(f"[-] Не удалось переключиться на {DEV_BRANCH}: {error_msg}")
        logger.error(f"ensure_dev_branch error: {error_msg}")
        return False

    except FileNotFoundError:
        print("[-] Утилита git не найдена.")
        return False


def release_to_main() -> bool:
    """
    Мерджит mira-dev в main и пушит оба.
    Возвращает True при успехе, False при ошибке.

    Логика:
    1. Убеждаемся что мы на mira-dev и всё закоммичено
    2. Переключаемся на main, делаем merge --no-ff
    3. Пушим main
    4. Возвращаемся на mira-dev
    """
    try:
        current = get_current_branch()

        # Убеждаемся что нет незакоммиченных изменений
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True
        )
        if status.stdout.strip():
            print("[-] Есть незакоммиченные изменения. Сначала /git.")
            return False

        if current != DEV_BRANCH:
            print(f"[-] /release работает только с ветки '{DEV_BRANCH}'.")
            print(f"    Сейчас: '{current}'. Переключись через /git или запусти /evolve.")
            return False

        # Переключаемся на main и мерджим
        print(f"[Git] Переключаюсь на main...")
        subprocess.run(["git", "checkout", "main"], check=True, capture_output=True, text=True)

        print(f"[Git] Мерджу {DEV_BRANCH} → main...")
        subprocess.run(
            ["git", "merge", "--no-ff", DEV_BRANCH, "-m", f"Release: merge {DEV_BRANCH} into main"],
            check=True, capture_output=True, text=True
        )

        print("[Git] Пушу main...")
        subprocess.run(
            ["git", "push", "origin", "main"],
            check=True, capture_output=True, text=True
        )

        print("[*] Релиз выполнен. main обновлён.")
        logger.info(f"Release: {DEV_BRANCH} → main успешно.")

        # Возвращаемся на mira-dev
        subprocess.run(["git", "checkout", DEV_BRANCH], capture_output=True, text=True)
        return True

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else str(e)
        print(f"[-] Ошибка при релизе: {error_msg}")
        logger.error(f"release_to_main error: {error_msg}")
        # Пытаемся вернуться на mira-dev
        subprocess.run(["git", "checkout", DEV_BRANCH], capture_output=True, text=True)
        return False

    except FileNotFoundError:
        print("[-] Утилита git не найдена.")
        return False
