import os
from models import models
import zibal.zibal as zibal

# Configuration
merchant_id = os.environ.get('ZIBAL_MERCHAND_ID', 'zibal')  # zibal for test mode
callback_url = os.environ.get('ZIBAL_RETURN_URL', 'http://localhost:8000/finance/confirm_pay')
START_PAYMENT_URL = 'https://gateway.zibal.ir/start/'

def create_pay_url_zibal(receipt, logger):
    """Create payment URL using Zibal gateway"""
    zb = zibal.zibal(merchant_id, callback_url)
    description = f'Charge account: {receipt.amount} Rials'
    
    request_to_zibal = zb.request(
        amount=receipt.amount,
        description=description,
        order_id=receipt.number
    )
    logger.info(f'Zibal request data {request_to_zibal}')
    
    if request_to_zibal.get('message') != 'success':
        raise Exception('Zibal request is not successful')
    
    # Update receipt extra data instead of assigning
    current_extra_data = receipt.extra_data or {}
    current_extra_data.update({'request_to_zibal': request_to_zibal})
    receipt.extra_data = current_extra_data
    
    receipt.tracker_id = str(request_to_zibal.get('trackId'))
    receipt.status = models.PaymentStatus.PENDING
    redirect_url = START_PAYMENT_URL + str(request_to_zibal.get('trackId'))
    return redirect_url

def verify_pay(receipt, logger):
    """Verify payment with Zibal gateway"""
    zb = zibal.zibal(merchant_id, callback_url)
    verify_zibal = zb.verify(receipt.tracker_id)
    verify_result = verify_zibal['result']
    logger.info(f'Verify result {verify_result}')
    
    # Update receipt extra data with verification result
    current_extra_data = receipt.extra_data or {}
    current_extra_data['verify_result'] = verify_result
    receipt.extra_data = current_extra_data
    
    return True