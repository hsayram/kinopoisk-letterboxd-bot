import logging
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from bs4 import BeautifulSoup
import csv
import re
import io

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def parse_kinopoisk_html_content(content: str):
    """Парсит HTML контент страницы Кинопоиска и извлекает фильмы"""
    soup = BeautifulSoup(content, 'html.parser')
    films = []
    
    # Различные селекторы для разных версий страниц Кинопоиска
    film_items = soup.select('.user-rating-item, .profileFilmsList .item, .film-item, .item')
    
    if not film_items:
        # Альтернативный поиск по тексту
        text_content = soup.get_text()
        lines = text_content.split('\n')
        for line in lines:
            # Ищем строки с годом в скобках
            year_match = re.search(r'(.+?)\s*\((\d{4})\)', line.strip())
            if year_match and len(year_match.group(1)) > 3:
                title = year_match.group(1).strip()
                year = year_match.group(2)
                films.append({'title': title, 'year': year})
    else:
        for item in film_items:
            # Ищем название фильма
            title_el = item.select_one('.nameRus, .name, .film-name, .film-title, a')
            year_el = item.select_one('.year')
            
            if title_el:
                title_full = title_el.get_text().strip()
                year_match = re.search(r'\((\d{4})\)', title_full)
                year = year_match.group(1) if year_match else (year_el.get_text().strip() if year_el else '')
                title = re.sub(r'\s*\(\d{4}\)', '', title_full).strip()
                
                if title and len(title) > 2:  # Фильтруем слишком короткие названия
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
    """Обработчик команды /start"""
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

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = """📖 Подробная инструкция:

Шаг 1: Сохранение HTML со страницы Кинопоиска
• Перейди по ссылке: https://www.kinopoisk.ru/user/ТВОЙ_ID/votes/
• Нажми Cmd+S (или через меню "Файл" → "Сохранить страницу как...")
• Выбери "Веб-страница, полностью" 
• Сохрани файл

Шаг 2: Отправка файла боту
• Прикрепи сохраненный .html файл к сообщению
• Отправь мне

Шаг 3: Импорт в Letterboxd
• Получи от меня готовый CSV файл
• Перейди на https://letterboxd.com/import
• Загрузи полученный CSV файл
• Letterboxd автоматически сопоставит фильмы

❓ Проблемы?
Если CSV пустой - проверь, что сохранил именно страницу с оценками, а не главную страницу профиля.

💡 Бот работает с русскими названиями - Letterboxd их понимает!"""
    
    await update.message.reply_text(help_text)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик получения документов"""
    document = update.message.document
    
    if not document:
        await update.message.reply_text("❌ Пожалуйста, отправь HTML файл.")
        return
    
    # Проверяем расширение файла
    if not document.file_name.lower().endswith(('.html', '.htm')):
        await update.message.reply_text("❌ Нужен именно HTML файл со страницы Кинопоиска.")
        return
    
    await update.message.reply_text("⏳ Получаю и обрабатываю файл, это может занять несколько секунд...")
    
    try:
        # Скачиваем файл
        file = await document.get_file()
        file_content = await file.download_as_bytearray()
        
        # Декодируем с различными кодировками
        content_str = None
        for encoding in ['utf-8', 'windows-1251', 'cp1252']:
            try:
                content_str = file_content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        
        if not content_str:
            await update.message.reply_text("❌ Не удалось прочитать файл. Проверьте кодировку.")
            return
        
        # Парсим фильмы
        films = parse_kinopoisk_html_content(content_str)
        
        if not films:
            await update.message.reply_text(
                "❌ Не удалось найти фильмы в файле.\n\n"
                "Убедись, что ты сохранил страницу с оценками:\n"
                "https://www.kinopoisk.ru/user/ТВОЙ_ID/votes/"
            )
            return
        
        # Генерируем CSV
        csv_content = films_to_csv(films)
        csv_file = io.BytesIO(csv_content)
        csv_file.name = 'letterboxd_import.csv'
        
        success_text = f"""✅ Успешно обработано {len(films)} фильмов!

📁 CSV файл готов для импорта в Letterboxd.

🔗 Следующие шаги:
1. Сохрани полученный CSV файл
2. Перейди на https://letterboxd.com/import  
3. Загрузи этот файл
4. Letterboxd автоматически добавит фильмы в твой профиль

🎉 Готово! Теперь твоя коллекция фильмов будет и в Letterboxd!"""
        
        await update.message.reply_document(
            document=csv_file,
            filename='letterboxd_import.csv',
            caption=success_text
        )
        
    except Exception as e:
        logger.error(f"Ошибка при обработке файла: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при обработке файла. Попробуй еще раз или обратись к разработчику."
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик обычных текстовых сообщений"""
    await update.message.reply_text(
        "📁 Отправь мне HTML файл страницы с оценками из Кинопоиска.\n\n"
        "Нужна помощь? Напиши /help"
    )

def main():
    """Главная функция запуска бота"""
    # Получаем токен из переменных окружения
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    
    if not token:
        print("❌ Ошибка: переменная окружения TELEGRAM_BOT_TOKEN не установлена")
        print("Установи её командой: export TELEGRAM_BOT_TOKEN='твой_токен'")
        return
    
    # Создаем приложение
    application = ApplicationBuilder().token(token).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Бот запущен и готов к работе!")
    
    # Запускаем бота
    application.run_polling(allowed_updates=['message'])

if __name__ == '__main__':
    main()
