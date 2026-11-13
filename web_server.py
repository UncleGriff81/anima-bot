from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import os
import json
import aiohttp

app = FastAPI()

# Разрешаем MiniApp обращаться к этому серверу
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

# Определяем путь к базе данных
DB_PATH = '/data/anima.db' if os.path.exists('/data') else 'anima.db'

# Токен бота (берется из переменных окружения Railway)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

@app.get("/api/scenarios")
async def get_scenarios():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, description, status, animator_id, scenes_data, audio_file_id FROM scenarios ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()

    result = []
    for row in rows:
        result.append({
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "status": row[3],
            "animator_id": row[4],
            "scenes": json.loads(row[5]) if row[5] else [],
            "audio_id": row[6]
        })
    return {"scenarios": result}

@app.get("/api/my_scenarios/{user_id}")
async def get_my_scenarios(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT title, selected_at, completed_at, status FROM scenarios WHERE animator_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()

    result = []
    for row in rows:
        result.append({
            "title": row[0],
            "selected_at": row[1].split('.')[0] if row[1] else "", 
            "completed_at": row[2].split('.')[0] if row[2] else "В работе",
            "status": row[3]
        })
    return {"scenarios": result}

@app.get("/api/all_animators")
async def get_all_animators():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT animator_id FROM scenarios WHERE animator_id IS NOT NULL")
    rows = cursor.fetchall()
    conn.close()
    return {"animators": [row[0] for row in rows]}

@app.get("/api/image/{file_id}")
async def get_image(file_id: str):
    """Скачивает картинку с Telegram и отдаёт её браузеру напрямую"""
    if not BOT_TOKEN:
        return Response(content="Bot token not configured", status_code=500)
        
    async with aiohttp.ClientSession() as session:
        # 1. Получаем путь к файлу
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
        async with session.get(url) as response:
            data = await response.json()
            
        if not data.get("ok"):
            return Response(content="File not found", status_code=404)
            
        file_path = data["result"]["file_path"]
        
        # 2. Скачиваем сам файл
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        async with session.get(file_url) as file_response:
            if file_response.status != 200:
                return Response(content="Error downloading file", status_code=500)
            
            # Читаем байты и отдаём их клиенту
            file_bytes = await file_response.read()
            return Response(content=file_bytes, media_type="image/jpeg")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)