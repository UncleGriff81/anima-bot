from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import json

app = FastAPI()

# Разрешаем MiniApp обращаться к этому серверу
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/my_scenarios/{user_id}")
async def get_my_scenarios(user_id: int):
    """Этот адрес будет возвращать таблицу для конкретного аниматора"""
    conn = sqlite3.connect('anima.db')
    cursor = conn.cursor()
    # Берем все ролики, которые взял этот пользователь
    cursor.execute("SELECT title, selected_at, completed_at, status FROM scenarios WHERE animator_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()

    result = []
    for row in rows:
        result.append({
            "title": row[0],
            "selected_at": row[1].split('.')[0] if row[1] else "", # Убираем микросекунды для красоты
            "completed_at": row[2].split('.')[0] if row[2] else "В работе",
            "status": row[3]
        })
    
    return {"scenarios": result}

@app.get("/api/all_animators")
async def get_all_animators():
    """Этот адрес будет возвращать общий список всех, кто брал ролики"""
    conn = sqlite3.connect('anima.db')
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT animator_id FROM scenarios WHERE animator_id IS NOT NULL")
    rows = cursor.fetchall()
    conn.close()
    return {"animators": [row[0] for row in rows]}

# Этот блок нужен только для локального запуска
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)