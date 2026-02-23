require('dotenv').config();
const { Telegraf, session, Markup } = require('telegraf');
const Database = require('better-sqlite3');
const http = require('http');

// --- CONFIGURATION ---
const BOT_TOKEN = process.env.BOT_TOKEN;
const ADMIN_ID = process.env.ADMIN_ID ? parseInt(process.env.ADMIN_ID) : null;
const MINI_APP_URL = process.env.MINI_APP_URL;

// Initial Validation
if (!BOT_TOKEN) {
    console.error("❌ ERROR: BOT_TOKEN is missing!");
    process.exit(1);
}

// Initialize Database
const db = new Database('members.db');

// --- DATABASE SCHEMA ---
db.exec(`
    CREATE TABLE IF NOT EXISTS members (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        status TEXT DEFAULT 'PENDING'
    );
    CREATE TABLE IF NOT EXISTS payments (
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
    );
    CREATE TABLE IF NOT EXISTS loan_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        amount REAL,
        duration INTEGER,
        reason TEXT,
        status TEXT DEFAULT 'PENDING',
        timestamp TEXT
    );
`);

const bot = new Telegraf(BOT_TOKEN);
bot.use(session());

// --- PILOT MODE: BYPASS GROUP CHECK ---
// We have disabled the group check so you can test the bot privately.
const checkGroupMembership = async (ctx, next) => {
    // For Pilot: Just let everyone through
    return next();
};

// --- USER COMMANDS ---

bot.start(checkGroupMembership, (ctx) => {
    db.prepare('INSERT OR IGNORE INTO members (user_id, username) VALUES (?, ?)').run(ctx.from.id, ctx.from.username || 'N/A');
    
    const welcomeMsg = `እንኳን ወደ **እሁድን በፍቅር (Pilot)** የክፍያ ቦት በሰላም መጡ! 🚀\n\n` +
        `ይህ የሙከራ ስሪት ስለሆነ ያለምንም ገደብ መሞከር ይችላሉ።\n\n` +
        `**ክፍያ ለመፈጸም** ከታች ያለውን ሰማያዊ ቁልፍ ይጠቀሙ።`;
    
    return ctx.replyWithMarkdown(welcomeMsg, 
        Markup.keyboard([
            [Markup.button.webApp("🚀 ክፍያ ያስገቡ", MINI_APP_URL)],
            ["📊 የጥያቄዬ ሁኔታ", "❓ እርዳታ"]
        ]).resize()
    );
});

// --- DATA HANDLERS ---

bot.on('web_app_data', async (ctx) => {
    try {
        const data = JSON.parse(ctx.webAppData.data.json());
        if (data.type === 'payment_report') {
            ctx.session.pendingPayment = { ...data, userId: ctx.from.id, username: ctx.from.username || 'N/A' };
            await ctx.reply(`✅ የ${data.purpose} መረጃ ተመዝግቧል። አሁን ደረሰኝዎን (Photo) ይላኩ።`);
        }
    } catch (e) {
        ctx.reply("⚠️ መረጃ ስህተት።");
    }
});

bot.on(['photo', 'document'], async (ctx) => {
    const pending = ctx.session?.pendingPayment;
    if (!pending) return ctx.reply("እባክዎ መጀመሪያ ፎርሙን ይሙሉ በ 'ክፍያ ያስገቡ' በኩል::");

    const fileId = ctx.message.photo ? ctx.message.photo.pop().file_id : ctx.message.document.file_id;
    
    const res = db.prepare(`INSERT INTO payments (user_id, username, purpose, location, base_amount, penalty_amount, total_amount, note, file_id, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).run(
        pending.userId, pending.username, pending.purpose, pending.location, pending.baseAmount, pending.penaltyAmount, pending.totalAmount, pending.note || '', fileId, new Date().toLocaleString()
    );

    ctx.session.pendingPayment = null;

    if (ADMIN_ID) {
        const adminKb = Markup.inlineKeyboard([
            [Markup.button.callback('✅ አጽድቅ', `papp_${res.lastInsertRowid}_${ctx.from.id}`), 
             Markup.button.callback('❌ ሰርዝ', `prej_${res.lastInsertRowid}_${ctx.from.id}`)]
        ]);
        await ctx.telegram.sendPhoto(ADMIN_ID, fileId, { 
            caption: `🚨 *አዲስ ክፍያ (Pilot)*\n👤 @${pending.username}\n🎯 ዓላማ: ${pending.purpose}\n💵 ድምር: ${pending.totalAmount} ብር`,
            parse_mode: 'Markdown',
            ...adminKb 
        });
    }

    await ctx.reply("📩 የሙከራ ደረሰኝዎ ተልኳል።");
});

// Admin Actions
bot.action(/^(papp|prej)_(\d+)_(\d+)$/, async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return ctx.answerCbQuery("ፍቃድ የሎትም!");
    const [action, id, targetId] = [ctx.match[1], ctx.match[2], parseInt(ctx.match[3])];
    const isApprove = action === 'papp';
    db.prepare(`UPDATE payments SET status = ? WHERE id = ?`).run(isApprove ? 'APPROVED' : 'REJECTED', id);
    await ctx.telegram.sendMessage(targetId, isApprove ? "✅ ክፍያዎ ተረጋግጧል!" : "❌ ክፍያዎ ውድቅ ተደርጓል።");
    await ctx.editMessageCaption(`${ctx.callbackQuery.message.caption}\n\n🏁 ውጤት: ${isApprove ? 'APPROVED ✅' : 'REJECTED ❌'}`);
    await ctx.answerCbQuery("ተከናውኗል");
});

// Health Check for Render
http.createServer((req, res) => {
    res.writeHead(200);
    res.end('Pilot Bot is active!');
}).listen(process.env.PORT || 3000);

bot.launch().then(() => console.log('✅ Pilot Bot is ACTIVE (No Group Check)!'));

process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
