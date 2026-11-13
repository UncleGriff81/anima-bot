from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import os
import json
import aiohttp
from datetime import datetime, timedelta
from io import BytesIO

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

# --- НАСТРОЙКА ШРИФТОВ ---
FONT_NAME_REGULAR = 'Helvetica'
FONT_NAME_BOLD = 'Helvetica-Bold'
FONT_NAME_ITALIC = 'Helvetica-Oblique'

def register_fonts():
    global FONT_NAME_REGULAR, FONT_NAME_BOLD, FONT_NAME_ITALIC
    try:
        pdfmetrics.registerFont(TTFont('DejaVu', 'DejaVuSans.ttf'))
        FONT_NAME_REGULAR = 'DejaVu'
        pdfmetrics.registerFont(TTFont('DejaVu-Bold', 'DejaVuSans-Bold.ttf'))
        FONT_NAME_BOLD = 'DejaVu-Bold'
        pdfmetrics.registerFont(TTFont('DejaVu-Oblique', 'DejaVuSans-Oblique.ttf'))
        FONT_NAME_ITALIC = 'DejaVu-Oblique'
        pdfmetrics.registerFont(TTFont('DejaVu-BoldOblique', 'DejaVuSans-BoldOblique.ttf'))
        print("✅ Шрифты DejaVu зарегистрированы.")
    except Exception as e:
        print(f"❌ Ошибка регистрации шрифтов: {e}.")

register_fonts()

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

def get_group_name(date_str):
    """Определяет название подгруппы для отчёта"""
    if not date_str: return "Без даты"
    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    if 3 <= dt.day <= 15:
        return f"02.{dt.month:02d} — 15.{dt.month:02d}"
    else:
        if dt.day >= 16:
            next_month = dt.month + 1
            if next_month > 12: next_month = 1
            return f"16.{dt.month:02d} — 03.{next_month:02d}"
        else:
            prev_month = dt.month - 1
            if prev_month < 1: prev_month = 12
            return f"16.{prev_month:02d} — 03.{dt.month:02d}"

# ... (остальные API методы: /api/scenarios, /api/users, select, cancel, complete, upload, my_scenarios, avatar, image, audio) ...
# Они остаются без изменений, вставь их из предыдущего кода.

@app.get("/api/report")
async def generate_report(start_date: str, end_date: str):
    try:
        conn = sqlite3.connect(DB_PATH); cursor = conn.cursor()
        query = """
            SELECT s.title, s.selected_at, s.completed_at, s.uploaded_at, u.username, u.first_name
            FROM scenarios s
            LEFT JOIN users u ON s.animator_id = u.user_id
            WHERE (s.selected_at >= ? AND s.selected_at <= ?)
               OR (s.uploaded_at >= ? AND s.uploaded_at <= ?)
            ORDER BY u.first_name, s.selected_at
        """
        start_dt = f"{start_date} 00:00:00"
        end_dt = f"{end_date} 23:59:59"
        cursor.execute(query, (start_dt, end_dt, start_dt, end_dt))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return Response(content="Нет данных за выбранный период", status_code=404)

        # Группируем по аниматорам, внутри — по группам
        animators_data = {}
        for row in rows:
            title, selected_at, completed_at, uploaded_at, username, first_name = row
            date_for_period = uploaded_at if uploaded_at else selected_at
            group_name = get_group_name(date_for_period)
            
            animator_key = username if username else "Без аниматора"
            if animator_key not in animators_data:
                display = f"{first_name} (@{username})" if first_name and username else (f"@{username}" if username else "Без аниматора")
                animators_data[animator_key] = {
                    "display_name": display,
                    "groups": {}
                }
            
            if group_name not in animators_data[animator_key]["groups"]:
                animators_data[animator_key]["groups"][group_name] = []
            
            animators_data[animator_key]["groups"][group_name].append({
                "title": title,
                "selected_at": selected_at.split('.')[0] if selected_at else "",
                "completed_at": completed_at.split('.')[0] if completed_at else "В работе",
                "uploaded_at": uploaded_at.split('.')[0] if uploaded_at else ""
            })

        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        y = height - 20 * mm

        p.setFont(FONT_NAME_BOLD, 16)
        p.drawString(20 * mm, y, f"Отчёт за период: {start_date} — {end_date}")
        y -= 15 * mm

        for animator_key, data in animators_data.items():
            y = draw_animator_header(p, y, width, data["display_name"])
            for group_name, titles in data["groups"].items():
                y = draw_group_block(p, y, width, group_name, titles)
                if y < 30 * mm:
                    p.showPage()
                    y = height - 20 * mm
            y -= 5 * mm

        p.save()
        pdf_bytes = buffer.getvalue()
        buffer.close()
        
        headers = {"Content-Disposition": f'attachment; filename="report_{start_date}_{end_date}.pdf"'}
        return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
    except Exception as e:
        return Response(content=f"Ошибка генерации PDF: {e}", status_code=500)

def draw_animator_header(p, y, width, animator_name):
    """Рисует заголовок аниматора"""
    p.setFont(FONT_NAME_BOLD, 14)
    p.drawString(20 * mm, y, f"Аниматор: {animator_name}")
    y -= 8 * mm
    p.line(20 * mm, y, width - 20 * mm, y)
    y -= 5 * mm
    return y

def draw_group_block(p, y, width, group_name, titles):
    """Рисует подгруппу (например, '02.09 — 15.09') с таблицей роликов"""
    p.setFont(FONT_NAME_BOLD, 11)
    p.drawString(25 * mm, y, f"Период: {group_name}")
    y -= 6 * mm

    p.setFont(FONT_NAME_BOLD, 9)
    p.drawString(30 * mm, y, "№")
    p.drawString(40 * mm, y, "Название ролика")
    p.drawString(120 * mm, y, "Взял в работу")
    p.drawString(160 * mm, y, "Сдал")
    y -= 4 * mm

    for idx, item in enumerate(titles, 1):
        p.setFont(FONT_NAME_REGULAR, 8)
        p.drawString(30 * mm, y, str(idx))
        title_text = item['title'][:45] + '...' if len(item['title']) > 45 else item['title']
        p.drawString(40 * mm, y, title_text)
        
        p.setFont(FONT_NAME_ITALIC, 8)
        p.drawString(120 * mm, y, item['selected_at'])
        p.drawString(160 * mm, y, item['completed_at'])
        
        y -= 4 * mm
        
        if y < 20 * mm:
            p.showPage()
            p.setFont(FONT_NAME_BOLD, 9)
            p.drawString(30 * mm, y, "№")
            p.drawString(40 * mm, y, "Название ролика")
            p.drawString(120 * mm, y, "Взял в работу")
            p.drawString(160 * mm, y, "Сдал")
            y -= 4 * mm

    y -= 8 * mm
    return y

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)