/**
 * እሁድን በፍቅር ዲጂታል ፕሮ v5.6.3 - Penalty Integration
 * ቴክኖሎጂ፡ Telegraf (Telegram Bot API), sqlite (Database), Node.js
 * ማሻሻያ፡ የቅጣት (Penalty) መረጃን በሪፖርት እና በአድሚን ማጠቃለያ ላይ ማካተት
 */

require('dotenv').config();
const { Telegraf, session, Markup } = require('telegraf');
const sqlite3 = require('sqlite3');
const { open } = require('sqlite');
const http = require('http');

// --- 1. HEALTH CHECK SERVER ---
const PORT = process.env.PORT || 3000;
http.createServer((req, res) => {
    res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('EdirPay Enterprise Bot is Operational');
}).listen(PORT, '0.0.0.0');

// --- 2. CONFIGURATION ---
const BOT_TOKEN = process.env.BOT_TOKEN;
const ADMIN_ID = process.env.ADMIN_ID ? parseInt(process.env.ADMIN_ID) : null;
const FINANCE_ID = process.env.FINANCE_ID ? parseInt(process.env.FINANCE_ID) : null;
const TEST_GROUP_ID = process.env.TEST_GROUP_ID ? parseInt(process.env.TEST_GROUP_ID) : null;
const MINI_APP_URL = "https://abiym.github.io/edirpaybot/";
const DB_FILE = 'edir_pro_final.db';

if (!BOT_TOKEN || !ADMIN_ID) {
    console.error("❌ CRITICAL: BOT_TOKEN or ADMIN_ID is missing!");
    process.exit(1);
}

const bot = new Telegraf(BOT_TOKEN);
let db;

// --- 3. DATABASE INITIALIZATION ---
async function initDB() {
    db = await open({
        filename: DB_FILE,
        driver: sqlite3.Database
    });

    await db.exec(`
        CREATE TABLE IF NOT EXISTS members (
            user_id INTEGER PRIMARY KEY, 
            username TEXT, 
            full_name TEXT, 
            balance REAL DEFAULT 0,
            joined_at TEXT
        );
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            tx_id TEXT UNIQUE, 
            user_id INTEGER, 
            username TEXT, 
            purpose TEXT, 
            period TEXT, 
            amount REAL, 
            penalty REAL DEFAULT 0, 
            pay_for TEXT,
            gateway TEXT,
            file_id TEXT, 
            status TEXT DEFAULT 'AWAITING_PHOTO', 
            group_msg_id INTEGER, 
            timestamp TEXT,
            reviewer_name TEXT,
            treasurer_name TEXT
        );
    `);
    console.log("✅ Database and Tables Ready.");
}

// --- 4. HELPERS ---
bot.use(session());

const isReviewer = (id) => id === ADMIN_ID;
const isTreasurer = (id) => id === FINANCE_ID || (id === ADMIN_ID && !FINANCE_ID);
const generateTXID = () => `#EUDE${Math.floor(1000 + Math.random() * 9000)}`;

// የተጠቃሚውን ምሳሌ መሰረት ያደረገ የሪፖርት ፎርማት (ቅጣት ተጨምሮበታል)
const formatPaymentReport = (p, emoji, statusText) => {
    let base = `======= የክፍያ ሪፖርት ${p.tx_id} =======\n\n` +
               `👤 አባል: @${p.username}\n` +
               `🎯 ዓላማ: ${p.purpose}\n` +
               `💰 መጠን: ${p.amount} ብር\n` +
               `⚠️ ቅጣት: ${p.penalty || 0} ብር\n` +
               `💳 መንገድ: ${p.gateway || 'MANUAL'}\n` +
               `📅 ጊዜ: ${p.period}\n` +
               `━━━━━━━━━━━━━━━━━━\n` +
               `${emoji} ሁኔታ: ${statusText}`;
    
    if (p.reviewer_name) base += `\n🔍 መርማሪ: ${p.reviewer_name}`;
    if (p.treasurer_name) base += `\n🏦 ፋይናንስ: ${p.treasurer_name}`;
    
    return base;
};

// --- 5. BOT COMMANDS ---

bot.start(async (ctx) => {
    const time = new Date().toLocaleString('am-ET');
    await db.run(
        'INSERT OR IGNORE INTO members (user_id, username, full_name, joined_at) VALUES (?, ?, ?, ?)',
        ctx.from.id, ctx.from.username || 'N/A', ctx.from.first_name, time
    );

    const text = `ሰላም ${ctx.from.first_name}! 👋 ወደ **እሁድን በፍቅር** ዲጂታል ዕድር እንኳን ደህና መጡ።`;
    const keyboard = { inline_keyboard: [[{ text: "📱 መተግበሪያውን ክፈት", web_app: { url: MINI_APP_URL } }]] };
    return ctx.replyWithMarkdown(text, { reply_markup: keyboard });
});

bot.command('pay', (ctx) => {
    const keyboard = { inline_keyboard: [[{ text: "💳 ክፍያ ይፈጽሙ", web_app: { url: MINI_APP_URL } }]] };
    return ctx.reply(`ክፍያ ለመፈጸም አዝራሩን ይጫኑ፦`, { reply_markup: keyboard });
});

// አስተዳዳሪ ማጠቃለያ (ቅጣት ተጨምሮበታል)
bot.command('admin', async (ctx) => {
    if (!isReviewer(ctx.from.id) && !isTreasurer(ctx.from.id)) return;
    
    const stats = await db.get("SELECT SUM(balance) as total, COUNT(*) as count FROM members");
    const penaltyStats = await db.get("SELECT SUM(penalty) as total_penalty FROM payments WHERE status = 'APPROVED'");
    const pendingCount = await db.get("SELECT COUNT(*) as count FROM payments WHERE status IN ('PENDING_REVIEW', 'PENDING_TREASURY')");

    const report = `📊 **የአስተዳዳሪ ማጠቃለያ**\n━━━━━━━━━━━━━━━━━━\n` +
                   `👥 ጠቅላላ አባላት: ${stats.count}\n` +
                   `💰 ጠቅላላ ቁጠባ: ${stats.total || 0} ብር\n` +
                   `⚠️ ጠቅላላ ቅጣት: ${penaltyStats.total_penalty || 0} ብር\n` +
                   `⏳ የሚጠባበቁ ክፍያዎች: ${pendingCount.count}\n━━━━━━━━━━━━━━━━━━`;
    
    await ctx.replyWithMarkdown(report);
});

bot.command('id', (ctx) => ctx.reply(`የዚህ ቻት ID፦ \`${ctx.chat.id}\``, { parse_mode: 'Markdown' }));

// --- 6. MINI APP DATA HANDLING ---

bot.on('web_app_data', async (ctx) => {
    try {
        const data = JSON.parse(ctx.webAppData.data.json());
        if (data.type === 'payment_report') {
            const txId = generateTXID();
            const timestamp = new Date().toLocaleString('am-ET');
            const gateway = data.gateway ? data.gateway.toUpperCase() : "MANUAL";

            await db.run("DELETE FROM payments WHERE user_id = ? AND status = 'AWAITING_PHOTO'", ctx.from.id);
            await db.run(
                `INSERT INTO payments (tx_id, user_id, username, purpose, period, amount, penalty, pay_for, gateway, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
                txId, ctx.from.id, ctx.from.username || ctx.from.first_name, data.purpose, data.period, data.amount, data.penalty, data.payFor, gateway, timestamp
            );
            await ctx.replyWithMarkdown(`✅ የ${data.amount} ብር መረጃ ተመዝግቧል፦ \`${txId}\`\n\n📷 **አሁን የባንክ ደረሰኝዎን ፎቶ (Screenshot) ይላኩ።**`);
        } 
    } catch (err) { console.error("WebAppData Error:", err); }
});

bot.on(['photo', 'document'], async (ctx) => {
    const pending = await db.get("SELECT * FROM payments WHERE user_id = ? AND status = 'AWAITING_PHOTO' ORDER BY id DESC LIMIT 1", ctx.from.id);
    if (!pending) return;

    const fileId = ctx.message.photo ? ctx.message.photo.pop().file_id : ctx.message.document.file_id;
    try {
        await db.run("UPDATE payments SET status = 'PENDING_REVIEW', file_id = ? WHERE id = ?", fileId, pending.id);

        if (TEST_GROUP_ID) {
            const report = formatPaymentReport(pending, "⏳", "በምርመራ ላይ...");
            const sent = await bot.telegram.sendMessage(TEST_GROUP_ID, report);
            await db.run('UPDATE payments SET group_msg_id = ? WHERE id = ?', sent.message_id, pending.id);
        }

        const reviewerKb = Markup.inlineKeyboard([[Markup.button.callback("✅ ደረሰኝ ትክክል ነው", `rev_app_${pending.id}`), Markup.button.callback("❌ ውድቅ", `rev_rej_${pending.id}`)]]);
        await bot.telegram.sendPhoto(ADMIN_ID, fileId, { 
            caption: `🚨 **ምርመራ**\nID: \`${pending.tx_id}\`\n👤 አባል: @${pending.username}\n💰 መጠን: ${pending.amount} ብር\n⚠️ ቅጣት: ${pending.penalty} ብር`, 
            ...reviewerKb
        });
        await ctx.reply(`📩 ደረሰኝዎ ለምርመራ ደርሷል። ሲረጋገጥ እናሳውቆታለን።`);
    } catch (err) { console.error("Upload Error:", err); }
});

// --- 7. MULTI-TIER APPROVAL ACTIONS ---

bot.action(/^(rev_app|rev_rej|tr_app|tr_rej)_(\d+)$/, async (ctx) => {
    const [tier, action, id] = ctx.match;
    const p = await db.get("SELECT * FROM payments WHERE id = ?", id);
    if (!p) return ctx.answerCbQuery("መረጃው አልተገኘም");

    const adminName = ctx.from.first_name;

    if (tier === 'rev') {
        if (!isReviewer(ctx.from.id)) return ctx.answerCbQuery("ፈቃድ የለዎትም");
        if (action === 'app') {
            await db.run("UPDATE payments SET status = 'PENDING_TREASURY', reviewer_name = ? WHERE id = ?", adminName, id);
            const treasurerKb = Markup.inlineKeyboard([[Markup.button.callback("✅ ባንክ ገብቷል", `tr_app_${id}`), Markup.button.callback("❌ ውድቅ", `tr_rej_${id}`)]]);
            const targetId = FINANCE_ID || ADMIN_ID;
            await bot.telegram.sendPhoto(targetId, p.file_id, { 
                caption: `🏦 **የባንክ ማረጋገጫ**\nID: \`${p.tx_id}\`\n💰 መጠን: ${p.amount} ብር\n⚠️ ቅጣት: ${p.penalty} ብር\n✅ Reviewed by ${adminName}`, 
                ...treasurerKb
            });
            if (TEST_GROUP_ID && p.group_msg_id) {
                const updatedP = await db.get("SELECT * FROM payments WHERE id = ?", id);
                await bot.telegram.editMessageText(TEST_GROUP_ID, p.group_msg_id, null, formatPaymentReport(updatedP, "⏳", "ደረሰኝ ተረጋግጧል፤ ባንክ እየታየ ነው..."));
            }
        } else {
            await db.run("UPDATE payments SET status = 'REJECTED' WHERE id = ?", id);
            await bot.telegram.sendMessage(p.user_id, `❌ ክፍያዎ ውድቅ ተደርጓል! (#${p.tx_id})`);
        }
    }

    if (tier === 'tr') {
        if (!isTreasurer(ctx.from.id)) return ctx.answerCbQuery("ፋይናንስ ብቻ!");
        if (action === 'app') {
            await db.run("UPDATE payments SET status = 'APPROVED', treasurer_name = ? WHERE id = ?", adminName, id);
            // አጠቃላይ የተከፈለው ገንዘብ (መደበኛ + ቅጣት) በባላንስ ላይ ይደመራል
            const totalPaid = (p.amount || 0) + (p.penalty || 0);
            await db.run("UPDATE members SET balance = balance + ? WHERE user_id = ?", totalPaid, p.user_id);
            
            await bot.telegram.sendMessage(p.user_id, `✅ ክፍያዎ ሙሉ በሙሉ ጸድቋል! (#${p.tx_id})\nጠቅላላ ብር፦ ${totalPaid}`);
            
            if (TEST_GROUP_ID && p.group_msg_id) {
                const finalP = await db.get("SELECT * FROM payments WHERE id = ?", id);
                await bot.telegram.editMessageText(TEST_GROUP_ID, p.group_msg_id, null, formatPaymentReport(finalP, "✅", "ተረጋግጦ ጽድቋል"));
            }
        } else {
            await db.run("UPDATE payments SET status = 'REJECTED' WHERE id = ?", id);
            await bot.telegram.sendMessage(p.user_id, `❌ ክፍያዎ ውድቅ ተደርጓል! (#${p.tx_id})`);
        }
    }

    await ctx.editMessageCaption(`${ctx.callbackQuery.message.caption}\n\n🏁 ውሳኔ: ${action === 'app' ? '✅' : '❌'} በ: ${adminName}`);
    ctx.answerCbQuery("ተጠናቋል");
});

async function start() {
    try {
        await initDB();
        await bot.telegram.deleteWebhook({ drop_pending_updates: true });
        await bot.launch({ dropPendingUpdates: true });
        console.log("🚀 EdirPay Enterprise v5.6.3 Online!");
    } catch (err) { console.error("❌ Startup Failed:", err); }
}
start();
