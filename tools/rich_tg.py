"""rich_tg.py — нативные Rich Messages Telegram (Bot API 10.1) для ответов Миры.

Раньше markdown Миры перед отправкой в TG зачищался (_strip_md_for_tg):
таблицы и заголовки превращались в кашу. sendRichMessage рендерит их
нативно. PTB 22.8 метода ещё не знает — зовём API напрямую.

Использование: rich только для ответов СО структурой (таблица/заголовок/
список/код) — обычная беседа остаётся в стиле чанков. Любая ошибка API
(фича раскатывается постепенно) → None/False, вызывающий falls back на
старый plain-путь.
"""

import os
import re
import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger("MiraBot")

_STRUCTURE_RE = re.compile(r"^(#{1,6} |\|.+\||```|[-*] |\d+\. |> )", re.M)


def has_rich_structure(md: str) -> bool:
    """Есть ли в markdown структура, ради которой стоит слать rich-сообщение."""
    return bool(_STRUCTURE_RE.search(md or ""))


# ---------------------------------------------------------------------------
# markdown → InputRichBlock[]
# ---------------------------------------------------------------------------

def _mk_md():
    from markdown_it import MarkdownIt
    return MarkdownIt("commonmark").enable("table").enable("strikethrough")


def _inline_html(md_parser, inline_token) -> str:
    """Инлайн-токен → HTML для parse_mode=HTML (テлеграм понимает b/i/code/a/s)."""
    html = md_parser.renderer.render([inline_token], md_parser.options, {})
    # Telegram HTML не знает <br> — markdown-it их не даёт при breaks=False,
    # но подстрахуемся.
    return html.replace("<br>", "\n").replace("<br/>", "\n").strip()


def md_to_rich_blocks(md_text: str) -> list[dict] | None:
    """Конвертирует markdown в блоки InputRichMessage. None — не смогли."""
    try:
        md = _mk_md()
        tokens = md.parse(md_text)
        blocks: list[dict] = []
        i = 0
        while i < len(tokens):
            t = tokens[i]

            if t.type == "heading_open":
                blocks.append({"type": "section_heading",
                               "text": _inline_html(md, tokens[i + 1]),
                               "parse_mode": "HTML"})
                i += 3
                continue

            if t.type == "paragraph_open":
                blocks.append({"type": "paragraph",
                               "text": _inline_html(md, tokens[i + 1]),
                               "parse_mode": "HTML"})
                i += 3
                continue

            if t.type in ("fence", "code_block"):
                block = {"type": "preformatted", "text": t.content.rstrip("\n")}
                lang = (t.info or "").strip()
                if lang:
                    block["language"] = lang
                blocks.append(block)
                i += 1
                continue

            if t.type == "hr":
                blocks.append({"type": "divider"})
                i += 1
                continue

            if t.type == "blockquote_open":
                depth, j, parts = 1, i + 1, []
                while j < len(tokens) and depth:
                    if tokens[j].type == "blockquote_open":
                        depth += 1
                    elif tokens[j].type == "blockquote_close":
                        depth -= 1
                    elif tokens[j].type == "inline":
                        parts.append(_inline_html(md, tokens[j]))
                    j += 1
                blocks.append({"type": "block_quotation",
                               "text": "\n".join(parts), "parse_mode": "HTML"})
                i = j
                continue

            if t.type in ("bullet_list_open", "ordered_list_open"):
                is_ordered = t.type == "ordered_list_open"
                close = t.type.replace("_open", "_close")
                depth, j, items = 1, i + 1, []
                current: list[str] = []
                while j < len(tokens) and depth:
                    tt = tokens[j]
                    if tt.type == t.type:
                        depth += 1
                    elif tt.type == close:
                        depth -= 1
                    elif tt.type == "list_item_open" and depth == 1:
                        current = []
                    elif tt.type == "list_item_close" and depth == 1:
                        items.append({"text": "\n".join(current) or " ",
                                      "parse_mode": "HTML"})
                    elif tt.type == "inline":
                        current.append(_inline_html(md, tt))
                    j += 1
                block = {"type": "list", "items": items}
                if is_ordered:
                    block["is_ordered"] = True
                blocks.append(block)
                i = j
                continue

            if t.type == "table_open":
                j, cells, n_cols, in_header = i + 1, [], 0, False
                header_rows = 0
                row_cols = 0
                while j < len(tokens) and tokens[j].type != "table_close":
                    tt = tokens[j]
                    if tt.type == "thead_open":
                        in_header = True
                    elif tt.type == "thead_close":
                        in_header = False
                    elif tt.type == "tr_open":
                        row_cols = 0
                        if in_header:
                            header_rows += 1
                    elif tt.type in ("th_open", "td_open"):
                        row_cols += 1
                    elif tt.type == "inline":
                        cells.append({"text": _inline_html(md, tt) or " ",
                                      "parse_mode": "HTML"})
                    elif tt.type == "tr_close":
                        n_cols = max(n_cols, row_cols)
                    j += 1
                blocks.append({"type": "table", "cells": cells,
                               "columns": n_cols, "header_rows": header_rows})
                i = j + 1
                continue

            i += 1

        return blocks or None
    except Exception as e:
        logger.warning(f"rich_tg: конвертация markdown не удалась: {e}")
        return None


# ---------------------------------------------------------------------------
# Отправка
# ---------------------------------------------------------------------------

def send_rich(chat_id: int, md_text: str) -> bool:
    """Шлёт rich-сообщение. False — не вышло (вызывающий шлёт по-старому)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return False
    blocks = md_to_rich_blocks(md_text)
    if not blocks:
        return False
    payload = {"chat_id": chat_id, "rich_message": {"blocks": blocks}}
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendRichMessage",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = bool(json.loads(resp.read().decode()).get("ok"))
    except urllib.error.HTTPError as e:
        try:
            desc = json.loads(e.read().decode()).get("description", "")
        except Exception:
            desc = str(e)
        logger.info(f"rich_tg: sendRichMessage отказ ({e.code}: {desc}) — фолбэк на plain")
        return False
    except Exception as e:
        logger.info(f"rich_tg: sendRichMessage недоступен ({e}) — фолбэк на plain")
        return False
    return ok
