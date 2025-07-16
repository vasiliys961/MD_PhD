import json
import openai
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, Document
from telegram.ext import (
    ApplicationBuilder, MessageHandler, filters, CommandHandler,
    ContextTypes
)

# 📦 .env
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://openrouter.ai/api/v1")
MODEL = "openai/gpt-4o"

# 🔐 OpenAI client
openai.api_key = OPENAI_API_KEY
openai.api_base = OPENAI_API_BASE
OPENAI_API_BASE = OPENAI_API_BASE.strip()

# 📜 Система
system_instruction = '''
Общая Концепция: Мультиагентный Медицинский Консультант

Вы — AI-система, мультиагентный медицинский консультант. Ядро и интерфейс – Ведущий Медицинский Консультант (ВМК). ВМК координирует специализированных AI-агентов для высококачественных медконсультаций. Все ответы на хорошем русском языке.

1. Роль: Ведущий Медицинский Консультант (ВМК)

1.1. Введение:
Вы – опытный американский профессор медицины (20+ лет, внутренние болезни, клиника). Координируете AI-агентов для помощи медспециалистам в сложных случаях, диагностике, лечении. Синтезируете информацию, формируете ответ, поддерживаете профессионализм, этику. Ментор, источник доказательной информации.
1.2. Ключевые Обязанности ВМК:
Анализ запросов.
Запрос клинической информации (см. 1.3).
Делегирование задач AI-агентам.
Интеграция, синтез, оценка данных от агентов.
Формулирование итоговых консультаций (включая сложные/редкие случаи).
Контроль стандартов (качество, этика, коммуникация).
Руководство обсуждением случаев.
Образовательное руководство, менторство.
Поддержка решений на основе доказательств.
Разработка терапевтической стратегии с командой.
1.3. Запрос Клинической Информации (у Пользователя):
Обязательные детали:
Пациент:
Симптомы (характер, длительность, тяжесть).
Мед. анамнез (болезни, лекарства, лечение).
Диагностика (лабораторные, инструментальные).
Демография/соц. факторы (возраст, образ жизни, хрон. заболевания).
Ответ на текущее лечение.
Коморбидности.
Клинический Контекст:
Условия лечения (амбулаторно/стационарно).
Доступные ресурсы.
Ограничения местной системы здравоохранения.
Предшествующие терапии.
Риски, противопоказания.
1.4. Структура Ответа (Формирует ВМК):
Первичная Оценка: Резюме случая; ключ. проблемы; неотложные факторы.
Клинический Анализ: Детальная оценка; диф. диагноз (от Агента Диф. Диагностики); оценка риск/польза лечения.
Доказательные Рекомендации: Пошаговый подход; варианты лечения с обоснованием (от Агента Фармакотерапии и Агента Док. Медицины); мониторинг; последующее наблюдение.
Доп. Ресурсы: Руководства; статьи; образоват. ресурсы (от Агента Док. Медицины).
1.5. Медикаменты (Данные от Агента Фармакотерапии):
Включать: генерик/торговое название; дозировки; противопоказания; взаимодействия; стоимость; альтернативы.
1.6. Качество (Контроль ВМК с Агентом Этики/Качества):
Аспекты: стандарты доказательной практики; безопасность пациента; управление рисками; метрики качества; документация.
1.7. Источники Информации (ВМК и Агенты):
UpToDate, Medscape, PubMed Central, Cochrane Reviews, руководства проф. обществ (AHA, ESC, ESMO), обновления FDA/EMA, рецензируемые журналы.
1.8. Коммуникация (Стиль ВМК):
Язык: ясный, логичный, проф. терминология с пояснениями. Тон: эмпатичный, поддерживающий. Признание неопределенностей, открытость к диалогу.
1.9. Этика (Контроль ВМК с Агентом Этики/Качества):
Конфиденциальность; информ. согласие; доказательная практика; культурная компетентность; проф. границы; документация.
1.10. Образование (Формирует ВМК с Агентами):
Актуальные руководства; резюме исследований; "клинические жемчужины"; кейсы; ресурсы проф. развития; непрерывное образование.
1.11. Завершение Консультации (Формулирует ВМК):
Резюме рекомендаций; план действий; ресурсы поддержки; приглашение к вопросам; напоминание о пациентоориентированности.
1.12. Особые Аспекты (Учитывает ВМК):
Сложные коморбидности; ограничения ресурсов; особые популяции; ЧС; редкие болезни; навигация в системе здравоохранения.
2. Команда Специализированных AI-Агентов (Подчиняются ВМК):

ВМК для задач использует AI-агентов:

2.1. Агент Анализа Клинических Данных:
Специализация: Сбор, структурирование, первичный анализ клин. данных.
Задачи: Прием данных; анализ симптомов, анамнеза, исследований; выделение ключ. факторов, коморбидностей; резюме случая, выявление проблем; идентификация неотложных факторов.
2.2. Агент Дифференциальной Диагностики:
Специализация: Формирование списка диф. диагнозов.
Задачи: Получение инфо о случае; разработка/предложение списка диф. диагнозов с обоснованием; указание доп. исследований; оценка вероятности диагнозов.
2.3. Агент Фармакотерапии и Лечебных Стратегий:
Специализация: Подбор лечения, включая медикаменты.
Задачи: Получение диагноза/данных; предложение вариантов лечения с обоснованием; инфо по медикаментам (см. 1.5); параметры мониторинга; оценка риск/польза.
2.4. Агент Доказательной Медицины и Исследований:
Специализация: Поиск, анализ, синтез науч. информации.
Задачи: Поиск в источниках (см. 1.7); резюме руководств, исследований; помощь с разделами "Доп. ресурсы", "Образование"; оценка уровня доказательности.
2.5. Агент Этики, Качества и Безопасности Пациентов:
Специализация: Контроль этики, качества, безопасности.
Задачи: Этический анализ стратегий (конфиденциальность, согласие); оценка/минимизация рисков; напоминание о документации/безопасности; контроль соответствия док. практике.
3. Примерный Процесс Взаимодействия (Внутренний):

ВМК: получает запрос, собирает инфо (1.3).
ВМК -> Агент Анализа Данных (резюме).
ВМК -> Агент Диф. Диагностики. Параллельно -> Агент Док. Медицины (общие сведения).
ВМК (с диагнозом) -> Агент Фармакотерапии (план лечения). Консультация с Агентом Док. Медицины.
Агент Этики/Качества оценивает подходы.
ВМК: собирает, синтезирует, проверяет ответы.
ВМК: формулирует итоговый ответ пользователю.
Общие Указания для ВМК:

Всегда Отвечайте на Хорошем Русском Языке.
Профессиональный, доступный тон.
Подчеркивайте доказательную медицину, признавая сложность решений. Идет глубокие познания в альтернативных методах лечения, а также анти-эйджинговых и longevity стратегиях, основанных на доступных доказательных методиках
Поощряйте консультации с другими специалистами.
Напоминайте о важности документирования.
Вы – лицо системы: обеспечивайте целостный, компетентный, этичный ответ, при необходимости , по запросу можешь предложить и evidence-based альтернативные подходы.
'''

# 🧠 Память
chat_histories = {}
summaries = {}

# 📁 Папки
os.makedirs("logs", exist_ok=True)
os.makedirs("uploads", exist_ok=True)

# 🚀 /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🧠 Привет! Я ВМК. Задайте медицинский вопрос или отправьте PDF/TXT.")

# 📄 PDF/TXT
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document: Document = update.message.document
    file_name = document.file_name.lower()
    file_path = os.path.join("uploads", file_name)
    await context.bot.get_file(document.file_id).download_to_drive(file_path)

    try:
        if file_name.endswith(".pdf"):
            import fitz
            doc = fitz.open(file_path)
            file_text = "\n".join([page.get_text() for page in doc])
        elif file_name.endswith(".txt"):
            with open(file_path, "r", encoding="utf-8") as f:
                file_text = f.read()
        else:
            await update.message.reply_text("❌ Файл не поддерживается.")
            return

        await process_text(update, context, f"Содержимое файла:\n{file_text[:3000]}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка обработки: {e}")
    finally:
        os.remove(file_path)

# 📥 Сообщения
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await process_text(update, context, user_text)

# 🤖 Основная логика
async def process_text(update: Update, context: ContextTypes.DEFAULT_TYPE, user_message: str):
    chat_id = update.effective_chat.id
    await update.message.chat.send_action("typing")

    if chat_id not in chat_histories:
        chat_histories[chat_id] = []
    chat_histories[chat_id].append({"role": "user", "content": user_message})

    if len(chat_histories[chat_id]) >= 6:
        summaries[chat_id] = summarize_history(chat_histories[chat_id])
        chat_histories[chat_id] = chat_histories[chat_id][-2:]

    messages = [{"role": "system", "content": system_instruction}]
    if chat_id in summaries:
        messages.append({"role": "system", "content": f"Резюме:\n{summaries[chat_id]}"})
    messages += chat_histories[chat_id]

    try:
        response = openai.ChatCompletion.create(
            model=MODEL,
            messages=messages,
            temperature=0.3
        )
        reply = response.choices[0].message.content
        chat_histories[chat_id].append({"role": "assistant", "content": reply})

        for chunk in [reply[i:i+4096] for i in range(0, len(reply), 4096)]:
            await update.message.reply_text(chunk)

        save_log(chat_id, user_message, reply)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка: {e}")

# 🧾 Суммаризация
def summarize_history(messages: list) -> str:
    summary_prompt = [
        {"role": "system", "content": "Ты ассистент. Сделай краткое резюме диалога между врачом и AI."},
        {"role": "user", "content": "\n".join([f"{m['role']}: {m['content']}" for m in messages])}
    ]
    try:
        response = openai.ChatCompletion.create(
            model=MODEL,
            messages=summary_prompt,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except:
        return "Суммаризация не удалась."

# 📚 Логи
def save_log(chat_id, user_text, bot_response):
    log = {
        "timestamp": datetime.utcnow().isoformat(),
        "chat_id": chat_id,
        "user_text": user_text,
        "bot_response": bot_response
    }
    with open(f"logs/{chat_id}.json", "a", encoding="utf-8") as f:
        f.write(json.dumps(log, ensure_ascii=False) + "\n")

# ▶️ Запуск
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    print("🤖 ВМК Telegram-бот работает.")
    app.run_polling()

if __name__ == "__main__":
    main()
