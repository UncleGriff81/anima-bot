from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import os
import json
import aiohttp
from datetime import datetime, timedelta
from io import BytesIO

# Импорты для PDF
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = '/data/anima.db' if os.path.exists('/data') else 'anima.db'
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Регистрируем шрифт с поддержкой кириллицы
# (на Railway часто есть DejaVuSans, но на всякий случай используем стандартный Helvetica, если что-то пойдет не так)
try:
    pdfmetrics.registerFont(TTFont('DejaVu', 'DejaVuSans.ttf'))
    FONT_NAME = 'DejaVu'
except:
    FONT_NAME = 'Helvetica'

def get_period_name(date_str):
    if not date_str: return "Без периода"
    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    day, month, year = dt.day, dt.month, dt.year
    if 3 <= day <= 15:
        return f"с 03.{month:02d} по 15.{month:02d}"
    elif 16 <= day <= 31:
        next_month = month + 1
        if next_month > 12: next_month = 1
        return f"с 16.{month:02d} по 02.{next_month:02d}"
    else:
        prev_month = month - 1
        if prev_month < 1: prev_month = 12
        return f"с 16.{prev_month:02d} по 02.{month:02d}"

@app.get("/api/scenarios")
async def get_scenarios():
    conn = sqlite3.connect(DB_PATH); cursor = conn.cursor()
    cursor.execute("SELECT id, title, description, status, animator_id, scenes_data, audio_file_id, work_link FROM scenarios ORDER BY id DESC")
    rows = cursor.fetchall(); conn.close()
    result = []
    for row in rows:
        result.append({"id": row[0], "title": row[1], "description": row[2], "status": row[3], "animator_id": row[4], "scenes": json.loads(row[5]) if row[5] else [], "audio_id": row[6], "work_link": row[7]})
    return {"scenarios": result}

@app.get("/api/users")
async def get_users():
    conn = sqlite3.connect(DB_PATH); cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, first_name, role FROM users ORDER BY role")
    rows = cursor.fetchall(); conn.close()
    result = []
    for row in rows:
        result.append({"id": row[0], "username": row[1], "first_name": row[2], "role": row[3]})
    return {"users": result}

@app.post("/api/select_scenario/{scenario_id}")
async def select_scenario(scenario_id: int, user_id: int):
    conn = sqlite3.connect(DB_PATH); cursor = conn.cursor()
    cursor.execute("SELECT status FROM scenarios WHERE id = ?", (scenario_id,))
    res = cursor.fetchone()
    if not res or res[0] != 'free':
        conn.close(); return {"error": "Сценарий уже занят или не найден"}
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    cursor.execute("UPDATE scenarios SET status = 'taken', animator_id = ?, selected_at = ? WHERE id = ?", (user_id, now_str, scenario_id))
    conn.commit(); conn.close(); return {"success": True}

@app.post("/api/cancel_scenario/{scenario_id}")
async def cancel_scenario(scenario_id: int, user_id: int):
    conn = sqlite3.connect(DB_PATH); cursor = conn.cursor()
    cursor.execute("SELECT status, animator_id, selected_at FROM scenarios WHERE id = ?", (scenario_id,))
    res = cursor.fetchone()
    if not res or res[0] != 'taken' or res[1] != user_id:
        conn.close(); return {"error": "Вы не можете отменить этот сценарий"}
    if res[2]:
        selected_at = datetime.strptime(res[2], "%Y-%m-%d %H:%M:%S.%f")
        if datetime.now() - selected_at > timedelta(hours=12):
            conn.close(); return {"error": "Отменить можно только в первые 12 часов"}
    cursor.execute("UPDATE scenarios SET status = 'free', animator_id = NULL, selected_at = NULL WHERE id = ?", (scenario_id,))
    conn.commit(); conn.close(); return {"success": True}

@app.post("/api/complete_scenario/{scenario_id}")
async def complete_scenario(scenario_id: int, user_id: int):
    conn = sqlite3.connect(DB_PATH); cursor = conn.cursor()
    cursor.execute("SELECT status, animator_id FROM scenarios WHERE id = ?", (scenario_id,))
    res = cursor.fetchone()
    if not res or res[0] != 'taken' or res[1] != user_id:
        conn.close(); return {"error": "Вы не можете завершить этот сценарий"}
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    cursor.execute("UPDATE scenarios SET status = 'completed', completed_at = ? WHERE id = ?", (now_str, scenario_id))
    conn.commit(); conn.close(); return {"success": True}

@app.post("/api/upload_work/{scenario_id}")
async def upload_work(scenario_id: int, work_link: str = ""):
    conn = sqlite3.connect(DB_PATH); cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    cursor.execute("UPDATE scenarios SET uploaded_at = ?, work_link = ? WHERE id = ?", (now_str, work_link, scenario_id))
    conn.commit(); conn.close(); return {"success": True}

@app.get("/api/my_scenarios/{user_id}")
async def get_my_scenarios(user_id: int):
    conn = sqlite3.connect(DB_PATH); cursor = conn.cursor()
    cursor.execute("SELECT title, selected_at, completed_at, status, uploaded_at FROM scenarios WHERE animator_id = ?", (user_id,))
    rows = cursor.fetchall(); conn.close()
    result = []
    for row in rows:
        title = row[0]
        selected_at_str = row[1].split('.')[0] if row[1] else ""
        completed_at_str = row[2].split('.')[0] if row[2] else "В работе"
        status = row[3]
        uploaded_at_str = row[4].split('.')[0] if row[4] else ""
        period_date_str = uploaded_at_str if uploaded_at_str else selected_at_str
        period_name = get_period_name(period_date_str)
        result.append({"title": title, "selected_at": selected_at_str, "completed_at": completed_at_str, "uploaded_at": uploaded_at_str, "status": status, "period": period_name})
    return {"scenarios": result}

@app.get("/api/avatar/{user_id}")
async def get_avatar(user_id: int):
    if not BOT_TOKEN: return Response(content="Bot token not configured", status_code=500)
    async with aiohttp.ClientSession() as session:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUserProfilePhotos?user_id={user_id}&limit=1"
        async with session.get(url) as response:
            data = await response.json()
        if not data.get("ok") or not data["result"]["photos"]:
            return Response(content="No avatar", status_code=404)
        file_id = data["result"]["photos"][0][-1]["file_id"]
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
        async with session.get(url) as response:
            data = await response.json()
        if not data.get("ok"): return Response(content="File not found", status_code=404)
        file_path = data["result"]["file_path"]
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        async with session.get(file_url) as file_response:
            if file_response.status != 200: return Response(content="Error", status_code=500)
            return Response(content=await file_response.read(), media_type="image/jpeg")

@app.get("/api/image/{file_id}")
async def get_image(file_id: str):
    if not BOT_TOKEN: return Response(content="Bot token not configured", status_code=500)
    async with aiohttp.ClientSession() as session:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
        async with session.get(url) as response:
            data = await response.json()
        if not data.get("ok"): return Response(content="File not found", status_code=404)
        file_path = data["result"]["file_path"]
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        async with session.get(file_url) as file_response:
            if file_response.status != 200: return Response(content="Error", status_code=500)
            return Response(content=await file_response.read(), media_type="image/jpeg")

@app.get("/api/audio/{file_id}")
async def get_audio(file_id: str):
    if not BOT_TOKEN: return Response(content="Bot token not configured", status_code=500)
    async with aiohttp.ClientSession() as session:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
        async with session.get(url) as response:
            data = await response.json()
        if not data.get("ok"): return Response(content="File not found", status_code=404)
        file_path = data["result"]["file_path"]
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        async with session.get(file_url) as file_response:
            if file_response.status != 200: return Response(content="Error", status_code=500)
            file_bytes = await file_response.read()
            headers = {"Content-Disposition": f'attachment; filename="{file_id}.mp3"'}
            return Response(content=file_bytes, media_type="audio/mpeg", headers=headers)

@app.get("/api/report")
async def generate_report(start_date: str, end_date: str):
    """Генерирует PDF-отчёт за период start_date - end_date (формат YYYY-MM-DD)"""
    try:
        # 1. Забираем данные из базы
        conn = sqlite3.connect(DB_PATH); cursor = conn.cursor()
        # Берем все сценарии, где дата выбора или загрузки попадает в диапазон
        query = """
            SELECT s.title, s.selected_at, s.completed_at, s.uploaded_at, u.username, u.first_name
            FROM scenarios s
            LEFT JOIN users u ON s.animator_id = u.user_id
            WHERE (s.selected_at >= ? AND s.selected_at <= ?)
               OR (s.uploaded_at >= ? AND s.uploaded_at <= ?)
            ORDER BY s.animator_id, s.selected_at
        """
        start_dt = f"{start_date} 00:00:00"
        end_dt = f"{end_date} 23:59:59"
        cursor.execute(query, (start_dt, end_dt, start_dt, end_dt))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return Response(content="Нет данных за выбранный период", status_code=404)

        # 2. Генерируем PDF
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        y = height - 20 * mm

        p.setFont(FONT_NAME, 16)
        p.drawString(20 * mm, y, f"Отчёт за период: {start_date} — {end_date}")
        y -= 15 * mm

        # Группируем по аниматору
        current_animator = None
        animator_titles = []

        for row in rows:
            title, selected_at, completed_at, uploaded_at, username, first_name = row
            # Формируем ключ аниматора
            animator_key = username if username else "Без аниматора"
            animator_name = f"{first_name} (@{username})" if username else "Без аниматора"

            if animator_key != current_animator:
                # Если это не первый аниматор, рисуем его таблицу
                if current_animator is not None:
                    y = draw_animator_block(p, y, width, current_animator, animator_titles)
                    if y < 30 * mm: # Новая страница
                        p.showPage()
                        y = height - 20 * mm
                current_animator = animator_key
                animator_titles = []
            
            animator_titles.append({
                "title": title,
                "selected_at": selected_at.split('.')[0] if selected_at else "",
                "completed_at": completed_at.split('.')[0] if completed_at else "В работе",
                "uploaded_at": uploaded_at.split('.')[0] if uploaded_at else ""
            })

        # Рисуем последнего аниматора
        if current_animator is not None:
            y = draw_animator_block(p, y, width, current_animator, animator_titles)

        p.save()
        pdf_bytes = buffer.getvalue()
        buffer.close()
        
        headers = {"Content-Disposition": f'attachment; filename="report_{start_date}_{end_date}.pdf"'}
        return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
    except Exception as e:
        return Response(content=f"Ошибка генерации PDF: {e}", status_code=500)

def draw_animator_block(p, y, width, animator_name, titles):
    """Рисует блок одного аниматора с таблицей"""
    # Заголовок аниматора
    p.setFont(FONT_NAME, 12)
    p.drawString(20 * mm, y, f"Аниматор: {animator_name}")
    y -= 7 * mm

    # Заголовки таблицы
    p.setFont(FONT_NAME, 10)
    p.drawString(20 * mm, y, "№")
    p.drawString(30 * mm, y, "Название ролика")
    p.drawString(110 * mm, y, "Взял в работу")
    p.drawString(150 * mm, y, "Сдал")
    y -= 5 * mm

    p.line(20 * mm, y, width - 20 * mm, y) # линия под заголовком
    y -= 5 * mm

    for idx, item in enumerate(titles, 1):
        p.setFont(FONT_NAME, 9)
        p.drawString(20 * mm, y, str(idx))
        # Обрезаем длинный текст
        title_text = item['title'][:40] + '...' if len(item['title']) > 40 else item['title']
        p.drawString(30 * mm, y, title_text)
        p.drawString(110 * mm, y, item['selected_at'])
        p.drawString(150 * mm, y, item['completed_at'])
        y -= 5 * mm
        
        if y < 20 * mm: # Если место кончается, переходим на новую страницу
            p.showPage()
            p.setFont(FONT_NAME, 10)
            y = A4[1] - 20 * mm

    y -= 10 * mm # Отступ между аниматорами
    return y

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)