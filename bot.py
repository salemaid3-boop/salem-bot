import os
import threading
from flask import Flask
import telebot

TOKEN = os.environ.get("BOT_TOKEN", "حط_التوكن_هنا")
bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "اهلا بيك في روبوت سالم")

@bot.message_handler(func=lambda m: True)
def echo(message):
    bot.reply_to(message, f"وصلتني رسالتك: {message.text}")

print("البوت شغال...")
bot.infinity_polling()
