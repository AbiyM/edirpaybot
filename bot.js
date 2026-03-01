/**
 * እሁድን በፍቅር ዲጂታል ፕሮ v5.6.7 - Handled Error & Group Fix
 * ቴክኖሎጂ፡ Telegraf (Telegram Bot API), sqlite (Database), Node.js
 * ማሻሻያ፡ Unhandled error ስህተትን ለመፍታት bot.catch መጨመር እና የግሩፕ አዝራር ማስተካከያ
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
const MINI_APP_URL = process.env.MINI_APP_URL || "https://abiym.github.io/edirpaybot/";
const DB_FILE = process.env.DISK_PATH ? `${process.env.DISK_PATH}/edir_pro_final.db` : 'edir_pro_final.db';

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
    console.log("✅ Database Ready.");
}

// --- 4. HELPERS & ERROR HANDLING ---
bot.use(session());

// [GLOBAL ERROR HANDLER] ቦቱ እንዳይቆም እና ስህተቱን እንዲያሳይ
bot.catch((err, ctx) => {
    console.error(`❌ Telegraf Error for ${ctx.updateType}:`, err);
});

bot.use(async (ctx, next) => {
    if (ctx.message && ctx.message.text) {
        console.log(`[INCOMING] ${ctx.chat.type}: ${ctx.message.text} from ${ctx.from.id}`);
    }
    return next();
});

const isReviewer = (id) => id === ADMIN_ID;
const isTreasurer = (id) => id === FINANCE_ID || (id === ADMIN_ID && !FINANCE_ID);
const generateTXID = () => `#EUDE${Math.floor(1000 + Math.random() * 9000)}`;

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
    try {
        const time = new Date().toLocaleString('am-ET');
        await db.run(
            'INSERT OR IGNORE INTO members (user_id, username, full_name, joined_at) VALUES (?, ?, ?, ?)',
            ctx.from.id, ctx.from.username || 'N/A', ctx.from.first_name, time
        );
        const text = `ሰላም ${ctx.from.first_name}! 👋 ወደ **እሁድን በፍቅር** ዲጂታል ዕድር እንኳን ደህና መጡ።`;
        return ctx.replyWithMarkdown(text, Markup.inlineKeyboard([
            [Markup.button.webApp("📱 መተግበሪያውን ክፈት", MINI_APP_URL)]
        ]));
    } catch (e) { console.error("Start Error:", e); }
});

bot.command('pay', async (ctx) => {
    console.log(`[PAY] Triggered in ${ctx.chat.id}`);
    try {
        const text = `ሰላም ${ctx.from.first_name}! ክፍያ ለመፈጸም ከታች ያለውን አዝራር ይጫኑ፦`;
        // በግሩፕ ውስጥ የዌብ አፕ አዝራር እንዲሰራ ጥንቃቄ የተሞላበት አወቃቀር
        return await ctx.reply(text, Markup.inlineKeyboard([
            [Markup.button.webApp("💳 ክፍያ ይፈጽሙ", MINI_APP_URL)]
        ]));
    } catch (e) {
        console.error("Pay Command Error:", e);
        return ctx.reply("❌ አዝራሩን መላክ አልተቻለም። እባክዎ ቦቱን በግል ቻት ያነጋግሩ ወይም አድሚን መሆኑን ያረጋግጡ።");
    }
});

bot.command('admin', async (ctx) => {
    if (!isReviewer(ctx.from.id) && !isTreasurer(ctx.from.id)) return;
    try {
        const stats = await db.get("SELECT SUM(balance) as total, COUNT(*) as count FROM members");
        const pStats = await db.get("SELECT SUM(penalty) as tp FROM payments WHERE status = 'APPROVED'");
        const pending = await db.get("SELECT COUNT(*) as count FROM payments WHERE status IN ('PENDING_REVIEW', 'PENDING_TREASURY')");
        await ctx.replyWithMarkdown(`📊 **የአስተዳዳሪ ማጠቃለያ**\n━━━━━━━━━━━━━━━━━━\n👥 አባላት: ${stats.count}\n💰 ቁጠባ: ${stats.total || 0} ብር\n⚠️ ቅጣት: ${pStats.tp || 0} ብር\n⏳ ጥያቄዎች: ${pending.count}`);
    } catch (e) { console.error("Admin Command Error:", e); }
});

bot.command('id', (ctx) => ctx.reply(`ID: \`${ctx.chat.id}\``, { parse_mode: 'Markdown' }));

// --- 6. DATA & MEDIA HANDLING ---

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
            await ctx.replyWithMarkdown(`✅ የ${data.amount} ብር መረጃ ተመዝግቧል፦ \`${txId}\`\n\n📷 **አሁን ደረሰኝዎን ይላኩ።**`);
        } 
    } catch (err) { console.error("WebAppData Error:", err); }
});

bot.on(['photo', 'document'], async (ctx) => {
    try {
        const pending = await db.get("SELECT * FROM payments WHERE user_id = ? AND status = 'AWAITING_PHOTO' ORDER BY id DESC LIMIT 1", ctx.from.id);
        if (!pending) return;
        const fileId = ctx.message.photo ? ctx.message.photo.pop().file_id : ctx.message.document.file_id;
        await db.run("UPDATE payments SET status = 'PENDING_REVIEW', file_id = ? WHERE id = ?", fileId, pending.id);
        if (TEST_GROUP_ID) {
            const report = formatPaymentReport(pending, "⏳", "በምርመራ ላይ...");
            const sent = await bot.telegram.sendMessage(TEST_GROUP_ID, report);
            await db.run('UPDATE payments SET group_msg_id = ? WHERE id = ?', sent.message_id, pending.id);
        }
        const revKb = Markup.inlineKeyboard([[Markup.button.callback("✅ አጽድቅ", `rev_app_${pending.id}`), Markup.button.callback("❌ ውድቅ", `rev_rej_${pending.id}`)]]);
        await bot.telegram.sendPhoto(ADMIN_ID, fileId, { caption: `🚨 ምርመራ: ${pending.tx_id}`, ...revKb });
        await ctx.reply(`📩 ደረሰኝዎ ለምርመራ ደርሷል።`);
    } catch (err) { console.error("Upload Error:", err); }
});

// --- 7. APPROVAL ACTIONS ---

bot.action(/^(rev_app|rev_rej|tr_app|tr_rej)_(\d+)$/, async (ctx) => {
    try {
        const [tier, action, id] = ctx.match;
        const p = await db.get("SELECT * FROM payments WHERE id = ?", id);
        if (!p) return ctx.answerCbQuery("Not found");
        const adminName = ctx.from.first_name;

        if (tier === 'rev') {
            if (!isReviewer(ctx.from.id)) return ctx.answerCbQuery("Denied");
            if (action === 'app') {
                await db.run("UPDATE payments SET status = 'PENDING_TREASURY', reviewer_name = ? WHERE id = ?", adminName, id);
                const trKb = Markup.inlineKeyboard([[Markup.button.callback("✅ ባንክ ገብቷል", `tr_app_${id}`), Markup.button.callback("❌ ውድቅ", `tr_rej_${id}`)]]);
                await bot.telegram.sendPhoto(FINANCE_ID || ADMIN_ID, p.file_id, { caption: `🏦 ባንክ ማረጋገጫ: ${p.tx_id}\n✅ Reviewed by ${adminName}`, ...trKb });
                if (TEST_GROUP_ID && p.group_msg_id) {
                    const up = await db.get("SELECT * FROM payments WHERE id = ?", id);
                    await bot.telegram.editMessageText(TEST_GROUP_ID, p.group_msg_id, null, formatPaymentReport(up, "⏳", "ባንክ እየታየ ነው..."));
                }
            } else {
                await db.run("UPDATE payments SET status = 'REJECTED' WHERE id = ?", id);
                await bot.telegram.sendMessage(p.user_id, `❌ ውድቅ ተደርጓል (#${p.tx_id})`);
            }
        }
        if (tier === 'tr') {
            if (!isTreasurer(ctx.from.id)) return ctx.answerCbQuery("Finance only");
            if (action === 'app') {
                await db.run("UPDATE payments SET status = 'APPROVED', treasurer_name = ? WHERE id = ?", adminName, id);
                const total = (p.amount || 0) + (p.penalty || 0);
                await db.run("UPDATE members SET balance = balance + ? WHERE user_id = ?", total, p.user_id);
                await bot.telegram.sendMessage(p.user_id, `✅ ጽድቋል (#${p.tx_id})\nብር፦ ${total}`);
                if (TEST_GROUP_ID && p.group_msg_id) {
                    const final = await db.get("SELECT * FROM payments WHERE id = ?", id);
                    await bot.telegram.editMessageText(TEST_GROUP_ID, p.group_msg_id, null, formatPaymentReport(final, "✅", "ጽድቋል"));
                }
            } else {
                await db.run("UPDATE payments SET status = 'REJECTED' WHERE id = ?", id);
            }
        }
        await ctx.editMessageCaption(`${ctx.callbackQuery.message.caption}\n🏁 ውሳኔ: ${action} በ: ${adminName}`);
        ctx.answerCbQuery("OK");
    } catch (e) { console.error("Action Error:", e); }
});

// --- 8. STARTUP ---
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function startBot(retries = 10) {
    try {
        await initDB();
        console.log("🧹 Clearing Webhooks...");
        await bot.telegram.deleteWebhook({ drop_pending_updates: true });
        console.log("⏳ Cooling down...");
        await sleep(6000); 
        await bot.launch({ dropPendingUpdates: true });
        console.log("🚀 EdirPay Enterprise v5.6.7 Online!");
    } catch (err) {
        if (err.response && err.response.error_code === 409 && retries > 0) {
            console.warn(`⚠️ Conflict. Retrying... (${retries})`);
            await sleep(10000);
            return startBot(retries - 1);
        }
        console.error("❌ Fatal Startup Error:", err);
    }
}
startBot();
