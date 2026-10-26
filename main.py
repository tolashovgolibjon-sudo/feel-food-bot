import os
import math
import sqlite3
import datetime
import pytz
from io import BytesIO
import openpyxl
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
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
TOKEN = "8767402192:AAHKaeM8ymcVm31TzehRvqmAbWbNS4vp1oQ"
ADMIN_TELEGRAM_ID = 1631414170  # Bosh admin ID raqami

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
# 3. BAZANI YARATISH (12 yoki 13 soatlik smena tizimi bilan)
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS employees (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            shift_rate REAL NOT NULL,
            shift_hours INTEGER NOT NULL DEFAULT 12,
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
    
    cursor.execute(
        "INSERT OR IGNORE INTO employees (user_id, full_name, shift_rate, shift_hours, is_admin) VALUES (?, ?, ?, ?, ?)",
        (ADMIN_TELEGRAM_ID, "Bosh Admin", 0.0, 12, 1)
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
# 5. ADMIN BUYRUQLARI
# ---------------------------------------------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Assalomu alaykum, {user.first_name}!\n"
        f"Xavfsiz davomat tizimiga xush kelibsiz.\n\n"
        f"🆔 Sizning Telegram ID raqamingiz: `{user.id}`",
        parse_mode="Markdown"
    )

# /qosh <id> <FIO> <summa> <soat (12 yoki 13)>
async def add_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_TELEGRAM_ID:
        await update.message.reply_text("❌ Bu buyruqni faqat admin bajarishi mumkin!")
        return

    args = context.args
    if len(args) < 4:
        await update.message.reply_text(
            "⚠️ Xato format!\n"
            "To'g'ri ishlatish: `/qosh 1631414170 G'olibjon_To'lashov 150000 12`",
            parse_mode="Markdown"
        )
        return

    try:
        new_user_id = int(args[0])
        full_name = args[1].replace("_", " ")
        shift_rate = float(args[2])
        shift_hours = int(args[3])
    except ValueError:
        await update.message.reply_text("❌ ID, summa va soat raqam shaklida bo'lishi kerak!")
        return

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO employees (user_id, full_name, shift_rate, shift_hours, is_admin) VALUES (?, ?, ?, ?, 0)",
        (new_user_id, full_name, shift_rate, shift_hours)
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ Xodim qo'shildi:\n"
        f"👤 {full_name} (ID: {new_user_id})\n"
        f"💰 Smena haqi: {shift_rate:,.0f} so'm\n"
        f"⏰ Smena vaqti: {shift_hours} soatlik"
    )

# /stavka <id> <yangi_summa> <soat (12 yoki 13)>
async def update_stavka(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_TELEGRAM_ID:
        await update.message.reply_text("❌ Faqat admin uchun!")
        return

    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "⚠️ Xato format!\n"
            "To'g'ri ishlatish: `/stavka 1631414170 160000 13`",
            parse_mode="Markdown"
        )
        return

    try:
        target_id = int(args[0])
        new_rate = float(args[1])
        new_hours = int(args[2])
    except ValueError:
        await update.message.reply_text("❌ ID, summa va soat raqam bo'lishi kerak!")
        return

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE employees SET shift_rate = ?, shift_hours = ? WHERE user_id = ?", (new_rate, new_hours, target_id))
    if cursor.rowcount == 0:
        await update.message.reply_text("❌ Bu ID raqamdagi xodim topilmadi!")
    else:
        conn.commit()
        await update.message.reply_text(f"✅ Xodim (ID: {target_id}) stavkasi {new_rate:,.0f} so'm ({new_hours} soatlik) qilib yangilandi.")
    conn.close()

# /ochir <id>
async def delete_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_TELEGRAM_ID:
        await update.message.reply_text("❌ Faqat admin uchun!")
        return

    args = context.args
    if not args:
        await update.message.reply_text("⚠️ Xato format!\nIshlatish: `/ochir 123456789`", parse_mode="Markdown")
        return

    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ ID raqam bo'lishi kerak!")
        return

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM employees WHERE user_id = ? AND is_admin = 0", (target_id,))
    if cursor.rowcount == 0:
        await update.message.reply_text("❌ Xodim topilmadi yoki adminni o'chirib bo'lmaydi!")
    else:
        conn.commit()
        await update.message.reply_text(f"✅ Xodim (ID: {target_id}) tizimdan o'chirildi.")
    conn.close()

# ---------------------------------------------------------
# 6. VIDEO VA DUMALOQ VIDEO ORQALI DAVOMATNI CHIQarish
# ---------------------------------------------------------
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("🟢 Keldim", callback_data="check_in"),
            InlineKeyboardButton("🔴 Ketdim", callback_data="check_out")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "📹 Video qabul qilindi! Davomatni belgilash uchun quyidagi tugmani bosing:",
        reply_markup=reply_markup
    )

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

    if not emp and user_id != ADMIN_TELEGRAM_ID:
        await query.message.reply_text(f"❌ {user_name}, siz xodimlar ro'yxatida emassiz! ID: `{user_id}`", parse_mode="Markdown")
        return

    context.user_data['pending_action'] = action

    location_keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Geolokatsiyani yuborish", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await query.message.reply_text(
        f"📍 {user_name}, ofisda ekanligingizni tasdiqlash uchun pastdagi **'📍 Geolokatsiyani yuborish'** tugmasini bosing:",
        reply_markup=location_keyboard
    )

# ---------------------------------------------------------
# 7. GPS LOKATSIYANI TEKSHIRISH VA HISOB-KITOB
# ---------------------------------------------------------
async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_loc = update.message.location
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name

    action = context.user_data.get('pending_action')
    if not action:
        await update.message.reply_text("⚠️ Avval video ostidagi Keldim/Ketdim tugmalaridan birini bosing.", reply_markup=ReplyKeyboardRemove())
        return

    dist = calculate_distance(user_loc.latitude, user_loc.longitude, OFFICE_LAT, OFFICE_LON)

    if dist > MAX_DISTANCE_METERS:
        await update.message.reply_text(
            f"🚫 **Xavfsizlik ogohlantirishi:** Siz ofis hududida emassiz!\n"
            f"Masofa: {int(dist)} metr (Ruxsat: {MAX_DISTANCE_METERS} m).",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    now_uzb = datetime.datetime.now(UZB_TZ)
    today_str = now_uzb.strftime("%Y-%m-%d")
    time_str = now_uzb.strftime("%H:%M:%S")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT shift_rate, shift_hours FROM employees WHERE user_id = ?", (user_id,))
    emp_data = cursor.fetchone()
    shift_rate = emp_data[0] if emp_data else 0.0
    shift_hours = emp_data[1] if emp_data else 12

    if action == "check_in":
        cursor.execute("SELECT id FROM attendance WHERE user_id = ? AND date = ?", (user_id, today_str))
        if cursor.fetchone():
            await update.message.reply_text(f"⚠️ {user_name}, siz bugun allaqachon 'Keldim' deb belgilagansiz!", reply_markup=ReplyKeyboardRemove())
        else:
            cursor.execute("INSERT INTO attendance (user_id, date, check_in) VALUES (?, ?, ?)", (user_id, today_str, time_str))
            conn.commit()
            await update.message.reply_text(f"✅ {user_name}, ishga kelgan vaqtingiz qayd etildi: {time_str} 🟢", reply_markup=ReplyKeyboardRemove())

    elif action == "check_out":
        cursor.execute("SELECT id, check_in FROM attendance WHERE user_id = ? AND date = ?", (user_id, today_str))
        row = cursor.fetchone()
        if not row:
            await update.message.reply_text(f"⚠️ {user_name}, siz bugun hali 'Keldim' tugmasini bosmagansiz!", reply_markup=ReplyKeyboardRemove())
        else:
            att_id, check_in_str = row
            check_in_dt = UZB_TZ.localize(datetime.datetime.strptime(f"{today_str} {check_in_str}", "%Y-%m-%d %H:%M:%S"))
            
            duration = (now_uzb - check_in_dt).total_seconds() / 3600.0
            earned = shift_rate

            cursor.execute(
                "UPDATE attendance SET check_out = ?, hours_worked = ?, earned_money = ? WHERE id = ?",
                (time_str, round(duration, 2), earned, att_id)
            )
            conn.commit()
            await update.message.reply_text(
                f"🔴 {user_name}, ishdan ketgan vaqtingiz qayd etildi: {time_str}\n"
                f"⏱ Smena vaqti: {shift_hours} soatlik\n"
                f"💰 Hisoblangan smena haqi: {earned:,.0f} so'm",
                reply_markup=ReplyKeyboardRemove()
            )

    conn.close()
    context.user_data['pending_action'] = None

# ---------------------------------------------------------
# 8. EXCEL HISOBOTLAR (/excel kun va /excel maosh)
# ---------------------------------------------------------
async def excel_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_TELEGRAM_ID:
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun!")
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ Xato format!\n"
            "Foydalanish:\n"
            "1️⃣ `/excel kun`\n"
            "2️⃣ `/excel maosh 2026-05-01 2026-05-31`",
            parse_mode="Markdown"
        )
        return

    sub_command = args[0].lower()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    wb = openpyxl.Workbook()
    ws = wb.active

    if sub_command == "kun":
        today_str = datetime.datetime.now(UZB_TZ).strftime("%Y-%m-%d")
        ws.title = f"Kunlik-{today_str}"
        ws.append(["Xodim FIO", "Sana", "Kelgan vaqt", "Ketgan vaqt", "Ish vaqti (soat)", "Smena Haqi (so'm)"])

        cursor.execute('''
            SELECT e.full_name, a.date, a.check_in, a.check_out, a.hours_worked, a.earned_money 
            FROM attendance a
            JOIN employees e ON a.user_id = e.user_id
            WHERE a.date = ?
        ''', (today_str,))
        rows = cursor.fetchall()
        for r in rows:
            ws.append(list(r))
        
        file_name = f"Kunlik_hisobot_{today_str}.xlsx"

    elif sub_command == "maosh" and len(args) >= 3:
        start_date = args[1]
        end_date = args[2]
        ws.title = "Maosh-Hisoboti"
        ws.append(["Xodim FIO", "Sana", "Kelgan vaqt", "Ketgan vaqt", "Ish vaqti (soat)", "Smena Haqi (so'm)"])

        cursor.execute('''
            SELECT e.full_name, a.date, a.check_in, a.check_out, a.hours_worked, a.earned_money 
            FROM attendance a
            JOIN employees e ON a.user_id = e.user_id
            WHERE a.date BETWEEN ? AND ?
        ''', (start_date, end_date))
        rows = cursor.fetchall()
        for r in rows:
            ws.append(list(r))

        file_name = f"Maosh_hisoboti_{start_date}_dan_{end_date}_gacha.xlsx"
    else:
        await update.message.reply_text("❌ Noto'g'ri buyruq formati!")
        conn.close()
        return

    conn.close()

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)

    await context.bot.send_document(
        chat_id=ADMIN_TELEGRAM_ID,
        document=bio,
        filename=file_name,
        caption="📊 So'ralgan Excel hisobot tayyor!"
    )
    if update.effective_chat.type != "private":
        await update.message.reply_text("✅ Excel hisobot shaxsiy chatingizga yuborildi!")

# ---------------------------------------------------------
# 9. ISHGA TUSHIRISH
# ---------------------------------------------------------
async def post_init(application: Application):
    await application.bot.delete_webhook(drop_pending_updates=True)

if __name__ == "__main__":
    init_db()
    keep_alive()

    app = Application.builder().token(TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("qosh", add_employee))
    app.add_handler(CommandHandler("stavka", update_stavka))
    app.add_handler(CommandHandler("ochir", delete_employee))
    app.add_handler(CommandHandler("excel", excel_report))
    app.add_handler(CommandHandler("exsel", excel_report))
    
    app.add_handler(CallbackQueryHandler(button_callback))
    
    # MUHIM: Ham oddiy video, ham dumaloq video xabarlarni tutish uchun:
    app.add_handler(MessageHandler(filters.VIDEO | filters.VIDEO_NOTE, handle_video))
    
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))

    print("🛡️ Bot muvaffaqiyatli ishga tushdi!")
    app.run_polling(drop_pending_updates=True, close_loop=False)
    
