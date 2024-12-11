from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from models.models import BotUser, User, FileTranslation, FileStatus
from .auth import authenticate_user
from sqlalchemy import func
from models.database import SessionLocal
import os
import aiohttp
import json
import re
from io import BytesIO
import logging
import sys
from datetime import datetime
import asyncio

API_KEY = "app-hXFNJRVr9Y6AjZXCRGdns3AN"
API_ENDPOINT = "https://api.morshed.pish.run/v1/chat-messages"
BATCH_SIZE = 20

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
    db = SessionLocal()
    try:
        total_users = db.query(func.count(BotUser.id)).scalar()
        logger.debug(f"Total users: {total_users}")
        await update.message.reply_text(f"تعداد کل کاربران: {total_users}")
    finally:
        db.close()

def count_translatable_lines(lines):
    """Count lines that need translation (excluding timestamps and numbers)"""
    translatable_lines = 0
    for line in lines:
        line = line.strip()
        if line and not line.isdigit() and not '-->' in line:
            translatable_lines += 1
    return translatable_lines

@authenticate_user
async def srt_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, bot_user: BotUser = None):
    """Handler for processing .srt files
        This function is going to translate the srt file to persian
        This is going to use a async function to translate with external API
        The price of each line is 200 Toman.
        First, in this function we have to show the user the estimated price.
    """
    logger.info(f"Received file from user {update.effective_user.id}")
    
    # Check if a file was sent
    if not update.message.document:
        logger.warning(f"No document received from user {update.effective_user.id}")
        await update.message.reply_text("لطفاً یک فایل زیرنویس (.srt) ارسال کنید.")
        return

    # Check if it's an .srt file
    file = update.message.document
    if not file.file_name.lower().endswith('.srt'):
        logger.warning(f"Invalid file type received from user {update.effective_user.id}: {file.file_name}")
        await update.message.reply_text("لطفاً فقط فایل‌های زیرنویس (.srt) ارسال کنید.")
        return

    try:
        logger.debug(f"Processing file {file.file_name} for user {update.effective_user.id}")
        # Download the file
        new_file = await context.bot.get_file(file.file_id)
        downloaded_file = await new_file.download_as_bytearray()
        
        # Convert bytes to string and split into lines
        content = downloaded_file.decode('utf-8', errors='ignore')
        lines = content.splitlines()
        
        # Count lines that need translation
        translatable_lines = count_translatable_lines(lines)
        logger.info(f"File {file.file_name} has {translatable_lines} translatable lines")
        
        # Calculate price (200 Toman per line)
        price_toman = translatable_lines * 200
        price_thousand_toman = price_toman / 1000

        # Store file information in database
        db = SessionLocal()
        try:
            file_translation = FileTranslation.create_from_telegram(
                db=db,
                user_id=bot_user.user_id,
                input_file_id=file.file_id,
                total_lines=translatable_lines
            )
            db.commit()
            logger.debug(f"Created FileTranslation record with ID {file_translation.id}")
            
            # Store the file information for later use
            context.user_data['current_file_id'] = file.file_id
            context.user_data['file_lines'] = lines
            context.user_data['translatable_lines'] = translatable_lines
            
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
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error processing file for user {update.effective_user.id}: {str(e)}", exc_info=True)
        await update.message.reply_text(f"خطا در پردازش فایل: {str(e)}")

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

async def process_translation(bot, chat_id: int, progress_message_id: int, file_translation: FileTranslation, db):
    """Process the translation of an SRT file in background"""
    logger.info(f"Starting translation process for file {file_translation.id} in background")
    
    try:
        # Download the file using input_file_id
        logger.debug(f"Downloading file with ID: {file_translation.input_file_id}")
        file = await bot.get_file(file_translation.input_file_id)
        downloaded_file = await file.download_as_bytearray()
        
        # Convert bytes to string and split into lines
        content = downloaded_file.decode('utf-8', errors='ignore')
        lines = content.splitlines()
        
        if not lines:
            error_msg = "File content is empty"
            logger.error(f"Error for file {file_translation.id}: {error_msg}")
            raise Exception(error_msg)

        # Extract text lines that need translation
        text_lines = extract_text_from_srt(lines)
        logger.info(f"Extracted {len(text_lines)} lines for translation from file {file_translation.id}")
        
        total_price = 0
        translated_pairs = []

        # Process in batches
        for i in range(0, len(text_lines), BATCH_SIZE):
            batch = text_lines[i:i + BATCH_SIZE]
            batch_lines = [line for _, line in batch]
            
            # Update progress message
            progress = (i / len(text_lines)) * 100
            logger.info(f"Translation progress for file {file_translation.id}: {progress:.1f}%")
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_message_id,
                text=f"در حال ترجمه... {progress:.1f}% تکمیل شده"
            )
            
            # Translate batch
            translations, batch_price = await translate_batch(batch_lines)
            total_price += batch_price
            
            # Store translations with their line numbers
            for (line_num, _), translation in zip(batch, translations):
                translated_pairs.append((line_num, translation))

        logger.info(f"Completed translation of file {file_translation.id}. Total price: ${total_price}")

        # Replace original lines with translations
        new_lines = replace_lines_in_srt(lines, translated_pairs)
        
        # Create file content
        file_content = "\n".join(new_lines)
        
        # Create file object to send
        bio = BytesIO(file_content.encode('utf-8'))
        bio.name = f"translated_{file_translation.id}.srt"
        
        # Send file to telegram
        logger.debug(f"Sending translated file to chat {chat_id}")
        message = await bot.send_document(
            chat_id=chat_id,
            document=bio
        )
        
        # Update database
        file_translation.output_file_id = message.document.file_id
        file_translation.total_price = total_price
        file_translation.status = FileStatus.COMPLETED
        db.commit()
        logger.info(f"Successfully completed translation for file {file_translation.id}")
        
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=progress_message_id,
            text=f"✅ ترجمه با موفقیت انجام شد!\n"
                 f"هزینه نهایی: ${total_price:.4f}"
        )
        
    except Exception as e:
        logger.error(f"Error in process_translation for file {file_translation.id}: {str(e)}", exc_info=True)
        file_translation.status = FileStatus.FAILED
        db.commit()
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=progress_message_id,
            text=f"❌ خطا در ترجمه: {str(e)}"
        )

@authenticate_user
async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, bot_user: BotUser = None):
    """Handle button callbacks for translation confirmation"""
    query = update.callback_query
    await query.answer()

    # Extract action and file_translation_id from callback data
    action, file_translation_id = query.data.split(":")
    file_translation_id = int(file_translation_id)
    
    logger.info(f"Button callback received: action={action}, file_id={file_translation_id}, user={update.effective_user.id}")

    db = SessionLocal()
    try:
        file_translation = db.query(FileTranslation).filter(FileTranslation.id == file_translation_id).first()
        if not file_translation:
            logger.warning(f"File translation {file_translation_id} not found for user {update.effective_user.id}")
            await query.edit_message_text("❌ خطا: فایل مورد نظر یافت نشد.")
            return

        if action == "cancel_translation":
            logger.info(f"Cancelling translation for file {file_translation_id}")
            file_translation.status = FileStatus.CANCELLED
            db.commit()
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
            await query.edit_message_text("✅ درخواست ترجمه ثبت شد.")
            
            # Start translation in background
            asyncio.create_task(
                process_translation(
                    bot=context.bot,
                    chat_id=update.effective_chat.id,
                    progress_message_id=progress_message.message_id,
                    file_translation=file_translation,
                    db=db
                )
            )

    except Exception as e:
        logger.error(f"Error in button_callback_handler: {str(e)}", exc_info=True)
        await query.edit_message_text(f"❌ خطا در پردازش درخواست: {str(e)}")
    finally:
        if action != "start_translation":  # Keep db session open for background task if starting translation
            db.close()
