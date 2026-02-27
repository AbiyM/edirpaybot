/**
 * እሁድን በፍቅር ዲጂታል ፕሮ v3.6.0 - Backend Core
 * ከሚኒ አፕ v1.1.0 ጋር የተናበበ
 */

require('dotenv').config();
const { Telegraf, session, Markup } = require('telegraf');
const Database = require('better-sqlite3');
const http = require('http');

// --- 1. RENDER STABILITY (Keep-Alive) ---
const PORT = process.env.PORT || 3000;
http.createServer((req, res) => {
    res.writeHead(200);
    res.end('Bot Backend is Running');
}).listen(PORT);

// --- 2. CONFIGURATION ---
const BOT_TOKEN = process.env.BOT_TOKEN;
const ADMIN_ID = process.env.ADMIN_ID ? parseInt(process.env.ADMIN_ID) : 1062635928;
const TEST_GROUP_ID = process.env.TEST_GROUP_ID ? parseInt(process.env.TEST_GROUP_ID) : null;
const MINI_APP_URL = process.env.MINI_APP_URL;
const DB_FILE = 'edir_pro_final.db';

if (!BOT_TOKEN) {
    console.error("❌ BOT_TOKEN missing!");
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
        timestamp TEXT
    );
`);

const bot = new Telegraf(BOT_TOKEN);
bot.use(session());

// --- 4. HELPERS ---
const isAdmin = (id) => id === ADMIN_ID;

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
            
            // የዋስ አባላትን መረጃ ማስተካከል
            const guarantorText = data.guarantors && data.guarantors.filter(g => g).length > 0 
                ? data.guarantors.join(', ') 
                : 'የለም';

            // ለጊዜያዊ ሴሽን ማስቀመጥ (ደረሰኝ ለመቀበል)
            ctx.session.pendingPayment = { ...data, guarantors: guarantorText, timestamp: time };

            // ለሙከራ ግሩፑ (edirpayTest) ማሳወቂያ መላክ
            if (TEST_GROUP_ID) {
                const groupMsg = `🔔 **አዲስ የክፍያ ሪፖርት ደርሷል**\n\n` +
                                `👤 አባል: @${ctx.from.username || ctx.from.first_name}\n` +
                                `💰 መጠን: ${data.amount} ብር\n` +
                                `📅 ጊዜ: ${data.period}\n` +
                                `💳 መንገድ: ${data.gateway.toUpperCase()}\n` +
                                `🛡 ዋሶች: ${guarantorText}\n\n` +
                                `✅ አስተዳዳሪዎች እባካችሁ በግል ገብታችሁ አጽድቁ።`;
                
                await bot.telegram.sendMessage(TEST_GROUP_ID, groupMsg, { parse_mode: 'Markdown' })
                         .catch(e => console.log("Group notification error:", e.message));
            }

            if (data.gateway === 'manual') {
                await ctx.reply(`✅ የ${data.amount} ብር መረጃ ተመዝግቧል።\n\n📷 እባክዎ የባንክ ደረሰኝዎን (Receipt) ፎቶ አሁን ይላኩ።`);
            } else {
                // ለወደፊት ዲጂታል ክፍያ ሲከፈት የሚሆን
                await ctx.reply(`🚀 የ${data.gateway} ክፍያዎ ተመዝግቧል። ሲረጋገጥ እናሳውቆታለን።`);
            }
        }
    } catch (e) {
        console.error("Data processing error:", e);
        ctx.reply("❌ መረጃውን በማስኬድ ላይ ስህተት አጋጥሟል።");
    }
});

// --- 7. PHOTO HANDLER (FOR RECEIPTS) ---

bot.on(['photo', 'document'], async (ctx) => {
    const pending = ctx.session?.pendingPayment;
    if (!pending) return;

    const fileId = ctx.message.photo ? ctx.message.photo.pop().file_id : ctx.message.document.file_id;
    
    // በዳታቤዝ ውስጥ ማስቀመጥ
    const insert = db.prepare(`
        INSERT INTO payments (user_id, username, gateway, purpose, period, total_amount, penalty, pay_for_member, guarantors, file_id, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);
    
    insert.run(
        ctx.from.id, ctx.from.username || 'N/A', pending.gateway, pending.purpose, pending.period, 
        pending.amount, pending.penalty, pending.payFor, pending.guarantors, fileId, pending.timestamp
    );

    // ለአስተዳዳሪው ማሳወቂያ መላክ
    const adminMsg = `🚨 **አዲስ የክፍያ ማረጋገጫ ጥያቄ**\n\n👤 አባል: @${ctx.from.username}\n🎯 ዓላማ: ${pending.purpose}\n💰 መጠን: ${pending.amount} ብር\n🛡 ዋሶች: ${pending.guarantors}`;
    const inlineKb = Markup.inlineKeyboard([
        [Markup.button.callback("✅ አጽድቅ", `approve_${ctx.from.id}_${pending.amount}`), Markup.button.callback("❌ ውድቅ አድርግ", `reject_${ctx.from.id}`)]
    ]);

    await bot.telegram.sendPhoto(ADMIN_ID, fileId, { caption: adminMsg, ...inlineKb });
    
    ctx.session.pendingPayment = null; 
    await ctx.reply(`📩 ደረሰኝዎ ለፋይናንስ ኦፊሰር ተልኳል። እንደተረጋገጠ እናሳውቆታለን!`);
});

// --- 8. ADMIN ACTIONS ---

bot.action(/^(approve|reject)_(\d+)_?(\d+)?$/, async (ctx) => {
    if (!isAdmin(ctx.from.id)) return ctx.answerCbQuery("ፈቃድ የለዎትም!");

    const [_, action, targetUserId, amount] = ctx.match;
    
    if (action === 'approve') {
        db.prepare("UPDATE members SET total_savings = total_savings + ? WHERE user_id = ?").run(amount, targetUserId);
        await bot.telegram.sendMessage(targetUserId, `✅ የ${amount} ብር ክፍያዎ ተረጋግጦ ጽድቋል። እናመሰግናለን!`);
    } else {
        await bot.telegram.sendMessage(targetUserId, `❌ ክፍያዎ ውድቅ ተደርጓል። እባክዎ መረጃውን በድጋሚ በትክክል ይላኩ።`);
    }

    await ctx.editMessageCaption(`${ctx.callbackQuery.message.caption}\n\n🏁 **ውሳኔ:** ${action === 'approve' ? '✅ ጸድቋል' : '❌ ውድቅ ተደርጓል'}`);
    ctx.answerCbQuery("ተጠናቋል");
});

bot.launch().then(() => console.log("🚀 Bot Backend v3.6.0 Online"));
