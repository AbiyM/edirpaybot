/**
 * እሁድን በፍቅር ዲጂታል ፕሮ v3.8 - የተሻሻለ የአስተዳዳሪ ክፍል (Improved Admin Mode)
 * ይህ ቦት የአባላትን ክፍያ ማጽደቅ፣ አጠቃላይ ሪፖርት ማሳየት እና ኖቲፊኬሽኖችን መላክ ይችላል።
 */

require('dotenv').config();
const { Telegraf, session, Markup } = require('telegraf');
const Database = require('better-sqlite3');
const http = require('http');

// --- 1. RENDER STABILITY ---
const PORT = process.env.PORT || 3000;
http.createServer((req, res) => {
    res.writeHead(200);
    res.end('Bot is Active');
}).listen(PORT);

// --- 2. CONFIGURATION ---
const BOT_TOKEN = process.env.BOT_TOKEN;
// አስተዳዳሪዎችን ለመለየት (ለምሳሌ: 123456, 789101)
const ADMIN_IDS = process.env.ADMIN_IDS ? process.env.ADMIN_IDS.split(/[, ]+/).map(id => parseInt(id.trim())) : [1062635928]; // @Abiymersha ID እዚህ ይገባል
const MINI_APP_URL = process.env.MINI_APP_URL;
const DB_FILE = 'edir_pro_final.db';

if (!BOT_TOKEN) {
    console.error("❌ BOT_TOKEN is missing!");
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
        joined_date TEXT
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
        file_id TEXT,
        status TEXT DEFAULT 'AWAIT_APPROVAL',
        timestamp TEXT
    );
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT,
        message TEXT,
        type TEXT,
        timestamp TEXT
    );
`);

const bot = new Telegraf(BOT_TOKEN);
bot.use(session());

const isAdmin = (id) => ADMIN_IDS.includes(id);

// --- 4. ADMIN HELPERS ---

function getDashboardStats() {
    const totalMembers = db.prepare("SELECT COUNT(*) as count FROM members").get().count;
    const totalSavings = db.prepare("SELECT SUM(total_amount) as total FROM payments WHERE status = 'APPROVED'").get().total || 0;
    const pendingCount = db.prepare("SELECT COUNT(*) as count FROM payments WHERE status = 'AWAIT_APPROVAL'").get().count;
    const eliteCount = db.prepare("SELECT COUNT(*) as count FROM members WHERE tier = 'ልዩ (Elite)'").get().count;
    
    return { totalMembers, totalSavings, pendingCount, eliteCount };
}

// --- 5. CORE HANDLERS ---

bot.start((ctx) => {
    const joinedDate = new Date().toLocaleDateString('am-ET');
    db.prepare('INSERT OR IGNORE INTO members (user_id, username, full_name, joined_date) VALUES (?, ?, ?, ?)').run(
        ctx.from.id, ctx.from.username || 'N/A', ctx.from.first_name, joinedDate
    );
    
    const kb = [[Markup.button.webApp("📱 ሚኒ አፑን ክፈት", MINI_APP_URL)]];
    
    if (isAdmin(ctx.from.id)) {
        kb.push(["⚙️ የአስተዳዳሪ ሁነታ (Admin Mode)"]);
    }
    
    kb.push(["📊 ሁኔታዬን እይ", "❓ እርዳታ"]);
    
    ctx.replyWithMarkdown(
        `እንኳን ወደ **እሁድን በፍቅር** ዲጂታል ዕድር መጡ! 👋\n\nከታች ያለውን ሜኑ በመጠቀም አገልግሎቶችን ያግኙ።`,
        Markup.keyboard(kb).resize()
    );
});

// --- 6. IMPROVED ADMIN MODE ---

bot.hears("⚙️ የአስተዳዳሪ ሁነታ (Admin Mode)", (ctx) => {
    if (!isAdmin(ctx.from.id)) return ctx.reply("ይህ ክፍል ለአስተዳዳሪዎች ብቻ የተፈቀደ ነው።");
    
    const stats = getDashboardStats();
    const adminKb = [
        ["📑 የሚጠባበቁ ክፍያዎች (" + stats.pendingCount + ")"],
        ["📈 አጠቃላይ ሪፖርት", "👥 የአባላት ዝርዝር"],
        ["📢 መልዕክት ላክ", "👤 ወደ አባልነት ተመለስ"]
    ];
    
    ctx.replyWithMarkdown(
        `🛠 **የአስተዳዳሪ መቆጣጠሪያ ማዕከል**\n\n` +
        `👥 ጠቅላላ አባላት: \`${stats.totalMembers}\`\n` +
        `💰 ጠቅላላ ቁጠባ: \`${stats.totalSavings} ብር\`\n` +
        `⏳ የሚጠባበቁ: \`${stats.pendingCount}\`\n` +
        `🌟 Elite አባላት: \`${stats.eliteCount}\``,
        Markup.keyboard(adminKb).resize()
    );
});

bot.hears("📑 የሚጠባበቁ ክፍያዎች", (ctx) => {
    if (!isAdmin(ctx.from.id)) return;
    const pending = db.prepare("SELECT * FROM payments WHERE status = 'AWAIT_APPROVAL' ORDER BY id ASC LIMIT 5").all();
    
    if (pending.length === 0) return ctx.reply("በአሁኑ ሰዓት የሚጠባበቅ ክፍያ የለም። ✅");
    
    pending.forEach(async (p) => {
        const caption = `🚨 **አዲስ ክፍያ ማረጋገጫ**\n\n` +
            `👤 ከፋይ: @${p.username}\n` +
            `🎯 ዓላማ: ${p.purpose}\n` +
            `📅 ጊዜ: ${p.period}\n` +
            `💰 መጠን: ${p.total_amount} ብር\n` +
            `⚠️ ቅጣት: ${p.penalty} ብር\n` +
            `💳 መንገድ: ${p.gateway.toUpperCase()}\n` +
            `🆔 ID: #${p.id}`;
            
        const inlineKb = Markup.inlineKeyboard([
            [Markup.button.callback("✅ አጽድቅ (Approve)", `adm_app_${p.id}`)],
            [Markup.button.callback("❌ ውድቅ አድርግ (Reject)", `adm_rej_${p.id}`)]
        ]);

        if (p.file_id) {
            await ctx.replyWithPhoto(p.file_id, { caption, parse_mode: 'Markdown', ...inlineKb });
        } else {
            await ctx.replyWithMarkdown(caption, inlineKb);
        }
    });
});

bot.hears("📈 አጠቃላይ ሪፖርት", (ctx) => {
    if (!isAdmin(ctx.from.id)) return;
    const stats = getDashboardStats();
    ctx.replyWithMarkdown(
        `📊 **ዝርዝር የዕድር ሪፖርት**\n\n` +
        `• ጠቅላላ አባላት: ${stats.totalMembers}\n` +
        `• ጠቅላላ የቁጠባ መጠን: ${stats.totalSavings} ብር\n` +
        `• በመጠባበቅ ላይ: ${stats.pendingCount}\n` +
        `• ሪፖርት የተሰናዳበት: ${new Date().toLocaleString('am-ET')}`
    );
});

bot.hears("👤 ወደ አባልነት ተመለስ", (ctx) => {
    const kb = [[Markup.button.webApp("📱 ሚኒ አፑን ክፈት", MINI_APP_URL)], ["📊 ሁኔታዬን እይ", "❓ እርዳታ"]];
    ctx.reply("ወደ አባልነት ሁነታ ተመልሰዋል።", Markup.keyboard(kb).resize());
});

// --- 7. ACTION HANDLERS (APPROVAL/REJECTION) ---

bot.action(/^adm_(app|rej)_(\d+)$/, async (ctx) => {
    if (!isAdmin(ctx.from.id)) return ctx.answerCbQuery("Authorized Only!");
    
    const action = ctx.match[1];
    const payId = ctx.match[2];
    const isApprove = action === 'app';
    
    const payment = db.prepare("SELECT * FROM payments WHERE id = ?").get(payId);
    if (!payment) return ctx.answerCbQuery("ክፍያው አልተገኘም!");

    db.prepare("UPDATE payments SET status = ? WHERE id = ?").run(isApprove ? 'APPROVED' : 'REJECTED', payId);
    
    if (isApprove) {
        // የቁጠባ ሂሳብ ጨምር
        db.prepare("UPDATE members SET total_savings = total_savings + ? WHERE user_id = ?").run(payment.total_amount, payment.user_id);
        
        // ለተጠቃሚው ኖቲፊኬሽን ላክ
        const time = new Date().toLocaleString('am-ET');
        db.prepare(`INSERT INTO notifications (user_id, title, message, type, timestamp) VALUES (?, ?, ?, ?, ?)`).run(
            payment.user_id, "ክፍያ ጸድቋል", `የ${payment.total_amount} ብር ክፍያዎ ተረጋግጦ ጽድቋል። እናመሰግናለን!`, 'success', time
        );
        
        try {
            await bot.telegram.sendMessage(payment.user_id, `✅ **የክፍያ ማረጋገጫ**\n\nየ${payment.total_amount} ብር የ${payment.purpose} ክፍያዎ በአስተዳዳሪው ጸድቋል።`);
        } catch (e) { console.log("User blocked bot"); }
    }

    const resultText = isApprove ? "✅ ጸድቋል" : "❌ ውድቅ ተደርጓል";
    await ctx.editMessageCaption(`${ctx.callbackQuery.message.caption || ctx.callbackQuery.message.text}\n\n🏁 **ውሳኔ:** ${resultText} (በ @${ctx.from.username})`);
    ctx.answerCbQuery("ክዋኔው ተጠናቋል");
});

bot.launch().then(() => console.log("🚀 ቦቱ በአስተዳዳሪ ሁነታ ስራ ጀምሯል::"));
