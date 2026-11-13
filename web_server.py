from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import os
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = '/data/anima.db' if os.path.exists('/data') else 'anima.db'

@app.get("/api/scenarios")
async def get_scenarios():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Берем все нужные поля, включая сцены и аудио
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)