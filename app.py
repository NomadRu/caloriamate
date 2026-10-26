import os
import asyncio
import base64
from datetime import datetime, timedelta, timezone
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
import google.generativeai as genai

from db import save_user, get_partner, link_partners, save_meal, get_stats

# --- Настройки ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
PORT = int(os.getenv("PORT", 8080))
URL = os.getenv("RENDER_EXTERNAL_URL")  # Render сам подставит свой URL
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{URL}{WEBHOOK_PATH}"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

class AddMeal(StatesGroup):
    wait_plates = State()

PERIODS = {"today": 0, "week": 7, "month": 30, "all": None}
def since(key):
    return "1970-01-01T00:00:00+00:00" if PERIODS[key] is None else (datetime.now(timezone.utc) - timedelta(days=PERIODS[key])).isoformat()

# --- Хэндлеры ---
@dp.message(CommandStart())
async def start(msg: Message, command: CommandStart):
    save_user(msg.from_user.id, msg.from_user.username)
    if command.args and command.args.startswith("p_"):
        inviter = int(command.args[2:])
        if inviter != msg.from_user.id:
            link_partners(inviter, msg.from_user.id)
            await msg.answer("💞 Вы теперь партнёры!")
            await bot.send_message(inviter, f"💞 {msg.from_user.first_name} присоединился к тебе!")
            return
    
    kb = InlineKeyboardBuilder()
    kb.button(text="📸 Анализ по фото", callback_data="photo")
    kb.button(text="📊 Мой прогресс", callback_data="my_stats")
    kb.button(text="👥 Партнёр", callback_data="partner")
    kb.adjust(1)
    await msg.answer("Привет! Я CalorieMate 🥗", reply_markup=kb.as_markup())

@dp.message(lambda m: m.photo)
async def on_photo(msg: Message, state: FSMContext):
    await msg.answer("🔍 Смотрю фото...")
    file = await bot.get_file(msg.photo[-1].file_id)
    buf = await bot.download_file(file.file_path)
    img = base64.b64encode(buf.read()).decode("utf-8")
    
    prompt = """Верни СТРОГО JSON: {"dish_name":"название","kcal_per_100g":число,"grams_per_plate":число}. Оцени порцию на фото."""
    try:
        resp = model.generate_content([prompt, {"mime_type": "image/jpeg", "data": img}])
        import json, re
        item = json.loads(re.sub(r"```json|```", "", resp.text).strip())
    except Exception as e:
        return await msg.answer(f"Ошибка ИИ: {e}")

    await state.update_data(item=item)
    await state.set_state(AddMeal.wait_plates)
    await msg.answer(f"🍽 {item['dish_name']}\n🔥 {item['kcal_per_100g']} ккал/100г\n⚖️ Порция ~{item['grams_per_plate']}г\n\nСколько тарелок? (например 1.5)")

@dp.message(AddMeal.wait_plates)
async def on_plates(msg: Message, state: FSMContext):
    try:
        plates = float(msg.text.replace(",", "."))
    except:
        return await msg.answer("Введи число, например 1.5")
    it = (await state.get_data())["item"]
    total = save_meal(msg.from_user.id, it['dish_name'], it['kcal_per_100g'], it['grams_per_plate'], plates)
    await state.clear()
    await msg.answer(f"✅ Записано: {it['dish_name']} × {plates}\n🔥 Итого: {total} ккал")

@dp.callback_query(lambda c: c.data == "my_stats")
async def my_stats(cb: CallbackQuery):
    kb = InlineKeyboardBuilder()
    for l, k in [("Сегодня","today"),("Неделя","week"),("Месяц","month"),("Всё время","all")]:
        kb.button(text=l, callback_data=f"sm_{k}")
    kb.adjust(2)
    await cb.message.answer("Период:", reply_markup=kb.as_markup())

@dp.callback_query(lambda c: c.data.startswith("sm_"))
async def stat_me(cb: CallbackQuery):
    total = get_stats(cb.from_user.id, since(cb.data[3:]))
    await cb.message.answer(f"📊 Твой итог: {total} ккал")

@dp.callback_query(lambda c: c.data == "partner")
async def partner(cb: CallbackQuery):
    pid = get_partner(cb.from_user.id)
    if not pid:
        me = await bot.me()
        return await cb.message.answer(f"Нет партнёра. Ссылка:\nt.me/{me.username}?start=p_{cb.from_user.id}")
    kb = InlineKeyboardBuilder()
    for l, k in [("Сегодня","today"),("Неделя","week"),("Месяц","month"),("Всё время","all")]:
        kb.button(text=l, callback_data=f"sp_{k}")
    kb.button(text="🔔 Напомнить покушать", callback_data="remind")
    kb.adjust(2)
    await cb.message.answer("Партнёр:", reply_markup=kb.as_markup())

@dp.callback_query(lambda c: c.data.startswith("sp_"))
async def stat_pt(cb: CallbackQuery):
    total = get_stats(get_partner(cb.from_user.id), since(cb.data[3:]))
    await cb.message.answer(f"📊 Партнёр съел: {total} ккал")

@dp.callback_query(lambda c: c.data == "remind")
async def remind(cb: CallbackQuery):
    pid = get_partner(cb.from_user.id)
    if pid:
        await bot.send_message(pid, "🍽 Пора подкрепиться! Твой партнёр напоминает 😊")
        await cb.answer("Отправлено ✅")

# --- Веб-сервер для Render (Webhook) ---
async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(app):
    await bot.delete_webhook()

def main():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
