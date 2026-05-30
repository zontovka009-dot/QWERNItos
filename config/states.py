"""
config/states.py — все состояния ConversationHandler в одном месте.
Импортируется из всех модулей чтобы не было расхождений.
"""

(
    # онбординг
    S_ONBOARD,

    # профиль
    S_AVATAR, S_BIO, S_DNAME, S_SKILLS,

    # создание проекта
    S_PT, S_PD, S_PM, S_PL, S_PCAT, S_PTAGS, S_PTPL,

    # заявки
    S_APP_FILL, S_APP_EDIT,

    # решения по заявкам
    S_APPROVE_MSG, S_REJECT_REASON,

    # поддержка
    S_SUPPORT_WRITE, S_SUPPORT_REPLY,

    # администраторы проекта
    S_PADMIN_ADD,

    # отзывы
    S_REVIEW_TEXT,

    # панель владельца
    S_ADMIN_BAN_ID, S_ADMIN_BAN_REASON,
    S_ADMIN_UNBAN, S_ADMIN_ADD_OWNER,
    S_ADMIN_SEARCH, S_ADMIN_EDIT_BIO,
    S_ADMIN_BROADCAST,
) = range(27)
