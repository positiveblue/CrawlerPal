import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# PayPal Configuration
PAYPAL_CLIENT_ID = os.getenv('PAYPAL_CLIENT_ID')
PAYPAL_CLIENT_SECRET = os.getenv('PAYPAL_CLIENT_SECRET')

# Validate that required environment variables are set
if not PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_SECRET:
    raise ValueError("PayPal credentials not found in environment variables. Please set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in your .env file.") 