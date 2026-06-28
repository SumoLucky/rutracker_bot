import os
import threading
import telebot
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Инициализация Flask
app = Flask(__name__)

# Инициализация бота
TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)


# --- ЗДЕСЬ ВАШИ ОБРАБОТЧИКИ БОТА ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Я работаю на Timeweb App Platform 🚀")


# Пример обработчика для OpenAI (если используете)
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    # Ваша логика с OpenAI
    bot.reply_to(message, f"Вы написали: {message.text}")


# --- ЗАПУСК БОТА В ОТДЕЛЬНОМ ПОТОКЕ ---
def run_bot():
    """Запускает бота в режиме polling в фоновом потоке"""
    print("🤖 Бот запускается...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)


# --- ЗАПУСК FLASK (для health-проверок) ---
@app.route('/health', methods=['GET'])
def health_check():
    """Эндпоинт для проверки работоспособности приложения"""
    return jsonify({"status": "ok", "message": "Bot is running"}), 200


@app.route('/webhook', methods=['POST'])
def webhook():
    """Опционально: если захотите переключиться на webhook"""
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return '', 403


# --- ТОЧКА ВХОДА ---
if __name__ == "__main__":
    # Запускаем бота в отдельном потоке (чтобы не блокировать Flask)
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Запускаем Flask-сервер
    print("🌐 Веб-сервер запускается на порту 8000...")
    app.run(host='0.0.0.0', port=8000, debug=False, threaded=True)