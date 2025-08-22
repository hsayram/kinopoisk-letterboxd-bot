import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from bs4 import BeautifulSoup
import csv
import re
import io
import asyncio
from aiohttp import web
import threading

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_kinopoisk_html_content(content: str):
    """Парсит HTML контент страницы Кинопоиска и извлекает фильмы"""
    soup = BeautifulSoup(content, 'html.parser')
    films = []
    
    film_items = soup.select('.user-rating-item, .profileFilmsList .item, .film-item, .item')
    
    if not film_items:
        text_content = soup.get_text()
        lines = text_content.split('\n')
        for line in lines:
            year_match = re.search(r'(.+?)\s*\((\d{4})\)', line.strip())
            if year_match and len(year_match.group(1)) > 3:
                title = year_match.group(1).strip()
                year = year_match.group(2)
                films.append({'title': title, 'year': year})
    else:
        for item in film_items:
            title_el = item.select_one('.nameRus, .name, .film-name, .film-title, a')
            year_el = item.select_one('.year')
            
            if title_el:
                title_full = title_el.get_text().strip()
                year_match = re.search(r'\((\d{4})\)', title_full)
                year = year_match.group(1) if year_match else (year_el.get_text().strip() if year_el else '')
                title = re.sub(r'\s*\(\d{4}\)', '', title_full).strip()
                
                if title and len(title) > 2:
                    films.append({'title': title, 'year': year})
    
    return films

def films_to_csv(films):
    """Конвертирует список фильмов в CSV для Letterboxd"""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Title', 'Year', 'Rating', 'WatchedDate', 'imdbID', 'tmdbID'])
    
    for film in films:
        writer.writerow([film['title'], film['year'], '', '', '', ''])
    
    output.seek(0)
    return output.getvalue().encode('utf-8')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = """🎬 Привет! Добро пожаловать в Kinopoisk to Letterboxd Bot!

Я помогу тебе перенести твои фильмы из Кинопоиска в Letterboxd.

📋 Как пользоваться:
1️⃣ Зайди на свою страницу оценок в Кинопоиске
2️⃣ Сохрани страницу как HTML файл (Cmd+S → "Веб-страница, полностью")
3️⃣ Отправь мне этот HTML файл
4️⃣ Получи готовый CSV для импорта в Letterboxd

🔗 Полезные ссылки:
• Твои оценки на Кинопоиске: https://www.kinopoisk.ru/user/ТВОЙ_ID/votes/
• Импорт в Letterboxd: https://letterboxd.com/import

Готов? Отправь мне HTML файл! 🚀"""
    
    await update.message.reply_text(welcome_text)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    
    if not document:
        await update.message.reply_text("❌ Пожалуйста, отправь HTML файл.")
        return
    
    if not document.file_name.lower().endswith(('.html', '.htm')):
        await update.message.reply_text("❌ Нужен именно HTML файл со страницы Кинопоиска.")
        return
    
    await update.message.reply_text("⏳ Получаю и обрабатываю файл...")
    
    try:
        file = await document.get_file()
        file_content = await file.download_as_bytearray()
        
        content_str = None
        for encoding in ['utf-8', 'windows-1251', 'cp1252']:
            try:
                content_str = file_content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        
        if not content_str:
            await update.message.reply_text("❌ Не удалось прочитать файл.")
            return
        
        films = parse_kinopoisk_html_content(content_str)
        
        if not films:
            await update.message.reply_text("❌ Не удалось найти фильмы в файле.")
            return
        
        csv_content = films_to_csv(films)
        csv_file = io.BytesIO(csv_content)
        csv_file.name = 'letterboxd_import.csv'
        
        success_text = f"✅ Успешно обработано {len(films)} фильмов!\n\nПерейди на https://letterboxd.com/import и загрузи этот файл."
        
        await update.message.reply_document(
            document=csv_file,
            filename='letterboxd_import.csv',
            caption=success_text
        )
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text("❌ Ошибка при обработке файла.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📁 Отправь мне HTML файл страницы с оценками из Кинопоиска.\n\n"
        "Нужна помощь? Напиши /start"
    )

# Web сервер для Render
async def health_check(request):
    return web.Response(text="Bot is running!")

async def run_web_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    
    port = int(os.environ.get('PORT', 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Web server started on port {port}")

def main():
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN не установлен")
        return
    
    # Создаем приложение
    application = Application.builder().token(token).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запускаем бота в отдельном потоке
    def run_bot():
        print("🚀 Бот запущен!")
        application.run_polling(drop_pending_updates=True)
    
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    # Запускаем веб-сервер в основном потоке
    asyncio.run(run_web_server())
    
    # Ждем завершения потока с ботом
    bot_thread.join()

if __name__ == '__main__':
    main()
