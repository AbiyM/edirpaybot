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
ADMIN_ID = int(os.getenv("ADMIN_ID"))
MINI_APP_URL = os.getenv("MINI_APP_URL")
GROUP_ID = os.getenv("EDIR_GROUP_ID")

# Enable logging to track errors and activity
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- DATABASE SETUP ---
def init_db():
    """Initializes the SQLite database and creates required tables."""
    conn = sqlite3.connect("members.db")
    cursor = conn.cursor()
    # Table for members
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

# --- SECURITY: GROUP CHECK ---
async def is_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Checks if the user is a member of the specified Telegram group."""
    # Pilot mode check: Allow everyone if Group ID is a placeholder
    if not GROUP_ID or GROUP_ID in ["YOUR_GROUP_ID", "-1001234567890"]:
        return True
        
    try:
        member = await context.bot.get_chat_member(chat_id=GROUP_ID, user_id=update.effective_user.id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
    except Exception as e:
        logging.error(f"Group check error: {e}")
        pass
    
    await update.effective_message.reply_text("❌ ይቅርታ! ይህን ቦት ለመጠቀም መጀመሪያ የእሁድን በፍቅር የቴሌግራም ግሩፕ አባል መሆን አለብዎት።")
    return False

# --- COMMAND HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message and main menu."""
    if not await is_member(update, context): return

    user = update.effective_user
    conn = sqlite3.connect("members.db")
    conn.execute("INSERT OR IGNORE INTO members (user_id, username) VALUES (?, ?)", (user.id, user.username))
    conn.commit()
    conn.close()

    keyboard = [
        [InlineKeyboardButton("🚀 ፎርሙን ክፈት", web_app=WebAppInfo(url=MINI_APP_URL))],
        [InlineKeyboardButton("📊 ሁኔታዬን አሳይ", callback_data="check_status"), 
         InlineKeyboardButton("❓ እርዳታ", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        "እንኳን ወደ **እሁድን በፍቅር (Pilot)** የክፍያ ቦት በሰላም መጡ! 🚀\n\n"
        "ይህ የሙከራ ስሪት ስለሆነ ያለምንም ገደብ መሞከር ይችላሉ።\n\n"
        "ክፍያ ለመፈጸም ወይም **ብድር ለመጠየቅ** ከታች ያለውን ቁልፍ ይጠቀሙ።"
    )
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Instructions on how to use the bot."""
    help_text = (
        "📖 **የአጠቃቀም መመሪያ**\n\n"
        "1. **ክፍያ ለመፈጸም:** '🚀 ፎርሙን ክፈት' የሚለውን ይጫኑ። መረጃውን ሞልተው ሲጨርሱ የደረሰኙን ፎቶ (Screenshot) እዚህ ይላኩ።\n"
        "2. **ብድር ለመጠየቅ:** በፎርሙ ውስጥ 'ብድር ይጠይቁ' የሚለውን ታብ ይምረጡ።\n"
        "3. **ሁኔታ ለመከታተል:** /status የሚለውን ይጫኑ።"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the user's current approval status."""
    user_id = update.effective_user.id
    conn = sqlite3.connect("members.db")
    member = conn.execute("SELECT status FROM members WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    
    status_text = "✅ የጸደቀ አባል" if member and member[0] == 'APPROVED' else "⏳ በመጠባበቅ ላይ ያለ"
    await update.message.reply_text(f"የእርስዎ አሁናዊ ሁኔታ: *{status_text}*", parse_mode="Markdown")

async def pay_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shortcut to open the Mini App."""
    keyboard = [[InlineKeyboardButton("🚀 ፎርሙን ክፈት", web_app=WebAppInfo(url=MINI_APP_URL))]]
    await update.message.reply_text("የክፍያ መረጃ ለመሙላት ከታች ያለውን ቁልፍ ይጫኑ፡", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin summary of pending tasks."""
    if update.effective_user.id != ADMIN_ID: return
    
    conn = sqlite3.connect("members.db")
    pending_payments = conn.execute("SELECT COUNT(*) FROM payments WHERE status = 'AWAIT_APPROVAL'").fetchone()[0]
    pending_loans = conn.execute("SELECT COUNT(*) FROM loan_requests WHERE status = 'PENDING'").fetchone()[0]
    conn.close()
    
    await update.message.reply_text(f"📊 **የአስተዳዳሪ ማጠቃለያ**\n\n• ማረጋገጫ የሚጠብቁ ክፍያዎች፡ {pending_payments}\n• ምላሽ የሚጠብቁ የብድር ጥያቄዎች፡ {pending_loans}")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Financial report for the admin."""
    if update.effective_user.id != ADMIN_ID: return
    
    conn = sqlite3.connect("members.db")
    stats = conn.execute('''
        SELECT 
            SUM(CASE WHEN purpose = 'Monthly Fee' THEN base_amount ELSE 0 END),
            SUM(CASE WHEN purpose = 'Loan Payment' THEN base_amount ELSE 0 END),
            SUM(penalty_amount),
            SUM(total_amount)
        FROM payments WHERE status = 'APPROVED'
    ''').fetchone()
    conn.close()

    if not stats or stats[3] is None:
        return await update.message.reply_text("💰 እስካሁን የጸደቀ የገንዘብ እንቅስቃሴ የለም።")

    report = (
        "💰 **የእሁድን በፍቅር የገንዘብ ሪፖርት**\n\n"
        f"• መደበኛ መዋጮ፡ **{stats[0] or 0} ብር**\n"
        f"• የተመለሰ ብድር፡ **{stats[1] or 0} ብር**\n"
        f"• ጠቅላላ ቅጣት፡ **{stats[2] or 0} ብር**\n"
        "--------------------------\n"
        f"📢 **አጠቃላይ ካዝና፡ {stats[3] or 0} ብር**"
    )
    await update.message.reply_text(report, parse_mode="Markdown")

# --- MINI APP DATA HANDLING ---
async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes JSON data sent from the Mini App."""
    try:
        data = json.loads(update.effective_message.web_app_data.data)
        user = update.effective_user

        if data.get('type') == 'payment_report':
            # Store payment info in user session to wait for the photo
            context.user_data['pending_payment'] = data
            await update.message.reply_text(
                f"✅ የ**{data['purpose']}** መረጃ ተመዝግቧል!\n"
                f"📍 ቦታ፡ {data['location']}\n"
                f"💰 መጠን፡ {data['totalAmount']} ብር\n\n"
                f"አሁን የደረሰኝዎን ፎቶ ወይም ስክሪንሹት (Screenshot) እዚህ ይላኩ።"
            )
        
        elif data.get('type') == 'loan_request':
            conn = sqlite3.connect("members.db")
            cursor = conn.cursor()
            cursor.execute("INSERT INTO loan_requests (user_id, username, amount, duration, reason, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                           (user.id, user.username, data['amount'], data['duration'], data['reason'], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            loan_id = cursor.lastrowid
            conn.commit()
            conn.close()

            await update.message.reply_text("📩 የብድር ጥያቄዎ ለገንዘብ ያዡ ተልኳል!")
            
            # Notify Admin immediately for loans (no photo required)
            admin_keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ ፍቀድ", callback_data=f"lapp_{loan_id}_{user.id}"), 
                InlineKeyboardButton("❌ ሰርዝ", callback_data=f"lrej_{loan_id}_{user.id}")
            ]])
            admin_text = f"❓ **አዲስ የብድር ጥያቄ (Pilot)**\n👤 @{user.username}\n💰 {data['amount']} ብር\n📅 {data['duration']} ወራት\n📝 {data['reason']}"
            await context.bot.send_message(ADMIN_ID, admin_text, reply_markup=admin_keyboard)
    except Exception as e:
        logging.error(f"WebAppData Error: {e}")
        await update.message.reply_text("⚠️ መረጃውን በማቀነባበር ላይ ስህተት አጋጥሟል። እባክዎ እንደገና ይሞክሩ።")

# --- RECEIPT PHOTO HANDLER ---
async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pairs an incoming photo with the pending payment report."""
    if 'pending_payment' not in context.user_data:
        await update.message.reply_text("እባክዎ መጀመሪያ ፎርሙን ይሙሉ (ክፍያ ያስገቡ የሚለውን ይጫኑ)።")
        return

    data = context.user_data['pending_payment']
    user = update.effective_user
    
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.document and update.message.document.mime_type.startswith('image/'):
        file_id = update.message.document.file_id
    else:
        await update.message.reply_text("⚠️ እባክዎ የደረሰኙን ፎቶ (Image) ብቻ ይላኩ።")
        return

    conn = sqlite3.connect("members.db")
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO payments (user_id, username, purpose, location, base_amount, penalty_amount, total_amount, note, file_id, timestamp) 
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                   (user.id, user.username, data['purpose'], data['location'], data['baseAmount'], data['penaltyAmount'], data['totalAmount'], data.get('note', ''), file_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    payment_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Clear temporary session data
    del context.user_data['pending_payment']
    await update.message.reply_text(f"📩 የ**{data['purpose']}** ደረሰኝ ለገንዘብ ያዡ ተልኳል። ሲረጋገጥ መልእክት ይደርስዎታል።")

    # Notify Admin with Approval buttons
    admin_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ አጽድቅ", callback_data=f"papp_{payment_id}_{user.id}"), 
        InlineKeyboardButton("❌ ሰርዝ", callback_data=f"prej_{payment_id}_{user.id}")
    ]])
    
    caption = (
        f"🚨 **አዲስ የክፍያ ማረጋገጫ (Pilot)**\n"
        f"👤 ተላኪ፦ @{user.username}\n"
        f"🎯 ዓላማ፦ {data['purpose']}\n"
        f"💵 ጠቅላላ፦ {data['totalAmount']} ብር\n"
        f"📍 ቦታ፦ {data['location']}"
    )
    await context.bot.send_photo(ADMIN_ID, file_id, caption=caption, reply_markup=admin_kb, parse_mode="Markdown")

# --- CALLBACK ACTIONS ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles Approve/Reject button clicks from the admin."""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("_")
    action, record_id, target_user = data[0], data[1], int(data[2])
    
    if query.from_user.id != ADMIN_ID: return

    is_approve = "app" in action
    status = "APPROVED" if is_approve else "REJECTED"
    table = "payments" if action.startswith("p") else "loan_requests"
    
    conn = sqlite3.connect("members.db")
    conn.execute(f"UPDATE {table} SET status = ? WHERE id = ?", (status, record_id))
    # If a payment is approved, mark the user as an approved member
    if is_approve and table == "payments":
        conn.execute("UPDATE members SET status = 'APPROVED' WHERE user_id = ?", (target_user,))
    conn.commit()
    conn.close()

    msg = "🎉 የእሁድን በፍቅር ጥያቄዎ/ክፍያዎ በአስተዳዳሪው ጸድቋል!" if is_approve else "⚠️ ጥያቄዎ/ክፍያዎ ውድቅ ተደርጓል። እባክዎ መረጃውን አረጋግጠው በድጋሚ ይላኩ።"
    await context.bot.send_message(target_user, msg)
    
    # Update admin message to show decision
    result_tag = "APPROVED ✅" if is_approve else "REJECTED ❌"
    current_text = query.message.caption if query.message.caption else query.message.text
    new_text = f"{current_text}\n\n🏁 **ውጤት፦ {result_tag}**"
    
    if query.message.photo:
        await query.edit_message_caption(caption=new_text, parse_mode="Markdown")
    else:
        await query.edit_message_text(text=new_text, parse_mode="Markdown")

def main():
    """Main entry point to start the bot polling."""
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("pay", pay_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    
    # Message Logic
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_receipt))
    
    # Inline button responses
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Ehuden Befikir Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
