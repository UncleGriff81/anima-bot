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
            first_name TEXT,
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

    # Проверяем и добавляем недостающие колонки в таблицу users
    cursor.execute("PRAGMA table_info(users)")
    user_columns = [col[1] for col in cursor.fetchall()]
    
    if 'first_name' not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN first_name TEXT")
        print("Добавлена колонка first_name в таблицу users.")

    # Проверяем и добавляем недостающие колонки в таблицу scenarios
    cursor.execute("PRAGMA table_info(scenarios)")
    scenario_columns = [col[1] for col in cursor.fetchall()]
    
    if 'uploaded_at' not in scenario_columns:
        cursor.execute("ALTER TABLE scenarios ADD COLUMN uploaded_at TIMESTAMP")
    if 'work_link' not in scenario_columns:
        cursor.execute("ALTER TABLE scenarios ADD COLUMN work_link TEXT")

    conn.commit()
    conn.close()
    print(f"База данных инициализирована. Путь: {db_path}")

if __name__ == "__main__":
    init_db()