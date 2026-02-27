/**
 * እሁድን በፍቅር ዲጂታል ፕሮ v3.8 - አማርኛ (Amharic)
 * ይህ ቦት የአባላትን ምዝገባ፣ የክፍያ ማጽደቅ እና ሪፖርቶችን ይቆጣጠራል።
 */

require('dotenv').config();
const { Telegraf, session, Markup } = require('telegraf');
const Database = require('better-sqlite3');
const http = require('http');

const PORT = process.env.PORT || 3000;
http.createServer((req, res) => {
    res.writeHead(200);
    res.end('ቦቱ በስራ ላይ ነው');
}).listen(PORT);

const BOT_TOKEN = process.env.BOT_TOKEN;
const ADMIN_IDS = process.env.ADMIN_IDS ? process.env.ADMIN_IDS.split(/[, ]+/).map(id => parseInt(id.trim())) : [1062635928];
const MINI_APP_URL = process.env.MINI_APP_URL;
const DB_FILE = 'edir_pro_final.db';

if (!BOT_TOKEN) { process.exit(1); }

const db = new Database(DB_FILE);
db.exec(`
    CREATE TABLE IF NOT EXISTS members (user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, tier TEXT DEFAULT 'መሠረታዊ', total_savings REAL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, gateway TEXT, purpose TEXT, period TEXT, total_amount REAL, penalty REAL DEFAULT 0, pay_for_member TEXT, file_id TEXT, status TEXT DEFAULT 'AWAIT_APPROVAL', timestamp TEXT);
    CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, title TEXT, message TEXT, type TEXT, timestamp TEXT);
`);

const bot = new Telegraf(BOT_TOKEN);
bot.use(session());

const isAdmin = (id) => ADMIN_IDS.includes(id);

bot.start((ctx) => {
    db.prepare('INSERT OR IGNORE INTO members (user_id, username, full_name) VALUES (?, ?, ?)').run(ctx.from.id, ctx.from.username || 'N/A', ctx.from.first_name);
    const kb = [[Markup.button.webApp("📱 ሚኒ አፑን ክፈት", MINI_APP_URL)]];
    if (isAdmin(ctx.from.id)) kb.push(["⚙️ የአስተዳዳሪ ሁነታ (Admin Mode)"]);
    ctx.replyWithMarkdown(`እንኳን ወደ **እሁድን በፍቅር** ዲጂታል ዕድር መጡ! 👋`, Markup.keyboard(kb).resize());
});

bot.hears("⚙️ የአስተዳዳሪ ሁነታ (Admin Mode)", (ctx) => {
    if (!isAdmin(ctx.from.id)) return;
    const stats = db.prepare("SELECT COUNT(*) as c FROM payments WHERE status = 'AWAIT_APPROVAL'").get();
    const adminKb = [["📑 የሚጠባበቁ ክፍያዎች (" + stats.c + ")"], ["📈 አጠቃላይ ሪፖርት", "👤 ወደ አባልነት ተመለስ"]];
    ctx.reply("🛠 የአስተዳዳሪ መቆጣጠሪያ ማዕከል", Markup.keyboard(adminKb).resize());
});

bot.on('web_app_data', async (ctx) => {
    try {
        const data = JSON.parse(ctx.webAppData.data.json());
        if (data.type === 'payment_report') {
            const time = new Date().toLocaleString('am-ET');
            ctx.session.pendingPayment = { ...data, timestamp: time };
            if (data.gateway === 'manual') {
                await ctx.reply(`✅ የ${data.amount} ብር የ${data.purpose} መረጃ ተመዝግቧል። 📷 እባክዎ የባንክ ደረሰኝዎን ፎቶ አሁን ይላኩ።`);
            } else {
                db.prepare(`INSERT INTO payments (user_id, username, gateway, purpose, period, total_amount, penalty, pay_for_member, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`)
                  .run(ctx.from.id, ctx.from.username || 'N/A', data.gateway, data.purpose, data.period, data.amount, data.penalty, data.payFor, time);
                await ctx.reply(`🚀 የ${data.gateway} ክፍያዎ ተመዝግቧል። ለፋይናንስ ኦፊሰር እንዲረጋገጥ ተልኳል።`);
            }
        }
    } catch (e) { console.error(e); }
});

bot.on(['photo', 'document'], async (ctx) => {
    const pending = ctx.session?.pendingPayment;
    if (!pending) return;
    const fileId = ctx.message.photo ? ctx.message.photo.pop().file_id : ctx.message.document.file_id;
    db.prepare(`INSERT INTO payments (user_id, username, gateway, purpose, period, total_amount, penalty, pay_for_member, file_id, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .run(ctx.from.id, ctx.from.username || 'N/A', pending.gateway, pending.purpose, pending.period, pending.amount, pending.penalty, pending.payFor, fileId, pending.timestamp);
    ctx.session.pendingPayment = null; 
    await ctx.reply(`📩 ደረሰኝዎ ተልኳል። እናመሰግናለን!`);
});

bot.launch().then(() => console.log("🚀 ቦቱ በስራ ላይ ነው"));
