"""
config/keyboards.py — ReplyKeyboard (нижняя панель) + удаление старых сообщений.

Логика:
  - ReplyKeyboardMarkup всегда внизу — базовые действия
  - InlineKeyboard — динамические кнопки над сообщением
  - delete_prev() — удаляет предыдущее сообщение бота перед показом нового
  - safe_edit()   — редактирует сообщение или удаляет+отправляет новое если медиа
"""

import logging
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton as B,
    InlineKeyboardMarkup as K,
)
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

log = logging.getLogger("kpp.keyboards")
MD  = ParseMode.MARKDOWN

# ── ключ для хранения message_id последнего сообщения бота ───
_LAST_MSG = "last_bot_msg_id"


# ══════════════════════════════════════════════════════════════
#  REPLY KEYBOARD — нижняя панель
# ══════════════════════════════════════════════════════════════

def reply_main(is_owner: bool = False) -> ReplyKeyboardMarkup:
    """Основная нижняя панель — всегда видна."""
    rows = [
        [KeyboardButton("📋 Создать анкету"), KeyboardButton("🔍 Витрина")],
        [KeyboardButton("📁 Проекты"),        KeyboardButton("👤 Профиль")],
        [KeyboardButton("💬 Поддержка"),       KeyboardButton("⭐ Pro")],
    ]
    if is_owner:
        rows.append([KeyboardButton("⚙️ Панель управления")])
    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        is_persistent=True,
    )


def reply_cancel() -> ReplyKeyboardMarkup:
    """Нижняя панель с отменой — показывается во время заполнения форм."""
    return ReplyKeyboardMarkup(
        [[KeyboardButton("✕ Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ══════════════════════════════════════════════════════════════
#  УДАЛЕНИЕ ПРЕДЫДУЩЕГО СООБЩЕНИЯ
# ══════════════════════════════════════════════════════════════

async def delete_prev(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Удаляет предыдущее сообщение бота.
    Вызывай перед отправкой нового чтобы не копились старые.
    """
    chat_id = update.effective_chat.id
    msg_id  = ctx.user_data.get(_LAST_MSG)
    if msg_id:
        try:
            await ctx.bot.delete_message(chat_id, msg_id)
        except Exception:
            pass  # уже удалено или недоступно
        ctx.user_data.pop(_LAST_MSG, None)


def save_msg_id(ctx: ContextTypes.DEFAULT_TYPE, msg_id: int) -> None:
    """Сохрани message_id после отправки чтобы потом удалить."""
    ctx.user_data[_LAST_MSG] = msg_id


# ══════════════════════════════════════════════════════════════
#  SAFE EDIT — умное редактирование/пересылка
# ══════════════════════════════════════════════════════════════

async def safe_edit(
    query,
    ctx: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup=None,
    parse_mode: str = MD,
) -> None:
    """
    Редактирует сообщение если возможно.
    Если сообщение содержит медиа — удаляет и отправляет новое.
    При любой ошибке редактирования — отправляет новое.
    """
    try:
        await query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    except Exception:
        # сообщение с фото — нельзя edit_message_text
        try:
            await query.message.delete()
        except Exception:
            pass
        msg = await query.message.chat.send_message(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
        save_msg_id(ctx, msg.message_id)


async def safe_send(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup=None,
    parse_mode: str = MD,
    delete_previous: bool = True,
) -> None:
    """
    Отправляет новое сообщение, предварительно удалив предыдущее.
    Используй вместо reply_text там где важна чистота чата.
    """
    if delete_previous:
        await delete_prev(update, ctx)
    msg = await update.effective_chat.send_message(
        text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
    )
    save_msg_id(ctx, msg.message_id)


# ══════════════════════════════════════════════════════════════
#  МАППИНГ REPLY-КНОПОК → callback_data
#  Используется в main.py для обработки текстовых кнопок внизу
# ══════════════════════════════════════════════════════════════

REPLY_BUTTON_MAP = {
    "📋 Создать анкету":    "create",
    "🔍 Витрина":           "catalog",
    "📁 Проекты":           "projects",
    "👤 Профиль":           "profile",
    "💬 Поддержка":         "support",
    "⭐ Pro":               "pro_menu",
    "⚙️ Панель управления": "panel",
    "✕ Отмена":            "cancel",
}


async def handle_reply_button(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> str | None:
    """
    Определяет нажатую Reply-кнопку и возвращает соответствующий callback_data.
    Возвращает None если текст не является кнопкой.
    """
    text = update.message.text if update.message else ""
    return REPLY_BUTTON_MAP.get(text)
