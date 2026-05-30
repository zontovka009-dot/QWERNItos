"""
config/projects.py — Управление проектами, заявками, отзывами.
"""

import logging
from telegram import Update, InlineKeyboardButton as B, InlineKeyboardMarkup as K
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from config.db import (
    proj_get, proj_list, proj_set, proj_delete, proj_can_manage,
    proj_count, proj_limit, is_pro, padmin_list,
    app_get, app_pending, app_all, app_for_user, app_user_all,
    app_create, app_set_status, app_set_answers,
    review_add, review_list, proj_rating,
    user_get, user_name, owner_check,
    deeplink, ptype_ru, s_icon, default_template,
)
from config.states import (
    S_APP_FILL, S_APP_EDIT,
    S_APPROVE_MSG, S_REJECT_REASON,
    S_PTPL, S_REVIEW_TEXT,
)

log = logging.getLogger("kpp.projects")
MD  = ParseMode.MARKDOWN


def _main(uid):
    from config.start import kb_main
    return kb_main(uid)

def _back(cb): return K([[B("‹ Назад", callback_data=cb)]])
def _cancel(): return K([[B("✕ Отмена", callback_data="cancel")]])


# ══════════════════════════════════════════════════════════════
#  СПИСОК ПРОЕКТОВ
# ══════════════════════════════════════════════════════════════

async def show_projects(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    ps  = proj_list(uid)

    if not ps:
        await q.edit_message_text(
            "📁 Проектов пока нет.\n\nСоздай первый набор — это займёт пару минут!",
            reply_markup=K([
                [B("📋 Создать набор", callback_data="create")],
                [B("‹ Назад",         callback_data="cancel")],
            ]),
        )
        return ConversationHandler.END

    pro   = is_pro(uid)
    limit = proj_limit(uid)
    cnt   = len(ps)
    hint  = f"\n_Слотов: {max(0, limit-cnt)}/{limit}_" if not pro else ""

    rows = []
    for p in ps:
        em = "🟢" if p["is_open"] else "🔴"
        tp = "👥" if p["ptype"] == "members" else "🛡️"
        vf = " ✔️" if p.get("is_verified") else ""
        rows.append([B(f"{em} {tp} {p['title']}{vf}", callback_data=f"p_{p['id']}")])
    rows.append([B("‹ Назад", callback_data="cancel")])

    await q.edit_message_text(
        f"📁 **Мои проекты** ({cnt}){hint}",
        reply_markup=K(rows), parse_mode=MD,
    )
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════
#  ДЕТАЛИ ПРОЕКТА
# ══════════════════════════════════════════════════════════════

async def show_project(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    pid = q.data[2:]  # strip "p_"

    p = proj_get(pid)
    if not p or not proj_can_manage(pid, uid):
        await q.edit_message_text("Проект не найден.", reply_markup=_main(uid))
        return ConversationHandler.END

    status  = "🟢 Открыт" if p["is_open"] else "🔴 Закрыт"
    pending = len(app_pending(pid))
    rating  = proj_rating(pid)
    stars   = f"{'⭐'*round(rating)} {rating}" if rating else "нет отзывов"
    toggle  = "🔴 Закрыть набор" if p["is_open"] else "🟢 Открыть набор"
    is_own  = p["owner_id"] == uid
    vf      = " ✔️ Верифицирован" if p.get("is_verified") else ""
    ft      = " 🔝 В топе" if p.get("is_featured") else ""

    rows = [
        [B(f"📋 Заявки ({pending})", callback_data=f"apps_{pid}"),
         B("📜 История",            callback_data=f"hist_{pid}")],
        [B("🔗 Ссылка",             callback_data=f"link_{pid}"),
         B("⭐ Отзывы",             callback_data=f"reviews_{pid}")],
        [B(toggle,                  callback_data=f"toggle_{pid}")],
    ]
    if is_own:
        rows.append([B("✏️ Шаблон анкеты", callback_data=f"tpl_{pid}"),
                     B("🗑 Удалить",       callback_data=f"del_{pid}")])
    rows.append([B("‹ Проекты", callback_data="projects")])

    await q.edit_message_text(
        f"📁 **{p['title']}**{vf}{ft}\n\n"
        f"Тип: {ptype_ru(p['ptype'])}\n"
        f"Статус: {status}\n"
        f"Заявок: {p['apps_total']} / принято: {p['apps_approved']}\n"
        f"Рейтинг: {stars}\n"
        f"🆔 `{pid}`",
        reply_markup=K(rows), parse_mode=MD,
    )
    return ConversationHandler.END


async def show_project_apps(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    pid = q.data[5:]  # strip "apps_"

    if not proj_can_manage(pid, uid):
        await q.edit_message_text("Нет доступа."); return ConversationHandler.END

    ps = app_pending(pid)
    if not ps:
        await q.edit_message_text("📭 Активных заявок пока нет.", reply_markup=_back(f"p_{pid}"))
        return ConversationHandler.END

    rows = [[B(f"📄 {a['id']} — @{a['username']}", callback_data=f"app_{a['id']}")] for a in ps[:20]]
    rows.append([B("‹ Назад", callback_data=f"p_{pid}")])
    await q.edit_message_text(
        f"📋 **Заявки на рассмотрении ({len(ps)})**",
        reply_markup=K(rows), parse_mode=MD,
    )
    return ConversationHandler.END


async def show_project_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    pid = q.data[5:]  # strip "hist_"

    if not proj_can_manage(pid, uid):
        await q.edit_message_text("Нет доступа."); return ConversationHandler.END

    ps = app_all(pid)
    if not ps:
        await q.edit_message_text("История пуста.", reply_markup=_back(f"p_{pid}"))
        return ConversationHandler.END

    text = f"📜 **История заявок ({len(ps)})**\n\n"
    for a in ps[:40]:
        text += f"{s_icon(a['status'])} `{a['id']}` @{a['username']} — {a['created_at'][:10]}\n"
    await q.edit_message_text(text, reply_markup=_back(f"p_{pid}"), parse_mode=MD)
    return ConversationHandler.END


async def show_project_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    pid  = q.data[5:]
    link = deeplink(pid)
    await q.edit_message_text(
        f"🔗 **Ссылка для набора:**\n\n`{link}`\n\n"
        "Поделись ею — по клику сразу откроется форма заявки.",
        reply_markup=_back(f"p_{pid}"), parse_mode=MD,
    )
    return ConversationHandler.END


async def toggle_project(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    pid = q.data[7:]
    p   = proj_get(pid)
    if p and p["owner_id"] == uid:
        proj_set(pid, is_open=0 if p["is_open"] else 1)
        # уведомить подписчиков если открыли
        if not p["is_open"]:
            from config.db import followers_of, notif_add
            for fid in followers_of(pid):
                notif_add(fid, "project_open", pid)
    await show_project(update, ctx)
    return ConversationHandler.END


async def delete_project_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    pid = q.data[4:]
    await q.edit_message_text(
        "⚠️ Удалить проект и все заявки к нему?\nЭто действие необратимо.",
        reply_markup=K([
            [B("✅ Да, удалить", callback_data=f"del_do_{pid}"),
             B("‹ Отмена",      callback_data=f"p_{pid}")],
        ]),
    )
    return ConversationHandler.END


async def delete_project_do(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    pid = q.data[7:]
    p   = proj_get(pid)
    if p and p["owner_id"] == uid:
        proj_delete(pid)
    await show_projects(update, ctx)
    return ConversationHandler.END


async def start_edit_template(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    pid = q.data[4:]
    ctx.user_data["tpl_pid"] = pid
    p   = proj_get(pid)
    cur = p["template"] if p else ""
    await q.edit_message_text(
        f"✏️ Текущий шаблон:\n\n{cur or '(пусто)'}\n\nОтправь новый:",
        reply_markup=K([[B("✕ Отмена", callback_data="cancel"),
                         B("Оставить", callback_data="tpl_skip")]]),
    )
    return S_PTPL


# ── эти два обработчика уже в create_nabor, здесь stub'ы ────

async def on_proj_template_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    pid = ctx.user_data.pop("tpl_pid", None)
    if pid:
        proj_set(pid, template=update.message.text.strip())
    await update.message.reply_text("✅ Шаблон обновлён!", reply_markup=_main(update.effective_user.id))
    return ConversationHandler.END

async def finish_proj_template(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    pid = ctx.user_data.pop("tpl_pid", None)
    if pid:
        p = proj_get(pid)
        if p:
            proj_set(pid, template=default_template(p["ptype"]))
    await q.edit_message_text("✅ Шаблон оставлен стандартным.", reply_markup=_main(q.from_user.id))
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════
#  ЗАЯВКИ — просмотр
# ══════════════════════════════════════════════════════════════

async def show_app_detail(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    aid = q.data[4:]

    a = app_get(aid)
    if not a:
        await q.edit_message_text("Заявка не найдена."); return ConversationHandler.END
    if not proj_can_manage(a["project_id"], uid):
        await q.edit_message_text("Нет доступа."); return ConversationHandler.END

    sm = {
        "pending":   "⏳ На рассмотрении",
        "approved":  "✅ Одобрена",
        "rejected":  "❌ Отклонена",
        "cancelled": "🚫 Отозвана",
    }
    rows = []
    if a["status"] == "pending":
        rows = [
            [B("✅ Одобрить",       callback_data=f"apr_{aid}"),
             B("✅ + Сообщение",    callback_data=f"apr_msg_{aid}")],
            [B("❌ Отклонить",      callback_data=f"rjt_{aid}")],
        ]
    rows.append([B("‹ Заявки", callback_data=f"apps_{a['project_id']}")])

    await q.edit_message_text(
        f"📄 **Заявка {aid}**\n\n"
        f"👤 @{a['username']} (`{a['user_id']}`)\n"
        f"Статус: {sm.get(a['status'], a['status'])}\n"
        f"Дата: {a['created_at'][:16]}\n\n"
        f"**Текст заявки:**\n{a['answers']}",
        reply_markup=K(rows), parse_mode=MD,
    )
    return ConversationHandler.END


# ── отправка заявки ───────────────────────────────────────────

async def submit_app(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    aid = q.data[7:]

    a = app_get(aid)
    if not a or a["user_id"] != uid:
        return ConversationHandler.END
    p = proj_get(a["project_id"])
    if not p:
        return ConversationHandler.END

    notify_ids = set([p["owner_id"]] + padmin_list(a["project_id"]))
    for nid in notify_ids:
        try:
            await ctx.bot.send_message(
                nid,
                f"📨 **Новая заявка!**\n\n"
                f"Проект: **{p['title']}**\n"
                f"🆔 `{aid}`\n"
                f"👤 @{a['username']} (`{a['user_id']}`)\n\n"
                f"{a['answers'][:600]}",
                reply_markup=K([[B("📄 Просмотреть", callback_data=f"app_{aid}")]]),
                parse_mode=MD,
            )
        except Exception as e:
            log.warning(f"notify {nid}: {e}")

    await q.edit_message_text(
        "✅ Заявка отправлена на рассмотрение!\n\n"
        "Как только примут решение — ты сразу узнаешь.",
        reply_markup=_main(uid),
    )
    return ConversationHandler.END


async def edit_app_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    aid = q.data[9:]
    a   = app_get(aid)
    if not a or a["user_id"] != uid:
        return ConversationHandler.END
    p   = proj_get(a["project_id"])
    tpl = f"\n\nШаблон:\n{p['template']}" if p and p["template"] else ""
    ctx.user_data["edit_aid"] = aid
    await q.edit_message_text(
        f"✏️ Напиши обновлённую заявку:{tpl}", reply_markup=_cancel()
    )
    return S_APP_EDIT

async def on_app_edit(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    aid = ctx.user_data.pop("edit_aid", None)

    # первое заполнение (S_APP_FILL)
    if not aid:
        pid = ctx.user_data.pop("applying_pid", None)
        if not pid:
            await update.message.reply_text("Что-то пошло не так.", reply_markup=_main(uid))
            return ConversationHandler.END
        uname = update.effective_user.username or f"user{uid}"
        aid   = app_create(pid, uid, uname, update.message.text.strip())
        await update.message.reply_text(
            f"📝 **Заявка сохранена!**\n🆔 `{aid}`\n\n{update.message.text.strip()[:400]}",
            reply_markup=K([
                [B("📤 Отправить на рассмотрение", callback_data=f"submit_{aid}")],
                [B("✏️ Изменить", callback_data=f"edit_app_{aid}"),
                 B("❌ Отозвать", callback_data=f"cancel_app_{aid}")],
            ]),
            parse_mode=MD,
        )
        return ConversationHandler.END

    # редактирование существующей
    app_set_answers(aid, update.message.text.strip())
    await update.message.reply_text(
        "✅ Заявка обновлена!",
        reply_markup=K([
            [B("📤 Отправить на рассмотрение", callback_data=f"submit_{aid}")],
            [B("‹ Меню", callback_data="cancel")],
        ]),
    )
    return ConversationHandler.END

async def cancel_app(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    aid = q.data[11:]
    a   = app_get(aid)
    if a and a["user_id"] == uid:
        app_set_status(aid, "cancelled")
        await q.edit_message_text("🚫 Заявка отозвана.", reply_markup=_main(uid))
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════
#  ОДОБРЕНИЕ / ОТКЛОНЕНИЕ
# ══════════════════════════════════════════════════════════════

async def approve_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    d   = q.data  # "apr_AID" или "apr_msg_AID"

    if d.startswith("apr_msg_"):
        aid = d[8:]
        ctx.user_data["apr_aid"] = aid
        await q.edit_message_text(
            "✉️ Напиши личное сообщение кандидату.\n"
            "Придёт вместе с уведомлением об одобрении.\n\n"
            "Или напиши **нет** чтобы одобрить без доп. текста:",
            reply_markup=_cancel(), parse_mode=MD,
        )
        return S_APPROVE_MSG
    else:
        aid = d[4:]
        await _do_approve(q, ctx, aid, None)
        return ConversationHandler.END

async def on_approve_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid  = update.effective_user.id
    aid  = ctx.user_data.pop("apr_aid", None)
    if not aid:
        return ConversationHandler.END
    text     = update.message.text.strip()
    personal = None if text.lower() == "нет" else text
    await _do_approve_msg(update.message, ctx, aid, personal)
    return ConversationHandler.END

async def reject_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    aid = q.data[4:]
    ctx.user_data["rjt_aid"] = aid
    await q.edit_message_text(
        "❌ Напиши причину отклонения.\n\nИли **нет** — без комментария:",
        reply_markup=_cancel(), parse_mode=MD,
    )
    return S_REJECT_REASON

async def on_reject_reason(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid    = update.effective_user.id
    aid    = ctx.user_data.pop("rjt_aid", None)
    if not aid:
        return ConversationHandler.END
    text   = update.message.text.strip()
    reason = "Без комментария" if text.lower() == "нет" else text
    a = app_get(aid)
    if not a or a["status"] != "pending":
        await update.message.reply_text("Заявка уже обработана.", reply_markup=_main(uid))
        return ConversationHandler.END
    app_set_status(aid, "rejected", reason, uid)
    try:
        await ctx.bot.send_message(a["user_id"], f"❌ Твоя заявка отклонена.\nПричина: {reason}")
    except Exception as e:
        log.warning(f"notify rejected: {e}")
    await update.message.reply_text(
        f"❌ Заявка `{aid}` отклонена.",
        reply_markup=_main(uid), parse_mode=MD,
    )
    return ConversationHandler.END


async def _do_approve(q_or_msg, ctx, aid, personal):
    is_cb = hasattr(q_or_msg, "edit_message_text")
    uid   = q_or_msg.from_user.id
    a     = app_get(aid)
    if not a or a["status"] != "pending":
        txt = "Заявка уже обработана."
        if is_cb: await q_or_msg.edit_message_text(txt)
        else:     await q_or_msg.reply_text(txt)
        return
    p = proj_get(a["project_id"])
    app_set_status(aid, "approved", "Одобрено", uid)
    notify = "🎉 Твоя заявка одобрена!"
    if p and p["chat_link"]:
        notify += f"\n\n🔗 Вступай: {p['chat_link']}"
    if personal:
        notify += f"\n\n✉️ Сообщение:\n{personal}"
    try:
        await ctx.bot.send_message(a["user_id"], notify)
    except Exception as e:
        log.warning(f"notify approved: {e}")
    txt = f"✅ Заявка `{aid}` одобрена."
    back = K([[B("‹ Заявки", callback_data=f"apps_{a['project_id']}")]])
    if is_cb: await q_or_msg.edit_message_text(txt, reply_markup=back, parse_mode=MD)
    else:     await q_or_msg.reply_text(txt, reply_markup=_main(uid), parse_mode=MD)

async def _do_approve_msg(msg, ctx, aid, personal):
    await _do_approve(msg, ctx, aid, personal)


# ══════════════════════════════════════════════════════════════
#  ОТЗЫВЫ
# ══════════════════════════════════════════════════════════════

async def show_reviews(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    pid = q.data[8:]

    reviews = review_list(pid)
    rating  = proj_rating(pid)
    p       = proj_get(pid)
    pname   = p["title"] if p else pid

    # проверяем может ли пользователь оставить отзыв
    # (только принятые участники)
    a = app_for_user(uid, pid)
    can_review = a and a["status"] == "approved"

    text = f"⭐ **Отзывы о «{pname}»**\n\nРейтинг: {rating}/5\n\n"
    if reviews:
        for r in reviews[:10]:
            u = user_get(r["user_id"])
            nm = user_name(u) if u else str(r["user_id"])
            stars = "⭐" * r["rating"]
            text += f"{stars} **{nm}**\n{r['text'] or '_без комментария_'}\n\n"
    else:
        text += "_Отзывов пока нет_"

    rows = []
    if can_review:
        rows.append([B("✏️ Оставить отзыв", callback_data=f"review_{pid}")])
    rows.append([B("‹ Назад", callback_data=f"p_{pid}")])

    await q.edit_message_text(text, reply_markup=K(rows), parse_mode=MD)
    return ConversationHandler.END


async def leave_review_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    pid = q.data[7:]
    ctx.user_data["review_pid"] = pid
    await q.edit_message_text(
        "⭐ Оцени проект от 1 до 5:",
        reply_markup=K([
            [B("1 ⭐", callback_data=f"rv_1_{pid}"),
             B("2 ⭐", callback_data=f"rv_2_{pid}"),
             B("3 ⭐", callback_data=f"rv_3_{pid}"),
             B("4 ⭐", callback_data=f"rv_4_{pid}"),
             B("5 ⭐", callback_data=f"rv_5_{pid}")],
            [B("✕ Отмена", callback_data="cancel")],
        ]),
    )
    return S_REVIEW_TEXT

async def on_review_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    # обработчик текстового комментария к отзыву
    q = update.callback_query if update.callback_query else None
    msg = update.message

    if q and q.data.startswith("rv_"):
        await q.answer()
        parts  = q.data.split("_")
        rating = int(parts[1])
        pid    = parts[2]
        ctx.user_data["review_pid"]    = pid
        ctx.user_data["review_rating"] = rating
        await q.edit_message_text(
            f"Оценка: {'⭐'*rating}\n\nДобавь комментарий или напиши **пропустить**:",
            reply_markup=_cancel(), parse_mode=MD,
        )
        return S_REVIEW_TEXT

    if msg:
        uid    = msg.from_user.id
        pid    = ctx.user_data.pop("review_pid", None)
        rating = ctx.user_data.pop("review_rating", 5)
        text   = msg.text.strip()
        comment = "" if text.lower() == "пропустить" else text

        if pid:
            ok = review_add(pid, uid, rating, comment)
            if ok:
                await msg.reply_text(
                    f"✅ Отзыв сохранён — {'⭐'*rating}",
                    reply_markup=_main(uid),
                )
            else:
                await msg.reply_text(
                    "Ты уже оставлял отзыв на этот проект.",
                    reply_markup=_main(uid),
                )
        return ConversationHandler.END

    return ConversationHandler.END
