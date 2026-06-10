"""bot/callbacks.py — Inline-кнопки (callback_query)."""

from agent import SYSTEM_PROMPT
from agent import approve
from agent import blacklist
from agent import delete_user
from agent import list_users
from agent import load_user_profile
from agent import notify_owner
from agent import reject
from agent import release_to_main
from agent import save_user_profile
from agent import set_status
from agent import unblacklist
from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup
from telegram import Update
from telegram.ext import ContextTypes
from tools import semantic_memory

from bot.config import logger
from bot.helpers import _is_owner, _save_session, _user_id
from bot.commands_owner import _user_card_keyboard, cmd_reflect, cmd_rollback, cmd_users
from bot.commands_user import cmd_clear, cmd_files, cmd_whoami


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await _handle_callback(update, context)
    except Exception as e:
        logger.error(f"handle_callback: необработанная ошибка: {e}", exc_info=True)
        notify_owner(f"Ошибка в handle_callback: {e}")
        try:
            await update.callback_query.edit_message_text("Что-то пошло не так. Попробуй снова.")
        except Exception:
            pass


async def _handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data    = query.data
    tg_id   = query.from_user.id
    user_id = _user_id(tg_id)

    # --- Быстрые команды из меню ---
    cmd_map = {
        "cmd_files":   cmd_files,
        "cmd_whoami":  cmd_whoami,
        "cmd_clear":   cmd_clear,
        "cmd_reflect": cmd_reflect,
        "cmd_rollback":cmd_rollback,
        "cmd_users":   cmd_users,
    }
    if data in cmd_map:
        await cmd_map[data](update, context)
        return

    if data == "cmd_forget":
        from agent import delete_user_profile
        delete_user_profile(user_id)
        _save_session(user_id, [{"role": "system", "content": SYSTEM_PROMPT}])
        await query.edit_message_text("Профиль удалён. Напиши /start.")
        return

    # --- Evolve подтверждение ---
    if data == "evolve_apply":
        if not _is_owner(tg_id):
            return
        diff = context.user_data.get("evolve_diff")
        if not diff:
            await query.edit_message_text("Сессия устарела — запусти /evolve снова.")
            return

        await query.edit_message_text("⏳ Применяю атомарно (бэкап → валидация → smoke-test)...")

        from tools.safe_apply import safe_apply
        import asyncio
        task_summary = context.user_data.get("pending_evolve", "") or ""
        # asyncio.to_thread не поддерживает kwargs до 3.11, поэтому ламбда
        result = await asyncio.to_thread(
            lambda: safe_apply(diff, project_root=".", task_summary=task_summary)
        )

        context.user_data.pop("evolve_diff", None)
        context.user_data.pop("evolve_code", None)

        if not result.ok:
            msg = f"❌ Не применено:\n{result.message}"
            if result.backup_dir:
                msg += f"\n\nОткат сделан, бэкап: {result.backup_dir}"
            await context.bot.send_message(chat_id=query.message.chat_id, text=msg[:4000])
            from agent import increment_evolution
            increment_evolution(success=False)
            return

        from agent import increment_evolution
        increment_evolution(success=True)
        files_list = "\n".join(f"  • {p}" for p in result.touched_paths)
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=(
                f"✅ {result.message}\n\n"
                f"Затронуто:\n{files_list}\n\n"
                f"Бэкап: {result.backup_dir}\n\n"
                f"♻️ Перезапускаюсь, чтобы загрузить новый код. До связи через ~5 сек."
            )[:4000],
        )

        # Дать сообщению дойти, потом systemd перезапустит — новый процесс
        # подхватит свежий код. Делаем в фоновом сабпроцессе чтобы текущий
        # процесс успел отдать ответ Telegram.
        import subprocess
        subprocess.Popen(
            ["sh", "-c", "sleep 2 && systemctl restart mira-bot mira-web"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    elif data == "evolve_reject":
        context.user_data.pop("evolve_diff", None)
        context.user_data.pop("evolve_code", None)
        await query.edit_message_text("Изменения отклонены.")

    # --- Release подтверждение ---
    elif data == "release_confirm":
        if not _is_owner(tg_id):
            return
        await query.edit_message_text("Мерджу mira-dev → main...")
        ok, err = release_to_main()
        text = "✅ Релиз выполнен. GitHub Actions задеплоит через ~1 мин." if ok else f"❌ Ошибка при релизе:\n{err}"
        await context.bot.send_message(chat_id=query.message.chat_id, text=text)
    elif data == "release_cancel":
        await query.edit_message_text("Отменено.")

    # --- Управление пользователями ---
    elif data == "u_list":
        if not _is_owner(tg_id):
            return
        users = [u for u in list_users() if u["status"] != "owner"]
        status_icons = {"regular": "✅", "guest": "👤", "rejected": "❌", "blacklisted": "🚫", "blocked": "🚫"}
        buttons = [[InlineKeyboardButton(
            f"{status_icons.get(u['status'], '?')} {u['name'] or u['id'][:12]}",
            callback_data=f"u_card_{u['id']}"
        )] for u in users]
        text = f"Пользователи ({len(users)}):" if users else "Других пользователей нет."
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)

    elif data.startswith("u_card_"):
        if not _is_owner(tg_id):
            return
        uid = data[7:]
        p = load_user_profile(uid)
        if not p:
            await query.edit_message_text("Пользователь не найден.")
            return
        status = p.get("status", "regular")
        child  = p.get("child_mode", False)
        text = (
            f"👤 {p.get('name', '—')}\n"
            f"ID: {uid}\n"
            f"Статус: {status}\n"
            f"Последний визит: {p.get('last_seen', '—')}\n"
            f"Детский режим: {'вкл' if child else 'выкл'}"
        )
        await query.edit_message_text(text, reply_markup=_user_card_keyboard(uid, status, child))

    elif data.startswith("u_ap_"):
        if not _is_owner(tg_id):
            return
        uid = data[5:]
        p = load_user_profile(uid)
        if approve(uid):
            await query.edit_message_text(f"✅ {p.get('name', uid)} одобрен.")
            # Уведомление пользователю
            raw_uid = uid.replace("tg_", "")
            if raw_uid.isdigit():
                try:
                    await context.bot.send_message(
                        chat_id=int(raw_uid),
                        text="Твой доступ одобрен!\n\nТеперь тебе доступны:\n"
                             "— общение с Мирой без ограничений\n"
                             "— работа с файлами (отправляй файлы боту)\n"
                             "— веб-интерфейс\n\n"
                             "Напиши что-нибудь — начнём работать."
                    )
                except Exception:
                    pass
        else:
            await query.edit_message_text("Не найден.")

    elif data.startswith("u_rj_"):
        if not _is_owner(tg_id):
            return
        uid = data[5:]
        p = load_user_profile(uid)
        if reject(uid):
            await query.edit_message_text(f"❌ {p.get('name', uid)} отклонён.")
            raw_uid = uid.replace("tg_", "")
            if raw_uid.isdigit():
                try:
                    await context.bot.send_message(
                        chat_id=int(raw_uid),
                        text="К сожалению, владелец не одобрил твой доступ. "
                             "Общение с Мирой будет прекращено."
                    )
                except Exception:
                    pass
        else:
            await query.edit_message_text("Не найден.")

    elif data.startswith("u_gs_"):
        if not _is_owner(tg_id):
            return
        uid = data[5:]
        set_status(uid, "guest")
        await query.edit_message_text("👤 Переведён в гости.")

    elif data.startswith("u_bl_"):
        if not _is_owner(tg_id):
            return
        uid = data[5:]
        p = load_user_profile(uid)
        blacklist(uid)
        await query.edit_message_text(f"🚫 {p.get('name', uid) if p else uid} добавлен в чёрный список.")

    elif data.startswith("u_ubl_"):
        if not _is_owner(tg_id):
            return
        uid = data[6:]
        p = load_user_profile(uid)
        unblacklist(uid)
        await query.edit_message_text(f"↩️ {p.get('name', uid) if p else uid} убран из чёрного списка.")

    elif data.startswith("u_kids_"):
        if not _is_owner(tg_id):
            return
        uid = data[7:]
        p = load_user_profile(uid)
        if p:
            p["child_mode"] = not p.get("child_mode", False)
            save_user_profile(uid, p)
            state = "включён" if p["child_mode"] else "выключен"
            await query.edit_message_text(
                f"🧒 Детский режим {state} для {p.get('name', uid)}.",
                reply_markup=_user_card_keyboard(uid, p.get("status", "regular"), p["child_mode"])
            )

    elif data.startswith("u_del_"):
        if not _is_owner(tg_id):
            return
        uid = data[6:]
        p = load_user_profile(uid)
        name = p.get("name", uid) if p else uid
        await query.edit_message_text(
            f"Удалить {name} и всю его историю? Это необратимо.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Да, удалить ⚠️", callback_data=f"u_cdel_{uid}"),
                InlineKeyboardButton("Отмена",          callback_data=f"u_card_{uid}"),
            ]])
        )

    elif data.startswith("u_cdel_"):
        if not _is_owner(tg_id):
            return
        uid = data[7:]
        delete_user(uid)
        try:
            semantic_memory.delete_user(uid)
        except Exception as e:
            logger.warning(f"semantic_memory delete failed: {e}")
        await query.edit_message_text(f"Пользователь {uid} удалён.")
