/**
 * ╔══════════════════════════════════════════════════╗
 *  🎰 Lucky Wheel Bot — Node.js
 *  • Polling mode (works on Render free tier 24/7)
 *  • Auto-save JSON database every 60s
 *  • Daily spin limit: 1 free / 3 paid (Stars)
 *  • Referral system + Streaks + VIP + Leaderboard
 *  • Full admin panel via commands
 * ╚══════════════════════════════════════════════════╝
 */

"use strict";

const TelegramBot = require("node-telegram-bot-api");
const express    = require("express");
const fs         = require("fs");
const path       = require("path");

// ══════════════════════════════════════════════
//  ⚙️  CONFIG  (set via Render Environment Vars)
// ══════════════════════════════════════════════
const TOKEN           = process.env.API_TOKEN  || "PUT_YOUR_TOKEN_HERE";
const ADMIN_ID        = parseInt(process.env.ADMIN_ID || "0");
const FREE_DAILY      = 1;
const PAID_DAILY      = 3;
const DB_FILE         = path.join(__dirname, "users_data.json");
const BOT_NAME        = "Lucky Wheel 🎰";
const WHEEL_IMAGE     = "https://f.top4top.io/p_37196npsr1.png";
// Set to a Telegram file_id string to send a video on every spin, or leave null
const SPIN_VIDEO      = process.env.SPIN_VIDEO || null;
const PORT            = process.env.PORT || 3000;

// ══════════════════════════════════════════════
//  Database
// ══════════════════════════════════════════════
let db = {};

function loadDB() {
  if (!fs.existsSync(DB_FILE)) { db = {}; return; }
  try {
    db = JSON.parse(fs.readFileSync(DB_FILE, "utf8"));
    console.log(`✅ Loaded ${Object.keys(db).length} users`);
  } catch (e) {
    console.error("DB load error:", e.message);
    db = {};
  }
}

function saveDB() {
  try {
    fs.writeFileSync(DB_FILE, JSON.stringify(db, null, 2), "utf8");
  } catch (e) {
    console.error("DB save error:", e.message);
  }
}

// Auto-save every 60 seconds
setInterval(saveDB, 60_000);

// ══════════════════════════════════════════════
//  User helpers
// ══════════════════════════════════════════════
function getUser(uid) {
  const id = String(uid);
  if (!db[id]) {
    db[id] = {
      lang:        "en",
      name:        "",
      username:    "",
      balance:     0,
      totalWon:    0,
      totalRefs:   0,
      totalSpins:  0,
      bonusSpins:  0,
      spinDate:    null,
      spinsUsed:   0,
      dailyLimit:  FREE_DAILY,
      paidToday:   false,
      streak:      0,
      lastSpinDay: null,
      joinedAt:    today(),
      vip:         false,
      banned:      false,
    };
  }
  return db[id];
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

function yesterday() {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return d.toISOString().slice(0, 10);
}

function resetDaily(u) {
  const t = today();
  if (u.spinDate !== t) {
    u.spinDate   = t;
    u.spinsUsed  = 0;
    u.paidToday  = false;
    u.dailyLimit = u.vip ? PAID_DAILY : FREE_DAILY;
  }
}

function dailyLeft(u)  { return Math.max(0, u.dailyLimit - u.spinsUsed); }
function totalLeft(u)  { return dailyLeft(u) + u.bonusSpins; }

function timeToReset() {
  const now  = new Date();
  const next = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  const diff = next - now;
  const h    = Math.floor(diff / 3_600_000);
  const m    = Math.floor((diff % 3_600_000) / 60_000);
  return `${h}h ${m}m`;
}

// ══════════════════════════════════════════════
//  Prizes
// ══════════════════════════════════════════════
const PRIZES  = ["win30","win10","discount","free_spin","x2","lose"];
const WEIGHTS = [0.01,   1.0,   30.0,      15.0,       10.0, 43.99];

function weightedRandom() {
  const total = WEIGHTS.reduce((a, b) => a + b, 0);
  let r = Math.random() * total;
  for (let i = 0; i < PRIZES.length; i++) {
    r -= WEIGHTS[i];
    if (r <= 0) return PRIZES[i];
  }
  return PRIZES[PRIZES.length - 1];
}

const PRIZE_TEXT = {
  en: {
    win30:     "💸 You won *$30*\\! Amazing\\!",
    win10:     "💵 You won *$10*\\! Nice\\!",
    discount:  "🏷️ You got a *30% discount* voucher\\!",
    free_spin: "🎟️ You got a *free spin*\\! Use it wisely\\.",
    x2:        "🔄 *Double deposit* activated\\!",
    lose:      "💔 Better luck next time\\!",
  },
  ar: {
    win30:     "💸 ربحت *30$*\\! رائع\\!",
    win10:     "💵 ربحت *10$*\\! ممتاز\\!",
    discount:  "🏷️ حصلت على *خصم 30%*\\!",
    free_spin: "🎟️ حصلت على *دوران مجاني*\\!",
    x2:        "🔄 *إيداع مضاعف* مفعّل\\!",
    lose:      "💔 حظ أوفر المرة القادمة\\!",
  },
  ru: {
    win30:     "💸 Вы выиграли *30$*\\! Невероятно\\!",
    win10:     "💵 Вы выиграли *10$*\\! Отлично\\!",
    discount:  "🏷️ Скидка *30%* — ваша\\!",
    free_spin: "🎟️ Бесплатное вращение\\!",
    x2:        "🔄 *Двойной депозит* активирован\\!",
    lose:      "💔 Повезёт в следующий раз\\!",
  },
};

// ══════════════════════════════════════════════
//  Texts
// ══════════════════════════════════════════════
const T = {
  en: {
    welcome:      "🎰 *{bot}*\n\n👋 Welcome, *{name}*\\!\n\n💼 *Wallet:* `${balance}`\n🏆 *Total Won:* `${totalWon}`\n👥 *Referrals:* `{totalRefs}`\n🎡 *Daily Spins:* `{dailyLeft}` / `{dailyLimit}`\n🎁 *Bonus Spins:* `{bonus}`\n🔥 *Streak:* `{streak}` days\n\n📌 Free: *1 spin/day*  \\|  Pay 50 ⭐: *3 spins/day*\n📌 Every 5 referrals \\= *$1* reward",
    no_spins:     "⏳ *No spins left today\\!*\n\n🕐 Resets in *{time}*\n\nOr pay 50 ⭐ for 3 daily spins\\.",
    spinning:     "🌀 Spinning the wheel\\.\\.\\.",
    result_title: "🎉 *Wheel Result*",
    already_paid: "✅ Already upgraded today \\(3 spins\\)\\.",
    withdraw_req: "💳 Send your withdrawal address\n_\\(USDT / TRC\\-20 or account number\\)_:",
    withdraw_done:"✅ *Withdrawal request sent\\!*\nAdmin will process it soon\\.",
    low_balance:  "❌ Minimum withdrawal is *\\$1*\\.",
    lang_set:     "✅ Language set to *English*\\.",
    payment_ok:   "✅ *Payment confirmed\\!*\n\n🎡 You now have *3 spins* for today\\.",
    ref_msg:      "🔗 *Your referral link:*\n`{link}`\n\n👥 Each invite \\= 1 bonus spin\\!\n💰 Every 5 referrals \\= \\$1 reward",
    ref_notif:    "🎁 *Bonus spin\\!* Someone joined using your link\\.",
    refs5_notif:  "🎉 *\\$1 reward\\!* You hit 5 referrals\\!",
    streak_notif: "🔥 *{streak}\\-day streak\\!* Here's a bonus spin\\!",
    stats:        "📊 *Your Stats*\n\n👤 Name: *{name}*\n📅 Joined: `{joined}`\n🎡 Total Spins: `{totalSpins}`\n💰 Total Won: `${totalWon}`\n👥 Referrals: `{totalRefs}`\n🔥 Streak: `{streak}` days\n⭐ VIP: {vip}",
    leaderboard:  "🏆 *Top 10 Players*\n\n{entries}",
    banned:       "🚫 You have been banned from using this bot\\.",
    vip_granted:  "⭐ *VIP granted\\!* You now get 3 daily spins forever\\.",
    wallet:       "💼 *Your Wallet*\n\n💰 Balance: `${balance}`\n🏆 Total Won: `${totalWon}`",
    help:         "📖 *Commands*\n\n/start — Main menu\n/spin — Spin the wheel\n/stats — Your statistics\n/ref — Referral link\n/top — Leaderboard\n/wallet — Your balance\n/help — This message",
    spin_btn:     "🎡 Spin  [{spins} 🎟]",
    upgrade_btn:  "⭐ Upgrade Today  (50 Stars → 3 spins)",
    paid_btn:     "✅ Upgraded Today (3 spins)",
    withdraw_btn: "💰 Withdraw Earnings",
    ref_btn:      "🔗 Referral Link",
    stats_btn:    "📊 My Stats",
    lb_btn:       "🏆 Leaderboard",
    lang_btn:     "🌐 Language",
    back_btn:     "🔙 Back",
  },
  ar: {
    welcome:      "🎰 *{bot}*\n\n👋 أهلاً، *{name}*\\!\n\n💼 *المحفظة:* `{balance}$`\n🏆 *إجمالي الأرباح:* `{totalWon}$`\n👥 *الإحالات:* `{totalRefs}`\n🎡 *دورانات اليوم:* `{dailyLeft}` / `{dailyLimit}`\n🎁 *دورانات مكافأة:* `{bonus}`\n🔥 *السلسلة:* `{streak}` يوم\n\n📌 مجاناً: *دوران واحد* يومياً  \\|  50 ⭐: *3 دورانات*\n📌 كل 5 إحالات \\= مكافأة *1$*",
    no_spins:     "⏳ *انتهت دوراناتك اليوم\\!*\n\n🕐 يتجدد بعد *{time}*\n\nادفع 50 ⭐ للحصول على 3 دورانات\\.",
    spinning:     "🌀 العجلة تدور\\.\\.\\.",
    result_title: "🎉 *نتيجة العجلة*",
    already_paid: "✅ لديك ترقية اليوم بالفعل\\.",
    withdraw_req: "💳 أرسل عنوان السحب\n_\\(USDT أو رقم الحساب\\)_:",
    withdraw_done:"✅ *تم إرسال طلب السحب\\!*\nسيعالجه الأدمين قريباً\\.",
    low_balance:  "❌ الحد الأدنى للسحب هو *1$*\\.",
    lang_set:     "✅ تم اختيار اللغة العربية\\.",
    payment_ok:   "✅ *تم الدفع بنجاح\\!*\n\n🎡 لديك الآن *3 دورانات* اليوم\\.",
    ref_msg:      "🔗 *رابط إحالتك:*\n`{link}`\n\n👥 كل دعوة \\= دوران مكافأة\\!\n💰 كل 5 إحالات \\= 1$",
    ref_notif:    "🎁 *دوران مكافأة\\!* شخص انضم عبر رابطك\\.",
    refs5_notif:  "🎉 *مكافأة 1$\\!* أكملت 5 إحالات\\!",
    streak_notif: "🔥 *سلسلة {streak} أيام\\!* حصلت على دوران مكافأة\\!",
    stats:        "📊 *إحصائياتك*\n\n👤 الاسم: *{name}*\n📅 انضممت: `{joined}`\n🎡 إجمالي الدورانات: `{totalSpins}`\n💰 إجمالي الأرباح: `{totalWon}$`\n👥 الإحالات: `{totalRefs}`\n🔥 السلسلة: `{streak}` يوم\n⭐ VIP: {vip}",
    leaderboard:  "🏆 *أفضل 10 لاعبين*\n\n{entries}",
    banned:       "🚫 تم حظرك من استخدام البوت\\.",
    vip_granted:  "⭐ *تم منحك VIP\\!* الآن 3 دورانات يومياً دائماً\\.",
    wallet:       "💼 *محفظتك*\n\n💰 الرصيد: `{balance}$`\n🏆 إجمالي الأرباح: `{totalWon}$`",
    help:         "📖 *الأوامر*\n\n/start — القائمة الرئيسية\n/spin — تدوير العجلة\n/stats — إحصائياتك\n/ref — رابط الإحالة\n/top — المتصدرون\n/wallet — محفظتك\n/help — هذه الرسالة",
    spin_btn:     "🎡 تدوير  [{spins} 🎟]",
    upgrade_btn:  "⭐ ترقية اليوم  (50 نجمة → 3 دورانات)",
    paid_btn:     "✅ مُرقَّى اليوم (3 دورانات)",
    withdraw_btn: "💰 سحب الأرباح",
    ref_btn:      "🔗 رابط الإحالة",
    stats_btn:    "📊 إحصائياتي",
    lb_btn:       "🏆 المتصدرون",
    lang_btn:     "🌐 اللغة",
    back_btn:     "🔙 رجوع",
  },
  ru: {
    welcome:      "🎰 *{bot}*\n\n👋 Привет, *{name}*\\!\n\n💼 *Кошелек:* `${balance}`\n🏆 *Всего выиграно:* `${totalWon}`\n👥 *Рефералы:* `{totalRefs}`\n🎡 *Вращений сегодня:* `{dailyLeft}` / `{dailyLimit}`\n🎁 *Бонусных:* `{bonus}`\n🔥 *Серия:* `{streak}` дней\n\n📌 Бесплатно: *1/день*  \\|  50 ⭐: *3/день*\n📌 5 рефералов \\= *$1*",
    no_spins:     "⏳ *Вращения закончились\\!*\n\n🕐 Сброс через *{time}*\n\n50 ⭐ \\= 3 вращения\\.",
    spinning:     "🌀 Колесо крутится\\.\\.\\.",
    result_title: "🎉 *Результат*",
    already_paid: "✅ Уже улучшено сегодня\\.",
    withdraw_req: "💳 Отправьте адрес для вывода\n_\\(USDT / TRC\\-20\\)_:",
    withdraw_done:"✅ *Запрос отправлен\\!*\nАдмин обработает скоро\\.",
    low_balance:  "❌ Минимум *\\$1* для вывода\\.",
    lang_set:     "✅ Язык изменён на Русский\\.",
    payment_ok:   "✅ *Оплата прошла\\!*\n\n🎡 Теперь *3 вращения* на сегодня\\.",
    ref_msg:      "🔗 *Ваша реф\\. ссылка:*\n`{link}`\n\n👥 Каждый реферал \\= бонусное вращение\\!\n💰 5 рефералов \\= \\$1",
    ref_notif:    "🎁 *Бонусное вращение\\!* Кто\\-то пришёл по вашей ссылке\\.",
    refs5_notif:  "🎉 *\\+\\$1\\!* Вы набрали 5 рефералов\\!",
    streak_notif: "🔥 *Серия {streak} дней\\!* Бонусное вращение\\!",
    stats:        "📊 *Ваша статистика*\n\n👤 Имя: *{name}*\n📅 Дата: `{joined}`\n🎡 Вращений: `{totalSpins}`\n💰 Выиграно: `${totalWon}`\n👥 Рефералов: `{totalRefs}`\n🔥 Серия: `{streak}` дней\n⭐ VIP: {vip}",
    leaderboard:  "🏆 *Топ 10*\n\n{entries}",
    banned:       "🚫 Вы заблокированы\\.",
    vip_granted:  "⭐ *VIP выдан\\!* Теперь 3 вращения в день навсегда\\.",
    wallet:       "💼 *Кошелёк*\n\n💰 Баланс: `${balance}`\n🏆 Выиграно: `${totalWon}`",
    help:         "📖 *Команды*\n\n/start — Главное меню\n/spin — Крутить колесо\n/stats — Статистика\n/ref — Реф\\. ссылка\n/top — Лидеры\n/wallet — Кошелёк\n/help — Справка",
    spin_btn:     "🎡 Крутить  [{spins} 🎟]",
    upgrade_btn:  "⭐ Улучшить  (50 Звёзд → 3 вращения)",
    paid_btn:     "✅ Улучшено (3 вращения)",
    withdraw_btn: "💰 Вывод средств",
    ref_btn:      "🔗 Реф. ссылка",
    stats_btn:    "📊 Статистика",
    lb_btn:       "🏆 Лидеры",
    lang_btn:     "🌐 Язык",
    back_btn:     "🔙 Назад",
  },
};

function tx(lang, key, vars = {}) {
  const l = T[lang] || T.en;
  let s = l[key] || T.en[key] || key;
  for (const [k, v] of Object.entries(vars)) {
    s = s.replaceAll(`{${k}}`, v);
  }
  return s;
}

// ══════════════════════════════════════════════
//  Keyboards
// ══════════════════════════════════════════════
function kbMain(uid) {
  const u = getUser(uid);
  const lang = u.lang;
  resetDaily(u);
  const spins = totalLeft(u);

  const rows = [
    [{ text: tx(lang,"spin_btn",{spins}), callback_data: "spin" }],
    u.paidToday || u.vip
      ? [{ text: tx(lang,"paid_btn"),     callback_data: "paid_info" }]
      : [{ text: tx(lang,"upgrade_btn"),  callback_data: "buy_spin"  }],
  ];
  if (u.balance >= 1) {
    rows.push([{ text: tx(lang,"withdraw_btn"), callback_data: "withdraw" }]);
  }
  rows.push([
    { text: tx(lang,"ref_btn"),   callback_data: "ref"       },
    { text: tx(lang,"stats_btn"), callback_data: "stats"     },
  ]);
  rows.push([
    { text: tx(lang,"lb_btn"),   callback_data: "leaderboard" },
    { text: tx(lang,"lang_btn"), callback_data: "lang_menu"   },
  ]);
  return { inline_keyboard: rows };
}

function kbLang() {
  return { inline_keyboard: [
    [{ text: "🇺🇸 English",  callback_data: "setlang_en" }],
    [{ text: "🇸🇦 العربية", callback_data: "setlang_ar" }],
    [{ text: "🇷🇺 Русский",  callback_data: "setlang_ru" }],
  ]};
}

function kbBack(lang) {
  return { inline_keyboard: [[
    { text: tx(lang,"back_btn"), callback_data: "back" }
  ]]};
}

// ══════════════════════════════════════════════
//  Bot init
// ══════════════════════════════════════════════
const bot = new TelegramBot(TOKEN, { polling: true });

// FSM state per user
const fsm = {}; // uid -> { state, data }
function getState(uid) { return fsm[String(uid)] || {}; }
function setState(uid, state, data={}) { fsm[String(uid)] = { state, data }; }
function clearState(uid) { delete fsm[String(uid)]; }

// ══════════════════════════════════════════════
//  Send helpers
// ══════════════════════════════════════════════
async function sendHome(chatId, uid) {
  const u = getUser(uid);
  resetDaily(u);
  const lang = u.lang;
  const text = tx(lang, "welcome", {
    bot:       BOT_NAME,
    name:      u.name || "Player",
    balance:   u.balance.toFixed(2),
    totalWon:  u.totalWon.toFixed(2),
    totalRefs: u.totalRefs,
    dailyLeft: dailyLeft(u),
    dailyLimit:u.dailyLimit,
    bonus:     u.bonusSpins,
    streak:    u.streak,
  });
  try {
    await bot.sendPhoto(chatId, WHEEL_IMAGE, {
      caption:      text,
      parse_mode:   "MarkdownV2",
      reply_markup: kbMain(uid),
    });
  } catch {
    await bot.sendMessage(chatId, text, {
      parse_mode:   "MarkdownV2",
      reply_markup: kbMain(uid),
    });
  }
}

async function editOrSend(chatId, msgId, isPhoto, text, markup) {
  try {
    if (isPhoto) {
      await bot.editMessageCaption(text, {
        chat_id:      chatId,
        message_id:   msgId,
        parse_mode:   "MarkdownV2",
        reply_markup: markup,
      });
    } else {
      await bot.editMessageText(text, {
        chat_id:      chatId,
        message_id:   msgId,
        parse_mode:   "MarkdownV2",
        reply_markup: markup,
      });
    }
  } catch {
    await bot.sendMessage(chatId, text, {
      parse_mode:   "MarkdownV2",
      reply_markup: markup,
    });
  }
}

function isPhotoMsg(msg) {
  return !!(msg.photo || msg.video || msg.animation || msg.document);
}

async function sendSpinVideo(chatId) {
  if (!SPIN_VIDEO) return;
  try {
    await bot.sendVideo(chatId, SPIN_VIDEO);
  } catch (e) {
    console.warn("spin video error:", e.message);
  }
}

function buildLeaderboard(lang) {
  const medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"];
  const top = Object.values(db)
    .sort((a,b) => (b.totalWon||0) - (a.totalWon||0))
    .slice(0, 10);
  if (!top.length) return "—";
  return top.map((u,i) => {
    const name = (u.name||u.username||"Unknown").replace(/[_*[\]()~`>#+=|{}.!-]/g,"\\$&");
    return `${medals[i]} ${name} — \`$${(u.totalWon||0).toFixed(2)}\``;
  }).join("\n");
}

// ══════════════════════════════════════════════
//  /start
// ══════════════════════════════════════════════
bot.onText(/\/start(.*)/, async (msg, match) => {
  const uid    = msg.from.id;
  const chatId = msg.chat.id;
  const isNew  = !db[String(uid)];
  const u      = getUser(uid);
  u.name     = msg.from.first_name + (msg.from.last_name ? " "+msg.from.last_name : "");
  u.username = msg.from.username || "";
  clearState(uid);

  // Handle referral
  const payload = (match[1]||"").trim();
  if (isNew && payload) {
    let refId = null;
    if (/^\d+$/.test(payload)) {
      refId = payload;
    } else {
      try {
        const dec = Buffer.from(payload, "base64").toString("utf8");
        if (/^\d+$/.test(dec)) refId = dec;
      } catch {}
    }
    if (refId && db[refId] && refId !== String(uid)) {
      const ru = db[refId];
      ru.totalRefs  = (ru.totalRefs  || 0) + 1;
      ru.bonusSpins = (ru.bonusSpins || 0) + 1;
      try {
        await bot.sendMessage(refId, tx(ru.lang,"ref_notif"), { parse_mode:"MarkdownV2" });
      } catch {}
      if (ru.totalRefs % 5 === 0) {
        ru.balance  = (ru.balance  || 0) + 1;
        ru.totalWon = (ru.totalWon || 0) + 1;
        try {
          await bot.sendMessage(refId, tx(ru.lang,"refs5_notif"), { parse_mode:"MarkdownV2" });
        } catch {}
      }
    }
  }

  saveDB();
  await sendHome(chatId, uid);
});

// ══════════════════════════════════════════════
//  Spin logic (shared between /spin cmd & button)
// ══════════════════════════════════════════════
async function doSpin(chatId, uid, msgId, isPhoto) {
  const u    = getUser(uid);
  const lang = u.lang;
  resetDaily(u);

  if (totalLeft(u) < 1) {
    await bot.answerCallbackQuery(msgId.cbId || "", {
      text: tx(lang,"no_spins",{time:timeToReset()}).replace(/\\/g,""),
      show_alert: true,
    }).catch(()=>{});
    if (!msgId.cbId) {
      await bot.sendMessage(chatId, tx(lang,"no_spins",{time:timeToReset()}), { parse_mode:"MarkdownV2" });
    }
    return;
  }

  // Deduct
  if (dailyLeft(u) > 0) u.spinsUsed++;
  else u.bonusSpins--;
  u.totalSpins = (u.totalSpins||0) + 1;

  // Streak
  const t = today(), yd = yesterday();
  if      (u.lastSpinDay === yd) u.streak = (u.streak||0) + 1;
  else if (u.lastSpinDay !== t)  u.streak = 1;
  u.lastSpinDay = t;
  const streakBonus = u.streak > 0 && u.streak % 7 === 0;

  // Show spinning
  await sendSpinVideo(chatId);
  const spinText = tx(lang,"spinning");
  if (isPhoto) {
    await bot.editMessageCaption(spinText, {
      chat_id: chatId, message_id: msgId.id, parse_mode: "MarkdownV2"
    }).catch(async () => {
      await bot.sendMessage(chatId, spinText, { parse_mode:"MarkdownV2" });
    });
  } else {
    await bot.editMessageText(spinText, {
      chat_id: chatId, message_id: msgId.id, parse_mode: "MarkdownV2"
    }).catch(async () => {
      await bot.sendMessage(chatId, spinText, { parse_mode:"MarkdownV2" });
    });
  }

  await new Promise(r => setTimeout(r, 2000));

  // Result
  const result = weightedRandom();
  let won = 0;
  if      (result === "win30")     { won = 30; }
  else if (result === "win10")     { won = 10; }
  else if (result === "free_spin") { u.bonusSpins++; }
  if (won > 0) { u.balance += won; u.totalWon += won; }
  if (streakBonus) u.bonusSpins++;

  const prizeText = PRIZE_TEXT[lang]?.[result] || PRIZE_TEXT.en[result];
  const resultMsg = `${tx(lang,"result_title")}\n\n${prizeText}` +
    (won > 0 ? `\n\n💼 *Balance: \\$${u.balance.toFixed(2)}*` : "");

  await bot.sendMessage(chatId, resultMsg, { parse_mode:"MarkdownV2" });
  if (streakBonus) {
    await bot.sendMessage(chatId, tx(lang,"streak_notif",{streak:u.streak}), { parse_mode:"MarkdownV2" });
  }
  saveDB();
  await sendHome(chatId, uid);
}

// ══════════════════════════════════════════════
//  Commands
// ══════════════════════════════════════════════
bot.onText(/\/spin$/, async (msg) => {
  const uid  = msg.from.id;
  const u    = getUser(uid);
  if (u.banned) return;
  resetDaily(u);
  await doSpin(msg.chat.id, uid, { id: msg.message_id }, isPhotoMsg(msg));
});

bot.onText(/\/stats$/, async (msg) => {
  const uid  = msg.from.id;
  const u    = getUser(uid);
  const lang = u.lang;
  const vip  = u.vip
    ? ({en:"Yes ⭐",ar:"نعم ⭐",ru:"Да ⭐"}[lang])
    : ({en:"No",ar:"لا",ru:"Нет"}[lang]);
  const name = (u.name||"—").replace(/[_*[\]()~`>#+=|{}.!-]/g,"\\$&");
  await bot.sendMessage(msg.chat.id,
    tx(lang,"stats",{ name, joined:u.joinedAt, totalSpins:u.totalSpins||0,
      totalWon:u.totalWon.toFixed(2), totalRefs:u.totalRefs, streak:u.streak||0, vip }),
    { parse_mode:"MarkdownV2", reply_markup: kbBack(lang) }
  );
});

bot.onText(/\/ref$/, async (msg) => {
  const uid  = msg.from.id;
  const u    = getUser(uid);
  const link = `https://t.me/${(await bot.getMe()).username}?start=${Buffer.from(String(uid)).toString("base64")}`;
  await bot.sendMessage(msg.chat.id,
    tx(u.lang,"ref_msg",{ link }),
    { parse_mode:"MarkdownV2" }
  );
});

bot.onText(/\/top$/, async (msg) => {
  const uid  = msg.from.id;
  const lang = getUser(uid).lang;
  await bot.sendMessage(msg.chat.id,
    tx(lang,"leaderboard",{ entries: buildLeaderboard(lang) }),
    { parse_mode:"MarkdownV2", reply_markup: kbBack(lang) }
  );
});

bot.onText(/\/wallet$/, async (msg) => {
  const uid  = msg.from.id;
  const u    = getUser(uid);
  await bot.sendMessage(msg.chat.id,
    tx(u.lang,"wallet",{ balance:u.balance.toFixed(2), totalWon:u.totalWon.toFixed(2) }),
    { parse_mode:"MarkdownV2" }
  );
});

bot.onText(/\/help$/, async (msg) => {
  const lang = getUser(msg.from.id).lang;
  await bot.sendMessage(msg.chat.id, tx(lang,"help"), { parse_mode:"MarkdownV2" });
});

// ── Admin commands ──────────────────────────
bot.onText(/\/admin$/, async (msg) => {
  if (msg.from.id !== ADMIN_ID) return;
  const total   = Object.keys(db).length;
  const active  = Object.values(db).filter(u => u.lastSpinDay === today()).length;
  const balSum  = Object.values(db).reduce((s,u) => s+(u.balance||0), 0);
  const wonSum  = Object.values(db).reduce((s,u) => s+(u.totalWon||0), 0);
  const vips    = Object.values(db).filter(u => u.vip).length;
  const banned  = Object.values(db).filter(u => u.banned).length;
  await bot.sendMessage(msg.chat.id,
    `🛠 *Admin Panel*\n\n` +
    `👥 Total users: \`${total}\`\n` +
    `🔥 Active today: \`${active}\`\n` +
    `💰 Total balances: \`$${balSum.toFixed(2)}\`\n` +
    `🏆 Total won: \`$${wonSum.toFixed(2)}\`\n` +
    `⭐ VIP: \`${vips}\`\n` +
    `🚫 Banned: \`${banned}\`\n\n` +
    `*Commands:*\n` +
    `/vip \\<id\\> — Grant VIP\n` +
    `/ban \\<id\\> — Ban user\n` +
    `/unban \\<id\\> — Unban user\n` +
    `/addbal \\<id\\> \\<amount\\> — Add balance\n` +
    `/userinfo \\<id\\> — User details\n` +
    `/broadcast — Send to all users\n` +
    `/savedb — Save DB now`,
    { parse_mode:"MarkdownV2" }
  );
});

bot.onText(/\/vip (\d+)/, async (msg, m) => {
  if (msg.from.id !== ADMIN_ID) return;
  const u = getUser(m[1]);
  u.vip = true; u.dailyLimit = PAID_DAILY;
  saveDB();
  await bot.sendMessage(msg.chat.id, `⭐ VIP granted to \`${m[1]}\``, { parse_mode:"MarkdownV2" });
  try { await bot.sendMessage(m[1], tx(u.lang,"vip_granted"), { parse_mode:"MarkdownV2" }); } catch {}
});

bot.onText(/\/ban (\d+)/, async (msg, m) => {
  if (msg.from.id !== ADMIN_ID) return;
  getUser(m[1]).banned = true; saveDB();
  await bot.sendMessage(msg.chat.id, `🚫 Banned \`${m[1]}\``, { parse_mode:"MarkdownV2" });
});

bot.onText(/\/unban (\d+)/, async (msg, m) => {
  if (msg.from.id !== ADMIN_ID) return;
  getUser(m[1]).banned = false; saveDB();
  await bot.sendMessage(msg.chat.id, `✅ Unbanned \`${m[1]}\``, { parse_mode:"MarkdownV2" });
});

bot.onText(/\/addbal (\d+) ([\d.]+)/, async (msg, m) => {
  if (msg.from.id !== ADMIN_ID) return;
  const u = getUser(m[1]);
  const amt = parseFloat(m[2]);
  u.balance  += amt;
  u.totalWon += amt;
  saveDB();
  await bot.sendMessage(msg.chat.id,
    `✅ Added \`$${amt}\` to \`${m[1]}\` → balance: \`$${u.balance.toFixed(2)}\``,
    { parse_mode:"MarkdownV2" }
  );
});

bot.onText(/\/userinfo (\d+)/, async (msg, m) => {
  if (msg.from.id !== ADMIN_ID) return;
  const u = db[m[1]];
  if (!u) { await bot.sendMessage(msg.chat.id, "❌ Not found"); return; }
  const name = (u.name||"—").replace(/[_*[\]()~`>#+=|{}.!-]/g,"\\$&");
  await bot.sendMessage(msg.chat.id,
    `👤 *${name}* \\(@${u.username||"—"}\\)\n` +
    `🆔 \`${m[1]}\`\n` +
    `💰 Balance: \`$${(u.balance||0).toFixed(2)}\`\n` +
    `🏆 Won: \`$${(u.totalWon||0).toFixed(2)}\`\n` +
    `👥 Refs: \`${u.totalRefs||0}\`\n` +
    `🎡 Spins: \`${u.totalSpins||0}\`\n` +
    `🎁 Bonus: \`${u.bonusSpins||0}\`\n` +
    `🔥 Streak: \`${u.streak||0}\`\n` +
    `⭐ VIP: \`${u.vip}\`\n` +
    `🚫 Banned: \`${u.banned}\`\n` +
    `📅 Joined: \`${u.joinedAt||"—"}\``,
    { parse_mode:"MarkdownV2" }
  );
});

bot.onText(/\/savedb$/, async (msg) => {
  if (msg.from.id !== ADMIN_ID) return;
  saveDB();
  await bot.sendMessage(msg.chat.id, `✅ DB saved \\(${Object.keys(db).length} users\\)`, { parse_mode:"MarkdownV2" });
});

// Broadcast FSM
bot.onText(/\/broadcast$/, async (msg) => {
  if (msg.from.id !== ADMIN_ID) return;
  setState(msg.from.id, "broadcast");
  await bot.sendMessage(msg.chat.id, "📢 Send the message to broadcast to all users:");
});

// ══════════════════════════════════════════════
//  Callback queries (buttons)
// ══════════════════════════════════════════════
bot.on("callback_query", async (cb) => {
  const uid    = cb.from.id;
  const chatId = cb.message.chat.id;
  const msgId  = cb.message.message_id;
  const data   = cb.data;
  const u      = getUser(uid);
  const lang   = u.lang;
  const photo  = isPhotoMsg(cb.message);

  if (u.banned) {
    await bot.answerCallbackQuery(cb.id, { text: "🚫 Banned", show_alert:true });
    return;
  }

  // ─ spin ─────────────────────────────────────
  if (data === "spin") {
    resetDaily(u);
    if (totalLeft(u) < 1) {
      await bot.answerCallbackQuery(cb.id, {
        text: tx(lang,"no_spins",{time:timeToReset()}).replace(/\\/g,""),
        show_alert: true
      });
      return;
    }
    await bot.answerCallbackQuery(cb.id);
    await doSpin(chatId, uid, { id: msgId }, photo);
    return;
  }

  // ─ back ─────────────────────────────────────
  if (data === "back") {
    resetDaily(u);
    const text = tx(lang,"welcome",{
      bot:BOT_NAME, name:u.name||"Player",
      balance:u.balance.toFixed(2), totalWon:u.totalWon.toFixed(2),
      totalRefs:u.totalRefs, dailyLeft:dailyLeft(u),
      dailyLimit:u.dailyLimit, bonus:u.bonusSpins, streak:u.streak||0,
    });
    await editOrSend(chatId, msgId, photo, text, kbMain(uid));
    await bot.answerCallbackQuery(cb.id);
    return;
  }

  // ─ stats ────────────────────────────────────
  if (data === "stats") {
    const vip = u.vip
      ? ({en:"Yes ⭐",ar:"نعم ⭐",ru:"Да ⭐"}[lang])
      : ({en:"No",ar:"لا",ru:"Нет"}[lang]);
    const name = (u.name||"—").replace(/[_*[\]()~`>#+=|{}.!-]/g,"\\$&");
    const text = tx(lang,"stats",{
      name, joined:u.joinedAt, totalSpins:u.totalSpins||0,
      totalWon:u.totalWon.toFixed(2), totalRefs:u.totalRefs,
      streak:u.streak||0, vip,
    });
    await editOrSend(chatId, msgId, photo, text, kbBack(lang));
    await bot.answerCallbackQuery(cb.id);
    return;
  }

  // ─ leaderboard ──────────────────────────────
  if (data === "leaderboard") {
    const text = tx(lang,"leaderboard",{ entries:buildLeaderboard(lang) });
    await editOrSend(chatId, msgId, photo, text, kbBack(lang));
    await bot.answerCallbackQuery(cb.id);
    return;
  }

  // ─ ref ──────────────────────────────────────
  if (data === "ref") {
    const me   = await bot.getMe();
    const link = `https://t.me/${me.username}?start=${Buffer.from(String(uid)).toString("base64")}`;
    await bot.sendMessage(chatId, tx(lang,"ref_msg",{link}), { parse_mode:"MarkdownV2" });
    await bot.answerCallbackQuery(cb.id);
    return;
  }

  // ─ lang_menu ────────────────────────────────
  if (data === "lang_menu") {
    const text = "🌍 Choose your language / اختر لغتك / Выберите язык";
    try {
      if (photo) await bot.editMessageCaption(text, { chat_id:chatId, message_id:msgId, reply_markup:kbLang() });
      else        await bot.editMessageText   (text, { chat_id:chatId, message_id:msgId, reply_markup:kbLang() });
    } catch {
      await bot.sendMessage(chatId, text, { reply_markup:kbLang() });
    }
    await bot.answerCallbackQuery(cb.id);
    return;
  }

  // ─ setlang ──────────────────────────────────
  if (data.startsWith("setlang_")) {
    const newLang = data.split("_")[1];
    if (T[newLang]) {
      u.lang = newLang;
      resetDaily(u);
    }
    await bot.answerCallbackQuery(cb.id, { text: tx(u.lang,"lang_set").replace(/\\/g,"") });
    const text = tx(u.lang,"welcome",{
      bot:BOT_NAME, name:u.name||"Player",
      balance:u.balance.toFixed(2), totalWon:u.totalWon.toFixed(2),
      totalRefs:u.totalRefs, dailyLeft:dailyLeft(u),
      dailyLimit:u.dailyLimit, bonus:u.bonusSpins, streak:u.streak||0,
    });
    await editOrSend(chatId, msgId, photo, text, kbMain(uid));
    return;
  }

  // ─ withdraw ─────────────────────────────────
  if (data === "withdraw") {
    if (u.balance < 1) {
      await bot.answerCallbackQuery(cb.id, { text: tx(lang,"low_balance").replace(/\\/g,""), show_alert:true });
      return;
    }
    setState(uid, "withdraw");
    await bot.sendMessage(chatId, tx(lang,"withdraw_req"), { parse_mode:"MarkdownV2" });
    await bot.answerCallbackQuery(cb.id);
    return;
  }

  // ─ buy_spin (Stars invoice) ──────────────────
  if (data === "buy_spin") {
    resetDaily(u);
    if (u.paidToday || u.vip) {
      await bot.answerCallbackQuery(cb.id, { text: tx(lang,"already_paid").replace(/\\/g,""), show_alert:true });
      return;
    }
    const titles = { en:"⭐ Daily Upgrade — 3 Spins", ar:"⭐ ترقية اليوم — 3 دورانات", ru:"⭐ Улучшение — 3 вращения" };
    const descs  = {
      en:"Pay 50 Stars for 3 daily spins instead of 1.",
      ar:"ادفع 50 نجمة للحصول على 3 دورانات يومياً.",
      ru:"50 Звёзд = 3 вращения в день.",
    };
    await bot.sendInvoice(chatId, titles[lang]||titles.en, descs[lang]||descs.en,
      "upgrade_daily_spins", "", "XTR",
      [{ label:"3 Daily Spins", amount:50 }]
    );
    await bot.answerCallbackQuery(cb.id);
    return;
  }

  // ─ paid_info ────────────────────────────────
  if (data === "paid_info") {
    await bot.answerCallbackQuery(cb.id, { text: tx(lang,"already_paid").replace(/\\/g,""), show_alert:true });
    return;
  }

  await bot.answerCallbackQuery(cb.id);
});

// ══════════════════════════════════════════════
//  Payments
// ══════════════════════════════════════════════
bot.on("pre_checkout_query", async (pcq) => {
  await bot.answerPreCheckoutQuery(pcq.id, true);
});

bot.on("successful_payment", async (msg) => {
  const uid = msg.from.id;
  const u   = getUser(uid);
  resetDaily(u);
  u.dailyLimit = PAID_DAILY;
  u.paidToday  = true;
  saveDB();
  await bot.sendMessage(msg.chat.id, tx(u.lang,"payment_ok"), { parse_mode:"MarkdownV2" });
  await sendHome(msg.chat.id, uid);
});

// ══════════════════════════════════════════════
//  Text messages (FSM)
// ══════════════════════════════════════════════
bot.on("message", async (msg) => {
  if (!msg.text || msg.text.startsWith("/")) return;
  const uid   = msg.from.id;
  const state = getState(uid);
  const u     = getUser(uid);
  const lang  = u.lang;

  // ─ withdraw address ─────────────────────────
  if (state.state === "withdraw") {
    clearState(uid);
    const amount = u.balance.toFixed(2);
    const admin  =
      `🚨 *New Withdrawal*\n\n` +
      `👤 ${(u.name||"—").replace(/[_*[\]()~`>#+=|{}.!-]/g,"\\$&")}\n` +
      `🆔 \`${uid}\`\n` +
      `💰 \`$${amount}\`\n` +
      `👥 Refs: \`${u.totalRefs}\`\n` +
      `📍 Address:\n\`${msg.text.replace(/[_*[\]()~`>#+=|{}.!-]/g,"\\$&")}\``;
    try {
      await bot.sendMessage(ADMIN_ID, admin, { parse_mode:"MarkdownV2" });
      u.balance = 0;
      saveDB();
      await bot.sendMessage(msg.chat.id, tx(lang,"withdraw_done"), { parse_mode:"MarkdownV2" });
    } catch {
      await bot.sendMessage(msg.chat.id, "⚠️ Error sending request\\. Try again later\\.", { parse_mode:"MarkdownV2" });
    }
    await sendHome(msg.chat.id, uid);
    return;
  }

  // ─ broadcast ────────────────────────────────
  if (state.state === "broadcast" && uid === ADMIN_ID) {
    clearState(uid);
    let count = 0;
    for (const id of Object.keys(db)) {
      try {
        await bot.sendMessage(id, msg.text, { parse_mode:"MarkdownV2" });
        count++;
        await new Promise(r => setTimeout(r, 50));
      } catch {}
    }
    await bot.sendMessage(msg.chat.id,
      `✅ Broadcast sent to *${count}* users\\.`,
      { parse_mode:"MarkdownV2" }
    );
    return;
  }
});

// ══════════════════════════════════════════════
//  Express keep-alive server (Render needs a port)
// ══════════════════════════════════════════════
const app = express();
app.get("/", (_, res) => res.json({
  status: "ok",
  bot:    BOT_NAME,
  users:  Object.keys(db).length,
  uptime: Math.floor(process.uptime()) + "s",
}));
app.listen(PORT, () => console.log(`🌐 Keep-alive server on port ${PORT}`));

// ══════════════════════════════════════════════
//  Startup
// ══════════════════════════════════════════════
loadDB();
console.log(`🤖 ${BOT_NAME} started in polling mode!`);
