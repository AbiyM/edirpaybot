require('dotenv').config();
const { Telegraf, session, Markup } = require('telegraf');
const Database = require('better-sqlite3');

// --- CONFIGURATION ---
const BOT_TOKEN = process.env.BOT_TOKEN;
const ADMIN_ID = parseInt(process.env.ADMIN_ID);
const MINI_APP_URL = process.env.MINI_APP_URL;
const EDIR_GROUP_ID = parseInt(process.env.EDIR_GROUP_ID); 

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

// --- MIDDLEWARE: GROUP ACCESS CHECK ---
const checkGroupMembership = async (ctx, next) => {
    if (ctx.from && ctx.chat.type === 'private') {
        try {
            const member = await ctx.telegram.getChatMember(EDIR_GROUP_ID, ctx.from.id);
            const allowed = ['member', 'administrator', 'creator'];
            if (!allowed.includes(member.status)) {
                return ctx.reply("❌ ይቅርታ! ይህን ቦት ለመጠቀም መጀመሪያ የእሁድን በፍቅር የቴሌግራም ግሩፕ አባል መሆን አለብዎት።");
            }
        } catch (error) {
            return ctx.reply("⚠️ ስህተት ተከስቷል። እባክዎ የእድሩ ግሩፕ ውስጥ መሆንዎን ያረጋግጡ።");
        }
    }
    return next();
};

// --- USER COMMANDS ---

bot.start(checkGroupMembership, (ctx) => {
    db.prepare('INSERT OR IGNORE INTO members (user_id, username) VALUES (?, ?)').run(ctx.from.id, ctx.from.username || 'N/A');
    
    const welcomeMsg = `እንኳን ወደ **እሁድን በፍቅር** የክፍያ ቦት በሰላም መጡ! 🚀\n\n` +
        `ይህ ቦት መዋጮን፣ ቅጣትን እና የብድር አገልግሎትን ለማስተዳደር ይረዳል።\n\n` +
        `**ክፍያ ለመፈጸም ወይም ብድር ለመጠየቅ** ከታች ያለውን ቁልፍ ይጠቀሙ።`;
    
    return ctx.replyWithMarkdown(welcomeMsg, 
        Markup.keyboard([
            [Markup.button.webApp("🚀 ክፍያ ያስገቡ", MINI_APP_URL)],
            ["📊 የጥያቄዬ ሁኔታ", "❓ እርዳታ"]
        ]).resize()
    );
});

bot.command('status', (ctx) => {
    const member = db.prepare('SELECT status FROM members WHERE user_id = ?').get(ctx.from.id);
    const statusText = member?.status === 'APPROVED' ? "✅ የጸደቀ አባል" : "⏳ በመጠባበቅ ላይ ያለ";
    ctx.replyWithMarkdown(`የአሁናዊ ሁኔታዎ: **${statusText}**`);
});

bot.command('stats', (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    const stats = db.prepare(`
        SELECT 
            SUM(CASE WHEN purpose = 'Monthly Fee' THEN base_amount ELSE 0 END) as monthly,
            SUM(CASE WHEN purpose = 'Loan Payment' THEN base_amount ELSE 0 END) as loans,
            SUM(penalty_amount) as penalties,
            SUM(total_amount) as grand_total
        FROM payments WHERE status = 'APPROVED'
    `).get();

    ctx.replyWithMarkdown(`💰 **የገንዘብ ሪፖርት**\n\n• መዋጮ፡ **${stats.monthly || 0} ብር**\n• ብድር፡ **${stats.loans || 0} ብር**\n• ቅጣት፡ **${stats.penalties || 0} ብር**\n---\n📢 **አጠቃላይ ካዝና፡ ${stats.grand_total || 0} ብር**`);
});

// --- WEB APP DATA HANDLER ---

bot.on('web_app_data', async (ctx) => {
    const data = JSON.parse(ctx.webAppData.data.json());
    if (data.type === 'payment_report') {
        ctx.session.pendingData = { ...data, userId: ctx.from.id, username: ctx.from.username || 'N/A' };
        await ctx.replyWithMarkdown(`✅ የ**${data.purpose}** መረጃ ተመዝግቧል!\n📍 ቦታ፡ ${data.location}\n\nአሁን ደረሰኝዎን (Screenshot) ይላኩ።`);
    } else if (data.type === 'loan_request') {
        const res = db.prepare(`INSERT INTO loan_requests (user_id, username, amount, duration, reason, timestamp) VALUES (?, ?, ?, ?, ?, ?)`).run(ctx.from.id, ctx.from.username || 'N/A', data.amount, data.duration, data.reason, new Date().toLocaleString());
        await ctx.reply("📩 የብድር ጥያቄዎ ተልኳል።");
        const adminKeyboard = Markup.inlineKeyboard([[Markup.button.callback('✅ ፍቀድ', `lapp_${res.lastInsertRowid}_${ctx.from.id}`), Markup.button.callback('❌ ሰርዝ', `lrej_${res.lastInsertRowid}_${ctx.from.id}`)]]);
        await ctx.telegram.sendMessage(ADMIN_ID, `❓ **አዲስ የብድር ጥያቄ**\n👤 @${ctx.from.username}\n💰 መጠን: ${data.amount} ብር`, adminKeyboard);
    }
});

// --- RECEIPT & ADMIN APPROVALS ---

bot.on(['photo', 'document'], async (ctx) => {
    const pending = ctx.session?.pendingData;
    if (!pending) return ctx.reply("እባክዎ መጀመሪያ ፎርሙን ይሙሉ (ክፍያ ያስገቡ የሚለውን ይጫኑ)።");
    const fileId = ctx.message.photo ? ctx.message.photo.pop().file_id : ctx.message.document.file_id;
    const res = db.prepare(`INSERT INTO payments (user_id, username, purpose, location, base_amount, penalty_amount, total_amount, note, file_id, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).run(pending.userId, pending.username, pending.purpose, pending.location, pending.baseAmount, pending.penaltyAmount, pending.totalAmount, pending.note || '', fileId, new Date().toLocaleString());
    ctx.session.pendingData = null;
    const adminKeyboard = Markup.inlineKeyboard([[Markup.button.callback('✅ ፍቀድ', `papp_${res.lastInsertRowid}_${ctx.from.id}`), Markup.button.callback('❌ ሰርዝ', `prej_${res.lastInsertRowid}_${ctx.from.id}`)]]);
    await ctx.telegram.sendPhoto(ADMIN_ID, fileId, { caption: `🚨 *አዲስ ክፍያ*\n👤 @${pending.username}\n🎯 ${pending.purpose}\n💵 ድምር: ${pending.totalAmount} ብር`, ...adminKeyboard });
    await ctx.reply("📩 ደረሰኝዎ ደርሶናል! አስተዳዳሪው ሲያረጋግጥ መልእክት ይደርስዎታል።");
});

bot.action(/^(papp|prej|lapp|lrej)_(\d+)_(\d+)$/, async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    const [action, id, uId] = [ctx.match[1], ctx.match[2], parseInt(ctx.match[3])];
    const isApprove = action.includes('app');
    const table = action.startsWith('l') ? 'loan_requests' : 'payments';
    db.prepare(`UPDATE ${table} SET status = ? WHERE id = ?`).run(isApprove ? 'APPROVED' : 'REJECTED', id);
    if (action.startsWith('p') && isApprove) db.prepare("UPDATE members SET status = 'APPROVED' WHERE user_id = ?").run(uId);
    await ctx.telegram.sendMessage(uId, isApprove ? "🎉 ጥያቄዎ/ክፍያዎ ጸድቋል!" : "⚠️ ጥያቄዎ/ክፍያዎ ውድቅ ተደርጓል።");
    const resultText = isApprove ? 'APPROVED' : 'REJECTED';
    if (ctx.callbackQuery.message.caption) {
        await ctx.editMessageCaption(`${ctx.callbackQuery.message.caption}\n\n🏁 ውጤት: ${resultText}`);
    } else {
        await ctx.editMessageText(`${ctx.callbackQuery.message.text}\n\n🏁 ውጤት: ${resultText}`);
    }
});

bot.launch().then(() => console.log('Ehuden Befikir Bot active...'));

// Enable graceful stop
process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));