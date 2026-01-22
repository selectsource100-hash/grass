import os
import threading
import asyncio
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

# --- 1. WEB SERVER FOR RENDER ---
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running!", 200

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 2. TELEGRAM BOT LOGIC ---
API_TOKEN = '8103948431:AAEZgtxTZPA1tvuo8Lc6iA5-UZ7RFiqSzhs' # Get from @BotFather
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Simple memory database (Resets on restart)
# Tip: Connect Supabase or MongoDB later to save data permanently
user_db = {} 

@dp.message_handler(commands=['start'])
async def welcome(message: types.Message):
    uid = message.from_user.id
    if uid not in user_db:
        user_db[uid] = 5  # 5 Free credits for new users
    
    await message.reply(
        "🚀 **Premium Lead Finder Bot**\n\n"
        "Send a website URL to find business emails.\n"
        "Each search costs **1 credit**.\n\n"
        f"💰 Your Balance: {user_db[uid]} credits.\n"
        "Use /buy to get 50 credits for $5."
    )

@dp.message_handler(commands=['buy'])
async def buy_credits(message: types.Message):
    # In a real bot, integrate Stripe here. For now, manual payment:
    await message.reply("💳 To buy credits, send $5 to: `your@paypal.com` and message @admin.")

@dp.message_handler(regexp=r'(http|https)://[^\s]+')
async def find_leads(message: types.Message):
    uid = message.from_user.id
    balance = user_db.get(uid, 0)

    if balance >= 1:
        user_db[uid] -= 1
        url = message.text
        await message.answer(f"🔎 Searching {url} for leads...")
        
        # MOCK LOGIC: In a real bot, use a Lead API (like Hunter.io) here
        await asyncio.sleep(2) 
        await message.answer(
            f"✅ **Leads Found for {url}:**\n"
            "- admin@domain.com\n"
            "- sales@domain.com\n\n"
            f"Remaining Credits: {user_db[uid]}"
        )
    else:
        await message.answer("❌ Out of credits! Use /buy to top up.")

# --- 3. START EVERYTHING ---
if __name__ == '__main__':
    # Start Web Server in a background thread
    threading.Thread(target=run_web_server, daemon=True).start()
    
    # Start Telegram Bot Polling
    print("Bot is starting...")
    executor.start_polling(dp, skip_updates=True)
