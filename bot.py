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
# Список ID админов через запятую (например, "123456789,987654321")
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_STR.split(",") if x.strip()]

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
    # Сохраняем пользователя в базу, если его там нет
    try:
        conn = sqlite3.connect(DB_PATH); cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
                       (message.from_user.id, message.from_user.username, message.from_user.first_name))
        conn.commit()
        conn.close()
        print(f"✅ Пользователь {message.from_user.id} (@{message.from_user.username}) сохранен/обновлен.")
    except Exception as e:
        print(f"❌ Ошибка при сохранении пользователя: {e}")

    await message.answer(
        f"Привет, {message.from_user.first_name}!\n\n"
        "/add_scenario — Добавить сценарий\n"
        "/list_scenarios — Свободные сценарии\n"
        "/my_scenarios — Мои ролики\n"
        "/add_user — Добавить участника (только для админа)"
    )

@dp.message(Command("add_user"))
async def add_user(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("У вас нет прав для этой команды.")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 3:
            await message.answer("Формат: /add_user @username роль\nПример: /add_user @ivan animator")
            return
            
        target_username = parts[1].replace("@", "")
        role = parts[2].lower()
        
        if role not in ['admin', 'scenarist', 'animator']:
            await message.answer("Роль должна быть: admin, scenarist или animator")
            return

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

@dp.message(Command("add_scenario"))
async def add_scenario_start(message: types.Message, state: FSMContext):
    await message.answer("Шаг 1/5. Введите название ролика:", reply_markup=cancel_kb); await state.set_state(AddScenario.title)

@dp.message(AddScenario.title)
async def process_title(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена": return await cancel_add(message, state)
    await state.update_data(title=message.text); await message.answer("Шаг 2/5. Введите описание:"); await state.set_state(AddScenario.description)

@dp.message(AddScenario.description)
async def process_description(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена": return await cancel_add(message, state)
    await state.update_data(description=message.text); await message.answer("Шаг 3/5. Сколько сцен? (число)"); await state.set_state(AddScenario.scenes_count)

@dp.message(AddScenario.scenes_count)
async def process_scenes_count(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена": return await cancel_add(message, state)
    if not message.text.isdigit(): await message.answer("Введите число."); return
    await state.update_data(scenes_count=int(message.text), current_scene=1, scenes=[])
    await message.answer(f"Шаг 4/5. Описание Сцены №1:"); await state.set_state(AddScenario.scene_text)

@dp.message(AddScenario.scene_text)
async def process_scene_text(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена": return await cancel_add(message, state)
    await state.update_data(current_scene_text=message.text); await message.answer("Фото (или 'Пропустить ⏭'):", reply_markup=skip_kb); await state.set_state(AddScenario.scene_photo)

@dp.message(AddScenario.scene_photo)
async def process_scene_photo(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена": return await cancel_add(message, state)
    data = await state.get_data(); scenes = data['scenes']; photo_id = None
    if message.photo: photo_id = message.photo[-1].file_id
    elif message.text != "Пропустить ⏭": await message.answer("Прикрепите фото или нажмите Пропустить."); return
    scenes.append({"text": data['current_scene_text'], "photo": photo_id})
    current = data['current_scene']; total = data['scenes_count']
    if current < total:
        await state.update_data(scenes=scenes, current_scene=current + 1)
        await message.answer(f"Описание Сцены №{current + 1}:", reply_markup=cancel_kb); await state.set_state(AddScenario.scene_text)
    else:
        await state.update_data(scenes=scenes); await message.answer("Шаг 5/5. Аудио (или 'Пропустить ⏭'):", reply_markup=skip_kb); await state.set_state(AddScenario.audio)

@dp.message(AddScenario.audio)
async def process_audio(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена": return await cancel_add(message, state)
    audio_id = None
    if message.audio: audio_id = message.audio.file_id
    elif message.text != "Пропустить ⏭": await message.answer("Прикрепите аудио."); return
    data = await state.get_data(); conn = sqlite3.connect(DB_PATH); cursor = conn.cursor()
    cursor.execute("INSERT INTO scenarios (title, description, scenes_count, scenes_data, audio_file_id) VALUES (?, ?, ?, ?, ?)",
        (data['title'], data['description'], data['scenes_count'], json.dumps(data['scenes'], ensure_ascii=False), audio_id))
    conn.commit(); conn.close()
    await message.answer(f"✅ Сценарий «{data['title']}» добавлен!", reply_markup=ReplyKeyboardRemove()); await state.clear()

async def cancel_add(message: types.Message, state: FSMContext):
    await state.clear(); await message.answer("Отменено.", reply_markup=ReplyKeyboardRemove())

@dp.message(Command("list_scenarios"))
async def list_scenarios(message: types.Message):
    conn = sqlite3.connect(DB_PATH); cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM scenarios WHERE status = 'free'")
    scenarios = cursor.fetchall(); conn.close()
    if not scenarios: await message.answer("Нет свободных сценариев."); return
    await message.answer("🎬 <b>Доступные сценарии:</b>", parse_mode="HTML")
    for scenario in scenarios:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"Посмотреть «{scenario[1]}»", callback_data=f"view_{scenario[0]}")]])
        await message.answer(f"📌 {scenario[1]}", reply_markup=kb)

@dp.callback_query(F.data.startswith("view_"))
async def process_view(callback: types.CallbackQuery):
    await callback.answer(); await send_scenario_details(callback.message, int(callback.data.split("_")[1]))

@dp.callback_query(F.data.startswith("select_"))
async def process_select(callback: types.CallbackQuery):
    scenario_id = int(callback.data.split("_")[1]); user_id = callback.from_user.id; username = callback.from_user.username or callback.from_user.first_name
    conn = sqlite3.connect(DB_PATH); cursor = conn.cursor()
    cursor.execute("SELECT status, title FROM scenarios WHERE id = ?", (scenario_id,)); result = cursor.fetchone()
    if result and result[0] == 'free':
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        cursor.execute("UPDATE scenarios SET status = 'taken', animator_id = ?, selected_at = ? WHERE id = ?", (user_id, now_str, scenario_id))
        conn.commit()
        text = f"📌 <b>{result[1]}</b>\n\n🔒 Выбрал: @{username}\nСтатус: В работе"
        await callback.message.edit_text(text, reply_markup=get_control_buttons(scenario_id, now_str), parse_mode="HTML")
        await callback.answer(f"Вы взяли сценарий!")
    else: await callback.answer("Уже занят.", show_alert=True)
    conn.close()

@dp.message(Command("my_scenarios"))
async def my_scenarios(message: types.Message):
    user_id = message.from_user.id; conn = sqlite3.connect(DB_PATH); cursor = conn.cursor()
    cursor.execute("SELECT id, title, selected_at FROM scenarios WHERE status = 'taken' AND animator_id = ?", (user_id,))
    scenarios = cursor.fetchall(); conn.close()
    if not scenarios: await message.answer("У вас нет роликов."); return
    for s in scenarios: await message.answer(f"📌 <b>{s[1]}</b>", reply_markup=get_control_buttons(s[0], s[2]), parse_mode="HTML")

@dp.callback_query(F.data.startswith("complete_"))
async def process_complete(callback: types.CallbackQuery):
    scenario_id = int(callback.data.split("_")[1]); conn = sqlite3.connect(DB_PATH); cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    cursor.execute("UPDATE scenarios SET status = 'completed', completed_at = ? WHERE id = ?", (now_str, scenario_id))
    conn.commit(); cursor.execute("SELECT title FROM scenarios WHERE id = ?", (scenario_id,)); title = cursor.fetchone()[0]; conn.close()
    await callback.message.edit_text(f"📌 <b>{title}</b>\n\n✅ <b>Завершено!</b>", parse_mode="HTML"); await callback.answer("Готово!")

@dp.callback_query(F.data.startswith("cancel_"))
async def process_cancel(callback: types.CallbackQuery):
    scenario_id = int(callback.data.split("_")[1]); conn = sqlite3.connect(DB_PATH); cursor = conn.cursor()
    cursor.execute("SELECT selected_at FROM scenarios WHERE id = ?", (scenario_id,)); res = cursor.fetchone()
    if res and res[0]:
        if datetime.now() - datetime.strptime(res[0], "%Y-%m-%d %H:%M:%S.%f") > timedelta(hours=12):
            await callback.answer("Отмена доступна только 12 часов!", show_alert=True); conn.close(); return
    cursor.execute("UPDATE scenarios SET status = 'free', animator_id = NULL, selected_at = NULL WHERE id = ?", (scenario_id,))
    conn.commit(); cursor.execute("SELECT title FROM scenarios WHERE id = ?", (scenario_id,)); title = cursor.fetchone()[0]; conn.close()
    await callback.message.edit_text(f"📌 <b>{title}</b>\n\nСтатус: Свободен", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Выбрать", callback_data=f"select_{scenario_id}")]]), parse_mode="HTML")
    await callback.answer("Отменено.")

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