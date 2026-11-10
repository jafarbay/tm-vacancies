"""Bot tables (users, favorites) in the same SQLite DB as the site."""
import json
from datetime import date, datetime, timedelta

from app import db
from app.classify import DIRECTIONS, OTHER

DIRS = [*DIRECTIONS, OTHER]  # index is used in callback data


def _ago(hours: int) -> str:
    """Timestamp in the same ISO format as db.now(), for string comparison."""
    return (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")

SCHEMA = """
CREATE TABLE IF NOT EXISTS bot_users(
  id INTEGER PRIMARY KEY,
  username TEXT,
  name TEXT,
  cities TEXT NOT NULL DEFAULT '[]',
  dirs TEXT NOT NULL DEFAULT '[]',
  keywords TEXT NOT NULL DEFAULT '[]',
  mode TEXT NOT NULL DEFAULT 'instant',      -- instant | digest | off
  last_vacancy_id INTEGER NOT NULL DEFAULT 0, -- notifications are sent for ids above this
  last_digest TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,       -- 0 = user blocked the bot
  is_banned INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  seen_at TEXT
);
CREATE TABLE IF NOT EXISTS bot_favorites(
  user_id INTEGER NOT NULL,
  vacancy_id INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(user_id, vacancy_id)
);
"""


def init() -> None:
    db.init()
    with db.session() as conn:
        conn.executescript(SCHEMA)


def _user(row) -> dict | None:
    if not row:
        return None
    u = dict(row)
    for k in ("cities", "dirs", "keywords"):
        u[k] = json.loads(u[k])
    return u


def touch_user(uid: int, username: str | None, name: str) -> dict:
    with db.session() as conn:
        max_id = conn.execute("SELECT COALESCE(MAX(id),0) FROM vacancies").fetchone()[0]
        conn.execute(
            "INSERT INTO bot_users(id, username, name, last_vacancy_id, created_at, seen_at) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET username=excluded.username, name=excluded.name, "
            "seen_at=excluded.seen_at, is_active=1",
            (uid, username, name, max_id, db.now(), db.now()))
        return _user(conn.execute("SELECT * FROM bot_users WHERE id=?", (uid,)).fetchone())


def get_user(uid: int) -> dict | None:
    with db.session() as conn:
        return _user(conn.execute("SELECT * FROM bot_users WHERE id=?", (uid,)).fetchone())


def update_user(uid: int, **fields) -> None:
    for k in ("cities", "dirs", "keywords"):
        if k in fields:
            fields[k] = json.dumps(fields[k], ensure_ascii=False)
    sets = ", ".join(f"{k}=?" for k in fields)
    with db.session() as conn:
        conn.execute(f"UPDATE bot_users SET {sets} WHERE id=?", (*fields.values(), uid))


def cities() -> list[str]:
    with db.session() as conn:
        return [r[0] for r in conn.execute(
            "SELECT city FROM vacancies WHERE city<>'' GROUP BY city ORDER BY COUNT(*) DESC, city")]


# ---------- vacancy queries ----------

LIST_COLS = "id, title, date, city, company, direction, salary, url"


def _filter_sql(u: dict) -> tuple[str, list]:
    cl, args = [], []
    if u["cities"]:
        cl.append(f"city IN ({','.join('?' * len(u['cities']))})")
        args += u["cities"]
    if u["dirs"]:
        cl.append(f"direction IN ({','.join('?' * len(u['dirs']))})")
        args += u["dirs"]
    if u["keywords"]:
        parts = [db.word_clause(k) for k in u["keywords"]]
        cl.append("(" + " OR ".join(sql for sql, _ in parts) + ")")
        args += [a for _, extra in parts for a in extra]
    return " AND ".join(cl) or "1=1", args


def browse(u: dict, page: int, per_page: int = 6, query: str = "") -> tuple[list, int]:
    where, args = _filter_sql(u)
    for w in query.lower().split()[:6]:
        sql, extra = db.word_clause(w)
        where += f" AND {sql}"
        args += extra
    with db.session() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM vacancies WHERE {where}", args).fetchone()[0]
        rows = conn.execute(f"SELECT {LIST_COLS} FROM vacancies WHERE {where} ORDER BY date DESC, id DESC "
                            f"LIMIT ? OFFSET ?", [*args, per_page, page * per_page]).fetchall()
    return [dict(r) for r in rows], total


def new_for(u: dict, upto: int, limit: int, max_age_days: int) -> list[dict]:
    """Fresh vacancies in (watermark, upto] matching the user's filters."""
    where, args = _filter_sql(u)
    since = (date.today() - timedelta(days=max_age_days)).isoformat()
    with db.session() as conn:
        rows = conn.execute(
            f"SELECT id FROM vacancies WHERE id>? AND id<=? AND date>=? AND {where} ORDER BY id LIMIT ?",
            [u["last_vacancy_id"], upto, since, *args, limit]).fetchall()
    return [vacancy(r[0]) for r in rows]


def ready_max_id() -> int:
    """Highest id below which every vacancy has its full text (or waited 1h) — safe notification watermark."""
    with db.session() as conn:
        pending = conn.execute("SELECT MIN(id) FROM vacancies WHERE has_detail=0 AND first_seen >= ?",
                               (_ago(1),)).fetchone()[0]
        top = conn.execute("SELECT COALESCE(MAX(id),0) FROM vacancies").fetchone()[0]
    return min(top, pending - 1) if pending else top


def vacancy(vid: int) -> dict | None:
    with db.session() as conn:
        return db.get(conn, vid)


# ---------- favorites ----------

def toggle_favorite(uid: int, vid: int) -> bool:
    with db.session() as conn:
        if conn.execute("DELETE FROM bot_favorites WHERE user_id=? AND vacancy_id=?", (uid, vid)).rowcount:
            return False
        conn.execute("INSERT INTO bot_favorites VALUES(?,?,?)", (uid, vid, db.now()))
        return True


def is_favorite(uid: int, vid: int) -> bool:
    with db.session() as conn:
        return bool(conn.execute("SELECT 1 FROM bot_favorites WHERE user_id=? AND vacancy_id=?",
                                 (uid, vid)).fetchone())


def favorites(uid: int, page: int, per_page: int = 6) -> tuple[list, int]:
    with db.session() as conn:
        total = conn.execute("SELECT COUNT(*) FROM bot_favorites WHERE user_id=?", (uid,)).fetchone()[0]
        rows = conn.execute(
            f"SELECT {', '.join('v.' + c.strip() for c in LIST_COLS.split(','))} FROM bot_favorites f "
            "JOIN vacancies v ON v.id=f.vacancy_id WHERE f.user_id=? ORDER BY f.created_at DESC LIMIT ? OFFSET ?",
            (uid, per_page, page * per_page)).fetchall()
    return [dict(r) for r in rows], total


# ---------- notifier / admin ----------

def users_for(mode: str) -> list[dict]:
    with db.session() as conn:
        return [_user(r) for r in conn.execute(
            "SELECT * FROM bot_users WHERE mode=? AND is_active=1 AND is_banned=0", (mode,))]


def all_recipients() -> list[int]:
    with db.session() as conn:
        return [r[0] for r in conn.execute("SELECT id FROM bot_users WHERE is_active=1 AND is_banned=0")]


def list_users(page: int, per_page: int = 8) -> tuple[list, int]:
    with db.session() as conn:
        total = conn.execute("SELECT COUNT(*) FROM bot_users").fetchone()[0]
        rows = conn.execute("SELECT * FROM bot_users ORDER BY created_at DESC LIMIT ? OFFSET ?",
                            (per_page, page * per_page)).fetchall()
    return [_user(r) for r in rows], total


def stats() -> dict:
    with db.session() as conn:
        u = conn.execute(
            "SELECT COUNT(*) total, SUM(is_active=1 AND is_banned=0) active, SUM(is_active=0) blocked, "
            "SUM(is_banned) banned, SUM(mode='instant') instant, SUM(mode='digest') digest, SUM(mode='off') off, "
            "SUM(created_at >= ?) new_day FROM bot_users", (_ago(24),)).fetchone()
        v = conn.execute(
            "SELECT COUNT(*) total, SUM(has_detail=0) pending, MAX(date) last_date, "
            "SUM(first_seen >= ?) new_day FROM vacancies", (_ago(24),)).fetchone()
        fav = conn.execute("SELECT COUNT(*) FROM bot_favorites").fetchone()[0]
        return {"u": {k: u[k] or 0 for k in u.keys()}, "v": dict(v), "fav": fav,
                "last_scrape": db.get_meta(conn, "last_scrape"), "paused": get_flag(conn, "notify_paused")}


def get_flag(conn, key: str) -> bool:
    return db.get_meta(conn, key) == "1"


def flag(key: str) -> bool:
    with db.session() as conn:
        return get_flag(conn, key)


def set_flag(key: str, value: bool) -> None:
    with db.session() as conn:
        db.set_meta(conn, key, "1" if value else "0")
