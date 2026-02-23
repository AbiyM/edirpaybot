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
    console.error("❌ ERROR: BOT_TOKEN is missing in Environment Variables!");
    process.exit(1);
}

// Initialize SQLite Database
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
        purpose TEXT,
        location TEXT,
        base_amount REAL,
        penalty_amount REAL,
        total_amount REAL,
        note TEXT,
        file_id TEXT,
        status TEXT DEFAULT 'AWAIT_APPROVAL',
        timestamp TEXT
    );
    CREATE TABLE IF NOT EXISTS loan_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        amount REAL,
        duration INTEGER,
        reason TEXT,
        status TEXT DEFAULT 'PENDING',
        timestamp TEXT
    );
`);

const bot = new Telegraf(BOT_TOKEN);
bot.use(session());

// --- MIDDLEWARE: GROUP ACCESS CHECK ---
const checkGroupMembership = async (ctx, next) => {
    // Skip check if Group ID is placeholder or not set
    if (!EDIR_GROUP_ID || EDIR_GROUP_ID.includes("123456789")) return next();
    
    if (ctx.from && ctx.chat.type === 'private') {
        try {
            const member = await ctx.telegram.getChatMember(EDIR_GROUP_ID, ctx.from.id);
            const allowed = ['member', 'administrator', 'creator'];
            if (!allowed.includes(member.status)) {
                return ctx.reply("❌ ይቅርታ! ይህን ቦት ለመጠቀም መጀመሪያ የእሁድን በፍቅር የቴሌግራም ግሩፕ አባል መሆን አለብዎት።");
            }
        } catch (error) {
            console.error("Group Check Error:", error.message);
            return next();
        }
    }
    return next();
};

// --- USER COMMANDS ---

bot.start(checkGroupMembership, (ctx) => {
    db.prepare('INSERT OR IGNORE INTO members (user_id, username) VALUES (?, ?)').run(ctx.from.id, ctx.from.username || 'N/A');
    
    const welcomeMsg = `እንኳን ወደ **እሁድን በፍቅር** የክፍያ ቦት በሰላም መጡ! 🚀\n\n` +
        `መዋጮን፣ ቅጣትን እና የብድር አገልግሎትን እዚህ ማስተዳደር ይችላሉ።\n\n` +
        `**ክፍያ ለመፈጸም** ከታች ያለውን ሰማያዊ ቁልፍ ይጠቀሙ።\n\n` +
        `_Powered by Skymark System Solution_`;
    
    return ctx.replyWithMarkdown(welcomeMsg, 
        Markup.keyboard([
            [Markup.button.webApp("🚀 ክፍያ ያስገቡ", MINI_APP_URL)],
            ["📊 የጥያቄዬ ሁኔታ", "❓ እርዳታ"]
        ]).resize()
    );
});

bot.command('help', (ctx) => {
    ctx.replyWithMarkdown("📖 **መመሪያ**\n\n1. '🚀 ክፍያ ያስገቡ' የሚለውን ይጫኑ\n2. ፎርሙን ሞልተው ሲጨርሱ 'መዝግብ' ይበሉ\n3. በመቀጠል የደረሰኝዎን ፎቶ (Screenshot) እዚህ ይላኩ።");
});

bot.hears("📊 የጥያቄዬ ሁኔታ", (ctx) => {
    const member = db.prepare('SELECT status FROM members WHERE user_id = ?').get(ctx.from.id);
    const statusText = member?.status === 'APPROVED' ? "✅ የጸደቀ አባል" : "⏳ በመጠባበቅ ላይ ያለ";
    ctx.replyWithMarkdown(`የአሁናዊ ሁኔታዎ: **${statusText}**`);
});

bot.hears("❓ እርዳታ", (ctx) => {
    ctx.replyWithMarkdown("📖 **መመሪያ**\n\n1. 'ክፍያ ያስገቡ' የሚለውን ይጫኑ\n2. ፎርሙን ሞልተው ሲጨርሱ 'Submit' ይበሉ\n3. በመቀጠል የደረሰኙን ፎቶ እዚህ ይላኩ።");
});

// --- ADMIN COMMANDS ---

bot.command('admin', (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return ctx.reply("❌ ይህ ትዕዛዝ ለአስተዳዳሪዎች ብቻ ነው።");
    
    const pendingPayments = db.prepare("SELECT COUNT(*) as count FROM payments WHERE status = 'AWAIT_APPROVAL'").get().count;
    const pendingLoans = db.prepare("SELECT COUNT(*) as count FROM loan_requests WHERE status = 'PENDING'").get().count;
    const totalMembers = db.prepare("SELECT COUNT(*) as count FROM members").get().count;

    const adminMsg = `🛠 **የአስተዳዳሪ መቆጣጠሪያ (Admin Dashboard)**\n\n` +
        `👥 ጠቅላላ ተመዝጋቢዎች: **${totalMembers}**\n` +
        `💰 ማረጋገጫ የሚጠብቁ ክፍያዎች: **${pendingPayments}**\n` +
        `📩 ማረጋገጫ የሚጠብቁ ብድሮች: **${pendingLoans}**\n\n` +
        `ለዝርዝር የገንዘብ ሪፖርት /stats ይበሉ።\n` +
        `ሁሉንም አባላት ለማነጋገር /broadcast [መልእክት] ይጠቀሙ።`;

    ctx.replyWithMarkdown(adminMsg, Markup.inlineKeyboard([
        [Markup.button.callback("📜 የአባላት ዝርዝር", "admin_list_members")],
        [Markup.button.callback("📥 የክፍያ ሁኔታ", "admin_pending_summary")]
    ]));
});

bot.command('broadcast', async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    
    const message = ctx.message.text.replace('/broadcast', '').trim();
    if (!message) return ctx.reply("❌ እባክዎ መልእክት ይጻፉ። ምሳሌ፡ `/broadcast ሰላም አባላት...`", { parse_mode: 'Markdown' });

    const members = db.prepare("SELECT user_id FROM members").all();
    let successCount = 0;
    
    await ctx.reply(`📣 ብሮድካስት እየተላከ ነው ለ ${members.length} አባላት...`);

    for (const member of members) {
        try {
            await ctx.telegram.sendMessage(member.user_id, `📢 **ከእሁድን በፍቅር አስተዳዳሪ:**\n\n${message}`, { parse_mode: 'Markdown' });
            successCount++;
        } catch (err) {
            console.error(`Failed to send broadcast to ${member.user_id}`);
        }
    }
    ctx.reply(`✅ ብሮድካስት ተጠናቋል። ለ ${successCount} አባላት ደርሷል።`);
});

bot.action('admin_list_members', (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    const members = db.prepare("SELECT username, status FROM members LIMIT 20").all();
    let list = "👥 **የአባላት ዝርዝር (የመጀመሪያዎቹ 20):**\n\n";
    members.forEach(m => {
        list += `• @${m.username} - ${m.status === 'APPROVED' ? '✅' : '⏳'}\n`;
    });
    ctx.replyWithMarkdown(list);
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
            await ctx.replyWithMarkdown(`✅ የ**${data.purpose}** መረጃ ተመዝግቧል!\n📍 ቦታ፡ ${data.location}\n💰 ድምር፡ ${data.totalAmount} ብር\n\nአሁን ደረሰኝዎን (Screenshot) እዚህ ይላኩ።`);
        } else if (data.type === 'loan_request') {
            const res = db.prepare(`INSERT INTO loan_requests (user_id, username, amount, duration, reason, timestamp) VALUES (?, ?, ?, ?, ?, ?)`).run(
                ctx.from.id, ctx.from.username || 'N/A', data.amount, data.duration, data.reason, new Date().toLocaleString()
            );
            await ctx.reply("📩 የብድር ጥያቄዎ ተልኳል። አስተዳዳሪው ሲያጸድቀው መልእክት ይደርስዎታል።");
            
            if (ADMIN_ID) {
                const adminKb = Markup.inlineKeyboard([
                    [Markup.button.callback('✅ ፍቀድ', `lapp_${res.lastInsertRowid}_${ctx.from.id}`), 
                     Markup.button.callback('❌ ሰርዝ', `lrej_${res.lastInsertRowid}_${ctx.from.id}`)]
                ]);
                await ctx.telegram.sendMessage(ADMIN_ID, `❓ **አዲስ የብድር ጥያቄ**\n👤 @${ctx.from.username}\n💰 መጠን: ${data.amount} ብር\n📅 ጊዜ: ${data.duration} ወራት\n📝 ምክንያት: ${data.reason}`, adminKb);
            }
        }
    } catch (e) {
        console.error("Data processing error:", e);
        ctx.reply("⚠️ መረጃውን በማቀነባበር ላይ ስህተት ተከስቷል።");
    }
});

// --- RECEIPT HANDLER ---

bot.on(['photo', 'document'], async (ctx) => {
    const pending = ctx.session?.pendingPayment;
    if (!pending) return ctx.reply("እባክዎ መጀመሪያ ፎርሙን ይሙሉ (ክፍያ ያስገቡ የሚለውን ይጫኑ)።");

    const fileId = ctx.message.photo ? ctx.message.photo.pop().file_id : ctx.message.document.file_id;
    
    const res = db.prepare(`INSERT INTO payments (user_id, username, purpose, location, base_amount, penalty_amount, total_amount, note, file_id, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).run(
        pending.userId, pending.username, pending.purpose, pending.location, pending.baseAmount, pending.penaltyAmount, pending.totalAmount, pending.note || '', fileId, new Date().toLocaleString()
    );

    ctx.session.pendingPayment = null; 

    if (ADMIN_ID) {
        const adminKb = Markup.inlineKeyboard([
            [Markup.button.callback('✅ አጽድቅ', `papp_${res.lastInsertRowid}_${ctx.from.id}`), 
             Markup.button.callback('❌ ሰርዝ', `prej_${res.lastInsertRowid}_${ctx.from.id}`)]
        ]);

        await ctx.telegram.sendPhoto(ADMIN_ID, fileId, { 
            caption: `🚨 *አዲስ ክፍያ*\n👤 @${pending.username}\n🎯 ዓላማ: ${pending.purpose}\n💵 ድምር: ${pending.totalAmount} ብር`,
            parse_mode: 'Markdown',
            ...adminKb 
        });
    }

    await ctx.reply("📩 ደረሰኝዎ ለገንዘብ ያዡ ተልኳል። ሲረጋገጥ መልእክት ይደርስዎታል።");
});

// --- ADMIN ACTIONS ---

bot.action(/^(papp|prej|lapp|lrej)_(\d+)_(\d+)$/, async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return ctx.answerCbQuery("አልተፈቀደልዎትም!");

    const [action, id, targetId] = [ctx.match[1], ctx.match[2], parseInt(ctx.match[3])];
    const isApprove = action.includes('app');
    const isLoan = action.startsWith('l');
    const table = isLoan ? 'loan_requests' : 'payments';

    db.prepare(`UPDATE ${table} SET status = ? WHERE id = ?`).run(isApprove ? 'APPROVED' : 'REJECTED', id);

    if (!isLoan && isApprove) {
        db.prepare("UPDATE members SET status = 'APPROVED' WHERE user_id = ?").run(targetId);
    }

    const message = isApprove ? "🎉 ጥያቄዎ/ክፍያዎ በአስተዳዳሪው ጸድቋል!" : "⚠️ ጥያቄዎ/ክፍያዎ ውድቅ ተደርጓል።";
    await ctx.telegram.sendMessage(targetId, message);

    const statusLabel = isApprove ? 'APPROVED ✅' : 'REJECTED ❌';
    await ctx.editMessageCaption(`${ctx.callbackQuery.message.caption || ctx.callbackQuery.message.text}\n\n🏁 ውጤት: ${statusLabel}`);
    await ctx.answerCbQuery(isApprove ? "ጸድቋል" : "ተሰርዟል");
});

bot.command('stats', (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    const stats = db.prepare(`
        SELECT 
            SUM(CASE WHEN purpose = 'Monthly Fee' THEN base_amount ELSE 0 END) as monthly,
            SUM(CASE WHEN purpose = 'Loan Payment' THEN base_amount ELSE 0 END) as loans,
            SUM(penalty_amount) as penalties,
            SUM(total_amount) as grand_total
        FROM payments WHERE status = 'APPROVED'
    `).get();

    ctx.replyWithMarkdown(`💰 **የገንዘብ ሪፖርት**\n\n• መዋጮ፡ **${stats.monthly || 0} ብር**\n• የተመለሰ ብድር፡ **${stats.loans || 0} ብር**\n• ቅጣት፡ **${stats.penalties || 0} ብር**\n---\n📢 **አጠቃላይ ካዝና፡ ${stats.grand_total || 0} ብር**\n\n_Powered by Skymark_`);
});

// Health check server for Render
http.createServer((req, res) => {
    res.writeHead(200);
    res.end('Ehuden Befikir Bot is active!');
}).listen(process.env.PORT || 3000);

bot.launch().then(() => console.log('✅ Ehuden Befikir Bot is ACTIVE!'));

process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
