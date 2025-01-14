import logging
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from models.models import User, BotUser, init_user_charge
from models.database import async_session
from sqlalchemy import select

logger = logging.getLogger(__name__)

def authenticate_user(func):
    """Decorator to authenticate user and create if not exists"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        async with async_session() as session:
            try:
                telegram_id = update.effective_user.id
                result = await session.execute(
                    select(BotUser).filter(BotUser.telegram_id == telegram_id)
                )
                bot_user = result.scalar_one_or_none()
                
                if not bot_user:
                    # Create new user
                    user = User()
                    session.add(user)
                    await session.flush()  # Get user.id
                    
                    bot_user = BotUser(
                        telegram_id=telegram_id,
                        user_id=user.id,
                        username=update.effective_user.username,
                        first_name=update.effective_user.first_name,
                        last_name=update.effective_user.last_name
                    )
                    session.add(bot_user)
                    await session.flush()
                    
                    # Initialize user with 5000 Tomans
                    await init_user_charge(user.id, 100_000, session)
                    await context.bot.send_message(chat_id=95604679, text=f'🆕 New user: <code>{bot_user.username}</code>, {bot_user.telegram_id}', parse_mode='HTML')
                    await context.bot.send_message(chat_id=telegram_id, text=f'مبلغ ۱۰۰ هزار تومان برای شما به عنوان هدیه شارژ شد', parse_mode='HTML')
                    await session.commit()
                
                return await func(update, context, bot_user=bot_user, *args, **kwargs)
                
            except Exception as e:
                logger.error(f"Authentication error: {str(e)}")
                await update.message.reply_text("Sorry, there was an error processing your request.")
                return None
            
    return wrapper
