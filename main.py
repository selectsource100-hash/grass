import os
import random
import logging
import asyncio
import tempfile
import json
import threading
from typing import Dict, Tuple, Optional
from datetime import datetime
from flask import Flask

import aiohttp
import aiofiles
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ===================================================================
# Configuration
# ===================================================================

BOT_TOKEN = "8103948431:AAEZgtxTZPA1tvuo8Lc6iA5-UZ7RFiqSzhs"
ADMIN_IDS = [7248171018]  # Your ID
TELEGRAM_USERNAME = "@selectsource100" 

MAX_FILE_SIZE = 10 * 1024 * 1024 
MAX_CARDS_PER_FILE = 500000
DELAY_BETWEEN_CHECKS = 1.5
SESSION_TIMEOUT = 30
CREDITS_FILE = "credits.json"
RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)

# ===================================================================
# Flask Server for Render Port Binding
# ===================================================================
server = Flask(__name__)

@server.route('/')
def health():
    return "Bot is Running", 200

def run_server():
    port = int(os.environ.get("PORT", 10000))
    server.run(host='0.0.0.0', port=port)

# ===================================================================
# Credit System
# ===================================================================
def load_credits():
    if os.path.exists(CREDITS_FILE):
        with open(CREDITS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_credits(data):
    with open(CREDITS_FILE, 'w') as f:
        json.dump(data, f)

user_credits = load_credits()

# ===================================================================
# Limiter & Stop Logic
# ===================================================================
class UserLimiter:
    def __init__(self):
        self.user_processing = {}
        self.stop_requests = {}
    
    def is_processing(self, uid): return self.user_processing.get(uid, False)
    def set_processing(self, uid, state): 
        self.user_processing[uid] = state
        if not state: self.stop_requests[uid] = False
    def request_stop(self, uid): self.stop_requests[uid] = True
    def should_stop(self, uid): return self.stop_requests.get(uid, False)

limiter = UserLimiter()

# ===================================================================
# Card Logic
# ===================================================================
async def check_card(card_data: str) -> Tuple[str, str]:
    # Simplified mock for the gateway logic
    await asyncio.sleep(DELAY_BETWEEN_CHECKS)
    if random.random() > 0.8:
        return card_data, "✅ LIVE » Checked"
    return card_data, "❌ DIE » Declined"

# ===================================================================
# Bot Setup
# ===================================================================
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

@dp.callback_query(lambda c: c.data == "stop_check")
async def handle_stop(callback: CallbackQuery):
    limiter.request_stop(callback.from_user.id)
    await callback.answer("🛑 Stopping process...")

@dp.message(Command("start"))
async def cmd_start(message: Message):
    uid = str(message.from_user.id)
    bal = user_credits.get(uid, 0)
    await message.answer(
        f"💳 <b>JT Checkbot</b>\n\n"
        f"Your Credits: <code>{bal}</code>\n"
        f"To purchase credits, DM {TELEGRAM_USERNAME}\n\n"
        "/mtxt - Check file\n/check - Single CC"
    )

@dp.message(Command("setcredits"))
async def cmd_set(message: Message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        _, target, amt = message.text.split()
        user_credits[str(target)] = int(amt)
        save_credits(user_credits)
        await message.answer(f"✅ User {target} now has {amt} credits.")
    except: await message.answer("Use: /setcredits [ID] [Amount]")

@dp.message(Command("mtxt"))
async def cmd_mtxt(message: Message):
    uid = str(message.from_user.id)
    if user_credits.get(uid, 0) <= 0:
        return await message.answer(f"❌ Out of credits. DM {TELEGRAM_USERNAME}")
    
    if not message.reply_to_message or not message.reply_to_message.document:
        return await message.answer("Reply to a .txt file with /mtxt")

    limiter.set_processing(message.from_user.id, True)
    status_msg = await message.answer("⏳ Processing... (Click Stop to cancel)")
    
    # Process Logic (Deduct 1 credit per file)
    user_credits[uid] -= 1
    save_credits(user_credits)
    
    stop_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="STOP 🛑", callback_query_data="stop_check")]])
    await status_msg.edit_text("🔎 Checking cards...", reply_markup=stop_kb)
    
    # Simulating a loop that checks for 'should_stop'
    for i in range(10): 
        if limiter.should_stop(message.from_user.id):
            await message.answer("🛑 Checking Cancelled.")
            break
        await asyncio.sleep(1)

    await status_msg.edit_text("✅ Done.")
    limiter.set_processing(message.from_user.id, False)

async def main():
    threading.Thread(target=run_server, daemon=True).start()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
