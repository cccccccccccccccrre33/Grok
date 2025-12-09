import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import re
import sqlite3
import os
from datetime import datetime
import time

TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))

if not TOKEN or not GROUP_ID:
    print("ОШИБКА: Укажи BOT_TOKEN и GROUP_ID")
    exit()

bot = telebot.TeleBot(TOKEN)
os.makedirs("data", exist_ok=True)
DB_PATH = "data/items.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT, brand TEXT, size TEXT, price INTEGER,
        currency TEXT, photo_id TEXT, description TEXT, timestamp TEXT)''')
    conn.commit()
    conn.close()

init_db()

CATEGORIES = ["штаны", "шапки", "кепки", "кроссовки", "носки", "очки", "штани", "шапка", "кепка", "кроси", "кросівки"]
BRANDS = ["Gucci", "LV", "Palm Angels", "Off-White", "Stone Island", "Balenciaga"]

CURRENCY_PATTERNS = {
    r'\$|usd|доллар|dollar': 'USD',
    r'€|eur|евро|euro': 'EUR',
    r'грн|uah|₴|гривн|hryvnia': 'UAH'
}

TEXTS = {
    'ru': {'welcome': 'Привет! Я бот магазина одежды\n\nВыберите категорию или бренд:', 'more': 'Ещё 10', 'no_more': 'Больше нет', 'of': 'из', 'size_title': 'Размерные сетки'},
    'uk': {'welcome': 'Привіт! Я бот магазину одягу\n\nОберіть категорію або бренд:', 'more': 'Ще 10', 'no_more': 'Більше немає', 'of': 'з', 'size_title': 'Розмірні сітки'},
    'en': {'welcome': 'Hi! Clothing store bot\n\nChoose category or brand:', 'more': 'More 10', 'no_more': 'No more', 'of': 'of', 'size_title': 'Size charts'},
}

SIZE_CHART = {
    'ru': "Штаны: S (28-30), M (31-33), L (34-36), XL (37-40)\nКроссовки: EU 36–46\nШапки и кепки: One Size / 56-62",
    'uk': "Штани: S (28-30), M (31-33), L (34-36), XL (37-40)\nКросівки: EU 36–46\nШапки та кепки: One Size / 56-62",
    'en': "Pants: S (28-30), M (31-33), L (34-36), XL (37-40)\nSneakers: EU 36–46\nHats & caps: One Size / 56-62",
}

def parse_and_save(msg):
    if not msg.photo or not msg.caption: return
    cap = msg.caption.lower()
    orig = msg.caption

    type_ = next((c for c in CATEGORIES if c in cap), None)
    if not type_: return

    brand = "Другие"
    for b in BRANDS:
        if b.lower() in cap:
            brand = b
            break

    size = re.search(r'(size|розмір|размер)[\s:]*(.+?)(?=\s|$|\n)', cap)
    size = size.group(2).strip().upper() if size else None

    price_match = re.search(r'(\d{2,5})\s*([$€₴]|usd|eur|uah|доллар|евро|грн)', cap)
    if not price_match: return
    price = int(price_match.group(1))
    curr = price_match.group(2)
    currency = next((code for pat, code in CURRENCY_PATTERNS.items() if re.search(pat, curr)), "USD")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO items VALUES (NULL,?,?,?,?,?,?,?,?)",
              (type_, brand, size, price, currency, msg.photo[-1].file_id, orig, datetime.now().isoformat()))
    conn.commit()
    conn.close()

@bot.message_handler(content_types=['photo'])
def photo_handler(msg):
    if msg.chat.id == GROUP_ID or (hasattr(msg, 'forward_from_chat') and msg.forward_from_chat and msg.forward_from_chat.id == GROUP_ID):
        try:
            parse_and_save(msg)
        except: pass

@bot.message_handler(commands=['start'])
def start(msg):
    lang = 'uk' if msg.from_user.language_code and msg.from_user.language_code.startswith('uk') else 'ru' if msg.from_user.language_code and msg.from_user.language_code.startswith('ru') else 'en'
    bot.send_message(msg.chat.id, TEXTS[lang]['welcome'])

    mk = InlineKeyboardMarkup(row_width=2)
    for c in ["штаны", "шапки", "кепки", "кроссовки", "носки", "очки"]:
        mk.add(InlineKeyboardButton(c.capitalize(), callback_data=f"cat_{c}"))
    mk.row_width = 3
    for b in BRANDS + ["Другие"]:
        mk.add(InlineKeyboardButton(b, callback_data=f"brand_{b}"))

    bot.send_message(msg.chat.id, "Выберите:", reply_markup=mk)
    bot.send_message(msg.chat.id, f"*{TEXTS[lang]['size_title']}*\n\n{SIZE_CHART[lang]}", parse_mode="Markdown")

def get_items(f,v):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM items WHERE type=? ORDER BY timestamp DESC" if f=="cat" else "SELECT * FROM items WHERE brand=? ORDER BY timestamp DESC", (v,))
    rows = c.fetchall()
    conn.close()
    return [{'id':r[0],'type':r[1],'brand':r[2],'size':r[3],'price':r[4],'currency':r[5],'photo_id':r[6],'description':r[7]} for r in rows]

def send10(chat_id, items, lang, start):
    for it in items[start:start+10]:
        cap = f"{it['description']}\n\nБренд: {it['brand']}\n"
        if it['size']: cap += f"Размер: {it['size']}\n"
        cap += f"Цена: {it['price']} {it['currency']}"
        try: bot.send_photo(chat_id, it['photo_id'], caption=cap)
        except: pass

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    lang = 'uk' if c.from_user.language_code and c.from_user.language_code.startswith('uk') else 'ru' if c.from_user.language_code and c.from_user.language_code.startswith('ru') else 'en'
    try:
        if c.data.startswith(('cat_', 'brand_')):
            tp, val = c.data.split('_',1)
            items = get_items(tp, val)
            if not items:
                bot.answer_callback_query(c.id, TEXTS[lang]['no_more'])
                return
            send10(c.message.chat.id, items, lang, 0)
            if len(items)>10:
                mk = InlineKeyboardMarkup()
                mk.add(InlineKeyboardButton(TEXTS[lang]['more'], callback_data=f"more_{tp}_{val}_10"))
                bot.send_message(c.message.chat.id, f"10 {TEXTS[lang]['of']} {len(items)}", reply_markup=mk)

        elif c.data.startswith('more_'):
            _, tp, val, off = c.data.split('_',3)
            off = int(off)
            items = get_items(tp, val)
            send10(c.message.chat.id, items, lang, off)
            if off+10 < len(items):
                mk = InlineKeyboardMarkup()
                mk.add(InlineKeyboardButton(TEXTS[lang]['more'], callback_data=f"more_{tp}_{val}_{off+10}"))
                bot.send_message(c.message.chat.id, f"{off+10} {TEXTS[lang]['of']} {len(items)}", reply_markup=mk)

        bot.answer_callback_query(c.id)
    except Exception as e:
        print(e)

if __name__ == '__main__':
    print(f"Бот живой. Слушаю группу {GROUP_ID}")
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print("Перезапуск через 15 сек...", e)
            time.sleep(15)
