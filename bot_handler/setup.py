from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from .handlers import start_handler, message_handler, stats_handler, srt_file_handler, button_callback_handler

def setup_handlers(application: Application) -> None:
    """Register all bot handlers"""
    # Add command handlers
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("stats", stats_handler))
    
    # Add file handler for .srt files
    application.add_handler(MessageHandler(
        filters.Document.FileExtension("srt"), 
        srt_file_handler
    ))
    
    # Add callback handler for inline buttons
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    
    # Add general message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # Add more handlers here as needed
