"""bot/files.py — Входящие документы и фото."""

import asyncio
import base64
import os
from agent import WORKSPACE_DIR
from agent import load_user_profile
from agent import notify_owner
from telegram import Update
from telegram.ext import ContextTypes
from tools import rate_limit
from tools.gdrive_tools import auto_upload_to_drive
from tools.gdrive_tools import is_authorized as gdrive_authorized

from bot.config import MAX_HISTORY, logger
from bot.helpers import (
    _is_approved,
    _load_session,
    _make_alpha,
    _reply,
    _save_session,
    _send_long,
    _user_id,
)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await _handle_document(update, context)
    except Exception as e:
        logger.error(f"handle_document: необработанная ошибка: {e}", exc_info=True)
        notify_owner(f"Ошибка в handle_document: {e}")
        try:
            await _reply(update, "Что-то пошло не так при обработке файла. Попробуй ещё раз.")
        except Exception:
            pass


async def _handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id   = update.effective_user.id
    user_id = _user_id(tg_id)

    if not _is_approved(user_id):
        await _reply(update, "Обмен файлами доступен только одобренным пользователям.")
        return

    # Rate limit: 20 файлов / минуту. Мира предупреждает голосом
    allowed, retry_after = rate_limit.check_and_record(user_id, "upload")
    if not allowed:
        logger.info(f"handle_document: rate limit для {user_id} → retry {retry_after}s")
        await _reply(update, rate_limit.friendly_message("upload", retry_after))
        return

    doc     = update.message.document
    raw_name = doc.file_name or f"file_{doc.file_id}"
    # Защита от path traversal: нормализуем windows-разделители и берём basename
    fname = os.path.basename(raw_name.replace("\\", "/")).replace("\x00", "")
    if not fname or fname in (".", ".."):
        fname = f"file_{doc.file_id}"
    fname = fname[:255]

    logger.info(f"handle_document: пользователь {user_id}, файл={fname}, размер={doc.file_size}")

    user_root = os.path.realpath(os.path.join(WORKSPACE_DIR, user_id))
    inbox = os.path.join(user_root, "inbox")
    os.makedirs(inbox, exist_ok=True)
    dest = os.path.realpath(os.path.join(inbox, fname))
    if not dest.startswith(user_root + os.sep):
        await _reply(update, "Недопустимое имя файла.")
        return

    tg_file = await context.bot.get_file(doc.file_id)
    await tg_file.download_to_drive(dest)

    logger.info(f"handle_document: файл {fname} сохранён для {user_id}")

    # Авто-загрузка на Google Drive (только для одобренных + авторизованных)
    if _is_approved(user_id) and gdrive_authorized(user_id):
        profile_data = load_user_profile(user_id)
        if profile_data and profile_data.get("preferences", {}).get("gdrive_auto_upload"):
            auto_upload_to_drive(user_id, f"inbox/{fname}")

    await _reply(update,
        f"📥 Файл сохранён: `inbox/{fname}`\n\nМогу прочитать, проанализировать или обработать — скажи что нужно.",
        parse_mode="Markdown",
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает фото: скачивает, отправляет Claude с vision, сохраняет [фото] в истории."""
    tg_id   = update.effective_user.id
    user_id = _user_id(tg_id)

    if not _is_approved(user_id):
        await _reply(update, "Отправка фото доступна только одобренным пользователям.")
        return

    logger.info(f"handle_photo: пользователь {user_id}, размер фото={len(update.message.photo)}")

    # Скачиваем фото в наилучшем качестве
    photo   = update.message.photo[-1]
    tg_file = await context.bot.get_file(photo.file_id)
    raw     = await tg_file.download_as_bytearray()
    b64     = base64.b64encode(bytes(raw)).decode()

    # Формируем vision-контент
    caption = (update.message.caption or "").strip()
    content = []
    if caption:
        content.append({"type": "text", "text": caption})
    content.append({
        "type": "image_url",
        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
    })

    msgs  = _load_session(user_id)
    alpha = _make_alpha(tg_id, user_id)
    if not alpha:
        await _reply(update,"Провайдеры не настроены.")
        return

    # Проверяем, поддерживает ли модель vision
    model_chain = alpha.model_chain
    supports_vision = any(
        "claude" in entry.get("model", "").lower() or
        "gemini" in entry.get("model", "").lower() or
        "gpt-4" in entry.get("model", "").lower()
        for entry in model_chain
    )
    if not supports_vision:
        logger.warning(f"handle_photo: модель не поддерживает vision, model_chain={model_chain}")
        await _reply(update,
            "Сейчас не могу посмотреть фото — модель с поддержкой изображений недоступна. "
            "Попробуй позже или опиши словами что на снимке."
        )
        return

    msgs.append({"role": "user", "content": content})
    system   = [m for m in msgs if m["role"] == "system"]
    the_rest = [m for m in msgs if m["role"] != "system"]
    msgs     = system + the_rest[-MAX_HISTORY:]

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        answer = await asyncio.to_thread(alpha.run, msgs)
        await _send_long(update, answer)

        # Сохраняем историю: заменяем image_url на текстовый placeholder
        def _strip_images(m: dict) -> dict:
            c = m.get("content")
            if not isinstance(c, list):
                return m
            texts = [p.get("text", "") for p in c if p.get("type") == "text"]
            placeholder = " ".join(t for t in texts if t).strip() or "[фото]"
            return {**m, "content": placeholder}

        _save_session(user_id, [_strip_images(m) for m in msgs])
        logger.info(f"handle_photo: успешно обработано для {user_id}")

    except Exception as e:
        logger.error(f"Ошибка при обработке фото: {e}", exc_info=True)
        err = str(e).lower()
        if any(k in err for k in ("vision", "image", "multimodal", "unsupported")):
            await _reply(update,
                "Сейчас не могу посмотреть фото — модель с поддержкой изображений недоступна. "
                "Попробуй позже или опиши словами что на снимке."
            )
        else:
            await _reply(update,"Что-то пошло не так. Попробуй ещё раз.")
