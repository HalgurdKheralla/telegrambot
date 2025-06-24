import os
import logging
import asyncio
import threading
import time
import shutil

# --- This must be at the very top ---
# In a WSGI server, we need to manage the asyncio event loop manually.
# We create one persistent loop for the entire application lifetime.
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

from flask import Flask, request, send_from_directory
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
from telegram.request import HTTPXRequest as TelegramHTTPXRequest
import yt_dlp

# --- CONFIGURATION ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
HOST_URL = os.environ.get("HOST_URL").rstrip('/')
DOWNLOAD_FOLDER = "/tmp/"

# --- VALIDATION ---
if not BOT_TOKEN or not HOST_URL:
    raise ValueError("FATAL ERROR: BOT_TOKEN or HOST_URL environment variables not set!")

# --- LOGGING SETUP ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def ensure_cookies_in_tmp():
    src = os.path.join(os.path.dirname(__file__), 'cookies.txt')
    dst = '/tmp/cookies.txt'
    if not os.path.exists(dst):
        try:
            shutil.copyfile(src, dst)
        except Exception as e:
            logger.error(f'Could not copy cookies.txt to /tmp: {e}')


# --- BOT HANDLER FUNCTIONS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}! I'm alive! Send me a YouTube link.",
    )

def cleanup_file(file_path: str, delay: int = 1800):
    time.sleep(delay)
    try:
        os.remove(file_path)
        logger.info(f"Cleaned up {file_path}")
    except OSError as e:
        logger.error(f"Error cleaning up file {file_path}: {e}")

async def show_quality_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ensure_cookies_in_tmp()
    status_message = await update.message.reply_text("Fetching available qualities...")
    try:
        video_url = update.message.text
        ydl_opts = {
            'noplaylist': True,
            'quiet': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'cookiefile': '/tmp/cookies.txt',
            'updatetime': False
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
        
        video_id = info.get('id')
        title = info.get('title')
        formats = info.get('formats', [])
        unique_formats = {}
        for f in formats:
            if f.get('vcodec') != 'none' and f.get('acodec') == 'none' and f.get('ext') == 'mp4' and f.get('filesize'):
                height = f.get('height')
                if height and height not in unique_formats:
                     unique_formats[height] = f
        
        sorted_formats = sorted(unique_formats.values(), key=lambda x: x['height'], reverse=True)
        if not sorted_formats:
            await status_message.edit_text("Sorry, I couldn't find any downloadable mp4 video formats.")
            return

        keyboard = []
        for f in sorted_formats:
            callback_data = f"quality:{f['format_id']}:{video_id}"
            filesize_mb = f['filesize'] / 1024 / 1024
            button_text = f"{f['height']}p - {filesize_mb:.1f} MB"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await status_message.edit_text(f"Please choose a quality for '{title}':", reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Error fetching formats for {video_url}: {e}")
        await status_message.edit_text("An error occurred while fetching formats. The link might be invalid or private.")


async def download_chosen_quality(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ensure_cookies_in_tmp()
    query = update.callback_query
    await query.answer()
    data_parts = query.data.split(':')
    action, format_id, video_id = data_parts
    if action == 'quality':
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        await query.edit_message_text(text=f"Great choice! Processing download...")
        try:
            output_template = os.path.join(DOWNLOAD_FOLDER, '%(title)s - %(height)sp.%(ext)s')
            ydl_opts = {
                'format': f'{format_id}+bestaudio/best',
                'outtmpl': output_template,
                'merge_output_format': 'mp4',
                'noplaylist': True,
                'quiet': True,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'cookiefile': '/tmp/cookies.txt',
                'updatetime': False
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                filename = ydl.prepare_filename(info)
            
            base_filename = os.path.basename(filename)
            download_url = f"{HOST_URL}/downloads/{base_filename}"
            keyboard = [[InlineKeyboardButton("✅ Download Video", url=download_url)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.reply_text(
                f"'{info['title']}' is ready!\n\nClick the button below to download.",
                reply_markup=reply_markup
            )
            threading.Thread(target=cleanup_file, args=(filename,), daemon=True).start()
        except Exception as e:
            logger.error(f"Error during download: {e}")
            await query.edit_message_text("An error occurred during the download process.")


# --- SETUP BOT AND FLASK ---

# Use default request object (no proxy)
ptb_app = Application.builder().token(BOT_TOKEN).build()

# Add all handlers
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex(r'http[s]?://'), show_quality_options))
ptb_app.add_handler(CallbackQueryHandler(download_chosen_quality))

# Use the managed event loop to run the one-time initialization
loop.run_until_complete(ptb_app.initialize())

# Create the flask app
flask_app = Flask(__name__)

@flask_app.route("/")
def index():
    return "<h1>Congratulations! The Bot's Web Server is running!</h1>"

@flask_app.route('/downloads/<path:filename>')
def download_file(filename):
    return send_from_directory(DOWNLOAD_FOLDER, filename, as_attachment=True)

@flask_app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    """A synchronous webhook that uses the managed event loop to process updates."""
    update_data = request.get_json()
    update = Update.de_json(data=update_data, bot=ptb_app.bot)
    
    # Use the managed event loop to run the async process_update function
    loop.run_until_complete(ptb_app.process_update(update))
    
    return "ok", 200
