from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from models.models import BotUser, User
from models.database import SessionLocal
from datetime import datetime
from sqlalchemy import select

def authenticate_user(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not update.effective_user:
            return await func(update, context, bot_user=None, *args, **kwargs)
        
        db = SessionLocal()
        try:
            # Get user from database or create new one
            telegram_id = update.effective_user.id
            stmt = select(BotUser).where(BotUser.telegram_id == telegram_id)
            bot_user = db.scalar(stmt)
            
            if not bot_user:
                # Create new bot user and optionally a linked user
                bot_user, user, _ = BotUser.create_from_telegram(
                    db=db,
                    telegram_user=update.effective_user,
                    password_hash_func=None,
                    create_user=True
                )
                
                db.commit()
            else:
                # Update bot user's last activity
                bot_user.updated_at = datetime.now()
                
                # If username changed, update it
                if bot_user.username != update.effective_user.username:
                    bot_user.username = update.effective_user.username
                    
                    # If user exists, update their username too
                    if bot_user.user:
                        bot_user.user.username = update.effective_user.username
                
                db.commit()
            
            # Pass the authenticated bot_user to the handler
            return await func(update, context, bot_user=bot_user, *args, **kwargs)
        finally:
            db.close()
    
    return wrapper
