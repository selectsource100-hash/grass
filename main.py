import os
import random
import asyncio
import logging
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# --- CONFIG ---
BOT_TOKEN = "8103948431:AAEZgtxTZPA1tvuo8Lc6iA5-UZ7RFiqSzhs"
TELEGRAM_USERNAME = "@Str_JT"

# --- RENDER PORT BINDING ---
app = Flask(__name__)
@app.route('/')
def health(): return "BOT ACTIVE", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- GLOBAL STATE ---
stop_flags = {} 

# --- BOT SETUP ---
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- UI KEYBOARDS ---
def stop_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="STOP 🛑", callback_data="stop_process")]
    ])

# --- HANDLERS ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        f"💳 <b>JT Card Checker</b>\n\n"
        f"To check a list, upload a <code>.txt</code> file and reply to it with <code>/mtxt</code>.\n\n"
        f"Support: {TELEGRAM_USERNAME}"
    )

@dp.callback_query(F.data == "stop_process")
async def handle_stop(callback: CallbackQuery):
    stop_flags[callback.from_user.id] = True
    await callback.answer("Stopping current check...")

@dp.message(Command("mtxt"))
async def process_mtxt(message: Message):
    if not message.reply_to_message or not message.reply_to_message.document:
        return await message.answer("❌ Reply to a <code>.txt</code> file with /mtxt")

    uid = message.from_user.id
    stop_flags[uid] = False
    
    status_msg = await message.answer("🔄 <b>Preparing...</b>", reply_markup=stop_kb())

    # Result Counters
    live, charged, die = 0, 0, 0
    total = 20 # Example count

    for i in range(1, total + 1):
        if stop_flags.get(uid):
            await status_msg.edit_text(f"🛑 <b>Checking Stopped.</b>\n\nFinal Stats:\n✅ Live: {live}\n⚡ Charged: {charged}\n❌ Die: {die}")
            return

        # Mock logic for different results
        res = random.choice(["live", "charged", "die", "die"]) 
        if res == "live": live += 1
        elif res == "charged": charged += 1
        else: die += 1

        # Periodic UI Update
        if i % 2 == 0 or i == total:
            ui_text = (
                f"🔎 <b>Checking Cards...</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"✅ <b>Live:</b> <code>{live}</code>\n"
                f"⚡ <b>Charged:</b> <code>{charged}</code>\n"
                f"❌ <b>Declined:</b> <code>{die}</code>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"Progress: <code>{i}/{total}</code>"
            )
            try:
                await status_msg.edit_text(ui_text, reply_markup=stop_kb())
            except: pass # Avoid errors if message hasn't changed

        await asyncio.sleep(1.2) # Checker Delay

    await status_msg.edit_text(
        f"🏁 <b>Check Completed!</b>\n\n"
        f"✅ Live: <code>{live}</code>\n"
        f"⚡ Charged: <code>{charged}</code>\n"
        f"❌ Declined: <code>{die}</code>"
    )

# --- MAIN ---
async def main():
    threading.Thread(target=run_flask, daemon=True).start()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
