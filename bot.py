import asyncio
import json
import logging
import os
import sqlite3
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.types import WebAppInfo
from dotenv import load_dotenv

# --- 1. CONFIGURATION & LOGGING ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
raw_admins = os.getenv("ADMIN_ID", "1062635928").replace(',', ' ').split()
ADMIN_IDS = [int(id.strip()) for id in raw_admins]
MINI_APP_URL = os.getenv("MINI_APP_URL")
TEST_GROUP_ID = os.getenv("TEST_GROUP_ID")
if TEST_GROUP_ID:
    TEST_GROUP_ID = int(TEST_GROUP_ID)

DB_FILE = 'edir_pro_final.db'

if not BOT_TOKEN:
    logger.critical("❌ BOT_TOKEN missing!")
    exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- 2. DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS members (
            user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, 
            total_savings REAL DEFAULT 0, joined_at TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, 
            gateway TEXT, purpose TEXT, period TEXT, total_amount REAL, 
            penalty REAL DEFAULT 0, pay_for_member TEXT, guarantors TEXT,
            file_id TEXT, status TEXT DEFAULT 'AWAIT_APPROVAL', 
            group_msg_id INTEGER, timestamp TEXT
        )
    ''')
    conn.commit()
    conn.close()

# --- 3. RENDER STABILITY ---
async def handle_ping(request):
    return web.Response(text="EdirPay Bot (Python) is Online")

async def start_http_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', int(os.getenv("PORT", 3000))).start()

# --- 4. UI HELPERS ---
def is_admin(user_id):
    return user_id in ADMIN_IDS

def format_group_report(p, status_emoji, status_text, reason=""):
    msg = (f"📋 **የክፍያ ሪፖርት**\n"
           f"━━━━━━━━━━━━━━━━━━\n"
           f"👤 **ከአባል:** @{p['username']}\n"
           f"🎯 **ዓላማ:** {p['purpose']}\n"
           f"📅 **ጊዜ:** {p['period']}\n"
           f"💰 **መጠን:** {p['total_amount']} ብር\n"
           f"⚠️ **ቅጣት:** {p['penalty'] if float(p['penalty']) > 0 else 'የለም'}\n"
           f"💳 **መንገድ:** {p['gateway'].upper()}\n"
           f"━━━━━━━━━━━━━━━━━━\n"
           f"{status_emoji} **ሁኔታ:** {status_text}")
    if reason:
        msg += f"\n📝 **ምክንያት:** {reason}"
    return msg

# --- 5. BOT HANDLERS ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO members (user_id, username, full_name, joined_at) VALUES (?, ?, ?, ?)',
                   (message.from_user.id, message.from_user.username or 'N/A', message.from_user.first_name, now))
    conn.commit()
    conn.close()

    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="📱 ሚኒ አፑን ክፈት", web_app=WebAppInfo(url=MINI_APP_URL)))
    if is_admin(message.from_user.id): builder.row(types.KeyboardButton(text="⚙️ የአስተዳዳሪ ሁነታ"))
    
    await message.reply(f"ሰላም {message.from_user.first_name}! 👋\nእንኳን ወደ **እሁድን በፍቅር** ዲጂታል ዕድር በደህና መጡ።",
                         reply_markup=builder.as_markup(resize_keyboard=True), parse_mode="Markdown")

@dp.message(F.content_type == types.ContentType.WEB_APP_DATA)
async def handle_webapp_data(message: types.Message):
    try:
        data = json.loads(message.web_app_data.data)
        if data.get('type') == 'payment_report':
            time_now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            guarantors = ", ".join([g for g in data.get('guarantors', []) if g]) or "የለም"
            
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO payments (user_id, username, gateway, purpose, period, total_amount, penalty, pay_for_member, guarantors, status, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (message.from_user.id, message.from_user.username or message.from_user.first_name, 
                  data['gateway'], data['purpose'], data['period'], data['amount'], 
                  data['penalty'], data.get('payFor', 'self'), guarantors, 'AWAITING_FILE', time_now))
            conn.commit()
            conn.close()
            await message.answer(f"✅ የ{data['amount']} ብር መረጃ ተመዝግቧል።\n\n📷 እባክዎ ደረሰኝዎን አሁን ይላኩ።")
    except Exception as e: logger.error(f"WebAppData Error: {e}")

@dp.message(F.photo | F.document)
async def handle_receipt_upload(message: types.Message):
    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM payments WHERE user_id = ? AND status = "AWAITING_FILE" ORDER BY id DESC LIMIT 1', (message.from_user.id,))
    pay_row = cursor.fetchone()
    
    if pay_row:
        p = {'id': pay_row[0], 'user_id': pay_row[1], 'username': pay_row[2], 'gateway': pay_row[3], 'purpose': pay_row[4], 
             'period': pay_row[5], 'total_amount': pay_row[6], 'penalty': pay_row[7], 'guarantors': pay_row[9]}
        
        cursor.execute('UPDATE payments SET file_id = ?, status = "AWAIT_APPROVAL" WHERE id = ?', (file_id, p['id']))
        conn.commit()

        # ግሩፕ ላይ ሪፖርት መላክ
        if TEST_GROUP_ID:
            report = format_group_report(p, "⏳", "በመጠባበቅ ላይ")
            try:
                sent = await bot.send_message(TEST_GROUP_ID, report, parse_mode="Markdown")
                cursor.execute('UPDATE payments SET group_msg_id = ? WHERE id = ?', (sent.message_id, p['id']))
                conn.commit()
            except Exception as e: logger.error(f"Group error: {e}")

        # ለአስተዳዳሪ መላክ
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ አጽድቅ", callback_data=f"app_{p['id']}")
        builder.button(text="❌ ውድቅ አድርግ", callback_data=f"rej_{p['id']}")
        
        for admin_id in ADMIN_IDS:
            try: await bot.send_photo(admin_id, file_id, caption=f"🚨 **አዲስ ክፍያ**\n👤 @{p['username']}\n💰 {p['total_amount']} ብር", 
                                        reply_markup=builder.as_markup(), parse_mode="Markdown")
            except: pass
        await message.answer("📩 ደረሰኝዎ ለፋይናንስ ኦፊሰር ተልኳል።")
    conn.close()

@dp.callback_query(F.data.startswith("app_") | F.data.startswith("rej_"))
async def process_approval(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return await callback.answer("ፈቃድ የለዎትም!")

    action, pay_id = callback.data.split("_")
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM payments WHERE id = ?', (pay_id,))
    p = cursor.fetchone()
    
    if p:
        if action == "app":
            cursor.execute('UPDATE payments SET status = "APPROVED" WHERE id = ?', (pay_id,))
            cursor.execute('UPDATE members SET total_savings = total_savings + ? WHERE user_id = ?', (p['total_amount'], p['user_id']))
            user_msg = f"✅ የ{p['total_amount']} ብር ክፍያዎ ጽድቋል።"
            status_txt, emoji, reason = "ተረጋግጦ ጽድቋል", "✅", ""
        else:
            cursor.execute('UPDATE payments SET status = "REJECTED" WHERE id = ?', (pay_id,))
            user_msg = f"❌ የ{p['total_amount']} ብር ክፍያዎ ውድቅ ተደርጓል። ደረሰኙ ግልጽ አይደለም።"
            status_txt, emoji, reason = "ውድቅ ተደርጓል", "❌", "ደረሰኙ ትክክል አይደለም"
        
        conn.commit()
        try: await bot.send_message(p['user_id'], user_msg)
        except: pass

        if TEST_GROUP_ID and p['group_msg_id']:
            updated_report = format_group_report(p, emoji, status_txt, reason)
            try: await bot.edit_message_text(updated_report, TEST_GROUP_ID, p['group_msg_id'], parse_mode="Markdown")
            except: pass

    await callback.message.edit_caption(caption=f"{callback.message.caption}\n\n🏁 **ውሳኔ:** {'✅ ጸድቋል' if action == 'app' else '❌ ውድቅ ተደርጓል'}")
    await callback.answer("ተጠናቋል")
    conn.close()

async def main():
    init_db()
    await asyncio.gather(start_http_server(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())
