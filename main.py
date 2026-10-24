import os
import math
import sqlite3
import datetime
import pytz
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ---------------------------------------------------------
# 1. ASOSIY SOZLAMALAR VA ADMIN ID
# ---------------------------------------------------------
TOKEN = "8767402192:AAHYvVYuEBQOCTYIXWTN01qBR_3hkwG9Ni0"

# 🔴 O'Z TELEGRAM ID RAQAMINGIZNI SHU YERGA YOZING (Masalan: 123456789)
ADMIN_TELEGRAM_ID = 1631414170  # <-- O'z ID raqamingizni yozing!

OFFICE_LAT = 41.003753
OFFICE_LON = 71.672794
MAX_DISTANCE_METERS = 150

UZB_TZ = pytz.timezone("Asia/Tashkent")
DB_FILE = "attendance.db"

# ---------------------------------------------------------
# 2. FLASK SERVER (24/7 UCHUN)
# ---------------------------------------------------------
web_app = Flask('')

@web_app.route('/')
def home():
    return "Bot 24/7 himoyalangan rejimda ishlamoqda!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# ---------------------------------------------------------
# 3. BAZANI YARATISH VA BOSHLANG'ICH ADMINNI QO'SHISH
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS employees (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            hourly_rate REAL NOT NULL,
            is_admin INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT,
            check_in TEXT,
            check_out TEXT,
            hours_worked REAL DEFAULT 0,
            earned_money REAL DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES employees(user_id)
        )
    ''')
    
    # Boshlang'ich adminni avtomatik bazaga kiritish (agar mavjud bo'lmasa)
    cursor.execute(
        "INSERT OR IGNORE INTO employees (user_id, full_name, hourly_rate, is_admin) VALUES (?, ?, ?, ?)",
        (ADMIN_TELEGRAM_ID, "Bosh Admin", 0.0, 1)
    )
    
    conn.commit()
    conn.close()

# ---------------------------------------------------------
# 4. GPS MASOFANI HISOBLASH
# ---------------------------------------------------------
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0)**2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# ---------------------------------------------------------
# 5. BUYRUQLAR VA HIMOYALANGAN FUNKSIYALAR
# ---------------------------------------------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Assalomu alaykum, {user.first_name}!\n"
        f"Xavfsiz davomat tizimiga xush kelibsiz.\n\n"
        f"🆔 Sizning Telegram ID raqamingiz: `{user.id}`\n"
        f"Agar ro'yxatda bo'lsangiz, davomat tugmalaridan foydalanishingiz mumkin.",
        parse_mode="Markdown"
    )

# 🛡️ ADMIN UCHUN: Yangi xodim qo'shish (/add ID FIO Soatlik_stavka)
async def add_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT is_admin FROM employees WHERE user_id = ?", (admin_id,))
    row = cursor.fetchone()
    
    if not row or row[0] != 1:
        await update.message.reply_text("❌ Bu buyruqni faqat asosiy admin bajarishi mumkin!")
        conn.close()
        return

    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "⚠️ Xato format!\n"
            "To'g'ri ishlatish: `/add 123456789 Alisher_Tursunov 15000`",
            parse_mode="Markdown"
        )
        conn.close()
        return

    try:
        new_user_id = int(args[0])
        full_name = args[1].replace("_", " ")
        hourly_rate = float(args[2])
    except ValueError:
        await update.message.reply_text("❌ ID yoki maosh raqam shaklida bo'lishi kerak!")
        conn.close()
        return

    cursor.execute(
        "INSERT OR REPLACE INTO employees (user_id, full_name, hourly_rate, is_admin) VALUES (?, ?, ?, 0)",
        (new_user_id, full_name, hourly_rate)
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(f"✅ Muvaffaqiyatli qo'shildi!\n👤 {full_name} (ID: {new_user_id}) - {hourly_rate:,.0f} so'm/soat")

# Davomat tugmalarini chiqarish
async def send_attendance_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("🟢 Keldim", callback_data="check_in"),
            InlineKeyboardButton("🔴 Ketdim", callback_data="check_out")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👇 Davomatni belgilash uchun tugmani bosing:",
        reply_markup=reply_markup
    )

# Tugma bosilganda xavfsizlik tekshiruvi
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action = query.data
    user_id = query.from_user.id
    user_name = query.from_user.full_name

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT full_name FROM employees WHERE user_id = ?", (user_id,))
    emp = cursor.fetchone()
    conn.close()

    if not emp:
        await query.message.reply_text(
            f"❌ {user_name}, xavfsizlik tizimi: Siz xodimlar ro'yxatida emassiz!\n"
            f"🆔 ID raqamingiz: `{user_id}`. Admindan ro'yxatga kiritishini so'rang.",
            parse_mode="Markdown"
        )
        return

    context.user_data['pending_action'] = action
    await query.message.reply_text(
        f"📍 {user_name}, ofisda ekanligingizni tasdiqlash uchun Telegram menyusidagi "
        f"**📎 (Qo'shimcha) -> Joylashuv (Location)** tugmasi orqali joriy GPS lokatsiyangizni yuboring.",
        parse_mode="Markdown"
    )

# GPS Lokatsiyani tekshirib qabul qilish
async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_loc = update.message.location
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name

    action = context.user_data.get('pending_action')
    if not action:
        await update.message.reply_text("Iltimos, avval /davomat tugmalaridan birini bosing.")
        return

    dist = calculate_distance(user_loc.latitude, user_loc.longitude, OFFICE_LAT, OFFICE_LON)

    if dist > MAX_DISTANCE_METERS:
        await update.message.reply_text(
            f"🚫 **Xavfsizlik ogohlantirishi:** Siz ofis hududida emassiz!\n"
            f"Siz belgilangan nuqtadan {int(dist)} metr uzoqlikdasiz (Ruxsat etilgan: {MAX_DISTANCE_METERS} m).",
            parse_mode="Markdown"
        )
        return

    now_uzb = datetime.datetime.now(UZB_TZ)
    today_str = now_uzb.strftime("%Y-%m-%d")
    time_str = now_uzb.strftime("%H:%M:%S")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT hourly_rate FROM employees WHERE user_id = ?", (user_id,))
    rate_row = cursor.fetchone()
    hourly_rate = rate_row[0] if rate_row else 0.0

    if action == "check_in":
        cursor.execute(
            "SELECT id FROM attendance WHERE user_id = ? AND date = ?", 
            (user_id, today_str)
        )
        existing = cursor.fetchone()
        
        if existing:
            await update.message.reply_text(f"⚠️ {user_name}, siz bugun allaqachon 'Keldim' deb belgilagansiz!")
        else:
            cursor.execute(
                "INSERT INTO attendance (user_id, date, check_in) VALUES (?, ?, ?)",
                (user_id, today_str, time_str)
            )
            conn.commit()
            await update.message.reply_text(f"✅ {user_name}, ishga kelgan vaqtingiz qayd etildi: {time_str} 🟢")

    elif action == "check_out":
        cursor.execute(
            "SELECT id, check_in FROM attendance WHERE user_id = ? AND date = ?", 
            (user_id, today_str)
        )
        row = cursor.fetchone()
        
        if not row:
            await update.message.reply_text(f"⚠️ {user_name}, siz bugun hali 'Keldim' tugmasini bosmagansiz!")
        else:
            att_id, check_in_str = row
            check_in_dt = datetime.datetime.strptime(f"{today_str} {check_in_str}", "%Y-%m-%d %H:%M:%S")
            check_in_dt = UZB_TZ.localize(check_in_dt)
            
            duration = (now_uzb - check_in_dt).total_seconds() / 3600.0
            earned = round(duration * hourly_rate, 2)

            cursor.execute(
                "UPDATE attendance SET check_out = ?, hours_worked = ?, earned_money = ? WHERE id = ?",
                (time_str, round(duration, 2), earned, att_id)
            )
            conn.commit()
            await update.message.reply_text(
                f"🔴 {user_name}, ishdan ketgan vaqtingiz qayd etildi: {time_str}\n"
                f"⏱ Ishlangan vaqt: {round(duration, 2)} soat\n"
                f"💰 Hisoblangan ish haqi: {earned:,.0f} so'm"
            )

    conn.close()
    context.user_data['pending_action'] = None

# Admin hisoboti
async def admin_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT is_admin FROM employees WHERE user_id = ?", (admin_id,))
    row = cursor.fetchone()
    
    if not row or row[0] != 1:
        await update.message.reply_text("❌ Bu buyruq faqat adminlar uchun!")
        conn.close()
        return

    now_uzb = datetime.datetime.now(UZB_TZ)
    today_str = now_uzb.strftime("%Y-%m-%d")

    cursor.execute('''
        SELECT e.full_name, a.check_in, a.check_out, a.hours_worked, a.earned_money 
        FROM attendance a
        JOIN employees e ON a.user_id = e.user_id
        WHERE a.date = ?
    ''', (today_str,))
    records = cursor.fetchall()
    conn.close()

    text = f"📊 **Kunlik Xavfsiz Hisobot ({today_str}):**\n\n"
    if not records:
        text += "Bugun hali hech qanday faollik yo'q."
    else:
        for rec in records:
            text += (
                f"👤 **{rec[0]}**\n"
                f" ├ Keldi: {rec[1] or '—'}\n"
                f" ├ Ketdi: {rec[2] or '—'}\n"
                f" ├ Ish vaqti: {rec[3]} soat\n"
                f" └ Maosh: {rec[4]:,.0f} so'm\n\n"
            )

    try:
        await context.bot.send_message(chat_id=admin_id, text=text, parse_mode="Markdown")
        if update.effective_chat.type != "private":
            await update.message.reply_text("✅ Maxfiy hisobot shaxsiy chatingizga yuborildi!")
    except Exception as e:
        await update.message.reply_text("⚠️ Avval botga shaxsiy chatda /start bosing!")

# ---------------------------------------------------------
# 6. CONFLICT OLDINI OLUVCHI POST_INIT VA ISHGA TUSHIRISH
# ---------------------------------------------------------
async def post_init(application: Application):
    await application.bot.delete_webhook(drop_pending_updates=True)

if __name__ == "__main__":
    init_db()
    keep_alive()

    app = Application.builder().token(TOKEN).post_init(post_init).build()

    # Handlerlar
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("add", add_employee))
    app.add_handler(CommandHandler("davomat", send_attendance_buttons))
    app.add_handler(CommandHandler("report", admin_report))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))

    print("🛡️ Himoyalangan va Admin ID o'rnatilgan bot muvaffaqiyatli ishga tushdi!")
    app.run_polling(drop_pending_updates=True, close_loop=False)
