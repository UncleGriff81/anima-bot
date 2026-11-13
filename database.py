import sqlite3
import os

def init_db():
    # Если папка /data существует (на Railway), используем её. Иначе - текущую папку.
    db_path = '/data/anima.db' if os.path.exists('/data') else 'anima.db'
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            role TEXT DEFAULT 'animator'
        )
    ''')

    # Таблица сценариев
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
            completed_at TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()
    print(f"База данных инициализирована. Путь: {db_path}")

if __name__ == "__main__":
    init_db()