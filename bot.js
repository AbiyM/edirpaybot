/**
 * እሁድን በፍቅር ዲጂታል ፕሮ v4.5.0 - Full Complete Backend (Node.js)
 * ቴክኖሎጂ፡ Telegraf, Better-SQLite3, Dotenv
 * ባህሪያት፡ #EUDE መለያ ቁጥር፣ አውቶማቲክ ሪፖርት፣ አስተዳዳሪ ማጽደቂያ
 */

require('dotenv').config();
const { Telegraf, session, Markup } = require('telegraf');
const Database = require('better-sqlite3');
const http = require('http');

// --- 1. የጤና ፍተሻ ሰርቨር (ለRender ስኬታማ ዲፕሎይመንት) ---
const PORT = process.env.PORT || 3000;
http.createServer((req, res) => {
    res.writeHead(200);
    res.end('EdirPay Bot is Online and Healthy');
}).listen(PORT);

// --- 2. ኮንፊገሬሽን (Configuration) ---
const BOT_TOKEN = process.env.BOT_TOKEN;
const ADMIN_ID = process.env.ADMIN_ID ? parseInt(process.env.ADMIN_ID) : 1062635928;
const TEST_GROUP_ID = process.env.TEST_GROUP_ID ? parseInt(process.env.TEST_GROUP_ID) : null;
const MINI_APP_URL = process.env.MINI_APP_URL || "https://abiym.github.io/edirpaybot/";
const DB_FILE = 'edir_pro_final.db';

if (!BOT_TOKEN) {
    console.error("❌ ስህተት፡ BOT_TOKEN አልተገኘም!");
    process.exit(1);
}

// --- 3. ዳታቤዝ ዝግጅት (Database Setup) ---
const db = new Database(DB_FILE);
db.exec(`
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
        file_id TEXT,
        status TEXT DEFAULT 'PENDING',
        group_msg_id INTEGER,
        timestamp TEXT
    );
`);

const bot = new Telegraf(BOT_TOKEN);
bot.use(session()); // መረጃን ለጊዜው ለማስታወስ

// --- 4. ረዳት ተግባራት (Helpers) ---
const isAdmin = (id) => id === ADMIN_ID;

// የ #EUDE መለያ ቁጥር ማመንጫ (ለምሳሌ፡ #EUDE7412)
const generateTXID = () => `#EUDE${Math.floor(1000 + Math.random() * 9000)}`;

// የግሩፕ ሪፖርት ፎርማት
const formatGroupReport = (p, emoji, statusText) => {
    return `📋 **የክፍያ ሪፖርት ${p.tx_id}**\n` +
           `━━━━━━━━━━━━━━━━━━\n` +
           `👤 **አባል:** @${p.username}\n` +
           `🎯 **ዓላማ:** ${p.purpose}\n` +
           `📅 **ጊዜ:** ${p.period}\n` +
           `💰 **መጠን:** ${p.amount} ብር\n` +
           `⚠️ **ቅጣት:** ${p.penalty > 0 ? p.penalty + ' ብር' : 'የለም'}\n` +
           `━━━━━━━━━━━━━━━━━━\n` +
           `${emoji} **ሁኔታ:** ${statusText}`;
};

// --- 5. ቦት ትዕዛዞች (Handlers) ---

// መጀመሪያ ሲጀመር (Start)
bot.start((ctx) => {
    const time = new Date().toLocaleString('am-ET');
    // አባሉን መመዝገብ
    db.prepare('INSERT OR IGNORE INTO members (user_id, username, full_name, joined_at) VALUES (?, ?, ?, ?)').run(
        ctx.from.id, ctx.from.username || 'N/A', ctx.from.first_name, time
    );

    const menu = Markup.keyboard([
        [Markup.button.webApp("📱 ሚኒ አፑን ክፈት", MINI_APP_URL)]
    ]).resize();

    ctx.replyWithMarkdown(
        `ሰላም ${ctx.from.first_name}! 👋\nእንኳን ወደ **እሁድን በፍቅር** ዲጂታል ዕድር በደህና መጡ።\n\nከታች ያለውን አዝራር በመጫን የክፍያ ሪፖርት መላክ ይችላሉ።`,
        menu
    );
});

// በሚኒ አፑ በኩል መረጃ ሲመጣ
bot.on('web_app_data', async (ctx) => {
    try {
        const data = JSON.parse(ctx.webAppData.data.json());
        if (data.type === 'payment_report') {
            const txId = generateTXID();
            const time = new Date().toLocaleString('am-ET');

            // መረጃውን ለጊዜው በሴሽን ውስጥ መያዝ (ፎቶው እስኪመጣ)
            ctx.session.activePayment = { ...data, txId, time };

            await ctx.replyWithMarkdown(
                `✅ የ${data.amount} ብር መረጃ ተመዝግቧል።\nመለያ ቁጥር፦ \`${txId}\`\n\nእባክዎ እስኪጸድቅ (APPROVE) ድረስ ይጠብቁ።\n\n📷 **አሁን የባንክ ደረሰኝዎን ፎቶ (Screenshot) ይላኩ።**`
            );
        }
    } catch (err) {
        console.error("WebAppData Processing Error:", err);
        ctx.reply("❌ መረጃውን በማስኬድ ላይ ስህተት ተከስቷል።");
    }
});

// የደረሰኝ ፎቶ ሲላክ
bot.on(['photo', 'document'], async (ctx) => {
    const paymentData = ctx.session?.activePayment;
    
    if (!paymentData) {
        return ctx.reply("❌ እባክዎ መጀመሪያ በሚኒ አፑ መረጃውን ይላኩ።");
    }

    const fileId = ctx.message.photo ? ctx.message.photo.pop().file_id : ctx.message.document.file_id;
    const username = ctx.from.username || ctx.from.first_name;

    try {
        // 1. በዳታቤዝ ውስጥ መመዝገብ
        const stmt = db.prepare(`
            INSERT INTO payments (tx_id, user_id, username, purpose, period, amount, penalty, file_id, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        `);
        const result = stmt.run(
            paymentData.txId, ctx.from.id, username, 
            paymentData.purpose, paymentData.period, 
            paymentData.amount, paymentData.penalty, fileId, paymentData.time
        );
        const paymentDbId = result.lastInsertRowid;

        // 2. ለግሩፑ ማሳወቂያ መላክ
        if (TEST_GROUP_ID) {
            const report = formatGroupReport({
                tx_id: paymentData.txId, username, purpose: paymentData.purpose, 
                period: paymentData.period, amount: paymentData.amount, penalty: paymentData.penalty
            }, "⏳", "በመጠባበቅ ላይ");
            
            const sentGroupMsg = await bot.telegram.sendMessage(TEST_GROUP_ID, report, { parse_mode: 'Markdown' });
            db.prepare('UPDATE payments SET group_msg_id = ? WHERE id = ?').run(sentGroupMsg.message_id, paymentDbId);
        }

        // 3. ለአስተዳዳሪው እንዲያጸድቅ መላክ
        const adminCaption = `🚨 **አዲስ የክፍያ ማረጋገጫ ጥያቄ**\n━━━━━━━━━━━━━━━━━━\n🆔 መለያ: \`${paymentData.txId}\`\n👤 አባል: @${username}\n💰 መጠን: ${paymentData.amount} ብር\n📅 ጊዜ: ${paymentData.period}`;
        const adminKeyboard = Markup.inlineKeyboard([
            [Markup.button.callback("✅ አጽድቅ", `approve_${paymentDbId}`), Markup.button.callback("❌ ውድቅ አድርግ", `reject_${paymentDbId}`)]
        ]);

        await bot.telegram.sendPhoto(ADMIN_ID, fileId, { caption: adminCaption, ...adminKeyboard, parse_mode: 'Markdown' });
        
        // ሴሽኑን ማጽዳት
        ctx.session.activePayment = null;
        await ctx.reply(`📩 ደረሰኝዎ ለፋይናንስ ኦፊሰር ደርሷል (መለያ፡ \`${paymentData.txId}\`)። ሲረጋገጥ እናሳውቆታለን።`);

    } catch (err) {
        console.error("File Handling Error:", err);
        ctx.reply("❌ ደረሰኙን በመመዝገብ ላይ ስህተት ተፈጥሯል።");
    }
});

// አስተዳዳሪው ሲያጸድቅ ወይም ውድቅ ሲያደርግ (Callback)
bot.action(/^(approve|reject)_(\d+)$/, async (ctx) => {
    if (!isAdmin(ctx.from.id)) return ctx.answerCbQuery("ይህንን ለማድረግ ፈቃድ የለዎትም!");

    const action = ctx.match[1];
    const paymentId = ctx.match[2];
    
    const payment = db.prepare("SELECT * FROM payments WHERE id = ?").get(paymentId);
    if (!payment || payment.status !== 'PENDING') {
        return ctx.answerCbQuery("ክፍያው ቀድሞውኑ ተስተናግዷል።");
    }

    if (action === 'approve') {
        // 1. ዳታቤዝ ማደስ
        db.prepare("UPDATE payments SET status = 'APPROVED' WHERE id = ?").run(paymentId);
        db.prepare("UPDATE members SET balance = balance + ? WHERE user_id = ?").run(payment.amount, payment.user_id);
        
        // 2. ተጠቃሚውን ማሳወቅ
        await bot.telegram.sendMessage(payment.user_id, `✅ **ክፍያዎ ጽድቋል!**\nመለያ፦ \`${payment.tx_id}\`\nየ${payment.amount} ብር ክፍያዎ ተረጋግጦ በቁጠባዎ ላይ ተጨምሯል። እናመሰግናለን!`);
        
        // 3. ግሩፕ ላይ ያለውን መልዕክት ማደስ
        if (TEST_GROUP_ID && payment.group_msg_id) {
            const updatedReport = formatGroupReport(payment, "✅", "ተረጋግጦ ጽድቋል");
            await bot.telegram.editMessageText(TEST_GROUP_ID, payment.group_msg_id, null, updatedReport, { parse_mode: 'Markdown' }).catch(()=>{});
        }
    } else {
        // 1. ውድቅ ማድረግ
        db.prepare("UPDATE payments SET status = 'REJECTED' WHERE id = ?").run(paymentId);
        await bot.telegram.sendMessage(payment.user_id, `❌ **ክፍያዎ ውድቅ ተደርጓል**\nመለያ፦ \`${payment.tx_id}\`\nደረሰኙ ትክክል ስላልሆነ ወይም ስላልተነበበ እባክዎ ደግመው ይላኩ።`);
        
        if (TEST_GROUP_ID && payment.group_msg_id) {
            const updatedReport = formatGroupReport(payment, "❌", "ውድቅ ተደርጓል (ደረሰኝ ስህተት)");
            await bot.telegram.editMessageText(TEST_GROUP_ID, payment.group_msg_id, null, updatedReport, { parse_mode: 'Markdown' }).catch(()=>{});
        }
    }

    // የአስተዳዳሪውን መልዕክት መቀየር
    const decision = action === 'approve' ? '✅ ጸድቋል' : '❌ ውድቅ ተደርጓል';
    await ctx.editMessageCaption(`${ctx.callbackQuery.message.caption}\n\n🏁 **ውሳኔ፡** ${decision}\n👤 **አስተዳዳሪ፡** ${ctx.from.first_name}`);
    ctx.answerCbQuery("ተጠናቋል");
});

// ቦቱን ማስጀመር
bot.launch().then(() => {
    console.log("🚀 EdirPay Premium Backend is Online!");
});

// ስህተት ቢፈጠር እንዳይቆም (Graceful stop)
process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
