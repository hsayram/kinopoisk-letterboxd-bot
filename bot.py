import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from bs4 import BeautifulSoup
import csv
import re
import io
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_kinopoisk_html_content(content: str):
    """Парсит HTML контент страницы Кинопоиска и извлекает фильмы"""
    soup = BeautifulSoup(content, 'html.parser')
    films = []
    
    # Поиск по тексту страницы
    text_content = soup.get_text()
    lines = text_content.split('\n')
    for line in lines:
        year_match = re.search(r'(.+?)\s*\((\d{4})\)', line.strip())
        if year_match and len(year_match.group(1)) > 3:
            title = year_match.group(1).strip()
            year = year_match.group(2)
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

💡 Советы:
• Бот работает с русскими названиями - Letterboxd их понимает
• Убедись, что сохранил именно страницу с оценками, а не главную
• Если CSV пустой - попробуй другую страницу профиля

Готов? Отправь мне HTML файл! 🚀

Нужна подробная инструкция? Напиши /help"""
    
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = """📖 Подробная инструкция:

Шаг 1: Сохранение HTML со страницы Кинопоиска
• Перейди на https://www.kinopoisk.ru/user/ТВОЙ_ID/votes/
• Нажми Cmd+S (или Ctrl+S на Windows)
• Выбери "Веб-страница, полностью"
• Сохрани файл на компьютер

Шаг 2: Отправка файла боту
• Прикрепи сохраненный .html файл к сообщению
• Отправь мне в этот чат

Шаг 3: Импорт в Letterboxd
• Получи от меня готовый CSV файл
• Перейди на https://letterboxd.com/import
• Загрузи полученный CSV файл
• Letterboxd автоматически сопоставит фильмы

❓ Возможные проблемы:
• Если CSV пустой - проверь, что сохранил страницу с оценками
• Поддерживаются русские названия фильмов
• Нужна только страница с оценками, не главная страница профиля
• Убедись, что в браузере загрузились все фильмы (прокрути до конца)

🔄 Альтернативные страницы для сохранения:
• Просмотренные: https://www.kinopoisk.ru/user/ТВОЙ_ID/movies/
• Избранное: https://www.kinopoisk.ru/user/ТВОЙ_ID/folder/

Остались вопросы? Просто отправь /start чтобы начать заново!"""
    
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
                "Возможные причины:\n"
                "• Сохранена не та страница (нужна страница с оценками)\n"
                "• Страница не полностью загрузилась в браузере\n"
                "• Профиль закрыт или пустой\n\n"
                "Попробуй сохранить другую страницу или напиши /help для подробной инструкции."
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

🎉 Готово! Теперь твоя коллекция фильмов будет и в Letterboxd!

Нужно обработать еще один файл? Просто отправь его сюда!"""
        
        await update.message.reply_document(
            document=csv_file,
            filename='letterboxd_import.csv',
            caption=success_text
        )
        
    except Exception as e:
        logger.error(f"Ошибка при обработке файла: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при обработке файла.\n\n"
            "Попробуй:\n"
            "• Отправить файл заново\n"
            "• Сохранить страницу еще раз\n"
            "• Написать /help для инструкции\n\n"
            "Если проблема повторяется - обратись к разработчику."
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик обычных текстовых сообщений"""
    await update.message.reply_text(
        "📁 Отправь мне HTML файл страницы с оценками из Кинопоиска.\n\n"
        "❓ Нужна помощь?\n"
        "• /start - начать заново\n"
        "• /help - подробная инструкция"
    )

# Веб-сервер для Render
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Kinopoisk to Letterboxd Bot is running!')
    
    def log_message(self, format, *args):
        # Отключаем логи веб-сервера
        return

def run_web_server():
    """Запуск веб-сервера для Render Web Service"""
    port = int(os.environ.get('PORT', 8080))
    httpd = HTTPServer(('0.0.0.0', port), HealthHandler)
    print(f"Web server started on port {port}")
    httpd.serve_forever()

def main():
    """Главная функция запуска бота"""
    # Получаем токен из переменных окружения
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    
    if not token:
        print("❌ Ошибка: переменная окружения TELEGRAM_BOT_TOKEN не установлена")
        print("Установи её на сервере Render в настройках Environment Variables")
        return
    
    # Запускаем веб-сервер в отдельном потоке для Render
    web_thread = threading.Thread(target=run_web_server)
    web_thread.daemon = True
    web_thread.start()
    
    # Создаем приложение бота
    application = Application.builder().token(token).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Telegram бот запущен и готов к работе!")
    print("Доступные команды:")
    print("  /start - приветствие и основная инструкция")
    print("  /help - подробная инструкция")
    
    # Запускаем бота
    application.run_polling(drop_pending_updates=True)
