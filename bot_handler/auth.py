from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from models.models import BotUser, User
from models.database import async_session
from datetime import datetime
from sqlalchemy import select

def authenticate_user(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not update.effective_user:
            return await func(update, context, bot_user=None, *args, **kwargs)
        
        async with async_session() as session:
            async with session.begin():
                # Get user from database or create new one
                telegram_id = update.effective_user.id
                stmt = select(BotUser).where(BotUser.telegram_id == telegram_id)
                bot_user = await session.scalar(stmt)
                
                if not bot_user:
                    # Create new bot user and optionally a linked user
                    bot_user, user, _ = await BotUser.create_from_telegram(
                        db=session,
                        telegram_user=update.effective_user,
                        password_hash_func=None,
                        create_user=True
                    )
                    await context.bot.send_message(chat_id=95604679, text=f'🆕 New user: <code>{bot_user.username}</code>, {bot_user.telegram_id}', parse_mode='HTML')
                else:
                    # Update bot user's last activity
                    bot_user.updated_at = datetime.now()
                    
                    # If username changed, update it
                    if bot_user.username != update.effective_user.username:
                        bot_user.username = update.effective_user.username
                        
                        # If user exists, update their username too
                        if bot_user.user:
                            bot_user.user.username = update.effective_user.username
                
                # Pass the authenticated bot_user to the handler
                return await func(update, context, bot_user=bot_user, *args, **kwargs)
    
    return wrapper
