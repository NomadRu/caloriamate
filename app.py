import os
import asyncio
import threading
from flask import Flask
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta, timezone

from db import upsert_user, get_partner, link_partners, save_meal, stats
from ai import analyze_food

app = Flask(__name__)
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class AddMeal(StatesGroup):
    waiting_plates = State()

# ---------- /start ----------
@dp.message(CommandStart())
async def start(msg: Message):
    upsert_user(msg.from_user.id, msg.from_user.username)
    kb = InlineKeyboardBuilder()
    kb.button(text="📸 Анализ по фото", callback_data="photo")
    kb.button(text="📊 Мой прогресс", callback_data="my_stats")
    kb.button(text="👥 Партнёр", callback_data="partner")
    kb.adjust(1)
    await msg.answer("Привет! Я CalorieMate 🥗\nВыбери действие:", reply_markup=kb.as_markup())

# ---------- фото ----------
@dp.message(lambda m: m.photo is not None)
async def on_photo(msg: Message, state: FSMContext):
    file = await bot.download(msg.photo[-1], destination=f"/tmp/{msg.photo[-1].file_id}.jpg")
    await msg.answer("🔍 Анализирую фото...")
    data = analyze_food(file.name)
    item = data["items"][0] if "items" in data else data
    await state.update_data(item=item)
    await state.set_state(AddMeal.waiting_plates)
    await msg.answer(
        f"🍽 Блюдо: <b>{item['dish_name']}</b>\n"
        f"🔥 {item['kcal_per_100g']} ккал / 100 г\n"
        f"⚖️ Порция ~{item['grams_per_plate']} г\n\n"
        f"Сколько тарелок съел? Введи число (например 1 или 1.5):",
        parse_mode="HTML"
    )

@dp.message(AddMeal.waiting_plates)
async def on_plates(msg: Message, state: FSMContext):
    try:
        plates = float(msg.text.replace(",", "."))
    except (ValueError, AttributeError):
        return await msg.answer("Введи число, например 1 или 1.5")
    data = await state.get_data()
    it = data["item"]
    total = save_meal(msg.from_user.id, it["dish_name"], it["kcal_per_100g"],
                      it["grams_per_plate"], plates)
    await state.clear()
    await msg.answer(f"✅ Записано: {it['dish_name']} × {plates}\n🔥 Итого: <b>{total} ккал</b>",
                     parse_mode="HTML")

# ---------- статистика ----------
PERIODS = {"today": 0, "week": 7, "month": 30, "all": None}

def period_since(key):
    if PERIODS[key] is None:
        return "1970-01-01T00:00:00+00:00"
    dt = datetime.now(timezone.utc) - timedelta(days=PERIODS[key])
    return dt.isoformat()

@dp.callback_query(lambda c: c.data == "my_stats")
async def my_stats(cb: CallbackQuery):
    kb = InlineKeyboardBuilder()
    for label, key in [("Сегодня","today"),("Неделя","week"),("Месяц","month"),("Всё время","all")]:
        kb.button(text=label, callback_data=f"stat_me_{key}")
    kb.adjust(2)
    await cb.message.answer("Выбери период:", reply_markup=kb.as_markup())

@dp.callback_query(lambda c: c.data.startswith("stat_me_"))
async def stat_me(cb: CallbackQuery):
    key = cb.data.split("_")[-1]
    total = stats(cb.from_user.id, period_since(key))
    await cb.message.answer(f"📊 Твой итог: <b>{total} ккал</b>", parse_mode="HTML")

@dp.callback_query(lambda c: c.data == "partner")
async def partner(cb: CallbackQuery):
    pid = get_partner(cb.from_user.id)
    me = await bot.me()
    if not pid:
        return await cb.message.answer(
            "У тебя нет партнёра. Пришли другу ссылку:\n"
            f"`t.me/{me.username}?start=partner_{cb.from_user.id}`",
            parse_mode="Markdown"
        )
    kb = InlineKeyboardBuilder()
    for label, key in [("Сегодня","today"),("Неделя","week"),("Месяц","month"),("Всё время","all")]:
        kb.button(text=label, callback_data=f"stat_pt_{key}")
    kb.button(text="🔔 Напомнить покушать", callback_data="remind")
    kb.adjust(2)
    await cb.message.answer("Прогресс партнёра:", reply_markup=kb.as_markup())

@dp.callback_query(lambda c: c.data.startswith("stat_pt_"))
async def stat_pt(cb: CallbackQuery):
    pid = get_partner(cb.from_user.id)
    key = cb.data.split("_")[-1]
    total = stats(pid, period_since(key))
    await cb.message.answer(f"📊 Партнёр съел: <b>{total} ккал</b>", parse_mode="HTML")

@dp.callback_query(lambda c: c.data == "remind")
async def remind(cb: CallbackQuery):
    pid = get_partner(cb.from_user.id)
    if pid:
        await bot.send_message(pid, "🍽 Эй, пора подкрепиться! Твой партнёр напоминает 😊")
        await cb.answer("Напоминание отправлено ✅")
    else:
        await cb.answer("У тебя нет партнёра")

# ---------- привязка партнёра ----------
@dp.message(CommandStart(deep_link=True))
async def deep_start(msg: Message, command: CommandStart):
    payload = command.args  # "partner_12345"
    if payload and payload.startswith("partner_"):
        inviter = int(payload.split("_")[1])
        if inviter != msg.from_user.id:
            upsert_user(msg.from_user.id, msg.from_user.username)
            link_partners(inviter, msg.from_user.id)
            await msg.answer("💞 Вы теперь партнёры! Следите за калориями друг друга.")
            await bot.send_message(inviter, f"💞 {msg.from_user.first_name} присоединился к тебе!")

# ---------- Flask ----------
@app.route("/")
def home():
    return "CalorieMate is running"

@app.route("/health")
def health():
    return "OK"

def run_bot():
    asyncio.run(dp.start_polling(bot))

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
