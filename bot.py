import os
import telebot

TOKEN = os.environ.get("BOT_TOKEN", "حط_التوكن_هنا")
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "اهلا بيك في روبوت سالم")

@bot.message_handler(func=lambda m: True)
def echo(message):
    bot.reply_to(message, f"وصلتني رسالتك: {message.text}")

print("البوت شغال...")
bot.infinity_polling()
