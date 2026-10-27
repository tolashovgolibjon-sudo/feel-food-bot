import os
import math
import sqlite3
import datetime
import pytz
from io import BytesIO
import openpyxl
from flask import Flask, render_template_string
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
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
TOKEN = "8767402192:AAFBJRCO-HzCdBfp5rAamvClQwWPwT78GR4"
ADMIN_TELEGRAM_ID = 1631414170  # Bosh admin ID raqami

OFFICE_LAT = 41.003753
OFFICE_LON = 71.672794
MAX_DISTANCE_METERS = 150

UZB_TZ = pytz.timezone("Asia/Tashkent")
DB_FILE = "attendance.db"

# Render'dagi tashqi URL manzilingiz (avtomatik aniqlanadi yoki Render bergan nomni yozasiz)
# Masalan: https://feel-food-bot-2.onrender.com
WEB_APP_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://feel-food-bot-2.onrender.com")

# ---------------------------------------------------------
# 2. FLASK SERVER (Web App va 24/7 uchun)
# ---------------------------------------------------------
web_app = Flask('')

@web_app.route('/')
def home():
    return "Bot 24/7 va Web App rejimida ishlamoqda!"

@web_app.route('/geo')
def geo_page():
    # Xodim tugmani bosganda ochiladigan va GPS oladigan mikro-sahifa
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Lokatsiyani aniqlash</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            body { font-family: sans-serif; text-align: center; padding-top: 50px; background: #f4f4f9; }
            h3 { color: #333; }
            .loader { border: 5px solid #f3f3f3; border-top: 5px solid #3498db; border-radius: 50%; width: 50px; height: 50px; animation: spin 1s linear infinite; margin: 20px auto; }
            @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        </style>
    </head>
    <body>
        <h3>📍 Geolokatsiyangiz aniqlanmoqda...</h3>
        <p>Iltimos, GPS ruxsatini bering va biroz kuting.</p>
        <div class="loader"></div>
        <script>
            let tg = window.Telegram.WebApp;
            tg.expand();
            
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(function(position) {
                    let lat = position.coords.latitude;
                    let lon = position.coords.longitude;
                    // Ma'lumotni botga yuboramiz
                    tg.sendData(lat + "," + lon);
                }, function(error) {
                    alert("GPS xatosi: Lokatsiyaga ruxsat berilmadi yoki GPS o'chiq!");
                    tg.close();
                }, { timeout: 10000, enableHighAccuracy: true });
            } else {
                alert("Brauzeringiz geolakatsiyani qo'llab-quvvatlamaydi.");
                tg.close();
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html_content)

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# ---------------------------------------------------------
# 3. BAZANI YARATISH
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS employees (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            shift_rate REAL DEFAULT 0,
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
# 6. VIDEO KELGANDA WEB APP TUGMALARNI CHIQARISH
# ---------------------------------------------------------
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Web App orqali ishlaydigan tugmalar (guruhning o'zida ochiladi)
    keyboard = [
        [
            InlineKeyboardButton("🟢 Keldim (GPS)", web_app=WebAppInfo(url=f"{WEB_APP_URL}/geo")),
            InlineKeyboardButton("🔴 Ketdim (GPS)", web_app=WebAppInfo(url=f"{WEB_APP_URL}/geo"))
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

# ---------------------------------------------------------
# 7. WEB APP ORQALI KELGAN GPS MA'LUMOTINI QABUL QILISH VA TEKSHIRISH
# ---------------------------------------------------------
async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name
    
    try:
        data_str = update.message.web_app_data.data  # "lat,lon" ko'rinishida keladi
        lat_str, lon_str = data_str.split(",")
        user_lat = float(lat_str)
        user_lon = float(lon_str)
    except Exception as e:
        await update.message.reply_text(f"❌ Geolokatsiyani o'qishda xatolik yuz berdi.")
        return

    dist = calculate_distance(user_lat, user_lon, OFFICE_LAT, OFFICE_LON)

    if dist > MAX_DISTANCE_METERS:
        await update.message.reply_text(
            f"🚫 **Xavfsizlik ogohlantirishi:** {user_name}, siz ofis hududida emassiz!\n"
            f"Masofa: {int(dist)} metr (Ruxsat: {MAX_DISTANCE_METERS} m).",
            parse_mode="Markdown"
        )
        return

    now_uzb = datetime.datetime.now(UZB_TZ)
    today_str = now_uzb.strftime("%Y-%m-%d")
    time_str = now_uzb.strftime("%H:%M:%S")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Xodim bazada bormi tekshiramiz, yo'q bo'lsa avtomatik qo'shamiz
    cursor.execute("SELECT shift_rate, shift_hours FROM employees WHERE user_id = ?", (user_id,))
    emp_data = cursor.fetchone()
    
    if not emp_data:
        cursor.execute(
            "INSERT OR IGNORE INTO employees (user_id, full_name, shift_rate, shift_hours, is_admin) VALUES (?, ?, 0, 12, 0)",
            (user_id, user_name)
        )
        conn.commit()
        shift_rate = 0.0
        shift_hours = 12
    else:
        shift_rate = emp_data[0]
        shift_hours = emp_data[1]

    # Qaysi tugma bosilganligini aniqlash uchun oddiy mantiq:
    # Agar bugun kelmagan bo'lsa - Keldim, kelgan bo'lsa - Ketdim deb yozamiz
    cursor.execute("SELECT id, check_in, check_out FROM attendance WHERE user_id = ? AND date = ?", (user_id, today_str))
    row = cursor.fetchone()

    if not row:
        # Hali kelmagan -> "Keldim" deb yozamiz
        cursor.execute("INSERT INTO attendance (user_id, date, check_in) VALUES (?, ?, ?)", (user_id, today_str, time_str))
        conn.commit()
        await update.message.reply_text(f"✅ {user_name}, ishga kelgan vaqtingiz muvaffaqiyatli qayd etildi: {time_str} 🟢 (Masofa: {int(dist)}m)")
    else:
        att_id, check_in_str, check_out_str = row
        if not check_out_str:
            # Kelgan, lekin ketmagan -> "Ketdim" deb yozamiz
            check_in_dt = UZB_TZ.localize(datetime.datetime.strptime(f"{today_str} {check_in_str}", "%Y-%m-%d %H:%M:%S"))
            duration = (now_uzb - check_in_dt).total_seconds() / 3600.0
            earned = shift_rate

            cursor.execute(
                "UPDATE attendance SET check_out = ?, hours_worked = ?, earned_money = ? WHERE id = ?",
                (time_str, round(duration, 2), earned, att_id)
            )
            conn.commit()
            
            if shift_rate == 0:
                await update.message.reply_text(
                    f"🔴 {user_name}, ishdan ketgan vaqtingiz qayd etildi: {time_str}\n"
                    f"⚠️ Diqqat: Sizga hali admin tomonidan stavka belgilanmagan!"
                )
            else:
                await update.message.reply_text(
                    f"🔴 {user_name}, ishdan ketgan vaqtingiz qayd etildi: {time_str}\n"
                    f"⏱ Smena vaqti: {shift_hours} soatlik\n"
                    f"💰 Hisoblangan smena haqi: {earned:,.0f} so'm"
                )
        else:
            await update.message.reply_text(f"⚠️ {user_name}, siz bugungi smenani allaqachon yakunlagansiz!")

    conn.close()

# ---------------------------------------------------------
# 8. EXCEL HISOBOTLAR
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
    app.add_handler(MessageHandler(filters.VIDEO | filters.VIDEO_NOTE, handle_video))
    
    # Web App orqali kelgan ma'lumotni ushlash uchun:
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))

    print("🛡️ Bot Web App rejimida muvaffaqiyatli ishga tushdi!")
    app.run_polling(drop_pending_updates=True, close_loop=False)
    
