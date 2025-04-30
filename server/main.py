from fastapi import FastAPI, Request, Header, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel # Import BaseModel
from typing import Optional, List, Dict, Any
import datetime
import random
import uuid
import json # Import json
from pathlib import Path # Import Path
from faker import Faker

app = FastAPI()

# --- Global In-Memory Store ---
payments_data: Dict[str, Dict[str, Any]] = {}

# --- Constants ---
PAYMENTS_DB_FILE = Path("payments_db.json")

# --- Models ---
class PaymentRequest(BaseModel):
    payment_context_token: str
    offer_id: str
    category: Optional[str] = None # Category might only be relevant for 'one_category' offer

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
def validate_token(token: Optional[str]) -> bool:
    # In a real app, you'd validate this token against a database or auth service
    
    # *** MODIFIED: Check against the in-memory payments_data ***
    # Check if the token exists as a key in our payments database
    # This is a simplified validation. Real validation might check expiry, scope, etc.
    return token in payments_data 

# Dependency to get the authorization header
async def get_authorization_header(authorization: Optional[str] = Header(None)) -> Optional[str]:
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
    return None

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, user_agent: Optional[str] = Header(None), token: Optional[str] = Depends(get_authorization_header)):
    global payments_data # Need access to the global data
    is_bot_request = not user_agent or not is_browser(user_agent)

    if is_bot_request:
        # Handle Bot Request
        print(f"Bot request detected (User-Agent: {user_agent})")
        
        if validate_token(token):
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
            # Assuming the server runs on port 8000 as per the original example
            port = 8000 # TODO: Get port dynamically if needed
            payment_request_url = f"http://localhost:{port}/l402/payment-request"

            offers = [
                {
                  "id": "one_category",
                  "title": "Access to one category",
                  "description": "Access to all the data in one category",
                  "amount": 1,
                  "currency": "USD",
                  "payment_methods": ["paypal"] # Example method
                },
                {
                  "id": "all_categories",
                  "title": "Monthly Subscription",
                  "description": "Access all the data in our website for a month, any category, any time",
                  "amount": 5,
                  "currency": "USD",
                  "type": "subscription",
                  "duration": "1 month",
                  "payment_methods": ["paypal"] # Example method
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
    load_payments_db() # Load data into the global variable on startup

# --- New Payment Endpoint ---
@app.post("/l402/payment-request")
async def process_payment_request(payment_request: PaymentRequest):
    global payments_data # Ensure we modify the global variable
    print(f"Received payment request: {payment_request.dict()}")

    # TODO: Implement actual payment processing logic here
    payment_successful = True # Simulate successful payment

    if payment_successful:
        # *** Update in-memory store first ***
        payment_details = {
            "offer_id": payment_request.offer_id,
            "timestamp": datetime.datetime.now().isoformat() # Add timestamp for record
        }
        if payment_request.category:
             payment_details["category"] = payment_request.category
        
        payments_data[payment_request.payment_context_token] = payment_details
        print(f"In-memory payments data updated for token: {payment_request.payment_context_token}")

        # *** Then, persist the entire updated store to disk ***
        save_payments_db(payments_data)
        
        return {"message": "Payment successful", "bearer_token": payment_request.payment_context_token}
    else:
        raise HTTPException(status_code=400, detail="Payment processing failed")

# --- Main Execution ---
if __name__ == "__main__":
    import uvicorn
    # Startup logic moved to FastAPI event handler
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
    # Note: Using reload=True might cause the startup event to run multiple times
    # In production, run without reload or use a more robust state management.
