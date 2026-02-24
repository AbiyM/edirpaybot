/**
 * Edir Digital Pro v3.6 - Backend Bot
 * Features: Admin/User Mode Switching, Participation-Based Tiers, and Group Notifications
 */

require('dotenv').config();
const { Telegraf, session, Markup } = require('telegraf');
const Database = require('better-sqlite3');
const http = require('http');

// --- 1. Configuration ---
const BOT_TOKEN = process.env.BOT_TOKEN;
const ADMIN_IDS = process.env.ADMIN_IDS ? process.env.ADMIN_IDS.split(',').map(id => parseInt(id.trim())) : [];
const MINI_APP_URL = process.env.MINI_APP_URL;
const TEST_GROUP_ID = process.env.TEST_GROUP_ID ? parseInt(process.env.TEST_GROUP_ID) : null;

if (!BOT_TOKEN) {
    console.error("❌ BOT_TOKEN is missing from .env!");
    process.exit(1);
}

// --- 2. Database Setup ---
const db = new Database('edir_pro_v3.db');
db.exec(`
    CREATE TABLE IF NOT EXISTS members (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        tier TEXT DEFAULT 'መሠረታዊ'
    );
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        gateway TEXT,
        purpose TEXT,
        total_amount REAL,
        file_id TEXT,
        status TEXT DEFAULT 'AWAIT_APPROVAL',
        timestamp TEXT
    );
`);

const bot = new Telegraf(BOT_TOKEN);
bot.use(session());

const isAdmin = (id) => ADMIN_IDS.includes(id);

// --- 3. Tier Logic (Participation-Based) ---
function updateMemberTier(userId) {
    const stats = db.prepare(`SELECT COUNT(*) as count FROM payments WHERE user_id = ? AND status = 'APPROVED'`).get(userId);
    let newTier = 'መሠረታዊ';
    if (stats.count >= 12) newTier = 'ልዩ (Elite)';
    else if (stats.count >= 5) newTier = 'ፕሮ (Pro)';

    db.prepare("UPDATE members SET tier = ? WHERE user_id = ?").run(newTier, userId);
    return newTier;
}

// --- 4. Keyboards ---
const getMemberKeyboard = (id) => {
    const btns = [[Markup.button.webApp("📱 ሚኒ አፑን ተጠቀም", MINI_APP_URL)]];
    if (isAdmin(id)) btns.push(["⚙️ የአስተዳዳሪ ሁነታ (Admin Mode)"]);
    btns.push(["📊 ሁኔታዬን እይ", "❓ እርዳታ"]);
    return Markup.keyboard(btns).resize();
};

const getAdminKeyboard = () => {
    return Markup.keyboard([
        ["📑 የሚጠባበቁ ክፍያዎች", "📊 ግሩፕ መለያ (ID)"],
        ["👤 ወደ አባልነት ተመለስ (User Mode)"]
    ]).resize();
};

// --- 5. Bot Handlers ---

bot.start((ctx) => {
    const from = ctx.from;
    db.prepare('INSERT OR IGNORE INTO members (user_id, username, full_name) VALUES (?, ?, ?)').run(
        from.id, from.username || 'N/A', from.first_name
    );
    
    const welcomeText = `እንኳን ወደ **እሁድን በፍቅር** (Sunday with Love) ዲጂታል መተግበሪያ በሰላም መጡ! 👋🌼\n\n` +
        `ይህ መድረክ በየሳምንቱ እሁድ የምናደርገውን መዋጮ በቀላሉ ለመፈጸም እና የተሳትፎ ሁኔታዎን ለመከታተል ይረዳዎታል።\n\n` +
        `ለመጀመር ከታች ያለውን ቁልፍ ይጫኑ።`;
        
    ctx.replyWithMarkdown(welcomeText, getMemberKeyboard(from.id));
});

bot.command('id', (ctx) => ctx.reply(`የዚህ ቻት መለያ (ID): ${ctx.chat.id}`));

// Role Switching
bot.hears("⚙️ የአስተዳዳሪ ሁነታ (Admin Mode)", (ctx) => {
    if (!isAdmin(ctx.from.id)) return ctx.reply("ይቅርታ፣ ይህ ክፍል ለገንዘብ ያዦች ብቻ የተፈቀደ ነው።");
    ctx.reply("🛠 አሁን በ**አስተዳዳሪ ሁነታ** ላይ ነዎት። የሚመጡ ክፍያዎችን ማጽደቅ ይችላሉ።", getAdminKeyboard());
});

bot.hears("👤 ወደ አባልነት ተመለስ (User Mode)", (ctx) => {
    ctx.reply("👤 ወደ **አባልነት ሁነታ** ተመልሰዋል። መዋጮዎን እዚህ መክፈል ይችላሉ።", getMemberKeyboard(ctx.from.id));
});

// Handling Payments from Mini App
bot.on('web_app_data', async (ctx) => {
    try {
        const data = JSON.parse(ctx.webAppData.data.json());
        if (data.type === 'payment_report') {
            const time = new Date().toLocaleString('en-GB', { timeZone: 'Africa/Addis_Ababa' });
            
            // ፎርሙ ተሞልቶ ሲመጣ በሴሽን (Session) ማስቀመጥ (ለፎቶ መጠበቂያ)
            ctx.session.pendingPayment = { 
                ...data, 
                timestamp: time 
            };

            if (data.gateway === 'manual') {
                await ctx.reply(`✅ የ${data.totalAmount} ብር ክፍያ መረጃ ተመዝግቧል።\n\n📷 አሁን የባንክ ደረሰኝዎን ፎቶ (Receipt Photo) እዚህ ይላኩ።`);
            } else {
                // ዲጂታል ክፍያ ከሆነ በቀጥታ ማስገባት
                const res = db.prepare(`INSERT INTO payments (user_id, username, gateway, purpose, total_amount, timestamp) VALUES (?, ?, ?, ?, ?, ?)`)
                    .run(ctx.from.id, ctx.from.username || 'N/A', data.gateway, data.purpose, data.totalAmount, time);
                
                notifyAdmins(ctx, data, res.lastInsertRowid, null, time);
                await ctx.reply(`🚀 ክፍያው ተመዝግቧል። ለአስተዳዳሪ እንዲረጋገጥ ተልኳል።`);
            }
        }
    } catch (err) {
        console.error("Data Error:", err);
    }
});

// Handling Receipt Photo
bot.on(['photo', 'document'], async (ctx) => {
    const pending = ctx.session?.pendingPayment;
    if (!pending) return;

    const fileId = ctx.message.photo ? ctx.message.photo.pop().file_id : ctx.message.document.file_id;
    
    // በዳታቤዝ መመዝገብ
    const res = db.prepare(`INSERT INTO payments (user_id, username, gateway, purpose, total_amount, file_id, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)`)
        .run(ctx.from.id, ctx.from.username || 'N/A', pending.gateway, pending.purpose, pending.totalAmount, fileId, pending.timestamp);

    notifyAdmins(ctx, pending, res.lastInsertRowid, fileId, pending.timestamp);
    
    ctx.session.pendingPayment = null; // ሴሽኑን ማጽዳት
    await ctx.reply(`📩 ደረሰኝዎ ለገንዘብ ያዡ ተልኳል። ሲረጋገጥ መልእክት ይደርስዎታል። እናመሰግናለን!`);
});

// Admin Notification Function
async function notifyAdmins(ctx, data, dbId, fileId, time) {
    const adminCaption = `🚨 **አዲስ የክፍያ ሪፖርት**\n\n` +
        `👤 አባል: @${ctx.from.username || 'N/A'}\n` +
        `💰 መጠን: ${data.totalAmount} ብር\n` +
        `🎯 ዓላማ: ${data.purpose}\n` +
        `📅 ቀን: ${time}`;

    const kb = Markup.inlineKeyboard([
        [Markup.button.callback('✅ አጽድቅ', `p_app_${dbId}_${ctx.from.id}`)],
        [Markup.button.callback('❌ ውድቅ አድርግ', `p_rej_${dbId}_${ctx.from.id}`)]
    ]);

    ADMIN_IDS.forEach(adminId => {
        if (fileId) {
            bot.telegram.sendPhoto(adminId, fileId, { caption: adminCaption, parse_mode: 'Markdown', ...kb });
        } else {
            bot.telegram.sendMessage(adminId, adminCaption, { parse_mode: 'Markdown', ...kb });
        }
    });
}

// Admin Approval Actions
bot.action(/^(p_app|p_rej)_(\d+)_(\d+)$/, async (ctx) => {
    if (!isAdmin(ctx.from.id)) return ctx.answerCbQuery("ፈቃድ የለዎትም!");
    const [action, dbId, targetUid] = [ctx.match[1], ctx.match[2], parseInt(ctx.match[3])];
    const isApprove = action === 'p_app';

    db.prepare(`UPDATE payments SET status = ? WHERE id = ?`).run(isApprove ? 'APPROVED' : 'REJECTED', dbId);
    
    let tier = 'መሠረታዊ';
    if (isApprove) {
        tier = updateMemberTier(targetUid);
        if (TEST_GROUP_ID && tier !== 'መሠረታዊ') {
            const member = db.prepare('SELECT username FROM members WHERE user_id = ?').get(targetUid);
            bot.telegram.sendMessage(TEST_GROUP_ID, `🌟 **የደረጃ ዕድገት!**\nአባል @${member?.username || targetUid} አሁን የ**${tier}** ደረጃ ላይ ደርሰዋል። 🎉`, { parse_mode: 'Markdown' });
        }
    }

    const feedbackMsg = isApprove 
        ? `🎉 እንኳን ደስ አለዎት! ክፍያዎ ተረጋግጧል። የአሁኑ ደረጃዎ: **${tier}**` 
        : "⚠️ ይቅርታ፣ የላኩት የክፍያ መረጃ በአስተዳዳሪው ውድቅ ተደርጓል። እባክዎ መረጃውን በድጋሚ በትክክል ይላኩ።";
    
    try {
        await bot.telegram.sendMessage(targetUid, feedbackMsg, { parse_mode: 'Markdown' });
    } catch (e) {
        console.log("User notification blocked by user");
    }

    const resultLabel = isApprove ? 'ጸድቋል ✅' : 'ውድቅ ተደርጓል ❌';
    if (ctx.callbackQuery.message.photo) {
        await ctx.editMessageCaption(`${ctx.callbackQuery.message.caption}\n\n🏁 ውጤት: ${resultLabel}`);
    } else {
        await ctx.editMessageText(`${ctx.callbackQuery.message.text}\n\n🏁 ውጤት: ${resultLabel}`);
    }
    await ctx.answerCbQuery(isApprove ? "ጸድቋል" : "ተሰርዟል");
});

// Member Status Check
bot.hears("📊 ሁኔታዬን እይ", (ctx) => {
    const stats = db.prepare(`SELECT COUNT(*) as count, SUM(total_amount) as total FROM payments WHERE user_id = ? AND status = 'APPROVED'`).get(ctx.from.id);
    const member = db.prepare(`SELECT tier FROM members WHERE user_id = ?`).get(ctx.from.id);
    ctx.replyWithMarkdown(`📋 **የእርስዎ የክፍያ ማጠቃለያ**\n\n🌟 ደረጃ: **${member?.tier || 'መሠረታዊ'}**\n✅ የጸደቀ ተሳትፎ: ${stats.count} ጊዜ\n💰 ጠቅላላ የተከፈለ: **${stats.total || 0} ብር**\n\nዝርዝር መረጃ ለማየት ሚኒ አፑን ይጠቀሙ።`);
});

bot.hears("❓ እርዳታ", (ctx) => {
    ctx.replyWithMarkdown(`📖 **መመሪያ**\n\n1. '📱 ሚኒ አፑን ተጠቀም' የሚለውን ይጫኑ።\n2. ክፍያዎን ፈጽመው ደረሰኝ ይላኩ።\n3. አስተዳዳሪው ሲያጸድቀው መልእክት ይደርስዎታል።`);
});

// Health check for Render
http.createServer((req, res) => { res.writeHead(200); res.end('Active'); }).listen(process.env.PORT || 3000);

bot.launch().then(() => console.log("🚀 Edir Pro Bot is running..."));

process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
