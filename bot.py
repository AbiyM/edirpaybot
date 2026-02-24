/**
 * Edir Digital Pro v3.6 - Backend Bot Code
 * ቋንቋ: አማርኛ (Amharic)
 * ቴክኖሎጂ: Node.js, Telegraf, Better-SQLite3
 */

require('dotenv').config();
const { Telegraf, session, Markup } = require('telegraf');
const Database = require('better-sqlite3');
const http = require('http');

// --- 1. ኮንፊገሬሽን (Configuration) ---
// እነዚህን መረጃዎች በ .env ፋይል ውስጥ ያስቀምጡ
const BOT_TOKEN = process.env.BOT_TOKEN;
const ADMIN_ID = process.env.ADMIN_ID ? parseInt(process.env.ADMIN_ID) : null;
const MINI_APP_URL = process.env.MINI_APP_URL;
const GITHUB_URL = process.env.GITHUB_URL || "https://github.com/"; // የGitHub ሊንክ እዚህ ይገባል

if (!BOT_TOKEN) {
    console.error("❌ ስህተት: የቦት ቶከን (BOT_TOKEN) አልተገኘም!");
    process.exit(1);
}

// --- 2. ዳታቤዝ ዝግጅት (Database Setup) ---
const db = new Database('edir_pro_v3.db');

// የዳታቤዝ ሰንጠረዦችን መፍጠር
db.exec(`
    CREATE TABLE IF NOT EXISTS members (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        tier TEXT DEFAULT 'መሠረታዊ',
        status TEXT DEFAULT 'PENDING'
    );
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        gateway TEXT,
        purpose TEXT,
        base_amount REAL DEFAULT 0,
        penalty_amount REAL DEFAULT 0,
        total_amount REAL,
        tx_ref TEXT,
        file_id TEXT,
        status TEXT DEFAULT 'AWAIT_APPROVAL',
        timestamp TEXT
    );
`);

const bot = new Telegraf(BOT_TOKEN);
bot.use(session());

// ሰዓት ለማስተካከል
const getAddisTime = () => {
    return new Date().toLocaleString('en-GB', { timeZone: 'Africa/Addis_Ababa' });
};

// --- 3. ቦት ትዕዛዞች (Bot Commands) ---

bot.start((ctx) => {
    const from = ctx.from;
    db.prepare('INSERT OR IGNORE INTO members (user_id, username, full_name) VALUES (?, ?, ?)').run(
        from.id, 
        from.username || 'N/A', 
        from.first_name + (from.last_name ? ' ' + from.last_name : '')
    );
    
    const welcomeMsg = `እንኳን ወደ **እሁድን በፍቅር** ዲጂታል መተግበሪያ በሰላም መጡ! 👋\n\n` +
        `ይህ ቦት መዋጮዎን እንዲከፍሉ፣ የክፍያ ሁኔታዎን እንዲከታተሉ እና የብድር አገልግሎቶችን እንዲያገኙ ይረዳዎታል።\n\n` +
        `ለመጀመር '📱 ሚኒ አፑን ተጠቀም' የሚለውን ቁልፍ ይጫኑ።`;
    
    return ctx.replyWithMarkdown(welcomeMsg, 
        Markup.keyboard([
            [Markup.button.webApp("📱 ሚኒ አፑን ተጠቀም", MINI_APP_URL)],
            ["❓ እርዳታ"]
        ]).resize()
    );
});

// የGitHub ሊንክ ትዕዛዝ
bot.command('github', (ctx) => {
    return ctx.replyWithMarkdown(`💻 **የምንጭ ኮድ (Source Code)**\n\nየዚህን መተግበሪያ ምንጭ ኮድ በGitHub ለማግኘት ከታች ያለውን ሊንክ ይጫኑ:\n\n🔗 [GitHub Repository](${GITHUB_URL})`);
});

// --- 4. የሚኒ አፕ መረጃ መቀበያ (Mini App Data Handler) ---

bot.on('web_app_data', async (ctx) => {
    try {
        const data = JSON.parse(ctx.webAppData.data.json());
        
        if (data.type === 'payment_report') {
            const isDigital = data.isDigital === true;
            const gatewayDisplay = data.gateway.toUpperCase();
            const serverTime = getAddisTime();
            
            // መረጃውን ለጊዜው በሴሽን ማስቀመጥ (ለፎቶ መጠበቂያ)
            ctx.session.pendingPayment = { 
                ...data, 
                userId: ctx.from.id, 
                username: ctx.from.username || 'N/A',
                time: serverTime
            };

            let replyMsg = `✅ **የ${data.purpose}** መረጃ ተመዝግቧል!\n\n`;
            replyMsg += `💳 መንገድ፦ ${gatewayDisplay}\n`;
            replyMsg += `💰 መጠን፦ **${data.totalAmount} ብር**\n`;
            replyMsg += `📅 ቀን፦ ${serverTime}\n`;

            if (isDigital) {
                replyMsg += `🔢 TX Ref: \`${data.tx_ref}\` \n\n`;
                replyMsg += `🚀 የዲጂታል ክፍያ መረጃዎ ለገንዘብ ያዡ ተልኳል። ሲረጋገጥ እናሳውቅዎታለን።`;
                
                // ዲጂታል ከሆነ በቀጥታ ዳታቤዝ መመዝገብ
                const res = db.prepare(`
                    INSERT INTO payments (user_id, username, gateway, purpose, total_amount, tx_ref, timestamp) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                `).run(ctx.from.id, ctx.from.username, data.gateway, data.purpose, data.totalAmount, data.tx_ref, serverTime);

                // ለአስተዳዳሪው ማሳወቅ
                notifyAdmin(ctx, data, res.lastInsertRowid, null, serverTime);
            } else {
                replyMsg += `\n📷 አሁን የባንክ ደረሰኝዎን (Receipt) ፎቶ ወይም ስክሪንሾት እዚህ ይላኩ።`;
            }

            await ctx.replyWithMarkdown(replyMsg);
        }
    } catch (e) {
        console.error("Web App Data Error:", e);
        ctx.reply("❌ መረጃውን በማስተናገድ ላይ ስህተት አጋጥሟል። እባክዎ ደግመው ይሞክሩ።");
    }
});

// --- 5. የፎቶ/ደረሰኝ መቀበያ (Receipt Handler) ---

bot.on(['photo', 'document'], async (ctx) => {
    const pending = ctx.session?.pendingPayment;
    
    if (!pending || pending.gateway === 'easypay') {
        return ctx.reply("እባክዎ መጀመሪያ በሚኒ አፑ በኩል የክፍያ ፎርሙን ይሙሉ::");
    }

    const fileId = ctx.message.photo ? ctx.message.photo.pop().file_id : ctx.message.document.file_id;
    const time = pending.time || getAddisTime();
    
    // በዳታቤዝ መመዝገብ
    const res = db.prepare(`
        INSERT INTO payments (user_id, username, gateway, purpose, base_amount, penalty_amount, total_amount, file_id, timestamp) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
        pending.userId, pending.username, 'MANUAL', pending.purpose, 
        pending.baseAmount, pending.penaltyAmount, pending.totalAmount, fileId, time
    );

    ctx.session.pendingPayment = null; // ሴሽኑን ማጽዳት

    // ለአስተዳዳሪው ማሳወቅ
    notifyAdmin(ctx, pending, res.lastInsertRowid, fileId, time);

    await ctx.reply("📩 ደረሰኝዎ ለገንዘብ ያዡ ተልኳል። ሲረጋገጥ መልእክት ይደርስዎታል። እናመሰግናለን!");
});

// --- 6. የአስተዳዳሪ ማሳወቂያ (Admin Notification) ---

async function notifyAdmin(ctx, data, dbId, fileId, time) {
    if (!ADMIN_ID) return;

    const adminKb = Markup.inlineKeyboard([
        [Markup.button.callback('✅ አጽድቅ (Approve)', `p_app_${dbId}_${ctx.from.id}`)],
        [Markup.button.callback('❌ ውድቅ አድርግ (Reject)', `p_rej_${dbId}_${ctx.from.id}`)]
    ]);

    const adminCaption = `🚨 **አዲስ የክፍያ ሪፖርት**\n\n` +
        `👤 አባል፦ @${ctx.from.username || 'N/A'} (${ctx.from.id})\n` +
        `🎯 ዓላማ፦ ${data.purpose}\n` +
        `💳 መንገድ፦ ${data.gateway.toUpperCase()}\n` +
        `💵 መጠን፦ ${data.totalAmount} ብር\n` +
        `📅 ቀን፦ ${time}\n` +
        (data.tx_ref ? `🔢 TX Ref: \`${data.tx_ref}\`` : `📷 ደረሰኝ ከታች ተያይዟል`);

    if (fileId) {
        await ctx.telegram.sendPhoto(ADMIN_ID, fileId, { caption: adminCaption, parse_mode: 'Markdown', ...adminKb });
    } else {
        await ctx.telegram.sendMessage(ADMIN_ID, adminCaption, { parse_mode: 'Markdown', ...adminKb });
    }
}

// --- 7. የአስተዳዳሪ ውሳኔዎች (Admin Decisions) ---

bot.action(/^(p_app|p_rej)_(\d+)_(\d+)$/, async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return ctx.answerCbQuery("ፈቃድ የለዎትም!");

    const [action, dbId, targetUserId] = [ctx.match[1], ctx.match[2], parseInt(ctx.match[3])];
    const isApprove = action === 'p_app';

    // ዳታቤዝ ማዘመን
    db.prepare(`UPDATE payments SET status = ? WHERE id = ?`).run(isApprove ? 'APPROVED' : 'REJECTED', dbId);
    
    if (isApprove) {
        db.prepare("UPDATE members SET status = 'APPROVED' WHERE user_id = ?").run(targetUserId);
    }

    // ለአባሉ መልእክት መላክ
    const notifyMsg = isApprove 
        ? "🎉 እንኳን ደስ አለዎት! ክፍያዎ በአስተዳዳሪው ጸድቋል። በሚኒ አፑ 'ሁኔታ' ገጽ ላይ ማየት ይችላሉ።" 
        : "⚠️ ይቅርታ፣ የላኩት የክፍያ መረጃ በአስተዳዳሪው ውድቅ ተደርጓል። እባክዎ መረጃውን በድጋሚ በትክክል ይላኩ።";

    try {
        await ctx.telegram.sendMessage(targetUserId, notifyMsg);
    } catch (e) {
        console.error("User notification failed", e);
    }

    const currentCaption = ctx.callbackQuery.message.caption || ctx.callbackQuery.message.text;
    const resultText = isApprove ? 'ጸድቋል ✅' : 'ውድቅ ተደርጓል ❌';
    
    if (ctx.callbackQuery.message.photo) {
        await ctx.editMessageCaption(`${currentCaption}\n\n🏁 ውጤት፦ ${resultText}`);
    } else {
        await ctx.editMessageText(`${currentCaption}\n\n🏁 ውጤት፦ ${resultText}`);
    }
    
    await ctx.answerCbQuery(isApprove ? "ጸድቋል" : "ተሰርዟል");
});

// --- 8. ተጨማሪ ትዕዛዞች (Misc) ---

bot.hears("❓ እርዳታ", (ctx) => {
    ctx.replyWithMarkdown(`📖 **አጭር መመሪያ**\n\n` +
        `1. '📱 ሚኒ አፑን ተጠቀም' የሚለውን ይጫኑ\n` +
        `2. በሚከፈተው ፎርም ላይ የክፍያ መረጃውን ይሙሉ\n` +
        `3. በደረሰኝ ከሆነ የባንክ ደረሰኝ ፎቶ እዚህ ቦት ላይ ይላኩ\n` +
        `4. ክፍያው በአስተዳዳሪው ሲረጋገጥ መልእክት ይደርስዎታል።\n\n` +
        `💻 **GitHub:** የኮዱን ምንጭ ለማየት /github ይበሉ።`);
});

// ሰርቨር ጤንነት መቆጣጠሪያ (Health Check)
http.createServer((req, res) => { res.writeHead(200); res.end('Bot is running'); }).listen(process.env.PORT || 3000);

bot.launch().then(() => console.log('🚀 Edir Pro Bot is active...'));
