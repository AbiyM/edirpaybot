import os
import logging
import sqlite3
import json
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, MenuButtonWebApp
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# የአካባቢ ተለዋዋጮችን (Environment Variables) መጫን
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None
MINI_APP_URL = os.getenv("MINI_APP_URL")

# ለ Deep Linking የ URL ቅርጽን ማስተካከል (መጨረሻው ላይ / መኖሩን ማረጋገጥ)
if MINI_APP_URL and not MINI_APP_URL.endswith('/'):
    MINI_APP_URL += '/'

GROUP_ID = os.getenv("EDIR_GROUP_ID")

# ስህተቶችን ለመከታተል Logging ማስተካከል
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

# --- ዳታቤዝ ማዘጋጀት (Database Setup) ---
def init_db():
    """ዳታቤዙን እና አስፈላጊ ሰንጠረዦችን መፍጠር"""
    conn = sqlite3.connect("members.db")
    cursor = conn.cursor()
    # የአባላት ሰንጠረዥ
    cursor.execute('''CREATE TABLE IF NOT EXISTS members (
        user_id INTEGER PRIMARY KEY, 
        username TEXT, 
        status TEXT DEFAULT 'PENDING'
    )''')
    # የክፍያ ሪፖርቶች ሰንጠረዥ
    cursor.execute('''CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        user_id INTEGER, 
        username TEXT, 
        purpose TEXT, 
        location TEXT, 
        base_amount REAL, 
        penalty_amount REAL, 
        total_amount REAL, 
        note TEXT, 
        file_id TEXT, 
        status TEXT DEFAULT 'AWAIT_APPROVAL', 
        timestamp TEXT
    )''')
    conn.commit()
    conn.close()

# --- የደህንነት ፍተሻ (Group Access Check) ---
async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ተጠቃሚው የእድሩ ግሩፕ አባል መሆኑን ማረጋገጥ"""
    if not GROUP_ID or str(GROUP_ID) in ["YOUR_GROUP_ID", "-1001234567890", ""]:
        return True
    try:
        member = await context.bot.get_chat_member(chat_id=GROUP_ID, user_id=update.effective_user.id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
    except Exception as e:
        logging.warning(f"Membership check failed: {e}")
        return True # ስህተት ካጋጠመ ለጊዜው እንዲያልፍ ማድረግ
    
    await update.effective_message.reply_text("❌ ይቅርታ! ይህን ቦት ለመጠቀም መጀመሪያ የእሁድን በፍቅር የቴሌግራም ግሩፕ አባል መሆን አለብዎት።")
    return False

# --- የትዕዛዝ አስተናጋጆች (Command Handlers) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ቦቱን ማስጀመር እና ሜኑውን ወደ 'Open' መቀየር"""
    if not await check_membership(update, context): return
    
    # 1. የቆዩ የሜኑ ትዕዛዞችን ማጽዳት
    await context.bot.delete_my_commands()
    
    # 2. የግራውን ሜኑ ቁልፍ ወደ 'ክፈት (Open)' መቀየር
    await context.bot.set_chat_menu_button(
        chat_id=update.effective_chat.id,
        menu_button=MenuButtonWebApp(text="ክፈት (Open)", web_app=WebAppInfo(url=MINI_APP_URL))
    )

    user = update.effective_user
    conn = sqlite3.connect("members.db")
    conn.execute("INSERT OR IGNORE INTO members (user_id, username) VALUES (?, ?)", (user.id, user.username))
    conn.commit()
    conn.close()

    keyboard = [
        [InlineKeyboardButton("🚀 ክፍያ ያስገቡ (Pay)", web_app=WebAppInfo(url=f"{MINI_APP_URL}?startapp=pay"))],
        [InlineKeyboardButton("📊 ሁኔታዬን አሳይ", callback_data="user_status"), 
         InlineKeyboardButton("❓ እርዳታ", callback_data="user_help")]
    ]
    
    msg = (f"ሰላም {user.first_name}! 👋 ወደ **እሁድን በፍቅር** ቦት እንኳን ደህና መጡ።\n\n"
           "ከታች በግራ በኩል ያለውን **'ክፈት (Open)'** ቁልፍ በመጫን በማንኛውም ሰዓት አገልግሎቱን ማግኘት ይችላሉ።\n\n"
           "_Powered by Skymark System Solution_")
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """የአባሉን አጠቃላይ ሁኔታ ማሳየት"""
    if not await check_membership(update, context): return
    user_id = update.effective_user.id
    conn = sqlite3.connect("members.db")
    member = conn.execute("SELECT status FROM members WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    
    status_label = "✅ የጸደቀ አባል" if member and member[0] == 'APPROVED' else "⏳ በመጠባበቅ ላይ ያለ"
    msg = f"🔍 **የአባልነት ሁኔታዎ፦**\n\n{status_label}\n\nዝርዝር የሂሳብ መረጃ ለማየት 'ሁኔታ' የሚለውን ታብ በሚኒ አፑ ውስጥ ይመልከቱ።"
    
    if update.callback_query:
        await update.callback_query.message.reply_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """መመሪያ ማሳየት"""
    help_text = ("📖 **የአጠቃቀም መመሪያ**\n\n"
                 "1. 'ክፈት' የሚለውን በመጫን የክፍያ ፎርሙን ይሙሉ::\n"
                 "2. መረጃውን ልከው ሲጨርሱ የደረሰኝ ፎቶ (Screenshot) እዚህ ይላኩ::\n"
                 "3. **/status** በማለት ክፍያዎ መጽደቁን ያረጋግጡ::")
    if update.callback_query:
        await update.callback_query.message.reply_text(help_text, parse_mode="Markdown")
    else:
        await update.message.reply_text(help_text, parse_mode="Markdown")

async def pay_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ለክፍያ በቀጥታ የሚወስድ አቋራጭ"""
    keyboard = [[InlineKeyboardButton("🚀 ፎርሙን ክፈት", web_app=WebAppInfo(url=f"{MINI_APP_URL}?startapp=pay"))]]
    await update.message.reply_text("የክፍያ ሪፖርት ለማቅረብ ከታች ያለውን ቁልፍ ይጫኑ፡", reply_markup=InlineKeyboardMarkup(keyboard))

async def loan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ለብድር በቀጥታ የሚወስድ አቋራጭ"""
    keyboard = [[InlineKeyboardButton("🏦 የብድር አገልግሎት", web_app=WebAppInfo(url=f"{MINI_APP_URL}?startapp=loan"))]]
    await update.message.reply_text("ስለ ብድር መረጃ ለማግኘት ከታች ያለውን ቁልፍ ይጫኑ፡", reply_markup=InlineKeyboardMarkup(keyboard))

# --- የአስተዳዳሪ ተግባራት (Admin Tasks) ---

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ያልጸደቁ ክፍያዎችን ማየት (Admin Only)"""
    if update.effective_user.id != ADMIN_ID: return
    conn = sqlite3.connect("members.db")
    p_count = conn.execute("SELECT COUNT(*) FROM payments WHERE status = 'AWAIT_APPROVAL'").fetchone()[0]
    m_count = conn.execute("SELECT COUNT(*) FROM members").fetchone()[0]
    conn.close()
    await update.message.reply_text(f"🛠 **Admin Dashboard**\n\n• ጠቅላላ ተመዝጋቢዎች፦ {m_count}\n• ያልጸደቁ ክፍያዎች፦ {p_count}\n\nሪፖርት ለማየት /stats ይበሉ።")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """የፋይናንስ ማጠቃለያ (Admin Only)"""
    if update.effective_user.id != ADMIN_ID: return
    conn = sqlite3.connect("members.db")
    stats = conn.execute('SELECT SUM(total_amount) FROM payments WHERE status = "APPROVED"').fetchone()
    conn.close()
    total = stats[0] if stats[0] else 0
    await update.message.reply_text(f"💰 **ጠቅላላ በካዝና ያለ ገንዘብ፦**\n\n{total} ብር")

# --- የመረጃ አያያዝ (Data Handling) ---

async def on_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ከሚኒ አፑ የሚላክ መረጃን መቀበል"""
    data = json.loads(update.effective_message.web_app_data.data)
    user = update.effective_user

    if data.get('type') == 'payment_report':
        context.user_data['pending_pay'] = data
        await update.message.reply_text(f"✅ የ**{data['purpose']}** መረጃ ተመዝግቧል።\n\nአሁን የደረሰኝ ፎቶ (Image) እዚህ ይላኩ።")

async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ደረሰኝ ሲላክ ከዳታው ጋር አቀናጅቶ መመዝገብ"""
    if 'pending_pay' not in context.user_data:
        return await update.message.reply_text("እባክዎ መጀመሪያ በሚኒ አፑ በኩል መረጃ ይላኩ።")
    
    data = context.user_data['pending_pay']
    user = update.effective_user
    file_id = update.message.photo[-1].file_id

    conn = sqlite3.connect("members.db")
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO payments (user_id, username, purpose, location, base_amount, penalty_amount, total_amount, note, file_id, timestamp) 
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                   (user.id, user.username, data['purpose'], data['location'], data['base_amount'], data['penalty_amount'], data['totalAmount'], data.get('note', ''), file_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    p_id = cursor.lastrowid
    conn.commit()
    conn.close()

    del context.user_data['pending_pay']
    await update.message.reply_text("📩 ደረሰኝዎ ተልኳል! በአስተዳዳሪው ሲረጋገጥ እናሳውቅዎታለን።")

    if ADMIN_ID:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ አጽድቅ", callback_data=f"papp_{p_id}_{user.id}"), InlineKeyboardButton("❌ ሰርዝ", callback_data=f"prej_{p_id}_{user.id}")]])
        await context.bot.send_photo(ADMIN_ID, file_id, caption=f"🚨 **አዲስ ክፍያ**\n👤 @{user.username}\n🎯 {data['purpose']}\n💵 {data['totalAmount']} ብር", reply_markup=kb)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """የማጽደቂያ ቁልፎችን ማስተናገድ"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "user_status": return await status_cmd(update, context)
    if query.data == "user_help": return await help_cmd(update, context)

    if query.from_user.id != ADMIN_ID: return
    
    try:
        parts = query.data.split("_")
        action, rec_id, target_uid = parts[0], parts[1], int(parts[2])
        is_app = "app" in action
        
        conn = sqlite3.connect("members.db")
        conn.execute("UPDATE payments SET status = ? WHERE id = ?", ("APPROVED" if is_app else "REJECTED", rec_id))
        if is_app: conn.execute("UPDATE members SET status = 'APPROVED' WHERE user_id = ?", (target_uid,))
        conn.commit()
        conn.close()

        await context.bot.send_message(target_uid, "🎉 ክፍያዎ ጸድቋል! እናመሰግናለን።" if is_app else "⚠️ ይቅርታ፣ ክፍያዎ በአስተዳዳሪው ውድቅ ተደርጓል።")
        
        res_tag = "ጸድቋል ✅" if is_app else "ውድቅ ተደርጓል ❌"
        await query.edit_message_caption(caption=f"{query.message.caption}\n\n🏁 **ውጤት፦ {res_tag}**")
    except Exception as e:
        logging.error(f"Callback error: {e}")

# --- ዋና ማስጀመሪያ (Main Launcher) ---

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    
    # ትዕዛዞች
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("pay", pay_cmd))
    app.add_handler(CommandHandler("loan", loan_cmd))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("stats", stats_cmd))
    
    # መረጃ መቀበያ
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, on_web_app_data))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    print("🚀 Ehuden Befikir Bot is active and running...")
    app.run_polling()

if __name__ == "__main__":
    main()
