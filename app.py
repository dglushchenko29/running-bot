from flask import Flask
import threading
from bot import main as run_bot

app = Flask(__name__)

@app.route('/')
def home():
    return "Бот работает! 🏃‍♂️"

@app.route('/health')
def health():
    return "OK"

# Запускаем бота в отдельном потоке
def start_bot():
    run_bot()

if __name__ == '__main__':
    # Запускаем бота в фоновом потоке
    bot_thread = threading.Thread(target=start_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    # Запускаем Flask сервер
    app.run(host='0.0.0.0', port=10000)
