import os
import logging
from typing import Dict, List, Optional
import sqlite3
from datetime import datetime

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.db_path = os.getenv('DATABASE_PATH', 'workouts.db')
        self.conn = self._get_connection()
        self._init_db()
        logger.info("✅ База данных инициализирована")
    
    def _get_connection(self):
        """Возвращает соединение с SQLite"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_db(self):
        """Инициализация базы данных"""
        try:
            cursor = self.conn.cursor()
            
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
            
            # Таблица пробежек - добавляем поле message_id для отслеживания сообщений
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS runs (
                    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    distance REAL,
                    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    message_id INTEGER,  -- ID сообщения в Telegram
                    original_date TIMESTAMP,  -- Оригинальная дата создания пробежки
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            self.conn.commit()
            logger.info("✅ Таблицы созданы/проверены")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации БД: {e}")
            raise
    
    def add_user(self, user_id: int, first_name: str, last_name: Optional[str] = None, username: Optional[str] = None):
        """Добавляет пользователя"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, first_name, last_name, username)
                VALUES (?, ?, ?, ?)
            ''', (user_id, first_name, last_name, username))
            self.conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка добавления пользователя: {e}")
    
    def add_run(self, user_id: int, distance: float, message_id: int = None):
        """Добавляет пробежку"""
        try:
            cursor = self.conn.cursor()
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute('''
                INSERT INTO runs (user_id, distance, message_id, original_date) 
                VALUES (?, ?, ?, ?)
            ''', (user_id, distance, message_id, current_time))
            self.conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"❌ Ошибка добавления пробежки: {e}")
            return None
    
    def find_run_by_message_id(self, user_id: int, message_id: int):
        """Находит пробежку по ID сообщения"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT run_id, distance, date FROM runs 
                WHERE user_id = ? AND message_id = ?
                ORDER BY date DESC LIMIT 1
            ''', (user_id, message_id))
            
            result = cursor.fetchone()
            if result:
                return {
                    'run_id': result[0],
                    'distance': result[1],
                    'date': result[2]
                }
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка поиска пробежки по message_id: {e}")
            return None
    
    def update_run(self, user_id: int, distance: float, message_id: int):
        """Обновляет пробежку по ID сообщения"""
        try:
            cursor = self.conn.cursor()
            
            # Находим пробежку по message_id
            run_data = self.find_run_by_message_id(user_id, message_id)
            
            if run_data:
                run_id = run_data['run_id']
                # Обновляем существующую запись
                cursor.execute('''
                    UPDATE runs SET distance = ?, date = CURRENT_TIMESTAMP 
                    WHERE run_id = ?
                ''', (distance, run_id))
                self.conn.commit()
                logger.info(f"✅ Обновлена пробежка {run_id} для пользователя {user_id}")
                return run_id
            else:
                # Если не нашли - создаем новую запись
                logger.info(f"Создаем новую пробежку для сообщения {message_id}")
                return self.add_run(user_id, distance, message_id)
                
        except Exception as e:
            logger.error(f"❌ Ошибка обновления пробежки: {e}")
            return None
    
    def get_user_stats(self, user_id: int) -> Dict:
        """Статистика пользователя"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) as total_runs, COALESCE(SUM(distance), 0) as total_distance
                FROM runs WHERE user_id = ?
            ''', (user_id,))
            
            result = cursor.fetchone()
            if result:
                total_runs = result[0]
                total_distance = float(result[1])
                return {
                    'total_runs': total_runs,
                    'total_distance': total_distance,
                    'average_distance': total_distance / max(total_runs, 1)
                }
            return {'total_runs': 0, 'total_distance': 0, 'average_distance': 0}
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики пользователя: {e}")
            return {'total_runs': 0, 'total_distance': 0, 'average_distance': 0}
    
    def get_week_stats(self) -> List[Dict]:
        """Статистика за неделю"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT u.first_name, u.username, COUNT(r.run_id) as runs_count, 
                       COALESCE(SUM(r.distance), 0) as total_distance
                FROM users u 
                JOIN runs r ON u.user_id = r.user_id
                WHERE r.date >= datetime('now', '-7 days')
                GROUP BY u.user_id, u.first_name, u.username
                ORDER BY total_distance DESC
            ''')
            
            stats = []
            for row in cursor.fetchall():
                stats.append({
                    'first_name': row[0],
                    'username': row[1],
                    'runs_count': row[2],
                    'total_distance': float(row[3])
                })
            return stats
        except Exception as e:
            logger.error(f"❌ Ошибка получения недельной статистики: {e}")
            return []
    
    def get_month_stats(self) -> List[Dict]:
        """Статистика за месяц"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT u.first_name, u.username, COUNT(r.run_id) as runs_count, 
                       COALESCE(SUM(r.distance), 0) as total_distance
                FROM users u 
                JOIN runs r ON u.user_id = r.user_id
                WHERE r.date >= datetime('now', '-30 days')
                GROUP BY u.user_id, u.first_name, u.username
                ORDER BY total_distance DESC
            ''')
            
            stats = []
            for row in cursor.fetchall():
                stats.append({
                    'first_name': row[0],
                    'username': row[1],
                    'runs_count': row[2],
                    'total_distance': float(row[3])
                })
            return stats
        except Exception as e:
            logger.error(f"❌ Ошибка получения месячной статистики: {e}")
            return []
    
    def get_all_stats(self):
        """Общая статистика всех пробежек"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT COUNT(*), SUM(distance) FROM runs')
            result = cursor.fetchone()
            return result
        except Exception as e:
            logger.error(f"❌ Ошибка получения общей статистики: {e}")
            return None
    
    def get_active_users_count(self):
        """Количество активных пользователей"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT COUNT(DISTINCT user_id) FROM runs')
            result = cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"❌ Ошибка получения количества активных пользователей: {e}")
            return 0
    
    def close(self):
        """Закрывает соединение с БД"""
        if self.conn:
            self.conn.close()