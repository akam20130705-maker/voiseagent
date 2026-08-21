import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from duckduckgo_search import DDGS
from openai import OpenAI
from dotenv import load_dotenv

# .env fayldan kalitlarni yuklash
load_dotenv()

# Log sozlamalari
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Kalitlarni o'qish
TELEGRAM_TOKEN = os.getenv("8951160061:AAGDox68ulAFgbHyMsKtLO7uFDENpCnoIUY")
OPENAI_API_KEY = os.getenv("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") # Bu Whisper uchun ishlatiladi
OPENROUTER_API_KEY = os.getenv("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") # Bu miya (LLM) uchun

# 1. Ovozni tanish uchun OpenAI (Whisper) klienti
whisper_client = None
if OPENAI_API_KEY:
    whisper_client = OpenAI(api_key=OPENAI_API_KEY)
else:
    logging.warning("⚠️ OpenAI API key topilmadi. Ovozli xabarlar ishlamaydi.")

# 2. Mantiq va Xulosa uchun OpenRouter klienti
brain_client = None
if OPENROUTER_API_KEY:
    # OpenRouter OpenAI kutubxonasi bilan ishlaydi, faqat base_url o'zgaradi
    brain_client = OpenAI(
        api_key=,
        base_url="https://openrouter.ai/api/v1"
    )
    logging.info("✅ OpenRouter muvaffaqiyatli ulandi.")
else:
    logging.error("❌ OpenRouter API key topilmadi! Bot mantiqiy qismi ishlamaydi.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Salom! Men sizning Aqlli Web Agentingizman (OpenRouter + Llama-3). 🤖\n"
        "Menga matn yoki ovozli xabar yuboring, men internetdan qidirib, javob beraman."
    )

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not whisper_client:
        await update.message.reply_text("❌ Xato: OpenAI API kaliti sozlanmagan. Ovozni taniy olmayman.")
        return

    file = await update.message.voice.get_file()
    file_path = "voice.ogg"
    await file.download_to_drive(file_path)

    try:
        with open(file_path, "rb") as audio_file:
            transcription = whisper_client.audio.transcriptions.create(
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
            for r in ddgs.text(query, max_results=5):
                results.append(f"• {r['title']}\n  {r['body']}")
        return "\n\n".join(results) if results else "Hech qanday natija topilmadi."
    except Exception as e:
        return f"Qidiruvda xatolik: {str(e)}"

async def generate_summary(query, search_results):
    """OpenRouter (Llama-3) yordamida qisqa xulosa"""
    
    if not brain_client:
        return "⚠️ OpenRouter API kaliti yo'q. Xulosa qilish mumkin emas.\n\nRaw ma'lumotlar:\n" + search_results

    prompt = f"""
    Sen foydali yordamchisan. Javoblarni faqat O'ZBEK tilida ber.
    
    Foydalanuvchi savoli: {query}
    
    Internetdan olingan ma'lumotlar:
    {search_results}
    
    Vazifa: Ushbu ma'lumotlarga asoslanib, foydalanuvchiga qisqa, aniq va tushunarli javob yoz. 
    Manbalarni sanab o'tma, shunchaki faktlarni jamlab ber.
    """
    
    try:
        response = brain_client.chat.completions.create(
            model="meta-llama/llama-3-70b-instruct", # Eng zo'r ochiq model
            messages=[
                {"role": "system", "content": "Sen o'zbek tilida gapiruvchi aqlli yordamchisan."},
                {"role": "user", "content": prompt}
            ],
            # OpenRouter uchun maxsus header (ixtiyoriy, lekin foydali)
            extra_headers={
                "HTTP-Referer": "https://github.com/sizning_username/voice-agent-bot", 
                "X-Title": "Voice Web Agent",
            }
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI xulosada xatolik: {str(e)}"

async def process_query(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str):
    status_msg = await update.message.reply_text("🔍 Internetdan qidiryapman...")
    
    try:
        search_results = await search_web(query)
        await status_msg.edit_text("🧠 Ma'lumotlarni tahlil qilyapman (Llama-3)...")
        final_answer = await generate_summary(query, search_results)
        
        if len(final_answer) > 4000:
            final_answer = final_answer[:4000] + "... (davomi bor)"
            
        await status_msg.edit_text(final_answer)
    except Exception as e:
        await status_msg.edit_text(f"❌ Jarayonda xatolik: {str(e)}")

if __name__ == '__main__':
    if not TELEGRAM_TOKEN:
        print("❌ XATO: TELEGRAM_TOKEN topilmadi!")
        exit(1)

    print("✅ Bot ishga tushmoqda...")
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    application.run_polling()
