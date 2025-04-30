import logging
import requests
import uuid
import os
from typing import Optional
from datetime import datetime

# Create logs directory if it doesn't exist
if not os.path.exists('logs'):
    os.makedirs('logs')

# Configure logging with both file and console handlers
logger = logging.getLogger('paypal')
logger.setLevel(logging.DEBUG)

# Create file handler with detailed formatting
log_file = f'logs/paypal_{datetime.now().strftime("%Y%m%d")}.log'
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s\n'
    'Additional Data: %(data)s\n'
    '----------------------------------------'
)
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# Create console handler with simpler formatting
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

def log_paypal_operation(operation: str, data: dict, level: str = 'info'):
    """Helper function to log PayPal operations with consistent formatting"""
    log_func = getattr(logger, level)
    log_func(
        operation,
        extra={
            'data': data
        }
    )

def configure_paypal(client_id: str, client_secret: str, sandbox: bool = True) -> None:
    """
    Configure PayPal with client credentials.
    
    Args:
        client_id (str): PayPal client ID
        client_secret (str): PayPal client secret
        sandbox (bool): Whether to use sandbox environment
    """
    # Store configuration in module-level variables
    global PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_SANDBOX
    PAYPAL_CLIENT_ID = client_id
    PAYPAL_CLIENT_SECRET = client_secret
    PAYPAL_SANDBOX = sandbox
    
    log_paypal_operation(
        'PayPal Configuration',
        {
            'environment': 'sandbox' if sandbox else 'live',
            'client_id_length': len(client_id) if client_id else 0,
            'timestamp': datetime.now().isoformat()
        }
    )

def get_access_token(client_id: str, client_secret: str, sandbox: bool = True) -> Optional[str]:
    """
    Get PayPal access token for API authentication.
    """
    base_url = "https://api-m.sandbox.paypal.com" if sandbox else "https://api-m.paypal.com"
    url = f"{base_url}/v1/oauth2/token"
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }
    
    data = {
        "grant_type": "client_credentials"
    }
    
    log_paypal_operation(
        'Requesting Access Token',
        {
            'url': url,
            'environment': 'sandbox' if sandbox else 'live',
            'timestamp': datetime.now().isoformat()
        }
    )
    
    response = requests.post(
        url,
        headers=headers,
        data=data,
        auth=(client_id, client_secret)
    )
    
    if response.status_code == 200:
        token_data = response.json()
        log_paypal_operation(
            'Access Token Retrieved',
            {
                'expires_in': token_data.get('expires_in'),
                'app_id': token_data.get('app_id'),
                'timestamp': datetime.now().isoformat()
            }
        )
        return token_data.get("access_token")
    else:
        log_paypal_operation(
            'Access Token Request Failed',
            {
                'status_code': response.status_code,
                'error': response.text,
                'timestamp': datetime.now().isoformat()
            },
            'error'
        )
        return None

def create_payment(
    amount: float,
    currency: str,
    description: str,
    return_url: str,
    cancel_url: str,
    client_id: str,
    client_secret: str,
    sandbox: bool = True
) -> Optional[str]:
    """
    Create a PayPal payment using v2 Orders API and return the approval URL.
    
    Args:
        amount (float): Payment amount
        currency (str): Currency code (e.g., 'USD')
        description (str): Payment description
        return_url (str): URL to return to after successful payment
        cancel_url (str): URL to return to if payment is cancelled
        client_id (str): PayPal client ID
        client_secret (str): PayPal client secret
        sandbox (bool): Whether to use sandbox environment
        
    Returns:
        Optional[str]: PayPal approval URL or None if creation failed
    """
    # Get access token
    access_token = get_access_token(client_id, client_secret, sandbox)
    if not access_token:
        return None
        
    base_url = "https://api-m.sandbox.paypal.com" if sandbox else "https://api-m.paypal.com"
    url = f"{base_url}/v2/checkout/orders"
    request_id = str(uuid.uuid4())
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "PayPal-Request-Id": request_id
    }
    
    data = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "amount": {
                    "currency_code": currency,
                    "value": str(amount)
                },
                "description": description
            }
        ],
        "application_context": {
            "return_url": return_url,
            "cancel_url": cancel_url,
            "brand_name": "CrawlerPal",
            "landing_page": "LOGIN",
            "user_action": "PAY_NOW",
            "shipping_preference": "NO_SHIPPING"
        }
    }
    
    log_paypal_operation(
        'Creating Payment Order',
        {
            'request_id': request_id,
            'amount': amount,
            'currency': currency,
            'description': description,
            'return_url': return_url,
            'timestamp': datetime.now().isoformat()
        }
    )
    
    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code in [200, 201]:
        response_data = response.json()
        approval_url = None
        for link in response_data.get("links", []):
            if link.get("rel") == "approve":
                approval_url = link.get("href")
                break
        
        log_paypal_operation(
            'Payment Order Created',
            {
                'order_id': response_data.get('id'),
                'status': response_data.get('status'),
                'approval_url': approval_url,
                'timestamp': datetime.now().isoformat()
            }
        )
        return approval_url
    else:
        log_paypal_operation(
            'Payment Order Creation Failed',
            {
                'status_code': response.status_code,
                'error': response.text,
                'request_id': request_id,
                'timestamp': datetime.now().isoformat()
            },
            'error'
        )
        return None

def execute_payment(payment_id: str, payer_id: str, client_id: str, client_secret: str, sandbox: bool = True) -> bool:
    """
    Execute (capture) a PayPal payment using v2 Orders API.
    Returns True if capture is successful, False otherwise.
    
    The capture response includes:
    - id: The PayPal-generated ID for the captured payment
    - status: The status of the captured payment (COMPLETED, DECLINED, etc.)
    - payer: Information about the payer (email, payer_id, etc.)
    - purchase_units: Details about the payment including amount, payee, etc.
    """
    # Get access token
    access_token = get_access_token(client_id, client_secret, sandbox)
    if not access_token:
        return False
        
    base_url = "https://api-m.sandbox.paypal.com" if sandbox else "https://api-m.paypal.com"
    url = f"{base_url}/v2/checkout/orders/{payment_id}/capture"
    request_id = str(uuid.uuid4())
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "PayPal-Request-Id": request_id
    }
    
    log_paypal_operation(
        'Executing Payment Capture',
        {
            'payment_id': payment_id,
            'payer_id': payer_id,
            'request_id': request_id,
            'timestamp': datetime.now().isoformat()
        }
    )
    
    response = requests.post(url, headers=headers)
    
    if response.status_code in [200, 201]:
        capture_data = response.json()
        log_paypal_operation(
            'Payment Capture Successful',
            {
                'capture_id': capture_data.get('id'),
                'status': capture_data.get('status'),
                'payer': capture_data.get('payer', {}),
                'purchase_units': capture_data.get('purchase_units', []),
                'timestamp': datetime.now().isoformat()
            }
        )
        return True
    else:
        log_paypal_operation(
            'Payment Capture Failed',
            {
                'status_code': response.status_code,
                'error': response.text,
                'payment_id': payment_id,
                'request_id': request_id,
                'timestamp': datetime.now().isoformat()
            },
            'error'
        )
        return False

def create_billing_agreement(payment_id: str, payer_id: str, client_id: str, client_secret: str, sandbox: bool = True) -> Optional[str]:
    """
    Create a billing agreement using v3 API.
    """
    # Get access token
    access_token = get_access_token(client_id, client_secret, sandbox)
    if not access_token:
        return None
        
    base_url = "https://api-m.sandbox.paypal.com" if sandbox else "https://api-m.paypal.com"
    url = f"{base_url}/v3/billing-agreements"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    
    data = {
        "description": "Monthly subscription",
        "payer": {
            "payment_method": "paypal",
            "payer_id": payer_id
        },
        "plan": {
            "type": "MERCHANT_INITIATED_BILLING",
            "merchant_preferences": {
                "return_url": "https://example.com/return",
                "cancel_url": "https://example.com/cancel",
                "auto_bill_amount": "YES",
                "initial_fail_amount_action": "CONTINUE",
                "max_fail_attempts": "0"
            }
        }
    }
    
    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 201:
        return response.json().get("id")
    else:
        logging.error(f"Billing agreement creation failed: {response.text}")
        return None

def execute_billing_agreement(agreement_id: str, client_id: str, client_secret: str, sandbox: bool = True) -> bool:
    """
    Execute a billing agreement using v3 API.
    """
    # Get access token
    access_token = get_access_token(client_id, client_secret, sandbox)
    if not access_token:
        return False
        
    base_url = "https://api-m.sandbox.paypal.com" if sandbox else "https://api-m.paypal.com"
    url = f"{base_url}/v3/billing-agreements/{agreement_id}/execute"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    
    response = requests.post(url, headers=headers)
    
    if response.status_code == 200:
        return True
    else:
        logging.error(f"Billing agreement execution failed: {response.text}")
        return False 