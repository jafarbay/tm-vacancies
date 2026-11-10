"""Admin panel inside the bot (/admin), available to ADMIN_IDS only."""
import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.main import human_dt

from . import storage, ui
from .config import ADMIN_IDS
from .user import show

router = Router()
router.message.filter(F.from_user.id.in_(ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))
log = logging.getLogger("bot.admin")
USERS_PAGE = 8
_tasks: set[asyncio.Task] = set()


class AdminForm(StatesGroup):
    broadcast = State()


def admin_menu():
    paused = storage.flag("notify_paused")
    return ui.kb(
        [ui.btn("📊 Статистика", "as", style="primary")],
        [ui.btn("👥 Пользователи", "au:0"), ui.btn("📣 Рассылка", "abc")],
        [ui.btn("▶️ Возобновить уведомления" if paused else "⏸ Пауза уведомлений", "ap",
                style="success" if paused else "danger")],
        [ui.btn("« Меню", "m")],
    )


def stats_text() -> str:
    s = storage.stats()
    u, v = s["u"], s["v"]
    return (
        "📊 <b>Статистика</b>\n\n"
        f"<b>Пользователи</b>: {u['total']} (+{u['new_day']} за сутки)\n"
        f"  активных {u['active']} · заблокировали бота {u['blocked']} · бан {u['banned']}\n"
        f"  ⚡ сразу {u['instant']} · 🗞 дайджест {u['digest']} · 🔕 выкл {u['off']}\n"
        f"  ⭐ в избранном: {s['fav']}\n\n"
        f"<b>Вакансии</b>: {v['total']} (+{v['new_day'] or 0} за сутки)\n"
        f"  без полного текста: {v['pending'] or 0}\n"
        f"  последняя дата: {v['last_date'] or '—'}\n"
        f"  парсер: {human_dt(s['last_scrape'])}\n\n"
        f"Уведомления: {'⏸ на паузе' if s['paused'] else '▶️ работают'}"
    )


@router.message(Command("admin"))
async def admin_cmd(m: Message, state: FSMContext):
    await state.set_state(None)
    await m.answer(stats_text(), reply_markup=admin_menu())


@router.callback_query(F.data == "a")
async def admin_cb(cb: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    await show(cb, stats_text(), admin_menu())


@router.callback_query(F.data == "as")
async def stats_cb(cb: CallbackQuery):
    await show(cb, stats_text(), admin_menu())


@router.callback_query(F.data == "ap")
async def pause_cb(cb: CallbackQuery):
    storage.set_flag("notify_paused", not storage.flag("notify_paused"))
    await show(cb, stats_text(), admin_menu())


# ---------- users ----------

def user_line(u: dict) -> str:
    status = "⛔" if u["is_banned"] else ("💤" if not u["is_active"] else "🟢")
    nick = f"@{u['username']}" if u["username"] else ""
    return f"{status} {ui.e(u['name'] or '—')} {ui.e(nick)} · {ui.MODES[u['mode']]}"


@router.callback_query(F.data.startswith("au:"))
async def users_cb(cb: CallbackQuery):
    page = int(cb.data[3:])
    rows, total = storage.list_users(page, USERS_PAGE)
    text = f"👥 <b>Пользователи</b>: {total}\n🟢 активен · 💤 заблокировал бота · ⛔ бан\n\n" + \
           "\n".join(f"{i}. {user_line(u)}" for i, u in enumerate(rows, page * USERS_PAGE + 1))
    b = [[ui.btn(f"{i}. {(u['name'] or str(u['id']))[:20]}", f"auv:{u['id']}:{page}")]
         for i, u in enumerate(rows, page * USERS_PAGE + 1)]
    nav = [ui.btn("◀️", f"au:{page - 1}")] if page else []
    if (page + 1) * USERS_PAGE < total:
        nav.append(ui.btn("▶️", f"au:{page + 1}"))
    await show(cb, text, ui.kb(*b, nav, [ui.btn("« Админка", "a")]))


def user_card(u: dict) -> str:
    return (f"👤 <b>{ui.e(u['name'] or '—')}</b> {ui.e('@' + u['username']) if u['username'] else ''}\n"
            f"ID: <code>{u['id']}</code>\n"
            f"С нами с {human_dt(u['created_at'])}, был {human_dt(u['seen_at'])}\n"
            f"Уведомления: {ui.MODES[u['mode']]}\n\n{ui.filters_line(u)}\n\n"
            f"Статус: {'⛔ забанен' if u['is_banned'] else ('💤 заблокировал бота' if not u['is_active'] else '🟢 активен')}")


@router.callback_query(F.data.startswith("auv:"))
async def user_cb(cb: CallbackQuery):
    _, uid, page = cb.data.split(":")
    await render_user(cb, int(uid), page)


async def render_user(cb: CallbackQuery, uid: int, page: str):
    u = storage.get_user(uid)
    if not u:
        await cb.answer("Не найден")
        return
    await show(cb, user_card(u), ui.kb(
        [ui.btn("✅ Разбанить" if u["is_banned"] else "⛔ Забанить", f"ab:{uid}:{page}",
                style="success" if u["is_banned"] else "danger")],
        [ui.btn("« К списку", f"au:{page}")]))


@router.callback_query(F.data.startswith("ab:"))
async def ban_cb(cb: CallbackQuery):
    _, uid, page = cb.data.split(":")
    u = storage.get_user(int(uid))
    if u and u["id"] not in ADMIN_IDS:
        storage.update_user(u["id"], is_banned=0 if u["is_banned"] else 1)
    await render_user(cb, int(uid), page)


# ---------- broadcast ----------

@router.callback_query(F.data == "abc")
async def broadcast_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminForm.broadcast)
    await show(cb, f"📣 <b>Рассылка</b>\nПолучателей: {len(storage.all_recipients())}\n\n"
                   "Пришли сообщение для рассылки: текст, фото, видео, с оформлением. Я покажу превью.",
               ui.kb([ui.btn("Отмена", "a")]))


@router.message(StateFilter(AdminForm.broadcast))
async def broadcast_preview(m: Message, state: FSMContext):
    await state.update_data(bc_chat=m.chat.id, bc_msg=m.message_id)
    await state.set_state(None)
    await m.copy_to(m.chat.id)
    await m.answer("☝️ Так увидят пользователи. Отправить?", reply_markup=ui.kb(
        [ui.btn("✅ Отправить всем", "abcy", style="success"), ui.btn("✖️ Отмена", "a", style="danger")]))


@router.callback_query(F.data == "abcy")
async def broadcast_send(cb: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    if "bc_msg" not in data:
        await cb.answer("Нет сообщения для рассылки", show_alert=True)
        return
    await state.update_data(bc_msg=None)
    await show(cb, "📣 Рассылка запущена, по завершении пришлю отчёт.", ui.kb([ui.btn("« Админка", "a")]))
    task = asyncio.create_task(run_broadcast(bot, cb.from_user.id, data["bc_chat"], data["bc_msg"]))
    _tasks.add(task)  # keep a reference so the task is not garbage-collected
    task.add_done_callback(_tasks.discard)


async def run_broadcast(bot: Bot, admin_id: int, chat_id: int, msg_id: int) -> None:
    ok = fail = 0
    for uid in storage.all_recipients():
        for _ in range(2):
            try:
                await bot.copy_message(uid, chat_id, msg_id)
                ok += 1
                break
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
            except TelegramForbiddenError:
                storage.update_user(uid, is_active=0)
                fail += 1
                break
            except Exception as e:
                log.warning("broadcast to %s failed: %s", uid, e)
                fail += 1
                break
        await asyncio.sleep(0.05)  # ~20 msg/s, under Telegram's 30/s limit
    await bot.send_message(admin_id, f"📣 Рассылка завершена\n✅ доставлено: {ok}\n❌ не доставлено: {fail}")
