import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import ContextTypes
from models.models import BotUser, User, FileTranslation, FileStatus, Transaction, get_user_balance, Invoice, InvoiceTransaction
from .auth import authenticate_user
from sqlalchemy import func, select
from models.database import async_session
from sqlalchemy.ext.asyncio import AsyncSession
import os, sys, re
import aiohttp
import json
import asyncio
from .translator import SubtitleTranslator
from io import BytesIO
import time
import uuid

API_KEY = "app-hXFNJRVr9Y6AjZXCRGdns3AN"  # Move this to environment variables
API_ENDPOINT = "https://api.morshed.pish.run/v1"
WEBHOOK_URL=os.getenv("WEBHOOK_URL")
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
        f"👋 سلام {update.effective_user.first_name}! به ربات خوش آمدید."
        f"\n"
        f"در این ربات شما میتوانید با ارسال فایل srt فایل ترجمه آن را به فارسی دریافت کنید"
        f"\n"
        f"کافی است که فایل srt را برای بات ارسال کنید."
        f"\n"
        f"هزینه هر خط ترجمه در این بات ۲۰۰ تومن در نظر گرفته شده است. قبل از شروع ترجمه شما تخمین هزینه را میبینید"
        f"\n"
        f"برای دریافت موجودی، دستور زیر را بزنید"
        f"\n"
        f"/balance"
        
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
        
        # Check if the user has enough balance
        user_balance_toman = await get_user_balance(bot_user.user_id)
        if user_balance_toman < price_toman:
            await update.message.reply_text("❌ موجودی شما کافی نیست")
            return

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
                        file_name=file.file_name,
                        message_id=update.message.message_id
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


async def process_translation(update: Update, context: ContextTypes.DEFAULT_TYPE, file_id: int):
    try:
        async with async_session() as session:
            start_time = time.time()
            file = await session.get(FileTranslation, file_id)
            if not file:
                logger.error(f"File {file_id} not found")
                return
            
            # Get the file from Telegram
            tg_file = await context.bot.get_file(file.input_file_id)
            file_content = await tg_file.download_as_bytearray()
            file_content = file_content.decode('utf-8')
            
            # Send initial progress message
            print(update.callback_query.message.message_id)
            progress_message = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="🔄 شروع ترجمه...",
                reply_to_message_id=file.message_id
            )

            admin_message = await context.bot.send_message(
                chat_id=95604679,
                text=f"📁 New File has been added to queue\nName: {file.file_name}\nLines: {file.total_lines}",
            )
            
            try:
                translator = SubtitleTranslator(API_KEY,
                                                base_url=API_ENDPOINT)
                logger.info(f'Going to translate file {file.id} for user {file.user_id}')
                # Parse SRT content
                subtitles = await translator.parse_srt_content(file_content)
                
                # Update status to PROCESSING
                file.status = FileStatus.PROCESSING
                await session.commit()
                
                # Progress callback
                async def progress_callback(progress):
                    try:
                        if progress > 0:
                            elapsed_time = time.time() - start_time
                            total_estimated_time = elapsed_time * (100 / progress)
                            remaining_time = total_estimated_time - elapsed_time
                            
                            # Format remaining time
                            remaining_minutes = int(remaining_time // 60)
                            remaining_seconds = int(remaining_time % 60)
                            eta_text = f"\nزمان تقریبی باقی مانده: {remaining_minutes} دقیقه و {remaining_seconds:02d} ثانیه"
                        else:
                            eta_text = "\nدر حال محاسبه زمان باقی مانده..."

                        await progress_message.edit_text(
                            f"🔄<b> در حال ترجمه کردن:</b>\n"
                            f"<code>[{'■' * int(progress / 10)}{'□' * (10 - int(progress / 10))}] "
                            f"{progress:.1f}% </code>"
                            f"<i>{eta_text}</i>",
                            parse_mode='HTML'
                        )
                    except Exception as e:
                        logger.error(f"Error updating progress: {str(e)}")
                
                # Translate content
                translated_content = await translator.translate_all_subtitles(
                    subtitles, 
                    progress_callback=progress_callback
                )
                
                translated_content = translator.compose_srt(translated_content)
                
                # Calculate total cost in Tomans
                total_cost_toman = translator.calculate_cost_toman(file.price_unit)
                total_cost_rial = total_cost_toman * 10  # Convert to Rials
                
                # Create transaction to deduct balance
                transaction = Transaction(
                    from_user_id=file.user_id,
                    amount=total_cost_rial,
                    description=f"Translation cost for {file.file_name} - {file.total_lines} lines"
                )
                session.add(transaction)
                await session.flush()
                
                # Create invoice
                invoice = Invoice(
                    user_id=file.user_id,
                    number=str(uuid.uuid4()),
                    description=f"Translation of {file.file_name}"
                )
                session.add(invoice)
                await session.flush()
                
                # Link transaction to invoice
                invoice_transaction = InvoiceTransaction(
                    invoice_id=invoice.id,
                    transaction_id=transaction.id
                )
                session.add(invoice_transaction)
                
                # Create output file
                output = BytesIO(translated_content.encode('utf-8'))
                output.name = f"translated_{file.file_name}" if file.file_name else f"translated_subtitle_{file.id}.srt"
                
                # Send the translated file
                total_time = time.time() - start_time
                total_minutes = int(total_time // 60)
                total_seconds = int(total_time % 60)
                
                message = await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=output,
                    caption=f"✅ ترجمه شما کامل شد!\n"
                            f"📝 تعداد کل خطوط: {file.total_lines}\n"
                            f"⏱ زمان کل: {total_minutes}:{total_seconds:02d}\n"
                            f"💰 هزینه کلی: {total_cost_toman:,} تومان",
                    reply_to_message_id=file.message_id
                )
                
                # Update file status and details
                file.status = FileStatus.COMPLETED
                file.output_file_id = message.document.file_id
                file.total_token_used = translator.total_tokens
                file.total_cost = translator.total_price  # Store in cents
                await session.commit()
                
                await progress_message.delete()
                
            except Exception as e:
                logger.error(f"Translation error: {str(e)}")
                file.status = FileStatus.FAILED
                await session.commit()
                await progress_message.edit_text(f"❌ خطای داخلی: {str(e)}")
                raise e
                
    except Exception as e:
        logger.error(f"Process translation error: {str(e)}")
        await progress_message.edit_text(f"❌ خطا!: {str(e)}")

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
                    file_translation.status = FileStatus.FAILED
                    await session.commit()
                    await query.edit_message_text("❌ درخواست ترجمه لغو شد.")
                    # Clear stored file data
                    context.user_data.pop('current_file_id', None)
                    context.user_data.pop('file_lines', None)
                    context.user_data.pop('translatable_lines', None)
                    
                if file_translation.status == FileStatus.COMPLETED:
                    await query.edit_message_text("❌ درخواست ترجمه قبلا انجام شده.")
                    message = await context.bot.send_document(
                        chat_id=update.effective_chat.id,
                        document=file_translation.output_file_id,
                        caption=f"✅ ترجمه شما کامل شد!\n"
                                f"📝 تعداد کل خطوط: {file_translation.total_lines}\n"
                                f"💰 هزینه کلی: {file_translation.total_lines * file_translation.price_unit} تومان"
                    )
                    return
                    
                elif action == "start_translation":
                    logger.info(f"Starting translation process for file {file_translation_id}")
                    await query.message.delete()
                    # Start translation in background
                    asyncio.create_task(
                        process_translation(
                            update=update,
                            context=context,
                            file_id=file_translation_id
                        )
                    )

        except Exception as e:
            logger.error(f"Error in button_callback_handler: {str(e)}", exc_info=True)
            await query.edit_message_text(f"❌ خطا در پردازش درخواست: {str(e)}")

@authenticate_user
async def balance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, bot_user: BotUser = None):
    """Handler for /balance command - shows user's current balance"""
    try:
        # Get incoming transactions sum


        # Calculate balance and convert to Toman
        balance_tomans = await get_user_balance(bot_user.user_id)
        
        # Create payment URLs with correct source parameter
        base_url = WEBHOOK_URL.rstrip('/')  # Remove trailing slash if present
        keyboard = [
            [InlineKeyboardButton(
                "اعبتار ۱۰۰ هزار تومان", 
                url=f"{base_url}/finance/{bot_user.user_id}/100000?source=telegram"
            )],
            [InlineKeyboardButton(
                "اعتبار ۵۰۰ هزار تومان", 
                url=f"{base_url}/finance/{bot_user.user_id}/500000?source=telegram"
            )],
            [InlineKeyboardButton(
                "اعتبار ۱ میلیون تومان", 
                url=f"{base_url}/finance/{bot_user.user_id}/1000000?source=telegram"
            )],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"💰 میزان شارژ شما {balance_tomans:,.0f} تومان\n\n"
            f"برای افزایش شارژ یکی از گزینه های زیر را انتخاب کنید:"
            f"‍\n\n"
            f"هر ۱۰۰ هزار تومان، ۵۰۰ خط به شما اعتبار میدهد",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Error in balance handler: {str(e)}")
        await update.message.reply_text("Sorry, there was an error getting your balance. Please try again later.")
