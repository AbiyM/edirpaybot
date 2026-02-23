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

# 1. የአካባቢ ተለዋዋጮችን መጫን (.env ፋይል ያስፈልጋል)
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None
MINI_APP_URL = os.getenv("MINI_APP_URL")

# ስህተቶችን ለመከታተል (Debugging)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

# --- 2. ዳታቤዝ ማዘጋጀት ---
def init_db():
    conn = sqlite3.connect("members.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS members (
        user_id INTEGER PRIMARY KEY, username TEXT, status TEXT DEFAULT 'PENDING'
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        user_id INTEGER, username TEXT, gateway TEXT, purpose TEXT, 
        location TEXT, base_amount REAL, penalty_amount REAL, 
        total_amount REAL, file_id TEXT, status TEXT DEFAULT 'AWAIT_APPROVAL', 
        timestamp TEXT
    )''')
    conn.commit()
    conn.close()

# --- 3. ቦቱ ሲጀመር የሚመጣ መልእክት (Start Handler) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # ተጠቃሚውን ዳታቤዝ ውስጥ መመዝገብ
    conn = sqlite3.connect("members.db")
    conn.execute("INSERT OR IGNORE INTO members (user_id, username) VALUES (?, ?)", (user.id, user.username))
    conn.commit()
    conn.close()

    # የሜኑ ቁልፍን ወደ "ክፈት (Open)" መቀየር (ቋሚ እንዲሆን)
    await context.bot.set_chat_menu_button(
        chat_id=update.effective_chat.id,
        menu_button=MenuButtonWebApp(text="ክፈት (Open)", web_app=WebAppInfo(url=MINI_APP_URL))
    )
    
    # የእንኳን ደህና መጡ መልእክት
    welcome_msg = (
        f"ሰላም **{user.first_name}**! 👋\n\n"
        f"ወደ **እሁድን በፍቅር** የክፍያ ቦት በሰላም መጡ።\n\n"
        "ይህ ቦት መደበኛ መዋጮዎን ለመክፈል፣ የብድር ሁኔታዎን ለማየት እና "
        "ክፍያዎችን በቀላሉ ለማከናወን ይረዳዎታል።\n\n"
        "ለመጀመር ከታች በግራ በኩል ያለውን **'ክፈት (Open)'** የሚለውን ቁልፍ ይጠቀሙ።"
    )
    
    # አብሮ የሚመጣ የአንድ ጊዜ ቁልፍ
    keyboard = [[InlineKeyboardButton("🚀 ክፍያ ይፈጽሙ (Pay Now)", web_app=WebAppInfo(url=MINI_APP_URL))]]
    
    await update.message.reply_text(
        welcome_msg, 
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# --- 4. ከሚኒ አፑ የሚመጣ መረጃን መቀበል ---
async def on_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = json.loads(update.effective_message.web_app_data.data)
        user = update.effective_user
        
        if data.get('type') == 'payment_report':
            # መረጃውን ለጊዜው በሴሽን መያዝ
            context.user_data['pending_pay'] = data
            
            msg = (
                f"✅ የ**{data['purpose']}** መረጃ ተመዝግቧል።\n"
                f"💰 መጠን፦ **{data.get('totalAmount', 0)} ብር**\n"
                f"💳 መተግበሪያ፦ {data.get('gateway', 'manual').upper()}\n\n"
                "አሁን ደረሰኝዎን (Screenshot) እዚህ ይላኩ።"
            )
            await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error processing web app data: {e}")

# --- 5. ደረሰኝ (ፎቶ) ሲላክ መቀበል ---
async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'pending_pay' not in context.user_data:
        return await update.message.reply_text("እባክዎ መጀመሪያ በሚኒ አፑ በኩል ፎርሙን ይሙሉ::")
    
    data = context.user_data['pending_pay']
    user = update.effective_user
    file_id = update.message.photo[-1].file_id # ትልቁን ፎቶ መውሰድ

    # ዳታቤዝ ውስጥ መመዝገብ
    conn = sqlite3.connect("members.db")
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO payments (user_id, username, gateway, purpose, location, base_amount, penalty_amount, total_amount, file_id, timestamp) 
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                   (user.id, user.username, data.get('gateway'), data['purpose'], data['location'], data.get('baseAmount', 0), data.get('penaltyAmount', 0), data.get('totalAmount', 0), file_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    p_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # መረጃውን ማጽዳት
    del context.user_data['pending_pay']
    await update.message.reply_text("📩 ደረሰኝዎ ተልኳል! በአስተዳዳሪው ሲረጋገጥ እናሳውቅዎታለን።")

    # ለአስተዳዳሪው ማሳወቅ
    if ADMIN_ID:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ አጽድቅ", callback_data=f"app_{p_id}_{user.id}"),
            InlineKeyboardButton("❌ ሰርዝ", callback_data=f"rej_{p_id}_{user.id}")
        ]])
        caption = f"🚨 **አዲስ ክፍያ**\n👤 @{user.username}\n🎯 {data['purpose']}\n💵 {data.get('totalAmount', 0)} ብር"
        await context.bot.send_photo(ADMIN_ID, file_id, caption=caption, reply_markup=kb, parse_mode="Markdown")

# --- 6. የአስተዳዳሪ ምላሽ (Approve/Reject) ---
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID: return
    
    await query.answer()
    parts = query.data.split("_")
    action, rec_id, target_uid = parts[0], parts[1], int(parts[2])
    
    conn = sqlite3.connect("members.db")
    conn.execute("UPDATE payments SET status = ? WHERE id = ?", ("APPROVED" if action == "app" else "REJECTED", rec_id))
    conn.commit()
    conn.close()

    status_msg = "🎉 ክፍያዎ ጸድቋል! እናመሰግናለን።" if action == "app" else "⚠️ ይቅርታ፣ ክፍያዎ ውድቅ ተደርጓል።"
    await context.bot.send_message(target_uid, status_msg)
    await query.edit_message_caption(caption=f"{query.message.caption}\n\n🏁 ውጤት፦ {'ጸድቋል ✅' if action == 'app' else 'ተሰርዟል ❌'}")

# --- 7. ዋና ማስጀመሪያ ---
def main():
    init_db()
    # ቦቱን መፍጠር
    application = Application.builder().token(BOT_TOKEN).build()

    # ትዕዛዞችን ማገናኘት
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, on_web_app_data))
    application.add_handler(MessageHandler(filters.PHOTO, on_photo))
    application.add_handler(CallbackQueryHandler(callback_handler))

    # ቦቱን ማስነሳት
    print("🚀 Ehuden Befikir Bot is active and running...")
    application.run_polling()

if __name__ == '__main__':
    main()
