
import logging
import os
import json
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- Configuration (Keep your existing details) ---
# BOT_TOKEN = "7354766103:AAFu_DkY0U4NJTjH0PMERZIX5p5RyZ7XBKw"
# MANAGER_CHAT_ID = "7790957691"

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
MANAGER_CHAT_ID = os.environ.get("MANAGER_CHAT_ID")

# !!! IMPORTANT: Make sure this is your correct GitHub Pages URL !!!
MINI_APP_URL = "https://halgurdkheralla.github.io/telegrambot/"

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- Bot Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message with a button to launch the Mini App."""
    keyboard = [[
        InlineKeyboardButton(
            "📋 Open Order Form", 
            web_app=WebAppInfo(url=MINI_APP_URL)
        )
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Welcome to our ordering system!\n\n"
        "Click the button below to open our interactive order form.",
        reply_markup=reply_markup
    )

async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processes the data sent from the Mini App."""
    try:
        data = json.loads(update.message.web_app_data.data)
        logger.info(f"Received web app data: {data}")

        name = data.get('name')
        phone = data.get('phone')
        address = data.get('address')
        order_details = data.get('order')

        await update.message.reply_text(
            f"Thank you, {name}! Your order has been received and is being processed.\n\n"
            "We will contact you shortly for confirmation."
        )

        # --- ROBUSTNESS IMPROVEMENT: Handle users without a username ---
        username = f"@{update.effective_user.username}" if update.effective_user.username else "Not available"

        manager_message = (
            f"🎉 New Mini App Order Received! 🎉\n\n"
            f"--- Customer Details ---\n"
            f"👤 Name: {name}\n"
            f"📞 Phone: {phone}\n"
            f"🏠 Address: {address}\n\n"
            f"--- Order Details ---\n"
            f"{order_details}\n\n"
            f"--- Telegram Info ---\n"
            f"User ID: {update.effective_user.id}\n"
            f"Username: {username}"
        )
    
        await context.bot.send_message(chat_id=MANAGER_CHAT_ID, text=manager_message)

    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Error processing web app data: {e}")
        await update.message.reply_text("Sorry, there was an error processing your order. Please try again.")


# --- NEW DEBUGGING FUNCTION ---
async def log_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Logs the full update object to see everything the bot receives."""
    logger.info(f"--- Full Update Received ---\n{update}\n--------------------------")


# --- Main Bot Execution ---
def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(MessageHandler(filters.ALL, log_all_updates), group=-1)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    
    
    print("Bot is running with Mini App support...")
    application.run_polling()

if __name__ == "__main__":
    main()