import os
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.database import get_db
from models.models import User, Receipt, PaymentStatus, Transaction, ReceiptTransaction, BotUser
from .zibal import create_pay_url_zibal, verify_pay
import logging
from telegram import Bot
from telegram.constants import ParseMode
import uuid

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize bot
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
bot = Bot(token=TELEGRAM_TOKEN)

router = APIRouter(prefix="/finance", tags=["finance"])

@router.get("/{user_id}/{amount}")
async def create_payment(
    user_id: int,
    amount: float,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Create a payment receipt and redirect to payment gateway"""
    try:
        # Get source from query parameters
        source = request.query_params.get('source', None)
        logger.info(f"Creating payment for user {user_id} with amount {amount} and source {source}")
        # Get user
        result = await db.execute(select(User).filter(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Convert amount to Rials (multiply by 10)
        amount_rials = float(amount * 10)
        logger.info(f'Requested amount for user {user_id} is {amount_rials}')
        
        # Create receipt
        receipt = Receipt(
            user_id=user_id,
            amount=amount_rials,
            description=f'Charge account {amount} Tomans',
            bank='zibal',
            status=PaymentStatus.INIT,
            number=str(uuid.uuid4()),  # Generate a unique number for the receipt
            extra_data={'source': source}
        )
        
        db.add(receipt)
        await db.flush()  # Get the receipt ID
        
        # Generate payment URL
        redirect_url = create_pay_url_zibal(receipt=receipt, logger=logger)
        
        await db.commit()
        return RedirectResponse(url=redirect_url)
        
    except Exception as e:
        logger.error(f"Error creating payment: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/confirm_pay")
async def confirm_payment(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Handle payment confirmation from gateway"""
    try:
        # Get query parameters
        params = dict(request.query_params)
        track_id = params.get('trackId')
        success = params.get('success')
        status = params.get('status')
        order_id = params.get('orderId')

        if not all([track_id, success, status]):
            logger.error('Missing required parameters')
            return {"status": "failed", "message": "Missing required parameters"}

        # Get receipt by tracker_id
        result = await db.execute(
            select(Receipt).filter(Receipt.tracker_id == track_id)
        )
        receipt = result.scalar_one_or_none()
        
        if not receipt or receipt.status != PaymentStatus.PENDING:
            logger.error(f'Invalid receipt state: {receipt}')
            return {"status": "failed", "message": "Invalid receipt"}

        # Update receipt with callback data
        current_extra_data = receipt.extra_data or {}
        current_extra_data.update({
            'zibal_get_request': {
                'tracker_id': track_id,
                'success': success,
                'status': status,
                'order_id': order_id
            }
        })
        receipt.extra_data = current_extra_data

        # Check payment status
        if status != '2' or success != '1':
            receipt.status = PaymentStatus.FAILED
            await db.commit()
            return {"status": "failed", "message": "Payment was not successful"}

        # Verify payment with gateway
        if not verify_pay(receipt=receipt, logger=logger):
            receipt.status = PaymentStatus.FAILED
            await db.commit()
            return {"status": "failed", "message": "Payment verification failed"}

        # Update receipt status and create transaction
        receipt.status = PaymentStatus.SUCCESS
        
        # Create transaction
        transaction = Transaction(
            to_user_id=receipt.user_id,
            amount=receipt.amount,
            description=f"Payment from gateway: {receipt.tracker_id}"
        )
        db.add(transaction)
        await db.flush()
        
        # Link transaction to receipt
        receipt_transaction = ReceiptTransaction(
            receipt_id=receipt.id,
            transaction_id=transaction.id
        )
        db.add(receipt_transaction)
        logger.info(f"Payment confirmed for user {receipt.user_id}, extra data: {receipt.extra_data}")
        # If payment was from telegram, send notification
        if receipt.extra_data and receipt.extra_data.get('source') == 'telegram':
            try:
                # Get user's telegram ID from BotUser
                bot_user_result = await db.execute(
                    select(BotUser).filter(BotUser.user_id == receipt.user_id)
                )
                bot_user = bot_user_result.scalar_one_or_none()
                
                if bot_user:
                    amount_tomans = receipt.amount / 10
                    await bot.send_message(
                        chat_id=bot_user.telegram_id,
                        text=f"✅ پرداخت شما با موفقیت انجام شد!\n"
                             f"💰 مبلغ: {amount_tomans:,.0f} تومان\n",
                        parse_mode=ParseMode.HTML
                    )
            except Exception as e:
                logger.error(f"Error sending Telegram notification: {str(e)}")
        
        await db.commit()

        # Get MAIN_BOT from environment
        main_bot = os.getenv('MAIN_BOT', '')
        if receipt.extra_data and receipt.extra_data.get('source') == 'telegram':
            # Redirect to Telegram bot
            return RedirectResponse(url=f"https://t.me/{main_bot}")
        else:
            return {"status": "success", "message": "Payment was successful"}

    except Exception as e:
        logger.error(f"Error confirming payment: {str(e)}")
        await db.rollback()
        return {"status": "failed", "message": str(e)}
