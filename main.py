import os
import time
import json
import requests
from flask import Flask, request
from threading import Thread
from datetime import datetime, timedelta
from pymongo import MongoClient
import hmac
import hashlib

# Configuration
BOT_TOKEN = "8046672909:AAHI4bFQF0lr9sf679btwKaPWm_N3XDuEhY"
ADMIN_IDS = [7504968899]
MONGO_URI = "mongodb+srv://<botuser>:<johntayler456>@cluster0.hheged6.mongodb.net/?appName=Cluster0"
NOWPAYMENTS_API_KEY = "WQZZBPD-G4MM7ZR-M1YTQ3Q-877VBHV"
NOWPAYMENTS_IPN_SECRET = "e/A/f2Guz17i8t8tayIWDq9JJGciMDfk"

# Pricing
MONTHLY_PRICE = 2.0  # $2 USDT per month
MAX_MONTHS = 12  # Can pay up to 1 year in advance

app = Flask(__name__)

# MongoDB Setup
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client['crypto_monitor_bot']
    users_col = db['users']
    payments_col = db['payments']
    pending_payments_col = db['pending_payments']
    print("✅ Connected to MongoDB")
except Exception as e:
    print(f"❌ MongoDB connection failed: {e}")
    db = None

# Available Coins
AVAILABLE_COINS = {
    'shiba-inu': '🐕 SHIB',
    'dogecoin': '🐶 DOGE',
    'litecoin': '🪙 Litecoin',
    'bitcoin': '₿ Bitcoin',
    'ethereum': 'Ξ Ethereum',
    'toncoin': '💎 TON',
    'binancecoin': '🔶 BNB',
    'solana': '◎ Solana',
    'cardano': '₳ Cardano',
    'polkadot': '⬤ Polkadot',
    'avalanche-2': '🔺 Avalanche',
    'chainlink': '🔗 Chainlink',
    'polygon': '🟣 Polygon',
    'ripple': '💧 XRP',
    'stellar': '⭐ Stellar',
    'monero': '🔒 Monero',
    'cosmos': '⚛️ Cosmos',
}

# Database Functions
def get_user(user_id):
    """Get user from database"""
    if not db:
        return None
    return users_col.find_one({'user_id': user_id})

def add_user(user_id, username):
    """Add new user to database"""
    if not db:
        return
    
    existing = get_user(user_id)
    if not existing:
        users_col.insert_one({
            'user_id': user_id,
            'username': username,
            'subscription_end': None,  # No active subscription
            'subscribed_coins': ['shiba-inu'],  # Free coin
            'joined_date': datetime.now().isoformat()
        })

def is_subscription_active(user_id):
    """Check if user has active premium subscription"""
    if user_id in ADMIN_IDS:
        return True
    
    user = get_user(user_id)
    if not user or not user.get('subscription_end'):
        return False
    
    # Parse subscription end date
    end_date = datetime.fromisoformat(user['subscription_end'])
    return datetime.now() < end_date

def get_subscription_end(user_id):
    """Get user's subscription end date"""
    user = get_user(user_id)
    if user and user.get('subscription_end'):
        return datetime.fromisoformat(user['subscription_end'])
    return None

def extend_subscription(user_id, months):
    """Extend user's subscription by X months"""
    if not db:
        return False
    
    user = get_user(user_id)
    if not user:
        return False
    
    # Get current end date or start from now
    current_end = user.get('subscription_end')
    if current_end:
        end_date = datetime.fromisoformat(current_end)
        # If already expired, start from now
        if end_date < datetime.now():
            end_date = datetime.now()
    else:
        end_date = datetime.now()
    
    # Add months
    new_end = end_date + timedelta(days=30 * months)
    
    users_col.update_one(
        {'user_id': user_id},
        {'$set': {'subscription_end': new_end.isoformat()}}
    )
    
    return True

def get_subscribed_coins(user_id):
    """Get user's subscribed coins"""
    user = get_user(user_id)
    if user:
        return user.get('subscribed_coins', ['shiba-inu'])
    return ['shiba-inu']

def update_subscribed_coins(user_id, coins):
    """Update user's coin list"""
    if not db:
        return
    users_col.update_one(
        {'user_id': user_id},
        {'$set': {'subscribed_coins': coins}}
    )

def is_admin(user_id):
    """Check if user is admin"""
    return user_id in ADMIN_IDS

# NOWPayments Integration
def create_payment(user_id, months):
    """Create payment via NOWPayments"""
    try:
        url = "https://api.nowpayments.io/v1/payment"
        headers = {
            'x-api-key': NOWPAYMENTS_API_KEY,
            'Content-Type': 'application/json'
        }
        
        amount = MONTHLY_PRICE * months
        order_id = f"{user_id}_{months}m_{int(time.time())}"
        
        data = {
            "price_amount": amount,
            "price_currency": "usd",
            "pay_currency": "usdttrc20",
            "ipn_callback_url": f"https://YOUR_RENDER_URL.onrender.com/nowpayments_webhook",
            "order_id": order_id,
            "order_description": f"{months} month(s) premium subscription"
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=10)
        
        if response.status_code == 201:
            payment_data = response.json()
            
            # Store pending payment
            if db:
                pending_payments_col.insert_one({
                    'payment_id': payment_data['payment_id'],
                    'user_id': user_id,
                    'months': months,
                    'amount': amount,
                    'status': 'waiting',
                    'created_at': datetime.now().isoformat()
                })
            
            return payment_data
        else:
            print(f"Payment creation failed: {response.text}")
            return None
            
    except Exception as e:
        print(f"Error creating payment: {e}")
        return None

def get_payment_status(payment_id):
    """Check payment status"""
    try:
        url = f"https://api.nowpayments.io/v1/payment/{payment_id}"
        headers = {'x-api-key': NOWPAYMENTS_API_KEY}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            return response.json()
        return None
        
    except Exception as e:
        print(f"Error checking payment: {e}")
        return None

# Crypto Price Functions
def get_crypto_prices(coin_ids):
    """Fetch crypto prices from CoinGecko"""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            'ids': ','.join(coin_ids),
            'vs_currencies': 'usd',
            'include_24hr_change': 'true'
        }
        response = requests.get(url, params=params, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Error fetching prices: {e}")
        return None

# Telegram Bot Functions
def send_message(chat_id, text, reply_markup=None):
    """Send Telegram message"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        if reply_markup:
            data['reply_markup'] = json.dumps(reply_markup)
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print(f"Error sending message: {e}")

def get_main_keyboard(user_id):
    """Generate main menu keyboard"""
    is_premium = is_subscription_active(user_id)
    
    keyboard = {
        'inline_keyboard': [
            [
                {'text': '📊 My Prices', 'callback_data': 'view_prices'},
                {'text': '💎 All Coins', 'callback_data': 'browse_coins'}
            ],
        ]
    }
    
    if is_premium:
        keyboard['inline_keyboard'].append([
            {'text': '⚙️ My Coins', 'callback_data': 'manage_coins'},
            {'text': '📅 Subscription', 'callback_data': 'sub_info'}
        ])
        keyboard['inline_keyboard'].append([
            {'text': '➕ Extend Premium', 'callback_data': 'extend'}
        ])
    else:
        keyboard['inline_keyboard'].append([
            {'text': '⭐ GET PREMIUM - $2/month', 'callback_data': 'get_premium'}
        ])
    
    if is_admin(user_id):
        keyboard['inline_keyboard'].append([
            {'text': '👑 Admin', 'callback_data': 'admin'}
        ])
    
    return keyboard

def get_duration_keyboard():
    """Generate subscription duration keyboard"""
    keyboard = {'inline_keyboard': [
        [
            {'text': '1️⃣ Month - $2', 'callback_data': 'buy_1'},
            {'text': '3️⃣ Months - $6', 'callback_data': 'buy_3'}
        ],
        [
            {'text': '6️⃣ Months - $12', 'callback_data': 'buy_6'},
            {'text': '🔥 1 YEAR - $24', 'callback_data': 'buy_12'}
        ],
        [{'text': '« Back to Menu', 'callback_data': 'main_menu'}]
    ]}
    
    return keyboard

def get_browse_coins_keyboard(page=0):
    """Generate browseable coin showcase with pagination"""
    coins_per_page = 6
    coin_list = list(AVAILABLE_COINS.items())
    total_pages = (len(coin_list) + coins_per_page - 1) // coins_per_page
    
    start_idx = page * coins_per_page
    end_idx = start_idx + coins_per_page
    page_coins = coin_list[start_idx:end_idx]
    
    keyboard = {'inline_keyboard': []}
    
    # Add coins for this page (2 per row)
    for i in range(0, len(page_coins), 2):
        row = []
        for j in range(2):
            if i + j < len(page_coins):
                coin_id, coin_name = page_coins[i + j]
                row.append({
                    'text': coin_name,
                    'callback_data': f'coin_info_{coin_id}'
                })
        keyboard['inline_keyboard'].append(row)
    
    # Pagination controls
    nav_row = []
    if page > 0:
        nav_row.append({'text': '⬅️ Prev', 'callback_data': f'browse_page_{page-1}'})
    
    nav_row.append({'text': f'📄 {page+1}/{total_pages}', 'callback_data': 'none'})
    
    if page < total_pages - 1:
        nav_row.append({'text': 'Next ➡️', 'callback_data': f'browse_page_{page+1}'})
    
    keyboard['inline_keyboard'].append(nav_row)
    keyboard['inline_keyboard'].append([{'text': '« Main Menu', 'callback_data': 'main_menu'}])
    
    return keyboard

def get_coins_keyboard(user_id):
    """Generate coin selection keyboard for premium users"""
    subscribed = get_subscribed_coins(user_id)
    
    keyboard = {'inline_keyboard': []}
    
    # Group into rows of 2
    coin_list = list(AVAILABLE_COINS.items())
    for i in range(0, len(coin_list), 2):
        row = []
        for j in range(2):
            if i + j < len(coin_list):
                coin_id, coin_name = coin_list[i + j]
                is_subscribed = coin_id in subscribed
                status = "✅" if is_subscribed else "➕"
                
                row.append({
                    'text': f"{status} {coin_name}",
                    'callback_data': f"toggle_{coin_id}"
                })
        keyboard['inline_keyboard'].append(row)
    
    keyboard['inline_keyboard'].append([
        {'text': '✅ Select All', 'callback_data': 'select_all'},
        {'text': '❌ Clear All', 'callback_data': 'clear_all'}
    ])
    keyboard['inline_keyboard'].append([{'text': '« Back to Menu', 'callback_data': 'main_menu'}])
    
    return keyboard

def get_coin_detail_keyboard(coin_id, user_id):
    """Generate keyboard for individual coin detail view"""
    is_premium = is_subscription_active(user_id)
    subscribed = get_subscribed_coins(user_id)
    is_monitoring = coin_id in subscribed
    
    keyboard = {'inline_keyboard': []}
    
    if is_premium:
        if is_monitoring:
            keyboard['inline_keyboard'].append([
                {'text': '✅ Monitoring ON', 'callback_data': f'toggle_{coin_id}'}
            ])
        else:
            keyboard['inline_keyboard'].append([
                {'text': '➕ Add to My Coins', 'callback_data': f'toggle_{coin_id}'}
            ])
    else:
        keyboard['inline_keyboard'].append([
            {'text': '🔒 Get Premium to Monitor', 'callback_data': 'get_premium'}
        ])
    
    keyboard['inline_keyboard'].append([
        {'text': '🔄 Refresh Price', 'callback_data': f'coin_info_{coin_id}'}
    ])
    keyboard['inline_keyboard'].append([
        {'text': '« Back to Coins', 'callback_data': 'browse_coins'}
    ])
    
    return keyboard

def format_prices(user_id):
    """Format price message"""
    coins = get_subscribed_coins(user_id)
    prices = get_crypto_prices(coins)
    
    if not prices:
        return "❌ Failed to fetch prices. Try again in a moment."
    
    is_premium = is_subscription_active(user_id)
    
    if is_premium:
        message = "💎 <b>Your Premium Portfolio</b>\n"
        message += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    else:
        message = "🆓 <b>Free Tier Prices</b>\n"
        message += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for coin_id in coins:
        if coin_id in prices:
            coin_name = AVAILABLE_COINS.get(coin_id, coin_id)
            price = prices[coin_id].get('usd', 0)
            change = prices[coin_id].get('usd_24h_change', 0)
            
            # Choose emoji based on change
            if change > 5:
                emoji = "🚀"
            elif change > 0:
                emoji = "🟢"
            elif change < -5:
                emoji = "📉"
            else:
                emoji = "🔴"
            
            # Format price appropriately
            if price < 0.000001:
                price_str = f"${price:.10f}"
            elif price < 0.01:
                price_str = f"${price:.8f}"
            elif price < 1:
                price_str = f"${price:.4f}"
            else:
                price_str = f"${price:,.2f}"
            
            # Format change
            change_str = f"{change:+.2f}%"
            
            message += f"{emoji} <b>{coin_name}</b>\n"
            message += f"    💰 {price_str}\n"
            message += f"    📊 24h: {change_str}\n\n"
    
    message += f"━━━━━━━━━━━━━━━━━━━━\n"
    message += f"<i>⏰ Updated: {datetime.now().strftime('%H:%M:%S')}</i>"
    
    if not is_premium:
        message += f"\n\n⭐ <b>Want more coins?</b>\nUpgrade to Premium for $2/month!"
    
    return message

def format_coin_detail(coin_id):
    """Format detailed view of a single coin"""
    prices = get_crypto_prices([coin_id])
    
    if not prices or coin_id not in prices:
        return "❌ Failed to fetch coin data"
    
    coin_name = AVAILABLE_COINS.get(coin_id, coin_id)
    price = prices[coin_id].get('usd', 0)
    change = prices[coin_id].get('usd_24h_change', 0)
    
    # Emoji based on performance
    if change > 10:
        trend = "🚀 STRONG RALLY"
    elif change > 5:
        trend = "📈 BULLISH"
    elif change > 0:
        trend = "🟢 UP"
    elif change > -5:
        trend = "🔴 DOWN"
    elif change > -10:
        trend = "📉 BEARISH"
    else:
        trend = "💥 HEAVY DUMP"
    
    # Format price
    if price < 0.000001:
        price_str = f"${price:.10f}"
    elif price < 0.01:
        price_str = f"${price:.8f}"
    elif price < 1:
        price_str = f"${price:.4f}"
    else:
        price_str = f"${price:,.2f}"
    
    message = f"<b>{coin_name}</b>\n"
    message += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    message += f"💰 <b>Price:</b> {price_str}\n\n"
    message += f"📊 <b>24h Change:</b> {change:+.2f}%\n"
    message += f"📈 <b>Trend:</b> {trend}\n\n"
    message += f"━━━━━━━━━━━━━━━━━━━━\n"
    message += f"<i>⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"
    
    return message

def handle_update(update):
    """Handle incoming Telegram update"""
    try:
        if 'message' in update:
            message = update['message']
            chat_id = message['chat']['id']
            user_id = message['from']['id']
            username = message['from'].get('username', 'Unknown')
            text = message.get('text', '')
            
            add_user(user_id, username)
            
            if text == '/start':
                is_premium = is_subscription_active(user_id)
                
                if is_premium:
                    end_date = get_subscription_end(user_id)
                    days_left = (end_date - datetime.now()).days
                    
                    welcome = f"""🎉 <b>Welcome Back, Premium Member!</b>

⭐ <b>PREMIUM STATUS: ACTIVE</b>
━━━━━━━━━━━━━━━━━━━━

📅 Valid Until: <b>{end_date.strftime('%b %d, %Y')}</b>
⏳ Days Remaining: <b>{days_left} days</b>

✅ Full access to all 17 coins
✅ Hourly price updates
✅ Customizable portfolio

Use the menu below to get started! 👇"""
                else:
                    welcome = f"""👋 <b>Welcome to Crypto Price Monitor!</b>

🤖 Your 24/7 crypto tracking companion

━━━━━━━━━━━━━━━━━━━━
🆓 <b>FREE FEATURES:</b>
• SHIB price monitoring
• Real-time updates

⭐ <b>PREMIUM - $2/MONTH:</b>
• All 17 cryptocurrencies
• Bitcoin, Ethereum, TON, BNB
• Litecoin, XRP, Cardano & more
• Custom portfolio tracking
• Hourly price alerts

💰 <b>PAYMENT:</b> USDT (TRC20)
⚡ <b>ACTIVATION:</b> Instant & automatic

━━━━━━━━━━━━━━━━━━━━

Ready to start? Tap below! 👇"""
                
                send_message(chat_id, welcome, get_main_keyboard(user_id))
            
            # Admin command to grant subscription
            elif text.startswith('/grant ') and is_admin(user_id):
                parts = text.split()
                if len(parts) == 3:
                    target_user = int(parts[1])
                    months = int(parts[2])
                    extend_subscription(target_user, months)
                    send_message(chat_id, f"✅ Granted {months} month(s) to user {target_user}")
        
        elif 'callback_query' in update:
            query = update['callback_query']
            chat_id = query['message']['chat']['id']
            user_id = query['from']['id']
            data = query['data']
            
            if data == 'none':
                pass  # Ignore placeholder buttons
            
            elif data == 'main_menu':
                send_message(chat_id, "📱 <b>Main Menu</b>\n\nChoose an option:", get_main_keyboard(user_id))
            
            elif data == 'view_prices':
                msg = format_prices(user_id)
                keyboard = get_main_keyboard(user_id)
                keyboard['inline_keyboard'].insert(0, [
                    {'text': '🔄 Refresh Prices', 'callback_data': 'view_prices'}
                ])
                send_message(chat_id, msg, keyboard)
            
            elif data == 'browse_coins' or data.startswith('browse_page_'):
                page = 0
                if data.startswith('browse_page_'):
                    page = int(data.replace('browse_page_', ''))
                
                msg = f"💎 <b>Browse All Cryptocurrencies</b>\n\n"
                msg += f"Tap any coin to see live price and details!\n"
                msg += f"Total coins available: <b>{len(AVAILABLE_COINS)}</b>"
                
                send_message(chat_id, msg, get_browse_coins_keyboard(page))
            
            elif data.startswith('coin_info_'):
                coin_id = data.replace('coin_info_', '')
                msg = format_coin_detail(coin_id)
                send_message(chat_id, msg, get_coin_detail_keyboard(coin_id, user_id))
            
            elif data == 'get_premium' or data == 'extend':
                msg = """⭐ <b>GET PREMIUM ACCESS</b>

━━━━━━━━━━━━━━━━━━━━

<b>💎 UNLOCK ALL FEATURES:</b>
✅ Monitor ALL 17 cryptocurrencies
✅ Bitcoin, Ethereum, TON, BNB
✅ Litecoin, XRP, Solana & more
✅ Custom portfolio selection
✅ Hourly price updates to your DMs
✅ Detailed coin statistics

━━━━━━━━━━━━━━━━━━━━

<b>💰 PRICING:</b>

🔹 1 Month  →  $2 USDT
🔹 3 Months  →  $6 USDT
🔹 6 Months  →  $12 USDT  
🔥 1 YEAR  →  $24 USDT  <i>(Best Value!)</i>

━━━━━━━━━━━━━━━━━━━━

💳 <b>Payment:</b> USDT (TRC20)
⚡ <b>Activation:</b> Instant & Automatic
🔒 <b>Secure:</b> Powered by NOWPayments

Select your plan below: 👇"""
                send_message(chat_id, msg, get_duration_keyboard())
            
            elif data.startswith('buy_'):
                months = int(data.replace('buy_', ''))
                amount = MONTHLY_PRICE * months
                
                payment = create_payment(user_id, months)
                
                if payment:
                    # Calculate savings for multi-month
                    duration_text = f"{months} month" if months == 1 else f"{months} months"
                    if months == 12:
                        duration_text = "1 YEAR 🔥"
                    
                    payment_msg = f"💳 <b>PAYMENT DETAILS</b>\n\n"
                    payment_msg += f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    payment_msg += f"📦 <b>Plan:</b> {duration_text}\n"
                    payment_msg += f"💰 <b>Total:</b> ${amount} USDT\n\n"
                    payment_msg += f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    payment_msg += f"<b>📍 SEND EXACTLY:</b>\n"
                    payment_msg += f"<code>{payment['pay_amount']}</code> USDT\n\n"
                    payment_msg += f"<b>📍 TO THIS ADDRESS:</b>\n"
                    payment_msg += f"<code>{payment['pay_address']}</code>\n\n"
                    payment_msg += f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    payment_msg += f"⚠️ <b>IMPORTANT:</b>\n"
                    payment_msg += f"• Use USDT on <b>TRON (TRC20)</b> network\n"
                    payment_msg += f"• Send exact amount shown above\n"
                    payment_msg += f"• Payment expires in 60 minutes\n\n"
                    payment_msg += f"⚡ <b>Activation:</b> Instant after 1 confirmation\n\n"
                    payment_msg += f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    payment_msg += f"<i>Payment ID: {payment['payment_id']}</i>"
                    
                    keyboard = {
                        'inline_keyboard': [
                            [{'text': '🔄 Check Payment Status', 'callback_data': f"check_{payment['payment_id']}"}],
                            [{'text': '❌ Cancel', 'callback_data': 'get_premium'}]
                        ]
                    }
                    
                    send_message(chat_id, payment_msg, keyboard)
                else:
                    send_message(chat_id, "❌ Failed to create payment. Please try again.", get_main_keyboard(user_id))
            
            elif data.startswith('check_'):
                payment_id = data.replace('check_', '')
                status = get_payment_status(payment_id)
                
                if status:
                    payment_status = status.get('payment_status', 'waiting')
                    
                    if payment_status == 'finished':
                        msg = "✅ <b>Payment Confirmed!</b>\n\nYour premium subscription is now active!"
                        send_message(chat_id, msg, get_main_keyboard(user_id))
                    elif payment_status in ['waiting', 'confirming']:
                        msg = "⏳ <b>Waiting for payment...</b>\n\nPlease complete payment. Confirmation takes 1-5 minutes."
                        keyboard = {
                            'inline_keyboard': [
                                [{'text': '🔄 Check Again', 'callback_data': f"check_{payment_id}"}],
                                [{'text': '« Back', 'callback_data': 'main_menu'}]
                            ]
                        }
                        send_message(chat_id, msg, keyboard)
                    else:
                        msg = f"❌ Payment status: {payment_status}\n\nContact admin if you paid."
                        send_message(chat_id, msg, get_main_keyboard(user_id))
            
            elif data == 'sub_info':
                end_date = get_subscription_end(user_id)
                if end_date:
                    days_left = (end_date - datetime.now()).days
                    hours_left = (end_date - datetime.now()).seconds // 3600
                    
                    msg = f"""📅 <b>YOUR SUBSCRIPTION</b>

━━━━━━━━━━━━━━━━━━━━

⭐ <b>Status:</b> ACTIVE ✅

📆 <b>Expires:</b>
{end_date.strftime('%B %d, %Y at %H:%M')}

⏳ <b>Time Remaining:</b>
<b>{days_left}</b> days, <b>{hours_left}</b> hours

━━━━━━━━━━━━━━━━━━━━

💡 <b>Tip:</b> Extend anytime to add more time!
Your new duration will stack on top of existing time."""
                else:
                    msg = "❌ No active subscription found"
                
                send_message(chat_id, msg, get_main_keyboard(user_id))
            
            elif data == 'manage_coins':
                if is_subscription_active(user_id):
                    subscribed_count = len(get_subscribed_coins(user_id))
                    msg = f"""⚙️ <b>MANAGE YOUR PORTFOLIO</b>

━━━━━━━━━━━━━━━━━━━━

Currently tracking: <b>{subscribed_count}/{len(AVAILABLE_COINS)}</b> coins

✅ Green checkmark = Currently monitoring
➕ Plus sign = Add to your list

Tap any coin to add/remove from tracking:"""
                    send_message(chat_id, msg, get_coins_keyboard(user_id))
                else:
                    msg = "🔒 <b>Premium Feature</b>\n\nUpgrade to Premium to customize your coin portfolio!"
                    send_message(chat_id, msg, get_main_keyboard(user_id))
            
            elif data.startswith('toggle_'):
                if is_subscription_active(user_id):
                    coin_id = data.replace('toggle_', '')
                    subscribed = get_subscribed_coins(user_id)
                    coin_name = AVAILABLE_COINS.get(coin_id, coin_id)
                    
                    if coin_id in subscribed:
                        if len(subscribed) > 1:
                            subscribed.remove(coin_id)
                            action_msg = f"➖ Removed {coin_name}"
                        else:
                            action_msg = f"⚠️ You must monitor at least 1 coin!"
                    else:
                        subscribed.append(coin_id)
                        action_msg = f"✅ Added {coin_name}"
                    
                    update_subscribed_coins(user_id, subscribed)
                    
                    subscribed_count = len(get_subscribed_coins(user_id))
                    msg = f"""⚙️ <b>MANAGE YOUR PORTFOLIO</b>

━━━━━━━━━━━━━━━━━━━━

{action_msg}

Currently tracking: <b>{subscribed_count}/{len(AVAILABLE_COINS)}</b> coins

✅ Green checkmark = Currently monitoring
➕ Plus sign = Add to your list

Tap any coin to add/remove from tracking:"""
                    send_message(chat_id, msg, get_coins_keyboard(user_id))
            
            elif data == 'select_all':
                if is_subscription_active(user_id):
                    all_coins = list(AVAILABLE_COINS.keys())
                    update_subscribed_coins(user_id, all_coins)
                    msg = f"""⚙️ <b>MANAGE YOUR PORTFOLIO</b>

━━━━━━━━━━━━━━━━━━━━

✅ All {len(AVAILABLE_COINS)} coins selected!

Currently tracking: <b>{len(AVAILABLE_COINS)}/{len(AVAILABLE_COINS)}</b> coins"""
                    send_message(chat_id, msg, get_coins_keyboard(user_id))
            
            elif data == 'clear_all':
                if is_subscription_active(user_id):
                    update_subscribed_coins(user_id, ['shiba-inu'])  # Keep at least one
                    msg = f"""⚙️ <b>MANAGE YOUR PORTFOLIO</b>

━━━━━━━━━━━━━━━━━━━━

🔄 Portfolio cleared! (Kept SHIB as minimum)

Currently tracking: <b>1/{len(AVAILABLE_COINS)}</b> coins"""
                    send_message(chat_id, msg, get_coins_keyboard(user_id))
            
            elif data == 'admin' and is_admin(user_id):
                if db:
                    total = users_col.count_documents({})
                    premium = users_col.count_documents({'subscription_end': {'$ne': None}})
                else:
                    total = 0
                    premium = 0
                
                msg = f"""👑 <b>Admin Panel</b>

📊 <b>Stats:</b>
• Total Users: {total}
• Premium Users: {premium}

<b>Commands:</b>
/grant USER_ID MONTHS

Example: /grant 123456789 1"""
                send_message(chat_id, msg, get_main_keyboard(user_id))
    
    except Exception as e:
        print(f"Error handling update: {e}")

def get_updates(offset=0):
    """Get updates from Telegram"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
        params = {'offset': offset, 'timeout': 30}
        response = requests.get(url, params=params, timeout=35)
        return response.json()
    except Exception as e:
        print(f"Error getting updates: {e}")
        return None

def delete_webhook():
    """Remove any existing webhook so polling works"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
        requests.get(url)
        print("✅ Webhook reset (Polling enabled)")
    except Exception as e:
        print(f"⚠️ Failed to reset webhook: {e}")

def check_expired_subscriptions():
    """Check and notify users with expiring subscriptions"""
    while True:
        try:
            if db:
                # Find users expiring in 3 days
                three_days = (datetime.now() + timedelta(days=3)).isoformat()
                expiring = users_col.find({
                    'subscription_end': {'$lte': three_days, '$gte': datetime.now().isoformat()}
                })
                
                for user in expiring:
                    end_date = datetime.fromisoformat(user['subscription_end'])
                    days_left = (end_date - datetime.now()).days
                    
                    if days_left in [3, 1]:  # Notify 3 days and 1 day before
                        msg = f"""⚠️ <b>Subscription Expiring Soon</b>

Your premium access expires in <b>{days_left} day(s)</b>

Renew now to keep full access!"""
                        
                        keyboard = {
                            'inline_keyboard': [[
                                {'text': '➕ Extend Subscription', 'callback_data': 'extend'}
                            ]]
                        }
                        
                        send_message(user['user_id'], msg, keyboard)
            
            time.sleep(86400)  # Check once per day
        except Exception as e:
            print(f"Error checking subscriptions: {e}")
            time.sleep(3600)

def send_price_updates():
    """Send hourly updates to premium users"""
    while True:
        try:
            if db:
                # Only send to active premium users
                users = users_col.find({
                    'subscription_end': {'$gte': datetime.now().isoformat()}
                })
                
                for user in users:
                    user_id = user['user_id']
                    message = format_prices(user_id)
                    send_message(user_id, message)
                    time.sleep(1)
            
            time.sleep(3600)
        except Exception as e:
            print(f"Error in price updates: {e}")
            time.sleep(60)

def bot_polling():
    """Main bot polling loop"""
    print("Bot started!")
    
    # FIX: Ensure we aren't fighting with a webhook
    delete_webhook()
    
    offset = 0
    
    while True:
        try:
            updates = get_updates(offset)
            if updates:
                if updates.get('ok'):
                    for update in updates.get('result', []):
                        handle_update(update)
                        offset = update['update_id'] + 1
                else:
                    # FIX: Print specific error if Telegram refuses connection
                    print(f"Telegram API Error: {updates.get('description')}")
                    time.sleep(5)
            else:
                time.sleep(1)
                
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)

@app.route('/')
def home():
    """Health check"""
    return "Crypto Monitor Bot Running! 🚀", 200

@app.route('/nowpayments_webhook', methods=['POST'])
def nowpayments_webhook():
    """Handle payment confirmations"""
    try:
        received_sig = request.headers.get('x-nowpayments-sig')
        payload = request.get_data()
        
        expected_sig = hmac.new(
            NOWPAYMENTS_IPN_SECRET.encode(),
            payload,
            hashlib.sha512
        ).hexdigest()
        
        if received_sig != expected_sig:
            return "Invalid signature", 403
        
        data = request.json
        payment_id = data.get('payment_id')
        payment_status = data.get('payment_status')
        
        if payment_status == 'finished':
            # Find pending payment
            if db:
                pending = pending_payments_col.find_one({'payment_id': payment_id})
                
                if pending:
                    user_id = pending['user_id']
                    months = pending['months']
                    
                    # Extend subscription
                    extend_subscription(user_id, months)
                    
                    # Mark as complete
                    pending_payments_col.update_one(
                        {'payment_id': payment_id},
                        {'$set': {'status': 'completed'}}
                    )
                    
                    # Notify user
                    end_date = get_subscription_end(user_id)
                    msg = f"""🎉 <b>Payment Confirmed!</b>

✅ Premium activated for {months} month(s)
📅 Valid until: {end_date.strftime('%Y-%m-%d')}

You now have access to all coins!"""
                    
                    send_message(user_id, msg, get_main_keyboard(user_id))
        
        return "OK", 200
        
    except Exception as e:
        print(f"Webhook error: {e}")
        return "Error", 500

if __name__ == '__main__':
    # 1. Start Subscription Checker in background
    print("⏳ Starting Subscription Checker...")
    sub_check_thread = Thread(target=check_expired_subscriptions)
    sub_check_thread.daemon = True
    sub_check_thread.start()
    
    # 2. Start Price Updates in background
    print("📊 Starting Price Updates...")
    update_thread = Thread(target=send_price_updates)
    update_thread.daemon = True
    update_thread.start()
    
    # 3. Start Telegram Bot Polling in background
    print("🚀 Starting Telegram Bot...")
    bot_thread = Thread(target=bot_polling)
    bot_thread.daemon = True
    bot_thread.start()

    # 4. RUN FLASK ON THE MAIN THREAD (This blocks the script and keeps it alive)
    print("🌐 Starting Flask Server on Port 10000...")
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
