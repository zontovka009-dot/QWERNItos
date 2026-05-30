"""
config/panel.py — Панель управления ботом.
Доступно только владельцам из bot_owners.
"""

import logging
from telegram import Update, InlineKeyboardButton as B, InlineKeyboardMarkup as K
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from config.db import (
    owner_check, owner_list, owner_add, owner_remove,
    user_get, user_set, user_list, user_count, user_search, user_name,
    ban_check, ban_add, ban_remove, ban_list,
    warn_add, warn_reset,
    proj_get, proj_list, proj_set, proj_delete,
    padmin_list, app_pending, app_all,
    ticket_open, ticket_close,
    stats_get, s_icon,
    is_pro,
)
from config.states import (
    S_ADMIN_BAN_ID, S_ADMIN_BAN_REASON,
    S_ADMIN_UNBAN, S_ADMIN_ADD_OWNER,
    S_ADMIN_SEARCH, S_ADMIN_EDIT_BIO,
    S_ADMIN_BROADCAST,
)

log = logging.getLogger("kpp.panel")
MD  = ParseMode.MARKDOWN


def _main(uid):
    from config.start import kb_main
    return kb_main(uid)

def _cancel(): return K([[B("✕ Отмена", callback_data="cancel")]])
def _back(cb): return K([[B("‹ Назад",  callback_data=cb)]])

def _guard(uid) -> bool:
    return owner_check(uid)


# ══════════════════════════════════════════════════════════════
#  ГЛАВНАЯ ПАНЕЛЬ
# ══════════════════════════════════════════════════════════════

async def show_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if not _guard(uid): return ConversationHandler.END

    s       = stats_get()
    owners  = owner_list()
    tickets = s.get("open_tickets", 0)

    rows = [
        [B(f"📩 Обращения ({tickets})", callback_data="pnl_tickets"),
         B("📊 Статистика",            callback_data="pnl_stats")],
        [B("👥 Пользователи",          callback_data="pnl_users"),
         B("🔍 Поиск",                 callback_data="pnl_search")],
        [B("🚫 Баны",                  callback_data="pnl_bans")],
        [B("🚫 Заблокировать",         callback_data="pnl_ban"),
         B("✅ Разблокировать",        callback_data="pnl_unban")],
        [B("👑 Добавить владельца",    callback_data="pnl_owner")],
        [B("📣 Рассылка",             callback_data="pnl_broadcast")],
    ]
    for o in owners:
        if o["user_id"] != uid:
            nm = o["username"] or str(o["user_id"])
            rows.append([B(f"❌ Снять @{nm}", callback_data=f"rm_owner_{o['user_id']}")])
    rows.append([B("‹ Главное меню", callback_data="cancel")])

    await q.edit_message_text(
        f"⚙️ **Панель управления**\n\n"
        f"👥 Пользователей: {s.get('users',0)} "
        f"(активных: {s.get('active_users',0)}, Pro: {s.get('pro_users',0)})\n"
        f"📁 Проектов: {s.get('projects',0)} / открытых: {s.get('open_projects',0)}\n"
        f"📄 Заявок: {s.get('apps',0)} / принято: {s.get('approved',0)}\n"
        f"⭐ Звёзд собрано: {s.get('stars_earned',0)}\n"
        f"📩 Обращений: {tickets}\n"
        f"🚫 Заблокированных: {s.get('banned_count',0)}",
        reply_markup=K(rows), parse_mode=MD,
    )
    return ConversationHandler.END


# ── статистика ────────────────────────────────────────────────

async def show_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    if not _guard(q.from_user.id): return ConversationHandler.END
    s   = stats_get()
    await q.edit_message_text(
        f"📊 **Статистика**\n\n"
        f"👥 Всего: {s.get('users',0)}\n"
        f"   └ Активных: {s.get('active_users',0)}\n"
        f"   └ Pro: {s.get('pro_users',0)}\n"
        f"   └ Забанено: {s.get('banned_count',0)}\n\n"
        f"📁 Проектов: {s.get('projects',0)} / открытых: {s.get('open_projects',0)}\n\n"
        f"📄 Заявок: {s.get('apps',0)} / принято: {s.get('approved',0)}\n\n"
        f"⭐ Звёзд собрано: {s.get('stars_earned',0)}\n"
        f"📩 Открытых обращений: {s.get('open_tickets',0)}\n"
        f"🏆 Отзывов: {s.get('total_reviews',0)}",
        reply_markup=_back("panel"), parse_mode=MD,
    )
    return ConversationHandler.END


# ── обращения ────────────────────────────────────────────────

async def show_tickets(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    if not _guard(q.from_user.id): return ConversationHandler.END
    ts  = ticket_open()
    if not ts:
        await q.edit_message_text("Открытых обращений нет.", reply_markup=_back("panel"))
        return ConversationHandler.END
    text = f"📩 **Обращения ({len(ts)})**\n\n"
    rows = []
    for t in ts[:20]:
        text += f"`{t['id']}` @{t['username']} — {t['created_at'][:10]}\n"
        rows.append([B(f"💬 {t['id']} — @{t['username']}",
                       callback_data=f"t_rpl_{t['id']}_{t['user_id']}")])
    rows.append([B("‹ Назад", callback_data="panel")])
    await q.edit_message_text(text, reply_markup=K(rows), parse_mode=MD)
    return ConversationHandler.END


# ── список пользователей ─────────────────────────────────────

async def show_users_page(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q      = update.callback_query
    await q.answer()
    uid    = q.from_user.id
    if not _guard(uid): return ConversationHandler.END

    offset = 0
    if q.data.startswith("upage_"):
        offset = int(q.data[6:]) * 20

    users  = user_list(limit=20, offset=offset)
    total  = user_count()

    rows = []
    for u in users:
        bm   = " ⛔" if u["is_banned"] else ""
        pro  = " ⭐" if is_pro(u["id"]) else ""
        nm   = f"@{u['username']}" if u["username"] else str(u["id"])
        rows.append([B(f"{nm}{bm}{pro}", callback_data=f"adm_user_{u['id']}")])

    nav = []
    if offset > 0:
        nav.append(B("‹", callback_data=f"upage_{(offset-20)//20}"))
    if offset + 20 < total:
        nav.append(B("›", callback_data=f"upage_{(offset+20)//20}"))
    if nav:
        rows.append(nav)
    rows.append([B("🔍 Поиск", callback_data="pnl_search"),
                 B("‹ Панель", callback_data="panel")])

    await q.edit_message_text(
        f"👥 **Пользователи** ({offset+1}–{min(offset+20,total)} из {total})",
        reply_markup=K(rows), parse_mode=MD,
    )
    return ConversationHandler.END


# ── карточка пользователя ────────────────────────────────────

async def show_user_card(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q      = update.callback_query
    await q.answer()
    uid    = q.from_user.id
    if not _guard(uid): return ConversationHandler.END
    target = int(q.data[9:])   # strip "adm_user_"
    return await _render_user_card(q, target)


async def _render_user_card(q, target_id: int) -> int:
    u = user_get(target_id)
    if not u:
        await q.edit_message_text("Пользователь не найден.", reply_markup=_back("pnl_users"))
        return ConversationHandler.END

    projs  = proj_list(target_id)
    banned = "⛔ Заблокирован" if u["is_banned"] else "✅ Активен"
    warns  = u.get("warn_count", 0)
    pro    = is_pro(target_id)
    pro_s  = f"⭐ Pro (до {u['pro_until'][:10]})" if pro and u.get("pro_until") else "Бесплатный"

    text = (
        f"👤 **{user_name(u)}**\n\n"
        f"Ник: @{u['username'] or '—'}\n"
        f"Имя: {u['first_name'] or '—'}\n"
        f"ID: `{target_id}`\n"
        f"Статус: {banned}\n"
        f"Тариф: {pro_s}\n"
        f"Предупреждений: {warns}/3\n"
        f"Проектов: {len(projs)}\n"
        f"В боте с: {u['created_at'][:10]}\n"
        f"Активен: {u['last_seen'][:10]}\n\n"
        f"Bio: {u['bio'] or '_не указано_'}\n"
        f"Навыки: {u.get('skills') or '_не указаны_'}\n"
        f"Аватар: {'есть ✅' if u['avatar_fid'] else 'нет'}"
    )

    rows = []
    if projs:
        rows.append([B(f"📁 Проекты ({len(projs)})", callback_data=f"adm_projs_{target_id}")])
    rows.append([B("✏️ Изменить bio", callback_data=f"adm_bio_{target_id}")])
    if u["avatar_fid"]:
        rows.append([B("🗑 Удалить аватар", callback_data=f"adm_delavatar_{target_id}")])
    rows.append([
        B(f"⚠️ Варн ({warns}/3)", callback_data=f"warn_{target_id}"),
        B("✕ Снять варны",        callback_data=f"unwarn_{target_id}"),
    ])
    if u["is_banned"]:
        rows.append([B("✅ Разблокировать", callback_data=f"unban_{target_id}")])
    else:
        rows.append([B("🚫 Заблокировать",  callback_data=f"ban_{target_id}")])
    rows.append([B("‹ Пользователи", callback_data="pnl_users")])

    has_av = bool(u.get("avatar_fid"))
    if has_av:
        try:
            await q.message.delete()
            await q.message.chat.send_photo(
                photo=u["avatar_fid"], caption=text,
                reply_markup=K(rows), parse_mode=MD,
            )
            return ConversationHandler.END
        except Exception as e:
            log.warning(f"adm user card photo: {e}")

    await q.edit_message_text(text, reply_markup=K(rows), parse_mode=MD)
    return ConversationHandler.END


# ── проекты пользователя (для админа) ────────────────────────

async def show_user_projects(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q      = update.callback_query
    await q.answer()
    if not _guard(q.from_user.id): return ConversationHandler.END
    target = int(q.data[10:])   # strip "adm_projs_"
    ps     = proj_list(target)
    u      = user_get(target)
    nm     = f"@{u['username']}" if u and u["username"] else str(target)
    if not ps:
        await q.edit_message_text(
            f"У {nm} нет проектов.",
            reply_markup=_back(f"adm_user_{target}"),
        )
        return ConversationHandler.END
    rows = [
        [B(f"{'🟢' if p['is_open'] else '🔴'} {p['title']}",
           callback_data=f"adm_proj_{p['id']}_{target}")]
        for p in ps
    ]
    rows.append([B("‹ Назад", callback_data=f"adm_user_{target}")])
    await q.edit_message_text(
        f"📁 **Проекты {nm} ({len(ps)})**",
        reply_markup=K(rows), parse_mode=MD,
    )
    return ConversationHandler.END


async def show_admin_project(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q      = update.callback_query
    await q.answer()
    if not _guard(q.from_user.id): return ConversationHandler.END
    parts  = q.data[9:].rsplit("_", 1)   # strip "adm_proj_"
    pid, owner_id = parts[0], int(parts[1])
    p      = proj_get(pid)
    if not p:
        await q.edit_message_text("Проект не найден."); return ConversationHandler.END

    admins = padmin_list(pid)
    adm_names = []
    for a in admins:
        au = user_get(a)
        adm_names.append(f"@{au['username']}" if au and au["username"] else str(a))

    status = "🟢 Открыт" if p["is_open"] else "🔴 Закрыт"
    toggle = "🔴 Закрыть" if p["is_open"] else "🟢 Открыть"
    vf_btn = "✔️ Снять верификацию" if p.get("is_verified") else "✔️ Верифицировать"
    ft_btn = "🔝 Снять из топа" if p.get("is_featured") else "🔝 Поднять в топ"

    await q.edit_message_text(
        f"📁 **{p['title']}**\n\n"
        f"🆔 `{pid}`\n"
        f"Статус: {status}\n"
        f"Заявок: {p['apps_total']} / принято: {p['apps_approved']}\n"
        f"Ссылка: {p['chat_link'] or '—'}\n"
        f"Администраторы: {', '.join(adm_names) or 'нет'}",
        reply_markup=K([
            [B(f"📋 Заявки", callback_data=f"adm_apps_{pid}_{owner_id}"),
             B("📜 История", callback_data=f"adm_hist_{pid}_{owner_id}")],
            [B(toggle,       callback_data=f"adm_tgl_{pid}_{owner_id}")],
            [B(vf_btn,       callback_data=f"adm_verify_{pid}"),
             B(ft_btn,       callback_data=f"adm_feature_{pid}")],
            [B("🗑 Удалить проект", callback_data=f"adm_del_{pid}_{owner_id}")],
            [B("‹ Назад", callback_data=f"adm_projs_{owner_id}")],
        ]),
        parse_mode=MD,
    )
    return ConversationHandler.END


async def admin_toggle_project(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q     = update.callback_query
    await q.answer()
    if not _guard(q.from_user.id): return ConversationHandler.END
    parts = q.data[8:].rsplit("_", 1)   # strip "adm_tgl_"
    pid, owner_id = parts[0], int(parts[1])
    p = proj_get(pid)
    if p: proj_set(pid, is_open=0 if p["is_open"] else 1)
    return await show_admin_project(update, ctx)


async def admin_delete_project(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q     = update.callback_query
    await q.answer()
    if not _guard(q.from_user.id): return ConversationHandler.END
    parts = q.data[8:].rsplit("_", 1)   # strip "adm_del_"
    pid, owner_id = parts[0], int(parts[1])
    proj_delete(pid)
    return await show_user_projects(update, ctx)


async def admin_show_apps(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q     = update.callback_query
    await q.answer()
    if not _guard(q.from_user.id): return ConversationHandler.END
    parts = q.data[9:].rsplit("_", 1)   # strip "adm_apps_"
    pid, owner_id = parts[0], int(parts[1])
    ps    = app_pending(pid)
    if not ps:
        await q.edit_message_text(
            "Активных заявок нет.",
            reply_markup=_back(f"adm_proj_{pid}_{owner_id}"),
        )
        return ConversationHandler.END
    rows = [[B(f"📄 {a['id']} — @{a['username']}", callback_data=f"app_{a['id']}")] for a in ps[:20]]
    rows.append([B("‹ Назад", callback_data=f"adm_proj_{pid}_{owner_id}")])
    await q.edit_message_text(
        f"📋 **Активные заявки ({len(ps)})**",
        reply_markup=K(rows), parse_mode=MD,
    )
    return ConversationHandler.END


async def admin_show_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q     = update.callback_query
    await q.answer()
    if not _guard(q.from_user.id): return ConversationHandler.END
    parts = q.data[9:].rsplit("_", 1)   # strip "adm_hist_"
    pid, owner_id = parts[0], int(parts[1])
    ps    = app_all(pid)
    if not ps:
        await q.edit_message_text(
            "История пуста.",
            reply_markup=_back(f"adm_proj_{pid}_{owner_id}"),
        )
        return ConversationHandler.END
    text = f"📜 **История ({len(ps)})**\n\n"
    for a in ps[:40]:
        text += f"{s_icon(a['status'])} `{a['id']}` @{a['username']} — {a['created_at'][:10]}\n"
    await q.edit_message_text(
        text,
        reply_markup=_back(f"adm_proj_{pid}_{owner_id}"),
        parse_mode=MD,
    )
    return ConversationHandler.END


async def admin_verify_project(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    if not _guard(q.from_user.id): return ConversationHandler.END
    pid = q.data[11:]   # strip "adm_verify_"
    p   = proj_get(pid)
    if p:
        new_val = 0 if p.get("is_verified") else 1
        proj_set(pid, is_verified=new_val)
        action = "снята" if not new_val else "выдана"
        try:
            await ctx.bot.send_message(
                p["owner_id"],
                f"{'✔️' if new_val else 'ℹ️'} Верификация проекта **«{p['title']}»** {action}.",
                parse_mode=MD,
            )
        except: pass
    await q.answer(f"Верификация {'выдана' if p and not p.get('is_verified') else 'снята'}", show_alert=True)
    return ConversationHandler.END


async def admin_feature_project(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    if not _guard(q.from_user.id): return ConversationHandler.END
    pid = q.data[12:]   # strip "adm_feature_"
    p   = proj_get(pid)
    if p:
        new_val = 0 if p.get("is_featured") else 1
        proj_set(pid, is_featured=new_val)
    await q.answer("Статус топа обновлён", show_alert=True)
    return ConversationHandler.END


# ── баны ─────────────────────────────────────────────────────

async def show_bans(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    if not _guard(q.from_user.id): return ConversationHandler.END
    bans = ban_list()
    if not bans:
        await q.edit_message_text("Заблокированных нет.", reply_markup=_back("panel"))
        return ConversationHandler.END
    text = f"🚫 **Заблокированные ({len(bans)})**\n\n"
    rows = []
    for b in bans:
        text += f"• `{b['user_id']}` @{b['username']} — {b['reason']}\n"
        rows.append([B(f"✅ Разбанить {b['user_id']}", callback_data=f"unban_{b['user_id']}")])
    rows.append([B("‹ Назад", callback_data="panel")])
    await q.edit_message_text(text, reply_markup=K(rows), parse_mode=MD)
    return ConversationHandler.END


async def admin_warn(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q      = update.callback_query
    await q.answer()
    if not _guard(q.from_user.id): return ConversationHandler.END
    target = int(q.data[5:])   # strip "warn_"
    cnt    = warn_add(target)
    try:
        await ctx.bot.send_message(
            target,
            f"⚠️ Тебе выдано предупреждение. Всего: {cnt}/3.\n"
            "При 3 предупреждениях аккаунт будет заблокирован.",
        )
    except: pass
    if cnt >= 3:
        u = user_get(target)
        ban_add(target, u["username"] if u else "", "Автобан: 3 предупреждения", q.from_user.id)
        try:
            await ctx.bot.send_message(target, "⛔ Аккаунт заблокирован после 3 предупреждений.")
        except: pass
    return await _render_user_card(q, target)


async def admin_unwarn(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q      = update.callback_query
    await q.answer()
    if not _guard(q.from_user.id): return ConversationHandler.END
    target = int(q.data[7:])   # strip "unwarn_"
    warn_reset(target)
    return await _render_user_card(q, target)


async def admin_ban_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q      = update.callback_query
    await q.answer()
    if not _guard(q.from_user.id): return ConversationHandler.END
    target = int(q.data[4:])   # strip "ban_"
    ctx.user_data["ban_target"] = target
    await q.edit_message_text(
        f"Укажи причину блокировки пользователя `{target}`:",
        reply_markup=_cancel(), parse_mode=MD,
    )
    return S_ADMIN_BAN_REASON


async def on_admin_ban_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    if not _guard(uid): return ConversationHandler.END
    try:
        target = int(update.message.text.strip())
        ctx.user_data["ban_target"] = target
        await update.message.reply_text(
            f"Укажи причину блокировки `{target}`:", reply_markup=_cancel(), parse_mode=MD,
        )
        return S_ADMIN_BAN_REASON
    except ValueError:
        await update.message.reply_text("Нужен числовой ID.", reply_markup=_main(uid))
        return ConversationHandler.END


async def on_admin_ban_reason(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid    = update.effective_user.id
    target = ctx.user_data.pop("ban_target", None)
    if not target: return ConversationHandler.END
    reason = update.message.text.strip()
    u      = user_get(target)
    ban_add(target, u["username"] if u else "", reason, uid)
    try:
        await ctx.bot.send_message(target, f"⛔ Твой аккаунт заблокирован.\nПричина: {reason}")
    except: pass
    await update.message.reply_text(
        f"✅ Пользователь `{target}` заблокирован.\nПричина: {reason}",
        reply_markup=_main(uid), parse_mode=MD,
    )
    return ConversationHandler.END


async def admin_unban_direct(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q      = update.callback_query
    await q.answer()
    target = int(q.data[6:])   # strip "unban_"
    ban_remove(target)
    try: await ctx.bot.send_message(target, "✅ Твой аккаунт разблокирован.")
    except: pass
    if _guard(q.from_user.id):
        return await _render_user_card(q, target)
    await q.edit_message_text("✅ Разблокировано.", reply_markup=_main(q.from_user.id))
    return ConversationHandler.END


async def admin_unban_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    if not _guard(q.from_user.id): return ConversationHandler.END
    await q.edit_message_text("Отправь Telegram ID для разблокировки:", reply_markup=_cancel())
    return S_ADMIN_UNBAN


async def on_admin_unban(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    try:
        target = int(update.message.text.strip())
        ban_remove(target)
        try: await ctx.bot.send_message(target, "✅ Твой аккаунт разблокирован.")
        except: pass
        await update.message.reply_text(f"✅ {target} разблокирован.", reply_markup=_main(uid))
    except ValueError:
        await update.message.reply_text("Нужен числовой ID.", reply_markup=_main(uid))
    return ConversationHandler.END


# ── владельцы ────────────────────────────────────────────────

async def admin_add_owner_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    if not _guard(q.from_user.id): return ConversationHandler.END
    await q.edit_message_text(
        "Отправь Telegram ID аккаунта для выдачи прав владельца бота:",
        reply_markup=_cancel(),
    )
    return S_ADMIN_ADD_OWNER


async def on_admin_add_owner(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    try:
        target = int(update.message.text.strip())
        u      = user_get(target)
        owner_add(target, u["username"] if u else "")
        try: await ctx.bot.send_message(target, "👑 Тебе выданы права владельца КПП Бота.")
        except: pass
        await update.message.reply_text(f"✅ {target} теперь владелец бота.", reply_markup=_main(uid))
    except ValueError:
        await update.message.reply_text("Нужен числовой ID.", reply_markup=_main(uid))
    return ConversationHandler.END


async def admin_remove_owner(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q      = update.callback_query
    await q.answer()
    uid    = q.from_user.id
    target = int(q.data[9:])   # strip "rm_owner_"
    if _guard(uid) and target != uid:
        owner_remove(target)
        try: await ctx.bot.send_message(target, "ℹ️ Твои права владельца КПП Бота были сняты.")
        except: pass
    return await show_panel(update, ctx)


# ── поиск ────────────────────────────────────────────────────

async def admin_search_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    if not _guard(q.from_user.id): return ConversationHandler.END
    await q.edit_message_text("🔍 Введи Telegram ID, username или имя:", reply_markup=_cancel())
    return S_ADMIN_SEARCH


async def on_admin_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid     = update.effective_user.id
    results = user_search(update.message.text.strip())
    if not results:
        await update.message.reply_text("Никого не нашёл.", reply_markup=_main(uid))
        return ConversationHandler.END
    rows = []
    for u in results[:10]:
        bm  = " ⛔" if u["is_banned"] else ""
        nm  = f"@{u['username']}" if u["username"] else str(u["id"])
        rows.append([B(f"{nm}{bm}", callback_data=f"adm_user_{u['id']}")])
    rows.append([B("‹ Назад", callback_data="pnl_users")])
    await update.message.reply_text(
        f"🔍 Найдено: {len(results)}", reply_markup=K(rows)
    )
    return ConversationHandler.END


# ── редактирование bio (за пользователя) ─────────────────────

async def admin_edit_bio_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q      = update.callback_query
    await q.answer()
    if not _guard(q.from_user.id): return ConversationHandler.END
    target = int(q.data[8:])   # strip "adm_bio_"
    ctx.user_data["adm_bio_target"] = target
    await q.edit_message_text(
        f"Напиши новое bio для пользователя `{target}`:",
        reply_markup=_cancel(), parse_mode=MD,
    )
    return S_ADMIN_EDIT_BIO


async def on_admin_edit_bio(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid    = update.effective_user.id
    target = ctx.user_data.pop("adm_bio_target", None)
    if target:
        user_set(target, bio=update.message.text.strip())
    await update.message.reply_text("✅ Bio обновлено.", reply_markup=_main(uid))
    return ConversationHandler.END


async def admin_del_avatar(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q      = update.callback_query
    await q.answer()
    if not _guard(q.from_user.id): return ConversationHandler.END
    target = int(q.data[14:])  # strip "adm_delavatar_"
    user_set(target, avatar_fid="")
    await q.edit_message_text("🗑 Аватар удалён.", reply_markup=_back(f"adm_user_{target}"))
    return ConversationHandler.END


# ── рассылка ─────────────────────────────────────────────────

async def admin_broadcast_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    if not _guard(q.from_user.id): return ConversationHandler.END
    await q.edit_message_text(
        "📣 **Рассылка**\n\n"
        "Напиши сообщение — оно будет отправлено всем пользователям бота.\n\n"
        "⚠️ Используй с умом — частые рассылки раздражают.",
        reply_markup=_cancel(), parse_mode=MD,
    )
    return S_ADMIN_BROADCAST


async def on_admin_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid   = update.effective_user.id
    if not _guard(uid): return ConversationHandler.END
    text  = update.message.text.strip()
    total = user_count()
    sent  = 0
    failed = 0

    await update.message.reply_text(
        f"📣 Начинаю рассылку для {total} пользователей...",
    )

    offset = 0
    while True:
        batch = user_list(limit=50, offset=offset)
        if not batch:
            break
        for u in batch:
            if u["is_banned"]:
                continue
            try:
                await ctx.bot.send_message(u["id"], text)
                sent += 1
            except Exception:
                failed += 1
        offset += 50

    await update.message.reply_text(
        f"✅ Рассылка завершена.\n\n"
        f"Отправлено: {sent}\n"
        f"Ошибок: {failed}",
        reply_markup=_main(uid),
    )
    return ConversationHandler.END
