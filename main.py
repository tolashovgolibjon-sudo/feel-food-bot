import os
import logging
import sqlite3
import math
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from flask import Flask
from threading import Thread

# Logging sozlamalari
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Token va Admin ID lari
TOKEN = "8767402192:AAF0TKS5Yc-S3W7SrxRCq7QQd9HHFft5GJI", "SIZNING_TOKENINGIZNI_SHU_YERga_YOZING")
ADMIN_IDS = [1631414170]  # Sizning Telegram ID raqamingiz

# O'zbekiston vaqt zonasi (UTC+5)
UZB_TIMEZONE = timezone(timedelta(hours=5))

# Ofis koordinatalari (Siz yuborgan aniq koordinatalar)
OFFICE_LAT = 41.003753  
OFFICE_LON = 71.672794  
MAX_DISTANCE_METERS = 200  # Ofisdan ruxsat etilgan maksimal masofa (metrda)

# Ma'lumotlar bazasini yaratish (SQLite)
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS employees (
            id TEXT PRIMARY KEY,
            name TEXT,
            rate REAL DEFAULT 0,
            hours REAL DEFAULT 0,
            check_in_time TEXT DEFAULT NULL,
            awaiting_location INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

# GPS masofani hisoblash (Haversine formulasi)
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000  # Yer radiusi metrda
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# Flask server (Render 24/7 ishlashi uchun)
web_app = Flask("")

@web_app.route("/")
def home():
    return "Bot ishlayapti!"

def run_web():
    web_app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Salom! Bu GPS va davomat nazoratli ish haqi bot.\n\n"
        "📋 **Admin buyruqlari:**\n"
        "/qosh [ID] [Ism] - Xodim qo'shish\n"
        "/ochir [ID] - Xodimni ishdan bo'shatish\n"
        "/stavka [ID] [Summa] - Soatlik stavka belgilash\n"
        "/xodimlar - Xodimlar ro'yxatini ko'rish\n"
        "/reset - Soatlarni nollash\n"
        "/excel - Maxfiy hisobotni shaxsiy chatga olish"
    )

async def add_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Kechirasiz, bu buyruqni faqat admin ishlata oladi!")
        return
    try:
        args = context.args
        emp_id = args[0]
        emp_name = " ".join(args[1:])
        
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO employees (id, name, rate, hours, check_in_time, awaiting_location) VALUES (?, ?, 0, 0, NULL, 0)", (emp_id, emp_name))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ Xodim muvaffaqiyatli qo'shildi:\n🆔 ID: {emp_id}\n👤 Ism: {emp_name}")
    except Exception as e:
        await update.message.reply_text("❌ Xatolik! Foydalanish: /qosh [ID] [Ism]")

async def remove_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Kechirasiz, bu buyruqni faqat admin ishlata oladi!")
        return
    try:
        args = context.args
        emp_id = args[0]
        
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM employees WHERE id = ?", (emp_id,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        if deleted > 0:
            await update.message.reply_text(f"✅ Xodim (ID: {emp_id}) ro'yxatdan o'chirildi!")
        else:
            await update.message.reply_text("❌ Bunday ID raqamdagi xodim topilmadi!")
    except Exception as e:
        await update.message.reply_text("❌ Xatolik! Foydalanish: /ochir [ID]")

async def set_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Kechirasiz, bu buyruqni faqat admin ishlata oladi!")
        return
    try:
        args = context.args
        emp_id = args[0]
        rate = float(args[1])
        
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE employees SET rate = ? WHERE id = ?", (rate, emp_id))
        updated = cursor.rowcount
        conn.commit()
        conn.close()
        
        if updated > 0:
            await update.message.reply_text(f"✅ Xodim (ID: {emp_id}) uchun soatlik stavka: {rate:,.0f} so'm etib belgilandi!")
        else:
            await update.message.reply_text("❌ Bunday ID raqamdagi xodim topilmadi!")
    except Exception as e:
        await update.message.reply_text("❌ Xatolik! Foydalanish: /stavka [ID] [Summa]")

async def list_employees(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun!")
        return
    
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, rate, hours FROM employees")
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        await update.message.reply_text("📊 Hozircha xodimlar ro'yxati bo'sh.")
        return
        
    text = "👥 **Xodimlar ro'yxati va hisobi:**\n\n"
    for r in rows:
        salary = r[2] * r[3]
        text += f"🆔 ID: {r[0]}\n👤 Ism: {r[1]}\n💰 Stavka: {r[2]:,.0f} so'm/soat\n⏳ Ishlagan soati: {r[3]:.2f} soat\n💵 Hisoblangan oylik: {salary:,.0f} so'm\n-------------------\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def reset_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun!")
        return
    
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE employees SET hours = 0, check_in_time = NULL, awaiting_location = 0")
    conn.commit()
    conn.close()
    await update.message.reply_text("🔄 Barcha xodimlarning ishlagan soatlari nollashtirildi.")

async def handle_video_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("Keldim 🟢", callback_data="keldim"),
            InlineKeyboardButton("Kettim 🔴", callback_data="kettim")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Davomat uchun quyidagi tugmani bosing:", reply_markup=reply_markup)

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name, rate, hours, check_in_time FROM employees WHERE id = ?", (user_id,))
    emp = cursor.fetchone()
    
    if not emp:
        conn.close()
        await query.edit_message_text("❌ Siz xodimlar ro'yxatida emassiz yoki ID raqamingiz mos kelmadi.")
        return
        
    name, rate, hours, check_in_time = emp
    
    if query.data == "keldim":
        if check_in_time:
            conn.close()
            await query.edit_message_text(f"⚠️ Siz allaqachon kelganingizni qayd etgansiz!\n⏰ Vaqt: {check_in_time}")
            return
            
        # GPS lokatsiyani kuta boshlash
        cursor.execute("UPDATE employees SET awaiting_location = 1 WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        
        # Lokatsiya so'rash uchun maxsus tugma
        location_keyboard = [[KeyboardButton("📍 GPS Lokatsiyani yuborish", request_location=True)]]
        reply_markup = ReplyKeyboardMarkup(location_keyboard, resize_keyboard=True, one_time_keyboard=True)
        
        await query.message.reply_text(
            f"📍 {name}, ish joyida ekanligingizni tasdiqlash uchun pastdagi tugmani bosing va **GPS lokatsiyangizni** yuboring:",
            reply_markup=reply_markup
        )
        await query.edit_message_text("✅ Davomat so'rovi qabul qilindi. Iltimos, lokatsiyani yuboring.")
        
    elif query.data == "kettim":
        if not check_in_time:
            conn.close()
            await query.edit_message_text("⚠️ Siz hali 'Keldim' deb qayd etmagansiz!")
            return
            
        current_time = datetime.now(UZB_TIMEZONE)
        current_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
        check_in_dt = datetime.fromisoformat(check_in_time)
        diff_hours = (current_time - check_in_dt).total_seconds() / 3600.0
        new_hours = hours + diff_hours
        
        cursor.execute("UPDATE employees SET hours = ?, check_in_time = NULL, awaiting_location = 0 WHERE id = ?", (new_hours, user_id))
        conn.commit()
        conn.close()
        
        await query.edit_message_text(
            f"🔴 Ketganingiz qayd etildi, {name}!\n"
            f"⏰ Vaqt: {current_time_str}\n"
            f"⏳ Bu smenada: {diff_hours:.2f} soat\n"
            f"📊 Jami ishlangan: {new_hours:.2f} soat"
        )

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name, awaiting_location FROM employees WHERE id = ?", (user_id,))
    emp = cursor.fetchone()
    
    if not emp or emp[1] != 1:
        conn.close()
        return
        
    name, awaiting = emp
    user_location = update.message.location
    
    if not user_location:
        conn.close()
        await update.message.reply_text("❌ Iltimos, lokatsiyani to'g'ri yuboring!")
        return
        
    user_lat = user_location.latitude
    user_lon = user_location.longitude
    
    # Masofani hisoblash (metrda)
    distance = calculate_distance(user_lat, user_lon, OFFICE_LAT, OFFICE_LON)
    
    if distance <= MAX_DISTANCE_METERS:
        current_time = datetime.now(UZB_TIMEZONE)
        current_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute("UPDATE employees SET check_in_time = ?, awaiting_location = 0 WHERE id = ?", (current_time.isoformat(), user_id))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"✅ Tabriklaymiz, {name}! Ofisga yaqin ekansiz (Masofa: {distance:.0f} metr).\n"
            f"🟢 Kelgan vaqtingiz qayd etildi: {current_time_str}",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        conn.close()
        await update.message.reply_text(
            f"❌ Xatolik! Siz ofisdan juda uzoqdasiz.\n"
            f"📍 Masofa: {distance:.0f} metr (Ruxsat etilgan limit: {MAX_DISTANCE_METERS} metr).\n"
            f"Iltimos, ish joyiga yaqinroq kelib qayta urinib ko'ring.",
            reply_markup=ReplyKeyboardRemove()
        )

async def export_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun!")
        return
    
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, rate, hours FROM employees")
    rows = cursor.fetchall()
    conn.close()
    
    report = "📊 **Xodimlar davomat va ish haqi yakuniy hisoboti:**\n\n"
    if not rows:
        report += "Hozircha xodimlar ma'lumotlari mavjud emas."
    else:
        total_payout = 0
        for r in rows:
            salary = r[2] * r[3]
            total_payout += salary
            report += f"🆔 ID: {r[0]}\n👤 Ism: {r[1]}\n💰 Stavka: {r[2]:,.0f} so'm\n⏳ Soat: {r[3]:.2f}\n💵 Oylik: {salary:,.0f} so'm\n-------------------\n"
        report += f"\n💎 **Jami to'lanishi kerak:** {total_payout:,.0f} so'm"
    
    try:
        await context.bot.send_message(chat_id=ADMIN_IDS[0], text=report, parse_mode="Markdown")
        await update.message.reply_text("✅ Maxfiy hisobot shaxsiy chatingizga yuborildi!")
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik yuz berdi: {e}")

if __name__ == "__main__":
    init_db()
    keep_alive()
    
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("qosh", add_employee))
    app.add_handler(CommandHandler("ochir", remove_employee))
    app.add_handler(CommandHandler("stavka", set_rate))
    app.add_handler(CommandHandler("xodimlar", list_employees))
    app.add_handler(CommandHandler("reset", reset_hours))
    app.add_handler(CommandHandler("excel", export_excel))
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(MessageHandler(filters.VIDEO_NOTE | filters.VIDEO, handle_video_note))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))

    print("Bot muvaffaqiyatli ishga tushdi...")
    app.run_polling(allowed_updates=["message", "edited_message", "callback_query"])
    
