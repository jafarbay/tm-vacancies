"""Web site: server-rendered vacancy list with filters, vacancy pages, JSON API, sitemap.

    uvicorn app.main:app --host 127.0.0.1 --port 8000
"""
import math
import mimetypes
import re
from datetime import date, datetime, timedelta
from urllib.parse import urlencode, urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from . import db
from .classify import DIRECTIONS, OTHER
from .config import BASE_DIR, SITE_NAME, SITE_URL

PER_PAGE = 20
FILTER_KEYS = ("q", "city", "dir", "period", "lang", "company")
LANGS = {"ru": "Русский", "en": "English", "tm": "Türkmençe"}
PERIOD_LABELS = {"": "Всё время", "1": "Сегодня", "3": "3 дня", "7": "Неделя", "30": "Месяц", "60": "2 месяца"}
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
          "ноября", "декабря"]
# stable hue per direction for colored tags
DIR_HUE = {name: (i * 360 // (len(DIRECTIONS) + 1) + 150) % 360 for i, name in enumerate([*DIRECTIONS, OTHER])}

db.init()
mimetypes.add_type("font/woff2", ".woff2")  # not registered on every OS
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# Everything is served from our own origin: no third-party scripts, styles or fonts.
# style-src allows inline style attributes (tag colors use style="--h:..."); scripts stay strict.
CSP = ("default-src 'self'; script-src 'self' 'inline-speculation-rules'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data: https:; "
       "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; "
       "object-src 'none'")
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), interest-cohort=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


@app.middleware("http")
async def headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    path = request.url.path
    if path.startswith("/static/"):
        # files are versioned (?v=N) or never change (fonts): cache for a year
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path.startswith("/api/"):
        response.headers["Cache-Control"] = "public, max-age=60"
    else:
        # pages change only after a scraper run (every 30 min): short cache, browser revalidates
        response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
    return response
templates = Jinja2Templates(directory=BASE_DIR / "templates")


# ---------- template helpers ----------

def human_date(d: str | None) -> str:
    if not d:
        return ""
    day = date.fromisoformat(d[:10])
    delta = (date.today() - day).days
    if delta == 0:
        return "сегодня"
    if delta == 1:
        return "вчера"
    s = f"{day.day} {MONTHS[day.month - 1]}"
    return s if day.year == date.today().year else f"{s} {day.year}"


STALE_DAYS = 30  # older vacancies get a "may be closed" warning


def age_days(d: str | None) -> int:
    return (date.today() - date.fromisoformat(d[:10])).days if d else 0


def ago(d: str | None) -> str:
    n = age_days(d)
    if n < 30:
        return f"{n} {plural(n, 'день', 'дня', 'дней')} назад"
    if n < 365:
        m = n // 30
        return f"{m} {plural(m, 'месяц', 'месяца', 'месяцев')} назад"
    return "больше года назад"


def valid_through(d: str | None) -> str:
    return (date.fromisoformat(d[:10]) + timedelta(days=60)).isoformat() if d else ""


def human_dt(s: str | None) -> str:
    if not s:
        return "—"
    dt = datetime.fromisoformat(s)
    return f"{human_date(s)}, {dt:%H:%M}"


def plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(n) % 100
    if 11 <= n <= 19:
        return many
    return one if n % 10 == 1 else few if 2 <= n % 10 <= 4 else many


_LINK_RE = re.compile(r"([\w.+-]+@[\w-]+\.[\w.-]+)|(\+?\(?\d[\d \-()]{7,}\d)|(https?://[^\s<>\"]+)")


def _linkify(s: str) -> Markup:
    out, pos = [], 0
    for m in _LINK_RE.finditer(s):
        val = m.group(0)
        if m.group(3):
            val = val.rstrip(").,;:!?»\"'")  # trailing punctuation is not part of the URL
        out.append(escape(s[pos:m.start()]))
        pos = m.start() + len(val)
        if m.group(1):
            out.append(Markup('<a href="mailto:{0}">{0}</a>').format(val))
        elif m.group(2):
            digits = re.sub(r"[^\d+]", "", val)
            groups = len(re.split(r"[ \-()]+", val.strip("+() ")))
            # phone: 8+ digits and either +/( prefix or 3+ groups ("3000-4000" salary range is not a phone)
            if len(digits.lstrip("+")) >= 8 and (val[0] in "+(" or groups >= 3):
                out.append(Markup('<a href="tel:{}">{}</a>').format(digits, val))
            else:
                out.append(escape(val))
        else:
            shown = val if len(val) <= 60 else urlsplit(val).netloc + "/…"
            out.append(Markup('<a href="{}" target="_blank" rel="nofollow noopener">{}</a>').format(val, shown))
    out.append(escape(s[pos:]))
    return Markup("").join(out)


def fmt_body(text: str | None) -> Markup:
    """Plain text with '• ' bullets -> safe HTML paragraphs and lists."""
    out, in_list = [], False
    for line in (text or "").split("\n"):
        line = line.strip()
        bullet = line.startswith("• ")
        if in_list and not bullet:
            out.append(Markup("</ul>"))
            in_list = False
        if not line:
            continue
        if bullet:
            if not in_list:
                out.append(Markup("<ul>"))
                in_list = True
            out.append(Markup("<li>{}</li>").format(_linkify(line[2:])))
        elif line.startswith("## "):
            out.append(Markup("<h2>{}</h2>").format(_linkify(line[3:])))
        elif line.endswith(":") and len(line) < 60:
            out.append(Markup("<h2>{}</h2>").format(_linkify(line.rstrip(":"))))
        else:
            out.append(Markup("<p>{}</p>").format(_linkify(line)))
    if in_list:
        out.append(Markup("</ul>"))
    return Markup("").join(out)


def contact_html(label: str, value: str) -> Markup:
    low = label.lower()
    if re.fullmatch(r"\+?[\d\s\-()]{8,}", value):
        d = re.sub(r"\D", "", value)
        shown = f"+993 {d[3:5]} {d[5:7]}-{d[7:9]}-{d[9:]}" if d.startswith("993") and len(d) == 11 else value
        return Markup('<a href="tel:+{}">{}</a>').format(d, shown) if value.startswith("+") or d.startswith("993") \
            else Markup('<a href="tel:{}">{}</a>').format(d, shown)
    if "телефон" in low or "phone" in low:
        return _linkify(value)  # several numbers / mixed text
    if "@" in value:
        return Markup('<a href="mailto:{0}">{0}</a>').format(value)
    if value.startswith("http") or low.startswith("сайт"):
        href = value if value.startswith("http") else "https://" + value
        return Markup('<a href="{}" target="_blank" rel="nofollow noopener">{}</a>').format(href, value)
    return escape(value)


templates.env.filters.update(human_date=human_date, human_dt=human_dt, fmt_body=fmt_body, age_days=age_days, ago=ago,
                             valid_through=valid_through)
templates.env.globals.update(contact_html=contact_html, stale_days=STALE_DAYS)
templates.env.globals.update(site_name=SITE_NAME, site_url=SITE_URL, dir_hue=DIR_HUE, langs=LANGS,
                             plural=plural, periods=PERIOD_LABELS)


def read_filters(request: Request) -> dict:
    f = {k: request.query_params.get(k, "").strip()[:100] for k in FILTER_KEYS}
    if f["period"] not in db.PERIODS:
        f["period"] = ""
    return f


def make_url(filters: dict, **changes) -> str:
    params = {k: v for k, v in {**filters, **changes}.items() if v not in ("", None, 1)}
    return "/?" + urlencode(params) if params else "/"


# ---------- routes ----------

@app.get("/", response_class=HTMLResponse)
def index(request: Request, page: int = Query(1, ge=1, le=10000)):
    f = read_filters(request)
    with db.session() as conn:
        rows, total = db.search(conn, f, page, PER_PAGE)
        ctx = {
            "f": f,
            "rows": rows,
            "total": total,
            "page": page,
            "pages": max(1, math.ceil(total / PER_PAGE)),
            "cities": db.facet(conn, f, "city", "city"),
            "dirs": db.facet(conn, f, "dir", "direction"),
            "lang_facet": dict(db.facet(conn, f, "lang", "lang")),
            "stats": db.stats(conn),
            "url": lambda **kw: make_url(f, **kw),
            "active": [(k, v) for k, v in f.items() if v],
        }
    return templates.TemplateResponse(request, "index.html", ctx)


@app.get("/vacancy/{vid}", response_class=HTMLResponse)
def vacancy(request: Request, vid: int):
    with db.session() as conn:
        v = db.get(conn, vid)
        if not v:
            raise HTTPException(404)
        phones = [re.sub(r"[^\d+]", "", val) for _, val in v["contacts"] if re.fullmatch(r"\+?[\d\s\-()]{8,}", val)]
        if not phones and (m := re.search(r"\+993[\d\s\-()]{8,}\d", v["body"] or "")):
            phones = [re.sub(r"[^\d+]", "", m.group(0))]
        ctx = {"v": v, "phone": phones[0] if phones else "", "related": db.related(conn, v), "stats": db.stats(conn),
               "url": lambda **kw: make_url({}, **kw)}
    return templates.TemplateResponse(request, "vacancy.html", ctx)


@app.get("/api/vacancies")
def api_vacancies(request: Request, page: int = Query(1, ge=1, le=10000), per_page: int = Query(20, ge=1, le=100)):
    f = read_filters(request)
    with db.session() as conn:
        rows, total = db.search(conn, f, page, per_page)
    return {"total": total, "page": page, "items": [dict(r) for r in rows]}


@app.get("/api/vacancies/{vid}")
def api_vacancy(vid: int):
    with db.session() as conn:
        v = db.get(conn, vid)
    if not v:
        raise HTTPException(404)
    return {k: v[k] for k in v.keys() if k != "search"}


@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    with db.session() as conn:
        conn.execute("SELECT 1")
    return "ok"


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots():
    lines = ["User-agent: *", "Disallow: /api/", "Allow: /"]
    if SITE_URL:
        lines.append(f"Sitemap: {SITE_URL}/sitemap.xml")
    return "\n".join(lines)


@app.get("/sitemap.xml")
def sitemap():
    with db.session() as conn:
        rows = db.sitemap_rows(conn)
    urls = [f"<url><loc>{SITE_URL}/</loc><changefreq>hourly</changefreq></url>"]
    urls += [f"<url><loc>{SITE_URL}/vacancy/{r['id']}</loc><lastmod>{r['date']}</lastmod></url>" for r in rows
             if r["date"]]
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' \
          + "".join(urls) + "</urlset>"
    return Response(xml, media_type="application/xml")


@app.exception_handler(404)
def not_found(request: Request, exc):
    if request.url.path.startswith("/api/"):
        return Response('{"detail":"Not Found"}', status_code=404, media_type="application/json")
    with db.session() as conn:
        st = db.stats(conn)
    return templates.TemplateResponse(request, "404.html", {"stats": st}, status_code=404)
