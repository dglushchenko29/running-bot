from flask import Flask
import threading
import os
from bot import main as run_bot

app = Flask(__name__)

@app.route('/')
def home():
    return "Бот работает! 🏃‍♂️"

@app.route('/health')
def health():
    return "OK"

def start_bot():
    run_bot()

if __name__ == '__main__':
    # Запускаем бота в фоновом потоке
    bot_thread = threading.Thread(target=start_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    # Получаем порт из переменной окружения Render
    port = int(os.environ.get('PORT', 10000))
    
    # Запускаем Flask сервер
    app.run(host='0.0.0.0', port=port)
