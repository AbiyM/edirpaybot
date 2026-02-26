/**
 * እሁድን በፍቅር ዲጂታል ፕሮ v3.6 - የኋላ ደንብ (Backend Bot)
 * ይህ ቦት የአባላትን ምዝገባ፣ የክፍያ ሪፖርቶችን መቀበል (ለራስም ሆነ ለሌላ ሰው)፣ 
 * ደረጃ ማሳደግ እና የፋይናንስ ኦፊሰሮች ክፍያ እንዲያጸድቁ መፍቀድን ይቆጣጠራል።
 */

require('dotenv').config();
const { Telegraf, session, Markup } = require('telegraf');
const Database = require('better-sqlite3');
const http = require('http');
const fs = require('fs');

// --- 1. የሬንደር (RENDER) መረጋጋት መጠበቂያ ---
/**
 * ሬንደር ቦቱ መስራቱን የሚያውቅበትን ፖርት (Port) በፍጥነት ማግኘት አለበት።
 * ይህ ሰርቨር "Bad Gateway" ስህተት እንዳይከሰት ይከላከላል።
 */
const PORT = process.env.PORT || 3000;
http.createServer((req, res) => {
    res.writeHead(200);
    res.end('ቦቱ በስራ ላይ ነው');
}).listen(PORT);

// --- 2. ውቅረት እና የአካባቢ ተለዋዋጮች (ENV VARIABLES) ---
const BOT_TOKEN = process.env.BOT_TOKEN;

// የአድሚን/ፋይናንስ ኦፊሰር መለያ ቁጥሮችን መለየት
const ADMIN_IDS = process.env.ADMIN_IDS 
    ? process.env.ADMIN_IDS.split(/[, ]+/).map(id => parseInt(id.trim())).filter(id => !isNaN(id)) 
    : [];

const MINI_APP_URL = process.env.MINI_APP_URL;
const TEST_GROUP_ID = process.env.TEST_GROUP_ID ? parseInt(process.env.TEST_GROUP_ID) : -1003740305702;
const DB_FILE = 'edir_pro_v3.db';

if (!BOT_TOKEN) {
    console.error("❌ የቦት ቶከን (BOT_TOKEN) አልተገኘም!");
    process.exit(1);
}

// --- 3. የዳታቤዝ ዝግጅት ---
const db = new Database(DB_FILE);
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
        period TEXT,
        total_amount REAL,
        penalty REAL DEFAULT 0,
        pay_for_member TEXT,
        file_id TEXT,
        status TEXT DEFAULT 'AWAIT_APPROVAL',
        timestamp TEXT
    );
`);

const bot = new Telegraf(BOT_TOKEN);
bot.use(session());

// አድሚን መሆኑን ማረጋገጫ
const isAdmin = (id) => ADMIN_IDS.includes(id);

// --- 4. የአባላት ደረጃ ማሳደጊያ ሎጂክ ---
function updateMemberTier(userId) {
    const stats = db.prepare(`SELECT COUNT(*) as count FROM payments WHERE user_id = ? AND status = 'APPROVED'`).get(userId);
    let newTier = 'መሠረታዊ';
    if (stats.count >= 12) newTier = 'ልዩ (Elite)';
    else if (stats.count >= 5) newTier = 'ፕሮ (Pro)';
    
    db.prepare("UPDATE members SET tier = ? WHERE user_id = ?").run(newTier, userId);
    return newTier;
}

// --- 5. የፋይናንስ ኦፊሰር ማሳወቂያ ---
async function notifyFinance(ctx, data, dbId, fileId, time) {
    const payerName = data.payFor === 'self' ? "ለራሱ (Self)" : `ለአባል: ${data.payFor}`;
    const caption = `🚨 **አዲስ የክፍያ ሪፖርት**\n\n` +
                `👤 የከፋይ: @${ctx.from.username}\n` +
                `🎯 ለማን: **${payerName}**\n` +
                `📅 ጊዜ: ${data.period}\n` +
                `💰 መጠን: ${data.amount} ብር\n` +
                `⚠️ ቅጣት: ${data.penalty || 0} ብር\n` +
                `📝 ዓላማ: ${data.purpose}`;
    
    const kb = Markup.inlineKeyboard([
        [Markup.button.callback('✅ አጽድቅ', `p_app_${dbId}_${ctx.from.id}`)],
        [Markup.button.callback('❌ ውድቅ አድርግ', `p_rej_${dbId}_${ctx.from.id}`)]
    ]);

    try {
        if (fileId) {
            await bot.telegram.sendPhoto(TEST_GROUP_ID, fileId, { caption, parse_mode: 'Markdown', ...kb });
        } else {
            await bot.telegram.sendMessage(TEST_GROUP_ID, caption, { parse_mode: 'Markdown', ...kb });
        }
    } catch (e) { console.error("Notification Error", e.message); }
}

// --- 6. የቦቱ ዋና ተግባራት ---

bot.start((ctx) => {
    db.prepare('INSERT OR IGNORE INTO members (user_id, username, full_name) VALUES (?, ?, ?)').run(
        ctx.from.id, 
        ctx.from.username || 'N/A', 
        ctx.from.first_name
    );
    const kb = [[Markup.button.webApp("📱 ሚኒ አፑን ተጠቀም", MINI_APP_URL)]];
    if (isAdmin(ctx.from.id)) kb.push(["⚙️ የአስተዳዳሪ ሁነታ (Admin Mode)"]);
    kb.push(["📊 ሁኔታዬን እይ", "❓ እርዳታ"]);
    ctx.replyWithMarkdown(`እንኳን ወደ **እሁድን በፍቅር** መጡ! 👋\nአሁን ለራስዎ ወይም ለሌላ አባል መክፈል ይችላሉ።`, Markup.keyboard(kb).resize());
});

bot.command('checkme', (ctx) => {
    const id = ctx.from.id;
    const status = isAdmin(id) ? "✅ የፋይናንስ ኦፊሰር ነዎት" : "❌ ተራ አባል ነዎት";
    ctx.replyWithMarkdown(`🆔 የእርስዎ ID: \`${id}\`\n🛡 ሁኔታ: ${status}`);
});

bot.hears("⚙️ የአስተዳዳሪ ሁነታ (Admin Mode)", (ctx) => {
    if (isAdmin(ctx.from.id)) {
        const adminKb = [
            ["📑 የሚጠባበቁ", "📈 ዝርዝር ሪፖርት"],
            ["📊 አጠቃላይ ማጠቃለያ", "👤 ወደ አባልነት ተመለስ"]
        ];
        ctx.reply("🛠 የአስተዳዳሪ ሁነታ ገብተዋል::", Markup.keyboard(adminKb).resize());
    }
});

bot.hears("👤 ወደ አባልነት ተመለስ", (ctx) => {
    const kb = [[Markup.button.webApp("📱 ሚኒ አፑን ተጠቀም", MINI_APP_URL)], ["📊 ሁኔታዬን እይ", "❓ እርዳታ"]];
    ctx.reply("👤 ወደ አባልነት ሁነታ ተመልሰዋል::", Markup.keyboard(kb).resize());
});

bot.hears("📑 የሚጠባበቁ", (ctx) => {
    if (!isAdmin(ctx.from.id)) return;
    const pending = db.prepare(`SELECT * FROM payments WHERE status = 'AWAIT_APPROVAL' ORDER BY id DESC`).all();
    if (pending.length === 0) return ctx.reply("ምንም የሚጠባበቅ ክፍያ የለም።");
    
    let msg = `⏳ **ለማጽደቅ የሚጠባበቁ ክፍያዎች**\n\n`;
    pending.forEach((p, i) => {
        const target = p.pay_for_member === 'self' ? p.username : p.pay_for_member;
        msg += `${i + 1}. @${p.username} -> ${target} (${p.total_amount} ብር)\n`;
    });
    ctx.replyWithMarkdown(msg);
});

// --- 7. የክፍያ ሂደት ---

bot.on('web_app_data', async (ctx) => {
    try {
        const data = JSON.parse(ctx.webAppData.data.json());
        if (data.type === 'payment_report') {
            const time = new Date().toLocaleString();
            ctx.session.pendingPayment = { ...data, timestamp: time };

            if (data.gateway === 'manual') {
                await ctx.reply(`✅ የ${data.amount} ብር ክፍያ መረጃ ተመዝግቧል። 📷 አሁን ደረሰኝ ይላኩ።`);
            } else {
                const res = db.prepare(`INSERT INTO payments (user_id, username, gateway, purpose, period, total_amount, penalty, pay_for_member, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`)
                    .run(ctx.from.id, ctx.from.username || 'N/A', data.gateway, data.purpose, data.period, data.amount, data.penalty, data.payFor, time);
                notifyFinance(ctx, data, res.lastInsertRowid, null, time);
                await ctx.reply(`🚀 ክፍያው ተመዝግቧል። ለፋይናንስ ኦፊሰር ተልኳል።`);
            }
        }
    } catch (e) { console.error("Data error:", e); }
});

bot.on(['photo', 'document'], async (ctx) => {
    const pending = ctx.session?.pendingPayment;
    if (!pending) return;

    const fileId = ctx.message.photo ? ctx.message.photo.pop().file_id : ctx.message.document.file_id;
    const res = db.prepare(`INSERT INTO payments (user_id, username, gateway, purpose, period, total_amount, penalty, pay_for_member, file_id, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
        .run(ctx.from.id, ctx.from.username || 'N/A', pending.gateway, pending.purpose, pending.period, pending.amount, pending.penalty, pending.payFor, fileId, pending.timestamp);
    
    notifyFinance(ctx, pending, res.lastInsertRowid, fileId, pending.timestamp);
    ctx.session.pendingPayment = null; 
    await ctx.reply(`📩 ደረሰኝዎ ተልኳል። እናመሰግናለን!`);
});

bot.action(/^(p_app|p_rej)_(\d+)_(\d+)$/, async (ctx) => {
    if (!isAdmin(ctx.from.id)) return ctx.answerCbQuery("Authorized Only!");
    
    const [action, dbId, targetUid] = [ctx.match[1], ctx.match[2], parseInt(ctx.match[3])];
    const isApprove = action === 'p_app';
    
    db.prepare(`UPDATE payments SET status = ? WHERE id = ?`).run(isApprove ? 'APPROVED' : 'REJECTED', dbId);
    
    if (isApprove) {
        const tier = updateMemberTier(targetUid);
        if (TEST_GROUP_ID && tier !== 'መሠረታዊ') {
            bot.telegram.sendMessage(TEST_GROUP_ID, `🌟 **የደረጃ ዕድገት!**\nአባል @${(await ctx.telegram.getChatMember(targetUid, targetUid)).user.username} አሁን **${tier}** ናቸው። 🎉`);
        }
    }
    
    const statusText = isApprove ? 'ጸድቋል ✅' : 'ውድቅ ተደርጓል ❌';
    ctx.editMessageText(`${ctx.callbackQuery.message.text || ctx.callbackQuery.message.caption}\n\n🏁 ውጤት በ @${ctx.from.username}: ${statusText}`);
    ctx.answerCbQuery("ተጠናቀቀ");
});

bot.launch().then(() => console.log("🚀 ቦቱ ስራ ጀምሯል"));
