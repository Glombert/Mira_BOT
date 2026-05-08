"""
tools/shell_tools.py — выполнение Python-кода в изолированном подпроцессе.

Безопасность:
  - Код запускается в подпроцессе — падение не роняет агента.
  - Таймаут 30 секунд — зависший код убивается.
  - Рабочая директория: workspace/{user_id}.
  - Если установлен firejail — код запускается в sandbox:
      --net=none      нет доступа в интернет
      --noroot        нет эскалации привилегий
      --nosound       нет доступа к звуку
      --nodbus        нет D-Bus
      --private-tmp   изолированный /tmp
    Без firejail — предупреждение в лог, запуск без изоляции.

Установить firejail на сервере: apt install firejail
"""

import os
import sys
import shutil
import subprocess
import tempfile
import logging

logger = logging.getLogger("Ouroborus")

DEFAULT_TIMEOUT  = 30
MAX_OUTPUT_CHARS = 8000

# Определяем один раз при импорте — есть ли firejail в системе
_FIREJAIL = shutil.which("firejail")
if _FIREJAIL:
    logger.info(f"run_python: изоляция через firejail ({_FIREJAIL})")
else:
    logger.warning(
        "run_python: firejail не найден — код выполняется БЕЗ изоляции. "
        "Установи: apt install firejail"
    )


def run_python(code: str, user_id: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """
    Выполняет Python-код в подпроцессе (с firejail если доступен).

    Возвращает:
        {"ok": bool, "stdout": str, "stderr": str, "exit_code": int,
         "sandboxed": bool, "truncated": bool}
    """
    work_dir = os.path.join("workspace", user_id)
    os.makedirs(work_dir, exist_ok=True)

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False,
            encoding="utf-8", dir=work_dir
        ) as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        if _FIREJAIL:
            cmd = [
                _FIREJAIL,
                "--quiet",
                "--noprofile",
                "--net=none",
                "--noroot",
                "--nosound",
                "--nodbus",
                "--private-tmp",
                sys.executable, tmp_path,
            ]
        else:
            cmd = [sys.executable, tmp_path]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=work_dir,
        )

        stdout = result.stdout
        truncated = False
        if len(stdout) > MAX_OUTPUT_CHARS:
            stdout = stdout[:MAX_OUTPUT_CHARS] + f"\n... [вывод обрезан до {MAX_OUTPUT_CHARS} символов]"
            truncated = True

        return {
            "ok":        result.returncode == 0,
            "stdout":    stdout,
            "stderr":    result.stderr,
            "exit_code": result.returncode,
            "sandboxed": bool(_FIREJAIL),
            "truncated": truncated,
        }

    except subprocess.TimeoutExpired:
        return {
            "ok":        False,
            "stdout":    "",
            "stderr":    f"Таймаут: код выполнялся дольше {timeout} секунд и был остановлен.",
            "exit_code": -1,
            "sandboxed": bool(_FIREJAIL),
            "truncated": False,
        }

    except Exception as e:
        return {
            "ok":        False,
            "stdout":    "",
            "stderr":    f"Ошибка запуска: {e}",
            "exit_code": -1,
            "sandboxed": bool(_FIREJAIL),
            "truncated": False,
        }

    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
