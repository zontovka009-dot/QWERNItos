"""
config/profile.py — Профиль пользователя.
Аватар, bio, имя, навыки, мои заявки.
"""

import logging
from telegram import Update, InlineKeyboardButton as B, InlineKeyboardMarkup as K
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from config.db import (
    user_get, user_set, user_name, is_pro,
    app_user_all, proj_get, s_icon, proj_count,
)
from config.states import S_AVATAR, S_BIO, S_DNAME, S_SKILLS

log = logging.getLogger("kpp.profile")
MD  = ParseMode.MARKDOWN


def _main(uid):
    from config.start import kb_main
    return kb_main(uid)

def _back(cb): return K([[B("‹ Назад", callback_data=cb)]])
def _cancel():  return K([[B("✕ Отмена", callback_data="cancel")]])


# ── показ профиля ─────────────────────────────────────────────

async def show_profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u   = user_get(uid)
    if not u:
        await q.edit_message_text("Профиль не найден.")
        return ConversationHandler.END

    pro       = is_pro(uid)
    badge     = "⭐ Pro" if pro else "Бесплатный"
    until     = f" (до {u['pro_until'][:10]})" if pro and u.get("pro_until") else ""
    bio       = u["bio"]    or "_не указано_"
    skills    = u["skills"] or "_не указаны_"
    has_av    = bool(u.get("avatar_fid"))

    text = (
        f"👤 **{user_name(u)}**\n\n"
        f"Ник: @{u['username'] or '—'}\n"
        f"ID: `{uid}`\n"
        f"Тариф: {badge}{until}\n"
        f"Проектов: {proj_count(uid)}\n"
        f"В боте с: {u['created_at'][:10]}\n\n"
        f"О себе: {bio}\n\n"
        f"Навыки: {skills}"
    )
    rows = [
        [B("✏️ Имя",            callback_data="edit_name"),
         B("📝 Bio",            callback_data="edit_bio")],
        [B("🔧 Навыки",         callback_data="edit_skills")],
        [B("🖼 Сменить аватар", callback_data="edit_avatar")],
        [B("📋 Мои заявки",     callback_data="my_apps")],
    ]
    if has_av:
        rows[2].append(B("🗑", callback_data="del_avatar"))
    rows.append([B("‹ Назад", callback_data="cancel")])

    if has_av:
        try:
            await q.message.delete()
            await q.message.chat.send_photo(
                photo=u["avatar_fid"], caption=text,
                reply_markup=K(rows), parse_mode=MD,
            )
            return ConversationHandler.END
        except Exception as e:
            log.warning(f"profile photo: {e}")

    await q.edit_message_text(text, reply_markup=K(rows), parse_mode=MD)
    return ConversationHandler.END


# ── мои заявки ────────────────────────────────────────────────

async def show_my_apps(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    apps = app_user_all(uid)

    if not apps:
        await q.edit_message_text(
            "📋 Заявок пока нет.\n\nНайди проект в **Витрине** и подай заявку!",
            reply_markup=K([[B("🔍 Витрина", callback_data="catalog")],
                            [B("‹ Назад",   callback_data="profile")]]),
            parse_mode=MD,
        )
        return ConversationHandler.END

    text = "📋 **Мои заявки**\n\n"
    for a in apps:
        p  = proj_get(a["project_id"])
        pn = p["title"] if p else a["project_id"]
        text += f"{s_icon(a['status'])} `{a['id']}` — {pn} — {a['created_at'][:10]}\n"

    await q.edit_message_text(text, reply_markup=_back("profile"), parse_mode=MD)
    return ConversationHandler.END


# ── имя ───────────────────────────────────────────────────────

async def edit_name_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    await q.edit_message_text("✏️ Напиши имя как хочешь отображаться:", reply_markup=_cancel())
    return S_DNAME

async def on_dname(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid  = update.effective_user.id
    text = update.message.text.strip()
    if len(text) > 50:
        await update.message.reply_text(f"Слишком длинно ({len(text)}/50):", reply_markup=_cancel())
        return S_DNAME
    user_set(uid, display_name=text)
    await update.message.reply_text("✅ Имя обновлено!", reply_markup=_main(uid))
    return ConversationHandler.END


# ── bio ───────────────────────────────────────────────────────

async def edit_bio_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    u = user_get(q.from_user.id)
    await q.edit_message_text(
        f"📝 Текущее bio:\n_{u['bio'] or 'не указано'}_\n\nНапиши новое (до 300 символов):",
        reply_markup=_cancel(), parse_mode=MD,
    )
    return S_BIO

async def on_bio(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid  = update.effective_user.id
    text = update.message.text.strip()
    if len(text) > 300:
        await update.message.reply_text(f"Слишком длинно ({len(text)}/300):", reply_markup=_cancel())
        return S_BIO
    user_set(uid, bio=text)
    await update.message.reply_text("✅ Bio обновлено!", reply_markup=_main(uid))
    return ConversationHandler.END


# ── навыки ────────────────────────────────────────────────────

async def edit_skills_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    u = user_get(q.from_user.id)
    await q.edit_message_text(
        f"🔧 Текущие навыки:\n_{u['skills'] or 'не указаны'}_\n\n"
        "Перечисли через запятую (например: модерация, монтаж, Python):",
        reply_markup=_cancel(), parse_mode=MD,
    )
    return S_SKILLS

async def on_skills(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid  = update.effective_user.id
    text = update.message.text.strip()
    if len(text) > 200:
        await update.message.reply_text(f"Слишком длинно ({len(text)}/200):", reply_markup=_cancel())
        return S_SKILLS
    user_set(uid, skills=text)
    await update.message.reply_text("✅ Навыки обновлены!", reply_markup=_main(uid))
    return ConversationHandler.END


# ── аватар ────────────────────────────────────────────────────

async def edit_avatar_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    await q.edit_message_text(
        "🖼 Отправь фото для аватара.\n\n_Через 📎 → «Фото», не «Файл»._",
        reply_markup=_cancel(), parse_mode=MD,
    )
    return S_AVATAR

async def on_avatar(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid   = update.effective_user.id
    photo = update.message.photo
    if not photo:
        await update.message.reply_text("📸 Нужно фото — через 📎 → «Фото»:", reply_markup=_cancel())
        return S_AVATAR
    user_set(uid, avatar_fid=photo[-1].file_id)
    await update.message.reply_text("✅ Аватар обновлён!", reply_markup=_main(uid))
    return ConversationHandler.END

async def on_avatar_wrong(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📸 Нужно именно фото — через 📎 → «Фото», не «Файл»:", reply_markup=_cancel()
    )
    return S_AVATAR

async def del_avatar(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    user_set(q.from_user.id, avatar_fid="")
    await q.edit_message_text("🗑 Аватар удалён.", reply_markup=_back("profile"))
    return ConversationHandler.END
