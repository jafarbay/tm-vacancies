"""SQLite storage. WAL mode lets the scraper write while the site reads."""
import json
import re
import sqlite3
from contextlib import contextmanager
from functools import lru_cache
from datetime import date, datetime, timedelta

from .classify import classify, detect_lang, extract_salary
from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS vacancies(
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  date TEXT,
  city TEXT,
  company TEXT,
  direction TEXT,
  lang TEXT,
  summary TEXT,
  body TEXT,
  salary TEXT,
  search TEXT,
  contacts TEXT,
  images TEXT,
  posted_at TEXT,
  has_detail INTEGER NOT NULL DEFAULT 0,
  first_seen TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_vac_date ON vacancies(date DESC, id DESC);
CREATE INDEX IF NOT EXISTS ix_vac_city ON vacancies(city);
CREATE INDEX IF NOT EXISTS ix_vac_dir ON vacancies(direction);
CREATE INDEX IF NOT EXISTS ix_vac_company ON vacancies(company);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""

PERIODS = {"1": 1, "3": 3, "7": 7, "30": 30, "60": 60}


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def init() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with session() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(vacancies)")}
        for col in ("contacts", "images", "posted_at"):  # migration for DBs created before these columns
            if col not in cols:
                conn.execute(f"ALTER TABLE vacancies ADD COLUMN {col} TEXT")


@lru_cache(maxsize=256)
def _rx(pattern: str) -> re.Pattern:
    return re.compile(pattern)


def _regexp(pattern: str, value: str | None) -> bool:
    return value is not None and _rx(pattern).search(value) is not None


def word_clause(word: str) -> tuple[str, list]:
    """SQL condition for one search word.
    Short words (it, hr, 1с) are matched as whole words in the title or as a direction name only:
    in body text "it" is an English pronoun and a substring of "elite", "with"...
    Longer words match anywhere in title/company/body, so "бухгалтер" also finds "бухгалтера"."""
    word = word.lower()
    if len(word) <= 3:
        return "(title REGEXP ? OR lower(direction)=?)", [r"(?i)(?<!\w)" + re.escape(word) + r"(?!\w)", word]
    return "search LIKE ? ESCAPE '\\'", ["%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"]


@contextmanager
def session():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.create_function("REGEXP", 2, _regexp, deterministic=True)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _derived(title: str, company: str, city: str, text: str) -> dict:
    return {
        "direction": classify(title, text),
        "lang": detect_lang(title),
        "salary": extract_salary(text),
        "search": " ".join(p for p in (title, company, city, text) if p).lower(),
    }


# ---------- writes (scraper) ----------

def upsert_listing(conn, v: dict) -> bool:
    """Insert or refresh listing fields. Returns True if the vacancy is new."""
    row = conn.execute("SELECT body FROM vacancies WHERE id=?", (v["id"],)).fetchone()
    text = (row["body"] if row else None) or v["summary"]
    rec = {**v, **_derived(v["title"], v["company"], v["city"], text), "ts": now()}
    if row:
        conn.execute(
            "UPDATE vacancies SET title=:title, url=:url, date=:date, city=:city, company=:company, "
            "summary=:summary, direction=:direction, lang=:lang, salary=:salary, search=:search, updated_at=:ts "
            "WHERE id=:id", rec)
        return False
    conn.execute(
        "INSERT INTO vacancies(id,title,url,date,city,company,summary,direction,lang,salary,search,first_seen,updated_at) "
        "VALUES(:id,:title,:url,:date,:city,:company,:summary,:direction,:lang,:salary,:search,:ts,:ts)", rec)
    return True


def set_detail(conn, vid: int, detail: dict) -> None:
    """detail: {body, contacts: [[label, value]], images: [url], posted_at}"""
    row = conn.execute("SELECT title, company, city, summary FROM vacancies WHERE id=?", (vid,)).fetchone()
    body = detail.get("body") or row["summary"] or ""
    contacts = detail.get("contacts") or []
    company = row["company"] or next((v for k, v in contacts if k.lower().startswith("работодател")), "")
    d = _derived(row["title"], company, row["city"], body + "\n" + " ".join(v for _, v in contacts))
    conn.execute(
        "UPDATE vacancies SET body=?, contacts=?, images=?, posted_at=?, company=?, direction=?, lang=?, salary=?, "
        "search=?, has_detail=1, updated_at=? WHERE id=?",
        (body, json.dumps(contacts, ensure_ascii=False), json.dumps(detail.get("images") or []),
         detail.get("posted_at"), company, d["direction"], d["lang"], d["salary"], d["search"], now(), vid))


def pending_details(conn, limit: int = 0) -> list[sqlite3.Row]:
    sql = "SELECT id, url, title, summary FROM vacancies WHERE has_detail=0 ORDER BY id DESC"
    return conn.execute(sql + (f" LIMIT {int(limit)}" if limit else "")).fetchall()


def reclassify(conn) -> int:
    rows = conn.execute("SELECT id, title, company, city, COALESCE(body, summary) AS t, contacts FROM vacancies").fetchall()
    for r in rows:
        extra = " ".join(v for _, v in json.loads(r["contacts"] or "[]"))
        d = _derived(r["title"], r["company"], r["city"], (r["t"] or "") + "\n" + extra)
        conn.execute("UPDATE vacancies SET direction=?, lang=?, salary=?, search=? WHERE id=?",
                     (d["direction"], d["lang"], d["salary"], d["search"], r["id"]))
    return len(rows)


def set_meta(conn, key: str, value: str) -> None:
    conn.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, value))


def get_meta(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


# ---------- reads (site) ----------

def _where(f: dict, skip: str = "") -> tuple[str, list]:
    cl, args = [], []
    for key, col in (("city", "city"), ("dir", "direction"), ("lang", "lang"), ("company", "company")):
        if f.get(key) and key != skip:
            cl.append(f"{col}=?")
            args.append(f[key])
    if f.get("period") in PERIODS and skip != "period":
        cl.append("date>=?")
        args.append((date.today() - timedelta(days=PERIODS[f["period"]] - 1)).isoformat())
    for word in (f.get("q") or "").lower().split()[:8]:
        sql, extra = word_clause(word)
        cl.append(sql)
        args += extra
    return (" WHERE " + " AND ".join(cl)) if cl else "", args


LIST_COLS = "id, title, date, city, company, direction, lang, summary, salary"


def search(conn, f: dict, page: int, per_page: int) -> tuple[list[sqlite3.Row], int]:
    where, args = _where(f)
    total = conn.execute(f"SELECT COUNT(*) FROM vacancies{where}", args).fetchone()[0]
    rows = conn.execute(
        f"SELECT {LIST_COLS} FROM vacancies{where} ORDER BY date DESC, id DESC LIMIT ? OFFSET ?",
        [*args, per_page, (page - 1) * per_page]).fetchall()
    return rows, total


def facet(conn, f: dict, key: str, col: str) -> list[tuple[str, int]]:
    where, args = _where(f, skip=key)
    sql = f"SELECT {col} AS v, COUNT(*) AS n FROM vacancies{where} GROUP BY {col} ORDER BY n DESC, v"
    return [(r["v"], r["n"]) for r in conn.execute(sql, args) if r["v"]]


def stats(conn) -> dict:
    week = (date.today() - timedelta(days=6)).isoformat()
    r = conn.execute(
        "SELECT COUNT(*) AS total, SUM(date>=?) AS week, COUNT(DISTINCT company) AS companies, "
        "COUNT(DISTINCT city) AS cities FROM vacancies", (week,)).fetchone()
    return {**dict(r), "week": r["week"] or 0, "updated": get_meta(conn, "last_scrape")}


def get(conn, vid: int) -> dict | None:
    row = conn.execute("SELECT * FROM vacancies WHERE id=?", (vid,)).fetchone()
    if not row:
        return None
    v = dict(row)
    v["contacts"] = json.loads(v["contacts"] or "[]")
    v["images"] = json.loads(v["images"] or "[]")
    return v


def related(conn, v: sqlite3.Row, limit: int = 6) -> list[sqlite3.Row]:
    return conn.execute(
        f"SELECT {LIST_COLS} FROM vacancies WHERE direction=? AND id<>? ORDER BY date DESC, id DESC LIMIT ?",
        (v["direction"], v["id"], limit)).fetchall()


def sitemap_rows(conn) -> list[sqlite3.Row]:
    return conn.execute("SELECT id, date FROM vacancies ORDER BY id DESC").fetchall()
