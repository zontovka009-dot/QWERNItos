"""
config/db.py — Вся работа с базой данных.
Создаёт database/data.db при первом запуске.
Все остальные модули импортируют функции отсюда.
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# ── загрузка конфига ─────────────────────────────────────────
_CFG_PATH = Path(__file__).parent.parent / "data" / "config.json"
with open(_CFG_PATH, encoding="utf-8") as _f:
    _CFG = json.load(_f)

DB_PATH      = Path(__file__).parent.parent / _CFG["db_path"]
BOT_USERNAME = _CFG.get("bot_username", "kppunkt_bot")
OWNER_IDS    = _CFG.get("owner_ids", [])
TOKEN        = _CFG["token"]

# тарифы подписки (звёзды)
PLANS = {
    "week":    {"stars": 50,  "days": 7,  "label": "1 неделя — 50 ⭐"},
    "two_weeks": {"stars": 120, "days": 14, "label": "2 недели — 120 ⭐"},
    "month":   {"stars": 300, "days": 30, "label": "1 месяц — 300 ⭐"},
}

FREE_PROJ_LIMIT = 2   # проектов на бесплатном тарифе
PRO_PROJ_LIMIT  = 999


# ══════════════════════════════════════════════════════════════
#  ПОДКЛЮЧЕНИЕ
# ══════════════════════════════════════════════════════════════

def conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    return c


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def uid8() -> str:
    return str(uuid.uuid4())[:8].upper()


def uid10() -> str:
    return str(uuid.uuid4())[:10]


# ══════════════════════════════════════════════════════════════
#  ИНИЦИАЛИЗАЦИЯ СХЕМЫ
# ══════════════════════════════════════════════════════════════

def init_db() -> None:
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY,
            username      TEXT    DEFAULT '',
            first_name    TEXT    DEFAULT '',
            display_name  TEXT    DEFAULT '',
            bio           TEXT    DEFAULT '',
            avatar_fid    TEXT    DEFAULT '',
            skills        TEXT    DEFAULT '',
            created_at    TEXT    NOT NULL,
            last_seen     TEXT    NOT NULL,
            is_banned     INTEGER DEFAULT 0,
            ban_reason    TEXT    DEFAULT '',
            warn_count    INTEGER DEFAULT 0,
            ref_code      TEXT    DEFAULT '',
            referred_by   INTEGER DEFAULT NULL,
            ref_count     INTEGER DEFAULT 0,
            pro_until     TEXT    DEFAULT NULL,
            onboarding    INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS projects (
            id            TEXT    PRIMARY KEY,
            owner_id      INTEGER NOT NULL,
            title         TEXT    NOT NULL,
            description   TEXT    DEFAULT '',
            media_fid     TEXT    DEFAULT '',
            chat_link     TEXT    DEFAULT '',
            ptype         TEXT    NOT NULL,
            category      TEXT    DEFAULT '',
            tags          TEXT    DEFAULT '',
            is_open       INTEGER DEFAULT 1,
            is_verified   INTEGER DEFAULT 0,
            is_featured   INTEGER DEFAULT 0,
            featured_until TEXT   DEFAULT NULL,
            template      TEXT    DEFAULT '',
            apps_total    INTEGER DEFAULT 0,
            apps_approved INTEGER DEFAULT 0,
            views         INTEGER DEFAULT 0,
            created_at    TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS project_admins (
            project_id TEXT    NOT NULL,
            user_id    INTEGER NOT NULL,
            added_at   TEXT    NOT NULL,
            PRIMARY KEY (project_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS applications (
            id          TEXT    PRIMARY KEY,
            project_id  TEXT    NOT NULL,
            user_id     INTEGER NOT NULL,
            username    TEXT    DEFAULT '',
            answers     TEXT    NOT NULL,
            status      TEXT    DEFAULT 'pending',
            comment     TEXT    DEFAULT '',
            decided_by  INTEGER DEFAULT NULL,
            created_at  TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  TEXT    NOT NULL,
            user_id     INTEGER NOT NULL,
            rating      INTEGER NOT NULL,
            text        TEXT    DEFAULT '',
            created_at  TEXT    NOT NULL,
            UNIQUE(project_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            plan        TEXT    NOT NULL,
            stars_paid  INTEGER NOT NULL,
            started_at  TEXT    NOT NULL,
            expires_at  TEXT    NOT NULL,
            payment_id  TEXT    DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS tickets (
            id          TEXT    PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            username    TEXT    DEFAULT '',
            text        TEXT    NOT NULL,
            status      TEXT    DEFAULT 'open',
            created_at  TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS global_ban (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT    DEFAULT '',
            reason      TEXT    DEFAULT '',
            banned_by   INTEGER NOT NULL,
            banned_at   TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS bot_owners (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT    DEFAULT '',
            added_at    TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            type        TEXT    NOT NULL,
            project_id  TEXT    DEFAULT NULL,
            created_at  TEXT    NOT NULL,
            sent        INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS project_followers (
            project_id  TEXT    NOT NULL,
            user_id     INTEGER NOT NULL,
            followed_at TEXT    NOT NULL,
            PRIMARY KEY (project_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS stats (
            key         TEXT    PRIMARY KEY,
            value       INTEGER DEFAULT 0
        );
        """)

        for uid in OWNER_IDS:
            c.execute("INSERT OR IGNORE INTO bot_owners VALUES(?,?,?)", (uid, "", now()))
        for k in ("users","projects","apps","approved","stars_earned"):
            c.execute("INSERT OR IGNORE INTO stats VALUES(?,0)", (k,))


# ══════════════════════════════════════════════════════════════
#  ПОЛЬЗОВАТЕЛИ
# ══════════════════════════════════════════════════════════════

def user_touch(uid: int, username: str, first_name: str) -> bool:
    """Возвращает True если пользователь новый."""
    with conn() as c:
        exists = c.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone()
        if exists:
            c.execute(
                "UPDATE users SET username=?,first_name=?,last_seen=? WHERE id=?",
                (username or "", first_name or "", now(), uid),
            )
            return False
        else:
            dn = username or first_name or str(uid)
            rc = uid8()
            c.execute(
                "INSERT INTO users(id,username,first_name,display_name,created_at,last_seen,ref_code)"
                " VALUES(?,?,?,?,?,?,?)",
                (uid, username or "", first_name or "", dn, now(), now(), rc),
            )
            c.execute("UPDATE stats SET value=value+1 WHERE key='users'")
            return True


def user_get(uid: int) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return dict(r) if r else None


def user_set(uid: int, **kw) -> None:
    if not kw:
        return
    with conn() as c:
        q = ", ".join(f"{k}=?" for k in kw)
        c.execute(f"UPDATE users SET {q} WHERE id=?", (*kw.values(), uid))


def user_list(limit=20, offset=0) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()]


def user_count() -> int:
    with conn() as c:
        return c.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def user_search(q: str) -> list[dict]:
    with conn() as c:
        try:
            rows = c.execute("SELECT * FROM users WHERE id=?", (int(q),)).fetchall()
        except ValueError:
            p = f"%{q}%"
            rows = c.execute(
                "SELECT * FROM users WHERE username LIKE ? OR display_name LIKE ?", (p, p)
            ).fetchall()
        return [dict(r) for r in rows]


def user_name(u: dict) -> str:
    return u.get("display_name") or u.get("username") or u.get("first_name") or str(u.get("id", "?"))


# ── реферальная система ──────────────────────────────────────

def ref_apply(new_uid: int, ref_code: str) -> bool:
    """Применяет реф-код при регистрации. Возвращает True если успешно."""
    with conn() as c:
        r = c.execute("SELECT id FROM users WHERE ref_code=?", (ref_code,)).fetchone()
        if not r or r["id"] == new_uid:
            return False
        referrer_id = r["id"]
        c.execute("UPDATE users SET referred_by=? WHERE id=?", (referrer_id, new_uid))
        c.execute("UPDATE users SET ref_count=ref_count+1 WHERE id=?", (referrer_id,))
        return True


def ref_bonus_check(uid: int) -> int:
    """Возвращает кол-во рефералов пользователя."""
    with conn() as c:
        r = c.execute("SELECT ref_count FROM users WHERE id=?", (uid,)).fetchone()
        return r["ref_count"] if r else 0


# ── про-тариф ────────────────────────────────────────────────

def is_pro(uid: int) -> bool:
    u = user_get(uid)
    if not u or not u.get("pro_until"):
        return owner_check(uid)
    try:
        return datetime.strptime(u["pro_until"], "%Y-%m-%d %H:%M:%S") > datetime.now()
    except Exception:
        return False


def activate_pro(uid: int, days: int) -> str:
    """Активирует Pro. Если уже активен — продлевает."""
    u = user_get(uid)
    base = datetime.now()
    if u and u.get("pro_until"):
        try:
            existing = datetime.strptime(u["pro_until"], "%Y-%m-%d %H:%M:%S")
            if existing > base:
                base = existing
        except Exception:
            pass
    expires = (base + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    user_set(uid, pro_until=expires)
    return expires


def sub_create(uid: int, plan: str, stars: int, payment_id: str = "") -> None:
    expires = activate_pro(uid, PLANS[plan]["days"])
    with conn() as c:
        c.execute(
            "INSERT INTO subscriptions(user_id,plan,stars_paid,started_at,expires_at,payment_id)"
            " VALUES(?,?,?,?,?,?)",
            (uid, plan, stars, now(), expires, payment_id),
        )
        c.execute("UPDATE stats SET value=value+? WHERE key='stars_earned'", (stars,))


def proj_limit(uid: int) -> int:
    return PRO_PROJ_LIMIT if is_pro(uid) else FREE_PROJ_LIMIT


# ══════════════════════════════════════════════════════════════
#  БАНЫ И ВАРНЫ
# ══════════════════════════════════════════════════════════════

def ban_check(uid: int) -> bool:
    with conn() as c:
        return c.execute("SELECT 1 FROM global_ban WHERE user_id=?", (uid,)).fetchone() is not None


def ban_add(uid: int, username: str, reason: str, by: int) -> None:
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO global_ban VALUES(?,?,?,?,?)",
                  (uid, username or "", reason, by, now()))
        c.execute("UPDATE users SET is_banned=1,ban_reason=? WHERE id=?", (reason, uid))


def ban_remove(uid: int) -> None:
    with conn() as c:
        c.execute("DELETE FROM global_ban WHERE user_id=?", (uid,))
        c.execute("UPDATE users SET is_banned=0,ban_reason='' WHERE id=?", (uid,))


def ban_list() -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM global_ban ORDER BY banned_at DESC"
        ).fetchall()]


def warn_add(uid: int) -> int:
    with conn() as c:
        c.execute("UPDATE users SET warn_count=warn_count+1 WHERE id=?", (uid,))
        return c.execute("SELECT warn_count FROM users WHERE id=?", (uid,)).fetchone()["warn_count"]


def warn_reset(uid: int) -> None:
    with conn() as c:
        c.execute("UPDATE users SET warn_count=0 WHERE id=?", (uid,))


# ══════════════════════════════════════════════════════════════
#  ВЛАДЕЛЬЦЫ БОТА
# ══════════════════════════════════════════════════════════════

def owner_check(uid: int) -> bool:
    with conn() as c:
        return c.execute("SELECT 1 FROM bot_owners WHERE user_id=?", (uid,)).fetchone() is not None


def owner_list() -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM bot_owners").fetchall()]


def owner_add(uid: int, username: str = "") -> None:
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO bot_owners VALUES(?,?,?)", (uid, username or "", now()))


def owner_remove(uid: int) -> None:
    with conn() as c:
        c.execute("DELETE FROM bot_owners WHERE user_id=?", (uid,))


# ══════════════════════════════════════════════════════════════
#  ПРОЕКТЫ
# ══════════════════════════════════════════════════════════════

def proj_count(owner_id: int) -> int:
    with conn() as c:
        return c.execute(
            "SELECT COUNT(*) FROM projects WHERE owner_id=?", (owner_id,)
        ).fetchone()[0]


def proj_create(owner_id, title, desc, media, link, ptype, category="", tags="", template="") -> str:
    pid = uid10()
    with conn() as c:
        c.execute(
            "INSERT INTO projects(id,owner_id,title,description,media_fid,chat_link,"
            "ptype,category,tags,template,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (pid, owner_id, title, desc, media or "", link, ptype,
             category, tags, template, now()),
        )
        c.execute("UPDATE stats SET value=value+1 WHERE key='projects'")
    return pid


def proj_get(pid: str) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None


def proj_list(owner_id: int) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM projects WHERE owner_id=? ORDER BY created_at DESC", (owner_id,)
        ).fetchall()]


def proj_catalog(category: str = "", ptype: str = "", limit: int = 20, offset: int = 0) -> list[dict]:
    """Публичная витрина — только открытые проекты."""
    with conn() as c:
        conditions = ["is_open=1"]
        params: list = []
        if category:
            conditions.append("category=?")
            params.append(category)
        if ptype:
            conditions.append("ptype=?")
            params.append(ptype)
        where = " AND ".join(conditions)
        params += [limit, offset]
        return [dict(r) for r in c.execute(
            f"SELECT * FROM projects WHERE {where}"
            " ORDER BY is_featured DESC, apps_total DESC, created_at DESC"
            " LIMIT ? OFFSET ?",
            params,
        ).fetchall()]


def proj_set(pid: str, **kw) -> None:
    if not kw:
        return
    with conn() as c:
        q = ", ".join(f"{k}=?" for k in kw)
        c.execute(f"UPDATE projects SET {q} WHERE id=?", (*kw.values(), pid))


def proj_delete(pid: str) -> None:
    with conn() as c:
        c.execute("DELETE FROM projects WHERE id=?", (pid,))
        c.execute("DELETE FROM project_admins WHERE project_id=?", (pid,))


def proj_inc_views(pid: str) -> None:
    with conn() as c:
        c.execute("UPDATE projects SET views=views+1 WHERE id=?", (pid,))


def padmin_list(pid: str) -> list[int]:
    with conn() as c:
        return [r["user_id"] for r in c.execute(
            "SELECT user_id FROM project_admins WHERE project_id=?", (pid,)
        ).fetchall()]


def padmin_add(pid: str, uid: int) -> None:
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO project_admins VALUES(?,?,?)", (pid, uid, now()))


def padmin_remove(pid: str, uid: int) -> None:
    with conn() as c:
        c.execute("DELETE FROM project_admins WHERE project_id=? AND user_id=?", (pid, uid))


def proj_can_manage(pid: str, uid: int) -> bool:
    p = proj_get(pid)
    return bool(p) and (p["owner_id"] == uid or uid in padmin_list(pid))


# ── отзывы ───────────────────────────────────────────────────

def review_add(pid: str, uid: int, rating: int, text: str) -> bool:
    try:
        with conn() as c:
            c.execute(
                "INSERT INTO reviews(project_id,user_id,rating,text,created_at) VALUES(?,?,?,?,?)",
                (pid, uid, rating, text, now()),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def review_list(pid: str) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM reviews WHERE project_id=? ORDER BY created_at DESC", (pid,)
        ).fetchall()]


def proj_rating(pid: str) -> float:
    with conn() as c:
        r = c.execute(
            "SELECT AVG(rating) as avg FROM reviews WHERE project_id=?", (pid,)
        ).fetchone()
        return round(r["avg"] or 0, 1)


# ── подписчики проекта ───────────────────────────────────────

def follow_project(pid: str, uid: int) -> None:
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO project_followers VALUES(?,?,?)", (pid, uid, now()))


def unfollow_project(pid: str, uid: int) -> None:
    with conn() as c:
        c.execute("DELETE FROM project_followers WHERE project_id=? AND user_id=?", (pid, uid))


def is_following(pid: str, uid: int) -> bool:
    with conn() as c:
        return c.execute(
            "SELECT 1 FROM project_followers WHERE project_id=? AND user_id=?", (pid, uid)
        ).fetchone() is not None


def followers_of(pid: str) -> list[int]:
    with conn() as c:
        return [r["user_id"] for r in c.execute(
            "SELECT user_id FROM project_followers WHERE project_id=?", (pid,)
        ).fetchall()]


# ══════════════════════════════════════════════════════════════
#  ЗАЯВКИ
# ══════════════════════════════════════════════════════════════

def app_create(pid: str, uid: int, username: str, answers: str) -> str:
    aid = uid8()
    with conn() as c:
        c.execute(
            "INSERT INTO applications(id,project_id,user_id,username,answers,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (aid, pid, uid, username or "", answers, now(), now()),
        )
        c.execute("UPDATE projects SET apps_total=apps_total+1 WHERE id=?", (pid,))
        c.execute("UPDATE stats SET value=value+1 WHERE key='apps'")
    return aid


def app_get(aid: str) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM applications WHERE id=?", (aid,)).fetchone()
        return dict(r) if r else None


def app_pending(pid: str) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM applications WHERE project_id=? AND status='pending'"
            " ORDER BY created_at DESC", (pid,)
        ).fetchall()]


def app_all(pid: str) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM applications WHERE project_id=? ORDER BY created_at DESC", (pid,)
        ).fetchall()]


def app_for_user(uid: int, pid: str) -> dict | None:
    with conn() as c:
        r = c.execute(
            "SELECT * FROM applications WHERE user_id=? AND project_id=?"
            " ORDER BY created_at DESC LIMIT 1",
            (uid, pid),
        ).fetchone()
        return dict(r) if r else None


def app_user_all(uid: int) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM applications WHERE user_id=? ORDER BY created_at DESC LIMIT 30",
            (uid,),
        ).fetchall()]


def app_set_status(aid: str, status: str, comment: str = "", by: int | None = None) -> None:
    with conn() as c:
        c.execute(
            "UPDATE applications SET status=?,comment=?,updated_at=?,decided_by=? WHERE id=?",
            (status, comment, now(), by, aid),
        )
        if status == "approved":
            r = c.execute("SELECT project_id FROM applications WHERE id=?", (aid,)).fetchone()
            if r:
                c.execute(
                    "UPDATE projects SET apps_approved=apps_approved+1 WHERE id=?",
                    (r["project_id"],),
                )
                c.execute("UPDATE stats SET value=value+1 WHERE key='approved'")


def app_set_answers(aid: str, answers: str) -> None:
    with conn() as c:
        c.execute(
            "UPDATE applications SET answers=?,updated_at=?,status='pending' WHERE id=?",
            (answers, now(), aid),
        )


# ══════════════════════════════════════════════════════════════
#  ТИКЕТЫ ПОДДЕРЖКИ
# ══════════════════════════════════════════════════════════════

def ticket_create(uid: int, username: str, text: str) -> str:
    tid = uid8()
    with conn() as c:
        c.execute("INSERT INTO tickets VALUES(?,?,?,?,'open',?)",
                  (tid, uid, username or "", text, now()))
    return tid


def ticket_open() -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM tickets WHERE status='open' ORDER BY created_at DESC"
        ).fetchall()]


def ticket_close(tid: str) -> None:
    with conn() as c:
        c.execute("UPDATE tickets SET status='closed' WHERE id=?", (tid,))


# ══════════════════════════════════════════════════════════════
#  УВЕДОМЛЕНИЯ
# ══════════════════════════════════════════════════════════════

def notif_add(uid: int, ntype: str, project_id: str | None = None) -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO notifications(user_id,type,project_id,created_at) VALUES(?,?,?,?)",
            (uid, ntype, project_id, now()),
        )


def notif_pending() -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM notifications WHERE sent=0 ORDER BY created_at"
        ).fetchall()]


def notif_mark_sent(nid: int) -> None:
    with conn() as c:
        c.execute("UPDATE notifications SET sent=1 WHERE id=?", (nid,))


# ══════════════════════════════════════════════════════════════
#  СТАТИСТИКА
# ══════════════════════════════════════════════════════════════

def stats_get() -> dict:
    with conn() as c:
        s = {r["key"]: r["value"] for r in c.execute("SELECT key,value FROM stats").fetchall()}
        s["open_projects"]  = c.execute("SELECT COUNT(*) FROM projects WHERE is_open=1").fetchone()[0]
        s["active_users"]   = c.execute("SELECT COUNT(*) FROM users WHERE is_banned=0").fetchone()[0]
        s["banned_count"]   = c.execute("SELECT COUNT(*) FROM global_ban").fetchone()[0]
        s["pro_users"]      = c.execute(
            "SELECT COUNT(*) FROM users WHERE pro_until > ?", (now(),)
        ).fetchone()[0]
        s["open_tickets"]   = len(ticket_open())
        s["total_reviews"]  = c.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
        return s


# ══════════════════════════════════════════════════════════════
#  ВСПОМОГАТЕЛЬНЫЕ
# ══════════════════════════════════════════════════════════════

def deeplink(pid: str) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=kpp_{pid}"


def reflink(ref_code: str) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=ref_{ref_code}"


def s_icon(s: str) -> str:
    return {"pending": "⏳", "approved": "✅", "rejected": "❌", "cancelled": "🚫"}.get(s, "❓")


def ptype_ru(pt: str) -> str:
    return "Участники" if pt == "members" else "Модераторы"


def default_template(ptype: str) -> str:
    if ptype == "mods":
        return (
            "1. Никнейм:\n"
            "2. Возраст:\n"
            "3. Опыт модерации:\n"
            "4. Почему хочешь стать модератором?\n"
            "5. Сколько времени готов уделять в неделю?"
        )
    return ""


CATEGORIES = [
    ("🎮 Игры",       "games"),
    ("📺 Контент",    "content"),
    ("💬 Комьюнити",  "community"),
    ("🎨 Творчество", "creative"),
    ("💼 Работа",     "work"),
    ("🎵 Музыка",     "music"),
    ("📚 Учёба",      "education"),
    ("🔧 Технологии", "tech"),
    ("🌐 Другое",     "other"),
]

CATEGORY_MAP = {k: v for v, k in CATEGORIES}  # code -> label
