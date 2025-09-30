import sqlite3
from datetime import datetime, timedelta
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
            
            # Таблица чатов для рассылки
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chats (
                    chat_id INTEGER PRIMARY KEY,
                    chat_title TEXT,
                    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                INSERT OR IGNORE INTO users (user_id, first_name, last_name, username)
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
                    COALESCE(AVG(distance), 0) as average_distance
                FROM runs 
                WHERE user_id = ?
            ''', (user_id,))
            
            result = cursor.fetchone()
            
            return {
                'total_runs': result[0],
                'total_distance': result[1],
                'average_distance': result[2]
            }
    
    def get_week_stats(self) -> List[Dict]:
        """Возвращает статистику за неделю"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    u.user_id,
                    u.first_name,
                    u.username,
                    COUNT(r.run_id) as runs_count,
                    SUM(r.distance) as total_distance
                FROM users u
                JOIN runs r ON u.user_id = r.user_id
                WHERE r.run_date >= datetime('now', '-7 days')
                GROUP BY u.user_id
                ORDER BY total_distance DESC
            ''')
            
            stats = []
            for row in cursor.fetchall():
                stats.append({
                    'user_id': row[0],
                    'first_name': row[1],
                    'username': row[2],
                    'runs_count': row[3],
                    'total_distance': row[4]
                })
            return stats
    
    def get_month_stats(self) -> List[Dict]:
        """Возвращает статистику за месяц"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    u.user_id,
                    u.first_name,
                    u.username,
                    COUNT(r.run_id) as runs_count,
                    SUM(r.distance) as total_distance
                FROM users u
                JOIN runs r ON u.user_id = r.user_id
                WHERE r.run_date >= datetime('now', '-30 days')
                GROUP BY u.user_id
                ORDER BY total_distance DESC
            ''')
            
            stats = []
            for row in cursor.fetchall():
                stats.append({
                    'user_id': row[0],
                    'first_name': row[1],
                    'username': row[2],
                    'runs_count': row[3],
                    'total_distance': row[4]
                })
            return stats
    
    def add_chat(self, chat_id: int, chat_title: str):
        """Добавляет чат для рассылки"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO chats (chat_id, chat_title)
                VALUES (?, ?)
            ''', (chat_id, chat_title))
            conn.commit()
    
    def get_chats(self) -> List[int]:
        """Возвращает список чатов для рассылки"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT chat_id FROM chats')
            return [row[0] for row in cursor.fetchall()]
