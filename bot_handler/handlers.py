import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import ContextTypes
from models.models import BotUser, User, FileTranslation, FileStatus
from .auth import authenticate_user
from sqlalchemy import func
from models.database import async_session
from sqlalchemy.ext.asyncio import AsyncSession
import os, sys, re
import aiohttp
import json
import asyncio
from .translator import SubtitleTranslator

API_KEY = "sk-KAzOhlJGVuYYd4cldtHw-Q"  # Move this to environment variables
API_ENDPOINT = "https://api.morshed.pish.run/v1/chat-messages"
BATCH_SIZE = 10

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Create handlers
console_handler = logging.StreamHandler(sys.stdout)
file_handler = logging.FileHandler('bot.log')

# Set levels
console_handler.setLevel(logging.INFO)
file_handler.setLevel(logging.DEBUG)

# Create formatters and add it to handlers
log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(log_format)
file_handler.setFormatter(log_format)

# Add handlers to the logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)

CLEANER = re.compile('<.*?>') 

def clean_html(raw_html):
    """Remove HTML tags from text"""
    clean_text = re.sub(CLEANER, '', raw_html)
    return clean_text

@authenticate_user
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, bot_user: BotUser = None):
    """Handler for /start command"""
    logger.info(f"Start command received from user {update.effective_user.id}")
    await update.message.reply_text(
        f"سلام {update.effective_user.first_name}! به ربات خوش آمدید."
    )

@authenticate_user
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, bot_user: BotUser = None):
    """Handler for regular messages"""
    logger.info(f"Message received from user {update.effective_user.id}: {update.message.text}")
    await update.message.reply_text(update.message.text)

@authenticate_user
async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, bot_user: BotUser = None):
    """Handler for /stats command - shows total number of users"""
    logger.info(f"Stats command received from user {update.effective_user.id}")
    async with async_session() as session:
        try:
            total_users = await session.scalar(func.count(BotUser.id))
            logger.debug(f"Total users: {total_users}")
            await update.message.reply_text(f"تعداد کل کاربران: {total_users}")
        finally:
            pass

def count_translatable_lines(lines):
    """Count lines that need translation (excluding timestamps and numbers)"""
    translatable_lines = 0
    for line in lines:
        line = line.strip()
        if '-->' in line:
            translatable_lines += 1
    return translatable_lines

@authenticate_user
async def srt_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, bot_user: BotUser = None):
    """Handle uploaded SRT files"""
    try:
        file = update.message.document
        if not file.file_name.lower().endswith('.srt'):
            await update.message.reply_text("❌ فایل باید با پسوند .srt باشد")
            return

        # Download and process the file
        new_file = await context.bot.get_file(file.file_id)
        downloaded_file = await new_file.download_as_bytearray()
        
        # Convert bytes to string and split into lines
        content = downloaded_file.decode('utf-8', errors='ignore')
        lines = content.split('\n')
        
        # Count translatable lines
        translatable_lines = count_translatable_lines(lines)
        if translatable_lines == 0:
            await update.message.reply_text("❌ هیچ متن قابل ترجمه‌ای در فایل یافت نشد")
            return
        
        # Calculate estimated price (200 Toman per line)
        price_unit = 200  # Toman per line
        price_toman = translatable_lines * price_unit
        price_thousand_toman = price_toman / 1000

        # Store file information in database
        async with async_session() as session:
            try:
                async with session.begin():
                    file_translation = await FileTranslation.create_from_telegram(
                        db=session,
                        user_id=bot_user.user_id,
                        input_file_id=file.file_id,
                        total_lines=translatable_lines,
                        price_unit=price_unit,
                        file_name=file.file_name
                    )
                    
                    # Create inline keyboard
                    keyboard = [
                        [InlineKeyboardButton("✅ بله، شروع ترجمه", callback_data=f"start_translation:{file_translation.id}")],
                        [InlineKeyboardButton("❌ انصراف", callback_data=f"cancel_translation:{file_translation.id}")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await update.message.reply_text(
                        f"📄 برآورد هزینه ترجمه:\n\n"
                        f"نام فایل: {file.file_name}\n"
                        f"تعداد خطوط قابل ترجمه: {translatable_lines}\n"
                        f"هزینه تخمینی: {price_thousand_toman:,.1f} هزار تومان\n\n"
                        f"آیا مایل به شروع ترجمه هستید؟",
                        reply_markup=reply_markup
                    )
            except Exception as e:
                logger.error(f"Error creating file translation: {str(e)}")
                await update.message.reply_text("❌ خطا در ذخیره‌سازی فایل")
                raise

    except Exception as e:
        logger.error(f"Error processing file for user {update.effective_user.id}: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ خطا در پردازش فایل: {str(e)}")

async def translate_batch(lines: list[str]) -> list[str]:
    """Translate a batch of subtitle lines"""
    logger.debug(f"Translating batch of {len(lines)} lines")
    # Join lines with delimiter
    text = "[DELIMITER]".join(lines)
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "inputs": {},
        "query": text,
        "response_mode": "blocking",
        "conversation_id": "",
        "user": "abc-123",
        "files": [{}]
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            logger.debug("Sending request to translation API")
            async with session.post(API_ENDPOINT, headers=headers, json=payload) as response:
                if response.status != 200:
                    error_msg = f"API request failed with status {response.status}"
                    logger.error(error_msg)
                    raise Exception(error_msg)
                
                data = await response.json()
                if "answer" not in data:
                    error_msg = "Invalid API response"
                    logger.error(error_msg)
                    raise Exception(error_msg)
                
                # Split the translated text back into lines
                translated_lines = data["answer"].split("[DELIMITER]")
                total_price = float(data["metadata"]["usage"]["total_price"])
                
                logger.debug(f"Successfully translated batch. Price: ${total_price}")
                return translated_lines, total_price
    except Exception as e:
        logger.error(f"Error in translate_batch: {str(e)}", exc_info=True)
        raise

def extract_text_from_srt(lines: list[str]) -> list[tuple[int, str]]:
    """Extract text lines from SRT content, returning (line_number, text) pairs"""
    text_lines = []
    current_line = 0
    
    for i, line in enumerate(lines):
        line = line.strip()
        # Skip empty lines, numbers, and timestamp lines
        if (not line or 
            line.isdigit() or 
            re.match(r'\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}', line)):
            continue
        # Clean any HTML tags from the text
        cleaned_line = clean_html(line)
        if cleaned_line:  # Only add if there's text after cleaning
            text_lines.append((i, cleaned_line))
    
    return text_lines

def replace_lines_in_srt(original_lines: list[str], translations: list[tuple[int, str]]) -> list[str]:
    """Replace original lines with translations"""
    new_lines = original_lines.copy()
    for line_num, translation in translations:
        new_lines[line_num] = translation
    return new_lines

async def process_translation(update: Update, context: ContextTypes.DEFAULT_TYPE, progress_message: Message=None):
    """Process the translation of a subtitle file"""
    try:
        # Get file_id from callback data
        query = update.callback_query
        action, file_id = query.data.split(':')
        file_id = int(file_id)
        
        # Create async session
        async with async_session() as session:
            async with session.begin():
                # Get file from database
                file = await session.get(FileTranslation, file_id)
                if not file:
                    await progress_message.edit_text("Error: File not found 😕")
                    return
                
                # Read file content
                new_file = await context.bot.get_file(file.input_file_id)
                downloaded_file = await new_file.download_as_bytearray()
                
                # Convert bytes to string
                file_content = downloaded_file.decode('utf-8', errors='ignore')
                
                # Initialize translator with the new endpoint
                translator = SubtitleTranslator(
                    api_key="app-hXFNJRVr9Y6AjZXCRGdns3AN",
                    base_url="https://api.morshed.pish.run/v1"
                )
                
                try:
                    logger.info(f'Going to translate file {file.id} for user {file.user_id}')
                    # Parse SRT content
                    subtitles = await translator.parse_srt_content(file_content)
                    file.status = FileStatus.PROCESSING
                    await session.commit()
                    # Progress callback
                    async def progress_callback(progress):
                        try:
                            await progress_message.edit_text(f"Translation in progress: {int(progress)}% complete... ⏳")
                        except Exception as e:
                            logger.error(f"Progress callback error: {str(e)}")
                    
                    # Translate subtitles
                    logger.info(f'Translating subtitles for file {file.id}')
                    translated_subtitles = await translator.translate_all_subtitles(
                        subtitles,
                        progress_callback=progress_callback
                    )
                    
                    # Compose translated SRT
                    logger.info(f'Composing translated content for file {file.id}')
                    translated_content = translator.compose_srt(translated_subtitles)
                    
                    # Calculate total cost
                    total_cost = translator.calculate_cost_toman(file.price_unit)
                    
                    # Send the translated file
                    logger.info(f'Sending translated file {file.id}')
                    send_file = await context.bot.send_document(
                        chat_id=query.message.chat_id,
                        document=translated_content.encode('utf-8'),
                        filename=f"{file.file_name.replace('.srt', '')}_translated.srt",
                        caption=f"✅ Translation completed!\nCost: {total_cost:,.0f} Toman"
                    )
                    
                    # Update file translation record
                    file.status = FileStatus.COMPLETED
                    file.output_file_id = send_file.document.file_id
                    file.total_token_used = translator.total_lines
                    file.total_cost = total_cost
                    await session.commit()
                    
                    await progress_message.edit_text("✅ Translation completed!")
                    
                except Exception as e:
                    logger.error(f"Translation error: {str(e)}")
                    await progress_message.edit_text(f"❌ Translation failed: {str(e)}")
                    raise
                    
    except Exception as e:
        raise e
        logger.error(f"Process translation error: {str(e)}")
        await progress_message.edit_text(f"❌ Translation failed: {str(e)}")

@authenticate_user
async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, bot_user: BotUser = None):
    """Handle button callbacks for translation confirmation"""
    query = update.callback_query
    await query.answer()

    # Extract action and file_translation_id from callback data
    action, file_translation_id = query.data.split(":")
    file_translation_id = int(file_translation_id)
    
    logger.info(f"Button callback received: action={action}, file_id={file_translation_id}, user={update.effective_user.id}")

    async with async_session() as session:
        try:
            async with session.begin():
                file_translation = await session.get(FileTranslation, file_translation_id)
                if not file_translation:
                    logger.warning(f"File translation {file_translation_id} not found for user {update.effective_user.id}")
                    await query.edit_message_text("❌ خطا: فایل مورد نظر یافت نشد.")
                    return

                if action == "cancel_translation":
                    logger.info(f"Cancelling translation for file {file_translation_id}")
                    file_translation.status = FileStatus.CANCELLED
                    await session.commit()
                    await query.edit_message_text("❌ درخواست ترجمه لغو شد.")
                    # Clear stored file data
                    context.user_data.pop('current_file_id', None)
                    context.user_data.pop('file_lines', None)
                    context.user_data.pop('translatable_lines', None)
                    
                elif action == "start_translation":
                    logger.info(f"Starting translation process for file {file_translation_id}")
                    # Send initial progress message
                    progress_message = await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="در حال شروع ترجمه..."
                    )
                    
                    # Update original message
                    # await query.edit_message_text("✅ درخواست ترجمه ثبت شد.")
                    
                    # Start translation in background
                    asyncio.create_task(
                        process_translation(
                            update=update,
                            context=context,
                            progress_message=progress_message
                        )
                    )

        except Exception as e:
            logger.error(f"Error in button_callback_handler: {str(e)}", exc_info=True)
            await query.edit_message_text(f"❌ خطا در پردازش درخواست: {str(e)}")
