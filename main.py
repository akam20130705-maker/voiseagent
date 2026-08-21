import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from duckduckgo_search import DDGS
from openai import OpenAI
import google.generativeai as genai
from dotenv import load_dotenv

# .env fayldan kalitlarni yuklash
load_dotenv()

# Log sozlamalari
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Kalitlarni o'qish
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# API klientlarni sozlash
openai_client = None
gemini_model = None

if OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
else:
    logging.warning("OpenAI API key topilmadi. Ovozli xabarlar ishlamaydi.")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-pro')
else:
    logging.warning("Gemini API key topilmadi. AI xulosa ishlamaydi.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Salom! Men sizning Aqlli Web Agentingizman. 🤖\n"
        "Menga matn yoki ovozli xabar yuboring, men internetdan qidirib, javob beraman."
    )

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not openai_client:
        await update.message.reply_text("❌ Xato: OpenAI API kaliti sozlanmagan. Ovozni taniy olmayman.")
        return

    file = await update.message.voice.get_file()
    file_path = "voice.ogg"
    await file.download_to_drive(file_path)

    try:
        with open(file_path, "rb") as audio_file:
            transcription = openai_client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file
            )
        user_query = transcription.text
        await update.message.reply_text(f"🎤 Siz dedingiz: _{user_query}_", parse_mode='Markdown')
        await process_query(update, context, user_query)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ovozni taniashda xatolik: {str(e)}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_query = update.message.text
    await process_query(update, context, user_query)

async def search_web(query):
    """DuckDuckGo orqali qidiruv"""
    try:
        results = []
        with DDGS() as ddgs:
            # MaxResults 5 ta
            for r in ddgs.text(query, max_results=5):
                results.append(f"• {r['title']}\n  {r['body']}")
        return "\n\n".join(results) if results else "Hech qanday natija topilmadi."
    except Exception as e:
        return f"Qidiruvda xatolik: {str(e)}"

async def generate_summary(query, search_results):
    """AI yordamida qisqa xulosa"""
    prompt = f"""
    Foydalanuvchi savoli: {query}
    
    Internetdan olingan ma'lumotlar:
    {search_results}
    
    Vazifa: Ushbu ma'lumotlarga asoslanib, foydalanuvchiga O'ZBEK tilida qisqa, aniq va tushunarli javob yoz. 
    Faqat faktlarni bayon qil, ortiqcha so'zlarni ishlatma.
    """
    
    if gemini_model:
        try:
            response = gemini_model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"AI xulosada xatolik: {str(e)}"
    else:
        return "⚠️ Gemini API kaliti yo'q. Xulosa qilish mumkin emas.\n\nRaw ma'lumotlar:\n" + search_results

async def process_query(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str):
    status_msg = await update.message.reply_text("🔍 Internetdan qidiryapman...")
    
    try:
        search_results = await search_web(query)
        await status_msg.edit_text("🧠 Ma'lumotlarni tahlil qilyapman...")
        final_answer = await generate_summary(query, search_results)
        
        # Agar javob juda uzun bo'lsa, Telegram chekloviga moslash
        if len(final_answer) > 4000:
            final_answer = final_answer[:4000] + "... (davomi bor)"
            
        await status_msg.edit_text(final_answer)
    except Exception as e:
        await status_msg.edit_text(f"❌ Jarayonda xatolik yuz berdi: {str(e)}")

if __name__ == '__main__':
    if not TELEGRAM_TOKEN:
        print("❌ XATO: TELEGRAM_TOKEN topilmadi! Iltimos, Secrets (.env) ni tekshiring.")
        exit(1)

    print("✅ Bot ishga tushmoqda...")
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    application.run_polling()
