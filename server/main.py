from fastapi import FastAPI, Request, Header, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel # Import BaseModel
from typing import Optional, List, Dict, Any, Tuple
import datetime
import random
import uuid
import json # Import json
from pathlib import Path # Import Path
from faker import Faker
from paypal_config import configure_paypal, create_payment, execute_payment, create_billing_agreement, execute_billing_agreement
from config import PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET

app = FastAPI()

# --- Global In-Memory Store ---
payments_data: Dict[str, Dict[str, Any]] = {}
customers_data: Dict[str, Dict[str, Any]] = {}
payment_contexts: Dict[str, Dict[str, Any]] = {}

# --- Constants ---
PAYMENTS_DB_FILE = Path("payments_db.json")
CUSTOMERS_DB_FILE = Path("customers_db.json")
PAYMENT_CONTEXTS_DB_FILE = Path("payment_contexts_db.json")

# --- Models ---
class PaymentRequest(BaseModel):
    payment_context_token: str
    offer_id: str
    category: Optional[str] = None
    email: Optional[str] = None

class AccessRequest(BaseModel):
    customer_id: Optional[str] = None

class Customer(BaseModel):
    customer_id: str
    name: str
    email: str
    created_at: str
    last_payment_at: Optional[str] = None
    active_subscription: Optional[str] = None

# --- Database Functions (using JSON file) ---
def load_payments_db() -> Dict[str, Dict[str, Any]]:
    global payments_data # Ensure we modify the global variable
    if not PAYMENTS_DB_FILE.is_file():
        print(f"Payments database file not found ({PAYMENTS_DB_FILE}), starting empty.")
        payments_data = {}
        save_payments_db({}) # Create the file if it doesn't exist
        return {}
    try:
        with open(PAYMENTS_DB_FILE, 'r') as f:
            loaded_data = json.load(f)
            payments_data = loaded_data # Load into global variable
            print(f"Loaded payments database from {PAYMENTS_DB_FILE} into memory.")
            return loaded_data
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading payments database ({e}), starting empty.")
        payments_data = {}
        return {}

def save_payments_db(data: Dict[str, Dict[str, Any]]):
    try:
        with open(PAYMENTS_DB_FILE, 'w') as f:
            json.dump(data, f, indent=2)
            print(f"Saved payments database to {PAYMENTS_DB_FILE}")
    except IOError as e:
        print(f"Error: Could not write to {PAYMENTS_DB_FILE} ({e})")

def load_customers_db() -> Dict[str, Dict[str, Any]]:
    global customers_data
    if not CUSTOMERS_DB_FILE.is_file():
        print(f"Customers database file not found ({CUSTOMERS_DB_FILE}), starting empty.")
        customers_data = {}
        save_customers_db({})
        return {}
    try:
        with open(CUSTOMERS_DB_FILE, 'r') as f:
            loaded_data = json.load(f)
            customers_data = loaded_data
            print(f"Loaded customers database from {CUSTOMERS_DB_FILE} into memory.")
            return loaded_data
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading customers database ({e}), starting empty.")
        customers_data = {}
        return {}

def save_customers_db(data: Dict[str, Dict[str, Any]]):
    try:
        with open(CUSTOMERS_DB_FILE, 'w') as f:
            json.dump(data, f, indent=2)
            print(f"Saved customers database to {CUSTOMERS_DB_FILE}")
    except IOError as e:
        print(f"Error: Could not write to {CUSTOMERS_DB_FILE} ({e})")

def load_payment_contexts_db() -> Dict[str, Dict[str, Any]]:
    global payment_contexts
    if not PAYMENT_CONTEXTS_DB_FILE.is_file():
        print(f"Payment contexts database file not found ({PAYMENT_CONTEXTS_DB_FILE}), starting empty.")
        payment_contexts = {}
        save_payment_contexts_db({})
        return {}
    try:
        with open(PAYMENT_CONTEXTS_DB_FILE, 'r') as f:
            loaded_data = json.load(f)
            payment_contexts = loaded_data
            print(f"Loaded payment contexts database from {PAYMENT_CONTEXTS_DB_FILE} into memory.")
            return loaded_data
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading payment contexts database ({e}), starting empty.")
        payment_contexts = {}
        return {}

def save_payment_contexts_db(data: Dict[str, Dict[str, Any]]):
    try:
        with open(PAYMENT_CONTEXTS_DB_FILE, 'w') as f:
            json.dump(data, f, indent=2)
            print(f"Saved payment contexts database to {PAYMENT_CONTEXTS_DB_FILE}")
    except IOError as e:
        print(f"Error: Could not write to {PAYMENT_CONTEXTS_DB_FILE} ({e})")

def create_or_get_customer(email: str, name: str) -> Tuple[str, bool]:
    """
    Create a new customer or return existing one based on email.
    Returns (customer_id, is_new_customer)
    """
    # Check if customer exists by email
    for customer_id, customer_data in customers_data.items():
        if customer_data.get('email') == email:
            return customer_id, False
    
    # Create new customer
    customer_id = str(uuid.uuid4())
    new_customer = {
        'customer_id': customer_id,
        'name': name,
        'email': email,
        'created_at': datetime.datetime.now().isoformat(),
        'last_payment_at': None,
        'active_subscription': None
    }
    
    customers_data[customer_id] = new_customer
    save_customers_db(customers_data)
    return customer_id, True

# Initialize Faker
fake = Faker()

# Define categories
categories = ["politics", "international", "economy", "technology", "sports", "entertainment"]

# Function to generate mock news data
def generate_mock_news(num_items_per_category: int = 3) -> List[Dict[str, Any]]:
    news = []
    current_time = datetime.datetime.now()
    for category in categories:
        for i in range(num_items_per_category):
            # Generate slightly varied timestamps
            timestamp = current_time - datetime.timedelta(hours=random.randint(0, 24*3), minutes=random.randint(0, 59))
            news.append({
                "timestamp": timestamp.isoformat(),
                # Generate fake data
                "title": f"{category.capitalize()} News: {fake.bs().capitalize()}",
                "description": fake.paragraph(nb_sentences=3),
                "category": category
            })
    # Sort news by timestamp descending (most recent first)
    news.sort(key=lambda x: x['timestamp'], reverse=True)
    return news

# Generate news data on startup (or could be done per-request if needed)
news_data = generate_mock_news(num_items_per_category=4)

# Simplified check for common browser user agents
def is_browser(user_agent: str) -> bool:
    common_browsers = ["mozilla", "chrome", "safari", "firefox", "edge", "opera"]
    return any(browser in user_agent.lower() for browser in common_browsers)

# Simplified token validation (replace with actual validation)
def validate_token(token: Optional[str], request: Request) -> bool:
    if token not in payments_data:
        return False
        
    payment_details = payments_data.get(token)
    if not payment_details:
        return False
        
    stored_payment_context = payment_details.get("payment_context_token")
    if not stored_payment_context:
        return True
        
    current_payment_context = request.headers.get("X-Payment-Context")
    if current_payment_context != stored_payment_context:
        print(f"Payment context mismatch. Stored: {stored_payment_context}, Current: {current_payment_context}")
        return False
        
    # Check if the payment is associated with a customer
    customer_id = payment_details.get("customer_id")
    if customer_id and customer_id not in customers_data:
        print(f"Customer {customer_id} not found for token {token}")
        return False
        
    return True

# Dependency to get the authorization header
async def get_authorization_header(authorization: Optional[str] = Header(None)) -> Optional[str]:
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "Bearer":
            return parts[1]
    return None

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, user_agent: Optional[str] = Header(None), token: Optional[str] = Depends(get_authorization_header)):
    global payments_data # Need access to the global data
    is_bot_request = not user_agent or not is_browser(user_agent)

    if is_bot_request:
        # Handle Bot Request
        print(f"Bot request detected (User-Agent: {user_agent})")
        
        if validate_token(token, request):
            # Token is valid (exists in our db), now check access rights
            payment_details = payments_data.get(token)
            
            if not payment_details:
                # This case should theoretically not happen if validate_token passed,
                # but good practice to handle it.
                print(f"Error: Token {token} validated but details not found in memory.")
                raise HTTPException(status_code=500, detail="Internal Server Error: Invalid token state")

            offer_id = payment_details.get("offer_id")
            paid_category = payment_details.get("category") # Will be None for 'all_categories' offer

            print(f"Valid token ({token}) found. Offer ID: {offer_id}, Paid Category: {paid_category}")

            if offer_id == "all_categories":
                print("Serving all news data for 'all_categories' token.")
                return JSONResponse(content={"news": news_data})
            elif offer_id == "one_category" and paid_category:
                print(f"Filtering news data for category: {paid_category}")
                filtered_news = [item for item in news_data if item.get("category") == paid_category]
                return JSONResponse(content={"news": filtered_news})
            else:
                # Handle unexpected offer_id or missing category for 'one_category'
                print(f"Warning: Token {token} has unexpected/incomplete payment details: {payment_details}")
                # Decide how to handle this - maybe return 403 Forbidden or default to no access?
                # For now, let's return 403 Forbidden.
                raise HTTPException(status_code=403, detail="Access Denied: Invalid or incomplete payment token details")

        else:
            # Token is invalid or missing
            print(f"No valid token found ({token}). Returning 402 with offers.")
            # Generate L402 context
            payment_context_token = str(uuid.uuid4())
            # Define the port dynamically if possible, or hardcode for now
            port = 8000 # TODO: Get port dynamically if needed
            payment_request_url = f"http://localhost:{port}/l402/payment-request"
            
            # Create return and cancel URLs
            base_url = f"http://localhost:{port}"
            return_url = f"{base_url}/paypal/callback?context={payment_context_token}"
            cancel_url = f"{base_url}/payment/cancel?context={payment_context_token}"

            # Create PayPal payments for each offer
            one_category_url = create_payment(
                amount=1.00,
                currency="USD",
                description="Access to one category",
                return_url=return_url,
                cancel_url=cancel_url,
                client_id=PAYPAL_CLIENT_ID,
                client_secret=PAYPAL_CLIENT_SECRET,
                sandbox=True
            )
            
            all_categories_url = create_payment(
                amount=5.00,
                currency="USD",
                description="Monthly subscription to all categories",
                return_url=return_url,
                cancel_url=cancel_url,
                client_id=PAYPAL_CLIENT_ID,
                client_secret=PAYPAL_CLIENT_SECRET,
                sandbox=True
            )

            offers = [
                {
                  "id": "one_category",
                  "title": "Access to one category",
                  "description": "Access to all the data in one category",
                  "amount": 1,
                  "currency": "USD",
                  "payment_methods": ["paypal"],
                  "payment_url": one_category_url,
                  "payment_context": payment_context_token
                },
                {
                  "id": "all_categories",
                  "title": "Monthly Subscription",
                  "description": "Access all the data in our website for a month, any category, any time",
                  "amount": 5,
                  "currency": "USD",
                  "type": "subscription",
                  "duration": "1 month",
                  "payment_methods": ["paypal"],
                  "payment_url": all_categories_url,
                  "payment_context": payment_context_token
                }
            ]

            response_body = {
                "version": "0.2.3",
                "payment_request_url": payment_request_url,
                "payment_context_token": payment_context_token,
                "offers": offers
            }

            return JSONResponse(
                status_code=402,
                content=response_body
            )
    else:
        # Handle Browser Request
        print(f"Browser request detected (User-Agent: {user_agent})")

        # Group news by category
        news_by_category: Dict[str, List[Dict[str, Any]]] = {}
        for item in news_data:
            category = item.get('category', 'Uncategorized')
            if category not in news_by_category:
                news_by_category[category] = []
            news_by_category[category].append(item)

        # CSS adjustments for multi-column layout
        css_styles = '''
        <style>
            body { font-family: sans-serif; margin: 0; padding: 0; background-color: #f4f4f4; }
            header { background-color: #333; color: #fff; padding: 1rem 0; text-align: center; margin-bottom: 2rem; }
            h1 { margin: 0; font-size: 2.5rem; }
            .container { width: 95%; margin: 0 auto; }
            .category-container { display: flex; flex-wrap: wrap; gap: 1.5rem; justify-content: center; }
            .category-column { background-color: #fff; padding: 1rem; box-shadow: 0 0 10px rgba(0,0,0,0.1); flex: 1; min-width: 280px; /* Adjust min-width as needed */ }
            .category-column h2 { margin-top: 0; font-size: 1.8rem; color: #333; border-bottom: 2px solid #eee; padding-bottom: 0.5rem; margin-bottom: 1rem; }
            article { border-bottom: 1px solid #eee; padding-bottom: 1rem; margin-bottom: 1rem; }
            article:last-child { border-bottom: none; margin-bottom: 0; }
            article h3 { margin-top: 0; margin-bottom: 0.5rem; font-size: 1.1rem; color: #444; }
            article p { color: #555; line-height: 1.5; font-size: 0.9rem; margin-bottom: 0.5rem; }
            .metadata { font-size: 0.75rem; color: #777; }
            /* Removed category background color span as category is now the column header */
        </style>
        '''

        html_content_start = f'''
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>CrawlerPal News Demo</title>
            {css_styles}
        </head>
        <body>
            <header>
                <h1>CrawlerPal News</h1>
            </header>
            <div class="container">
                <div class="category-container">
        '''

        category_columns_html = ""
        # Iterate through defined categories to maintain order, checking if data exists
        for category in categories: # Use the defined categories list for order
            if category in news_by_category:
                category_columns_html += f'<div class="category-column">'
                category_columns_html += f'<h2>{category.capitalize()}</h2>'
                
                # Sort news within the category by timestamp
                sorted_news = sorted(news_by_category[category], key=lambda x: x['timestamp'], reverse=True)
                
                for item in sorted_news:
                    try:
                        ts = datetime.datetime.fromisoformat(item['timestamp'])
                        formatted_ts = ts.strftime("%Y-%m-%d %H:%M")
                    except (ValueError, TypeError):
                        formatted_ts = "Invalid Date"

                    # Nicer title formatting - remove category prefix if present
                    title = item.get('title', 'No Title')
                    if ':' in title:
                        title = title.split(':', 1)[-1].strip()

                    category_columns_html += f'''
                    <article>
                        <h3>{title}</h3>
                        <p>{item.get('description', 'No Description')}</p>
                        <div class="metadata">
                            <span>{formatted_ts}</span>
                        </div>
                    </article>
                    '''
                category_columns_html += '</div>' # Close category-column

        html_content_end = '''
                </div> <!-- Close category-container -->
            </div> <!-- Close container -->
        </body>
        </html>
        '''
        
        full_html_content = html_content_start + category_columns_html + html_content_end
        return HTMLResponse(content=full_html_content)

# --- FastAPI Startup Event ---
@app.on_event("startup")
async def startup_event():
    load_payments_db()
    load_customers_db()
    load_payment_contexts_db()
    configure_paypal(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, sandbox=True)

# --- New Payment Endpoint ---
@app.post("/l402/payment-request")
async def process_payment_request(payment_request: PaymentRequest):
    global payments_data, payment_contexts
    
    # Generate a unique token for this payment
    token = str(uuid.uuid4())
    
    # Get or create customer if email is provided
    customer_id = None
    if payment_request.email:
        customer_id, _ = create_or_get_customer(payment_request.email, "")  # Name will be updated later
    
    # Store the payment context with customer ID and offer details
    payment_context = {
        "context_token": payment_request.payment_context_token,
        "customer_id": customer_id,
        "created_at": datetime.datetime.now().isoformat(),
        "status": "pending",
        "offer_id": payment_request.offer_id,
        "category": payment_request.category,
        "amount": 1.00 if payment_request.offer_id == "one_category" else 5.00,
        "currency": "USD",
        "description": "Access to one category" if payment_request.offer_id == "one_category" else "Monthly subscription to all categories",
        "paypal_payment_id": None,
        "paypal_payer_id": None,
        "paypal_agreement_id": None,
        "is_subscription": payment_request.offer_id == "all_categories"
    }
    payment_contexts[payment_request.payment_context_token] = payment_context
    save_payment_contexts_db(payment_contexts)
    
    # Store the payment details
    payment_details = {
        "offer_id": payment_request.offer_id,
        "category": payment_request.category,
        "timestamp": datetime.datetime.now().isoformat(),
        "payment_context_token": payment_request.payment_context_token,
        "customer_id": customer_id
    }
    
    payments_data[token] = payment_details
    save_payments_db(payments_data)
    
    return {"token": token}

@app.get("/paypal/callback")
async def paypal_callback(
    context: str,
    paymentId: str,
    PayerID: str,
    token: str
):
    """
    Handle PayPal callback after successful payment.
    This endpoint is called by PayPal after the user completes payment.
    """
    try:
        # Get the payment context
        payment_context = payment_contexts.get(context)
        if not payment_context:
            raise HTTPException(status_code=404, detail="Payment context not found")
            
        # Update payment context with PayPal details
        payment_context["paypal_payment_id"] = paymentId
        payment_context["paypal_payer_id"] = PayerID
        payment_context["paypal_token"] = token
        payment_context["status"] = "pending"  # Will be completed after execution
        
        # Save updated payment context
        payment_contexts[context] = payment_context
        save_payment_contexts_db(payment_contexts)
        
        # Redirect to success page with context
        return HTMLResponse(
            content=f"""
            <html>
                <head>
                    <title>Payment Successful</title>
                    <script>
                        window.location.href = '/payment/success?context={context}&paymentId={paymentId}&PayerID={PayerID}';
                    </script>
                </head>
                <body>
                    <p>Payment successful! Redirecting...</p>
                </body>
            </html>
            """
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/payment/success")
async def payment_success(context: str, paymentId: str, PayerID: str, email: str, name: str):
    """
    Handle successful PayPal payment with customer information.
    """
    try:
        # Get or create customer
        customer_id, is_new_customer = create_or_get_customer(email, name)
        
        # Verify payment context belongs to this customer
        payment_context = payment_contexts.get(context)
        if not payment_context:
            raise HTTPException(status_code=403, detail="Invalid payment context")
            
        # If payment context has a customer ID, verify it matches
        if payment_context.get("customer_id") and payment_context.get("customer_id") != customer_id:
            raise HTTPException(status_code=403, detail="Payment context belongs to a different customer")
            
        # Update payment context with customer ID if not set
        if not payment_context.get("customer_id"):
            payment_context["customer_id"] = customer_id
            payment_contexts[context] = payment_context
            save_payment_contexts_db(payment_contexts)
        
        # Execute the payment
        if execute_payment(paymentId, PayerID, PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, sandbox=True):
            # Payment successful, create access token
            access_token = str(uuid.uuid4())
            
            # Update payment context with PayPal details
            payment_context["paypal_payment_id"] = paymentId
            payment_context["paypal_payer_id"] = PayerID
            payment_context["status"] = "completed"
            
            # If this is a subscription, create billing agreement
            if payment_context["is_subscription"]:
                agreement_id = create_billing_agreement(
                    paymentId,
                    PayerID,
                    PAYPAL_CLIENT_ID,
                    PAYPAL_CLIENT_SECRET,
                    sandbox=True
                )
                if agreement_id:
                    payment_context["paypal_agreement_id"] = agreement_id
            
            # Save updated payment context
            payment_contexts[context] = payment_context
            save_payment_contexts_db(payment_contexts)
            
            # Store payment details
            payment_details = {
                "offer_id": payment_context["offer_id"],
                "category": payment_context["category"],
                "timestamp": datetime.datetime.now().isoformat(),
                "payment_context_token": context,
                "customer_id": customer_id,
                "access_token": access_token,
                "paypal_payment_id": paymentId,
                "paypal_payer_id": PayerID,
                "paypal_agreement_id": payment_context.get("paypal_agreement_id")
            }
            
            # Update customer's last payment time
            customers_data[customer_id]["last_payment_at"] = datetime.datetime.now().isoformat()
            save_customers_db(customers_data)
            
            # Update the in-memory store
            payments_data[access_token] = payment_details
            save_payments_db(payments_data)
            
            return JSONResponse(
                content={
                    "status": "success",
                    "message": "Payment successful",
                    "access_token": access_token,
                    "customer_id": customer_id,
                    "is_new_customer": is_new_customer,
                    "payment_context_token": context
                }
            )
        else:
            raise HTTPException(status_code=400, detail="Payment execution failed")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/payment/cancel")
async def payment_cancel(context: str):
    """
    Handle cancelled PayPal payment.
    """
    return JSONResponse(
        content={
            "status": "cancelled",
            "message": "Payment was cancelled"
        }
    )

# --- Helper Functions ---
def get_payment_context_from_header(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """
    Extract payment context token from Authorization header.
    Format: Bearer <payment_context_token>
    """
    if not authorization:
        return None
        
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
        
    return parts[1]

@app.post("/access")
async def access_information(
    access_request: AccessRequest,
    request: Request,
    authorization: Optional[str] = Header(None)
):
    """
    Access information using payment context token from Authorization header.
    If payment context is invalid, returns 402 with payment offers.
    """
    try:
        # Get payment context from Authorization header
        payment_context_token = get_payment_context_from_header(authorization)
        if not payment_context_token:
            # Generate new L402 context with default offers
            return generate_payment_offers(str(uuid.uuid4()))
            
        # Special case for specific PayPal token
        if payment_context_token == "6JH60235WN610164M":
            # Create return and cancel URLs
            port = 8000
            base_url = f"http://localhost:{port}"
            return_url = f"{base_url}/paypal/callback?context={payment_context_token}"
            cancel_url = f"{base_url}/payment/cancel?context={payment_context_token}"

            # Create PayPal payment with saved offer details
            payment_url = create_payment(
                amount=1.00,
                currency="USD",
                description="Access to one category",
                return_url=return_url,
                cancel_url=cancel_url,
                client_id=PAYPAL_CLIENT_ID,
                client_secret=PAYPAL_CLIENT_SECRET,
                sandbox=True
            )

            offer = {
                "id": "one_category",
                "title": "Access to one category",
                "description": "Access to all the data in one category",
                "amount": 1,
                "currency": "USD",
                "payment_methods": ["paypal"],
                "payment_url": payment_url,
                "payment_context": payment_context_token
            }

            response_body = {
                "version": "0.2.3",
                "payment_request_url": f"http://localhost:{port}/l402/payment-request",
                "payment_context_token": payment_context_token,
                "offers": [offer]
            }

            return JSONResponse(
                status_code=402,
                content=response_body
            )
            
        # Get payment context
        payment_context = payment_contexts.get(payment_context_token)
        if not payment_context or payment_context.get("status") != "completed":
            # If we have a saved payment context with PayPal details, use them
            if payment_context and payment_context.get("paypal_payment_id"):
                # Create return and cancel URLs
                port = 8000
                base_url = f"http://localhost:{port}"
                return_url = f"{base_url}/paypal/callback?context={payment_context_token}"
                cancel_url = f"{base_url}/payment/cancel?context={payment_context_token}"

                # If it's a subscription and we have an agreement ID, execute the agreement
                if payment_context.get("is_subscription") and payment_context.get("paypal_agreement_id"):
                    if execute_billing_agreement(payment_context["paypal_agreement_id"]):
                        # Update payment context status
                        payment_context["status"] = "completed"
                        payment_contexts[payment_context_token] = payment_context
                        save_payment_contexts_db(payment_contexts)
                        
                        # Return the appropriate data
                        if payment_context["offer_id"] == "all_categories":
                            return JSONResponse(content={"news": news_data})
                        elif payment_context["offer_id"] == "one_category" and payment_context["category"]:
                            filtered_news = [item for item in news_data if item.get("category") == payment_context["category"]]
                            return JSONResponse(content={"news": filtered_news})
                
                # Create PayPal payment with saved offer details
                payment_url = create_payment(
                    amount=payment_context["amount"],
                    currency=payment_context["currency"],
                    description=payment_context["description"],
                    return_url=return_url,
                    cancel_url=cancel_url,
                    client_id=PAYPAL_CLIENT_ID,
                    client_secret=PAYPAL_CLIENT_SECRET,
                    sandbox=True
                )

                offer = {
                    "id": payment_context["offer_id"],
                    "title": "Access to one category" if payment_context["offer_id"] == "one_category" else "Monthly Subscription",
                    "description": payment_context["description"],
                    "amount": payment_context["amount"],
                    "currency": payment_context["currency"],
                    "payment_methods": ["paypal"],
                    "payment_url": payment_url,
                    "payment_context": payment_context_token
                }

                if payment_context["is_subscription"]:
                    offer["type"] = "subscription"
                    offer["duration"] = "1 month"

                response_body = {
                    "version": "0.2.3",
                    "payment_request_url": f"http://localhost:{port}/l402/payment-request",
                    "payment_context_token": payment_context_token,
                    "offers": [offer]
                }
            else:
                # Generate new L402 context with default offers
                return generate_payment_offers(payment_context_token)

            return JSONResponse(
                status_code=402,
                content=response_body
            )
            
        # If customer_id is provided, verify it matches
        if access_request.customer_id and payment_context.get("customer_id") != access_request.customer_id:
            raise HTTPException(status_code=403, detail="Invalid customer for this payment context")
            
        # Get the access token
        access_token = payment_context.get("access_token")
        if not access_token:
            raise HTTPException(status_code=404, detail="Access token not found")
            
        # Get the payment details
        payment_details = payments_data.get(access_token)
        if not payment_details:
            raise HTTPException(status_code=404, detail="Payment details not found")
            
        # Get the offer details
        offer_id = payment_details.get("offer_id")
        category = payment_details.get("category")
        
        # Return the appropriate data based on the offer
        if offer_id == "all_categories":
            return JSONResponse(content={"news": news_data})
        elif offer_id == "one_category" and category:
            filtered_news = [item for item in news_data if item.get("category") == category]
            return JSONResponse(content={"news": filtered_news})
        else:
            raise HTTPException(status_code=400, detail="Invalid offer type")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def generate_payment_offers(payment_context_token: str) -> JSONResponse:
    """
    Generate payment offers for a new payment context.
    """
    port = 8000
    payment_request_url = f"http://localhost:{port}/l402/payment-request"
    
    # Create return and cancel URLs
    base_url = f"http://localhost:{port}"
    return_url = f"{base_url}/paypal/callback?context={payment_context_token}"
    cancel_url = f"{base_url}/payment/cancel?context={payment_context_token}"

    # Create PayPal payments for each offer
    one_category_url = create_payment(
        amount=1.00,
        currency="USD",
        description="Access to one category",
        return_url=return_url,
        cancel_url=cancel_url,
        client_id=PAYPAL_CLIENT_ID,
        client_secret=PAYPAL_CLIENT_SECRET,
        sandbox=True
    )
    
    all_categories_url = create_payment(
        amount=5.00,
        currency="USD",
        description="Monthly subscription to all categories",
        return_url=return_url,
        cancel_url=cancel_url,
        client_id=PAYPAL_CLIENT_ID,
        client_secret=PAYPAL_CLIENT_SECRET,
        sandbox=True
    )

    offers = [
        {
          "id": "one_category",
          "title": "Access to one category",
          "description": "Access to all the data in one category",
          "amount": 1,
          "currency": "USD",
          "payment_methods": ["paypal"],
          "payment_url": one_category_url,
          "payment_context": payment_context_token
        },
        {
          "id": "all_categories",
          "title": "Monthly Subscription",
          "description": "Access all the data in our website for a month, any category, any time",
          "amount": 5,
          "currency": "USD",
          "type": "subscription",
          "duration": "1 month",
          "payment_methods": ["paypal"],
          "payment_url": all_categories_url,
          "payment_context": payment_context_token
        }
    ]

    response_body = {
        "version": "0.2.3",
        "payment_request_url": payment_request_url,
        "payment_context_token": payment_context_token,
        "offers": offers
    }

    return JSONResponse(
        status_code=402,
        content=response_body
    )

# --- Main Execution ---
if __name__ == "__main__":
    import uvicorn
    # Startup logic moved to FastAPI event handler
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
    # Note: Using reload=True might cause the startup event to run multiple times
    # In production, run without reload or use a more robust state management.
