import sqlite3

def init_db():
    conn = sqlite3.connect('anima.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            role TEXT DEFAULT 'animator'
        )
    ''')

    # Добавили поле scenes_count (кол-во сцен), scenes_data (текст и фото), audio_file_id
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
    print("База данных пересоздана с новыми полями.")

if __name__ == "__main__":
    init_db()