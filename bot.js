require('dotenv').config();
const { Telegraf, session, Markup } = require('telegraf');
const Database = require('better-sqlite3');
const fs = require('fs');

// --- CONFIGURATION ---
// Render ወይም ሰርቨር ላይ የተቀመጡትን Environment Variables ያነባል
const BOT_TOKEN = process.env.BOT_TOKEN;
const ADMIN_ID = process.env.ADMIN_ID ? parseInt(process.env.ADMIN_ID) : null;
const MINI_APP_URL = process.env.MINI_APP_URL;
const EDIR_GROUP_ID = process.env.EDIR_GROUP_ID; 

// Debugging: ቶክኑ መኖሩን በሰርቨር ሎግ ላይ ለማረጋገጥ
if (!BOT_TOKEN) {
    console.error("❌ ERROR: BOT_TOKEN is missing! Check Render Environment Variables.");
    process.exit(1);
}

// Initialize Database (members.db ፋይል በራሱ ይፈጠራል)
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
// ተጠቃሚው የእድሩ ግሩፕ አባል መሆኑን የሚያረጋግጥ ሲስተም
const checkGroupMembership = async (ctx, next) => {
    if (ctx.from && ctx.chat.type === 'private') {
        try {
            if (!EDIR_GROUP_ID) return next(); 
            const member = await ctx.telegram.getChatMember(EDIR_GROUP_ID, ctx.from.id);
            const allowed = ['member', 'administrator', 'creator'];
            if (!allowed.includes(member.status)) {
                return ctx.reply("❌ ይቅርታ! ይህን ቦት ለመጠቀም መጀመሪያ የእሁድን በፍቅር የቴሌግራም ግሩፕ አባል መሆን አለብዎት።");
            }
        } catch (error) {
            console.error("Group Check Error:", error.message);
            return ctx.reply("⚠️ የደህንነት ማረጋገጫ ስህተት። ቦቱ በግሩፑ ውስጥ Admin መሆኑን ያረጋግጡ።");
        }
    }
    return next();
};

// --- USER COMMANDS ---
bot.start(checkGroupMembership, (ctx) => {
    // አዲስ ተጠቃሚ ሲመጣ በዳታቤዝ ውስጥ መመዝገብ
    db.prepare('INSERT OR IGNORE INTO members (user_id, username) VALUES (?, ?)').run(ctx.from.id, ctx.from.username || 'N/A');
    
    const welcomeMsg = `እንኳን ወደ **እሁድን በፍቅር** የክፍያ ቦት በሰላም መጡ! 🚀\n\n` +
        `መዋጮን፣ ቅጣትን እና የብድር አገልግሎትን እዚህ ማስተዳደር ይችላሉ።\n\n` +
        `**ክፍያ ለመፈጸም** ከታች ያለውን ሰማያዊ ቁልፍ ይጠቀሙ።`;
    
    return ctx.replyWithMarkdown(welcomeMsg, 
        Markup.keyboard([
            [Markup.button.webApp("🚀 ክፍያ ያስገቡ", MINI_APP_URL)],
            ["📊 የጥያቄዬ ሁኔታ", "❓ እርዳታ"]
        ]).resize()
    );
});

// ሰርቨሩ መስራቱን ለማረጋገጫ
bot.command('ping', (ctx) => ctx.reply('pong'));

// ስህተት ሲፈጠር ሎግ ላይ ለማሳየት
bot.catch((err) => {
    console.error('Telegraf error:', err);
});

// ቦቱን ማስጀመር
bot.launch()
    .then(() => console.log('✅ Ehuden Befikir Bot is ACTIVE!'))
    .catch((err) => {
        console.error('❌ Bot launch failed:', err.message);
        if (err.message.includes('401')) {
            console.error("👉 ማሳሰቢያ፡ BOT_TOKEN ስህተት ነው። እባክዎ አዲስ ቶክን ከ @BotFather ወስደው Render ላይ ይቀይሩ።");
        }
    });

// ሲስተሙ ሲዘጋ ቦቱንም በሰላም ማቆም
process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
