import os
import logging
import sqlite3
import json
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# Load environment variables from .env file
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None
MINI_APP_URL = os.getenv("MINI_APP_URL")
GROUP_ID = os.getenv("EDIR_GROUP_ID")

# Logging setup to track activity and errors
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- DATABASE SETUP ---
def init_db():
    """Initializes the database and creates tables if they don't exist."""
    conn = sqlite3.connect("members.db")
    cursor = conn.cursor()
    # Table for registered members
    cursor.execute('''CREATE TABLE IF NOT EXISTS members (
        user_id INTEGER PRIMARY KEY, 
        username TEXT, 
        status TEXT DEFAULT 'PENDING'
    )''')
    # Table for payment reports
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
    # Table for loan requests
    cursor.execute('''CREATE TABLE IF NOT EXISTS loan_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        user_id INTEGER, 
        username TEXT, 
        amount REAL, 
        duration INTEGER, 
        reason TEXT, 
        status TEXT DEFAULT 'PENDING', 
        timestamp TEXT
    )''')
    conn.commit()
    conn.close()

# --- SECURITY: MEMBERSHIP CHECK ---
async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verifies if the user is a member of the required Telegram group."""
    if not GROUP_ID or GROUP_ID.startswith("YOUR_") or GROUP_ID == "":
        return True
    try:
        member = await context.bot.get_chat_member(chat_id=GROUP_ID, user_id=update.effective_user.id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
    except Exception as e:
        logging.error(f"Group membership check failed: {e}")
        return True # Default to true if check fails (optional)
    
    await update.effective_message.reply_text("❌ ይቅርታ! ይህን ቦት ለመጠቀም መጀመሪያ የእሁድን በፍቅር የቴሌግራም ግሩፕ አባል መሆን አለብዎት።")
    return False

# --- COMMAND HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command and shows the main menu."""
    if not await check_membership(update, context): return

    user = update.effective_user
    conn = sqlite3.connect("members.db")
    conn.execute("INSERT OR IGNORE INTO members (user_id, username) VALUES (?, ?)", (user.id, user.username))
    conn.commit()
    conn.close()

    keyboard = [
        [InlineKeyboardButton("🚀 ፎርሙን ክፈት (Open Form)", web_app=WebAppInfo(url=MINI_APP_URL))],
        [InlineKeyboardButton("📊 ሁኔታዬን አሳይ", callback_data="user_status"), 
         InlineKeyboardButton("❓ እርዳታ", callback_data="user_help")]
    ]
    
    welcome_msg = (
        f"ሰላም {user.first_name}! 👋 ወደ **እሁድን በፍቅር** የክፍያ ቦት በሰላም መጡ!\n\n"
        "ክፍያ ለመፈጸም ወይም የብድር መረጃ ለመከታተል ከታች ያሉትን ቁልፎች ይጠቀሙ።\n\n"
        "**Powered by Skymark System Solution**"
    )
    await update.message.reply_text(welcome_msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the user's current approval status."""
    user_id = update.effective_user.id
    conn = sqlite3.connect("members.db")
    member = conn.execute("SELECT status FROM members WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    
    status_label = "✅ የጸደቀ አባል (Approved)" if member and member[0] == 'APPROVED' else "⏳ በመጠባበቅ ላይ ያለ (Pending)"
    msg = f"🔍 **የአባልነት ሁኔታዎ፦**\n\n{status_label}"
    
    if update.callback_query:
        await update.callback_query.message.reply_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays help information."""
    help_text = (
        "📖 **የአጠቃቀም መመሪያ**\n\n"
        "1. **ክፍያ ለመፈጸም፦** '🚀 ፎርሙን ክፈት' የሚለውን ይጫኑ። መረጃውን ሞልተው 'ደረሰኝ ላክ' ሲሉ ወደ ቦቱ ይመለሳሉ።\n"
        "2. **ደረሰኝ መላክ፦** ፎርሙን እንደጨረሱ የክፍያ ማረጋገጫ ፎቶ (Screenshot) እዚህ ቦት ላይ ይላኩ።\n"
        "3. **ሁኔታ ለማየት፦** /status ብለው ይላኩ።"
    )
    if update.callback_query:
        await update.callback_query.message.reply_text(help_text, parse_mode="Markdown")
    else:
        await update.message.reply_text(help_text, parse_mode="Markdown")

# --- ADMIN COMMANDS ---

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays admin dashboard summary."""
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ ይህ ትዕዛዝ ለአስተዳዳሪ ብቻ ነው።")
    
    conn = sqlite3.connect("members.db")
    p_count = conn.execute("SELECT COUNT(*) FROM payments WHERE status = 'AWAIT_APPROVAL'").fetchone()[0]
    l_count = conn.execute("SELECT COUNT(*) FROM loan_requests WHERE status = 'PENDING'").fetchone()[0]
    m_count = conn.execute("SELECT COUNT(*) FROM members").fetchone()[0]
    conn.close()
    
    admin_text = (
        f"🛠 **Admin Dashboard**\n\n"
        f"• ጠቅላላ ተመዝጋቢዎች፦ **{m_count}**\n"
        f"• ያልጸደቁ ክፍያዎች፦ **{p_count}**\n"
        f"• የብድር ጥያቄዎች፦ **{l_count}**\n\n"
        "ለዝርዝር ሪፖርት /stats ይጠቀሙ።"
    )
    await update.message.reply_text(admin_text, parse_mode="Markdown")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows financial statistics to the admin."""
    if update.effective_user.id != ADMIN_ID: return
    
    conn = sqlite3.connect("members.db")
    stats = conn.execute('''
        SELECT SUM(total_amount), SUM(penalty_amount),
               SUM(CASE WHEN purpose = 'Monthly Fee' THEN base_amount ELSE 0 END)
        FROM payments WHERE status = 'APPROVED'
    ''').fetchone()
    conn.close()

    total = stats[0] if stats[0] else 0
    penalty = stats[1] if stats[1] else 0
    monthly = stats[2] if stats[2] else 0
    
    report = (
        f"💰 **የፋይናንስ ሪፖርት**\n\n"
        f"• ጠቅላላ በካዝና ያለ፦ **{total} ብር**\n"
        f"• ከመደበኛ መዋጮ፦ **{monthly} ብር**\n"
        f"• ከቅጣት የተሰበሰበ፦ **{penalty} ብር**"
    )
    await update.message.reply_text(report, parse_mode="Markdown")

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a message to all registered bot users."""
    if update.effective_user.id != ADMIN_ID: return
    
    msg_to_send = update.message.text.replace("/broadcast", "").strip()
    if not msg_to_send:
        return await update.message.reply_text("❌ እባክዎ መልእክት ይጻፉ። ምሳሌ፦ `/broadcast ሰላም አባላት...`")
    
    conn = sqlite3.connect("members.db")
    users = conn.execute("SELECT user_id FROM members").all()
    conn.close()
    
    count = 0
    for user in users:
        try:
            await context.bot.send_message(chat_id=user[0], text=f"📢 **ከአስተዳዳሪ የተላከ መልእክት፦**\n\n{msg_to_send}", parse_mode="Markdown")
            count += 1
        except:
            pass
    await update.message.reply_text(f"✅ መልእክቱ ለ {count} አባላት ተልኳል።")

# --- DATA & PHOTO HANDLING ---

async def on_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receives JSON data from the Mini App."""
    data = json.loads(update.effective_message.web_app_data.data)
    user = update.effective_user

    if data.get('type') == 'payment_report':
        context.user_data['active_payment'] = data
        await update.message.reply_text(
            f"✅ የ**{data['purpose']}** መረጃ ተመዝግቧል!\n"
            f"💰 መጠን፦ {data['totalAmount']} ብር\n\n"
            "አሁን እባክዎ የደረሰኝ ፎቶ (Image/Screenshot) ይላኩ።"
        )
    elif data.get('type') == 'loan_request':
        # Loans are currently 'under construction' in frontend but code handles it just in case
        await update.message.reply_text("📩 የብድር ጥያቄዎ ተመዝግቧል።")

async def on_photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pairs an incoming photo with the last submitted payment report."""
    if 'active_payment' not in context.user_data:
        return await update.message.reply_text("እባክዎ መጀመሪያ ፎርሙን ሞልተው 'ደረሰኝ ላክ' የሚለውን ይጫኑ።")

    data = context.user_data['active_payment']
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

    del context.user_data['active_payment']
    await update.message.reply_text("📩 ደረሰኝዎ ለአስተዳዳሪ ተልኳል። ሲረጋገጥ እናሳውቅዎታለን።")

    # Notify Admin for Approval
    if ADMIN_ID:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ አጽድቅ (Approve)", callback_data=f"papp_{p_id}_{user.id}"),
            InlineKeyboardButton("❌ ውድቅ አድርግ (Reject)", callback_data=f"prej_{p_id}_{user.id}")
        ]])
        caption = f"🚨 **አዲስ የክፍያ ሪፖርት**\n👤 @{user.username}\n🎯 ዓላማ፦ {data['purpose']}\n💵 ብር፦ {data['totalAmount']}"
        await context.bot.send_photo(ADMIN_ID, file_id, caption=caption, reply_markup=kb, parse_mode="Markdown")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all button clicks (User menu and Admin approvals)."""
    query = update.callback_query
    await query.answer()
    
    data = query.data

    # User-level callbacks
    if data == "user_status":
        return await status_cmd(update, context)
    if data == "user_help":
        return await help_cmd(update, context)

    # Admin-level callbacks
    if query.from_user.id != ADMIN_ID: return
    
    try:
        parts = data.split("_")
        action, rec_id, target_uid = parts[0], parts[1], int(parts[2])
        
        is_app = "app" in action
        status = "APPROVED" if is_app else "REJECTED"
        
        conn = sqlite3.connect("members.db")
        conn.execute("UPDATE payments SET status = ? WHERE id = ?", (status, rec_id))
        if is_app:
            conn.execute("UPDATE members SET status = 'APPROVED' WHERE user_id = ?", (target_uid,))
        conn.commit()
        conn.close()

        notify_text = "🎉 የእሁድን በፍቅር ክፍያዎ ጸድቋል! እናመሰግናለን።" if is_app else "⚠️ ይቅርታ፣ ክፍያዎ በአስተዳዳሪው ውድቅ ተደርጓል። እባክዎ በትክክል መሙላትዎን ያረጋግጡ።"
        await context.bot.send_message(chat_id=target_uid, text=notify_text)
        
        result_label = "ጸድቋል ✅" if is_app else "ውድቅ ተደርጓል ❌"
        await query.edit_message_caption(caption=f"{query.message.caption}\n\n🏁 **ውጤት፦ {result_label}**", parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Callback error: {e}")

# --- MAIN APP ---

def main():
    """Starts the bot application."""
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Command Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("pay", start)) # Alias for convenience
    
    # Message Handlers
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, on_web_app_data))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, on_photo_received))
    
    # Button Handlers
    app.add_handler(CallbackQueryHandler(callback_handler))

    print("🚀 Ehuden Befikir Bot is active and running...")
    app.run_polling()

if __name__ == "__main__":
    main()
