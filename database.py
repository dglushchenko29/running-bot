import os
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Пробуем импортировать PostgreSQL
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    POSTGRES_AVAILABLE = True
    logger.info("✅ PostgreSQL доступен")
except ImportError:
    POSTGRES_AVAILABLE = False
    logger.info("ℹ️ PostgreSQL недоступен, используем SQLite")

import sqlite3

class Database:
    def __init__(self):
        self.use_postgres = POSTGRES_AVAILABLE and os.getenv('DATABASE_URL')
        logger.info(f"🔄 Используется: {'PostgreSQL' if self.use_postgres else 'SQLite'}")
        self._init_db()
    
    def _get_connection(self):
        """Возвращает соединение с базой данных"""
        if self.use_postgres:
            return self._get_postgres_connection()
        else:
            return self._get_sqlite_connection()
    
    def _get_postgres_connection(self):
        """Соединение с PostgreSQL"""
        try:
            database_url = os.getenv('DATABASE_URL')
            if not database_url:
                raise Exception("DATABASE_URL не настроен")
            
            conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
            return conn
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к PostgreSQL: {e}")
            raise
    
    def _get_sqlite_connection(self):
        """Соединение с SQLite"""
        db_path = os.getenv('DATABASE_PATH', 'workouts.db')
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _execute_query(self, query: str, params=None):
        """Универсальный метод выполнения запроса"""
        try:
            if self.use_postgres:
                conn = self._get_postgres_connection()
                cursor = conn.cursor()
                cursor.execute(query, params or [])
                result = cursor.fetchall()
                conn.commit()
                conn.close()
                return result
            else:
                conn = self._get_sqlite_connection()
                cursor = conn.cursor()
                cursor.execute(query, params or [])
                result = cursor.fetchall()
                conn.commit()
                conn.close()
                return result
        except Exception as e:
            logger.error(f"❌ Ошибка выполнения запроса: {e}")
            logger.error(f"Запрос: {query}")
            logger.error(f"Параметры: {params}")
            return []
    
    def _init_db(self):
        """Инициализация базы данных"""
        try:
            # Таблица пользователей
            self._execute_query('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    first_name TEXT,
                    last_name TEXT,
                    username TEXT,
                    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица пробежек
            self._execute_query('''
                CREATE TABLE IF NOT EXISTS runs (
                    run_id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    distance REAL,
                    run_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # Таблица чатов
            self._execute_query('''
                CREATE TABLE IF NOT EXISTS chats (
                    chat_id BIGINT PRIMARY KEY,
                    chat_title TEXT,
                    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            logger.info("✅ База данных инициализирована")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации БД: {e}")
    
    def add_user(self, user_id: int, first_name: str, last_name: Optional[str] = None, username: Optional[str] = None):
        """Добавляет пользователя"""
        try:
            if self.use_postgres:
                self._execute_query('''
                    INSERT INTO users (user_id, first_name, last_name, username)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                ''', (user_id, first_name, last_name, username))
            else:
                self._execute_query('''
                    INSERT OR IGNORE INTO users (user_id, first_name, last_name, username)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, first_name, last_name, username))
        except Exception as e:
            logger.error(f"❌ Ошибка добавления пользователя: {e}")
    
    def add_run(self, user_id: int, distance: float):
        """Добавляет пробежку"""
        try:
            if self.use_postgres:
                self._execute_query('INSERT INTO runs (user_id, distance) VALUES (%s, %s)', (user_id, distance))
            else:
                self._execute_query('INSERT INTO runs (user_id, distance) VALUES (?, ?)', (user_id, distance))
        except Exception as e:
            logger.error(f"❌ Ошибка добавления пробежки: {e}")
    
    def get_user_stats(self, user_id: int) -> Dict:
        """Статистика пользователя"""
        try:
            result = self._execute_query('''
                SELECT COUNT(*) as total_runs, COALESCE(SUM(distance), 0) as total_distance
                FROM runs WHERE user_id = ?
            ''', (user_id,))
            
            if result:
                total_runs = result[0][0]
                total_distance = float(result[0][1])
                return {
                    'total_runs': total_runs,
                    'total_distance': total_distance,
                    'average_distance': total_distance / max(total_runs, 1)
                }
            return {'total_runs': 0, 'total_distance': 0, 'average_distance': 0}
        except:
            return {'total_runs': 0, 'total_distance': 0, 'average_distance': 0}
    
    def get_week_stats(self) -> List[Dict]:
        """Статистика за неделю"""
        try:
            if self.use_postgres:
                result = self._execute_query('''
                    SELECT u.first_name, u.username, COUNT(r.run_id) as runs_count, SUM(r.distance) as total_distance
                    FROM users u JOIN runs r ON u.user_id = r.user_id
                    WHERE r.run_date >= CURRENT_TIMESTAMP - INTERVAL '7 days'
                    GROUP BY u.user_id, u.first_name, u.username
                    ORDER BY total_distance DESC
                ''')
            else:
                result = self._execute_query('''
                    SELECT u.first_name, u.username, COUNT(r.run_id) as runs_count, SUM(r.distance) as total_distance
                    FROM users u JOIN runs r ON u.user_id = r.user_id
                    WHERE r.run_date >= datetime('now', '-7 days')
                    GROUP BY u.user_id
                    ORDER BY total_distance DESC
                ''')
            
            stats = []
            for row in result:
                if self.use_postgres:
                    stats.append({
                        'first_name': row['first_name'],
                        'username': row['username'],
                        'runs_count': row['runs_count'],
                        'total_distance': float(row['total_distance']) if row['total_distance'] else 0
                    })
                else:
                    stats.append({
                        'first_name': row[0],
                        'username': row[1],
                        'runs_count': row[2],
                        'total_distance': row[3] or 0
                    })
            return stats
        except:
            return []
    
    def get_month_stats(self) -> List[Dict]:
        """Статистика за месяц"""
        try:
            if self.use_postgres:
                result = self._execute_query('''
                    SELECT u.first_name, u.username, COUNT(r.run_id) as runs_count, SUM(r.distance) as total_distance
                    FROM users u JOIN runs r ON u.user_id = r.user_id
                    WHERE r.run_date >= CURRENT_TIMESTAMP - INTERVAL '30 days'
                    GROUP BY u.user_id, u.first_name, u.username
                    ORDER BY total_distance DESC
                ''')
            else:
                result = self._execute_query('''
                    SELECT u.first_name, u.username, COUNT(r.run_id) as runs_count, SUM(r.distance) as total_distance
                    FROM users u JOIN runs r ON u.user_id = r.user_id
                    WHERE r.run_date >= datetime('now', '-30 days')
                    GROUP BY u.user_id
                    ORDER BY total_distance DESC
                ''')
            
            stats = []
            for row in result:
                if self.use_postgres:
                    stats.append({
                        'first_name': row['first_name'],
                        'username': row['username'],
                        'runs_count': row['runs_count'],
                        'total_distance': float(row['total_distance']) if row['total_distance'] else 0
                    })
                else:
                    stats.append({
                        'first_name': row[0],
                        'username': row[1],
                        'runs_count': row[2],
                        'total_distance': row[3] or 0
                    })
            return stats
        except:
            return []
    
    def add_chat(self, chat_id: int, chat_title: str):
        """Добавляет чат"""
        try:
            if self.use_postgres:
                self._execute_query('''
                    INSERT INTO chats (chat_id, chat_title) VALUES (%s, %s)
                    ON CONFLICT (chat_id) DO UPDATE SET chat_title = EXCLUDED.chat_title
                ''', (chat_id, chat_title))
            else:
                self._execute_query('INSERT OR REPLACE INTO chats (chat_id, chat_title) VALUES (?, ?)', (chat_id, chat_title))
        except Exception as e:
            logger.error(f"❌ Ошибка добавления чата: {e}")
    
    def get_chats(self) -> List[int]:
        """Список чатов"""
        try:
            result = self._execute_query('SELECT chat_id FROM chats')
            return [row[0] for row in result]
        except:
            return []
