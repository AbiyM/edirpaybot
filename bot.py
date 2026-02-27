import asyncio
import json
import logging
import os
import sqlite3
import random
import string
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.types import WebAppInfo
from dotenv import load_dotenv

# --- 1. CONFIGURATION ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_ID", "1062635928").replace(',', ' ').split()]
MINI_APP_URL = os.getenv("MINI_APP_URL")
TEST_GROUP_ID = int(os.getenv("TEST_GROUP_ID")) if os.getenv("TEST_GROUP_ID") else None
DB_FILE = 'edir_pro_final.db'

if not BOT_TOKEN:
    logger.critical("BOT_TOKEN አልተገኘም!")
    exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- 2. DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS members (
        user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, 
        total_savings REAL DEFAULT 0, joined_at TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, tx_id TEXT, user_id INTEGER, 
        username TEXT, gateway TEXT, purpose TEXT, period TEXT, 
        total_amount REAL, penalty REAL DEFAULT 0, guarantors TEXT,
        file_id TEXT, status TEXT DEFAULT 'PENDING', 
        processed_by TEXT, group_msg_id INTEGER, timestamp TEXT)''')
    conn.commit()
    conn.close()

def generate_tx_id():
    return "#EUDE" + ''.join(random.choices(string.digits, k=4))

# --- 3. RENDER STABILITY ---
async def handle_ping(request):
    return web.Response(text="EdirPay System is Online")

async def start_http_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', int(os.getenv("PORT", 3000))).start()

# --- 4. UI FORMATTERS ---
def format_status_msg(p, status_text, emoji):
    return (f"📋 **የክፍያ ሪፖርት {p['tx_id']}**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **አባል:** @{p['username']}\n"
            f"🎯 **ዓላማ:** {p['purpose']}\n"
            f"📅 **ጊዜ:** {p['period']}\n"
            f"💰 **መጠን:** {p['total_amount']} ብር\n"
            f"⚠️ **ቅጣት:** {p['penalty'] if float(p['penalty']) > 0 else 'የለም'}\n"
            f"🏦 **መንገድ:** {p['gateway'].upper()}\n"
            f"🛡 **ዋሶች:** {p['guarantors']}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{emoji} **ሁኔታ:** {status_text}")

# --- 5. HANDLERS ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO members (user_id, username, full_name, joined_at) VALUES (?, ?, ?, ?)',
                   (message.from_user.id, message.from_user.username or 'N/A', 
                    message.from_user.first_name, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()

    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="📱 ሚኒ አፑን ክፈት", web_app=WebAppInfo(url=MINI_APP_URL)))
    
    welcome_text = (f"ሰላም {message.from_user.first_name}! 👋\n"
                    f"እንኳን ወደ **እሁድን በፍቅር** ዲጂታል ዕድር በደህና መጡ።\n\n"
                    f"ከታች ያለውን አዝራር በመጫን የክፍያ ሪፖርት መላክ ይችላሉ።")
    
    await message.reply(welcome_text, reply_markup=builder.as_markup(resize_keyboard=True), parse_mode="Markdown")

@dp.message(F.content_type == types.ContentType.WEB_APP_DATA)
async def handle_webapp_data(message: types.Message):
    try:
        data = json.loads(message.web_app_data.data)
        if data.get('type') == 'payment_report':
            tx_id = generate_tx_id()
            guarantors = ", ".join([g for g in data.get('guarantors', []) if g]) or "የለም"
            
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute('''INSERT INTO payments (tx_id, user_id, username, gateway, purpose, period, total_amount, penalty, guarantors, status, timestamp)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                           (tx_id, message.from_user.id, message.from_user.username or message.from_user.first_name,
                            data['gateway'], data['purpose'], data['period'], data['amount'], data['penalty'], 
                            guarantors, 'WAITING_PHOTO', datetime.now().strftime("%Y-%m-%d %H:%M")))
            conn.commit()
            conn.close()

            # ተጠቃሚው የጠየቁት የአማርኛ መልዕክት
            await message.answer(f"✅ የ{data['amount']} ብር መረጃ ተመዝግቧል።\n\nእባክዎ እስኪጸድቅ (APPROVE) ድረስ ይጠብቁ።")
    except Exception as e:
        logger.error(f"Data error: {e}")

@dp.message(F.photo | F.document)
async def handle_receipt(message: types.Message):
    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM payments WHERE user_id = ? AND status = "WAITING_PHOTO" ORDER BY id DESC LIMIT 1', (message.from_user.id,))
    p = cursor.fetchone()
    
    if p:
        cursor.execute('UPDATE payments SET file_id = ?, status = "PENDING" WHERE id = ?', (file_id, p['id']))
        conn.commit()

        # ግሩፕ ላይ ማሳወቅ
        if TEST_GROUP_ID:
            report = format_status_msg(p, "በመጠባበቅ ላይ", "⏳")
            try:
                sent = await bot.send_message(TEST_GROUP_ID, report, parse_mode="Markdown")
                cursor.execute('UPDATE payments SET group_msg_id = ? WHERE id = ?', (sent.message_id, p['id']))
                conn.commit()
            except: pass

        # ለአስተዳዳሪ ማሳወቅ
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ አጽድቅ", callback_data=f"ok_{p['id']}")
        builder.button(text="❌ ውድቅ አድርግ", callback_data=f"no_{p['id']}")
        
        admin_cap = (f"🚨 **አዲስ የክፍያ ማረጋገጫ ጥያቄ**\n"
                     f"🆔 መለያ: `{p['tx_id']}`\n"
                     f"👤 አባል: @{p['username']}\n"
                     f"💰 መጠን: {p['total_amount']} ብር")
        
        for admin_id in ADMIN_IDS:
            try: await bot.send_photo(admin_id, file_id, caption=admin_cap, reply_markup=builder.as_markup(), parse_mode="Markdown")
            except: pass
        await message.answer(f"📩 ደረሰኝዎ ለፋይናንስ ኦፊሰር ደርሷል (መለያ፡ `{p['tx_id']}`)።")
    conn.close()

@dp.callback_query(F.data.startswith(("ok_", "no_")))
async def process_admin(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return await callback.answer("ፈቃድ የለዎትም!")

    action, pay_id = callback.data.split("_")
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM payments WHERE id = ?', (pay_id,))
    p = cursor.fetchone()
    
    if p and p['status'] == 'PENDING':
        admin_name = callback.from_user.first_name
        if action == "ok":
            cursor.execute('UPDATE payments SET status = "APPROVED", processed_by = ? WHERE id = ?', (admin_name, pay_id))
            cursor.execute('UPDATE members SET total_savings = total_savings + ? WHERE user_id = ?', (p['total_amount'], p['user_id']))
            u_msg = f"✅ **ክፍያዎ ጽድቋል!**\nመለያ፦ `{p['tx_id']}`\nየ{p['total_amount']} ብር ክፍያዎ ተረጋግጦ በቁጠባዎ ላይ ተጨምሯል።"
            s_txt, emoji = "ተረጋግጦ ጽድቋል", "✅"
        else:
            cursor.execute('UPDATE payments SET status = "REJECTED", processed_by = ? WHERE id = ?', (admin_name, pay_id))
            u_msg = f"❌ **ክፍያዎ ውድቅ ተደርጓል**\nመለያ፦ `{p['tx_id']}`\nደረሰኙ ትክክል ስላልሆነ እባክዎ ደግመው ይላኩ።"
            s_txt, emoji = "ውድቅ ተደርጓል", "❌"
        
        conn.commit()
        try: await bot.send_message(p['user_id'], u_msg, parse_mode="Markdown")
        except: pass

        if TEST_GROUP_ID and p['group_msg_id']:
            try: await bot.edit_message_text(format_status_msg(p, s_txt, emoji), TEST_GROUP_ID, p['group_msg_id'], parse_mode="Markdown")
            except: pass

        await callback.message.edit_caption(caption=f"{callback.message.caption}\n\n🏁 **ውሳኔ:** {s_txt}\n👤 **አስተዳዳሪ:** {admin_name}")
    
    await callback.answer("ተጠናቋል")
    conn.close()

async def main():
    init_db()
    await asyncio.gather(start_http_server(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())
