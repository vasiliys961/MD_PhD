import os
import json
import asyncio
from datetime import datetime
from telegram import Update, Document
from telegram.ext import (
    ApplicationBuilder, MessageHandler, filters, CommandHandler,
    ContextTypes
)
from openai import OpenAI
import fitz
import tempfile

# 🔐 Альтернативные способы получения переменных окружения
def get_env_var(var_name, possible_names=None):
    """Попытка получить переменную окружения с разными именами"""
    if possible_names is None:
        possible_names = [var_name]
    else:
        possible_names = [var_name] + possible_names
    
    for name in possible_names:
        value = os.getenv(name, "").strip()
        if value:
            print(f"DEBUG: Found {var_name} as {name}")
            return value
    
    print(f"ERROR: Could not find {var_name} in any of: {possible_names}")
    return ""

# Попытка получить переменные разными способами
TELEGRAM_TOKEN = get_env_var("TELEGRAM_TOKEN", ["TG_TOKEN", "BOT_TOKEN", "TELEGRAM_BOT_TOKEN"])
OPENAI_API_KEY = get_env_var("OPENAI_API_KEY", ["OPENAI_KEY", "API_KEY", "OPENROUTER_API_KEY"])
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://openrouter.ai/api/v1").strip()
MODEL = "openai/gpt-4o"

# ⚠️ Полная диагностика
print("="*50)
print("ENVIRONMENT VARIABLES DIAGNOSTIC")
print("="*50)
print(f"All environment variables: {sorted(os.environ.keys())}")
print(f"TELEGRAM_TOKEN: {'✓' if TELEGRAM_TOKEN else '✗'} (length: {len(TELEGRAM_TOKEN)})")
print(f"OPENAI_API_KEY: {'✓' if OPENAI_API_KEY else '✗'} (length: {len(OPENAI_API_KEY)})")
print(f"OPENAI_API_BASE: {OPENAI_API_BASE}")

if TELEGRAM_TOKEN:
    print(f"TELEGRAM_TOKEN preview: {TELEGRAM_TOKEN[:10]}...{TELEGRAM_TOKEN[-10:]}")
if OPENAI_API_KEY:
    print(f"OPENAI_API_KEY preview: {OPENAI_API_KEY[:10]}...{OPENAI_API_KEY[-10:]}")

print("="*50)

# Проверка обязательных переменных
if not TELEGRAM_TOKEN:
    print("CRITICAL ERROR: TELEGRAM_TOKEN is missing")
    telegram_vars = [k for k in os.environ.keys() if 'TOKEN' in k.upper() or 'TG' in k.upper() or 'BOT' in k.upper()]
    print(f"Available telegram-related vars: {telegram_vars}")
    raise ValueError("TELEGRAM_TOKEN not found")

if not OPENAI_API_KEY:
    print("CRITICAL ERROR: OPENAI_API_KEY is missing")
    api_vars = [k for k in os.environ.keys() if 'API' in k.upper() or 'KEY' in k.upper() or 'OPENAI' in k.upper()]
    print(f"Available API-related vars: {api_vars}")
    raise ValueError("OPENAI_API_KEY not found")

# 🔌 Создание клиента OpenAI с полной диагностикой
def create_openai_client():
    try:
        print("Creating OpenAI client...")
        
        # Проверка формата ключа
        if not OPENAI_API_KEY.startswith(('sk-', 'sk-or-')):
            print(f"WARNING: API key format unusual: {OPENAI_API_KEY[:20]}...")
        
        client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_API_BASE,
            timeout=30.0
        )
        
        print("Testing OpenAI connection...")
        test_response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=5
        )
        
        print("✓ OpenAI client created and tested successfully")
        return client
        
    except Exception as e:
        print(f"✗ OpenAI client creation failed: {e}")
        print(f"Error type: {type(e).__name__}")
        
        # Дополнительная диагностика
        if "authentication" in str(e).lower() or "401" in str(e):
            print("This looks like an authentication error. Check your API key.")
        elif "404" in str(e):
            print("This might be a model or endpoint issue.")
        elif "timeout" in str(e).lower():
            print("This looks like a timeout issue.")
        
        raise

client = create_openai_client()

# 📎 Инструкция для ВМК (остается та же)
system_instruction = """
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
Вы – лицо системы: обеспечивайте целостный, компетентный, этичный ответ, при необходимости , по запросу можешь предложить и evidence-based альтернативные подходы.]
"""

# 🧠 Хранилище чатов и резюме
chat_histories = {}
summaries = {}

# 📁 Создание папок
try:
    os.makedirs("logs", exist_ok=True)
    os.makedirs("uploads", exist_ok=True)
    print("✓ Directories created successfully")
except Exception as e:
    print(f"✗ Failed to create directories: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = """
🧠 Привет! Я ВМК (Ведущий Медицинский Консультант).

Я могу помочь с:
• Анализом медицинских случаев
• Дифференциальной диагностикой
• Рекомендациями по лечению
• Обработкой медицинских документов (PDF/TXT)

Задайте медицинский вопрос или отправьте документ для анализа.
"""
    await update.message.reply_text(welcome_message)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document: Document = update.message.document
    file_name = document.file_name.lower()
    file_path = os.path.join("uploads", file_name)
    
    print(f"Processing document: {file_name}")
    
    try:
        file_obj = await context.bot.get_file(document.file_id)
        await file_obj.download_to_drive(file_path)
        print(f"✓ File downloaded: {file_name}")
    except Exception as e:
        print(f"✗ Failed to download file: {e}")
        await update.message.reply_text(f"❌ Ошибка скачивания файла: {e}")
        return

    try:
        if file_name.endswith(".pdf"):
            doc = fitz.open(file_path)
            file_text = "\n".join([page.get_text() for page in doc])
            doc.close()
            print(f"✓ PDF processed, text length: {len(file_text)}")
        elif file_name.endswith(".txt"):
            with open(file_path, "r", encoding="utf-8") as f:
                file_text = f.read()
            print(f"✓ TXT processed, text length: {len(file_text)}")
        else:
            await update.message.reply_text("❌ Формат не поддерживается. Только PDF или TXT.")
            return

        await process_text(update, context, f"Содержимое файла '{file_name}':\n{file_text[:3000]}")
        
    except Exception as e:
        print(f"✗ Failed to process file: {e}")
        await update.message.reply_text(f"❌ Ошибка обработки файла: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_text(update, context, update.message.text)

async def process_text(update: Update, context: ContextTypes.DEFAULT_TYPE, user_message: str):
    chat_id = update.effective_chat.id
    print(f"Processing message from chat {chat_id}, length: {len(user_message)}")
    
    try:
        await update.message.chat.send_action("typing")
    except Exception as e:
        print(f"Failed to send typing action: {e}")

    if chat_id not in chat_histories:
        chat_histories[chat_id] = []
    chat_histories[chat_id].append({"role": "user", "content": user_message})

    # Управление историей чата
    if len(chat_histories[chat_id]) >= 6:
        summaries[chat_id] = summarize_history(chat_histories[chat_id])
        chat_histories[chat_id] = chat_histories[chat_id][-2:]

    # Формирование сообщений для API
    messages = [{"role": "system", "content": system_instruction}]
    if chat_id in summaries:
        messages.append({"role": "system", "content": f"Резюме предыдущего диалога:\n{summaries[chat_id]}"})
    messages += chat_histories[chat_id]

    try:
        print("Sending request to OpenAI API...")
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=2000
        )
        print("✓ Received response from OpenAI API")
        
        reply = response.choices[0].message.content
        chat_histories[chat_id].append({"role": "assistant", "content": reply})

        # Отправка ответа частями
        for i, chunk in enumerate([reply[i:i+4096] for i in range(0, len(reply), 4096)]):
            await update.message.reply_text(chunk)
            if i > 0:  # Небольшая задержка между частями
                await asyncio.sleep(0.5)

        save_log(chat_id, user_message, reply)
        print(f"✓ Successfully processed message for chat {chat_id}")
        
    except Exception as e:
        print(f"✗ Failed to process message: {e}")
        print(f"Error type: {type(e).__name__}")
        
        if "rate limit" in str(e).lower():
            error_message = "⚠️ Превышен лимит запросов. Попробуйте через несколько минут."
        elif "timeout" in str(e).lower():
            error_message = "⚠️ Превышено время ожидания. Попробуйте еще раз."
        else:
            error_message = f"⚠️ Ошибка обработки запроса: {str(e)}"
            
        await update.message.reply_text(error_message)

def summarize_history(messages: list) -> str:
    try:
        print("Creating summary of chat history...")
        summary_prompt = [
            {"role": "system", "content": "Сделай краткое резюме медицинского диалога на русском языке. Выдели ключевые моменты."},
            {"role": "user", "content": "\n".join([f"{m['role']}: {m['content'][:500]}..." for m in messages])}
        ]
        
        response = client.chat.completions.create(
            model=MODEL,
            messages=summary_prompt,
            temperature=0.3,
            max_tokens=500
        )
        
        summary = response.choices[0].message.content.strip()
        print("✓ Summary created successfully")
        return summary
        
    except Exception as e:
        print(f"✗ Failed to create summary: {e}")
        return "Резюме недоступно из-за ошибки суммаризации."

def save_log(chat_id, user_text, bot_response):
    try:
        log = {
            "timestamp": datetime.utcnow().isoformat(),
            "chat_id": chat_id,
            "user_text": user_text[:1000],
            "bot_response": bot_response[:1000]
        }
        
        log_file = f"logs/{chat_id}.json"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log, ensure_ascii=False) + "\n")
        
        print(f"✓ Log saved for chat {chat_id}")
        
    except Exception as e:
        print(f"✗ Failed to save log: {e}")

def main():
    try:
        print("Building Telegram application...")
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        
        # Добавляем обработчики
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        
        print("🤖 ВМК Telegram-бот запущен успешно!")
        print(f"Model: {MODEL}")
        print(f"API Base: {OPENAI_API_BASE}")
        
        # Запуск бота
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query"]
        )
        
    except Exception as e:
        print(f"CRITICAL ERROR: Failed to start bot: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    main()
