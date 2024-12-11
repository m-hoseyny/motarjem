import os
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from bot_handler.handlers import start_handler, message_handler, stats_handler
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def create_bot_application():
    """Create and configure the bot application"""
    # Get bot token from environment variables
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")

    # Create application
    application = Application.builder().token(bot_token).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("stats", stats_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    return application

def main():
    """Run the bot"""
    app = create_bot_application()
    app.run_polling()

if __name__ == "__main__":
    main()
