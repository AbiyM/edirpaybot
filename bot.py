/**
 * Edir Digital Pro v3.6 - Backend Bot
 * * This bot handles member registration, payment processing from the Mini App,
 * automated tier upgrades, admin reporting, and database backups.
 */

require('dotenv').config();
const { Telegraf, session, Markup } = require('telegraf');
const Database = require('better-sqlite3');
const http = require('http');
const fs = require('fs');

// --- 1. CONFIGURATION & ENVIRONMENT VARIABLES ---
// BOT_TOKEN: The unique token from @BotFather
const BOT_TOKEN = process.env.BOT_TOKEN;

// ADMIN_IDS: A list of Telegram User IDs allowed to access the Admin Panel
const ADMIN_IDS = process.env.ADMIN_IDS ? process.env.ADMIN_IDS.split(',').map(id => parseInt(id.trim())) : [];

// MINI_APP_URL: The URL of your hosted index.html (e.g., on Render or Vercel)
const MINI_APP_URL = process.env.MINI_APP_URL;

// TEST_GROUP_ID: The ID of the Telegram group where tier-up notifications are sent
const TEST_GROUP_ID = process.env.TEST_GROUP_ID ? parseInt(process.env.TEST_GROUP_ID) : -1003740305702;

// DB_FILE: The filename for the SQLite database
const DB_FILE = 'edir_pro_v3.db';

if (!BOT_TOKEN) {
    console.error("❌ BOT_TOKEN is missing! Please check your .env file or Render settings.");
    process.exit(1);
}

// --- 2. DATABASE INITIALIZATION ---
const db = new Database(DB_FILE);

// Initialize tables:
// 'members' stores user identity and their current rank (Tier).
// 'payments' stores all transaction history and status (AWAIT_APPROVAL, APPROVED, REJECTED).
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
bot.use(session()); // Enables session storage for temporary data handling

// Helper function to verify if a user is an authorized Admin
const isAdmin = (id) => ADMIN_IDS.includes(id);

// --- 3. TIER & RANKING LOGIC ---
/**
 * Calculates and updates a user's tier based on successfully APPROVED payments.
 * Thresholds:
 * - 0-4 payments: መሠረታዊ (Basic)
 * - 5-11 payments: ፕሮ (Pro)
 * - 12+ payments: ልዩ (Elite)
 */
function updateMemberTier(userId) {
    const stats = db.prepare(`SELECT COUNT(*) as count FROM payments WHERE user_id = ? AND status = 'APPROVED'`).get(userId);
    let newTier = 'መሠረታዊ';
    if (stats.count >= 12) newTier = 'ልዩ (Elite)';
    else if (stats.count >= 5) newTier = 'ፕሮ (Pro)';
    
    db.prepare("UPDATE members SET tier = ? WHERE user_id = ?").run(newTier, userId);
    return newTier;
}

// --- 4. KEYBOARDS (MENU SYSTEMS) ---

// Main menu for regular members
const getMemberKeyboard = (id) => {
    const btns = [[Markup.button.webApp("📱 ሚኒ አፑን ተጠቀም", MINI_APP_URL)]];
    if (isAdmin(id)) btns.push(["⚙️ የአስተዳዳሪ ሁነታ (Admin Mode)"]);
    btns.push(["📊 ሁኔታዬን እይ", "❓ እርዳታ"]);
    return Markup.keyboard(btns).resize();
};

// Menu for administrators
const getAdminKeyboard = () => {
    return Markup.keyboard([
        ["📑 የሚጠባበቁ", "📈 ዝርዝር ሪፖርት"],
        ["📊 አጠቃላይ ማጠቃለያ", "💾 ዳታቤዝ ባክአፕ"],
        ["👤 ወደ አባልነት ተመለስ (User Mode)"]
    ]).resize();
};

// --- 5. BACKUP LOGIC ---
/**
 * Sends the entire SQLite database file to an Admin's private Telegram chat.
 * This ensures data recovery if the Render server resets.
 */
async function sendBackup(targetId) {
    try {
        if (fs.existsSync(DB_FILE)) {
            await bot.telegram.sendDocument(targetId, { source: DB_FILE }, {
                caption: `💾 **Edir Database Backup**\n📅 Date: ${new Date().toLocaleString()}\n⚠️ Save this file locally for safety.`
            });
        }
    } catch (err) {
        console.error("Backup failed:", err);
    }
}

// Automatically send a backup to the first listed Admin every 12 hours
setInterval(() => {
    if (ADMIN_IDS.length > 0) {
        sendBackup(ADMIN_IDS[0]);
    }
}, 12 * 60 * 60 * 1000);

// --- 6. ADMIN HANDLERS (REPORTING & BACKUP) ---

// Manual backup trigger
bot.hears("💾 ዳታቤዝ ባክአፕ", async (ctx) => {
    if (!isAdmin(ctx.from.id)) return;
    await ctx.reply("⏳ Generating backup file...");
    await sendBackup(ctx.from.id);
});

// Quick Summary: Shows total members and total approved money
bot.hears("📊 አጠቃላይ ማጠቃለያ", (ctx) => {
    if (!isAdmin(ctx.from.id)) return;
    const stats = db.prepare(`SELECT COUNT(*) as count, SUM(total_amount) as total FROM payments WHERE status = 'APPROVED'`).get();
    const members = db.prepare(`SELECT COUNT(*) as count FROM members`).get();
    
    let msg = `📊 **አጠቃላይ የገንዘብ ማጠቃለያ**\n\n`;
    msg += `👥 ጠቅላላ አባላት: ${members.count}\n`;
    msg += `✅ የጸደቁ ክፍያዎች: ${stats.count}\n`;
    msg += `💰 ጠቅላላ የተሰበሰበ: **${stats.total || 0} ብር**`;
    ctx.replyWithMarkdown(msg);
});

// Detailed List: Shows the last 100 approved payments
bot.hears("📈 ዝርዝር ሪፖርት", (ctx) => {
    if (!isAdmin(ctx.from.id)) return;
    const records = db.prepare(`SELECT * FROM payments WHERE status = 'APPROVED' ORDER BY id DESC LIMIT 100`).all();
    if (records.length === 0) return ctx.reply("ምንም የጸደቀ ክፍያ የለም።");
    
    let msg = `📑 **የጸደቁ ክፍያዎች ዝርዝር (ያለፉት ${records.length} ክፍያዎች)**\n\n`;
    records.forEach((r, index) => {
        msg += `${index + 1}. @${r.username} - ${r.total_amount} ብር (${r.purpose})\n`;
    });
    
    // Split message if it's too long for a single Telegram message
    if (msg.length > 4000) {
        ctx.replyWithMarkdown(msg.substring(0, 4000) + "...");
    } else {
        ctx.replyWithMarkdown(msg);
    }
});

// --- 7. GENERAL BOT COMMANDS ---

// Start Command: Register user and show main menu
bot.start((ctx) => {
    db.prepare('INSERT OR IGNORE INTO members (user_id, username, full_name) VALUES (?, ?, ?)').run(
        ctx.from.id, 
        ctx.from.username || 'N/A', 
        ctx.from.first_name
    );
    ctx.replyWithMarkdown(`እንኳን ወደ **እሁድን በፍቅር** ዲጂታል መተግበሪያ በሰላም መጡ! 👋`, getMemberKeyboard(ctx.from.id));
});

// Switch to Admin keyboard
bot.hears("⚙️ የአስተዳዳሪ ሁነታ (Admin Mode)", (ctx) => {
    if (!isAdmin(ctx.from.id)) return ctx.reply("ፈቃድ የለዎትም።");
    ctx.reply("🛠 አሁን በ**አስተዳዳሪ ሁነታ** ላይ ነዎት።", getAdminKeyboard());
});

// Switch back to Member keyboard
bot.hears("👤 ወደ አባልነት ተመለስ (User Mode)", (ctx) => {
    ctx.reply("👤 ወደ **አባልነት ሁነታ** ተመልሰዋል።", getMemberKeyboard(ctx.from.id));
});

// --- 8. PAYMENT PROCESSING ---

// Listener for data sent from the Mini App
bot.on('web_app_data', async (ctx) => {
    try {
        const data = JSON.parse(ctx.webAppData.data.json());
        if (data.type === 'payment_report') {
            const time = new Date().toLocaleString();
            ctx.session.pendingPayment = { ...data, timestamp: time };

            // If user pays manually, ask for receipt photo
            if (data.gateway === 'manual') {
                await ctx.reply(`✅ የ${data.totalAmount} ብር ክፍያ ተመዝግቧል። 📷 አሁን የደረሰኝ ፎቶ ይላኩ።`);
            } else {
                // Digital payments are logged directly
                const res = db.prepare(`INSERT INTO payments (user_id, username, gateway, purpose, total_amount, timestamp) VALUES (?, ?, ?, ?, ?, ?)`)
                    .run(ctx.from.id, ctx.from.username || 'N/A', data.gateway, data.purpose, data.totalAmount, time);
                notifyAdmins(ctx, data, res.lastInsertRowid, null, time);
                await ctx.reply(`🚀 ክፍያው ተመዝግቧል። ለአስተዳዳሪ እንዲረጋገጥ ተልኳል።`);
            }
        }
    } catch (e) {
        console.error("Payload error:", e);
    }
});

// Listener for receipt photos/files
bot.on(['photo', 'document'], async (ctx) => {
    const pending = ctx.session?.pendingPayment;
    if (!pending) return; // Ignore if user sends a photo without filling the form first

    const fileId = ctx.message.photo ? ctx.message.photo.pop().file_id : ctx.message.document.file_id;
    
    const res = db.prepare(`INSERT INTO payments (user_id, username, gateway, purpose, total_amount, file_id, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)`)
        .run(ctx.from.id, ctx.from.username || 'N/A', pending.gateway, pending.purpose, pending.totalAmount, fileId, pending.timestamp);
    
    notifyAdmins(ctx, pending, res.lastInsertRowid, fileId, pending.timestamp);
    ctx.session.pendingPayment = null; // Clear the temporary session
    await ctx.reply(`📩 ደረሰኝዎ ተልኳል። ሲጸድቅ መልእክት ይደርስዎታል። እናመሰግናለን!`);
});

/**
 * Notifies all admins about a new payment with an inline Approve/Reject menu.
 */
async function notifyAdmins(ctx, data, dbId, fileId, time) {
    const adminCaption = `🚨 **አዲስ የክፍያ ሪፖርት**\n👤 @${ctx.from.username}\n💰 ${data.totalAmount} ብር\n🎯 ${data.purpose}`;
    const kb = Markup.inlineKeyboard([
        [Markup.button.callback('✅ አጽድቅ', `p_app_${dbId}_${ctx.from.id}`)], 
        [Markup.button.callback('❌ ውድቅ አድርግ', `p_rej_${dbId}_${ctx.from.id}`)]
    ]);

    ADMIN_IDS.forEach(async id => {
        try {
            if (fileId) {
                await bot.telegram.sendPhoto(id, fileId, { caption: adminCaption, ...kb });
            } else {
                await bot.telegram.sendMessage(id, adminCaption, kb);
            }
        } catch (e) {
            console.error("Admin notification failed for:", id);
        }
    });
}

// --- 9. APPROVAL WORKFLOW ---

// Listener for Approve/Reject button clicks
bot.action(/^(p_app|p_rej)_(\d+)_(\d+)$/, async (ctx) => {
    const [action, dbId, targetUid] = [ctx.match[1], ctx.match[2], parseInt(ctx.match[3])];
    const isApprove = action === 'p_app';

    // Update database status
    db.prepare(`UPDATE payments SET status = ? WHERE id = ?`).run(isApprove ? 'APPROVED' : 'REJECTED', dbId);
    
    if (isApprove) {
        // Check for tier upgrade and notify group if necessary
        const tier = updateMemberTier(targetUid);
        if (TEST_GROUP_ID && tier !== 'መሠረታዊ') {
            bot.telegram.sendMessage(TEST_GROUP_ID, `🌟 **የደረጃ ዕድገት!**\nአባል @${(await ctx.telegram.getChatMember(targetUid, targetUid)).user.username} አሁን የ**${tier}** ደረጃ ደርሰዋል። 🎉`);
        }
    }

    // Notify the user about the decision
    const userMsg = isApprove ? `🎉 ክፍያዎ ተረጋግጧል! እናመሰግናለን::` : `❌ ክፍያዎ ውድቅ ተደርጓል:: እባክዎ መረጃውን በድጋሚ ይላኩ::`;
    try { await bot.telegram.sendMessage(targetUid, userMsg); } catch(e) {}

    // Update the admin message to show result
    ctx.editMessageText(`${ctx.callbackQuery.message.text || ctx.callbackQuery.message.caption}\n\n🏁 ውጤት: ${isApprove ? 'ጸድቋል ✅' : 'ውድቅ ተደርጓል ❌'}`);
    ctx.answerCbQuery("ተጠናቀቀ"); 
});

// --- 10. SERVER & HEALTH CHECK ---
// Keeps the bot alive on Render and prevents idle sleeping
http.createServer((req, res) => {
    res.writeHead(200);
    res.end('Bot is Active');
}).listen(process.env.PORT || 3000);

bot.launch().then(() => console.log("🚀 Edir Digital Pro Bot is online!"));
