"""
tools/shell_tools.py — инструмент для выполнения Python-кода.

Агент может запустить произвольный Python-код в отдельном процессе
и получить результат. Это нужно для вычислений, обработки данных,
проверки логики — всего что сложнее сделать на уровне текста.

Безопасность:
- Код запускается в подпроцессе, а не в текущем процессе агента.
  Если код упадёт — агент продолжит работу.
- Таймаут: по умолчанию 30 секунд. Зависший код будет убит.
- Рабочая директория: workspace/{user_id} — код не знает ничего
  выше этой папки (в рамках разумного; это не полная изоляция).

Ограничения (честно):
- Код может делать import и использовать стандартную библиотеку.
- Полной изоляции (sandbox) нет — это CLI-инструмент, не production.
  Для production нужен Docker или аналог. Это этап 6+.
"""

import os
import sys
import subprocess
import tempfile

# Таймаут по умолчанию — сколько секунд ждать выполнения кода
DEFAULT_TIMEOUT = 30

# Максимальный размер вывода который вернём агенту (в символах)
# Если вывод больше — обрезаем, чтобы не засорять контекст
MAX_OUTPUT_CHARS = 8000


def run_python(code: str, user_id: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """
    Выполняет Python-код в отдельном подпроцессе.

    Аргументы:
        code     — строка с Python-кодом для выполнения
        user_id  — рабочая директория будет workspace/{user_id}
        timeout  — максимальное время выполнения в секундах

    Возвращает словарь:
        {
            "ok":        True/False,
            "stdout":    "вывод программы (print и т.д.)",
            "stderr":    "ошибки если были",
            "exit_code": 0  (0 = успех, не-0 = ошибка)
        }

    Пример использования агентом:
        result = run_python("print(2 + 2)", user_id="cli_andrey")
        # result["stdout"] == "4\\n"
    """
    # Рабочая директория — папка пользователя в workspace
    # Если её нет — создаём (на всякий случай)
    work_dir = os.path.join("workspace", user_id)
    os.makedirs(work_dir, exist_ok=True)

    # Записываем код во временный файл
    # Почему файл, а не -c "код"? Потому что в файле корректно работают
    # многострочный код, отступы, кавычки — без экранирования.
    tmp_path = None  # инициализируем до try, чтобы finally мог безопасно обратиться
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
            encoding="utf-8",
            dir=work_dir   # временный файл — в папке пользователя
        ) as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        # Запускаем код в подпроцессе
        result = subprocess.run(
            [sys.executable, tmp_path],   # sys.executable = тот же python что запустил агента
            capture_output=True,          # перехватываем stdout и stderr
            text=True,                    # декодируем байты в строки (UTF-8)
            timeout=timeout,
            cwd=work_dir                  # рабочая директория внутри workspace
        )

        # Обрезаем вывод если он слишком большой
        stdout = result.stdout
        stderr = result.stderr

        truncated = False
        if len(stdout) > MAX_OUTPUT_CHARS:
            stdout = stdout[:MAX_OUTPUT_CHARS] + f"\n... [вывод обрезан, показано {MAX_OUTPUT_CHARS} символов]"
            truncated = True

        return {
            "ok":        result.returncode == 0,
            "stdout":    stdout,
            "stderr":    stderr,
            "exit_code": result.returncode,
            "truncated": truncated
        }

    except subprocess.TimeoutExpired:
        return {
            "ok":        False,
            "stdout":    "",
            "stderr":    f"Таймаут: код выполнялся дольше {timeout} секунд и был остановлен.",
            "exit_code": -1,
            "truncated": False
        }

    except Exception as e:
        return {
            "ok":        False,
            "stdout":    "",
            "stderr":    f"Ошибка запуска: {e}",
            "exit_code": -1,
            "truncated": False
        }

    finally:
        # Удаляем временный файл в любом случае — даже если упали
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass  # если не удалось удалить — не страшно, это temp-файл
