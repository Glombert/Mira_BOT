"""agent_tools.py — реестр инструментов и диспетчер Миры.

Вынесено из agent.py: tool-слой замыкается только на функции из tools/ и
memory_manager, не на внутреннее состояние agent.py. Держим его отдельным
модулем чтобы agent.py не разрастался и диспетчер было легко аудировать.

Контракт для остального кода:
    execute_tool(tool_name, tool_args, user_id) -> str (JSON)
    _humanize_tool(tool_name, tool_args) -> str   (для облачка «💭 ...»)
    TOOL_SCHEMAS                                   (реэкспорт из tools.tool_schemas)
"""

import os
import json
import time
import logging

from tools import (
    list_files, read_file, write_file, run_python, web_search,
    excel_read, excel_write, list_self, read_self, git_log,
    write_persona, write_agent_config,
)
from tools import semantic_memory
from tools import file_tools
from tools import image_tools
from tools.gdrive_tools import (
    gdrive_list, gdrive_read, gdrive_write,
    gcal_list, gcal_create, gcal_quick_add,
    gsheet_read, gsheet_write, gsheet_create,
)
from tools.metrics_tools import metrics_read
from tools.log_tools import read_logs
from tools.scheduler import schedule_reminder, list_reminders, cancel_reminder
from tools.openrouter_tools import list_models as _openrouter_list_models
from tools.whats_new import whats_new as _whats_new
from tools.messaging import (
    find_user as _find_user,
    send_to_user as _send_to_user,
    confirm_send_to_user as _confirm_send_to_user,
    cancel_send_to_user as _cancel_send_to_user,
    block_sender as _block_sender,
    unblock_sender as _unblock_sender,
)
from tools.cloud_tools import sync_output_to_drive, sync_inbox_from_drive
from tools.tool_schemas import TOOL_SCHEMAS
import memory_manager as _memory_manager

logger = logging.getLogger("Ouroboros")


# ---------------------------------------------------------------------------
# Адаптеры с pre/post-хуками — именованные функции.
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


def _is_owner_user(user_id: str) -> bool:
    """Проверка статуса owner по user_id (формат tg_<id> или cli_<id>)."""
    try:
        from tools import db as _db
        profile = _db.load_user_profile(user_id)
        return bool(profile and profile.get("status") == "owner")
    except Exception:
        return False


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
    "read_logs":          lambda u, a: read_logs(a.get("days", 14), a.get("include_warnings", False)),
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
    "attach_file":       lambda u, a: file_tools.attach_file(u, a["path"]),
    "whats_new":         lambda u, a: _whats_new(
        audience=("owner" if _is_owner_user(u) else "all"),
        limit=int(a.get("limit", 6)),
    ),
    "find_user":              lambda u, a: _find_user(a.get("query", ""), caller_id=u),
    "send_to_user":           lambda u, a: _send_to_user(a.get("target", ""), a.get("body", ""), caller_id=u),
    "confirm_send_to_user":   lambda u, a: _confirm_send_to_user(int(a.get("pending_id", 0)), caller_id=u),
    "cancel_send_to_user":    lambda u, a: _cancel_send_to_user(int(a.get("pending_id", 0)), caller_id=u),
    "block_sender":           lambda u, a: _block_sender(a.get("target", ""), caller_id=u),
    "unblock_sender":         lambda u, a: _unblock_sender(a.get("target", ""), caller_id=u),
}


_TOOL_HUMAN = {
    "list_files":             "смотрит твои файлы",
    "read_file":              "читает файл",
    "write_file":             "пишет файл",
    "excel_read":             "читает таблицу",
    "excel_write":            "правит таблицу",
    "recall":                 "вспоминает",
    "run_python":             "запускает код",
    "web_search":             "ищет в интернете",
    "save_template":          "сохраняет шаблон",
    "list_templates":         "смотрит шаблоны",
    "list_self":              "смотрит на свой код",
    "read_self":              "читает свой код",
    "git_log":                "смотрит историю изменений",
    "write_persona":          "обновляет себя",
    "write_agent_config":     "правит конфиг агента",
    "gdrive_list":            "смотрит Google Drive",
    "gdrive_read":            "читает файл из Drive",
    "gdrive_write":           "загружает в Drive",
    "metrics_read":           "смотрит метрики",
    "read_logs":              "разбирает логи на ошибки",
    "gcal_list":              "смотрит календарь",
    "gcal_create":            "создаёт событие",
    "gcal_quick_add":         "добавляет событие",
    "gsheet_read":            "читает таблицу",
    "gsheet_write":           "пишет в таблицу",
    "gsheet_create":          "создаёт таблицу",
    "schedule_reminder":      "ставит напоминание",
    "list_reminders":         "смотрит напоминания",
    "cancel_reminder":        "отменяет напоминание",
    "openrouter_list_models": "смотрит список моделей",
    "generate_image":         "рисует",
    "attach_file":            "прикрепляет файл",
    "whats_new":              "сверяется со списком новых возможностей",
    "find_user":              "ищет человека",
    "send_to_user":           "готовит письмо",
    "confirm_send_to_user":   "отправляет письмо",
    "cancel_send_to_user":    "отменяет черновик",
    "block_sender":           "включает блокировку",
    "unblock_sender":         "снимает блокировку",
}


def _humanize_tool(tool_name: str, tool_args: dict | None = None) -> str:
    """Человеческое описание инструмента для облачка «💭 ...» на клиенте."""
    base = _TOOL_HUMAN.get(tool_name, tool_name.replace("_", " "))
    if tool_name == "web_search" and tool_args:
        q = (tool_args.get("query") or "").strip()
        if q:
            return f"{base}: «{q[:40]}»"
    if tool_name == "read_file" and tool_args:
        p = (tool_args.get("relative_path") or "").strip()
        if p:
            return f"{base} {p[:40]}"
    return base


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
