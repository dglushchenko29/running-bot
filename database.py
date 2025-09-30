import sqlite3
from datetime import datetime
from typing import Dict, List, Optional

class Database:
    def __init__(self, db_path: str = "running_bot.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Инициализация базы данных"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    first_name TEXT,
                    last_name TEXT,
                    username TEXT,
                    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица пробежек
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS runs (
                    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    distance REAL,
                    run_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            conn.commit()
    
    def user_exists(self, user_id: int) -> bool:
        """Проверяет, существует ли пользователь"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
            return cursor.fetchone() is not None
    
    def add_user(self, user_id: int, first_name: str, last_name: Optional[str] = None, username: Optional[str] = None):
        """Добавляет нового пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO users (user_id, first_name, last_name, username)
                VALUES (?, ?, ?, ?)
            ''', (user_id, first_name, last_name, username))
            conn.commit()
    
    def add_run(self, user_id: int, distance: float):
        """Добавляет пробежку"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO runs (user_id, distance)
                VALUES (?, ?)
            ''', (user_id, distance))
            conn.commit()
    
    def get_user_stats(self, user_id: int) -> Dict:
        """Возвращает статистику пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_runs,
                    COALESCE(SUM(distance), 0) as total_distance,
                    COALESCE(AVG(distance), 0) as average_distance,
                    COALESCE(MAX(distance), 0) as last_run_distance
                FROM runs 
                WHERE user_id = ?
            ''', (user_id,))
            
            result = cursor.fetchone()
            
            return {
                'total_runs': result[0],
                'total_distance': result[1],
                'average_distance': result[2],
                'last_run_distance': result[3]
            }
    
    def get_user_runs(self, user_id: int) -> List[Dict]:
        """Возвращает все пробежки пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT distance, run_date 
                FROM runs 
                WHERE user_id = ? 
                ORDER BY run_date DESC
            ''', (user_id,))
            
            runs = []
            for row in cursor.fetchall():
                runs.append({
                    'distance': row[0],
                    'run_date': row[1]
                })
            
            return runs
