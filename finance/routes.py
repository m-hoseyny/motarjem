import os
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.database import get_db
from models.models import User, Receipt, PaymentStatus, Transaction, ReceiptTransaction
from .zibal import create_pay_url_zibal, verify_pay
import logging
import uuid

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/finance", tags=["finance"])

@router.get("/{user_id}/{amount}")
async def create_payment(
    user_id: int,
    amount: float,
    db: AsyncSession = Depends(get_db)
):
    """Create a payment receipt and redirect to payment gateway"""
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
        number=str(uuid.uuid4())  # Generate a unique number for the receipt
    )
    db.add(receipt)
    await db.flush()  # Get the receipt ID
    
    # Generate payment URL
    redirect_url = create_pay_url_zibal(receipt=receipt, logger=logger)
    
    await db.commit()
    return RedirectResponse(url=redirect_url)

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
        print(track_id)
        result = await db.execute(
            select(Receipt).filter(Receipt.tracker_id == track_id)
        )
        receipt = result.scalar_one_or_none()
        print(receipt)
        if not receipt or receipt.status != PaymentStatus.PENDING:
            logger.error(f'Invalid receipt state: {receipt}')
            return {"status": "failed", "message": "Invalid receipt"}

        # Update receipt with callback data
        receipt.update_extra_data({
            'zibal_get_request': {
                'tracker_id': track_id,
                'success': success,
                'status': status,
                'order_id': order_id
            }
        })

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
        
        await db.commit()
        return {"status": "success", "message": "Payment successful"}

    except Exception as e:
        logger.error(f"Error confirming payment: {str(e)}")
        await db.rollback()
        return {"status": "failed", "message": str(e)}
