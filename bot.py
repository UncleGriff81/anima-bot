import asyncio
import logging
import sqlite3
import json
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "9102167219:AAEMqwGo-ecnnR4SJeCVcSgcrRObYpf4FQs")
# Список ID админов (сюда можно добавить свой ID через запятую)
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
DB_PATH = '/data/anima.db' if os.path.exists('/data') else 'anima.db'

class AddScenario(StatesGroup):
    title = State(); description = State(); scenes_count = State(); scene_text = State(); scene_photo = State(); audio = State()

cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
skip_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Пропустить ⏭")], [KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)

def get_control_buttons(scenario_id, selected_at_str):
    kb = [[InlineKeyboardButton(text="✅ Завершить", callback_data=f"complete_{scenario_id}")]]
    if selected_at_str:
        selected_at = datetime.strptime(selected_at_str, "%Y-%m-%d %H:%M:%S.%f")
        if datetime.now() - selected_at < timedelta(hours=12):
            kb.append([InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_{scenario_id}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

async def send_scenario_details(target_message: types.Message, scenario_id: int, show_buttons=True):
    conn = sqlite3.connect(DB_PATH); cursor = conn.cursor()
    cursor.execute("SELECT title, description, scenes_data, audio_file_id, status FROM scenarios WHERE id = ?", (scenario_id,))
    row = cursor.fetchone(); conn.close()
    if not row: return
    title, description, scenes_json, audio_id, status = row
    await target_message.answer(f"🎬 <b>{title}</b>\n\n📝 <b>Описание:</b>\n{description}", parse_mode="HTML")
    if scenes_json:
        scenes = json.loads(scenes_json)
        for i, scene in enumerate(scenes, 1):
            caption = f"<b>Сцена {i}:</b>\n{scene['text']}"
            if scene.get('photo'): await target_message.answer_photo(photo=scene['photo'], caption=caption, parse_mode="HTML")
            else: await target_message.answer(caption, parse_mode="HTML")
    if audio_id: await target_message.answer_audio(audio=audio_id, caption="🎵 Голосовое сопровождение")
    if show_buttons and status == 'free':
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Выбрать этот сценарий", callback_data=f"select_{scenario_id}")]])
        await target_message.answer("Готовы взять этот сценарий в работу?", reply_markup=kb)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(f"Привет, {message.from_user.first_name}!\n\n/add_scenario — Добавить\n/list_scenarios — Свободные\n/my_scenarios — Мои ролики")

# --- НОВАЯ КОМАНДА ДЛЯ АДМИНА ---
@dp.message(Command("add_user"))
async def add_user(message: types.Message):
    # Проверка, что пишет админ
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("У вас нет прав для этой команды.")
        return
    
    # Формат: /add_user @username роль
    try:
        parts = message.text.split()
        if len(parts) < 3:
            await message.answer("Формат: /add_user @username роль\nПример: /add_user @ivan сценарист")
            return
            
        target_username = parts[1].replace("@", "")
        role = parts[2].lower()
        
        if role not in ['admin', 'scenarist', 'animator']:
            await message.answer("Роль должна быть: admin, scenarist или animator")
            return

        # Пытаемся получить ID пользователя по нику (если он писал боту)
        conn = sqlite3.connect(DB_PATH); cursor = conn.cursor()
        cursor.execute("SELECT user_id, first_name FROM users WHERE username = ?", (target_username,))
        existing = cursor.fetchone()
        
        if not existing:
            await message.answer(f"Пользователь @{target_username} не найден. Попросите его написать боту /start.")
            conn.close()
            return
            
        user_id, first_name = existing
        cursor.execute("UPDATE users SET role = ? WHERE user_id = ?", (role, user_id))
        conn.commit()
        conn.close()
        
        await message.answer(f"✅ Пользователь @{target_username} ({first_name}) назначен на роль: {role}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

# Обработчик регистрации (когда пользователь пишет /start)
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Сохраняем пользователя в базу, если его там нет
    conn = sqlite3.connect(DB_PATH); cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
                   (message.from_user.id, message.from_user.username, message.from_user.first_name))
    conn.commit(); conn.close()
    
    await message.answer(f"Привет, {message.from_user.first_name}!\n\n/add_scenario — Добавить\n/list_scenarios — Свободные\n/my_scenarios — Мои ролики")

# ... остальной код бота (add_scenario, process_..., list_scenarios, select_, cancel_, complete_, reminders) ...
# Он остается без изменений, я его пропущу для краткости, чтобы ты вставил только новые части.
# Но ты можешь просто взять старый код и вставить в него эти новые обработчики.

async def check_reminders():
    while True:
        try:
            conn = sqlite3.connect(DB_PATH); cursor = conn.cursor()
            six_days_ago = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d %H:%M:%S.%f")
            cursor.execute("SELECT id, title, animator_id FROM scenarios WHERE status = 'taken' AND selected_at < ?", (six_days_ago,))
            overdue = cursor.fetchall(); conn.close()
            for s in overdue:
                try:
                    await bot.send_message(s[2], f"⚠️ Напоминание: Вы взяли сценарий «{s[1]}» более 6 дней назад, но не завершили его.")
                except: pass
        except Exception as e:
            print(f"Ошибка в напоминаниях: {e}")
        await asyncio.sleep(3600)

async def main():
    asyncio.create_task(check_reminders())
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("Остановлен.")