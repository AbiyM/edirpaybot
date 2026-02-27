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
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
# አስተዳዳሪዎችን ለመለየት (ለምሳሌ: 1062635928)
admin_env = os.getenv("ADMIN_IDS", "1062635928")
ADMIN_IDS = [int(id.strip()) for id in admin_env.replace(',', ' ').split()]
MINI_APP_URL = os.getenv("MINI_APP_URL")
TEST_GROUP_ID = os.getenv("TEST_GROUP_ID")
if TEST_GROUP_ID:
    TEST_GROUP_ID = int(TEST_GROUP_ID)

DB_FILE = 'edir_pro_final.db'

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN missing in .env file!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- 2. DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS members (
            user_id INTEGER PRIMARY KEY, 
            username TEXT, 
            full_name TEXT, 
            tier TEXT DEFAULT 'መሠረታዊ', 
            total_savings REAL DEFAULT 0, 
            joined_at TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            user_id INTEGER, 
            username TEXT, 
            gateway TEXT, 
            purpose TEXT, 
            period TEXT, 
            total_amount REAL, 
            penalty REAL DEFAULT 0, 
            pay_for_member TEXT, 
            file_id TEXT, 
            status TEXT DEFAULT 'AWAIT_APPROVAL', 
            timestamp TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            user_id INTEGER, 
            title TEXT, 
            message TEXT, 
            type TEXT, 
            timestamp TEXT
        )
    ''')
    conn.commit()
    conn.close()

# --- 3. RENDER STABILITY (HTTP SERVER) ---
async def handle_ping(request):
    return web.Response(text="EdirPay Bot (Python) is Active")

async def start_http_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.getenv("PORT", 3000)))
    await site.start()

# --- 4. BOT HANDLERS ---

def is_admin(user_id):
    return user_id in ADMIN_IDS

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
    
    if is_admin(message.from_user.id):
        builder.row(types.KeyboardButton(text="⚙️ የአስተዳዳሪ ሁነታ (Admin Mode)"))
    
    builder.row(types.KeyboardButton(text="📊 ሁኔታዬን እይ"), types.KeyboardButton(text="❓ እርዳታ"))
    
    await message.reply(
        f"እንኳን ወደ **እሁድን በፍቅር** መጡ! 👋 v25.2.2 (Python)\n\nእባክዎ ሚኒ አፑን በመክፈት የክፍያ ሪፖርትዎን ይላኩ።",
        reply_markup=builder.as_markup(resize_keyboard=True),
        parse_mode="Markdown"
    )

@dp.message(Command("id"))
async def cmd_id(message: types.Message):
    await message.reply(
        f"📌 **የቻት መረጃ**\n\n👤 ስም: *{message.chat.title or 'የግል ቻት'}*\n"
        f"🆔 ID: `{message.chat.id}`\n"
        f"🌐 ዓይነት: `{message.chat.type}`\n\n"
        f"💡 ይህንን ID በሬንደር ላይ በ `TEST_GROUP_ID` ቦታ ያስገቡት።",
        parse_mode="Markdown"
    )

@dp.message(F.content_type == types.ContentType.WEB_APP_DATA)
async def handle_webapp_data(message: types.Message):
    try:
        data = json.loads(message.web_app_data.data)
        if data.get('type') == 'payment_report':
            time_now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            
            # ለግሩፕ ማሳወቂያ መላክ
            if TEST_GROUP_ID:
                try:
                    await bot.send_message(
                        TEST_GROUP_ID,
                        f"🔔 **አዲስ የክፍያ ሪፖርት ደርሷል**\n\n"
                        f"👤 አባል: @{message.from_user.username or message.from_user.first_name}\n"
                        f"🎯 ዓላማ: {data['purpose']}\n"
                        f"💰 መጠን: {data['amount']} ብር\n"
                        f"💳 መንገድ: {data['gateway'].upper()}\n\n"
                        f"✅ አስተዳዳሪዎች እባካችሁ በግል ገብታችሁ አጽድቁ።",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logging.error(f"Group notification error: {e}")

            if data['gateway'] == 'manual':
                # ሴሽን ለመምሰል እዚህ ጋር ዳታውን ለጊዜው እናስቀምጣለን (ቀላል በሆነ መንገድ)
                # በእውነተኛ ስራ ላይ Redis ወይም FSM መጠቀም ይመከራል
                await message.answer(f"✅ የ{data['amount']} ብር መረጃ ተመዝግቧል። 📷 እባክዎ ደረሰኝዎን አሁን ይላኩ።")
                # ለቀላልነት ዳታውን በዴታቤዝ ውስጥ 'PENDING_FILE' ብለን እናስቀምጠዋለን
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO payments (user_id, username, gateway, purpose, period, total_amount, penalty, pay_for_member, status, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (message.from_user.id, message.from_user.username or 'N/A', data['gateway'], data['purpose'], data['period'], data['amount'], data['penalty'], data.get('payFor', 'self'), 'AWAITING_FILE', time_now))
                conn.commit()
                conn.close()
            else:
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO payments (user_id, username, gateway, purpose, period, total_amount, penalty, pay_for_member, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (message.from_user.id, message.from_user.username or 'N/A', data['gateway'], data['purpose'], data['period'], data['amount'], data['penalty'], data.get('payFor', 'self'), time_now))
                conn.commit()
                conn.close()
                await message.answer(f"🚀 የ{data['gateway'].upper()} ክፍያዎ ተመዝግቧል። ሲረጋገጥ እናሳውቆታለን።")
    except Exception as e:
        logging.error(f"WebAppData Error: {e}")

@dp.message(F.photo | F.document)
async def handle_receipt_upload(message: types.Message):
    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # ፋይል የሚጠባበቅ የመጨረሻ ክፍያ መፈለግ
    cursor.execute('SELECT id FROM payments WHERE user_id = ? AND status = "AWAITING_FILE" ORDER BY id DESC LIMIT 1', (message.from_user.id,))
    row = cursor.fetchone()
    
    if row:
        cursor.execute('UPDATE payments SET file_id = ?, status = "AWAIT_APPROVAL" WHERE id = ?', (file_id, row[0]))
        conn.commit()
        await message.answer("📩 ደረሰኝዎ ለፋይናንስ ኦፊሰር ተልኳል። እናመሰግናለን!")
    conn.close()

# --- 5. ADMIN ACTIONS ---

@dp.message(F.text == "⚙️ የአስተዳዳሪ ሁነታ (Admin Mode)")
async def admin_mode(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM payments WHERE status = "AWAIT_APPROVAL"')
    pending_count = cursor.fetchone()[0]
    conn.close()

    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text=f"📑 የሚጠባበቁ ክፍያዎች ({pending_count})"))
    builder.row(types.KeyboardButton(text="📈 አጠቃላይ ሪፖርት"), types.KeyboardButton(text="👤 ወደ አባልነት ተመለስ"))
    
    await message.answer("🛠 የአስተዳዳሪ መቆጣጠሪያ ማዕከል", reply_markup=builder.as_markup(resize_keyboard=True))

@dp.callback_query(F.data.startswith("app_") | F.data.startswith("rej_"))
async def process_approval(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("ፈቃድ የለዎትም!")
        return

    action, pay_id = callback.data.split("_")
    new_status = "APPROVED" if action == "app" else "REJECTED"
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, total_amount FROM payments WHERE id = ?', (pay_id,))
    payment = cursor.fetchone()
    
    if payment:
        cursor.execute('UPDATE payments SET status = ? WHERE id = ?', (new_status, pay_id))
        if action == "app":
            cursor.execute('UPDATE members SET total_savings = total_savings + ? WHERE user_id = ?', (payment[1], payment[0]))
            try:
                await bot.send_message(payment[0], f"✅ የ{payment[1]} ብር ክፍያዎ ተረጋግጦ ጽድቋል።")
            except: pass
        conn.commit()
    conn.close()

    await callback.message.edit_caption(caption=f"{callback.message.caption}\n\n🏁 **ውሳኔ:** {'✅ ጸድቋል' if action == 'app' else '❌ ውድቅ ተደርጓል'}")
    await callback.answer("ተጠናቋል")

# --- 6. MAIN ---
async def main():
    init_db()
    # የሬንደር ሰርቨርን እና ቦቱን በአንድ ላይ ማስነሳት
    await asyncio.gather(
        start_http_server(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())
