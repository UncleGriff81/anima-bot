from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import os
import json
import aiohttp
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = '/data/anima.db' if os.path.exists('/data') else 'anima.db'
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

@app.post("/api/select_scenario/{scenario_id}")
async def select_scenario(scenario_id: int, user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM scenarios WHERE id = ?", (scenario_id,))
    res = cursor.fetchone()
    
    if not res or res[0] != 'free':
        conn.close()
        return {"error": "Сценарий уже занят или не найден"}
        
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    cursor.execute(
        "UPDATE scenarios SET status = 'taken', animator_id = ?, selected_at = ? WHERE id = ?",
        (user_id, now_str, scenario_id)
    )
    conn.commit()
    conn.close()
    return {"success": True}

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
            # Заголовок для скачивания файла
            headers = {"Content-Disposition": f'attachment; filename="{file_id}.mp3"'}
            return Response(content=file_bytes, media_type="audio/mpeg", headers=headers)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)