"""Message texts and inline keyboards."""
import re
from html import escape as e

from aiogram.types import InlineKeyboardButton as Btn
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import SITE_URL
from app.main import STALE_DAYS, age_days, ago, human_date, plural


MSG_LIMIT = 4096
MODES = {"instant": "⚡ Сразу", "digest": "🗞 Раз в день", "off": "🔕 Выкл"}


SOURCE_NAME = "business.com.tm"
SOURCE_URL = "https://business.com.tm/ru/work/rabota/vakansii"


def vacancy_url(v: dict) -> str:
    """Our site if configured, otherwise the original page."""
    return f"{SITE_URL}/vacancy/{v['id']}" if SITE_URL else v["url"]


def links_line(v: dict) -> str:
    """'🔗 Наш сайт · Источник: business.com.tm' for the bottom of a card."""
    parts = [f'<a href="{e(SITE_URL)}/vacancy/{v["id"]}">Наш сайт</a>'] if SITE_URL else []
    parts.append(f'Источник: <a href="{e(v["url"])}">{SOURCE_NAME}</a>')
    return "🔗 " + " · ".join(parts)


def btn(text: str, data: str | None = None, url: str | None = None, style: str | None = None) -> Btn:
    return Btn(text=text, callback_data=data, url=url, style=style)


def kb(*rows: list[Btn]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[r for r in rows if r])


# ---------- texts ----------

def filters_line(u: dict) -> str:
    parts = [
        "📍 " + (", ".join(u["cities"]) if u["cities"] else "все города"),
        "🧭 " + (", ".join(u["dirs"]) if u["dirs"] else "все направления"),
    ]
    if u["keywords"]:
        parts.append("🔤 " + ", ".join(u["keywords"]))
    return "\n".join(e(p) for p in parts)


def welcome(u: dict) -> str:
    return (
        f"👋 <b>Привет, {e(u['name'] or 'друг')}!</b>\n\n"
        f'Я собираю вакансии Туркменистана с <a href="{SOURCE_URL}">{SOURCE_NAME}</a> '
        "и присылаю новые по твоим фильтрам.\n"
        + (f'🌐 Все вакансии с фильтрами: <a href="{e(SITE_URL)}">наш сайт</a>\n' if SITE_URL else "")
        + "\n"
        f"<b>Твои фильтры</b>\n{filters_line(u)}\n"
        f"🔔 Уведомления: {MODES[u['mode']]}\n\n"
        "💡 Просто напиши слово, например <i>бухгалтер</i> или <i>python</i>, и я найду вакансии."
    )


def _body_quote(body: str, limit: int) -> str:
    lines = []
    for line in (body or "").split("\n"):
        line = line.strip()
        if line.startswith("## "):
            if lines:
                lines.append("")
            line =f"\x00b{line[3:]}\x00/b"  # placeholder survives escaping
        lines.append(line)
    text = "\n".join(lines)
    if len(text) > limit:
        text = text[:limit].rsplit("\n", 1)[0] + "\n…"
    text = e(text).replace("\x00b", "<b>").replace("\x00/b", "</b>")
    return f"<blockquote expandable>{text}</blockquote>"


def card(v: dict) -> str:
    """Full vacancy card; body goes into an expandable quote and is cut to fit Telegram's limit."""
    head = [f"<b>{e(v['title'])}</b>", ""]
    if v.get("company"):
        head.append(f"🏢 {e(v['company'])}")
    head.append(f"📍 {e(v['city'])}  ·  🧭 {e(v['direction'])}")
    if v.get("salary"):
        head.append(f"💰 <b>{e(v['salary'])}</b>")
    age = age_days(v["date"])
    date_line = f"🗓 {human_date(v['date'])}"
    if age <= 2:
        date_line += "  🆕"
    elif age > STALE_DAYS:
        date_line += f"\n⚠️ <i>Опубликована {ago(v['date'])}, может быть уже закрыта</i>"
    head.append(date_line)

    tail = []
    contacts = [(k, val) for k, val in v.get("contacts") or [] if k.lower() not in ("работодатель", "регион")]
    if contacts:
        tail += ["", "☎️ <b>Контакты</b>"] + [f"{e(k)}: <code>{e(val)}</code>" if "елефон" in k else f"{e(k)}: {e(val)}"
                                             for k, val in contacts]
    tail += ["", links_line(v)]
    head_txt, tail_txt = "\n".join(head), "\n".join(tail)
    # links are hidden in tags: count only visible text
    room = MSG_LIMIT - len(head_txt) - len(re.sub(r"<[^>]+>", "", tail_txt)) - 120
    body = v.get("body") or v.get("summary") or ""
    return f"{head_txt}\n\n{_body_quote(body, room)}{tail_txt}" if body else head_txt + tail_txt


def list_text(title: str, rows: list[dict], total: int, page: int, per_page: int) -> str:
    if not rows:
        return f"{title}\n\n😕 Ничего не нашлось. Попробуй ослабить фильтры или изменить запрос."
    out = [title, f"Найдено <b>{total}</b>", DIVIDER]
    has_stale = False
    for i, r in enumerate(rows, 1):
        age = age_days(r["date"])
        has_stale |= age > STALE_DAYS
        badge = " 🆕" if age <= 2 else ""
        lines = [f"{NUM[i]} <b>{e(short_title(r['title']))}</b>{badge}"]
        if r.get("company"):
            lines.append(f"🏢 {e(r['company'])}")
        place = [] if r["city"] in ("", "Не указан") else [f"📍 {e(r['city'])}"]
        lines.append("   ".join([*place, ("⏳ " if age > STALE_DAYS else "🗓 ") + human_date(r["date"])]))
        if r.get("salary"):
            sal = r["salary"] if len(r["salary"]) <= 40 else r["salary"][:38].rstrip(" ,.") + "…"
            lines.append(f"💰 <b>{e(sal)}</b>")
        out.append("\n".join(lines))
        out.append("")
    if has_stale:
        out.append("<i>⏳ опубликована больше месяца назад, может быть закрыта</i>")
    return "\n".join(out).rstrip()


NUM = {i: f"{i}️⃣" for i in range(1, 10)}  # 1️⃣ … 9️⃣
DIVIDER = "━━━━━━━━━━━━━━"
_TITLE_PREFIX = re.compile(r"^\s*(вакансия|vacancy|wakansiýa|job vacancy)\s*[:\-–—]\s*", re.I)


def short_title(title: str) -> str:
    """Drop boilerplate prefixes like 'Вакансия:' for compact lists."""
    return _TITLE_PREFIX.sub("", title).strip() or title


def filters_short(u: dict) -> str:
    def part(icon, items, empty):
        if not items:
            return f"{icon} {empty}"
        return f"{icon} " + (", ".join(items) if len(items) <= 2 else f"{items[0]} +{len(items) - 1}")
    parts = [part("📍", u["cities"], "все города"), part("🧭", u["dirs"], "все направления")]
    if u["keywords"]:
        parts.append(part("🔤", u["keywords"], ""))
    return e(" · ".join(parts))


def digest(rows: list[dict]) -> str:
    out = [f"🗞 <b>Подборка новых вакансий</b> — {len(rows)}", ""]
    for r in rows:
        meta = " · ".join(x for x in (r.get("company"), r["city"], r.get("salary")) if x)
        src = f' · <a href="{e(r["url"])}">источник</a>' if SITE_URL else ""
        out.append(f"▫️ <a href=\"{e(vacancy_url(r))}\">{e(r['title'])}</a>\n     <i>{e(meta)}</i>{src}")
    out += ["", f'<i>Источник вакансий: <a href="{SOURCE_URL}">{SOURCE_NAME}</a></i>']
    return "\n".join(out)


# ---------- keyboards ----------

def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    return kb(
        [btn("🔎 Смотреть вакансии", "bl:0", style="primary")],
        [btn("⚙️ Фильтры", "flt"), btn("🔔 Уведомления", "n")],
        [btn("⭐ Избранное", "fl:0"), btn("ℹ️ Помощь", "h")],
        [btn("🌐 Наш сайт", url=SITE_URL), btn("📰 Источник", url=SOURCE_URL)] if SITE_URL
        else [btn("📰 Источник: " + SOURCE_NAME, url=SOURCE_URL)],
        [btn("🛠 Админка", "a", style="danger")] if is_admin else [],
    )


def list_kb(rows: list[dict], total: int, page: int, per_page: int, prefix: str, extra: list[Btn] | None = None):
    b = InlineKeyboardBuilder()
    for i, r in enumerate(rows, 1):
        b.button(text=NUM[i], callback_data=f"v:{r['id']}:{prefix}{page}")
    b.adjust(min(len(rows), 6) or 1)
    pages = max(1, (total - 1) // per_page + 1)
    if pages > 1:
        b.row(btn("◀️", f"{prefix}l:{page - 1}") if page > 0 else btn(" ", "noop"),
              btn(f"{page + 1} / {pages}", "noop"),
              btn("▶️", f"{prefix}l:{page + 1}", style="primary") if page + 1 < pages else btn(" ", "noop"))
    b.row(*(extra or []), btn("🏠 Меню", "m"))
    return b.as_markup()


def card_kb(v: dict, fav: bool, back: str | None) -> InlineKeyboardMarkup:
    return kb(
        [btn("💔 Убрать из избранного" if fav else "⭐ В избранное", f"fav:{v['id']}:{back or '-'}",
             style=None if fav else "success")],
        [*([btn("🌐 На нашем сайте", url=f"{SITE_URL}/vacancy/{v['id']}", style="primary")] if SITE_URL else []),
         btn("📰 Источник", url=v["url"])],
        [btn("« К списку", f"back:{back}")] if back and back != "-" else [],
    )


def filters_kb(u: dict) -> InlineKeyboardMarkup:
    return kb(
        [btn(f"📍 Города ({len(u['cities']) or 'все'})", "fc:0")],
        [btn(f"🧭 Направления ({len(u['dirs']) or 'все'})", "fd")],
        [btn(f"🔤 Ключевые слова ({len(u['keywords']) or 'нет'})", "fk")],
        [btn("♻️ Сбросить всё", "fr", style="danger"), btn("✅ Готово", "m", style="success")],
    )


def toggle_list_kb(items: list[str], selected: list[str], prefix: str, page: int = 0, per_page: int = 0,
                   back: str = "flt") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    start = page * per_page if per_page else 0
    chunk = items[start:start + per_page] if per_page else items
    for i, name in enumerate(chunk, start):
        on = name in selected
        b.button(text=("✅ " if on else "") + name, callback_data=f"{prefix}:{i}:{page}",
                 style="success" if on else None)
    b.adjust(2)
    if per_page and len(items) > per_page:
        nav = []
        if page > 0:
            nav.append(btn("◀️", f"{prefix}p:{page - 1}"))
        if start + per_page < len(items):
            nav.append(btn("▶️", f"{prefix}p:{page + 1}"))
        b.row(*nav)
    b.row(btn("Все (сбросить)", f"{prefix}x:{page}"), btn("✅ Готово", back, style="success"))
    return b.as_markup()


def notify_kb(mode: str) -> InlineKeyboardMarkup:
    return kb([btn(("● " if m == mode else "") + label, f"nm:{m}", style="primary" if m == mode else None)
               for m, label in MODES.items()], [btn("« Меню", "m")])


def help_text() -> str:
    return (
        "ℹ️ <b>Как пользоваться</b>\n\n"
        "• <b>Фильтры</b>: выбери города, направления и ключевые слова. По ним работают и уведомления, и просмотр.\n"
        "• <b>Уведомления</b>: «Сразу» присылает каждую новую вакансию, «Раз в день» присылает подборку утром.\n"
        "• <b>Поиск</b>: просто напиши слово, например <i>водитель</i>.\n"
        "• <b>⭐ Избранное</b>: сохраняй вакансии, чтобы вернуться к ним.\n\n"
        "⚠️ Источник не снимает старые объявления. Вакансии старше месяца помечены ⏳, уточняй их актуальность у работодателя.\n\n"
        f'📰 Все вакансии берутся с <a href="{SOURCE_URL}">{SOURCE_NAME}</a>, у каждой есть ссылка на оригинал.\n'
        + (f'🌐 Сайт с фильтрами: <a href="{e(SITE_URL)}">{e(SITE_URL.split("://")[-1])}</a>\n' if SITE_URL else "")
        + "\nКоманды: /start · /filters · /favorites · /help"
    )


def users_word(n: int) -> str:
    return plural(n, "пользователь", "пользователя", "пользователей")

