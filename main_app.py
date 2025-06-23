import os
import logging
import threading
import time
import asyncio
from flask import Flask, send_from_directory
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- CONFIGURATION ---
# BOT_TOKEN = "7927259172:AAHU0koa3rEgPkFnyhPcenaHeb-oahIyvAo"  # IMPORTANT: Make sure this is your correct token
# HOST_URL = "https://strong-crabs-follow.loca.lt" # Replace with your current localtunnel URL
# DOWNLOAD_FOLDER = "downloads"

BOT_TOKEN = os.environ.get("BOT_TOKEN")
HOST_URL = os.environ.get("HOST_URL")
DOWNLOAD_FOLDER = "downloads"

# --- FLASK WEB SERVER SETUP ---
app = Flask(__name__)

@app.route("/")
def index():
    return "<h1>Web Server is Alive!</h1>"

@app.route('/downloads/<path:filename>')
def download_file(filename):
    return send_from_directory(DOWNLOAD_FOLDER, filename, as_attachment=True)

# --- TELEGRAM BOT SETUP ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        rf"سڵاو {user.mention_html()}! لینکی یوتیوبەکەت بنێرە بۆ داگرتن.",
    )

def cleanup_file(file_path: str, delay: int = 1800):
    time.sleep(delay)
    try:
        os.remove(file_path)
        logger.info(f"Cleaned up {file_path}")
    except OSError as e:
        logger.error(f"Error cleaning up file {file_path}: {e}")

async def handle_youtube_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    NEW: This function now only fetches formats and shows a quality selection menu.
    """
    video_url = update.message.text
    await update.message.reply_text("پشاندانی کوالیتیەکان...")

    try:
        ydl_opts = {'noplaylist': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            video_id = info.get('id')
            title = info.get('title')
        
        # Filter for unique video formats (mp4) and sort by quality
        formats = info.get('formats', [])
        unique_formats = {}
        for f in formats:
            # We only want mp4 video formats with a known file size
            if f.get('vcodec') != 'none' and f.get('acodec') == 'none' and f.get('ext') == 'mp4' and f.get('filesize'):
                height = f.get('height')
                if height and height not in unique_formats:
                     unique_formats[height] = f
        
        # Sort by height (quality) descending
        sorted_formats = sorted(unique_formats.values(), key=lambda x: x['height'], reverse=True)

        if not sorted_formats:
            await update.message.reply_text("ببورە، من هیچ فۆرماتی داگرتنی ڤیدیۆ بۆ ئەم لینکه نابینم، تکایە لینکەکە با دروستی بنێرە.")
            return

        # Create a keyboard button for each quality
        keyboard = []
        for f in sorted_formats:
            # callback_data must be a string. We format it like "quality:format_id:video_id"
            # This gives our button_handler all the info it needs.
            callback_data = f"quality:{f['format_id']}:{video_id}"
            filesize_mb = f['filesize'] / 1024 / 1024
            button_text = f"{f['height']}p - {filesize_mb:.1f} MB"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f" تکایە کوالێتییەک هەڵبژێرە بۆ '{title}':", reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Error handling URL {video_url}: {e}")
        await update.message.reply_text(f"An error occurred while fetching formats: {e}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    NEW: This function handles the button clicks from the quality selection menu.
    """
    query = update.callback_query
    await query.answer() # Acknowledge the button press

    # Parse the data we stored in the button
    data_parts = query.data.split(':')
    action = data_parts[0]
    
    if action == 'quality':
        format_id = data_parts[1]
        video_id = data_parts[2]
        video_url = f"https://www.youtube.com/watch?v=LXb3EKWsInQ "

        await query.edit_message_text(text=f"داگرتنی ڤیدیۆیەکە بە کوالێتی {format_id} دەستپێدەکات...تکایە چاوەڕوان بە.")

        try:
            output_template = os.path.join(DOWNLOAD_FOLDER, '%(title)s - %(height)sp.%(ext)s')
            # The format string now uses the user's chosen format_id + bestaudio
            ydl_opts = {
                'format': f'{format_id}+bestaudio/best',
                'outtmpl': output_template,
                'merge_output_format': 'mp4',
                'noplaylist': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                filename = ydl.prepare_filename(info)
            
            base_filename = os.path.basename(filename)
            download_url = f"{HOST_URL}/downloads/{base_filename}"
            
            # Send a NEW message with the final download link
            keyboard = [[InlineKeyboardButton("✅ داگرتنی ڤیدیۆ", url=download_url)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text(
                f"'{info['title']}' ئامادەیە بۆ داگرتن!\n\nگرتە بکە لەم لینکەی خوارەوە بۆ داگرتنی ڤیدیۆ:\n{download_url}. تکایە ئاگادار بە کە ئەم لینکە لە ٣٠ خولەکدا بەسەردەچێت",
                reply_markup=reply_markup
            )

            cleanup_thread = threading.Thread(target=cleanup_file, args=(filename,))
            cleanup_thread.start()

        except Exception as e:
            logger.error(f"Error during download: {e}")
            await query.message.reply_text(f"An error occurred during download: {e}")

# --- MAIN APPLICATION ---
async def main() -> None:
    if not os.path.exists(DOWNLOAD_FOLDER):
        os.makedirs(DOWNLOAD_FOLDER)

    flask_thread = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=5000), daemon=True)
    flask_thread.start()
    logger.info("Flask web server has started in a background thread.")

    bot_app = Application.builder().token(BOT_TOKEN).build()
    
    # Add all our handlers
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex(r'http[s]?://'), handle_youtube_link))
    
    # NEW: Add the handler for our buttons
    bot_app.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info("Telegram Bot is initializing...")
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()
    logger.info("Telegram Bot has started and is polling for updates.")
    
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
