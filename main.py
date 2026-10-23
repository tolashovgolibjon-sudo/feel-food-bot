import os
import sqlite3
import math
from datetime import datetime
import openpyxl
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ==========================================
# SOZLAMALAR VA OFIS GEOLOKATSIYASI
# ==========================================
TOKEN = "8767402192:AAH5xDUsI78Kr4kg51l8yDsXbMX7RggpG1k"  # O'zingizning tokeningiz
ADMIN_ID = 1631414170                            # Rahbarning ID raqami

# Ofis koordinatalari (Chust / Namangan)
OFFICE_LAT = 41.003753
OFFICE_LON = 71.672794  
ALLOWED_RADIUS_METERS = 150  # Ruxsat etilgan radius (metrda)

# ==========================================
# BAZANI (DATABASE) YARATISH
# ==========================================
conn = sqlite3.connect('attendance.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        user_name TEXT,
        action TEXT,
        date_time TEXT
    )
''')

# Smena stavkasi va soati saqlanadigan jadval
cursor.execute('''
    CREATE TABLE IF NOT EXISTS rates (
        user_id INTEGER PRIMARY KEY,
        shift_rate REAL,
        shift_hours REAL
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS employees (
        user_id INTEGER PRIMARY KEY,
        user_name TEXT
    )
''')
conn.commit()

# Masofani hisoblash funksiyasi (Haversine formulasi)
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000  # Yer radiusi (metrda)
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c

# ==========================================
# 1. FLASK VEB-SERVER QISMI (UptimeRobot uchun)
# ==========================================
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "Bot faol va ishlamoqda!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ==========================================
# 2. BOT FUNKSIYALARI
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Assalomu alaykum! Moslashuvchan smena stavkali davomat boti ishga tushdi.")

# Xodimni bazaga qo'shish (/qosh [user_id] [Ism])
async def add_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Kechirasiz, bu buyruq faqat rahbar uchun! ❌")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text("⚠️ Xato! Ishlatish tartibi:\n`/qosh XODIM_ID Xodim_Ismi`\nMasalan: `/qosh 123456789 Anvar`", parse_mode="Markdown")
        return

    try:
        emp_id = int(args[0])
        emp_name = " ".join(args[1:])
        
        cursor.execute("REPLACE INTO employees (user_id, user_name) VALUES (?, ?)", (emp_id, emp_name))
        conn.commit()
        await update.message.reply_text(f"✅ Xodim muvaffaqiyatli qo'shildi:\nID: `{emp_id}`\nIsm: {emp_name}", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("Xatolik! ID faqat raqamlardan iborat bo'lishi kerak.")

# Stavka, summa va soatni kiritish (/stavka [user_id] [summa] [soat])
async def set_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Kechirasiz, bu buyruq faqat rahbar uchun! ❌")
        return

    args = context.args
    if len(args) < 3:
        await update.message.reply_text("⚠️ Xato! Ishlatish tartibi:\n`/stavka XODIM_ID SUMMA SOAT`\nMasalan: `/stavka 123456789 150000 12`", parse_mode="Markdown")
        return

    try:
        target_user_id = int(args[0])
        rate = float(args[1])
        hours = float(args[2])
        
        cursor.execute("REPLACE INTO rates (user_id, shift_rate, shift_hours) VALUES (?, ?, ?)", (target_user_id, rate, hours))
        conn.commit()
        await update.message.reply_text(f"✅ Xodim (ID: {target_user_id}) uchun **{hours} soatlik** smena stavkasi **{rate:,.0f} so'm** etib belgilandi!", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("Xatolik! ID, summa va soat raqam bo'lishi kerak.")

# Guruhga video xabar (krujok) tashlanganda tekshirish
async def handle_video_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cursor.execute("SELECT user_id FROM employees WHERE user_id = ?", (user_id,))
    if not cursor.fetchone() and user_id != ADMIN_ID:
        return

    keyboard = [
        [
            InlineKeyboardButton("Keldim 🟢", callback_data="keldim"),
            InlineKeyboardButton("Kettim 🔴", callback_data="kettim")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Iltimos, harakatni tanlang:", reply_markup=reply_markup)

# Tugma bosilganda GPS so'rash
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action = "Keldim" if query.data == "keldim" else "Kettim"
    context.user_data['pending_action'] = action

    location_keyboard = [[KeyboardButton("📍 Turgan joyimni yuborish", request_location=True)]]
    reply_markup = ReplyKeyboardMarkup(location_keyboard, one_time_keyboard=True, resize_keyboard=True)

    await query.edit_message_text(text=f"Siz **{action}** tugmasini bosdingiz. Ofisda ekanligingizni tasdiqlash uchun lokatsiyangizni yuboring:", parse_mode="Markdown")
    await query.message.reply_text("Pastdagi tugmani bosing:", reply_markup=reply_markup)

# Lokatsiyani qabul qilish va saqlash
async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    user_name = user.full_name
    
    if 'pending_action' not in context.user_data:
        return

    action = context.user_data['pending_action']
    user_location = update.message.location

    if not user_location:
        await update.message.reply_text("Iltimos, haqiqiy lokatsiyangizni yuboring!", reply_markup=ReplyKeyboardRemove())
        return

    distance = calculate_distance(user_location.latitude, user_location.longitude, OFFICE_LAT, OFFICE_LON)

    if distance <= ALLOWED_RADIUS_METERS:
        date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO attendance (user_id, user_name, action, date_time) VALUES (?, ?, ?, ?)",
                       (user_id, user_name, action, date_time))
        conn.commit()

        await update.message.reply_text(
            f"✅ Tasdiqlandi! {user_name} — {action} sifatida belgilandi.\n📍 Ofisdan masofa: {int(distance)} metr.\nVaqt: {date_time}",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await update.message.reply_text(
            f"❌ Xatolik! Siz ofis hududida emassiz.\n📍 Masofangiz: {int(distance)} metr (Ruxsat etilgan limit: {ALLOWED_RADIUS_METERS} m).",
            reply_markup=ReplyKeyboardRemove()
        )
    
    context.user_data.pop('pending_action', None)

# HAMMA MA'LUMOTLARNI EXCEL FORMATDA YUBORISH (/excel)
async def export_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Kechirasiz, bu buyruq faqat rahbar uchun! ❌")
        return

    wb = openpyxl.Workbook()
    
    # 1-sahifa: Davomat tarixi
    ws_att = wb.active
    ws_att.title = "Davomat"
    ws_att.append(["Xodim ID", "Xodim Ismi", "Harakat", "Sana va Vaqt"])
    
    cursor.execute("SELECT user_id, user_name, action, date_time FROM attendance ORDER BY date_time ASC")
    for row in cursor.fetchall():
        ws_att.append(row)

    # 2-sahifa: Oylik hisob-kitoblar (Har bir xodimning o'zining belgilangan soati va summasi asosida)
    ws_sal = wb.create_sheet(title="Oylik Hisoboti")
    ws_sal.append(["Xodim ID", "Xodim Ismi", "Smena Summasi", "Smena Soati", "Jami Ishlagan Soat", "Hisoblangan Maosh (so'm)"])

    cursor.execute("SELECT user_id, user_name FROM employees")
    employees = cursor.fetchall()

    for emp_id, emp_name in employees:
        # Stavka va soatni olish
        cursor.execute("SELECT shift_rate, shift_hours FROM rates WHERE user_id = ?", (emp_id,))
        rate_row = cursor.fetchone()
        
        if rate_row:
            shift_rate = rate_row[0]
            shift_hours = rate_row[1]
        else:
            shift_rate = 0
            shift_hours = 12  # Standart 12 deb olinadi agar belgilanmagan bo'lsa

        # 1 soatlik haqni hisoblash
        hourly_equivalent = (shift_rate / shift_hours) if shift_hours > 0 else 0

        # Ishlagan vaqtini hisoblash
        cursor.execute("SELECT action, date_time FROM attendance WHERE user_id = ? ORDER BY date_time ASC", (emp_id,))
        records = cursor.fetchall()

        total_seconds = 0
        last_in_time = None
        for action, dt_str in records:
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            if action == "Keldim":
                last_in_time = dt
            elif action == "Kettim" and last_in_time:
                diff = (dt - last_in_time).total_seconds()
                if diff > 0:
                    total_seconds += diff
                last_in_time = None

        total_hours = total_seconds / 3600
        total_salary = total_hours * hourly_equivalent

        ws_sal.append([emp_id, emp_name, shift_rate, shift_hours, round(total_hours, 2), round(total_salary, 2)])

    file_name = "Moslashuvchan_Hisobot.xlsx"
    wb.save(file_name)

    with open(file_name, "rb") as file:
        await update.message.reply_document(
            document=file, 
            filename=file_name, 
            caption="📊 **Hisobot tayyor!**\nHar bir xodimning o'zi belgilangan soatlik smenasi va ishlagan vaqtiga qarab oylik maoshlari hisoblandi."
        )

# ==========================================
# 3. ASOSIY ISHGA TUSHIRISH (MAIN)
# ==========================================
if __name__ == "__main__":
    # Flask serverni ishga tushiramiz
    keep_alive()
    
    # Telegram bot dasturini tuzamiz
    app = Application.builder().token(TOKEN).build()

    # Buyruqlar va hodisalar
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("qosh", add_employee))
    app.add_handler(CommandHandler("stavka", set_rate))
    app.add_handler(CommandHandler("excel", export_excel))
    app.add_handler(CallbackQueryHandler(button_click))
    
    # Krujok va video xabarlarni tutib olish
    app.add_handler(MessageHandler(filters.VIDEO_NOTE | filters.VIDEO, handle_video_note))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))

    print("Bot muvaffaqiyatli ishga tushdi...")
    
    # Pollingni barcha turdagi xabarlarni qabul qiladigan qilib ishga tushiramiz
    app.run_polling(allowed_updates=["message", "edited_message", "callback_query"])
    
