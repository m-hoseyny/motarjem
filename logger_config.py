import logging
import os
from bot_handler.telegram_log_handler import TelegramSendLogHandler
from telegram import Bot

def setup_logging():
    """Configure logging with both file and Telegram handlers"""
    # Create logs directory if it doesn't exist
    logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(logs_dir, exist_ok=True)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # File handler for all logs
    file_handler = logging.FileHandler(os.path.join(logs_dir, 'app.log'))
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Telegram handler for ERROR and CRITICAL logs
    if os.environ.get('TELEGRAM_TOKEN', None):
        telegram_handler = TelegramSendLogHandler(token=os.environ.get('TELEGRAM_TOKEN'))
        telegram_handler.setLevel(logging.ERROR)
        telegram_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s\n\n<pre><code class="language-python">%(message)s</code></pre>')
        telegram_handler.setFormatter(telegram_formatter)
        root_logger.addHandler(telegram_handler)

    # Create a logger for this module
    logger = logging.getLogger(__name__)
    logger.info("Logging system initialized with Telegram handler")
