"""
Client-side PayPal configuration for merchant account details.
This file contains the merchant account information where payments will be received.
"""

# PayPal Merchant Account Details
MERCHANT_ACCOUNT = {
    "email": "merchant@example.com",  # Replace with your PayPal merchant email
    "business_name": "CrawlerPal",    # Your business name
    "account_id": "YOUR_MERCHANT_ACCOUNT_ID",  # Your PayPal merchant account ID
    "currency": "USD",                # Default currency for transactions
    "sandbox": True                   # Set to False for production
}

# Payment Configuration
PAYMENT_CONFIG = {
    "one_category": {
        "amount": 1.00,
        "description": "Access to one category",
        "item_name": "Single Category Access"
    },
    "all_categories": {
        "amount": 5.00,
        "description": "Monthly subscription to all categories",
        "item_name": "Monthly Subscription"
    }
}

# Return URLs Configuration
URLS = {
    "success": "http://localhost:8000/payment/success",
    "cancel": "http://localhost:8000/payment/cancel"
} 