import os
import asyncio
import feedparser
from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import logging
import re
import json
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

if not BOT_TOKEN or not CHANNEL_ID:
    raise ValueError("❌ BOT_TOKEN и CHANNEL_ID обязательны!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Нейтральный GIF по умолчанию (гармония, семья, спокойствие)
DEFAULT_GIF_URL = "https://media.giphy.com/media/l0MYt5jPR6QX5pnqM/giphy.gif"

# Источники: только русскоязычные и рабочие
FEEDS = [
    {"name": "Психология.ру", "url": "https://www.psychology.ru/rss/", "tag": "🧠 Психология"},
    {"name": "Psychologies.ru", "url": "https://psychologies.ru/rss/", "tag": "❤️ Отношения"},
    {"name": "Московский центр психотерапии", "url": "https://mcpsy.ru/feed/", "tag": "👨‍👩‍👧 Семья"},
    {"name": "Habr — Психология", "url": "https://habr.com/ru/hub/psychology/rss/", "tag": "📚 Саморазвитие"},
    {"name": "Психология отношений (TG)", "url": "https://rsshub.app/telegram/channel/psihologiya_otnosheniy", "tag": "💬 Советы"},
]

# Файл для хранения опубликованных ссылок
SEEN_POSTS_FILE = "/tmp/seen_posts.json"

def is_valid_image_url(url):
    if not url:
        return False
    parsed = urlparse(url)
    return bool(parsed.netloc) and bool(parsed.scheme) and url.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))

def load_seen_posts():
    if os.path.exists(SEEN_POSTS_FILE):
        try:
            with open(SEEN_POSTS_FILE, "r") as f:
                return set(json.load(f))
        except Exception as e:
            logging.warning(f"Не удалось загрузить историю: {e}")
            return set()
    return set()

def save_seen_post(post_id):
    seen = load_seen_posts()
    seen.add(post_id)
    # Ограничиваем размер списка
    seen = set(list(seen)[-100:])
    try:
        with open(SEEN_POSTS_FILE, "w") as f:
            json.dump(list(seen), f)
    except Exception as e:
        logging.error(f"Ошибка сохранения истории: {e}")

async def send_test_message():
    try:
        await bot.send_message(CHANNEL_ID, "✅ Тест: бот по психологии семьи запущен!")
        logging.info("✅ Тестовое сообщение отправлено.")
    except Exception as e:
        logging.error(f"❌ Ошибка теста: {e}")

async def send_post(bot, channel_id, caption, image_url=None):
    try:
        if image_url and is_valid_image_url(image_url):
            if image_url.lower().endswith('.gif'):
                await bot.send_animation(chat_id=channel_id, animation=image_url, caption=caption, parse_mode="HTML")
            else:
                await bot.send_photo(chat_id=channel_id, photo=image_url, caption=caption, parse_mode="HTML")
        else:
            await bot.send_animation(chat_id=channel_id, animation=DEFAULT_GIF_URL, caption=caption, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Ошибка отправки поста: {e}")
        await bot.send_message(chat_id=channel_id, text=caption, parse_mode="HTML")

async def fetch_and_post():
    logging.info("🔄 Проверка источников по психологии...")
    seen_posts = load_seen_posts()
    for feed in FEEDS:
        try:
            logging.info(f"Источник: {feed['name']}")
            parsed = feedparser.parse(feed["url"])
            if parsed.entries:
                entry = parsed.entries[0]
                title = entry.get("title", "Без заголовка").strip()
                link = entry.get("link", "").strip()

                if not link or not title:
                    logging.info(f"⚠️ Пропущено: нет ссылки или заголовка ({feed['name']})")
                    continue

                # Защита от дублей
                if link in seen_posts:
                    logging.info(f"⏭️ Уже опубликовано: {title}")
                    continue

                caption = (
                    f'{feed["tag"]}\n\n'
                    f'<b>{title}</b>\n\n'
                    f'🔗 <a href="{link}">Читать оригинал</a>'
                )

                # Поиск изображения
                image_url = None
                if hasattr(entry, 'enclosures') and entry.enclosures:
                    for enc in entry.enclosures:
                        url = getattr(enc, 'href', None) or (enc.get('href') if isinstance(enc, dict) else None)
                        if url and is_valid_image_url(url):
                            image_url = url
                            break
                if not image_url and hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
                    image_url = entry.media_thumbnail[0].get('url')
                if not image_url:
                    content = getattr(entry, 'summary', '') + getattr(entry, 'content', [{}])[0].get('value', '')
                    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content)
                    if match:
                        image_url = match.group(1)

                await send_post(bot, CHANNEL_ID, caption, image_url)
                logging.info(f"✅ Опубликовано: {title}")

                # Сохраняем ссылку
                save_seen_post(link)
                await asyncio.sleep(1)
            else:
                logging.info(f"ℹ️ Нет записей: {feed['name']}")
        except Exception as e:
            logging.error(f"Ошибка при обработке {feed['name']}: {e}")
    logging.info("🔚 Проверка завершена.")

async def main():
    await send_test_message()
    scheduler = AsyncIOScheduler()
    interval_hours = int(os.getenv("POST_INTERVAL_HOURS", 6))
    scheduler.add_job(fetch_and_post, 'interval', hours=interval_hours)
    scheduler.start()
    logging.info(f"✅ Бот 'Психология семьи' запущен. Интервал: {interval_hours} ч.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
