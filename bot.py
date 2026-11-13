import asyncio
import logging
import sqlite3
import json
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.markdown import hbold

# --- НАСТРОЙКИ ---
BOT_TOKEN = "9102167219:AAEMqwGo-ecnnR4SJeCVcSgcrRObYpf4FQs" # ВСТАВЬ СВОЙ ТОКЕН!

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- МАШИНА СОСТОЯНИЙ ---
class AddScenario(StatesGroup):
    title = State()
    description = State()
    scenes_count = State()
    scene_text = State()
    scene_photo = State()
    audio = State()

# --- КЛАВИАТУРЫ ---
cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
skip_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Пропустить ⏭")], [KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)

# --- ФУНКЦИЯ ДЛЯ ГЕНЕРАЦИИ КНОПОК УПРАВЛЕНИЯ ---
def get_control_buttons(scenario_id, selected_at_str):
    kb = [[InlineKeyboardButton(text="✅ Завершить", callback_data=f"complete_{scenario_id}")]]
    
    # Проверяем, прошло ли 12 часов с момента выбора
    if selected_at_str:
        selected_at = datetime.strptime(selected_at_str, "%Y-%m-%d %H:%M:%S.%f")
        if datetime.now() - selected_at < timedelta(hours=12):
            kb.append([InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_{scenario_id}")])
            
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- ФУНКЦИЯ ОТПРАВКИ ДЕТАЛЕЙ СЦЕНАРИЯ ---
async def send_scenario_details(target_message: types.Message, scenario_id: int, show_buttons=True):
    conn = sqlite3.connect('anima.db')
    cursor = conn.cursor()
    cursor.execute("SELECT title, description, scenes_data, audio_file_id, status FROM scenarios WHERE id = ?", (scenario_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        await target_message.answer("Сценарий не найден.")
        return

    title, description, scenes_json, audio_id, status = row
    
    await target_message.answer(f"🎬 {hbold(title)}\n\n📝 {hbold('Описание:')}\n{description}", parse_mode="HTML")

    if scenes_json:
        scenes = json.loads(scenes_json)
        for i, scene in enumerate(scenes, 1):
            caption = f"{hbold(f'Сцена {i}:')}\n{scene['text']}"
            if scene.get('photo'):
                await target_message.answer_photo(photo=scene['photo'], caption=caption, parse_mode="HTML")
            else:
                await target_message.answer(caption, parse_mode="HTML")

    if audio_id:
        await target_message.answer_audio(audio=audio_id, caption="🎵 Голосовое сопровождение")

    if show_buttons and status == 'free':
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выбрать этот сценарий", callback_data=f"select_{scenario_id}")]
        ])
        await target_message.answer("Готовы взять этот сценарий в работу?", reply_markup=kb)

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        f"Привет, {message.from_user.first_name}!\n"
        "Я — бот для управления сценариями Anima Tasks.\n\n"
        "/add_scenario — Добавить сценарий (Сценарист)\n"
        "/list_scenarios — Свободные сценарии (Аниматор)\n"
        "/my_scenarios — Мои ролики в работе"
    )

@dp.message(Command("add_scenario"))
async def add_scenario_start(message: types.Message, state: FSMContext):
    await message.answer("Шаг 1/5. Введите название ролика:", reply_markup=cancel_kb)
    await state.set_state(AddScenario.title)

@dp.message(AddScenario.title)
async def process_title(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена": return await cancel_add(message, state)
    await state.update_data(title=message.text)
    await message.answer("Шаг 2/5. Введите описание ролика:")
    await state.set_state(AddScenario.description)

@dp.message(AddScenario.description)
async def process_description(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена": return await cancel_add(message, state)
    await state.update_data(description=message.text)
    await message.answer("Шаг 3/5. Сколько будет сцен в ролике? (Напишите число)")
    await state.set_state(AddScenario.scenes_count)

@dp.message(AddScenario.scenes_count)
async def process_scenes_count(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена": return await cancel_add(message, state)
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите число.")
        return
    await state.update_data(scenes_count=int(message.text), current_scene=1, scenes=[])
    await message.answer(f"Шаг 4/5. Введите описание для Сцены №1:")
    await state.set_state(AddScenario.scene_text)

@dp.message(AddScenario.scene_text)
async def process_scene_text(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена": return await cancel_add(message, state)
    await state.update_data(current_scene_text=message.text)
    await message.answer("Прикрепите фото для этой сцены (или нажмите 'Пропустить ⏭'):", reply_markup=skip_kb)
    await state.set_state(AddScenario.scene_photo)

@dp.message(AddScenario.scene_photo)
async def process_scene_photo(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена": return await cancel_add(message, state)
    
    data = await state.get_data()
    scenes = data['scenes']
    photo_id = None

    if message.photo:
        photo_id = message.photo[-1].file_id
    elif message.text != "Пропустить ⏭":
        await message.answer("Пожалуйста, прикрепите фото или нажмите 'Пропустить ⏭'.")
        return

    scenes.append({"text": data['current_scene_text'], "photo": photo_id})
    current = data['current_scene']
    total = data['scenes_count']

    if current < total:
        await state.update_data(scenes=scenes, current_scene=current + 1)
        await message.answer(f"Введите описание для Сцены №{current + 1}:", reply_markup=cancel_kb)
        await state.set_state(AddScenario.scene_text)
    else:
        await state.update_data(scenes=scenes)
        await message.answer("Шаг 5/5. Прикрепите аудиофайл (или нажмите 'Пропустить ⏭'):", reply_markup=skip_kb)
        await state.set_state(AddScenario.audio)

@dp.message(AddScenario.audio)
async def process_audio(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена": return await cancel_add(message, state)
    
    audio_id = None
    if message.audio:
        audio_id = message.audio.file_id
    elif message.text != "Пропустить ⏭":
        await message.answer("Пожалуйста, прикрепите аудио или нажмите 'Пропустить ⏭'.")
        return

    data = await state.get_data()
    conn = sqlite3.connect('anima.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO scenarios (title, description, scenes_count, scenes_data, audio_file_id) VALUES (?, ?, ?, ?, ?)",
        (data['title'], data['description'], data['scenes_count'], json.dumps(data['scenes'], ensure_ascii=False), audio_id)
    )
    conn.commit()
    conn.close()

    await message.answer(f"✅ Сценарий «{data['title']}» успешно добавлен!", reply_markup=ReplyKeyboardRemove())
    await state.clear()

async def cancel_add(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Добавление отменено.", reply_markup=ReplyKeyboardRemove())

# --- СПИСОК СЦЕНАРИЕВ ---

@dp.message(Command("list_scenarios"))
async def list_scenarios(message: types.Message):
    conn = sqlite3.connect('anima.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM scenarios WHERE status = 'free'")
    scenarios = cursor.fetchall()
    conn.close()

    if not scenarios:
        await message.answer("Сейчас нет свободных сценариев.")
        return

    await message.answer(f"🎬 {hbold('Доступные сценарии:')}", parse_mode="HTML")
    for scenario in scenarios:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"Посмотреть «{scenario[1]}»", callback_data=f"view_{scenario[0]}")]
        ])
        await message.answer(f"📌 {scenario[1]}", reply_markup=kb)

@dp.callback_query(F.data.startswith("view_"))
async def process_view(callback: types.CallbackQuery):
    scenario_id = int(callback.data.split("_")[1])
    await callback.answer("Загружаю детали...")
    await send_scenario_details(callback.message, scenario_id, show_buttons=True)

@dp.callback_query(F.data.startswith("select_"))
async def process_select(callback: types.CallbackQuery):
    scenario_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    username = callback.from_user.username or callback.from_user.first_name
    
    conn = sqlite3.connect('anima.db')
    cursor = conn.cursor()
    cursor.execute("SELECT status, title FROM scenarios WHERE id = ?", (scenario_id,))
    result = cursor.fetchone()
    
    if result and result[0] == 'free':
        title = result[1]
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        cursor.execute(
            "UPDATE scenarios SET status = 'taken', animator_id = ?, selected_at = ? WHERE id = ?",
            (user_id, now_str, scenario_id)
        )
        conn.commit()
        
        text = f"📌 {hbold(title)}\n\n🔒 Выбрал: @{username}\nСтатус: В работе"
        kb = get_control_buttons(scenario_id, now_str)
        
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await callback.answer(f"Вы взяли сценарий «{title}»!")
    else:
        await callback.answer("Упс! Этот сценарий уже кто-то забрал.", show_alert=True)
    
    conn.close()

# --- МОИ РОЛИКИ ---

@dp.message(Command("my_scenarios"))
async def my_scenarios(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect('anima.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, selected_at FROM scenarios WHERE status = 'taken' AND animator_id = ?", (user_id,))
    scenarios = cursor.fetchall()
    conn.close()

    if not scenarios:
        await message.answer("У вас нет активных роликов в работе.")
        return

    await message.answer(f"📂 {hbold('Ваши ролики в работе:')}", parse_mode="HTML")
    for scenario in scenarios:
        # Передаем дату выбора в функцию, чтобы она решила, показывать ли кнопку отмены
        kb = get_control_buttons(scenario[0], scenario[2])
        await message.answer(f"📌 {hbold(scenario[1])}", reply_markup=kb, parse_mode="HTML")

# --- ЗАВЕРШЕНИЕ И ОТМЕНА ---

@dp.callback_query(F.data.startswith("complete_"))
async def process_complete(callback: types.CallbackQuery):
    scenario_id = int(callback.data.split("_")[1])
    conn = sqlite3.connect('anima.db')
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    cursor.execute("UPDATE scenarios SET status = 'completed', completed_at = ? WHERE id = ?", (now_str, scenario_id))
    conn.commit()
    cursor.execute("SELECT title FROM scenarios WHERE id = ?", (scenario_id,))
    title = cursor.fetchone()[0]
    conn.close()
    
    await callback.message.edit_text(f"📌 {hbold(title)}\n\n✅ Статус: {hbold('Завершено')}!", parse_mode="HTML")
    await callback.answer("Отлично! Работа сдана.")

@dp.callback_query(F.data.startswith("cancel_"))
async def process_cancel(callback: types.CallbackQuery):
    scenario_id = int(callback.data.split("_")[1])
    
    # Проверяем время еще раз (защита от взлома кнопки)
    conn = sqlite3.connect('anima.db')
    cursor = conn.cursor()
    cursor.execute("SELECT selected_at FROM scenarios WHERE id = ?", (scenario_id,))
    res = cursor.fetchone()
    
    if res and res[0]:
        selected_at = datetime.strptime(res[0], "%Y-%m-%d %H:%M:%S.%f")
        if datetime.now() - selected_at > timedelta(hours=12):
            await callback.answer("Отменить можно только в первые 12 часов!", show_alert=True)
            conn.close()
            return

    cursor.execute("UPDATE scenarios SET status = 'free', animator_id = NULL, selected_at = NULL WHERE id = ?", (scenario_id,))
    conn.commit()
    
    cursor.execute("SELECT title FROM scenarios WHERE id = ?", (scenario_id,))
    title = cursor.fetchone()[0]
    conn.close()
    
    text = f"📌 {hbold(title)}\n\nСтатус: Свободен"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Выбрать", callback_data=f"select_{scenario_id}")]
    ])
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer("Выбор отменен.")

async def main():
    print("Бот запущен и готов к работе...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен.")