/**
 * እሁድን በፍቅር ዲጂታል ፕሮ v4.9.2 - Final Group Fix
 * ቴሌግራም ግሩፕ ላይ ትዕዛዞች ምላሽ ካልሰጡ ይህን ስሪት ይጠቀሙ
 */

require('dotenv').config();
const { Telegraf, session, Markup } = require('telegraf');
const Database = require('better-sqlite3');
const http = require('http');

// --- 1. የጤና ፍተሻ ሰርቨር (ለRender ስኬታማ ዲፕሎይመንት) ---
const PORT = process.env.PORT || 3000;
http.createServer((req, res) => {
    res.writeHead(200);
    res.end('EdirPay Bot is Online and Listening');
}).listen(PORT);

// --- 2. ኮንፊገሬሽን (Configuration) ---
const BOT_TOKEN = process.env.BOT_TOKEN;
const ADMIN_ID = process.env.ADMIN_ID ? parseInt(process.env.ADMIN_ID) : null;
const TEST_GROUP_ID = process.env.TEST_GROUP_ID ? parseInt(process.env.TEST_GROUP_ID) : null;
const MINI_APP_URL = process.env.MINI_APP_URL || "https://abiym.github.io/edirpaybot/";
const DB_FILE = 'edir_pro_final.db';

if (!BOT_TOKEN || !ADMIN_ID) {
    console.error("❌ ስህተት፡ BOT_TOKEN ወይም ADMIN_ID አልተገኘም!");
    process.exit(1);
}

// --- 3. ዳታቤዝ ዝግጅት (Database Setup) ---
const db = new Database(DB_FILE);
db.exec(`
    CREATE TABLE IF NOT EXISTS members (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        balance REAL DEFAULT 0
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
        status TEXT DEFAULT 'PENDING',
        group_msg_id INTEGER,
        timestamp TEXT
    );
`);

const bot = new Telegraf(BOT_TOKEN);
bot.use(session());

// --- 4. ረዳት ተግባራት (Helpers) ---
const isAdmin = (id) => id === ADMIN_ID;
const generateTXID = () => `#EUDE${Math.floor(1000 + Math.random() * 9000)}`;

// የግሩፕ ሪፖርት ፎርማት
const formatGroupReport = (p, emoji, statusText) => {
    return `📋 **የክፍያ ሪፖርት ${p.tx_id}**\n` +
           `━━━━━━━━━━━━━━━━━━\n` +
           `👤 **አባል:** @${p.username}\n` +
           `🎯 **ዓላማ:** ${p.purpose}\n` +
           `📅 **ጊዜ:** ${p.period}\n` +
           `💰 **መጠን:** ${p.amount} ብር\n` +
           `🛡 **ዋሶች:** ${p.guarantors || 'የለም'}\n` +
           `━━━━━━━━━━━━━━━━━━\n` +
           `${emoji} **ሁኔታ:** ${statusText}`;
};

// --- 5. ቦት ትዕዛዞች (Handlers) ---

// ግሩፕ ውስጥ የሚላኩ መልዕክቶችን ለመከታተል (Debug Logger)
bot.on('message', (ctx, next) => {
    if (ctx.chat.type === 'group' || ctx.chat.type === 'supergroup') {
        console.log(`[DEBUG LOG] Message in Group (${ctx.chat.id}): "${ctx.message.text || 'Not Text'}" From: ${ctx.from.username || ctx.from.id}`);
    }
    return next();
});

// START ትዕዛዝ (ለግል ቻት)
bot.start((ctx) => {
    const time = new Date().toLocaleString('am-ET');
    db.prepare('INSERT OR IGNORE INTO members (user_id, username) VALUES (?, ?)').run(ctx.from.id, ctx.from.username || 'N/A');

    ctx.replyWithMarkdown(
        `እንኳን ወደ **እሁድን በፍቅር** ዲጂታል ዕድር በደህና መጡ! 👋\n\nከታች ያለውን አዝራር በመጫን የክፍያ ሪፖርት መላክ ይችላሉ።`,
        Markup.keyboard([[Markup.button.webApp("📱 ሚኒ አፑን ክፈት", MINI_APP_URL)]]).resize()
    );
});

// /id ትዕዛዝ - የግሩፑን ID ለማወቅ (በፎቶው ላይ እንዳየሁት የሞከሩት)
bot.command('id', (ctx) => {
    ctx.reply(`የዚህ ቻት መለያ ቁጥር (Chat ID)፦ \`${ctx.chat.id}\``, { parse_mode: 'Markdown' });
});

// /pay ትዕዛዝ - በግሩፕ ውስጥ ምላሽ እንዲሰጥ ይበልጥ ተሻሽሏል
bot.hears(/^\/pay(@[a-zA-Z0-9_]+bot)?(\s.*)?$/i, async (ctx) => {
    console.log(`[COMMAND LOG] /pay triggered in ${ctx.chat.type}: ${ctx.chat.id}`);
    try {
        await ctx.reply(
            `ሰላም ${ctx.from.first_name}! 👋\nክፍያ ለመፈጸም ወይም ቀሪ ሂሳብዎን ለማየት ከታች ያለውን አዝራር ይጫኑ፦`,
            Markup.inlineKeyboard([
                Markup.button.webApp('💳 ክፍያ ይፈጽሙ', MINI_APP_URL)
            ])
        );
    } catch (err) {
        console.error("❌ Reply Error in /pay:", err.message);
    }
});

// በሚኒ አፑ በኩል መረጃ ሲመጣ
bot.on('web_app_data', async (ctx) => {
    try {
        const data = JSON.parse(ctx.webAppData.data.json());
        if (data.type === 'payment_report') {
            const txId = generateTXID();
            const time = new Date().toLocaleString('am-ET');
            const guarantors = data.guarantors ? data.guarantors.filter(g => g).join(', ') : "የለም";

            ctx.session.activePayment = { ...data, txId, time, guarantors };

            await ctx.replyWithMarkdown(
                `✅ የ${data.amount} ብር መረጃ ተመዝግቧል።\nመለያ ቁጥር፦ \`${txId}\`\n\n📷 **አሁን የባንክ ደረሰኝዎን ፎቶ (Screenshot) ይላኩ።**`
            );
        }
    } catch (err) {
        console.error("❌ WebAppData Processing Error:", err);
    }
});

// የደረሰኝ ፎቶ ሲላክ
bot.on(['photo', 'document'], async (ctx) => {
    const paymentData = ctx.session?.activePayment;
    if (!paymentData) return;

    const fileId = ctx.message.photo ? ctx.message.photo.pop().file_id : ctx.message.document.file_id;
    const username = ctx.from.username || ctx.from.first_name;

    try {
        const result = db.prepare(`
            INSERT INTO payments (tx_id, user_id, username, purpose, period, amount, penalty, guarantors, file_id, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        `).run(paymentData.txId, ctx.from.id, username, paymentData.purpose, paymentData.period, paymentData.amount, paymentData.penalty, paymentData.guarantors, fileId, paymentData.time);

        const paymentDbId = result.lastInsertRowid;

        // ለግሩፕ ሪፖርት መላክ
        if (TEST_GROUP_ID) {
            const report = formatGroupReport({
                tx_id: paymentData.txId, username, purpose: paymentData.purpose, 
                period: paymentData.period, amount: paymentData.amount, 
                penalty: paymentData.penalty, guarantors: paymentData.guarantors
            }, "⏳", "በመጠባበቅ ላይ");
            
            const sentGroupMsg = await bot.telegram.sendMessage(TEST_GROUP_ID, report, { parse_mode: 'Markdown' });
            db.prepare('UPDATE payments SET group_msg_id = ? WHERE id = ?').run(sentGroupMsg.message_id, paymentDbId);
        }

        // ለአስተዳዳሪ መላክ
        await bot.telegram.sendPhoto(ADMIN_ID, fileId, {
            caption: `🚨 **አዲስ የክፍያ ጥያቄ**\n🆔 መለያ: \`${paymentData.txId}\`\n👤 አባል: @${username}\n💰 መጠን: ${paymentData.amount} ብር`,
            ...Markup.inlineKeyboard([
                [Markup.button.callback("✅ አጽድቅ", `app_${paymentDbId}`), Markup.button.callback("❌ ውድቅ", `rej_${paymentDbId}`)]
            ]),
            parse_mode: 'Markdown'
        });
        
        ctx.session.activePayment = null;
        await ctx.reply(`📩 ደረሰኝዎ ለፋይናንስ ኦፊሰር ደርሷል (መለያ፡ \`${paymentData.txId}\`)።`);

    } catch (err) {
        console.error("❌ Processing Error (Photo/Receipt):", err);
    }
});

// የአስተዳዳሪ ውሳኔ
bot.action(/^(app|rej)_(\d+)$/, async (ctx) => {
    if (!isAdmin(ctx.from.id)) return ctx.answerCbQuery("Denied");

    const [_, action, id] = ctx.match;
    const payment = db.prepare("SELECT * FROM payments WHERE id = ?").get(id);
    if (!payment || payment.status !== 'PENDING') return ctx.answerCbQuery("Already processed.");

    if (action === 'app') {
        db.prepare("UPDATE payments SET status = 'APPROVED' WHERE id = ?").run(id);
        db.prepare("UPDATE members SET balance = balance + ? WHERE user_id = ?").run(payment.amount, payment.user_id);
        
        await bot.telegram.sendMessage(payment.user_id, `✅ **ክፍያዎ ጽድቋል!**\nመለያ፦ \`${payment.tx_id}\``);
        
        if (TEST_GROUP_ID && payment.group_msg_id) {
            const updated = formatGroupReport(payment, "✅", "ተረጋግጦ ጽድቋል");
            await bot.telegram.editMessageText(TEST_GROUP_ID, payment.group_msg_id, null, updated, { parse_mode: 'Markdown' }).catch(()=>{});
        }
    } else {
        db.prepare("UPDATE payments SET status = 'REJECTED' WHERE id = ?").run(id);
        await bot.telegram.sendMessage(payment.user_id, `❌ **ክፍያዎ ውድቅ ተደርጓል**\nመለያ፦ \`${payment.tx_id}\``);
        
        if (TEST_GROUP_ID && payment.group_msg_id) {
            const updated = formatGroupReport(payment, "❌", "ውድቅ ተደርጓል");
            await bot.telegram.editMessageText(TEST_GROUP_ID, payment.group_msg_id, null, updated, { parse_mode: 'Markdown' }).catch(()=>{});
        }
    }

    await ctx.editMessageCaption(`${ctx.callbackQuery.message.caption}\n\n🏁 **ውሳኔ፡** ${action === 'app' ? '✅ ጸድቋል' : '❌ ውድቅ ተደርጓል'}`);
    ctx.answerCbQuery("Done");
});

bot.launch().then(() => console.log("🚀 EdirPay Bot Online! Listening for /pay command in all chats."));

process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
