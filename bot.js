/**
 * እሁድን በፍቅር ዲጂታል ፕሮ v5.4.2 - JavaScript (Node.js) Backend
 * ቴክኖሎጂ፡ Telegraf, sqlite3, Node.js
 * ባህሪያት፡ Multi-admin, Render-compatible DB, Group Reporting
 */

require('dotenv').config();
const { Telegraf, session, Markup } = require('telegraf');
const sqlite3 = require('sqlite3');
const { open } = require('sqlite');
const http = require('http');

// --- 1. የጤና ፍተሻ ሰርቨር (Render Health Check) ---
const PORT = process.env.PORT || 3000;
http.createServer((req, res) => {
    res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' });
    const status = (process.env.BOT_TOKEN && process.env.ADMIN_ID) ? "ACTIVE" : "CONFIG_MISSING";
    res.end(`EdirPay Bot Status: ${status}`);
}).listen(PORT, '0.0.0.0');

// --- 2. ኮንፊገሬሽን ፍተሻ ---
const BOT_TOKEN = process.env.BOT_TOKEN;
const ADMIN_ID = process.env.ADMIN_ID ? parseInt(process.env.ADMIN_ID) : null;
const FINANCE_ID = process.env.FINANCE_ID ? parseInt(process.env.FINANCE_ID) : null;
const TEST_GROUP_ID = process.env.TEST_GROUP_ID ? parseInt(process.env.TEST_GROUP_ID) : null;
const MINI_APP_URL = "https://abiym.github.io/edirpaybot/";
const DB_FILE = 'edir_pro_final.db';

if (!BOT_TOKEN || !ADMIN_ID) {
    console.error("❌ CRITICAL: Environment Variables (BOT_TOKEN/ADMIN_ID) are missing!");
    process.exit(1);
}

const bot = new Telegraf(BOT_TOKEN);
let db;

// --- 3. ዳታቤዝ ዝግጅት ---
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
            guarantors TEXT, 
            file_id TEXT, 
            status TEXT DEFAULT 'AWAITING_PHOTO', 
            group_msg_id INTEGER, 
            timestamp TEXT
        );
    `);
    console.log("✅ Database Ready (sqlite3).");
}

// --- 4. Helpers ---
bot.use(session());

const isAuthorized = (id) => id === ADMIN_ID || id === FINANCE_ID;
const generateTXID = () => `#EUDE${Math.floor(1000 + Math.random() * 9000)}`;

const formatGroupReport = (p, emoji, statusText) => {
    return `📋 **የክፍያ ሪፖርት ${p.tx_id}**\n━━━━━━━━━━━━━━━━━━\n👤 **አባል:** @${p.username}\n🎯 **ዓላማ:** ${p.purpose}\n📅 **ጊዜ:** ${p.period}\n💰 **መጠን:** ${p.amount} ብር\n🛡 **ዋሶች:** ${p.guarantors || 'የለም'}\n━━━━━━━━━━━━━━━━━━\n${emoji} **ሁኔታ:** ${statusText}`;
};

// --- 5. ቦት ትዕዛዞች (Commands) ---

bot.start(async (ctx) => {
    const time = new Date().toLocaleString('am-ET');
    await db.run(
        'INSERT OR IGNORE INTO members (user_id, username, full_name, joined_at) VALUES (?, ?, ?, ?)',
        ctx.from.id, ctx.from.username || 'N/A', ctx.from.first_name, time
    );

    const text = `ሰላም ${ctx.from.first_name}! 👋\nወደ **እሁድን በፍቅር** ዲጂታል ዕድር በደህና መጡ።\n\nእባክዎ ክፍያ ለመፈጸም ከታች ያለውን አዝራር ይጠቀሙ።`;
    
    if (ctx.chat.type !== 'private') {
        return ctx.replyWithMarkdown(text, Markup.inlineKeyboard([[Markup.button.webApp("📱 ሚኒ አፑን ክፈት", MINI_APP_URL)]]));
    }
    return ctx.replyWithMarkdown(text, Markup.keyboard([[Markup.button.webApp("📱 ሚኒ አፑን ክፈት", MINI_APP_URL)]]).resize());
});

bot.command('admin', async (ctx) => {
    if (!isAuthorized(ctx.from.id)) return;
    const stats = await db.get("SELECT SUM(balance) as total, COUNT(*) as count FROM members");
    const pendingCount = await db.get("SELECT COUNT(*) as count FROM payments WHERE status = 'PENDING'");
    await ctx.replyWithMarkdown(`📊 **የዕድር መረጃ**\n👥 አባላት: ${stats.count}\n💰 ጠቅላላ: ${stats.total || 0} ብር\n⏳ በመጠባበቅ: ${pendingCount.count}`);
});

bot.command('pay', (ctx) => ctx.reply(`ክፍያ ለመፈጸም አዝራሩን ይጫኑ፦`, Markup.inlineKeyboard([[Markup.button.webApp('💳 ክፍያ ይፈጽሙ', MINI_APP_URL)]])));

bot.command('id', (ctx) => ctx.reply(`የዚህ ቻት ID፦ \`${ctx.chat.id}\``, { parse_mode: 'Markdown' }));

// --- 6. የክፍያ ሂደት (Payment Logic) ---

bot.on('web_app_data', async (ctx) => {
    try {
        const data = JSON.parse(ctx.webAppData.data.json());
        const txId = generateTXID();
        const timestamp = new Date().toLocaleString('am-ET');
        const guarantors = data.guarantors ? data.guarantors.filter(g => g).join(', ') : "የለም";

        await db.run("DELETE FROM payments WHERE user_id = ? AND status = 'AWAITING_PHOTO'", ctx.from.id);
        await db.run(
            `INSERT INTO payments (tx_id, user_id, username, purpose, period, amount, penalty, guarantors, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
            txId, ctx.from.id, ctx.from.username || ctx.from.first_name, data.purpose, data.period, data.amount, data.penalty, guarantors, timestamp
        );
        await ctx.replyWithMarkdown(`✅ የ${data.amount} ብር መረጃ ተመዝግቧል፦ \`${txId}\`\n\n📷 **አሁን የባንክ ደረሰኝዎን ፎቶ ይላኩ።**`);
    } catch (err) { console.error("WebAppData Error:", err); }
});

bot.on(['photo', 'document'], async (ctx) => {
    const pending = await db.get("SELECT * FROM payments WHERE user_id = ? AND status = 'AWAITING_PHOTO' ORDER BY id DESC LIMIT 1", ctx.from.id);
    if (!pending) return;

    const fileId = ctx.message.photo ? ctx.message.photo.pop().file_id : ctx.message.document.file_id;
    try {
        await db.run("UPDATE payments SET status = 'PENDING', file_id = ? WHERE id = ?", fileId, pending.id);

        if (TEST_GROUP_ID) {
            const report = formatGroupReport(pending, "⏳", "በመጠባበቅ ላይ");
            bot.telegram.sendMessage(TEST_GROUP_ID, report, { parse_mode: 'Markdown' }).then(async (sent) => {
                await db.run('UPDATE payments SET group_msg_id = ? WHERE id = ?', sent.message_id, pending.id);
            }).catch(()=>{});
        }

        const adminKb = Markup.inlineKeyboard([[Markup.button.callback("✅ አጽድቅ", `app_${pending.id}`), Markup.button.callback("❌ ውድቅ", `rej_${pending.id}`)]]);
        const adminMsg = `🚨 **አዲስ የክፍያ ጥያቄ**\nID: \`${pending.tx_id}\`\n👤 አባል: @${pending.username}\n💰 መጠን: ${pending.amount} ብር`;
        
        await bot.telegram.sendPhoto(ADMIN_ID, fileId, { caption: adminMsg, ...adminKb, parse_mode: 'Markdown' });
        if (FINANCE_ID && FINANCE_ID !== ADMIN_ID) {
            await bot.telegram.sendPhoto(FINANCE_ID, fileId, { caption: adminMsg, ...adminKb, parse_mode: 'Markdown' });
        }
        await ctx.reply(`📩 ደረሰኝዎ ለፋይናንስ ኦፊሰር ደርሷል። ሲረጋገጥ እናሳውቆታለን።`);
    } catch (err) { console.error("Photo Error:", err); }
});

bot.action(/^(app|rej)_(\d+)$/, async (ctx) => {
    if (!isAuthorized(ctx.from.id)) return ctx.answerCbQuery("Denied");
    const [_, action, id] = ctx.match;
    const p = await db.get("SELECT * FROM payments WHERE id = ?", id);
    if (!p || p.status !== 'PENDING') return ctx.answerCbQuery("Done");

    if (action === 'app') {
        await db.run("UPDATE payments SET status = 'APPROVED' WHERE id = ?", id);
        await db.run("UPDATE members SET balance = balance + ? WHERE user_id = ?", p.amount, p.user_id);
        await bot.telegram.sendMessage(p.user_id, `✅ ክፍያዎ ጽድቋል! (#${p.tx_id})`);
        if (TEST_GROUP_ID && p.group_msg_id) await bot.telegram.editMessageText(TEST_GROUP_ID, p.group_msg_id, null, formatGroupReport(p, "✅", "ተረጋግጦ ጽድቋል"), { parse_mode: 'Markdown' }).catch(()=>{});
    } else {
        await db.run("UPDATE payments SET status = 'REJECTED' WHERE id = ?", id);
        await bot.telegram.sendMessage(p.user_id, `❌ ክፍያዎ ውድቅ ተደርጓል! (#${p.tx_id})`);
    }
    await ctx.editMessageCaption(`${ctx.callbackQuery.message.caption}\n\n🏁 ውሳኔ: ${action === 'app' ? '✅' : '❌'}\n👤 በ፡ ${ctx.from.first_name}`);
    ctx.answerCbQuery("Done");
});

// --- 7. ቦቱን የማስነሻ ተግባር ---
async function start() {
    try {
        await initDB();
        await bot.telegram.deleteWebhook({ drop_pending_updates: true });
        await bot.launch();
        console.log("🚀 EdirPay Bot Online (bot.js)!");
    } catch (err) {
        console.error("❌ Startup Failed:", err);
    }
}

start();

process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
