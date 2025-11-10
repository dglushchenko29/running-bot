#!/usr/bin/env python3
import sqlite3
import os

def migrate_database():
    db_path = 'workouts.db'
    
    # Создаем резервную копию
    if os.path.exists(db_path):
        os.rename(db_path, 'workouts_backup.db')
        print("✅ Создана резервная копия БД")
    
    # Создаем новую БД
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            username TEXT,
            registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица пробежек с новыми полями
    cursor.execute('''
        CREATE TABLE runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            distance REAL,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            message_id INTEGER,
            original_date TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Новая БД создана с обновленной структурой")

if __name__ == "__main__":
    migrate_database()