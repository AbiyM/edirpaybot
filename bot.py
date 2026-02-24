/**
 * Edir Digital Pro v3.6 - Backend System
 * Powered by Telegraf, SQLite & Node.js
 */

require('dotenv').config();
const { Telegraf, session, Markup } = require('telegraf');
const Database = require('better-sqlite3');
const http = require('http');

// --- ኮንፊገሬሽን ---
const BOT_TOKEN = process.env.BOT_TOKEN;
const ADMIN_ID = process.env.ADMIN_ID ? parseInt(process.env.ADMIN_ID) : null;
const MINI_APP_URL = process.env.MINI_APP_URL;

if (!BOT_TOKEN) {
    console.error("❌ ስህተት: BOT_TOKEN አልተገኘም!");
    process.exit(1);
}

// ዳታቤዝ ዝግጅት
const db = new Database('edir_pro.db');

// የዳታቤዝ ሰንጠረዦች (Schema)
db.exec(`
    CREATE TABLE IF NOT EXISTS members (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
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
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    );
`);

const bot = new Telegraf(BOT_TOKEN);
bot.use(session());

// --- የጅማሬ መልእክት ---
bot.start((ctx) => {
    const from = ctx.from;
    db.prepare('INSERT OR IGNORE INTO members (user_id, username, full_name) VALUES (?, ?, ?)').run(
        from.id, 
        from.username || 'N/A', 
        from.first_name + (from.last_name ? ' ' + from.last_name : '')
    );
    
    const welcome = `እንኳን ወደ **እሁድን በፍቅር** ዲጂታል መተግበሪያ በሰላም መጡ! 👋\n\n` +
        `እዚህ መዋጮዎን መክፈል፣ የክፍያ ሁኔታዎን ማየት እና የብድር አገልግሎቶችን ማግኘት ይችላሉ።\n\n` +
        `ለመጀመር '🚀 ክፍያ ፈጽም' የሚለውን ይጫኑ።`;
    
    return ctx.replyWithMarkdown(welcome, 
        Markup.keyboard([
            [Markup.button.webApp("🚀 ክፍያ ፈጽም", MINI_APP_URL)],
            ["📊 የክፍያ ሁኔታ", "❓ እርዳታ"]
        ]).resize()
    );
});

// --- ከሚኒ አፑ መረጃ መቀበያ (Web App Data Handlers) ---
bot.on('web_app_data', async (ctx) => {
    try {
        const data = JSON.parse(ctx.webAppData.data.json());
        
        if (data.type === 'payment_report') {
            const isDigital = data.isDigital === true;
            const gatewayName = data.gateway.toUpperCase();
            
            // ለጊዜው በሴሽን ውስጥ መረጃውን ማስቀመጥ (ለፎቶ መጠበቂያ)
            ctx.session.pendingPayment = { 
                ...data, 
                userId: ctx.from.id, 
                username: ctx.from.username || 'N/A' 
            };

            let msg = `✅ **የ${data.purpose}** መረጃ ተመዝግቧል!\n\n`;
            msg += `💳 የክፍያ መንገድ፦ ${gatewayName}\n`;
            msg += `💰 ጠቅላላ መጠን፦ **${data.totalAmount} ETB**\n`;

            if (isDigital) {
                msg += `🔢 TX Ref: \`${data.tx_ref}\` \n\n`;
                msg += `🚀 የዲጂታል ክፍያ መረጃዎ ለገንዘብ ያዡ ተልኳል። ሲረጋገጥ እናሳውቅዎታለን።`;
                
                // ዲጂታል ከሆነ በቀጥታ ዳታቤዝ ውስጥ መመዝገብ
                const res = db.prepare(`
                    INSERT INTO payments (user_id, username, gateway, purpose, total_amount, tx_ref, status) 
                    VALUES (?, ?, ?, ?, ?, ?, 'AWAIT_APPROVAL')
                `).run(ctx.from.id, ctx.from.username, data.gateway, data.purpose, data.totalAmount, data.tx_ref);

                // ለአስተዳዳሪ ማሳወቅ
                sendAdminNotification(ctx, data, res.lastInsertRowid, null);
            } else {
                msg += `\n📷 አሁን የባንክ ደረሰኝዎን (Receipt) ፎቶ ወይም ስክሪንሾት እዚህ ይላኩ።`;
            }

            await ctx.replyWithMarkdown(msg);
        }
    } catch (e) {
        console.error("Web App Data Error:", e);
        ctx.reply("❌ መረጃውን በማስተናገድ ላይ ስህተት አጋጥሟል።");
    }
});

// --- የደረሰኝ ፎቶ መቀበያ ---
bot.on(['photo', 'document'], async (ctx) => {
    const pending = ctx.session?.pendingPayment;
    
    if (!pending || pending.gateway !== 'manual') {
        return ctx.reply("እባክዎ መጀመሪያ በሚኒ አፑ በኩል የክፍያ ፎርሙን ይሙሉ::");
    }

    const fileId = ctx.message.photo ? ctx.message.photo.pop().file_id : ctx.message.document.file_id;
    
    // ዳታቤዝ ውስጥ መመዝገብ
    const res = db.prepare(`
        INSERT INTO payments (user_id, username, gateway, purpose, base_amount, penalty_amount, total_amount, file_id) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
        pending.userId, pending.username, 'MANUAL', pending.purpose, 
        pending.baseAmount, pending.penaltyAmount, pending.totalAmount, fileId
    );

    ctx.session.pendingPayment = null; // ሴሽኑን ማፅዳት

    // ለአስተዳዳሪ ማሳወቅ
    sendAdminNotification(ctx, pending, res.lastInsertRowid, fileId);

    await ctx.reply("📩 ደረሰኝዎ ለገንዘብ ያዡ ተልኳል። ሲረጋገጥ መልእክት ይደርስዎታል። እናመሰግናለን!");
});

// --- ለአስተዳዳሪ (ገንዘብ ያዥ) ማሳወቂያ መላኪያ ---
async function sendAdminNotification(ctx, data, dbId, fileId) {
    if (!ADMIN_ID) return;

    const adminKb = Markup.inlineKeyboard([
        [Markup.button.callback('✅ አጽድቅ (Approve)', `approve_${dbId}_${ctx.from.id}`)],
        [Markup.button.callback('❌ ሰርዝ (Reject)', `reject_${dbId}_${ctx.from.id}`)]
    ]);

    const adminMsg = `🚨 **አዲስ የክፍያ ሪፖርት**\n\n` +
        `👤 አባል፦ @${ctx.from.username || 'N/A'} (${ctx.from.id})\n` +
        `🎯 ዓላማ፦ ${data.purpose}\n` +
        `💳 መንገድ፦ ${data.gateway.toUpperCase()}\n` +
        `💵 መጠን፦ ${data.totalAmount} ETB\n` +
        (data.tx_ref ? `🔢 TX Ref: \`${data.tx_ref}\`` : `📷 ደረሰኝ ከታች ተያይዟል`);

    if (fileId) {
        await ctx.telegram.sendPhoto(ADMIN_ID, fileId, { caption: adminMsg, parse_mode: 'Markdown', ...adminKb });
    } else {
        await ctx.telegram.sendMessage(ADMIN_ID, adminMsg, { parse_mode: 'Markdown', ...adminKb });
    }
}

// --- የአስተዳዳሪ ውሳኔዎች (Approval Actions) ---
bot.action(/^(approve|reject)_(\d+)_(\d+)$/, async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return ctx.answerCbQuery("ፈቃድ የለዎትም!");

    const [action, dbId, targetUserId] = [ctx.match[1], ctx.match[2], parseInt(ctx.match[3])];
    const isApprove = action === 'approve';

    // ዳታቤዝ ማዘመን
    db.prepare(`UPDATE payments SET status = ? WHERE id = ?`).run(isApprove ? 'APPROVED' : 'REJECTED', dbId);
    
    if (isApprove) {
        db.prepare("UPDATE members SET status = 'APPROVED' WHERE user_id = ?").run(targetUserId);
    }

    // ለአባሉ መልእክት መላክ
    const notifyMsg = isApprove 
        ? "🎉 እንኳን ደስ አለዎት! ክፍያዎ በአስተዳዳሪው ጸድቋል። በሁኔታ (Status) ገጽ ላይ ማየት ይችላሉ።" 
        : "⚠️ ይቅርታ፣ የላኩት የክፍያ መረጃ በአስተዳዳሪው ውድቅ ተደርጓል። እባክዎ መረጃውን በድጋሚ በትክክል ይላኩ።";

    try {
        await ctx.telegram.sendMessage(targetUserId, notifyMsg);
    } catch (e) {
        console.error("Notification failed", e);
    }

    await ctx.editMessageCaption(`${ctx.callbackQuery.message.caption}\n\n🏁 ውጤት፦ ${isApprove ? 'ጸድቋል ✅' : 'ተሰርዟል ❌'}`);
    await ctx.answerCbQuery(isApprove ? "ጸድቋል" : "ተሰርዟል");
});

// --- የገንዘብ ሪፖርት ማጠቃለያ (Stats) ---
bot.hears("📊 የክፍያ ሁኔታ", (ctx) => {
    const stats = db.prepare(`
        SELECT COUNT(*) as count, SUM(total_amount) as total 
        FROM payments WHERE user_id = ? AND status = 'APPROVED'
    `).get(ctx.from.id);

    const pending = db.prepare(`SELECT COUNT(*) as count FROM payments WHERE user_id = ? AND status = 'AWAIT_APPROVAL'`).get(ctx.from.id);

    let msg = `📋 **የእርስዎ የክፍያ ማጠቃለያ**\n\n`;
    msg += `✅ የጸደቁ ክፍያዎች፦ ${stats.count || 0}\n`;
    msg += `💰 ጠቅላላ የተከፈለ፦ **${stats.total || 0} ETB**\n`;
    if (pending.count > 0) {
        msg += `⏳ ማረጋገጫ የሚጠብቁ፦ ${pending.count} ክፍያዎች\n`;
    }

    ctx.replyWithMarkdown(msg);
});

// Admin Stats Command
bot.command('stats', (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    const allStats = db.prepare(`SELECT SUM(total_amount) as grandTotal FROM payments WHERE status = 'APPROVED'`).get();
    ctx.replyWithMarkdown(`💰 **ጠቅላላ የኢድር ካዝና፦ ${allStats.grandTotal || 0} ETB**`);
});

// Health check server
http.createServer((req, res) => { res.writeHead(200); res.end('Backend Active'); }).listen(process.env.PORT || 3000);

bot.launch().then(() => console.log('🚀 Edir Digital Pro Backend is running...'));
