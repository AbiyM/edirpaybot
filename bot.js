/**
 * እሁድን በፍቅር ዲጂታል ፕሮ v5.7.4 - Group Menu & Station Expert
 * ቴክኖሎጂ፡ Telegraf (Telegram Bot API), sqlite (Database), Node.js
 * ማሻሻያ፡ በግሩፕ ውስጥ እንደ ሜኑ አዝራር የሚያገለግል የ'Pay Here' ጣቢያ እና የ'/setup' መመሪያ ተጨምሯል
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

// --- 4. HELPERS & LOGGING ---
bot.use(session());

bot.catch((err, ctx) => {
    console.error(`❌ Bot Logic Error [${ctx.updateType}]:`, err);
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

// --- 5. INLINE MODE HANDLER ---

bot.on('inline_query', async (ctx) => {
    const results = [
        {
            type: 'article',
            id: 'pay_now',
            title: '💳 ክፍያ ይፈጽሙ (Pay Now)',
            description: 'የእሁድን በፍቅር ሚኒ አፕ በመጠቀም ክፍያ ለመፈጸም እዚህ ይጫኑ',
            input_message_content: { message_text: `ሰላም! የዕድር ክፍያ ለመፈጸም ከታች ያለውን አዝራር ይጠቀሙ።` },
            reply_markup: { inline_keyboard: [[{ text: "📱 ሚኒ አፑን ክፈት", web_app: { url: MINI_APP_URL } }]] },
            thumb_url: 'https://cdn-icons-png.flaticon.com/512/10149/10149458.png'
        }
    ];
    return await ctx.answerInlineQuery(results, { cache_time: 0 });
});

// --- 6. BOT COMMANDS ---

// ቦቱ ወደ ግሩፕ ሲገባ የሚላክ ሰላምታ
bot.on('new_chat_members', async (ctx) => {
    const isBotAdded = ctx.message.new_chat_members.some(m => m.id === ctx.botInfo.id);
    if (isBotAdded) {
        const text = `ሰላም! 🖐 እኔ **የእሁድን በፍቅር** ዲጂታል ዕድር ቦት ነኝ።\n\n` +
                     `አባላት በዚህ ግሩፕ ውስጥ ሆነው ክፍያ ለመፈጸም እንዲችሉ እባክዎ **Admin** ያድርጉኝ።\n\n` +
                     `ለመጀመር፦ /setup ብለው ይላኩ።`;
        return ctx.replyWithMarkdown(text);
    }
});

bot.start(async (ctx) => {
    try {
        const time = new Date().toLocaleString('am-ET');
        await db.run(
            'INSERT OR IGNORE INTO members (user_id, username, full_name, joined_at) VALUES (?, ?, ?, ?)',
            ctx.from.id, ctx.from.username || 'N/A', ctx.from.first_name, time
        );
        const text = `ሰላም ${ctx.from.first_name}! 👋 ወደ **እሁድን በፍቅር** ዲጂታል ዕድር እንኳን ደህና መጡ።`;
        return await ctx.replyWithMarkdown(text, {
            reply_markup: { inline_keyboard: [[{ text: "📱 መተግበሪያውን ክፈት", web_app: { url: MINI_APP_URL } }]] }
        });
    } catch (e) { console.error("Start Error:", e); }
});

// [SETUP COMMAND] - ለግሩፕ አድሚኖች መመሪያ
bot.command('setup', async (ctx) => {
    const text = `⚙️ **የግሩፕ አቀነባበር መመሪያ**\n━━━━━━━━━━━━━━━━━━\n` +
                 `ቦቱ በግሩፕ ውስጥ እንደ "ሜኑ አዝራር" ሆኖ እንዲያገለግል እነዚህን 2 ደረጃዎች ይከተሉ፦\n\n` +
                 `1️⃣ **አስተዳዳሪ ያድርጉኝ፦** ቦቱ መልዕክቶችን የማንበብ እና የማጥፋት መብት ያለው አድሚን መሆን አለበት።\n\n` +
                 `2️⃣ **ጣቢያውን ይፍጠሩ፦** በግሩፕ ውስጥ \`/payhere\` ብለው ይላኩ። የሚመጣውን መልዕክት **Pin** በማድረግ አባላት ሁልጊዜ እንዲያገኙት ያድርጉ።\n\n` +
                 `3️⃣ **Command Menu፦** በ @BotFather በኩል 'Edit Commands' በማድረግ 'pay' እና 'payhere' የሚሉትን ይጨምሩ።`;
    return ctx.replyWithMarkdown(text);
});

// [PAYHERE STATION] - የግሩፑ 'ሜኑ አዝራር'
bot.command('payhere', async (ctx) => {
    const stationText = `🏦 **የእሁድን በፍቅር ዲጂታል ዕድር ጣቢያ**\n` +
                        `━━━━━━━━━━━━━━━━━━\n` +
                        `ሰላም አባላት! 👋 በዚህ ግሩፕ ውስጥ ክፍያ ለመፈጸም ወይም ቁጠባዎን ለማየት ከታች ያለውን አዝራር ይጠቀሙ።\n\n` +
                        `💡 **ማሳሰቢያ፦** መረጃውን ከላኩ በኋላ ደረሰኝዎን ለቦቱ (@${ctx.botInfo.username}) በግል መላክዎን አይርሱ።\n` +
                        `━━━━━━━━━━━━━━━━━━`;
    try {
        await ctx.replyWithMarkdown(stationText, {
            reply_markup: { inline_keyboard: [[{ text: "💳 ክፍያ ይፈጽሙ / ሚኒ አፕ", web_app: { url: MINI_APP_URL } }]] }
        });
        return ctx.reply("☝️ **የክፍያ ጣቢያው ተፈጥሯል። አባላት በቀላሉ እንዲያገኙት እባክዎ ይህንን መልዕክት ፒን (Pin) ያድርጉት።**");
    } catch (e) {
        console.error("PayHere Error:", e);
        return ctx.reply("❌ አዝራሩን መላክ አልተቻለም። ቦቱ አድሚን መሆኑን ያረጋግጡ።");
    }
});

bot.command('pay', async (ctx) => {
    try {
        return await ctx.reply(`ሰላም ${ctx.from.first_name}! ክፍያ ለመፈጸም ከታች ያለውን አዝራር ይጫኑ፦`, {
            reply_markup: { inline_keyboard: [[{ text: "💳 ክፍያ ይፈጽሙ", web_app: { url: MINI_APP_URL } }]] }
        });
    } catch (e) {
        console.error("Pay Error:", e);
        return ctx.reply("❌ እባክዎ ቦቱን በግል ቻት ያነጋግሩ።");
    }
});

bot.command('admin', async (ctx) => {
    if (!isReviewer(ctx.from.id) && !isTreasurer(ctx.from.id)) return;
    try {
        const stats = await db.get("SELECT SUM(balance) as total, COUNT(*) as count FROM members");
        const pStats = await db.get("SELECT SUM(penalty) as tp FROM payments WHERE status = 'APPROVED'");
        const pending = await db.get("SELECT COUNT(*) as count FROM payments WHERE status IN ('PENDING_REVIEW', 'PENDING_TREASURY')");
        await ctx.replyWithMarkdown(`📊 **የአስተዳዳሪ ማጠቃለያ**\n━━━━━━━━━━━━━━━━━━\n👥 አባላት: ${stats.count}\n💰 ቁጠባ: ${stats.total || 0} ብር\n⚠️ ቅጣት: ${pStats.tp || 0} ብር\n⏳ ጥያቄዎች: ${pending.count}`);
    } catch (e) { console.error("Admin Error:", e); }
});

bot.command('id', async (ctx) => ctx.reply(`Chat ID: \`${ctx.chat.id}\``, { parse_mode: 'Markdown' }));

// --- 7. DATA & MEDIA HANDLING ---

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
            await ctx.replyWithMarkdown(`✅ የ${data.amount} ብር መረጃ ተመዝግቧል፦ \`${txId}\`\n\n📷 **አሁን ደረሰኝዎን (Screenshot) ይላኩ።**`);
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
        await ctx.reply(`📩 ደረሰኝዎ ለምርመራ ደርሷል። ሲጸድቅ እናሳውቆታለን።`);
    } catch (err) { console.error("Upload Error:", err); }
});

// --- 8. APPROVAL ACTIONS ---

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
                    await bot.telegram.editMessageText(TEST_GROUP_ID, p.group_msg_id, null, formatPaymentReport(up, "⏳", "ደረሰኝ ተረጋግጧል፤ ባንክ እየታየ ነው..."));
                }
            } else {
                await db.run("UPDATE payments SET status = 'REJECTED' WHERE id = ?", id);
                await bot.telegram.sendMessage(p.user_id, `❌ ክፍያዎ ውድቅ ተደርጓል (#${p.tx_id})`);
            }
        }
        if (tier === 'tr') {
            if (!isTreasurer(ctx.from.id)) return ctx.answerCbQuery("Finance only");
            if (action === 'app') {
                await db.run("UPDATE payments SET status = 'APPROVED', treasurer_name = ? WHERE id = ?", adminName, id);
                const total = (p.amount || 0) + (p.penalty || 0);
                await db.run("UPDATE members SET balance = balance + ? WHERE user_id = ?", total, p.user_id);
                await bot.telegram.sendMessage(p.user_id, `✅ ክፍያዎ ጽድቋል (#${p.tx_id})\nአጠቃላይ ብር፦ ${total}`);
                if (TEST_GROUP_ID && p.group_msg_id) {
                    const final = await db.get("SELECT * FROM payments WHERE id = ?", id);
                    await bot.telegram.editMessageText(TEST_GROUP_ID, p.group_msg_id, null, formatPaymentReport(final, "✅", "ተረጋግጦ ጽድቋል"));
                }
            } else {
                await db.run("UPDATE payments SET status = 'REJECTED' WHERE id = ?", id);
                await bot.telegram.sendMessage(p.user_id, `❌ ክፍያዎ ውድቅ ተደርጓል (#${p.tx_id})`);
            }
        }
        await ctx.editMessageCaption(`${ctx.callbackQuery.message.caption}\n🏁 ውሳኔ: ${action} በ: ${adminName}`);
        ctx.answerCbQuery("Done");
    } catch (e) { console.error("Action Error:", e); }
});

// --- 9. STARTUP & CONFLICT RESOLUTION ---
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function startBot(retries = 10) {
    try {
        await initDB();
        console.log("🧹 Webhook ማጽዳት...");
        await bot.telegram.deleteWebhook({ drop_pending_updates: true });
        
        // በግሩፕ ውስጥ የሚታዩ ትዕዛዞችን ማዘጋጀት
        await bot.telegram.setMyCommands([
            { command: 'pay', description: 'ክፍያ ለመጀመር' },
            { command: 'payhere', description: 'የክፍያ ጣቢያ በግሩፕ ለመፍጠር' },
            { command: 'setup', description: 'የግሩፕ አቀነባበር መመሪያ' },
            { command: 'admin', description: 'የአስተዳዳሪ ማጠቃለያ' }
        ]);

        console.log("⏳ ኮኔክሽን በማስተካከል ላይ...");
        await sleep(6000); 
        await bot.launch({ dropPendingUpdates: true });
        console.log("🚀 EdirPay Enterprise v5.7.4 Online!");
    } catch (err) {
        if (err.response && err.response.error_code === 409 && retries > 0) {
            console.warn(`⚠️ Conflict. Retrying in 10s... (${retries} left)`);
            await sleep(10000);
            return startBot(retries - 1);
        }
        console.error("❌ Fatal Startup Error:", err);
    }
}
startBot();

process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
