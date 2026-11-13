import sqlite3
import os

def init_db():
    db_path = '/data/anima.db' if os.path.exists('/data') else 'anima.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            role TEXT DEFAULT 'animator'
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scenarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT,
            scenes_count INTEGER,
            scenes_data TEXT,
            audio_file_id TEXT,
            status TEXT DEFAULT 'free',
            animator_id INTEGER,
            selected_at TIMESTAMP,
            completed_at TIMESTAMP,
            uploaded_at TIMESTAMP,
            work_link TEXT
        )
    ''')

    # Проверяем, есть ли уже новые поля (если база старая, мы их добавим)
    cursor.execute("PRAGMA table_info(scenarios)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'uploaded_at' not in columns:
        cursor.execute("ALTER TABLE scenarios ADD COLUMN uploaded_at TIMESTAMP")
    if 'work_link' not in columns:
        cursor.execute("ALTER TABLE scenarios ADD COLUMN work_link TEXT")

    conn.commit()
    conn.close()
    print(f"База данных инициализирована. Путь: {db_path}")

if __name__ == "__main__":
    init_db()