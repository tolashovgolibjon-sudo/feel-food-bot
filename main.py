import os
import openpyxl
from flask import Flask
from threading import Thread
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Token va Admin ID sozlamalari
TOKEN = "8767402192:AAGQJDclo-kPeufBD1VqXWkXzd7keV2i86c"
ADMIN_ID = 1631414170  # O'zingizning rahbar ID raqamingizni yozing (agar boshqacha bo'lsa)

# ==========================================
# 1. FLASK VEB-SERVER QISMI (UptimeRobot uchun 24/7)
# ==========================================
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "Bot faol va ishlamoqda!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)  # To'g'irlandi: app_flask ishlatildi

def keep_alive():
    t = Thread(target=run)
    t.start()


# ==========================================
# 2. BOTNING ASOSIY FUNKSIYALARI VA EXCEL
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Assalomu alaykum! Bot 24/7 rejimida ishlamoqda.")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def calculate_full_salary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def calculate_15_days_salary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def set_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def handle_video_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

# Oylik hisobotini Excelga chiqarish funksiyalari
async def export_salary_excel(update: Update, context: ContextTypes.DEFAULT_TYPE, days_limit=None):
    # Bu yerda ma'lumotlar bazadan olinadi (data o'zgaruvchisi)
    data = [] # O'zingizdagi data so'rovini shu yerga yozasiz
    
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

    # cursor.execute(...) orqali bazadan olish qismi
    records = [] 

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
        await update.message.reply_document(document=file, filename=file_name, caption="📊 Davomat hisoboti Excel faylda!")


# ==========================================
# 3. ASOSIY ISHGA TUSHIRISH (MAIN)
# ==========================================
if __name__ == "__main__":
    # 1. Telegram bot ilovasini yaratish va handlerlarni ulash
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

    # 2. Flask veb-serverini orqa fonda (fon rejimida) ishga tushiramiz
    keep_alive()

    print("Bot ishga tushdi...")
    
    # 3. Telegram botni ishga tushiramiz
    app.run_polling()
        
