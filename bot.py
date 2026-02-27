/**
 * እሁድን በፍቅር ዲጂታል ፕሮ v3.7.2 - Final Backend Core
 * ለአስተዳዳሪዎች እና ለግሩፕ ማሳወቂያዎች የተመቻቸ
 */

require('dotenv').config();
const { Telegraf, session, Markup } = require('telegraf');
const Database = require('better-sqlite3');
const http = require('http');

// --- 1. RENDER HEALTH CHECK ---
const PORT = process.env.PORT || 3000;
http.createServer((req, res) => {
    res.writeHead(200);
    res.end('Ehuden Befikir Bot is Online');
}).listen(PORT, () => {
    console.log(`📡 Health-check server is running on port ${PORT}`);
});

// --- 2. CONFIGURATION ---
const BOT_TOKEN = process.env.BOT_TOKEN;
const ADMIN_ID = process.env.ADMIN_ID ? parseInt(process.env.ADMIN_ID) : 1062635928;
const TEST_GROUP_ID = process.env.TEST_GROUP_ID ? parseInt(process.env.TEST_GROUP_ID) : null;
const MINI_APP_URL = process.env.MINI_APP_URL;
const DB_FILE = 'edir_pro_final.db';

if (!BOT_TOKEN) {
    console.error("❌ ስህተት: BOT_TOKEN በ Environment Variables ውስጥ አልተገኘም!");
    process.exit(1);
}

// --- 3. DATABASE SETUP ---
const db = new Database(DB_FILE);
db.exec(`
    CREATE TABLE IF NOT EXISTS members (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        tier TEXT DEFAULT 'መሠረታዊ',
        total_savings REAL DEFAULT 0,
        joined_at TEXT
    );
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
        guarantors TEXT,
        file_id TEXT,
        status TEXT DEFAULT 'AWAIT_APPROVAL',
        group_msg_id INTEGER,
        timestamp TEXT
    );
`);

const bot = new Telegraf(BOT_TOKEN);
bot.use(session());

// --- 4. HELPERS ---
const isAdmin = (id) => id === ADMIN_ID;

// ግሩፕ ውስጥ የሚላከውን መልእክት ቅርጽ የሚያስተካክል ፋንክሽን
const formatGroupReport = (p, statusEmoji, statusText) => {
    return `📋 **የክፍያ ሪፖርት**\n` +
           `━━━━━━━━━━━━━━━━━━\n` +
           `👤 **አባል:** @${p.username}\n` +
           `🎯 **ዓላማ:** ${p.purpose}\n` +
           `📅 **ጊዜ:** ${p.period}\n` +
           `💰 **መጠን:** ${p.total_amount} ብር\n` +
           `⚠️ **ቅጣት:** ${p.penalty > 0 ? p.penalty + ' ብር' : 'የለም'}\n` +
           `💳 **መንገድ:** ${p.gateway ? p.gateway.toUpperCase() : 'MANUAL'}\n` +
           `━━━━━━━━━━━━━━━━━━\n` +
           `${statusEmoji} **ሁኔታ:** ${statusText}`;
};

// --- 5. COMMANDS ---

bot.start((ctx) => {
    const now = new Date().toLocaleString('am-ET');
    db.prepare('INSERT OR IGNORE INTO members (user_id, username, full_name, joined_at) VALUES (?, ?, ?, ?)').run(
        ctx.from.id, ctx.from.username || 'N/A', ctx.from.first_name, now
    );
    
    const kb = [[Markup.button.webApp("📱 ሚኒ አፑን ክፈት", MINI_APP_URL)]];
    if (isAdmin(ctx.from.id)) kb.push(["⚙️ የአስተዳዳሪ ሁነታ"]);
    
    ctx.replyWithMarkdown(
        `እንኳን ወደ **እሁድን በፍቅር** መጡ! 👋\n\nከታች ያለውን ሜኑ በመጠቀም የክፍያ ሪፖርት መላክ ወይም ቁጠባዎን ማየት ይችላሉ።`,
        Markup.keyboard(kb).resize()
    );
});

bot.command('id', (ctx) => {
    ctx.replyWithMarkdown(`📌 የዚህ ቻት መለያ (ID): \`${ctx.chat.id}\``);
});

// --- 6. WEB APP DATA HANDLER ---

bot.on('web_app_data', async (ctx) => {
    try {
        const data = JSON.parse(ctx.webAppData.data.json());
        if (data.type === 'payment_report') {
            const time = new Date().toLocaleString('am-ET');
            const guarantorText = data.guarantors && data.guarantors.filter(g => g).length > 0 
                ? data.guarantors.join(', ') 
                : 'የለም';

            ctx.session.pendingPayment = { ...data, guarantors: guarantorText, timestamp: time };

            if (data.gateway === 'manual') {
                await ctx.reply(`✅ የ${data.amount} ብር መረጃ ተመዝግቧል።\n\n📷 እባክዎ የባንክ ደረሰኝዎን (Receipt) ፎቶ አሁን ይላኩ።`);
            } else {
                await ctx.reply(`🚀 የ${data.gateway} ክፍያዎ ተመዝግቧል። ሲረጋገጥ እናሳውቆታለን።`);
            }
        }
    } catch (e) {
        console.error("Processing Error:", e);
    }
});

// --- 7. PHOTO HANDLER ---

bot.on(['photo', 'document'], async (ctx) => {
    const pending = ctx.session?.pendingPayment;
    if (!pending) return;

    const fileId = ctx.message.photo ? ctx.message.photo.pop().file_id : ctx.message.document.file_id;
    const username = ctx.from.username || ctx.from.first_name;

    // 1. ዳታቤዝ መመዝገብ
    const insert = db.prepare(`
        INSERT INTO payments (user_id, username, gateway, purpose, period, total_amount, penalty, pay_for_member, guarantors, file_id, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);
    
    const result = insert.run(
        ctx.from.id, username, pending.gateway, pending.purpose, pending.period, 
        pending.amount, pending.penalty, pending.payFor, pending.guarantors, fileId, pending.timestamp
    );
    const paymentId = result.lastInsertRowid;

    // 2. ለግሩፑ ማሳወቂያ መላክ (Waiting Status)
    let groupMsgId = null;
    if (TEST_GROUP_ID) {
        const reportText = formatGroupReport({
            username: username,
            purpose: pending.purpose,
            period: pending.period,
            total_amount: pending.amount,
            penalty: pending.penalty,
            gateway: pending.gateway
        }, "⏳", "በመጠባበቅ ላይ");

        try {
            const sent = await bot.telegram.sendMessage(TEST_GROUP_ID, reportText, { parse_mode: 'Markdown' });
            groupMsgId = sent.message_id;
            db.prepare("UPDATE payments SET group_msg_id = ? WHERE id = ?").run(groupMsgId, paymentId);
        } catch (e) { console.log("Group notification error"); }
    }

    // 3. ለአስተዳዳሪው ማሳወቂያ መላክ
    const adminMsg = `🚨 **አዲስ የክፍያ ማረጋገጫ ጥያቄ**\n\n👤 አባል: @${username}\n💰 መጠን: ${pending.amount} ብር\n🎯 ዓላማ: ${pending.purpose}`;
    const inlineKb = Markup.inlineKeyboard([
        [Markup.button.callback("✅ አጽድቅ", `app_${paymentId}`), Markup.button.callback("❌ ውድቅ አድርግ", `rej_${paymentId}`)]
    ]);

    await bot.telegram.sendPhoto(ADMIN_ID, fileId, { caption: adminMsg, ...inlineKb });
    
    ctx.session.pendingPayment = null; 
    await ctx.reply(`📩 ደረሰኝዎ ለፋይናንስ ኦፊሰር ተልኳል። እንደተረጋገጠ እናሳውቆታለን!`);
});

// --- 8. ADMIN ACTIONS ---

bot.action(/^(app|rej)_(\d+)$/, async (ctx) => {
    if (!isAdmin(ctx.from.id)) return ctx.answerCbQuery("ፈቃድ የለዎትም!");

    const [_, action, paymentId] = ctx.match;
    const pay = db.prepare("SELECT * FROM payments WHERE id = ?").get(paymentId);
    
    if (!pay) return ctx.answerCbQuery("ክፍያው አልተገኘም!");

    if (action === 'app') {
        db.prepare("UPDATE payments SET status = 'APPROVED' WHERE id = ?").run(paymentId);
        db.prepare("UPDATE members SET total_savings = total_savings + ? WHERE user_id = ?").run(pay.total_amount, pay.user_id);
        
        await bot.telegram.sendMessage(pay.user_id, `✅ የ${pay.total_amount} ብር ክፍያዎ ተረጋግጦ ጽድቋል። እናመሰግናለን!`);
        
        if (TEST_GROUP_ID && pay.group_msg_id) {
            const updatedText = formatGroupReport(pay, "✅", "ተረጋግጦ ጽድቋል");
            await bot.telegram.editMessageText(TEST_GROUP_ID, pay.group_msg_id, null, updatedText, { parse_mode: 'Markdown' }).catch(()=>{});
        }
    } else {
        db.prepare("UPDATE payments SET status = 'REJECTED' WHERE id = ?").run(paymentId);
        await bot.telegram.sendMessage(pay.user_id, `❌ የ${pay.total_amount} ብር ክፍያዎ ውድቅ ተደርጓል። እባክዎ በትክክል ደግመው ይላኩ።`);
        
        if (TEST_GROUP_ID && pay.group_msg_id) {
            const updatedText = formatGroupReport(pay, "❌", "ውድቅ ተደርጓል (Invalid Receipt)");
            await bot.telegram.editMessageText(TEST_GROUP_ID, pay.group_msg_id, null, updatedText, { parse_mode: 'Markdown' }).catch(()=>{});
        }
    }

    await ctx.editMessageCaption(`${ctx.callbackQuery.message.caption}\n\n🏁 **ውሳኔ:** ${action === 'app' ? '✅ ጸድቋል' : '❌ ውድቅ ተደርጓል'}`);
    ctx.answerCbQuery("ተጠናቋል");
});

// --- 9. LAUNCH ---
bot.launch().then(() => console.log("🚀 Bot Backend v3.7.2 is fully operational!"));

process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
