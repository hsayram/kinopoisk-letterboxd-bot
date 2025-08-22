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

logging.basicConfig(level=logging.INFO)

def parse_kinopoisk_html_content(content: str):
    soup = BeautifulSoup(content, 'html.parser')
    films = []
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
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Title', 'Year', 'Rating', 'WatchedDate', 'imdbID', 'tmdbID'])
    for film in films:
        writer.writerow([film['title'], film['year'], '', '', '', ''])
    output.seek(0)
    return output.getvalue().encode('utf-8')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎬 Отправь HTML файл со страницы Кинопоиска!")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document or not document.file_name.lower().endswith(('.html', '.htm')):
        await update.message.reply_text("❌ Нужен HTML файл.")
        return
    
    await update.message.reply_text("⏳ Обрабатываю...")
    
    try:
        file = await document.get_file()
        file_content = await file.download_as_bytearray()
        content_str = file_content.decode('utf-8', errors='ignore')
        films = parse_kinopoisk_html_content(content_str)
        
        if not films:
            await update.message.reply_text("❌ Фильмы не найдены.")
            return
        
        csv_content = films_to_csv(films)
        csv_file = io.BytesIO(csv_content)
        
        await update.message.reply_document(
            document=csv_file,
            filename='letterboxd_import.csv',
            caption=f"✅ {len(films)} фильмов готово!"
        )
    except Exception as e:
        await update.message.reply_text("❌ Ошибка обработки.")

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK')

def run_web_server():
    port = int(os.environ.get('PORT', 8080))
    httpd = HTTPServer(('0.0.0.0', port), HealthHandler)
    httpd.serve_forever()

def main():
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not token:
        print("❌ Токен не установлен")
        return
    
    # Веб-сервер
    web_thread = threading.Thread(target=run_web_server)
    web_thread.daemon = True
    web_thread.start()
    
    # Бот
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print("🚀 Запущен!")
    application.run_polling()

if __name__ == '__main__':
    main()
