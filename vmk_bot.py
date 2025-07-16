from dotenv import load_dotenv
load_dotenv()

import os
import json
from datetime import datetime
from telegram import Update, Document
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from openai import OpenAI
import fitz

# 📌 Получение переменных окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://openrouter.ai/api/v1").strip()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()
PORT = int(os.getenv("PORT", "8080"))
MODEL = "openai/gpt-4o"

# ⚠️ Проверка ключей
print("=" * 50)
print("ENVIRONMENT VARIABLES DIAGNOSTIC")
print("=" * 50)
print(f"TELEGRAM_TOKEN: {'✓' if TELEGRAM_TOKEN else '✗'} (len: {len(TELEGRAM_TOKEN)})")
print(f"OPENAI_API_KEY: {'✓' if OPENAI_API_KEY else '✗'} (len: {len(OPENAI_API_KEY)})")
print(f"WEBHOOK_URL: {WEBHOOK_URL}")
print(f"PORT: {PORT}")
print("=" * 50)

# 🌐 OpenAI клиент
client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_API_BASE
)

# 💾 Папки
os.makedirs("logs", exist_ok=True)
os.makedirs("uploads", exist_ok=True)

# 💬 История диалогов
chat_histories = {}
summaries = {}

# 🧠 system-инструкция (сокращённая)
system_instruction = "Вы — ВМК, мультиагентный медицинский консультант. Отвечайте на хорошем русском, используя доказательную медицину."

# 📥 Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🧠 Привет! Я ВМК. Задайте медицинский вопрос или отправьте PDF/TXT файл.")

# 📂 Обработка файлов
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document: Document = update.message.document
    file_name = document.file_name.lower()
    file_path = os.path.join("uploads", file_name)
    await context.bot.get_file(document.file_id).download_to_drive(file_path)

    try:
        if file_name.endswith(".pdf"):
            doc = fitz.open(file_path)
            file_text = "\n".join([page.get_text() for page in doc])
        elif file_name.endswith(".txt"):
            with open(file_path, "r", encoding="utf-8") as f:
                file_text = f.read()
        else:
            await update.message.reply_text("❌ Формат не поддерживается. Только PDF или TXT.")
            return

        await process_text(update, context, f"Содержимое файла:\n{file_text[:3000]}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка обработки файла: {e}")
    finally:
        os.remove(file_path)

# 💬 Обработка текста
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_text(update, context, update.message.text)

# 🧠 Обработка и диалог с OpenAI
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
        messages.append({"role": "system", "content": f"Резюме диалога:\n{summaries[chat_id]}"})
    messages += chat_histories[chat_id]

    try:
        response = client.chat.completions.create(
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
        await update.message.reply_text(f"⚠️ Ошибка OpenAI: {e}")

# 🧠 Суммаризация диалога
def summarize_history(messages: list) -> str:
    try:
        summary_prompt = [
            {"role": "system", "content": "Сделай краткое резюме диалога между врачом и AI."},
            {"role": "user", "content": "\n".join([f"{m['role']}: {m['content']}" for m in messages])}
        ]
        response = client.chat.completions.create(
            model=MODEL,
            messages=summary_prompt,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except:
        return "Суммаризация не удалась."

# 💾 Логирование
def save_log(chat_id, user_text, bot_response):
    log = {
        "timestamp": datetime.utcnow().isoformat(),
        "chat_id": chat_id,
        "user_text": user_text,
        "bot_response": bot_response
    }
    with open(f"logs/{chat_id}.json", "a", encoding="utf-8") as f:
        f.write(json.dumps(log, ensure_ascii=False) + "\n")

# 🚀 Запуск Webhook
def main():
    if not TELEGRAM_TOKEN or not WEBHOOK_URL:
        raise RuntimeError("❌ Переменные TELEGRAM_TOKEN или WEBHOOK_URL не заданы")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    print(f"🚀 Запуск Webhook на {WEBHOOK_URL}:{PORT}")

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL
    )

if __name__ == "__main__":
    main()
