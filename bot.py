import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest
from openai import OpenAI

# ================= НАСТРОЙКИ =================
# Токен Telegram: сначала ищем TELEGRAM_TOKEN, если нет — берём BOT_TOKEN (авто-переменная BotHost)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("BOT_TOKEN")

# Ключ OpenRouter (добавьте вручную в переменные окружения BotHost)
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY")

# Бесплатная модель DeepSeek через OpenRouter
MODEL_NAME = "deepseek/deepseek-r1:free"

# Проверка, что ключи вообще есть
if not TELEGRAM_TOKEN:
    raise ValueError("Не найден TELEGRAM_TOKEN или BOT_TOKEN в переменных окружения!")
if not OPENROUTER_KEY:
    raise ValueError("Не найден OPENROUTER_KEY в переменных окружения!")
# =============================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# Клиент OpenRouter (совместим с форматом OpenAI)
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_KEY,
)

# Системный промпт таролога
SYSTEM_PROMPT = """
Ты — опытный таролог, работающий с колодой Райдера-Уэйта. Пользователь описывает ситуацию или задаёт вопрос.

Твой ответ должен строго следовать структуре:

1. **Вытянутые карты**: случайным образом выбери 3 карты из 78 карт колоды. Напиши их названия и положение (прямое/перевёрнутое). Пример:
   «Выпавшие карты: **Отшельник (прямое)**, **Тройка Мечей (перевёрнутое)**, **Звезда (прямое)**.»

2. **Толкование каждой карты**: для каждой карты напиши отдельный абзац, начиная с её названия. Толкование должно быть привязано к ситуации пользователя, конкретным и глубоким, без общих фраз.

3. **Общий итог**: 2–3 предложения о том, как карты связаны между собой, и мягкий, практичный совет.

Ограничения:
- Не давай медицинских, юридических или финансовых советов.
- Даже «плохие» карты трактуй через призму роста, не пугай пользователя.
- Тон — тёплый, вдумчивый, как у доверенного советчика.
- Не объясняй правила таро и не описывай процесс вытягивания карт — сразу переходи к делу.
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
    await update.message.reply_text(
        "🔮 Здравствуйте, я ваш таролог.\n\n"
        "Опишите вашу ситуацию или задайте вопрос — я вытяну три карты и дам толкование."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка обычного текстового сообщения"""
    user_text = update.message.text

    # Сообщение-заглушка, чтобы пользователь видел, что бот работает
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

        # Удаляем сообщение-заглушку
        await wait_msg.delete()

        # Telegram ограничивает длину одного сообщения — делим на части при необходимости
        if len(reply_text) > 4000:
            for i in range(0, len(reply_text), 4000):
                await update.message.reply_text(reply_text[i:i+4000])
        else:
            await update.message.reply_text(reply_text)

    except Exception as e:
        logging.error(f"Ошибка при вызове AI: {e}")
        await wait_msg.edit_text(
            "⚠️ Не удалось вытянуть карты. Попробуйте ещё раз через минуту.\n"
            "（Возможно, временный лимит бесплатной модели）"
        )

def main():
    # Настройка таймаутов, чтобы бот не падал с ошибкой TimedOut на хостинге
    request = HTTPXRequest(
        connect_timeout=30.0,   # ждать соединения до 30 секунд
        read_timeout=30.0,      # ждать ответа до 30 секунд
        write_timeout=30.0,
    )

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).request(request).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logging.info("Таро-бот запущен…")
    app.run_polling()

if __name__ == "__main__":
    main()
