import os
import random
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes,
)
from telegram.request import HTTPXRequest
from openai import OpenAI, RateLimitError, APIError

# ================= НАСТРОЙКИ =================
TELEGRAM_TOKEN = "9027099521:AAEKoWCW0RnlCBE3cIOF8qJYbCYIej2D24A"
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY")
MODEL_NAME = "deepseek/deepseek-r1:free"

if not OPENROUTER_KEY:
    raise ValueError("Не найден OPENROUTER_KEY в переменных окружения!")
# =============================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
# Не логируем URL запросов httpx — там может быть токен бота
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_KEY,
)

# ================= КОЛОДА (78 карт) =================
MAJOR = [
    "Шут", "Маг", "Верховная Жрица", "Императрица", "Император",
    "Иерофант", "Влюблённые", "Колесница", "Сила", "Отшельник",
    "Колесо Фортуны", "Справедливость", "Повешенный", "Смерть",
    "Умеренность", "Дьявол", "Башня", "Звезда", "Луна", "Солнце",
    "Суд", "Мир",
]
SUITS = {
    "Жезлы": ["Туз", "Двойка", "Тройка", "Четвёрка", "Пятёрка", "Шестёрка",
              "Семёрка", "Восьмёрка", "Девятка", "Десятка", "Паж", "Рыцарь",
              "Королева", "Король"],
    "Кубки": ["Туз", "Двойка", "Тройка", "Четвёрка", "Пятёрка", "Шестёрка",
              "Семёрка", "Восьмёрка", "Девятка", "Десятка", "Паж", "Рыцарь",
              "Королева", "Король"],
    "Мечи": ["Туз", "Двойка", "Тройка", "Четвёрка", "Пятёрка", "Шестёрка",
             "Семёрка", "Восьмёрка", "Девятка", "Десятка", "Паж", "Рыцарь",
             "Королева", "Король"],
    "Пентакли": ["Туз", "Двойка", "Тройка", "Четвёрка", "Пятёрка", "Шестёрка",
                 "Семёрка", "Восьмёрка", "Девятка", "Десятка", "Паж", "Рыцарь",
                 "Королева", "Король"],
}
DECK = MAJOR + [f"{rank} {suit}" for suit, ranks in SUITS.items() for rank in ranks]

POSITIONS = ["прошлое", "настоящее", "будущее"]

def draw_cards() -> str:
    picked = random.sample(DECK, 3)
    lines = []
    for card, pos in zip(picked, POSITIONS):
        orientation = random.choice(["прямое", "перевёрнутое"])
        lines.append(f"- {card} ({pos}, {orientation} положение)")
    return "\n".join(lines)

# ================= ПРОМПТ =================
SYSTEM_PROMPT = """
Ты — опытный таролог, работающий с колодой Райдера-Уэйта. Пользователь описывает ситуацию или задаёт вопрос.
Тебе уже даны три вытянутые карты с их положением — НЕ придумывай свои, работай только с ними.
Твой ответ должен строго следовать структуре:
1. **Вытянутые карты**: перечисли карты ровно так, как они даны.
2. **Толкование каждой карты**: для каждой карты напиши отдельный абзац в контексте вопроса.
3. **Общий итог**: 2–3 предложения.
Ограничения: не давай медицинских, юридических или финансовых советов. Тон — тёплый и вдумчивый.
Не используй markdown-разметку (звёздочки, решётки) — пиши обычным текстом.
"""

# ================= УТИЛИТЫ =================
def split_text(text: str, limit: int = 4000) -> list[str]:
    """Разбивает текст по абзацам/переносам, не рвя слова."""
    parts = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut == -1:
            cut = text.rfind(" ", 0, limit)
        if cut == -1:
            cut = limit
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        parts.append(text)
    return parts

# ================= ХЕНДЛЕРЫ =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔮 Здравствуйте, я ваш таролог.\n\n"
        "Опишите вашу ситуацию или задайте вопрос — я вытяну три карты и дам толкование."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_text = update.message.text
    wait_msg = await update.message.reply_text("🃏 Тасую колоду и вытягиваю карты…")

    cards_block = draw_cards()
    user_prompt = (
        f"Вопрос пользователя: {user_text}\n\n"
        f"Вытянутые карты:\n{cards_block}\n\n"
        f"Растолкуй расклад по заданной структуре."
    )

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.8,
            max_tokens=2500,
        )
        reply_text = (response.choices[0].message.content or "").strip()

        if not reply_text:
            await wait_msg.edit_text("⚠️ Модель вернула пустой ответ. Попробуйте переформулировать.")
            return

        if response.choices[0].finish_reason == "length":
            logging.warning("Ответ обрезан по max_tokens")

        try:
            await wait_msg.delete()
        except Exception:
            pass  # сообщение могло уже исчезнуть — не критично

        for chunk in split_text(reply_text):
            await update.message.reply_text(chunk)

    except RateLimitError:
        logging.warning("OpenRouter: rate limit")
        try:
            await wait_msg.edit_text("⏳ Модель перегружена. Попробуйте через минуту.")
        except Exception:
            pass
    except APIError as e:
        logging.error(f"OpenRouter API error: {e}")
        try:
            await wait_msg.edit_text("⚠️ Сервис временно недоступен. Попробуйте позже.")
        except Exception:
            pass
    except Exception as e:
        logging.exception(f"Неожиданная ошибка: {e}")
        try:
            await wait_msg.edit_text("⚠️ Не удалось вытянуть карты. Попробуйте ещё раз через минуту.")
        except Exception:
            pass

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error("Ошибка в хендлере:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("⚠️ Внутренняя ошибка. Попробуйте позже.")
        except Exception:
            pass

# ================= ЗАПУСК =================
def main():
    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=60.0,
        write_timeout=30.0,
        pool_timeout=30.0,
    )
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).request(request).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    logging.info("Таро-бот запущен…")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
