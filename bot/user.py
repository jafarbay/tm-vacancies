"""User-facing handlers: menu, filters, browse/search, favorites, notification mode."""
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from . import storage, ui
from .config import ADMIN_IDS

router = Router()
PER_PAGE = 6
CITY_PAGE = 12


class Form(StatesGroup):
    keywords = State()


async def show(target: Message | CallbackQuery, text: str, markup=None) -> None:
    """Edit the callback's message in place, or send a new one."""
    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=markup)
        except TelegramBadRequest as e:
            if "not modified" not in str(e):
                await target.message.answer(text, reply_markup=markup)
        await target.answer()
    else:
        await target.answer(text, reply_markup=markup)


def user_of(event: Message | CallbackQuery) -> dict:
    f = event.from_user
    return storage.get_user(f.id) or storage.touch_user(f.id, f.username, f.full_name)


# ---------- menu ----------

@router.message(CommandStart())
@router.message(Command("menu"))
async def start(m: Message, state: FSMContext):
    await state.clear()
    u = storage.touch_user(m.from_user.id, m.from_user.username, m.from_user.full_name)
    await m.answer(ui.welcome(u), reply_markup=ui.main_menu(m.from_user.id in ADMIN_IDS))


@router.callback_query(F.data == "m")
async def menu(cb: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    await show(cb, ui.welcome(user_of(cb)), ui.main_menu(cb.from_user.id in ADMIN_IDS))


@router.message(Command("help"))
async def help_cmd(m: Message):
    await m.answer(ui.help_text(), reply_markup=ui.kb([ui.btn("« Меню", "m")]))


@router.callback_query(F.data == "h")
async def help_cb(cb: CallbackQuery):
    await show(cb, ui.help_text(), ui.kb([ui.btn("« Меню", "m")]))


# ---------- browse / search ----------

async def render_browse(target, u: dict, page: int, query: str):
    rows, total = storage.browse(u, page, PER_PAGE, query)
    title = f"🔎 <b>Поиск: «{ui.e(query)}»</b>" if query else "🔎 <b>Вакансии по твоим фильтрам</b>"
    title += f"\n<i>{ui.filters_short(u)}</i>"
    extra = [ui.btn("✖️ Сбросить поиск", "bq")] if query else [ui.btn("⚙️ Фильтры", "flt")]
    await show(target, ui.list_text(title, rows, total, page, PER_PAGE),
               ui.list_kb(rows, total, page, PER_PAGE, "b", extra))


@router.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery):
    await cb.answer()


@router.callback_query(F.data.startswith("bl:"))
async def browse(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await render_browse(cb, user_of(cb), int(cb.data[3:]), data.get("q", ""))


@router.callback_query(F.data == "bq")
async def reset_query(cb: CallbackQuery, state: FSMContext):
    await state.update_data(q="")
    await render_browse(cb, user_of(cb), 0, "")


@router.message(Command("search"))
async def search_cmd(m: Message, state: FSMContext):
    q = (m.text or "").partition(" ")[2].strip()
    if not q:
        await m.answer("Напиши, что ищем, например: <i>бухгалтер</i>")
        return
    await state.update_data(q=q[:60])
    await render_browse(m, user_of(m), 0, q[:60])


# ---------- vacancy card ----------

@router.callback_query(F.data.startswith("v:"))
async def open_vacancy(cb: CallbackQuery):
    _, vid, back = cb.data.split(":", 2)
    v = storage.vacancy(int(vid))
    if not v:
        await cb.answer("Вакансия не найдена", show_alert=True)
        return
    await show(cb, ui.card(v), ui.card_kb(v, storage.is_favorite(cb.from_user.id, v["id"]), back))


@router.callback_query(F.data.startswith("fav:"))
async def toggle_fav(cb: CallbackQuery):
    _, vid, back = cb.data.split(":", 2)
    v = storage.vacancy(int(vid))
    if not v:
        await cb.answer("Вакансия не найдена", show_alert=True)
        return
    added = storage.toggle_favorite(cb.from_user.id, v["id"])
    await cb.message.edit_reply_markup(reply_markup=ui.card_kb(v, added, back))
    await cb.answer("⭐ Сохранено" if added else "Убрано из избранного")


@router.callback_query(F.data.startswith("back:"))
async def back(cb: CallbackQuery, state: FSMContext):
    target = cb.data[5:]
    kind, page = target[0], int(target[1:] or 0)
    if kind == "f":
        await render_favorites(cb, page)
    else:
        await render_browse(cb, user_of(cb), page, (await state.get_data()).get("q", ""))


# ---------- favorites ----------

async def render_favorites(target, page: int):
    rows, total = storage.favorites(target.from_user.id, page, PER_PAGE)
    text = ui.list_text("⭐ <b>Избранное</b>", rows, total, page, PER_PAGE) if total else \
        "⭐ <b>Избранное</b>\n\nПока пусто. Открой вакансию и нажми «⭐ В избранное»."
    await show(target, text, ui.list_kb(rows, total, page, PER_PAGE, "f"))


@router.callback_query(F.data.startswith("fl:"))
async def favorites_cb(cb: CallbackQuery):
    await render_favorites(cb, int(cb.data[3:]))


@router.message(Command("favorites"))
async def favorites_cmd(m: Message):
    await render_favorites(m, 0)


# ---------- filters ----------

FILTERS_TEXT = "⚙️ <b>Фильтры</b>\nПо ним работают уведомления и просмотр.\n\n"


@router.callback_query(F.data == "flt")
async def filters(cb: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    u = user_of(cb)
    await show(cb, FILTERS_TEXT + ui.filters_line(u), ui.filters_kb(u))


@router.message(Command("filters"))
async def filters_cmd(m: Message):
    u = user_of(m)
    await m.answer(FILTERS_TEXT + ui.filters_line(u), reply_markup=ui.filters_kb(u))


async def render_cities(cb: CallbackQuery, u: dict, page: int):
    await show(cb, "📍 <b>Города</b>\nОтметь нужные. Если не выбрано ни одного, ищу по всем.",
               ui.toggle_list_kb(storage.cities(), u["cities"], "tc", page, CITY_PAGE))


@router.callback_query(F.data.startswith("fc:"))
async def cities(cb: CallbackQuery):
    await render_cities(cb, user_of(cb), int(cb.data[3:]))


@router.callback_query(F.data.startswith("tcp:"))
async def cities_page(cb: CallbackQuery):
    await render_cities(cb, user_of(cb), int(cb.data[4:]))


@router.callback_query(F.data.startswith("tcx:"))
async def cities_reset(cb: CallbackQuery):
    storage.update_user(cb.from_user.id, cities=[])
    await render_cities(cb, user_of(cb), int(cb.data[4:]))


@router.callback_query(F.data.startswith("tc:"))
async def city_toggle(cb: CallbackQuery):
    _, idx, page = cb.data.split(":")
    u, all_cities = user_of(cb), storage.cities()
    if int(idx) < len(all_cities):
        name = all_cities[int(idx)]
        sel = [c for c in u["cities"] if c != name] if name in u["cities"] else [*u["cities"], name]
        storage.update_user(u["id"], cities=sel)
    await render_cities(cb, user_of(cb), int(page))


async def render_dirs(cb: CallbackQuery, u: dict):
    await show(cb, "🧭 <b>Направления</b>\nОтметь нужные. Если не выбрано ни одного, ищу по всем.",
               ui.toggle_list_kb(storage.DIRS, u["dirs"], "td"))


@router.callback_query(F.data == "fd")
async def dirs(cb: CallbackQuery):
    await render_dirs(cb, user_of(cb))


@router.callback_query(F.data.startswith("tdx:"))
async def dirs_reset(cb: CallbackQuery):
    storage.update_user(cb.from_user.id, dirs=[])
    await render_dirs(cb, user_of(cb))


@router.callback_query(F.data.startswith("td:"))
async def dir_toggle(cb: CallbackQuery):
    idx = int(cb.data.split(":")[1])
    u = user_of(cb)
    if idx < len(storage.DIRS):
        name = storage.DIRS[idx]
        sel = [d for d in u["dirs"] if d != name] if name in u["dirs"] else [*u["dirs"], name]
        storage.update_user(u["id"], dirs=sel)
    await render_dirs(cb, user_of(cb))


@router.callback_query(F.data == "fk")
async def keywords(cb: CallbackQuery, state: FSMContext):
    u = user_of(cb)
    await state.set_state(Form.keywords)
    current = ", ".join(u["keywords"]) or "нет"
    await show(cb, f"🔤 <b>Ключевые слова</b>\nСейчас: <i>{ui.e(current)}</i>\n\n"
                   "Пришли слова через запятую, например: <code>python, аналитик, english</code>\n"
                   "Будут приходить вакансии, где есть <b>хотя бы одно</b> из слов.",
               ui.kb([ui.btn("🗑 Очистить", "fkc", style="danger"), ui.btn("« Назад", "flt")]))


@router.callback_query(F.data == "fkc")
async def keywords_clear(cb: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    storage.update_user(cb.from_user.id, keywords=[])
    u = user_of(cb)
    await show(cb, FILTERS_TEXT + ui.filters_line(u), ui.filters_kb(u))


@router.message(StateFilter(Form.keywords), F.text)
async def keywords_set(m: Message, state: FSMContext):
    words = [w.strip()[:30] for w in m.text.replace("\n", ",").split(",") if w.strip()][:10]
    storage.update_user(m.from_user.id, keywords=words)
    await state.set_state(None)
    u = user_of(m)
    await m.answer("✅ Сохранено\n\n" + FILTERS_TEXT + ui.filters_line(u), reply_markup=ui.filters_kb(u))


@router.callback_query(F.data == "fr")
async def filters_reset(cb: CallbackQuery):
    storage.update_user(cb.from_user.id, cities=[], dirs=[], keywords=[])
    u = user_of(cb)
    await show(cb, FILTERS_TEXT + ui.filters_line(u), ui.filters_kb(u))


# ---------- notifications ----------

NOTIFY_TEXT = ("🔔 <b>Уведомления</b>\n\n⚡ <b>Сразу</b>: каждая новая вакансия по фильтрам приходит отдельным сообщением.\n"
               "🗞 <b>Раз в день</b>: одна подборка утром.\n🔕 <b>Выкл</b>: ничего не присылаю.")


@router.callback_query(F.data == "n")
async def notify(cb: CallbackQuery):
    await show(cb, NOTIFY_TEXT, ui.notify_kb(user_of(cb)["mode"]))


@router.callback_query(F.data.startswith("nm:"))
async def notify_set(cb: CallbackQuery):
    mode = cb.data[3:]
    if mode in ui.MODES:
        # start from "now": no backlog after switching
        storage.update_user(cb.from_user.id, mode=mode, last_vacancy_id=storage.ready_max_id())
    await show(cb, NOTIFY_TEXT, ui.notify_kb(mode))


# ---------- free text = search (must be the last handler) ----------

@router.message(StateFilter(None), F.text & ~F.text.startswith("/"))
async def free_search(m: Message, state: FSMContext):
    q = m.text.strip()[:60]
    await state.update_data(q=q)
    await render_browse(m, user_of(m), 0, q)
