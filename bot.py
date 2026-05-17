import asyncio
import logging
import os
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, ContextTypes, filters
from telegram.request import HTTPXRequest

# ============================================================
# 🔑 ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ (НЕ ВШИТЫ В КОД)
# ============================================================
TELEGRAM_TOKEN = os.environ.get('8771269443:AAHEk-qiVy7ebt0E7frFSBMT_rN27Olghk0')
GROQ_API_KEY = os.environ.get('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')

# Проверка наличия ключей
if not TELEGRAM_TOKEN:
    logging.error("❌ Переменная окружения TELEGRAM_TOKEN не установлена!")
    exit(1)
if not GROQ_API_KEY:
    logging.error("❌ Переменная окружения GROQ_API_KEY не установлена!")
    exit(1)

# Настройки Groq
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "llama-3.1-8b-instant"

# ============================================================
# 🔧 НАСТРОЙКА ЛОГИРОВАНИЯ
# ============================================================
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

# ============================================================
# 🤖 ИНИЦИАЛИЗАЦИЯ GROQ
# ============================================================
groq_client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)
log.info(f"✅ Groq инициализирован. Модель: {GROQ_MODEL}")

# ============================================================
# 🌐 НАСТРОЙКА TELEGRAM
# ============================================================
request = HTTPXRequest(
    connection_pool_size=8,
    connect_timeout=60.0,
    read_timeout=60.0,
)

# ============================================================
# ✂️ ФУНКЦИЯ РАЗБИВКИ ДЛИННЫХ СООБЩЕНИЙ
# ============================================================
async def send_long_message(message_obj, text, reply_markup=None):
    MAX_LEN = 4000
    if len(text) <= MAX_LEN:
        await message_obj.reply_text(text=text, parse_mode="Markdown", reply_markup=reply_markup)
        return
    parts = []
    current_part = ""
    for line in text.split('\n'):
        if len(current_part) + len(line) + 1 <= MAX_LEN:
            current_part += line + '\n'
        else:
            if current_part:
                parts.append(current_part.strip())
            current_part = line + '\n'
    if current_part:
        parts.append(current_part.strip())
    for i, part in enumerate(parts):
        markup = reply_markup if i == 0 else None
        if len(parts) > 1:
            part = f"📄 *Часть {i+1}/{len(parts)}*\n\n{part}"
        await message_obj.reply_text(text=part, parse_mode="Markdown", reply_markup=markup)

# ============================================================
# 📝 ПЕРЕВОДЫ
# ============================================================
STR = {
    "ru": {
        "welcome": "👋 Добро пожаловать!\n🤖 Модель: **Groq Llama 3.1**\n📊 Лимит: 14 400 запросов/день\n\nВыберите язык:",
        "lang_ok": "✅ Язык: Русский",
        "choose_type": "📝 Выберите тип поста:",
        "type_chosen": "✅ Тип: *{type_name}*\n\n✏️ Введите тему:",
        "bad_topic": "❌ Введите тему.",
        "ask_details": "📋 Детали? /skip",
        "summary": "📋 *Итог*\n• Тип: {type_name}\n• Тема: {topic}\n• Детали: {details}\n\n✨ Генерировать?",
        "gen_btn": "✅ Генерировать",
        "restart_btn": "🔄 Сначала",
        "regen_btn": "🔁 Ещё раз",
        "new_btn": "✏️ Новый пост",
        "generating": "⏳ Groq пишет...",
        "result": "✨ *Пост:*\n\n{post}",
        "err": "❌ Ошибка: {error}",
        "new_head": "🆕 Новый пост!",
        "help": "Команды: /start, /new, /lang, /help",
        "types": {"NEWS": "📰 Новость", "PROMO": "🎯 Реклама", "EDUCATIONAL": "📚 Обучение", "MOTIVATIONAL": "💡 Мотивация", "STORY": "✍️ История", "PRODUCT": "🛍️ Продукт"},
        "ai_lang": "Напиши пост на русском. 200-300 слов.",
    },
    "en": {
        "welcome": "👋 Welcome!\n🤖 Model: **Groq Llama 3.1**\n📊 Limit: 14,400 requests/day\n\nSelect language:",
        "lang_ok": "✅ Language: English",
        "choose_type": "📝 Choose post type:",
        "type_chosen": "✅ Type: *{type_name}*\n\n✏️ Enter topic:",
        "bad_topic": "❌ Enter a topic.",
        "ask_details": "📋 Details? /skip",
        "summary": "📋 *Summary*\n• Type: {type_name}\n• Topic: {topic}\n• Details: {details}\n\n✨ Generate?",
        "gen_btn": "✅ Generate",
        "restart_btn": "🔄 Restart",
        "regen_btn": "🔁 Regenerate",
        "new_btn": "✏️ New post",
        "generating": "⏳ Groq is writing...",
        "result": "✨ *Post:*\n\n{post}",
        "err": "❌ Error: {error}",
        "new_head": "🆕 New post!",
        "help": "Commands: /start, /new, /lang, /help",
        "types": {"NEWS": "📰 News", "PROMO": "🎯 Promo", "EDUCATIONAL": "📚 Educational", "MOTIVATIONAL": "💡 Motivational", "STORY": "✍️ Story", "PRODUCT": "🛍️ Product"},
        "ai_lang": "Write a post in English. 200-300 words.",
    },
}

def get_text(ctx, key, **kwargs):
    lang = ctx.user_data.get("lang", "ru")
    text = STR[lang].get(key, "")
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            return text
    return text

# Состояния
LANG, TYPE, TOPIC, DETAILS, CONFIRM, RESULT = range(6)

# ============================================================
# 🧠 ГЕНЕРАЦИЯ ПОСТА
# ============================================================
SYSTEM_PROMPT = "Ты — автор постов для Telegram. Пиши живо, с эмодзи, короткими абзацами, в конце 3-5 хэштегов. 200-300 слов."

async def generate_post(post_type, topic, details, language):
    user_prompt = f"{language}\n\n{post_type}\nТема: {topic}\nДетали: {details or 'нет'}\n\nНапиши пост."
    response = await asyncio.to_thread(
        groq_client.chat.completions.create,
        model=GROQ_MODEL,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
        max_tokens=1200,
        temperature=0.8,
    )
    return response.choices[0].message.content.strip()

# ============================================================
# 🎹 КЛАВИАТУРЫ
# ============================================================
def get_lang_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🇷🇺 Русский", callback_data="lang:ru"),
        InlineKeyboardButton("🇬🇧 English", callback_data="lang:en"),
    ]])

def get_types_keyboard(ctx):
    lang = ctx.user_data.get("lang", "ru")
    buttons = [[InlineKeyboardButton(label, callback_data=f"type:{key}")] for key, label in STR[lang]["types"].items()]
    return InlineKeyboardMarkup(buttons)

def get_confirm_keyboard(ctx):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(get_text(ctx, "gen_btn"), callback_data="confirm:yes"),
        InlineKeyboardButton(get_text(ctx, "restart_btn"), callback_data="confirm:restart"),
    ]])

def get_after_keyboard(ctx):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(get_text(ctx, "regen_btn"), callback_data="after:regen"),
        InlineKeyboardButton(get_text(ctx, "new_btn"), callback_data="after:new"),
    ]])

# ============================================================
# 🎯 ОБРАБОТЧИКИ
# ============================================================
async def cmd_start(update, ctx):
    ctx.user_data.clear()
    await update.message.reply_text(STR["ru"]["welcome"], parse_mode="Markdown", reply_markup=get_lang_keyboard())
    return LANG

async def cmd_lang(update, ctx):
    await update.message.reply_text("Выберите язык:", reply_markup=get_lang_keyboard())
    return LANG

async def cb_lang(update, ctx):
    q = update.callback_query
    await q.answer()
    lang = q.data.split(":")[1]
    ctx.user_data["lang"] = lang
    await q.edit_message_text(STR[lang]["lang_ok"])
    await q.message.reply_text(get_text(ctx, "choose_type"), reply_markup=get_types_keyboard(ctx))
    return TYPE

async def cb_type(update, ctx):
    q = update.callback_query
    await q.answer()
    type_key = q.data.split(":")[1]
    lang = ctx.user_data.get("lang", "ru")
    type_name = STR[lang]["types"][type_key]
    ctx.user_data["type_name"] = type_name
    await q.edit_message_text(get_text(ctx, "type_chosen", type_name=type_name))
    return TOPIC

async def on_topic(update, ctx):
    topic = update.message.text.strip()
    if not topic:
        await update.message.reply_text(get_text(ctx, "bad_topic"))
        return TOPIC
    ctx.user_data["topic"] = topic
    await update.message.reply_text(get_text(ctx, "ask_details"))
    return DETAILS

async def on_details(update, ctx):
    ctx.user_data["details"] = update.message.text.strip()
    return await show_summary(update, ctx)

async def on_skip(update, ctx):
    ctx.user_data["details"] = ""
    return await show_summary(update, ctx)

async def show_summary(update, ctx):
    data = ctx.user_data
    text = get_text(ctx, "summary", type_name=data["type_name"], topic=data["topic"], details=data.get("details", "—") or "—")
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_confirm_keyboard(ctx))
    return CONFIRM

async def cb_confirm(update, ctx):
    q = update.callback_query
    await q.answer()
    action = q.data.split(":")[1]
    if action == "restart":
        lang = ctx.user_data.get("lang", "ru")
        ctx.user_data.clear()
        ctx.user_data["lang"] = lang
        await q.edit_message_text("🔄 Начинаем сначала...")
        await q.message.reply_text(get_text(ctx, "choose_type"), reply_markup=get_types_keyboard(ctx))
        return TYPE
    await q.edit_message_text(get_text(ctx, "generating"))
    try:
        lang = ctx.user_data.get("lang", "ru")
        post = await generate_post(ctx.user_data["type_name"], ctx.user_data["topic"], ctx.user_data.get("details", ""), STR[lang]["ai_lang"])
        result_text = get_text(ctx, "result", post=post)
        await send_long_message(q.message, result_text, reply_markup=get_after_keyboard(ctx))
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg:
            error_msg = "Превышен лимит Groq API (14 400 запросов/день)"
        await q.message.reply_text(get_text(ctx, "err", error=error_msg[:200]), parse_mode="Markdown")
    return RESULT

async def cb_after(update, ctx):
    q = update.callback_query
    await q.answer()
    action = q.data.split(":")[1]
    if action == "new":
        lang = ctx.user_data.get("lang", "ru")
        ctx.user_data.clear()
        ctx.user_data["lang"] = lang
        await q.edit_message_reply_markup(reply_markup=None)
        await q.message.reply_text(get_text(ctx, "new_head"), reply_markup=get_types_keyboard(ctx))
        return TYPE
    await q.edit_message_text(get_text(ctx, "regenerating"))
    try:
        lang = ctx.user_data.get("lang", "ru")
        post = await generate_post(ctx.user_data["type_name"], ctx.user_data["topic"], ctx.user_data.get("details", ""), STR[lang]["ai_lang"])
        result_text = get_text(ctx, "result", post=post)
        await send_long_message(q.message, result_text, reply_markup=get_after_keyboard(ctx))
    except Exception as e:
        await q.message.reply_text(get_text(ctx, "err", error=str(e)[:200]), parse_mode="Markdown")
    return RESULT

async def cmd_new(update, ctx):
    lang = ctx.user_data.get("lang")
    if not lang:
        return await cmd_start(update, ctx)
    ctx.user_data.clear()
    ctx.user_data["lang"] = lang
    await update.message.reply_text(get_text(ctx, "new_head"), reply_markup=get_types_keyboard(ctx))
    return TYPE

async def cmd_help(update, ctx):
    await update.message.reply_text(get_text(ctx, "help"), parse_mode="Markdown")

async def fallback(update, ctx):
    await update.message.reply_text(get_text(ctx, "fallback"))

# ============================================================
# 🚀 ЗАПУСК
# ============================================================
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).request(request).build()
    
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start), CommandHandler("new", cmd_new), CommandHandler("lang", cmd_lang)],
        states={
            LANG: [CallbackQueryHandler(cb_lang, pattern=r"^lang:")],
            TYPE: [CallbackQueryHandler(cb_type, pattern=r"^type:")],
            TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_topic)],
            DETAILS: [CommandHandler("skip", on_skip), MessageHandler(filters.TEXT & ~filters.COMMAND, on_details)],
            CONFIRM: [CallbackQueryHandler(cb_confirm, pattern=r"^confirm:")],
            RESULT: [CallbackQueryHandler(cb_after, pattern=r"^after:")],
        },
        fallbacks=[CommandHandler("start", cmd_start), CommandHandler("new", cmd_new), CommandHandler("lang", cmd_lang), MessageHandler(filters.ALL, fallback)],
    )
    
    app.add_handler(conv)
    app.add_handler(CommandHandler("help", cmd_help))
    
    log.info("🚀 БОТ ЗАПУЩЕН! Модель: %s", GROQ_MODEL)
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()