"""
🎰 Lucky Wheel Bot
==================
- English default language
- Single spin animation video (sent once per spin)
- Wheel image: https://f.top4top.io/p_37196npsr1.png
- Auto JSON database (saves every 60s)
- Daily spin limit: 1 free / 3 paid (50 Stars)
- Referral system, Streaks, VIP, Leaderboard
- Full Admin Panel with broadcast, stats, user management
"""

import asyncio
import random
import logging
import base64
import json
import os
from datetime import datetime, date, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.deep_linking import create_start_link
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import LabeledPrice, PreCheckoutQuery

# ═══════════════════════════════════════════════
#  ⚙️  CONFIG — Edit these values
# ═══════════════════════════════════════════════
API_TOKEN        = "8652849537:AAGvOLd3_W7TcgY7SnU1b2rpF0c1APhtLWM"
ADMIN_ID         = 8453835458
FREE_DAILY_SPINS = 1
PAID_DAILY_SPINS = 3
DB_FILE          = "users_data.json"
BOT_NAME         = "Lucky Wheel 🎰"

# ── Spin video ──
# Put your Telegram file_id here, or a local path like "spin.mp4"
# This video is sent ONCE every time the wheel spins.
# Leave as None to disable.
SPIN_VIDEO: str | None = None
# Example: SPIN_VIDEO = "BAACAgIAAxkBAAI...file_id..."
# Example: SPIN_VIDEO = "spin.mp4"

# ── Wheel image (shown in /start & /play) ──
WHEEL_IMAGE = "https://f.top4top.io/p_37196npsr1.png"

# ═══════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(message)s",
)
logger = logging.getLogger(__name__)

bot = Bot(token=API_TOKEN)
dp  = Dispatcher()

users_db: dict = {}

# ═══════════════════════════════════════════════
#  FSM States
# ═══════════════════════════════════════════════
class WithdrawState(StatesGroup):
    waiting_address = State()

class BroadcastState(StatesGroup):
    waiting_msg = State()

class AdminAddBalance(StatesGroup):
    waiting = State()

# ═══════════════════════════════════════════════
#  Database helpers
# ═══════════════════════════════════════════════
def load_db():
    global users_db
    if not os.path.exists(DB_FILE):
        users_db = {}
        return
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        users_db = {int(k): v for k, v in raw.items()}
        logger.info(f"✅ Loaded {len(users_db)} users from DB.")
    except Exception as e:
        logger.error(f"DB load error: {e}")
        users_db = {}

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(users_db, f, ensure_ascii=False, default=str, indent=2)
    except Exception as e:
        logger.error(f"DB save error: {e}")

async def auto_save_loop():
    while True:
        await asyncio.sleep(60)
        save_db()
        logger.debug("💾 Auto-saved DB.")

# ═══════════════════════════════════════════════
#  User helpers
# ═══════════════════════════════════════════════
def get_user(uid: int) -> dict:
    if uid not in users_db:
        users_db[uid] = {
            "lang":          "en",
            "name":          "",
            "username":      "",
            "balance":       0.0,
            "total_won":     0.0,
            "total_refs":    0,
            "total_spins":   0,
            "bonus_spins":   0,
            "spin_date":     None,
            "spins_used":    0,
            "daily_limit":   FREE_DAILY_SPINS,
            "paid_today":    False,
            "streak":        0,
            "last_spin_day": None,
            "joined_at":     str(date.today()),
            "vip":           False,
            "banned":        False,
        }
    return users_db[uid]

def sync_user(uid: int, tg_user) -> dict:
    d = get_user(uid)
    d["name"]     = tg_user.full_name or ""
    d["username"] = tg_user.username  or ""
    return d

def reset_daily(d: dict):
    today = str(date.today())
    if d.get("spin_date") != today:
        d["spin_date"]   = today
        d["spins_used"]  = 0
        d["paid_today"]  = False
        d["daily_limit"] = PAID_DAILY_SPINS if d.get("vip") else FREE_DAILY_SPINS

def daily_left(d: dict) -> int:
    return max(0, d["daily_limit"] - d["spins_used"])

def total_spins_left(d: dict) -> int:
    return daily_left(d) + d["bonus_spins"]

def time_to_reset() -> str:
    now  = datetime.now()
    next = datetime(now.year, now.month, now.day) + timedelta(days=1)
    diff = next - now
    h, m = diff.seconds // 3600, (diff.seconds % 3600) // 60
    return f"{h}h {m}m"

# ═══════════════════════════════════════════════
#  Prizes
# ═══════════════════════════════════════════════
PRIZES  = ["win30", "win10", "discount", "free_spin", "x2", "lose"]
WEIGHTS = [0.01,    1.0,     30.0,       15.0,        10.0,  43.99]

PRIZE_TEXT = {
    "en": {
        "win30":     "💸 You won *$30*! Amazing!",
        "win10":     "💵 You won *$10*! Nice!",
        "discount":  "🏷️ You got a *30% discount* voucher!",
        "free_spin": "🎟️ You got a *free spin*! Use it wisely.",
        "x2":        "🔄 *Double deposit* activated!",
        "lose":      "💔 Better luck next time!",
    },
    "ar": {
        "win30":     "💸 ربحت *30$*! رائع!",
        "win10":     "💵 ربحت *10$*! ممتاز!",
        "discount":  "🏷️ حصلت على *خصم 30%*!",
        "free_spin": "🎟️ حصلت على *دوران مجاني*!",
        "x2":        "🔄 *إيداع مضاعف* مفعّل!",
        "lose":      "💔 حظ أوفر المرة القادمة!",
    },
    "ru": {
        "win30":     "💸 Вы выиграли *30$*! Невероятно!",
        "win10":     "💵 Вы выиграли *10$*! Отлично!",
        "discount":  "🏷️ Скидка *30%* — ваша!",
        "free_spin": "🎟️ Бесплатное вращение!",
        "x2":        "🔄 *Двойной депозит* активирован!",
        "lose":      "💔 Повезёт в следующий раз!",
    },
}

# ═══════════════════════════════════════════════
#  Texts
# ═══════════════════════════════════════════════
T = {
    "en": {
        "welcome": (
            "🎰 *{bot}*\n\n"
            "👋 Welcome, *{name}*!\n\n"
            "💼 *Wallet:* `${balance}`\n"
            "🏆 *Total Won:* `${total_won}`\n"
            "👥 *Referrals:* `{refs}`\n"
            "🎡 *Daily Spins:* `{daily_left}` / `{daily_limit}`\n"
            "🎁 *Bonus Spins:* `{bonus}`\n"
            "🔥 *Streak:* `{streak}` days\n\n"
            "📌 Free: *1 spin/day*  |  Pay 50 ⭐: *3 spins/day*\n"
            "📌 Every 5 referrals = *$1* reward"
        ),
        "no_spins":     "⏳ *No spins left today!*\n\n🕐 Resets in *{time}*\n\nOr pay 50 ⭐ for 3 daily spins.",
        "spinning":     "🌀 Spinning the wheel...",
        "result_title": "🎉 *Wheel Result*",
        "already_paid": "✅ Already upgraded today (3 spins).",
        "withdraw_req": "💳 Send your withdrawal address\n_(USDT / TRC-20 or account number)_:",
        "withdraw_done":"✅ *Withdrawal request sent!*\nAdmin will process it soon.",
        "low_balance":  "❌ Minimum withdrawal is *$1*.",
        "lang_set":     "✅ Language set to *English*.",
        "payment_ok":   "✅ *Payment confirmed!*\n\n🎡 You now have *3 spins* for today.",
        "ref_msg":      "🔗 *Your referral link:*\n`{link}`\n\n👥 Each invite = 1 bonus spin for you!\n💰 Every 5 referrals = $1 reward",
        "ref_notif":    "🎁 *Bonus spin!* Someone joined using your link.",
        "refs5_notif":  "🎉 *$1 reward!* You hit 5 referrals!",
        "streak_notif": "🔥 *{streak}-day streak!* Here's a bonus spin!",
        "stats": (
            "📊 *Your Stats*\n\n"
            "👤 Name: *{name}*\n"
            "📅 Joined: `{joined}`\n"
            "🎡 Total Spins: `{total_spins}`\n"
            "💰 Total Won: `${total_won}`\n"
            "👥 Referrals: `{refs}`\n"
            "🔥 Best Streak: `{streak}` days\n"
            "⭐ VIP: {vip}"
        ),
        "leaderboard":  "🏆 *Top 10 Players*\n\n{entries}",
        "banned":       "🚫 You have been banned from using this bot.",
        "vip_granted":  "⭐ *VIP granted!* You now get 3 daily spins forever.",
        "already_paid_btn": "✅ Upgraded Today (3 spins)",
        "spin_btn":     "🎡 Spin  [{spins} 🎟]",
        "upgrade_btn":  "⭐ Upgrade Today  (50 Stars → 3 spins)",
        "withdraw_btn": "💰 Withdraw Earnings",
        "ref_btn":      "🔗 Referral Link",
        "stats_btn":    "📊 My Stats",
        "lb_btn":       "🏆 Leaderboard",
        "lang_btn":     "🌐 Language",
        "back_btn":     "🔙 Back",
        "help": (
            "📖 *Commands*\n\n"
            "/start — Main menu\n"
            "/spin  — Spin the wheel\n"
            "/stats — Your statistics\n"
            "/ref   — Referral link\n"
            "/top   — Leaderboard\n"
            "/wallet— Your balance\n"
            "/help  — This message"
        ),
        "wallet": "💼 *Your Wallet*\n\n💰 Balance: `${balance}`\n🏆 Total Won: `${total_won}`",
    },
    "ar": {
        "welcome": (
            "🎰 *{bot}*\n\n"
            "👋 أهلاً، *{name}*!\n\n"
            "💼 *المحفظة:* `{balance}$`\n"
            "🏆 *إجمالي الأرباح:* `{total_won}$`\n"
            "👥 *الإحالات:* `{refs}`\n"
            "🎡 *دورانات اليوم:* `{daily_left}` / `{daily_limit}`\n"
            "🎁 *دورانات مكافأة:* `{bonus}`\n"
            "🔥 *السلسلة:* `{streak}` يوم\n\n"
            "📌 مجاناً: *دوران واحد* يومياً  |  50 ⭐: *3 دورانات*\n"
            "📌 كل 5 إحالات = مكافأة *1$*"
        ),
        "no_spins":     "⏳ *انتهت دوراناتك اليوم!*\n\n🕐 يتجدد بعد *{time}*\n\nادفع 50 ⭐ للحصول على 3 دورانات.",
        "spinning":     "🌀 العجلة تدور...",
        "result_title": "🎉 *نتيجة العجلة*",
        "already_paid": "✅ لديك ترقية اليوم بالفعل.",
        "withdraw_req": "💳 أرسل عنوان السحب\n_(USDT أو رقم الحساب)_:",
        "withdraw_done":"✅ *تم إرسال طلب السحب!*\nسيعالجه الأدمين قريباً.",
        "low_balance":  "❌ الحد الأدنى للسحب هو *1$*.",
        "lang_set":     "✅ تم اختيار اللغة العربية.",
        "payment_ok":   "✅ *تم الدفع بنجاح!*\n\n🎡 لديك الآن *3 دورانات* اليوم.",
        "ref_msg":      "🔗 *رابط إحالتك:*\n`{link}`\n\n👥 كل دعوة = دوران مكافأة لك!\n💰 كل 5 إحالات = 1$",
        "ref_notif":    "🎁 *دوران مكافأة!* شخص انضم عبر رابطك.",
        "refs5_notif":  "🎉 *مكافأة 1$!* أكملت 5 إحالات!",
        "streak_notif": "🔥 *سلسلة {streak} أيام!* حصلت على دوران مكافأة!",
        "stats": (
            "📊 *إحصائياتك*\n\n"
            "👤 الاسم: *{name}*\n"
            "📅 انضممت: `{joined}`\n"
            "🎡 إجمالي الدورانات: `{total_spins}`\n"
            "💰 إجمالي الأرباح: `{total_won}$`\n"
            "👥 الإحالات: `{refs}`\n"
            "🔥 السلسلة: `{streak}` يوم\n"
            "⭐ VIP: {vip}"
        ),
        "leaderboard":  "🏆 *أفضل 10 لاعبين*\n\n{entries}",
        "banned":       "🚫 تم حظرك من استخدام البوت.",
        "vip_granted":  "⭐ *تم منحك VIP!* الآن 3 دورانات يومياً دائماً.",
        "already_paid_btn": "✅ مُرقَّى اليوم (3 دورانات)",
        "spin_btn":     "🎡 تدوير  [{spins} 🎟]",
        "upgrade_btn":  "⭐ ترقية اليوم  (50 نجمة → 3 دورانات)",
        "withdraw_btn": "💰 سحب الأرباح",
        "ref_btn":      "🔗 رابط الإحالة",
        "stats_btn":    "📊 إحصائياتي",
        "lb_btn":       "🏆 المتصدرون",
        "lang_btn":     "🌐 اللغة",
        "back_btn":     "🔙 رجوع",
        "help": (
            "📖 *الأوامر*\n\n"
            "/start — القائمة الرئيسية\n"
            "/spin  — تدوير العجلة\n"
            "/stats — إحصائياتك\n"
            "/ref   — رابط الإحالة\n"
            "/top   — المتصدرون\n"
            "/wallet— محفظتك\n"
            "/help  — هذه الرسالة"
        ),
        "wallet": "💼 *محفظتك*\n\n💰 الرصيد: `{balance}$`\n🏆 إجمالي الأرباح: `{total_won}$`",
    },
    "ru": {
        "welcome": (
            "🎰 *{bot}*\n\n"
            "👋 Привет, *{name}*!\n\n"
            "💼 *Кошелек:* `${balance}`\n"
            "🏆 *Всего выиграно:* `${total_won}`\n"
            "👥 *Рефералы:* `{refs}`\n"
            "🎡 *Вращений сегодня:* `{daily_left}` / `{daily_limit}`\n"
            "🎁 *Бонусных:* `{bonus}`\n"
            "🔥 *Серия:* `{streak}` дней\n\n"
            "📌 Бесплатно: *1/день*  |  50 ⭐: *3/день*\n"
            "📌 5 рефералов = *$1*"
        ),
        "no_spins":     "⏳ *Вращения закончились!*\n\n🕐 Сброс через *{time}*\n\n50 ⭐ = 3 вращения.",
        "spinning":     "🌀 Колесо крутится...",
        "result_title": "🎉 *Результат*",
        "already_paid": "✅ Уже улучшено сегодня.",
        "withdraw_req": "💳 Отправьте адрес для вывода\n_(USDT / TRC-20)_:",
        "withdraw_done":"✅ *Запрос отправлен!*\nАдмин обработает скоро.",
        "low_balance":  "❌ Минимум *$1* для вывода.",
        "lang_set":     "✅ Язык изменён на Русский.",
        "payment_ok":   "✅ *Оплата прошла!*\n\n🎡 Теперь *3 вращения* на сегодня.",
        "ref_msg":      "🔗 *Ваша реф. ссылка:*\n`{link}`\n\n👥 Каждый реферал = бонусное вращение!\n💰 5 рефералов = $1",
        "ref_notif":    "🎁 *Бонусное вращение!* Кто-то пришёл по вашей ссылке.",
        "refs5_notif":  "🎉 *+$1!* Вы набрали 5 рефералов!",
        "streak_notif": "🔥 *Серия {streak} дней!* Бонусное вращение!",
        "stats": (
            "📊 *Ваша статистика*\n\n"
            "👤 Имя: *{name}*\n"
            "📅 Дата: `{joined}`\n"
            "🎡 Вращений: `{total_spins}`\n"
            "💰 Выиграно: `${total_won}`\n"
            "👥 Рефералов: `{refs}`\n"
            "🔥 Серия: `{streak}` дней\n"
            "⭐ VIP: {vip}"
        ),
        "leaderboard":  "🏆 *Топ 10*\n\n{entries}",
        "banned":       "🚫 Вы заблокированы.",
        "vip_granted":  "⭐ *VIP выдан!* Теперь 3 вращения в день навсегда.",
        "already_paid_btn": "✅ Улучшено (3 вращения)",
        "spin_btn":     "🎡 Крутить  [{spins} 🎟]",
        "upgrade_btn":  "⭐ Улучшить  (50 Звёзд → 3 вращения)",
        "withdraw_btn": "💰 Вывод средств",
        "ref_btn":      "🔗 Реф. ссылка",
        "stats_btn":    "📊 Статистика",
        "lb_btn":       "🏆 Лидеры",
        "lang_btn":     "🌐 Язык",
        "back_btn":     "🔙 Назад",
        "help": (
            "📖 *Команды*\n\n"
            "/start — Главное меню\n"
            "/spin  — Крутить колесо\n"
            "/stats — Статистика\n"
            "/ref   — Реф. ссылка\n"
            "/top   — Лидеры\n"
            "/wallet— Кошелёк\n"
            "/help  — Эта справка"
        ),
        "wallet": "💼 *Кошелёк*\n\n💰 Баланс: `${balance}`\n🏆 Выиграно: `${total_won}`",
    },
}

def t(lang: str, key: str, **kw) -> str:
    text = T.get(lang, T["en"]).get(key, T["en"].get(key, key))
    return text.format(**kw) if kw else text

# ═══════════════════════════════════════════════
#  Keyboards
# ═══════════════════════════════════════════════
def kb_main(uid: int) -> types.InlineKeyboardMarkup:
    d    = get_user(uid)
    lang = d["lang"]
    reset_daily(d)
    spins = total_spins_left(d)
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(
        text=t(lang, "spin_btn", spins=spins), callback_data="spin"
    ))
    if d["paid_today"] or d["vip"]:
        b.row(types.InlineKeyboardButton(
            text=t(lang, "already_paid_btn"), callback_data="paid_info"
        ))
    else:
        b.row(types.InlineKeyboardButton(
            text=t(lang, "upgrade_btn"), callback_data="buy_spin"
        ))
    if d["balance"] >= 1:
        b.row(types.InlineKeyboardButton(
            text=t(lang, "withdraw_btn"), callback_data="withdraw"
        ))
    b.row(
        types.InlineKeyboardButton(text=t(lang, "ref_btn"),   callback_data="ref"),
        types.InlineKeyboardButton(text=t(lang, "stats_btn"), callback_data="stats"),
    )
    b.row(
        types.InlineKeyboardButton(text=t(lang, "lb_btn"),   callback_data="leaderboard"),
        types.InlineKeyboardButton(text=t(lang, "lang_btn"), callback_data="lang_menu"),
    )
    return b.as_markup()

def kb_lang() -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.add(types.InlineKeyboardButton(text="🇺🇸 English",  callback_data="setlang_en"))
    b.add(types.InlineKeyboardButton(text="🇸🇦 العربية", callback_data="setlang_ar"))
    b.add(types.InlineKeyboardButton(text="🇷🇺 Русский",  callback_data="setlang_ru"))
    return b.as_markup()

def kb_back(lang: str) -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.add(types.InlineKeyboardButton(text=t(lang, "back_btn"), callback_data="back"))
    return b.as_markup()

# ═══════════════════════════════════════════════
#  Smart edit — handles both photo and text msgs
# ═══════════════════════════════════════════════
async def smart_edit(cb: types.CallbackQuery, text: str, markup=None, parse_mode="Markdown"):
    """
    Telegram raises an error when calling edit_text on a photo message.
    This helper detects the message type and uses the correct method:
      - Photo / video message → edit_caption
      - Text message          → edit_text
    Falls back to sending a new message if both fail.
    """
    msg    = cb.message
    kwargs = {"reply_markup": markup}
    if parse_mode:
        kwargs["parse_mode"] = parse_mode
    try:
        if msg.photo or msg.video or msg.animation or msg.document:
            await msg.edit_caption(caption=text, **kwargs)
        else:
            await msg.edit_text(text, **kwargs)
    except Exception:
        try:
            await msg.delete()
        except Exception:
            pass
        await msg.answer(text, **kwargs)

# ═══════════════════════════════════════════════
#  Send spin video helper
# ═══════════════════════════════════════════════
async def send_spin_video(chat_id: int, caption: str = ""):
    if not SPIN_VIDEO:
        return
    try:
        if SPIN_VIDEO.startswith("BA") or len(SPIN_VIDEO) > 60:
            await bot.send_video(chat_id, video=SPIN_VIDEO,
                                 caption=caption, parse_mode="Markdown")
        elif os.path.exists(SPIN_VIDEO):
            from aiogram.types import FSInputFile
            await bot.send_video(chat_id, video=FSInputFile(SPIN_VIDEO),
                                 caption=caption, parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"send_spin_video: {e}")

# ═══════════════════════════════════════════════
#  Send dashboard
# ═══════════════════════════════════════════════
async def send_home(msg: types.Message, uid: int, with_image: bool = False):
    d    = get_user(uid)
    lang = d["lang"]
    reset_daily(d)
    text = t(lang, "welcome",
        bot        = BOT_NAME,
        name       = d["name"] or "Player",
        balance    = round(d["balance"], 2),
        total_won  = round(d["total_won"], 2),
        refs       = d["total_refs"],
        daily_left = daily_left(d),
        daily_limit= d["daily_limit"],
        bonus      = d["bonus_spins"],
        streak     = d["streak"],
    )
    markup = kb_main(uid)
    if with_image:
        try:
            await msg.answer_photo(
                photo=WHEEL_IMAGE,
                caption=text,
                reply_markup=markup,
                parse_mode="Markdown",
            )
            return
        except Exception:
            pass
    await msg.answer(text, reply_markup=markup, parse_mode="Markdown")

# ═══════════════════════════════════════════════
#  Leaderboard helper
# ═══════════════════════════════════════════════
MEDALS = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]

def build_lb(lang: str) -> str:
    top = sorted(users_db.values(), key=lambda x: x.get("total_won", 0), reverse=True)[:10]
    if not top:
        return "—"
    lines = []
    for i, u in enumerate(top):
        name = u.get("name") or u.get("username") or "Unknown"
        lines.append(f"{MEDALS[i]} *{name}* — `${round(u.get('total_won',0),2)}`")
    return "\n".join(lines)

# ═══════════════════════════════════════════════
#  /start
# ═══════════════════════════════════════════════
@dp.message(Command("start"))
async def cmd_start(msg: types.Message):
    uid    = msg.from_user.id
    args   = msg.text.split()
    is_new = uid not in users_db
    d      = sync_user(uid, msg.from_user)

    if d.get("banned"):
        await msg.answer(t(d["lang"], "banned"))
        return

    # Handle referral
    if is_new and len(args) > 1:
        payload = args[1]
        ref_id  = None
        if payload.isdigit():
            ref_id = int(payload)
        else:
            try:
                dec = base64.urlsafe_b64decode(payload + "==").decode()
                if dec.isdigit():
                    ref_id = int(dec)
            except Exception:
                pass

        if ref_id and ref_id in users_db and ref_id != uid:
            rd = get_user(ref_id)
            rd["total_refs"]  += 1
            rd["bonus_spins"] += 1
            rl = rd["lang"]
            try:
                await bot.send_message(ref_id, t(rl, "ref_notif"), parse_mode="Markdown")
            except Exception:
                pass
            if rd["total_refs"] % 5 == 0:
                rd["balance"]   += 1.0
                rd["total_won"] += 1.0
                try:
                    await bot.send_message(ref_id, t(rl, "refs5_notif"), parse_mode="Markdown")
                except Exception:
                    pass

    save_db()
    await send_home(msg, uid, with_image=True)

# ═══════════════════════════════════════════════
#  /spin command
# ═══════════════════════════════════════════════
@dp.message(Command("spin"))
async def cmd_spin(msg: types.Message):
    uid = msg.from_user.id
    d   = sync_user(uid, msg.from_user)
    if d.get("banned"):
        return
    reset_daily(d)
    lang = d["lang"]
    if total_spins_left(d) < 1:
        await msg.answer(t(lang, "no_spins", time=time_to_reset()), parse_mode="Markdown")
        return
    await _do_spin(msg, uid)

# ═══════════════════════════════════════════════
#  /stats  /ref  /top  /wallet  /help
# ═══════════════════════════════════════════════
@dp.message(Command("stats"))
async def cmd_stats(msg: types.Message):
    uid  = msg.from_user.id
    d    = sync_user(uid, msg.from_user)
    lang = d["lang"]
    vip_y = {"en":"Yes ⭐","ar":"نعم ⭐","ru":"Да ⭐"}
    vip_n = {"en":"No","ar":"لا","ru":"Нет"}
    text = t(lang, "stats",
        name        = d["name"] or "—",
        joined      = d["joined_at"],
        total_spins = d["total_spins"],
        total_won   = round(d["total_won"],2),
        refs        = d["total_refs"],
        streak      = d["streak"],
        vip         = vip_y[lang] if d["vip"] else vip_n[lang],
    )
    await msg.answer(text, reply_markup=kb_back(lang), parse_mode="Markdown")

@dp.message(Command("ref"))
async def cmd_ref(msg: types.Message):
    uid  = msg.from_user.id
    d    = sync_user(uid, msg.from_user)
    lang = d["lang"]
    link = await create_start_link(bot, str(uid), encode=True)
    await msg.answer(t(lang, "ref_msg", link=link), parse_mode="Markdown")

@dp.message(Command("top"))
async def cmd_top(msg: types.Message):
    uid  = msg.from_user.id
    d    = get_user(uid)
    lang = d["lang"]
    await msg.answer(
        t(lang, "leaderboard", entries=build_lb(lang)),
        reply_markup=kb_back(lang),
        parse_mode="Markdown"
    )

@dp.message(Command("wallet"))
async def cmd_wallet(msg: types.Message):
    uid  = msg.from_user.id
    d    = get_user(uid)
    lang = d["lang"]
    await msg.answer(
        t(lang, "wallet", balance=round(d["balance"],2), total_won=round(d["total_won"],2)),
        parse_mode="Markdown"
    )

@dp.message(Command("help"))
async def cmd_help(msg: types.Message):
    uid  = msg.from_user.id
    lang = get_user(uid)["lang"]
    await msg.answer(t(lang, "help"), parse_mode="Markdown")

# ═══════════════════════════════════════════════
#  Callbacks — main menu
# ═══════════════════════════════════════════════
@dp.callback_query(F.data == "back")
async def cb_back(cb: types.CallbackQuery):
    uid  = cb.from_user.id
    d    = get_user(uid)
    lang = d["lang"]
    reset_daily(d)
    text = t(lang, "welcome",
        bot        = BOT_NAME,
        name       = d["name"] or "Player",
        balance    = round(d["balance"],2),
        total_won  = round(d["total_won"],2),
        refs       = d["total_refs"],
        daily_left = daily_left(d),
        daily_limit= d["daily_limit"],
        bonus      = d["bonus_spins"],
        streak     = d["streak"],
    )
    await smart_edit(cb, text, markup=kb_main(uid))
    await cb.answer()

@dp.callback_query(F.data == "spin")
async def cb_spin(cb: types.CallbackQuery):
    uid = cb.from_user.id
    d   = get_user(uid)
    if d.get("banned"):
        await cb.answer("🚫", show_alert=True)
        return
    reset_daily(d)
    lang = d["lang"]
    if total_spins_left(d) < 1:
        await cb.answer(t(lang, "no_spins", time=time_to_reset()), show_alert=True)
        return
    await cb.answer()
    await _do_spin(cb.message, uid, edit=True)

async def _do_spin(msg: types.Message, uid: int, edit: bool = False):
    d    = get_user(uid)
    lang = d["lang"]

    # Deduct spin
    if daily_left(d) > 0:
        d["spins_used"] += 1
    else:
        d["bonus_spins"] -= 1
    d["total_spins"] += 1

    # Streak logic
    today     = str(date.today())
    yesterday = str(date.today() - timedelta(days=1))
    last      = d.get("last_spin_day")
    if last == yesterday:
        d["streak"] += 1
    elif last != today:
        d["streak"] = 1
    d["last_spin_day"] = today
    streak_bonus = d["streak"] > 0 and d["streak"] % 7 == 0

    # Send spin video (the ONE video)
    await send_spin_video(msg.chat.id)

    # Spinning indicator
    spin_text = t(lang, "spinning")
    if edit:
        try:
            if msg.photo or msg.video or msg.animation or msg.document:
                await msg.edit_caption(caption=spin_text)
            else:
                await msg.edit_text(spin_text)
        except Exception:
            await msg.answer(spin_text)
    else:
        await msg.answer(spin_text)
    await asyncio.sleep(2)

    # Spin result
    result = random.choices(PRIZES, weights=WEIGHTS, k=1)[0]
    won    = 0.0
    if result == "win30":
        won = 30.0
    elif result == "win10":
        won = 10.0
    elif result == "free_spin":
        d["bonus_spins"] += 1

    if won > 0:
        d["balance"]   += won
        d["total_won"] += won

    result_msg = f"{t(lang,'result_title')}\n\n{PRIZE_TEXT[lang][result]}"
    if won > 0:
        result_msg += f"\n\n💼 *Balance: ${round(d['balance'],2)}*"

    await msg.answer(result_msg, parse_mode="Markdown")

    if streak_bonus:
        d["bonus_spins"] += 1
        await msg.answer(t(lang, "streak_notif", streak=d["streak"]), parse_mode="Markdown")

    save_db()
    await send_home(msg, uid)

# ═══════════════════════════════════════════════
#  Callbacks — misc
# ═══════════════════════════════════════════════
@dp.callback_query(F.data == "ref")
async def cb_ref(cb: types.CallbackQuery):
    uid  = cb.from_user.id
    lang = get_user(uid)["lang"]
    link = await create_start_link(bot, str(uid), encode=True)
    await cb.message.answer(t(lang, "ref_msg", link=link), parse_mode="Markdown")
    await cb.answer()

@dp.callback_query(F.data == "stats")
async def cb_stats(cb: types.CallbackQuery):
    uid  = cb.from_user.id
    d    = get_user(uid)
    lang = d["lang"]
    vip_y = {"en":"Yes ⭐","ar":"نعم ⭐","ru":"Да ⭐"}
    vip_n = {"en":"No","ar":"لا","ru":"Нет"}
    text = t(lang, "stats",
        name        = d["name"] or "—",
        joined      = d["joined_at"],
        total_spins = d["total_spins"],
        total_won   = round(d["total_won"],2),
        refs        = d["total_refs"],
        streak      = d["streak"],
        vip         = vip_y[lang] if d["vip"] else vip_n[lang],
    )
    await smart_edit(cb, text, markup=kb_back(lang))
    await cb.answer()

@dp.callback_query(F.data == "leaderboard")
async def cb_lb(cb: types.CallbackQuery):
    uid  = cb.from_user.id
    lang = get_user(uid)["lang"]
    await smart_edit(
        cb,
        t(lang, "leaderboard", entries=build_lb(lang)),
        markup=kb_back(lang),
    )
    await cb.answer()

@dp.callback_query(F.data == "paid_info")
async def cb_paid_info(cb: types.CallbackQuery):
    lang = get_user(cb.from_user.id)["lang"]
    await cb.answer(t(lang, "already_paid"), show_alert=True)

@dp.callback_query(F.data == "lang_menu")
async def cb_lang_menu(cb: types.CallbackQuery):
    await smart_edit(
        cb,
        "🌍 Choose your language / اختر لغتك / Выберите язык",
        markup=kb_lang(),
        parse_mode=None,
    )
    await cb.answer()

@dp.callback_query(F.data.startswith("setlang_"))
async def cb_setlang(cb: types.CallbackQuery):
    lang = cb.data.split("_")[1]
    if lang not in T:
        await cb.answer("❌")
        return
    uid          = cb.from_user.id
    d            = get_user(uid)
    d["lang"]    = lang
    reset_daily(d)
    await cb.answer(t(lang, "lang_set"))
    text = t(lang, "welcome",
        bot        = BOT_NAME,
        name       = d["name"] or "Player",
        balance    = round(d["balance"],2),
        total_won  = round(d["total_won"],2),
        refs       = d["total_refs"],
        daily_left = daily_left(d),
        daily_limit= d["daily_limit"],
        bonus      = d["bonus_spins"],
        streak     = d["streak"],
    )
    await smart_edit(cb, text, markup=kb_main(uid))

# ═══════════════════════════════════════════════
#  Withdraw
# ═══════════════════════════════════════════════
@dp.callback_query(F.data == "withdraw")
async def cb_withdraw(cb: types.CallbackQuery, state: FSMContext):
    uid  = cb.from_user.id
    d    = get_user(uid)
    lang = d["lang"]
    if d["balance"] < 1:
        await cb.answer(t(lang, "low_balance"), show_alert=True)
        return
    await cb.message.answer(t(lang, "withdraw_req"), parse_mode="Markdown")
    await state.set_state(WithdrawState.waiting_address)
    await cb.answer()

@dp.message(WithdrawState.waiting_address)
async def fsm_withdraw(msg: types.Message, state: FSMContext):
    uid     = msg.from_user.id
    d       = get_user(uid)
    lang    = d["lang"]
    addr    = msg.text
    amount  = round(d["balance"], 2)
    admin_text = (
        f"🚨 *New Withdrawal Request*\n\n"
        f"👤 *{msg.from_user.full_name}*\n"
        f"🆔 `{uid}`  |  @{msg.from_user.username or '—'}\n"
        f"💰 Amount: `${amount}`\n"
        f"🏆 Total Won: `${round(d['total_won'],2)}`\n"
        f"👥 Refs: `{d['total_refs']}`\n"
        f"📍 Address:\n`{addr}`"
    )
    try:
        await bot.send_message(ADMIN_ID, admin_text, parse_mode="Markdown")
        d["balance"] = 0.0
        save_db()
        await msg.answer(t(lang, "withdraw_done"), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Withdraw notify failed: {e}")
        await msg.answer("⚠️ Error. Please try again later.")
    await state.clear()
    await send_home(msg, uid)

# ═══════════════════════════════════════════════
#  Stars payment
# ═══════════════════════════════════════════════
@dp.callback_query(F.data == "buy_spin")
async def cb_buy(cb: types.CallbackQuery):
    uid  = cb.from_user.id
    d    = get_user(uid)
    reset_daily(d)
    lang = d["lang"]
    if d["paid_today"] or d["vip"]:
        await cb.answer(t(lang, "already_paid"), show_alert=True)
        return
    titles = {"en":"⭐ Daily Upgrade — 3 Spins","ar":"⭐ ترقية اليوم — 3 دورانات","ru":"⭐ Улучшение — 3 вращения"}
    descs  = {
        "en":"Pay 50 Stars for 3 daily spins instead of 1. Resets every midnight.",
        "ar":"ادفع 50 نجمة للحصول على 3 دورانات يومياً بدلاً من واحدة.",
        "ru":"50 Звёзд = 3 вращения в день вместо 1. Сбрасывается каждую полночь."
    }
    await bot.send_invoice(
        chat_id       = cb.message.chat.id,
        title         = titles[lang],
        description   = descs[lang],
        payload       = "upgrade_3spins",
        provider_token= "",
        currency      = "XTR",
        prices        = [LabeledPrice(label="3 Daily Spins", amount=50)]
    )
    await cb.answer()

@dp.pre_checkout_query()
async def pre_checkout(pcq: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pcq.id, ok=True)

@dp.message(F.successful_payment)
async def payment_done(msg: types.Message):
    uid  = msg.from_user.id
    d    = get_user(uid)
    reset_daily(d)
    lang = d["lang"]
    d["daily_limit"] = PAID_DAILY_SPINS
    d["paid_today"]  = True
    save_db()
    await msg.answer(t(lang, "payment_ok"), parse_mode="Markdown")
    await send_home(msg, uid)

# ═══════════════════════════════════════════════
#  Admin commands
# ═══════════════════════════════════════════════
def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID

@dp.message(Command("admin"))
async def cmd_admin(msg: types.Message):
    if not is_admin(msg.from_user.id):
        return
    total   = len(users_db)
    today   = str(date.today())
    active  = sum(1 for u in users_db.values() if u.get("last_spin_day") == today)
    balances= sum(u.get("balance",0) for u in users_db.values())
    won     = sum(u.get("total_won",0) for u in users_db.values())
    vips    = sum(1 for u in users_db.values() if u.get("vip"))
    banned  = sum(1 for u in users_db.values() if u.get("banned"))
    await msg.answer(
        f"🛠 *Admin Panel*\n\n"
        f"👥 Total users   : `{total}`\n"
        f"🔥 Active today  : `{active}`\n"
        f"💰 Total balances: `${round(balances,2)}`\n"
        f"🏆 Total won     : `${round(won,2)}`\n"
        f"⭐ VIP users     : `{vips}`\n"
        f"🚫 Banned        : `{banned}`\n\n"
        f"*Commands:*\n"
        f"`/vip <id>` — grant VIP\n"
        f"`/ban <id>` — ban user\n"
        f"`/unban <id>` — unban user\n"
        f"`/addbal <id> <amount>` — add balance\n"
        f"`/userinfo <id>` — user details\n"
        f"`/broadcast` — send to all\n"
        f"`/save` — save DB now",
        parse_mode="Markdown"
    )

@dp.message(Command("vip"))
async def cmd_vip(msg: types.Message):
    if not is_admin(msg.from_user.id): return
    parts = msg.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await msg.answer("Usage: /vip <user_id>"); return
    tid = int(parts[1])
    d   = get_user(tid)
    d["vip"] = True; d["daily_limit"] = PAID_DAILY_SPINS
    save_db()
    await msg.answer(f"⭐ VIP granted to `{tid}`", parse_mode="Markdown")
    try:
        await bot.send_message(tid, t(d["lang"], "vip_granted"), parse_mode="Markdown")
    except Exception: pass

@dp.message(Command("ban"))
async def cmd_ban(msg: types.Message):
    if not is_admin(msg.from_user.id): return
    parts = msg.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await msg.answer("Usage: /ban <user_id>"); return
    tid = int(parts[1])
    get_user(tid)["banned"] = True
    save_db()
    await msg.answer(f"🚫 Banned `{tid}`", parse_mode="Markdown")

@dp.message(Command("unban"))
async def cmd_unban(msg: types.Message):
    if not is_admin(msg.from_user.id): return
    parts = msg.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await msg.answer("Usage: /unban <user_id>"); return
    tid = int(parts[1])
    get_user(tid)["banned"] = False
    save_db()
    await msg.answer(f"✅ Unbanned `{tid}`", parse_mode="Markdown")

@dp.message(Command("addbal"))
async def cmd_addbal(msg: types.Message):
    if not is_admin(msg.from_user.id): return
    parts = msg.text.split()
    if len(parts) < 3 or not parts[1].isdigit():
        await msg.answer("Usage: /addbal <user_id> <amount>"); return
    tid = int(parts[1])
    try: amount = float(parts[2])
    except ValueError:
        await msg.answer("❌ Invalid amount"); return
    d = get_user(tid)
    d["balance"]   += amount
    d["total_won"] += max(0, amount)
    save_db()
    await msg.answer(f"✅ Added `${amount}` to `{tid}` — new balance: `${round(d['balance'],2)}`", parse_mode="Markdown")

@dp.message(Command("userinfo"))
async def cmd_userinfo(msg: types.Message):
    if not is_admin(msg.from_user.id): return
    parts = msg.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await msg.answer("Usage: /userinfo <user_id>"); return
    tid = int(parts[1])
    if tid not in users_db:
        await msg.answer("❌ User not found"); return
    d = users_db[tid]
    await msg.answer(
        f"👤 *{d.get('name','—')}* (@{d.get('username','—')})\n"
        f"🆔 `{tid}`\n"
        f"🌐 Lang: `{d.get('lang','—')}`\n"
        f"💰 Balance: `${round(d.get('balance',0),2)}`\n"
        f"🏆 Total Won: `${round(d.get('total_won',0),2)}`\n"
        f"👥 Refs: `{d.get('total_refs',0)}`\n"
        f"🎡 Spins: `{d.get('total_spins',0)}`\n"
        f"🎁 Bonus: `{d.get('bonus_spins',0)}`\n"
        f"🔥 Streak: `{d.get('streak',0)}`\n"
        f"⭐ VIP: `{d.get('vip',False)}`\n"
        f"🚫 Banned: `{d.get('banned',False)}`\n"
        f"📅 Joined: `{d.get('joined_at','—')}`",
        parse_mode="Markdown"
    )

@dp.message(Command("save"))
async def cmd_save(msg: types.Message):
    if not is_admin(msg.from_user.id): return
    save_db()
    await msg.answer(f"✅ Database saved. ({len(users_db)} users)")

@dp.message(Command("broadcast"))
async def cmd_broadcast(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    await msg.answer("📢 Send the message to broadcast to all users:")
    await state.set_state(BroadcastState.waiting_msg)

@dp.message(BroadcastState.waiting_msg)
async def fsm_broadcast(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        await state.clear(); return
    count = 0
    for uid in list(users_db.keys()):
        try:
            await bot.send_message(uid, msg.text, parse_mode="Markdown")
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await state.clear()
    await msg.answer(f"✅ Broadcast sent to *{count}* users.", parse_mode="Markdown")

# ═══════════════════════════════════════════════
#  Webhook setup (Vercel / any HTTPS host)
# ═══════════════════════════════════════════════
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from aiogram.types import Update

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "my_super_secret_42")
WEBHOOK_PATH   = f"/webhook/{WEBHOOK_SECRET}"
# Set WEBHOOK_URL in your Vercel env vars, e.g.:
#   WEBHOOK_URL = https://your-project.vercel.app
WEBHOOK_URL    = os.getenv("WEBHOOK_URL", "")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Called once on startup — register webhook & load DB."""
    load_db()
    if WEBHOOK_URL:
        webhook_full = WEBHOOK_URL.rstrip("/") + WEBHOOK_PATH
        await bot.set_webhook(
            url          = webhook_full,
            drop_pending_updates = True,
            secret_token = WEBHOOK_SECRET,
        )
        logger.info(f"✅ Webhook set: {webhook_full}")
    else:
        logger.warning("⚠️  WEBHOOK_URL not set — webhook NOT registered.")
    yield
    # Shutdown
    save_db()
    await bot.delete_webhook()
    logger.info("🛑 Webhook removed, DB saved.")

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def health():
    """Vercel health-check endpoint."""
    return {"status": "ok", "bot": BOT_NAME, "users": len(users_db)}

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    """Receive updates from Telegram."""
    # Verify secret token header
    token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if token != WEBHOOK_SECRET:
        return Response(status_code=403)

    data   = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return Response(status_code=200)

# ─── Local polling fallback (run directly with python bot.py) ───
if __name__ == "__main__":
    import sys
    if "--poll" in sys.argv or not WEBHOOK_URL:
        # Local dev: use polling
        async def _poll():
            load_db()
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info(f"🤖 Polling mode — {BOT_NAME}")
            await dp.start_polling(bot)
        asyncio.run(_poll())
    else:
        import uvicorn
        uvicorn.run("bot:app", host="0.0.0.0", port=8000, reload=False)
