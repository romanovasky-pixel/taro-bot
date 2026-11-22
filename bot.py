import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest
from openai import OpenAI

# ================= НАСТРОЙКИ =================
# Токен вписан прямо в код (как вы просили)
TELEGRAM_TOKEN = "9027099521:AAEKoWCW0RnlCBE3cIOF8qJYbCYIej2D24A"

# Ключ OpenRouter (оставляем через переменную, чтобы не светить в коде)
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY")

# Бесплатная модель DeepSeek через OpenRouter
MODEL_NAME = "deepseek/deepseek-r1:free"

if not OPENROUTER_KEY:
    raise ValueError("Не найден OPENROUTER_KEY в переменных окружения!")
# =============================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_KEY,
)

SYSTEM_PROMPT = """
Ты — опытный таролог, работающий с колодой Райдера-Уэйта. Пользователь описывает ситуацию или задаёт вопрос.
Твой ответ должен строго следовать структуре:
1. **Вытянутые карты**: случайным образом выбери 3 карты из 78 карт колоды. Напиши их названия и положение.
2. **Толкование каждой карты**: для каждой карты напиши отдельный абзац.
3. **Общий итог**: 2–3 предложения.
Ограничения: не давай медицинских, юридических или финансовых советов. Тон — тёплый и вдумчивый.
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔮 Здравствуйте, я ваш таролог.\n\n"
        "Опишите вашу ситуацию или задайте вопрос — я вытяну три карты и дам толкование."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    wait_msg = await update.message.reply_text("🃏 Тасую колоду и вытягиваю карты…")

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ],
            temperature=0.8,
            max_tokens=1200,
        )
        reply_text = response.choices[0].message.content
        await wait_msg.delete()
        
        if len(reply_text) > 4000:
            for i in range(0, len(reply_text), 4000):
                await update.message.reply_text(reply_text[i:i+4000])
        else:
            await update.message.reply_text(reply_text)

    except Exception as e:
        logging.error(f"Ошибка при вызове AI: {e}")
        await wait_msg.edit_text("⚠️ Не удалось вытянуть карты. Попробуйте ещё раз через минуту.")

def main():
    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
    )
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).request(request).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logging.info("Таро-бот запущен…")
    app.run_polling()

if __name__ == "__main__":
    main()
