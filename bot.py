require('dotenv').config();
const { Telegraf, session, Markup } = require('telegraf');
const Database = require('better-sqlite3');
const http = require('http');

// --- CONFIGURATION ---
const BOT_TOKEN = process.env.BOT_TOKEN;
const ADMIN_ID = process.env.ADMIN_ID ? parseInt(process.env.ADMIN_ID) : null;
const MINI_APP_URL = process.env.MINI_APP_URL;
const EDIR_GROUP_ID = process.env.EDIR_GROUP_ID; 

if (!BOT_TOKEN) {
    console.error("❌ ERROR: BOT_TOKEN is missing!");
    process.exit(1);
}

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
        gateway TEXT,
        purpose TEXT,
        location TEXT,
        base_amount REAL,
        penalty_amount REAL,
        total_amount REAL,
        file_id TEXT,
        status TEXT DEFAULT 'AWAIT_APPROVAL',
        timestamp TEXT
    );
`);

const bot = new Telegraf(BOT_TOKEN);
bot.use(session());

// --- MIDDLEWARE: GROUP ACCESS CHECK ---
const checkGroupMembership = async (ctx, next) => {
    if (!EDIR_GROUP_ID || EDIR_GROUP_ID.includes("123456789")) return next();
    if (ctx.from && ctx.chat.type === 'private') {
        try {
            const member = await ctx.telegram.getChatMember(EDIR_GROUP_ID, ctx.from.id);
            const allowed = ['member', 'administrator', 'creator'];
            if (!allowed.includes(member.status)) {
                return ctx.reply("❌ ይቅርታ! ይህን ቦት ለመጠቀም መጀመሪያ የ'እሁድን በፍቅር' የቴሌግራም ግሩፕ አባል መሆን አለብዎት።");
            }
        } catch (error) {
            return next();
        }
    }
    return next();
};

// --- USER COMMANDS ---

bot.start(checkGroupMembership, (ctx) => {
    db.prepare('INSERT OR IGNORE INTO members (user_id, username) VALUES (?, ?)').run(ctx.from.id, ctx.from.username || 'N/A');
    
    const welcomeMsg = `እንኳን ወደ **እሁድን በፍቅር** የክፍያ ቦት በሰላም መጡ! 👋\n\n` +
        `መዋጮን፣ ቅጣትን እና ብድርን እዚህ በቀላሉ መክፈል እና ሁኔታውን መከታተል ይችላሉ።\n\n` +
        `ለመጀመር ከታች ያለውን ሰማያዊ ቁልፍ ይጠቀሙ።`;
    
    return ctx.replyWithMarkdown(welcomeMsg, 
        Markup.keyboard([
            [Markup.button.webApp("🚀 ክፍያ ያስገቡ", MINI_APP_URL)],
            ["📊 የጥያቄዬ ሁኔታ", "❓ እርዳታ"]
        ]).resize()
    );
});

bot.hears("📊 የጥያቄዬ ሁኔታ", (ctx) => {
    const member = db.prepare('SELECT status FROM members WHERE user_id = ?').get(ctx.from.id);
    const pendingCount = db.prepare("SELECT COUNT(*) as count FROM payments WHERE user_id = ? AND status = 'AWAIT_APPROVAL'").get(ctx.from.id).count;
    
    let msg = `የአባልነት ሁኔታዎ: **${member?.status === 'APPROVED' ? "✅ የጸደቀ" : "⏳ በመጠባበቅ ላይ"}**\n`;
    if (pendingCount > 0) {
        msg += `\n⚠️ ማረጋገጫ የሚጠብቁ **${pendingCount}** ክፍያዎች አሉዎት።`;
    }
    ctx.replyWithMarkdown(msg);
});

bot.hears("❓ እርዳታ", (ctx) => {
    const helpMsg = `📖 **አጭር መመሪያ**\n\n` +
        `1. '🚀 ክፍያ ያስገቡ' የሚለውን ይጫኑ።\n` +
        `2. ፎርሙን ሞልተው ሲጨርሱ 'ላክ' ይበሉ።\n` +
        `3. ሚኒ አፑ ሲዘጋ የደረሰኝ ፎቶ (Screenshot) እዚህ ይላኩ።\n\n` +
        `የከፈሉት ክፍያ በአስተዳዳሪው ሲረጋገጥ መልእክት ይደርስዎታል።`;
    ctx.replyWithMarkdown(helpMsg);
});

// --- WEB APP DATA HANDLER ---

bot.on('web_app_data', async (ctx) => {
    try {
        const data = JSON.parse(ctx.webAppData.data.json());
        
        if (data.type === 'payment_report') {
            ctx.session.pendingPayment = { 
                ...data, 
                userId: ctx.from.id, 
                username: ctx.from.username || 'N/A' 
            };

            const isAuto = data.isAutomatic === 'YES';
            const gatewayDisplay = data.gateway === 'manual' ? 'በደረሰኝ (Manual)' : `${data.gateway.toUpperCase()} (ዲጂታል)`;

            let replyMsg = `✅ **የ${data.purpose}** መረጃ ተመዝግቧል!\n`;
            replyMsg += `💳 መንገድ፦ ${gatewayDisplay}\n`;
            replyMsg += `💰 ድምር፡ **${data.totalAmount} ብር**\n\n`;
            
            if (isAuto) {
                replyMsg += `🚀 በዲጂታል መተግበሪያው ክፍያውን ከጨረሱ በኋላ የማረጋገጫ ደረሰኝ (Screenshot) እዚህ ይላኩ።`;
            } else {
                replyMsg += `📷 አሁን የባንክ ደረሰኝዎን ፎቶ እዚህ ይላኩ።`;
            }

            await ctx.replyWithMarkdown(replyMsg);
        }
    } catch (e) {
        console.error("Web App Data Error:", e);
        ctx.reply("❌ መረጃውን በማስተናገድ ላይ ስህተት አጋጥሟል። እባክዎ ደግመው ይሞክሩ።");
    }
});

// --- RECEIPT HANDLER (Photo/Document) ---

bot.on(['photo', 'document'], async (ctx) => {
    const pending = ctx.session?.pendingPayment;
    if (!pending) return ctx.reply("እባክዎ መጀመሪያ '🚀 ክፍያ ያስገቡ' የሚለውን ቁልፍ ተጠቅመው ፎርሙን ይሙሉ::");

    const fileId = ctx.message.photo ? ctx.message.photo.pop().file_id : ctx.message.document.file_id;
    
    const res = db.prepare(`
        INSERT INTO payments (user_id, username, gateway, purpose, location, base_amount, penalty_amount, total_amount, file_id, timestamp) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
        pending.userId, pending.username, pending.gateway, pending.purpose, pending.location, 
        pending.baseAmount, pending.penaltyAmount, pending.totalAmount, fileId, new Date().toLocaleString()
    );

    ctx.session.pendingPayment = null; 

    if (ADMIN_ID) {
        const adminKb = Markup.inlineKeyboard([
            [Markup.button.callback('✅ አጽድቅ', `papp_${res.lastInsertRowid}_${ctx.from.id}`), 
             Markup.button.callback('❌ ሰርዝ', `prej_${res.lastInsertRowid}_${ctx.from.id}`)]
        ]);

        const adminCaption = `🚨 **አዲስ የክፍያ ሪፖርት**\n\n` +
            `👤 አባል፦ @${pending.username}\n` +
            `🎯 ዓላማ፦ ${pending.purpose}\n` +
            `💳 መንገድ፦ ${pending.gateway.toUpperCase()}\n` +
            `💵 መጠን፦ ${pending.totalAmount} ብር\n` +
            `📍 ቦታ፦ ${pending.location}`;

        await ctx.telegram.sendPhoto(ADMIN_ID, fileId, { 
            caption: adminCaption,
            parse_mode: 'Markdown',
            ...adminKb 
        });
    }

    await ctx.reply("📩 ደረሰኝዎ ለገንዘብ ያዡ ተልኳል። ሲረጋገጥ እናሳውቅዎታለን። እናመሰግናለን!");
});

// --- ADMIN ACTIONS ---

bot.action(/^(papp|prej)_(\d+)_(\d+)$/, async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return ctx.answerCbQuery("አልተፈቀደልዎትም!");

    const [action, id, targetId] = [ctx.match[1], ctx.match[2], parseInt(ctx.match[3])];
    const isApprove = action.includes('app');

    db.prepare(`UPDATE payments SET status = ? WHERE id = ?`).run(isApprove ? 'APPROVED' : 'REJECTED', id);

    if (isApprove) {
        db.prepare("UPDATE members SET status = 'APPROVED' WHERE user_id = ?").run(targetId);
    }

    const resultMsg = isApprove ? "🎉 ክፍያዎ በአስተዳዳሪው ጸድቋል! እናመሰግናለን።" : "⚠️ ይቅርታ፣ የላኩት ክፍያ በአስተዳዳሪው ውድቅ ተደርጓል። እባክዎ ትክክለኛውን ደረሰኝ በድጋሚ ይላኩ።";
    
    try {
        await ctx.telegram.sendMessage(targetId, resultMsg);
    } catch (err) {
        console.error("Notification Error:", err);
    }
    
    await ctx.editMessageCaption(`${ctx.callbackQuery.message.caption}\n\n🏁 ውጤት: ${isApprove ? 'APPROVED ✅' : 'REJECTED ❌'}`);
    await ctx.answerCbQuery(isApprove ? "ጸድቋል" : "ተሰርዟል");
});

// --- STATS COMMAND (Admin Only) ---

bot.command('stats', (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    
    const stats = db.prepare(`
        SELECT 
            SUM(CASE WHEN purpose LIKE 'የመዋጮ:%' THEN base_amount ELSE 0 END) as contributions,
            SUM(CASE WHEN purpose = 'Loan Payment' OR purpose = 'የብድር መመለሻ' THEN base_amount ELSE 0 END) as loans,
            SUM(penalty_amount) as penalties,
            SUM(total_amount) as grand_total
        FROM payments WHERE status = 'APPROVED'
    `).get();

    const report = `💰 **የፋይናንስ ማጠቃለያ (Financial Stats)**\n\n` +
        `📅 ጠቅላላ መዋጮ፦ **${stats.contributions || 0} ብር**\n` +
        `🏦 የተመለሰ ብድር፦ **${stats.loans || 0} ብር**\n` +
        `⚠️ የቅጣት ገቢ፦ **${stats.penalties || 0} ብር**\n` +
        `------------------------\n` +
        `📢 **ጠቅላላ በካዝና፦ ${stats.grand_total || 0} ብር**\n\n` +
        `_Powered by Skymark System Solution_`;

    ctx.replyWithMarkdown(report);
});

// Health check for Render / Deployment
http.createServer((req, res) => {
    res.writeHead(200);
    res.end('Bot is Active');
}).listen(process.env.PORT || 3000);

bot.launch().then(() => console.log('🚀 Ehuden Befikir Bot is active and running...'));
