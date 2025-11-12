import os
import logging
import sqlite3
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.db_path = 'workouts.db'
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()
        logger.info("✅ База данных инициализирована")
    
    def _init_db(self):
        """Инициализация базы данных"""
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
        
        # Таблица пробежек - ВАЖНО: используем date вместо created_at
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                distance REAL,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                message_id INTEGER,
                run_time TEXT,
                pace TEXT,
                run_time_seconds INTEGER,
                pace_seconds INTEGER,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        self.conn.commit()
        logger.info("✅ Таблицы созданы/проверены")
    
    def add_user(self, user_id: int, first_name: str, last_name: str = None, username: str = None):
        """Добавляет пользователя - УПРОЩЕННАЯ ВЕРСИЯ"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, first_name, last_name, username)
                VALUES (?, ?, ?, ?)
            ''', (user_id, first_name, last_name, username))
            self.conn.commit()
            logger.info(f"✅ Пользователь добавлен: {user_id} - {first_name}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка добавления пользователя {user_id}: {e}")
            return False
    
    def add_run(self, user_id: int, distance: float, run_time: str = None, pace: str = None, 
                run_time_seconds: int = None, pace_seconds: int = None):
        """Добавляет пробежку - ГАРАНТИРОВАННОЕ СОХРАНЕНИЕ"""
        try:
            cursor = self.conn.cursor()
            
            # ВАЖНО: Используем CURRENT_TIMESTAMP для автоматической даты
            cursor.execute('''
                INSERT INTO runs (user_id, distance, run_time, pace, run_time_seconds, pace_seconds)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, distance, run_time, pace, run_time_seconds, pace_seconds))
            
            self.conn.commit()
            run_id = cursor.lastrowid
            
            logger.info(f"✅ ПРОБЕЖКА СОХРАНЕНА: user_id={user_id}, distance={distance}, "
                       f"time={run_time}, pace={pace}, run_id={run_id}")
            
            return run_id
            
        except Exception as e:
            logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА СОХРАНЕНИЯ ПРОБЕЖКИ: {e}")
            # Пробуем еще раз с простым запросом
            try:
                cursor.execute('''
                    INSERT INTO runs (user_id, distance) VALUES (?, ?)
                ''', (user_id, distance))
                self.conn.commit()
                logger.info(f"✅ Пробежка сохранена (упрощенный запрос)")
                return cursor.lastrowid
            except Exception as e2:
                logger.error(f"❌ ПОЛНЫЙ СБОЙ БАЗЫ ДАННЫХ: {e2}")
                return None
    
    def get_user_stats(self, user_id: int):
        """Статистика пользователя"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) as total_runs, COALESCE(SUM(distance), 0) as total_distance
                FROM runs WHERE user_id = ?
            ''', (user_id,))
            
            result = cursor.fetchone()
            if result and result[0]:
                return {
                    'total_runs': result[0],
                    'total_distance': float(result[1])
                }
            return {'total_runs': 0, 'total_distance': 0}
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {'total_runs': 0, 'total_distance': 0}
    
    def get_weekly_top(self, days_back=7):
        """Получает топ бегунов за период - ИСПРАВЛЕННЫЙ ЗАПРОС"""
        try:
            cursor = self.conn.cursor()
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            logger.info(f"🔍 Поиск топа за период: {start_date} - {end_date}")
            
            # ВАЖНО: Используем date а не created_at
            cursor.execute('''
                SELECT 
                    u.first_name,
                    u.last_name,
                    u.username,
                    COUNT(r.run_id) as runs_count,
                    SUM(r.distance) as total_distance,
                    AVG(r.distance) as avg_distance
                FROM runs r
                JOIN users u ON r.user_id = u.user_id
                WHERE r.date >= ? AND r.date <= ?
                GROUP BY u.user_id
                ORDER BY total_distance DESC
                LIMIT 10
            ''', (start_date.strftime("%Y-%m-%d 00:00:00"), end_date.strftime("%Y-%m-%d 23:59:59")))
            
            results = cursor.fetchall()
            logger.info(f"📊 Найдено записей в топе: {len(results)}")
            
            return results, start_date, end_date
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения топа: {e}")
            return [], None, None
    
    def get_all_stats(self):
        """Общая статистика"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT COUNT(*), SUM(distance) FROM runs')
            result = cursor.fetchone()
            
            cursor.execute('SELECT COUNT(DISTINCT user_id) FROM runs')
            active_users = cursor.fetchone()[0]
            
            stats = {
                'total_runs': result[0] if result and result[0] else 0,
                'total_distance': float(result[1]) if result and result[1] else 0,
                'active_users': active_users
            }
            
            logger.info(f"📊 Общая статистика: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения общей статистики: {e}")
            return {'total_runs': 0, 'total_distance': 0, 'active_users': 0}
    
    def debug_info(self):
        """Отладочная информация о базе"""
        try:
            cursor = self.conn.cursor()
            
            # Все таблицы
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            # Пользователи
            cursor.execute("SELECT COUNT(*) FROM users")
            users_count = cursor.fetchone()[0]
            
            # Пробежки
            cursor.execute("SELECT COUNT(*) FROM runs")
            runs_count = cursor.fetchone()[0]
            
            # Последние пробежки
            cursor.execute("SELECT * FROM runs ORDER BY date DESC LIMIT 5")
            recent_runs = cursor.fetchall()
            
            return {
                'tables': tables,
                'users_count': users_count,
                'runs_count': runs_count,
                'recent_runs': recent_runs
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка отладки: {e}")
            return {}