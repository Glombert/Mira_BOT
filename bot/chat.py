"""bot/chat.py — Основной обработчик сообщений и онбординг."""

import asyncio
import json
import time
from core import memory_manager
from core import providers as _providers
from agent import load_user_profile
from agent import save_user_profile
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from tools import rate_limit
from tools import rich_tg
from tools import semantic_memory
from tools import tg_presence
from tools.access_tools import increment_guest_counter

from bot.config import MAX_HISTORY, logger
from bot.helpers import (
    _is_owner,
    _load_session,
    _make_alpha,
    _make_conclave,
    _reply,
    _save_session,
    _send_long,
    _send_output_files,
    _strip_md_for_tg,
    _user_id,
)
from bot.menu import _help_keyboard


_user_locks: dict[str, asyncio.Lock] = {}


def _user_lock(uid: str) -> asyncio.Lock:
    lock = _user_locks.get(uid)
    if lock is None:
        lock = _user_locks[uid] = asyncio.Lock()
    return lock


async def handle_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Реакция пользователя на сообщение Миры → пометка в сессии.

    Не triggering LLM: Мира увидит реакцию в контексте следующего хода
    и сама решит, заметить её или нет.
    """
    mru = update.message_reaction
    if mru is None or mru.user is None:
        return
    added = (
        {r.emoji for r in mru.new_reaction if getattr(r, "emoji", None)}
        - {r.emoji for r in mru.old_reaction if getattr(r, "emoji", None)}
    )
    if not added:
        return  # снятие реакции — не событие
    user_id = _user_id(mru.user.id)
    emoji = " ".join(sorted(added))
    logger.info(f"handle_reaction: {user_id} поставил {emoji}")
    async with _user_lock(user_id):
        msgs = _load_session(user_id)
        msgs.append({
            "role": "user",
            "content": f"[реакция: собеседник поставил {emoji} на твоё последнее сообщение. "
                       f"Это не текст — отвечать не нужно, просто знай.]",
        })
        _save_session(user_id, msgs)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id   = update.effective_user.id
    user_id = _user_id(tg_id)
    text    = update.message.text or ""

    # Координаты входящего — для инструмента tg_react (реакция на сообщение)
    tg_presence.remember_message(user_id, update.effective_chat.id, update.message.message_id)

    logger.info(f"handle_message: пользователь {user_id}, длина сообщения={len(text)}")

    # Онбординг
    if context.user_data.get("onboarding"):
        await _handle_onboarding(update, context, tg_id, user_id, text)
        return

    # Rate limit: 60 сообщ/мин (owner без лимитов). Сообщаем как Мира,
    # а не молча отбрасываем
    allowed, retry_after = rate_limit.check_and_record(user_id, "message")
    if not allowed:
        logger.info(f"handle_message: rate limit для {user_id} → retry {retry_after}s")
        await _reply(update, rate_limit.friendly_message("message", retry_after))
        return

    # Проверка статуса
    async with _user_lock(user_id):
        profile_data = load_user_profile(user_id)
        if profile_data and profile_data.get("status") == "blocked":
            logger.warning(f"handle_message: заблокированный пользователь {user_id} пытается отправить сообщение")
            await _reply(update,"Доступ закрыт.")
            return

        # Гостевой лимит — единый источник в access_tools.GUEST_LIMIT
        if profile_data and profile_data.get("status") == "guest":
            count, limit = increment_guest_counter(user_id, profile_data)
            if count > limit:
                logger.info(f"handle_message: гость {user_id} исчерпал лимит сообщений")
                await _reply(update, "Лимит сообщений исчерпан. Ожидай одобрения.")
                return
            elif count >= limit - 2:
                await _reply(update, f"(осталось {limit - count} сообщений из {limit})")

        msgs   = _load_session(user_id)
        alpha  = _make_alpha(tg_id, user_id)
        conc   = _make_conclave(tg_id, user_id)
        context.user_data["conclave"] = conc

        msgs.append({"role": "user", "content": text})
        # trim
        system   = [m for m in msgs if m["role"] == "system"]
        the_rest = [m for m in msgs if m["role"] != "system"]
        msgs     = system + the_rest[-MAX_HISTORY:]

        # Семантический поиск по прошлым разговорам (Этап v1.3).
        # Augment-блок добавляем только в copy для LLM — в msgs не сохраняем.
        semantic_augment = ""
        try:
            matches = semantic_memory.search(user_id, text, top_k=5, max_distance=0.35)
            semantic_augment = semantic_memory.format_for_prompt(matches)
        except Exception as e:
            logger.warning(f"semantic_memory search failed: {e}")

        # Подсказка про новые возможности и непрочитанные входящие письма
        from web.sessions import (
            _changelog_augment, _mark_changelog_seen,
            _incoming_augment, _mark_incoming_seen,
        )
        changelog_aug = _changelog_augment(user_id)
        incoming_aug = _incoming_augment(user_id)
        combined_aug = "\n\n".join(filter(None, [semantic_augment, changelog_aug, incoming_aug]))

        def _augmented(orig: list) -> list:
            # Всегда shallow-copy: agent.run() мутирует свой аргумент (добавляет
            # assistant-ответ). Если возвращать orig, мутации попадают в сохранённую
            # историю. Если возвращать копию — теряем ответ. Решение: всегда копия,
            # а ответ дописываем явно после run() (см. ниже).
            out = list(orig)
            if combined_aug and out and out[0].get("role") == "system":
                out[0] = {**out[0], "content": out[0]["content"] + "\n\n" + combined_aug}
            return out

        ts_before = datetime.now().timestamp()

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        # Живая печать: sendMessageDraft показывает накопленный текст ответа
        # по мере генерации. Колбэки прилетают из рабочего потока alpha.run —
        # троттлим и прыгаем в event loop через run_coroutine_threadsafe.
        loop     = asyncio.get_running_loop()
        chat_id  = update.effective_chat.id
        draft_id = update.message.message_id  # ненулевой и уникальный на ход
        draft_state = {"last": 0.0, "active": False}

        def _push_draft(text: str, min_interval: float = 0.7) -> None:
            try:
                now = time.monotonic()
                if now - draft_state["last"] < min_interval:
                    return
                snippet = _strip_md_for_tg(text).strip()[:4000]
                if not snippet:
                    return
                draft_state["last"] = now
                draft_state["active"] = True
                asyncio.run_coroutine_threadsafe(
                    context.bot.send_message_draft(chat_id=chat_id, draft_id=draft_id, text=snippet),
                    loop,
                )
            except Exception:
                pass  # черновик — украшение, не роняем ответ

        def _on_tool_progress(status: str) -> None:
            _push_draft(f"⚙️ {status}…", min_interval=0.0)

        try:
            # Инверсия: Мира всегда отвечает сама (alpha.run умеет вызывать
            # инструменты). Специалисты — её инструменты, не маршрут «мимо» неё.
            if alpha:
                answer = await asyncio.to_thread(
                    alpha.run, _augmented(msgs),
                    on_progress=_on_tool_progress, on_delta=_push_draft,
                )
                # alpha.run мутирует _augmented(msgs) — копию. Сюда не попало.
                msgs.append({"role": "assistant", "content": answer})
            else:
                await _reply(update,"Провайдеры не настроены.")
                return

            # Гасим черновик перед финальными сообщениями (пустой text = очистка)
            if draft_state["active"]:
                try:
                    await context.bot.send_message_draft(chat_id=chat_id, draft_id=draft_id, text="")
                except Exception:
                    pass
            # Структурные ответы (таблицы/заголовки/списки/код) — нативным
            # rich-сообщением; беседа без структуры — привычными чанками.
            sent_rich = False
            if rich_tg.has_rich_structure(answer):
                sent_rich = await asyncio.to_thread(rich_tg.send_rich, chat_id, answer)
            if not sent_rich:
                await _send_long(update, _strip_md_for_tg(answer), split_for_chat=True)
            await _send_output_files(context, update.effective_chat.id, user_id, ts_before)
            _save_session(user_id, msgs)
            if changelog_aug:
                _mark_changelog_seen(user_id)
            if incoming_aug:
                _mark_incoming_seen(user_id)

            # Фоновые задачи памяти — не блокируют ответ
            model_chain = alpha.model_chain if alpha else []
            msgs_snapshot = list(msgs)
            user_text     = text
            bot_answer    = answer

            def _memory_tasks():
                # 1. Семантическая память — индексируем оба сообщения
                try:
                    semantic_memory.index_message(user_id, "user", user_text)
                    if bot_answer:
                        semantic_memory.index_message(user_id, "assistant", bot_answer)
                except Exception as e:
                    logger.warning(f"semantic_memory index failed: {e}")

                if not model_chain:
                    return
                # 2. Суммаризация если история длинная
                updated = memory_manager.maybe_summarize(
                    user_id, msgs_snapshot, model_chain,
                    load_user_profile, save_user_profile,
                )
                if updated is not msgs_snapshot:
                    _save_session(user_id, updated)

                # 3. Обновление профиля новыми фактами
                memory_manager.update_user_profile(
                    user_id, msgs_snapshot, model_chain,
                    load_user_profile, save_user_profile,
                )

            memory_manager.run_background(_memory_tasks)

        except Exception as e:
            logger.error(f"Ошибка при обработке сообщения: {e}", exc_info=True)
            await _reply(update,"Что-то пошло не так. Попробуй снова.")
            if msgs and msgs[-1]["role"] == "user":
                msgs.pop()


async def _handle_onboarding(update, context, tg_id, user_id, text):
    """Онбординг через диалог в Telegram."""
    hist = context.user_data.get("onboarding_history", [])
    hist.append({"role": "user", "content": text})

    alpha = _make_alpha(tg_id, user_id)
    if not alpha:
        context.user_data.pop("onboarding", None)
        return

    try:
        response = _providers.call(alpha.model_chain, hist, temperature=0.7)
        reply = response.choices[0].message.content
        hist.append({"role": "assistant", "content": reply})
        context.user_data["onboarding_history"] = hist

        await _reply(update,reply)

        if "Принято" in reply or "Начинаем" in reply or len(hist) >= 10:
            # Завершаем онбординг — структурируем профиль
            dialog = "\n".join(
                f"{m['role']}: {m['content']}"
                for m in hist if m["role"] in ("user", "assistant")
            )
            today = datetime.now().strftime("%Y-%m-%d")
            struct_prompt = (
                f"Создай JSON-профиль пользователя по диалогу.\n"
                f"Верни ТОЛЬКО JSON.\n\nДиалог:\n{dialog}\n\n"
                f'{{"id":"{user_id}","name":"имя","created_at":"{today}",'
                f'"last_seen":"{today}","sessions_count":1,'
                f'"status":"{"owner" if _is_owner(tg_id) else "regular"}",'
                f'"about":{{"role":"...","communication_style":"..."}},'
                f'"preferences":{{"language":"ru"}},"domain":{{}},"notes":[]}}'
            )
            try:
                r = _providers.call(
                    alpha.model_chain,
                    [{"role": "user", "content": struct_prompt}],
                    temperature=0.1,
                )
                raw = r.choices[0].message.content.strip()
                if raw.startswith("```"):
                    raw = "\n".join(l for l in raw.splitlines() if not l.strip().startswith("```"))
                data = json.loads(raw)
            except Exception:
                data = {
                    "id": user_id, "name": user_id.replace("tg_", ""),
                    "created_at": today, "last_seen": today, "sessions_count": 1,
                    "status": "owner" if _is_owner(tg_id) else "regular",
                    "about": {}, "preferences": {}, "domain": {}, "notes": [],
                }
            save_user_profile(user_id, data)
            context.user_data.pop("onboarding", None)
            context.user_data.pop("onboarding_history", None)
            await _reply(update,
                "Профиль сохранён. Можем начинать.",
                reply_markup=_help_keyboard(_is_owner(tg_id)),
            )
    except Exception as e:
        logger.error(f"Онбординг: {e}")
        await _reply(update,"Ошибка API. Попробуй снова.")
