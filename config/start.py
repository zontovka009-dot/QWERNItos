"""
config/start.py — /start, онбординг, deep link, pro, оплата.
"""

import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from config.db import (
    user_touch, user_get, user_set, user_name,
    ban_check, owner_check, is_pro,
    proj_get, app_for_user, ref_apply, reflink,
)from config.keyboards import (
    reply_main, reply_cancel,
    safe_edit, safe_send, delete_prev,
    save_msg_id, REPLY_BUTTON_MAP,
)
from config.states import S_ONBOARD, S_APP_FILL

log = logging.getLogger("kpp.start")
MD  = ParseMode.MARKDOWN


# ══════════════════════════════════════════════════════════════
#  /start
# ══════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    user   = update.effective_user
    is_new = user_touch(user.id, user.username or "", user.first_name or "")

    if ban_check(user.id):
        await update.message.reply_text(
            "⛔ Твой аккаунт ограничен.\n"
            "Если считаешь это ошибкой — напиши в поддержку."
        )
        return ConversationHandler.END

    args = ctx.args or []

    if args and args[0].startswith("ref_"):
        if is_new:
            if ref_apply(user.id, args[0][4:]):
                ctx.user_data["ref_bonus"] = True

    if args and args[0].startswith("kpp_"):
        return await _deeplink_project(update, ctx, args[0][4:])

    u = user_get(user.id)

    # новый пользователь — онбординг
    if is_new or (u and not u.get("onboarding")):
        return await _onboarding(update, ctx, u)

    # возвращающийся — главное меню
    await _show_main(update.message, user.id, ctx, is_new=False)
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════
#  ОБРАБОТЧИК REPLY КНОПОК (текст снизу)
# ══════════════════════════════════════════════════════════════

async def handle_reply_buttons(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Перехватывает нажатия на ReplyKeyboard (кнопки внизу экрана)
    и превращает их в обычные callback — без дублирования логики.
    """
    text = update.message.text
    cb   = REPLY_TO_CALLBACK.get(text)
    if not cb:
        return ConversationHandler.END

    # удаляем сообщение с нажатой кнопкой чтобы не засорять чат
    try:
        await update.message.delete()
    except Exception:
        pass

    uid = update.effective_user.id

    # эмулируем нажатие нужной кнопки через отправку нового сообщения
    # с inline-клавиатурой нужного раздела
    if cb == "back_main":
        await _show_main_new(update, uid, ctx)
    elif cb == "projects":
        from config.projects import _send_projects
        await _send_projects(update.message, uid, ctx)
    elif cb == "catalog":
        from config.catalog import _send_catalog
        await _send_catalog(update.message, uid, ctx)
    elif cb == "profile":
        from config.profile import _send_profile
        await _send_profile(update.message, uid, ctx)
    elif cb == "support":
        await _send_support(update.message, uid, ctx)
    elif cb == "pro_menu":
        await _send_pro(update.message, uid, ctx)
    elif cb == "panel":
        if owner_check(uid):
            from config.panel import _send_panel
            await _send_panel(update.message, uid, ctx)

    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════
#  ОНБОРДИНГ
# ══════════════════════════════════════════════════════════════

async def _onboarding(update: Update, ctx: ContextTypes.DEFAULT_TYPE, u) -> int:
    uid  = update.effective_user.id
    name = user_name(u) if u else update.effective_user.first_name or "друг"

    ref_msg = ""
    if ctx.user_data.pop("ref_bonus", False):
        ref_msg = "\n\n🎁 Пришёл по реферальной ссылке — добро пожаловать!"

    msg = await update.message.reply_text(
        f"Привет, **{name}**! 👋{ref_msg}\n\n"
        "**КПП** — платформа для поиска команды и участников.\n\n"
        "Ты здесь чтобы...",
        reply_markup=kb_main_inline(owner_check(uid)),
        parse_mode=MD,
    )
    await save_bot_msg(ctx, msg)
    return S_ONBOARD


async def onboard_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    d   = q.data

    user_set(uid, onboarding=1)

    if d == "ob_find":
        text = (
            "В **Витрине** найдёшь открытые анкеты — "
            "фильтруй и подавай заявки.\n\nГлавное меню 👇"
        )
    else:
        text = (
            "Нажми **«📋 Анкеты»** внизу экрана — "
            "за пару минут создашь анкету и получишь ссылку.\n\n"
            f"Бесплатно: до **{FREE_PROJ_LIMIT} анкет**. Больше — на Pro.\n\n"
            "Главное меню 👇"
        )

    # показываем ReplyKeyboard первый раз
    msg = await q.message.reply_text(
        text,
        reply_markup=reply_main(owner_check(uid)),
        parse_mode=MD,
    )
    await q.message.delete()
    await save_bot_msg(ctx, msg)
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════
#  ГЛАВНОЕ МЕНЮ
# ══════════════════════════════════════════════════════════════

async def _show_main(target, uid: int, ctx: ContextTypes.DEFAULT_TYPE, is_new=False) -> None:
    """target — Message."""
    u         = user_get(uid)
    returning = u and u["last_seen"] != u["created_at"]
    pro       = is_pro(uid)

    greeting  = (f"С возвращением, **{user_name(u)}**! 👋"
                 if returning else f"Привет, **{user_name(u)}**! 👋")
    pro_line  = "\n⭐ **Pro активен**" if pro else f"\n_Бесплатный тариф — до {FREE_PROJ_LIMIT} анкет_"

    msg = await target.reply_text(
        f"{greeting}{pro_line}\n\nВыбирай что нужно 👇",
        reply_markup=reply_main(owner_check(uid)),
        parse_mode=MD,
    )
    await save_bot_msg(ctx, msg)


async def _show_main_new(update: Update, uid: int, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет главное меню как новое сообщение (для Reply кнопки 🏠 Меню)."""
    await delete_prev(update, ctx)
    u   = user_get(uid)
    pro = is_pro(uid)
    pro_line = "\n⭐ **Pro активен**" if pro else f"\n_Бесплатный тариф — до {FREE_PROJ_LIMIT} анкет_"
    msg = await update.message.reply_text(
        f"**{user_name(u)}**{pro_line}\n\nГлавное меню 👇",
        reply_markup=reply_main(owner_check(uid)),
        parse_mode=MD,
    )
    await save_bot_msg(ctx, msg)


async def show_main_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """cancel / back_main — возврат в главное меню через callback."""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    ctx.user_data.clear()

    u   = user_get(uid)
    pro = is_pro(uid)
    pro_line = "\n⭐ **Pro активен**" if pro else f"\n_До {FREE_PROJ_LIMIT} анкет бесплатно_"

    await safe_edit(q, ctx, 
        f"**{user_name(u)}**{pro_line}\n\nВыбирай 👇",
        reply_markup=kb_main_inline(owner_check(uid)),
        parse_mode=MD,
    )
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════
#  ВСПОМОГАТЕЛЬНЫЕ ОТПРАВКИ (для Reply кнопок)
# ══════════════════════════════════════════════════════════════

async def _send_support(msg, uid: int, ctx) -> None:
    from config.keyboards import kb_support
    await delete_prev(ctx=ctx, update=msg._bot and None or msg)
    sent = await msg.reply_text(
        "💬 **Поддержка**\n\nЕсть вопрос или что-то пошло не так?\nНапиши нам.",
        reply_markup=kb_support(), parse_mode=MD,
    )
    await save_bot_msg(ctx, sent)


async def _send_pro(msg, uid: int, ctx) -> None:
    u       = user_get(uid)
    pro     = is_pro(uid)
    ref_url = reflink(u["ref_code"]) if u else "—"
    ref_cnt = u.get("ref_count", 0) if u else 0

    if pro and u and u.get("pro_until"):
        status = f"⭐ **Pro активен до:** {u['pro_until'][:10]}"
    else:
        status = "Сейчас у тебя бесплатный тариф."

    sent = await msg.reply_text(
        f"⭐ **Pro тариф**\n\n{status}\n\n"
        "**Что входит:**\n"
        "• Безлимит анкет\n"
        "• Место в витрине\n"
        "• Приоритет в поиске\n"
        "• Значок ⭐ в профиле\n"
        "• Расширенная статистика\n\n"
        f"**Рефералка:** приведи друга — оба получат бонус.\n"
        f"Приглашено: **{ref_cnt}** чел.\n"
        f"Ссылка: `{ref_url}`",
        reply_markup=kb_pro(ref_url), parse_mode=MD,
    )
    await save_bot_msg(ctx, sent)


# ══════════════════════════════════════════════════════════════
#  DEEP LINK
# ══════════════════════════════════════════════════════════════

async def _deeplink_project(update: Update, ctx: ContextTypes.DEFAULT_TYPE, pid: str) -> int:
    uid = update.effective_user.id
    p   = proj_get(pid)

    if not p:
        await update.message.reply_text(
            "😕 Анкета не найдена — возможно, её уже удалили.",
            reply_markup=reply_main(owner_check(uid)),
        )
        return ConversationHandler.END

    if not p["is_open"]:
        await update.message.reply_text(
            f"🔒 Анкета **«{p['title']}»** сейчас закрыта.",
            reply_markup=reply_main(owner_check(uid)), parse_mode=MD,
        )
        return ConversationHandler.END

    existing = app_for_user(uid, pid)
    if existing and existing["status"] == "pending":
        from config.keyboards import kb_existing_app
        await update.message.reply_text(
            f"📬 У тебя уже есть заявка в **«{p['title']}»**.\n🆔 `{existing['id']}`",
            reply_markup=kb_existing_app(existing["id"]), parse_mode=MD,
        )
        return ConversationHandler.END

    ctx.user_data["applying_pid"] = pid
    from config.db import default_template
    tpl = p["template"] or default_template(p["ptype"])

    if p["ptype"] == "members":
        text = f"📋 **{p['title']}**\n\n{p['description']}\n\nРасскажи о себе:"
    else:
        text = f"📋 **{p['title']}**\n\nЗаполни анкету:\n\n{tpl}"

    await update.message.reply_text(text, reply_markup=kb_cancel(), parse_mode=MD)
    return S_APP_FILL


# ══════════════════════════════════════════════════════════════
#  ОПЛАТА ЗВЁЗДАМИ
#  ⚠️ Внешняя настройка: fragment.com → подключить бота
# ══════════════════════════════════════════════════════════════

async def show_pro_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u   = user_get(uid)
    pro = is_pro(uid)

    status  = (f"⭐ **Pro до:** {u['pro_until'][:10]}"
               if pro and u and u.get("pro_until")
               else "Сейчас у тебя бесплатный тариф.")
    ref_url = reflink(u["ref_code"]) if u else "—"
    ref_cnt = u.get("ref_count", 0) if u else 0

    await safe_edit(q, ctx, 
        f"⭐ **Pro тариф**\n\n{status}\n\n"
        "**Возможности Pro:**\n"
        "• Безлимит анкет\n• Место в витрине\n• Приоритет в поиске\n"
        "• Значок ⭐\n• Расширенная статистика\n\n"
        f"**Рефералка:** `{ref_url}`\nПриглашено: {ref_cnt} чел.",
        reply_markup=kb_pro(ref_url), parse_mode=MD,
    )


async def share_ref(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q   = update.callback_query
    await q.answer()
    u   = user_get(q.from_user.id)
    url = reflink(u["ref_code"]) if u else "—"
    await safe_edit(q, ctx, 
        f"📤 **Твоя реферальная ссылка:**\n\n`{url}`\n\n"
        f"Приглашено: **{u.get('ref_count',0)}** чел.",
        reply_markup=kb_back("pro_menu"), parse_mode=MD,
    )


async def buy_plan(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q    = update.callback_query
    await q.answer()
    uid  = q.from_user.id
    plan = q.data.replace("buy_", "")
    if plan not in PLANS:
        return
    p = PLANS[plan]
    from telegram import LabeledPrice
    inv_msg = await ctx.bot.send_invoice(
        chat_id=uid,
        title=f"КПП Pro — {p['label']}",
        description="Безлимит анкет • Витрина • Приоритет • Статистика",
        payload=f"pro_{plan}",
        currency="XTR",
        prices=[LabeledPrice(p["label"], p["stars"])],
        provider_token="",
    )


async def pre_checkout(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.pre_checkout_query.answer(ok=True)


async def successful_payment(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid     = update.effective_user.id
    payment = update.message.successful_payment
    plan    = payment.invoice_payload.replace("pro_", "")
    stars   = payment.total_amount

    if plan not in PLANS:
        await update.message.reply_text("Оплата получена — напиши в поддержку для активации.")
        return

    from config.db import sub_create, activate_pro
    sub_create(uid, plan, stars, str(payment.telegram_payment_charge_id))
    u = user_get(uid)

    if u and u.get("referred_by"):
        activate_pro(u["referred_by"], 3)
        try:
            await ctx.bot.send_message(
                u["referred_by"],
                "🎁 Твой друг оформил Pro — тебе **+3 дня** бонуса!",
                parse_mode=MD,
            )
        except Exception:
            pass

    await update.message.reply_text(
        f"🎉 **Pro активирован!**\n\n"
        f"Тариф: {PLANS[plan]['label']}\n"
        f"До: **{u['pro_until'][:10] if u else '—'}**\n\n"
        "Спасибо за поддержку ⭐",
        reply_markup=reply_main(owner_check(uid)), parse_mode=MD,
    )
