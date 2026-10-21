import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import sqlite3
from datetime import datetime, timedelta
import openpyxl
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- RENDER PORT TALABINI QONDIRISH UCHUN KICHIK VEB-SERVER ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive and running!")

    def log_message(self, self_format, *args):
        pass # Loglarni to'ldirib yubormasligi uchun

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# Veb-serverni alohida oqimda (thread) ishga tushiramiz
threading.Thread(target=run_web_server, daemon=True).start()
# ------------------------------------------------------------

TOKEN = "8962973921:AAH-UlxazPSmF8FtYFHaYniZpU1DWCsOqNM"

ADMIN_ID = 1449598743 # <--- HAQIQIY TELEGRAM ID RAQAMINGIZNI YOZING!

DEFAULT_DAILY_SALARY = 300000
DEFAULT_WORK_HOURS = 12

conn = sqlite3.connect("davomat.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS attendance (
    user_id INTEGER,
    user_name TEXT,
    action TEXT,
    date_time TEXT,
    latitude REAL,
    longitude REAL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS salaries (
    user_id INTEGER PRIMARY KEY,
    daily_rate INTEGER,
    work_hours REAL
)
""")

try:
    cursor.execute("ALTER TABLE salaries ADD COLUMN work_hours REAL DEFAULT 12")
except sqlite3.OperationalError:
    pass

try:
    cursor.execute("ALTER TABLE attendance ADD COLUMN latitude REAL")
    cursor.execute("ALTER TABLE attendance ADD COLUMN longitude REAL")
except sqlite3.OperationalError:
    pass

conn.commit()

def get_inline_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🟢 Ishga keldim", callback_data="keldim"),
            InlineKeyboardButton("🔴 Ishdan ketdim", callback_data="ketdim")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Feel Food davomat botiga xush kelibsiz! 🏢\n\n"
        "Guruhda davomat qilish uchun quyidagi tugmalardan foydalaning yoki 'Keldim' / 'Ketdim' deb yozing:",
        reply_markup=get_inline_keyboard()
    )

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("Kechirasiz, bu buyruq faqat rahbar uchun! ❌")
        return

    cursor.execute("SELECT user_name, action, date_time FROM attendance ORDER BY date_time DESC LIMIT 15")
    records = cursor.fetchall()

    if records:
        response = "📋 **Admin paneli - Davomat nazorati:**\n\n"
        for row in records:
            response += f"👤 {row[0]} — {row[1]} ({row[2]})\n"
        response += (
            "\n📥 Davomat Excel: /excel"
            "\n💰 To'liq oylik (Matn): /oylik"
            "\n📊 To'liq oylik (Excel): /oylikexcel"
            "\n⏳ 15 kunlik (Matn): /15kun"
            "\n📉 15 kunlik (Excel): /15kunexcel"
            "\n⚙️ Stavka: '/stavka ID SUMMA SOAT'"
        )
        await update.message.reply_text(response, reply_markup=get_inline_keyboard())
    else:
        await update.message.reply_text("Hozircha ma'lumotlar bazasi bo'sh.")

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    user_id = user.id
    user_name = user.first_name
    current_time = (datetime.now() + timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")

    if query.data == "keldim":
        action = "🟢 Ishga keldim"
        cursor.execute("INSERT INTO attendance (user_id, user_name, action, date_time) VALUES (?, ?, ?, ?)",
                       (user_id, user_name, action, current_time))
        conn.commit()
        await query.message.reply_text(f"✅ {user_name}, ishga kelganingiz qayd etildi! [{current_time}]")

    elif query.data == "ketdim":
        action = "🔴 Ishdan ketdim"
        cursor.execute("INSERT INTO attendance (user_id, user_name, action, date_time) VALUES (?, ?, ?, ?)",
                       (user_id, user_name, action, current_time))
        conn.commit()
        await query.message.reply_text(f"🛑 {user_name}, ishdan ketganingiz qayd etildi! [{current_time}]")

async def handle_video_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_name = user.first_name
    await update.message.reply_text(
        f"📹 {user_name}, video xabaringiz qabul qilindi!\nIltimos, maksadni tanlang:",
        reply_markup=get_inline_keyboard()
    )

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    user = update.effective_user
    user_id = user.id
    user_name = user.first_name
    current_time = (datetime.now() + timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")

    if text in ["keldim", "ishga keldim", "keldim (gps)", "ishdaman"]:
        action = "🟢 Ishga keldim"
        cursor.execute("INSERT INTO attendance (user_id, user_name, action, date_time) VALUES (?, ?, ?, ?)",
                       (user_id, user_name, action, current_time))
        conn.commit()
        await update.message.reply_text(f"✅ {user_name}, kelganingiz qayd etildi! [{current_time}]")

    elif text in ["ketdim", "ishdan ketdim", "ketdim (gps)", "ish tugadi"]:
        action = "🔴 Ishdan ketdim"
        cursor.execute("INSERT INTO attendance (user_id, user_name, action, date_time) VALUES (?, ?, ?, ?)",
                       (user_id, user_name, action, current_time))
        conn.commit()
        await update.message.reply_text(f"🛑 {user_name}, ketganingiz qayd etildi! [{current_time}]")

async def set_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("Kechirasiz, bu buyruq faqat rahbar uchun! ❌")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Foydalanish: '/stavka <Xodim_ID> <Kunlik_Stavka> [Kunlik_Soat]'")
        return

    try:
        target_user_id = int(context.args[0])
        rate = int(context.args[1])
        hours = float(context.args[2]) if len(context.args) >= 3 else DEFAULT_WORK_HOURS

        cursor.execute("INSERT OR REPLACE INTO salaries (user_id, daily_rate, work_hours) VALUES (?, ?, ?)",
                       (target_user_id, rate, hours))
        conn.commit()

        hourly = rate / hours
        await update.message.reply_text(f"✅ ID '{target_user_id}' uchun stavka: {rate:,} so'm ({hours} soat).")
    except ValueError:
        await update.message.reply_text("Xatolik! ID, Summa va Soat raqam bo'lishi kerak.")

def get_calculated_salary_data(days_limit=None):
    if days_limit:
        start_date = ((datetime.now() + timedelta(hours=5)) - timedelta(days=days_limit)).strftime("%Y-%m-%d 00:00:00")
        cursor.execute("SELECT user_id, user_name, action, date_time FROM attendance WHERE date_time >= ? ORDER BY user_id, date_time ASC", (start_date,))
    else:
        cursor.execute("SELECT user_id, user_name, action, date_time FROM attendance ORDER BY user_id, date_time ASC")

    records = cursor.fetchall()
    if not records:
        return None

    user_minutes = {}
    user_names = {}
    last_in_time = {}

    for uid, name, action, dt_str in records:
        user_names[uid] = name
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")

        if "Ishga keldim" in action:
            last_in_time[uid] = dt
        elif "Ishdan ketdim" in action and uid in last_in_time:
            time_worked = dt - last_in_time[uid]
            minutes = time_worked.total_seconds() / 60
            user_minutes[uid] = user_minutes.get(uid, 0) + minutes
            del last_in_time[uid]

    results = []
    for uid, total_mins in user_minutes.items():
        name = user_names[uid]
        cursor.execute("SELECT daily_rate, work_hours FROM salaries WHERE user_id = ?", (uid,))
        rate_row = cursor.fetchone()

        daily_rate = rate_row[0] if (rate_row and rate_row[0]) else DEFAULT_DAILY_SALARY
        norm_hours = rate_row[1] if (rate_row and rate_row[1]) else DEFAULT_WORK_HOURS

        hourly_rate = daily_rate / norm_hours
        minute_rate = hourly_rate / 60

        total_hours = total_mins / 60
        total_pay = round(total_mins * minute_rate)

        results.append({
            "user_id": uid,
            "name": name,
            "hours": int(total_hours),
            "minutes": int(total_mins % 60),
            "hourly_rate": int(hourly_rate),
            "total_pay": total_pay
        })

    return results

async def calculate_salary(update: Update, context: ContextTypes.DEFAULT_TYPE, days_limit=None):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("Kechirasiz, bu buyruq faqat rahbar uchun! ❌")
        return

    data = get_calculated_salary_data(days_limit)
    if not data:
        await update.message.reply_text("Ko'rsatilgan davr uchun ma'lumot topilmadi.")
        return

    title_text = f"📊 **Oxirgi {days_limit} kunlik hisoblangan maoshlar:**\n\n" if days_limit else "📊 **Barcha davr uchun hisoblangan maoshlar:**\n\n"
    response = title_text

    for item in data:
        response += f"👤 **{item['name']}** (ID: `{item['user_id']}`):\n"
        response += f"  • Ishlagani: {item['hours']} soat {item['minutes']} daqiqa\n"
        response += f"  • Soatlik stavka: {item['hourly_rate']:,} so'm\n"
        response += f"  • **Hisoblangan summa:** {item['total_pay']:,} so'm\n\n"

    await update.message.reply_text(response)

async def calculate_full_salary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await calculate_salary(update, context, days_limit=None)

async def calculate_15_days_salary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await calculate_salary(update, context, days_limit=15)

async def export_salary_excel(update: Update, context: ContextTypes.DEFAULT_TYPE, days_limit=None):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("Kechirasiz, bu buyruq faqat rahbar uchun! ❌")
        return

    data = get_calculated_salary_data(days_limit)
    if not data:
        await update.message.reply_text("Bazada eksport qilish uchun ma'lumot yo'q.")
        return

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Oylik Hisoboti"

    ws.append(["Xodim ID", "Xodim Ismi", "Ishlagan vaqti", "Soatlik Stavka (so'm)", "Hisoblangan Oylik (so'm)"])
    for item in data:
        time_str = f"{item['hours']} soat {item['minutes']} daqiqa"
        ws.append([item['user_id'], item['name'], time_str, item['hourly_rate'], item['total_pay']])

    file_name = "Oylik_Hisoboti_15kun.xlsx" if days_limit else "Oylik_Hisoboti_Toliq.xlsx"
    wb.save(file_name)

    caption_text = f"📊 Oxirgi {days_limit} kunlik oylik hisoboti Excel faylda!" if days_limit else "📊 Barcha davr uchun oylik hisoboti Excel faylda!"
    with open(file_name, "rb") as file:
        await update.message.reply_document(document=file, filename=file_name, caption=caption_text)

async def export_full_salary_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await export_salary_excel(update, context, days_limit=None)

async def export_15_salary_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await export_salary_excel(update, context, days_limit=15)

async def export_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("Kechirasiz, bu buyruq faqat rahbar uchun! ❌")
        return

    cursor.execute("SELECT user_id, user_name, action, date_time FROM attendance ORDER BY date_time ASC")
    records = cursor.fetchall()

    if not records:
        await update.message.reply_text("Bazada yuklash uchun ma'lumot yo'q.")
        return

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Davomat"

    ws.append(["Xodim ID", "Xodim Ismi", "Harakat", "Sana va Vaqt"])
    for row in records:
        ws.append(row)

    file_name = "Davomat_Hisoboti.xlsx"
    wb.save(file_name)

    with open(file_name, "rb") as info_file:
        await update.message.reply_document(document=info_file, filename=file_name, caption="📊 Davomat hisoboti Excel faylda!")

app = Application.builder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin_panel))
app.add_handler(CommandHandler("excel", export_excel))
app.add_handler(CommandHandler("oylik", calculate_full_salary))
app.add_handler(CommandHandler("15kun", calculate_15_days_salary))
app.add_handler(CommandHandler("oylikexcel", export_full_salary_excel))
app.add_handler(CommandHandler("15kunexcel", export_15_salary_excel))
app.add_handler(CommandHandler("stavka", set_rate))

app.add_handler(CallbackQueryHandler(button_click))
app.add_handler(MessageHandler(filters.VIDEO_NOTE, handle_video_note))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

print("Bot ishga tushdi...")
app.run_polling()
        
