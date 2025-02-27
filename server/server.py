##################################################################################################
# Librairies
##################################################################################################
from fastapi import FastAPI, HTTPException, Depends, Request, Header, WebSocket, status
import httpx
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import logging
import asyncio
import json
import websockets
from pydantic import BaseModel, validator
from typing import Dict, Optional, List
from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import jwt, JWTError
import time
from contextlib import asynccontextmanager

##################################################################################################
# FastAPI Lifespan Event Handler
##################################################################################################
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the FastAPI application lifecycle for the TWAP trading server.
    This async context is espacially critical for two phases:
    
    1. Startup Phase (before the yield):
       - Initializes all trading pairs from Binance and Kraken exchanges
       - Populates the ORDER_BOOKS dictionary with initial data
       - Ensures market data is available before accepting client requests
    
    2. Shutdown Phase (after the yield):
       - Performs clean closing of all active WebSocket connections
       - Cancels all running tasks to prevent resource leaks
       - Ensures proper cleanup when the server is stopped
       
    This pattern guarantees proper resource initialization and cleanup
    regardless of how the application starts or terminates.
    """
    # Initialize trading pairs from exchanges during startup
    await initialize_trading_pairs()
    
    # Server is running and handling requests during this yield
    yield
    
    # Cleanup resources during shutdown
    for task in active_websockets.values():
        task.cancel()


##################################################################################################
# FastAPI application creation
##################################################################################################
app = FastAPI(
    title="TWAP Paper trading API using Binance or Kraken cryptocurrencies market data",
    description="""
    API for TWAP (Time-Weighted Average Price) paper trading on the cryptocurrency market.

    # 1. What are TWAP Orders ?
    TWAP orders execute large volumes by dividing them over a specified period to minimize market impact (slipping).

    # 2. Collected market data :
    - Collected in real-time via WebSocket from Binance or Kraken (choice given to the user).
    - Order book updates for supported trading pairs.

    # 3. Supported Exchanges and Pairs :
    - Binance: All available trading pairs
    - Kraken: All available trading pairs

    # 4. Authentication :
    - Uses an authentication token to access protected endpoints.

    # 5. Key Endpoints :
    - GET /exchanges: List of supported exchanges.
    - GET /orders: List all orders (requires authentication).
    - GET /orders/{token_id}: Status of a specific order.
    - GET /exchanges/{exchange}/pairs: Trading pairs (Websocket format) for an exchange.
    - GET /exchanges/kraken/pairs_restpoint: Kraken trading pairs in REST API format. For Binance, these are identical to the Websocket format
    - GET /klines/{exchange}/{symbol}: Get historical candlestick data.
    - POST /orders/twap: Submit a TWAP order.
    - WebSocket /ws: Real-time order book updates.

    # 6. Usage :
    - Simulates trading without risking real capital, ideal for testing strategies.
    """,
    version="1.0.0",
    contact={
        "name": "Tania ADMANE, Antonin DEVALLAND, Fanny GAUDUCHEAU, Lauryn LETACONNOUX, Giovanni MANCHE, \
            Cherine RHELLAB, Ariane TRUSSANT",
        "email": "giovanni.manche@dauphine.eu"},
    license_info={"name": "MIT"},
    lifespan=lifespan
)


##################################################################################################
# Rate Limiting configuration using SlowAPI
##################################################################################################
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


##################################################################################################
# Security / Authentication configiration
##################################################################################################
SECRET_KEY = "CryptoTWAPKey"  # For our purposes, no need to hide the key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Possible users
# For our purposes, we only create one type of user. 
users_db = {
    "premium": {
        "username": "premium",
        "hashed_password": pwd_context.hash("CryptoTWAPpremium"), 
    }
}
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# User and token models
class User(BaseModel):
    username: str

class Token(BaseModel):
    access_token: str
    token_type: str

def verify_password(plain_password, hashed_password) -> bool:
    """
    Check if the plain password corresponds to the hash one
    """
    return pwd_context.verify(plain_password, hashed_password)

# Authenticate user
def authenticate_user(username: str, password: str):
    """
    Verify the identity of the user (if the id is in the database and passwords match)
    """
    user = users_db.get(username)
    if not user or not verify_password(password, user["hashed_password"]):
        return False
    return User(username=user["username"])

def create_access_token(username: str):
    """
    Generate a JWT token
    """
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Decrypt the JWT token and get the corresponding user
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return User(username=username)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# Token endpoint
@app.post(
    "/token",
    response_model=Token,
    tags=["Authentication"],
    summary="Obtain an access token",
    description="""
    This endpoint allows a user to authenticate and obtain a JWT access token. 
    1. The user provides a valid username and password.
    2. If authentication is successful, a JWT token is returned.
    3. This token must be included in the `Authorization` header as `Bearer <token>` for protected endpoints.

    Request Body (form-data):
    - `username` (str): The username of the user.
    - `password` (str): The corresponding password.
    """,
    responses={
        200: {
            "description": "Successful authentication",
            "content": {
                "application/json": {
                    "example": {
                        "access_token": "eyJhbGciOiJIUzI1NiIsInR5c...",
                        "token_type": "bearer"
                    }
                }
            }
        },
        401: {
            "description": "Invalid credentials",
            "content": {
                "application/json": {
                    "example": {"detail": "Incorrect username or password"}
                }
            }
        }
    }
)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    OAuth2 authentication endpoint. Returns a JWT token if IDs are valid.
    """
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    access_token = create_access_token(user.username)
    return {"access_token": access_token, "token_type": "bearer"}


##################################################################################################
# Exchanges configuration 
##################################################################################################
SUPPORTED_EXCHANGES = ["binance", "kraken"]
TRADING_PAIRS = {
    "binance": [],
    "kraken": []
}

# Real-time trading books (will be completed dynamically)
ORDER_BOOKS = {}

# Global dictionary to track active WebSocket connections by pair
active_websockets = {}


##################################################################################################
# Functions to fetch all available trading pairs from exchanges
##################################################################################################
async def fetch_binance_pairs() -> List[str]:
    """
    Fetch all available trading pairs from Binance
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("https://api.binance.com/api/v3/exchangeInfo")
            if response.status_code == 200:
                data = response.json()
                # Extract all active trading pairs
                pairs = [symbol["symbol"] for symbol in data["symbols"] if symbol["status"] == "TRADING"]
                return pairs
            else:
                logging.error(f"Failed to fetch Binance pairs: {response.status_code}")
                return []
    except Exception as e:
        logging.error(f"Error fetching Binance pairs: {e}")
        return []

async def fetch_kraken_pairs(format_type: str = "websocket") -> List[str]:
    """
    Fetch all available trading pairs from Kraken 
    We have to take into account the differences between Restpoint and Websocket pairs format.
    When we fetch market data, via the Websocket connexion, we have to use the Websocket pair names.
    When we ask the API Respoint from Kraken (to get klines for instance), we have to use the Restpoint pair names.
    That is why the argument "format_type" is needed. 
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("https://api.kraken.com/0/public/AssetPairs")
            if response.status_code == 200:
                data = response.json()
                if data["error"]:
                    logging.error(f"Kraken API error: {data['error']}")
                    return []
                
                # If we need to use Restpoint trading pair names
                if format_type != "websocket":
                    api_pairs = []
                    for pair_info in data["result"].values():
                        if "altname" in pair_info:
                            api_pairs.append(pair_info["altname"])
                    return api_pairs
    
                # Else
                ws_pairs = []
                for pair_info in data["result"].values():
                    if "wsname" in pair_info:
                        ws_pairs.append(pair_info["wsname"])
                
                # Use altname as fallback if wsname is not available (just a precaution)
                for pair_key, pair_info in data["result"].items():
                    if "wsname" not in pair_info and "altname" in pair_info:
                        # Format altname to match WebSocket format if needed
                        altname = pair_info["altname"]
                        if "/" not in altname and len(altname) >= 6:
                            # Try to split into base/quote (simple approach)
                            mid = len(altname) // 2
                            formatted_altname = f"{altname[:mid]}/{altname[mid:]}"
                            ws_pairs.append(formatted_altname)
                
                logging.info(f"Fetched {len(ws_pairs)} Kraken pairs using WebSocket format")
                return ws_pairs
            else:
                logging.error(f"Failed to fetch Kraken pairs: {response.status_code}")
                return []
    except Exception as e:
        logging.error(f"Error fetching Kraken pairs: {e}")
        return []

async def initialize_trading_pairs():
    """
    Initialize the TRADING_PAIRS dictionary with all available pairs (Websocket format) from all exchanges
    """
    # TRADING_PAIRS and ORDER_BOOKS are used outside of this function
    global TRADING_PAIRS, ORDER_BOOKS
    
    # Fetch pairs from both exchanges 
    binance_task = asyncio.create_task(fetch_binance_pairs())
    kraken_task = asyncio.create_task(fetch_kraken_pairs(format_type="websocket"))
    
    binance_pairs = await binance_task
    kraken_pairs = await kraken_task
    
    # Update the TRADING_PAIRS dictionary
    TRADING_PAIRS["binance"] = binance_pairs
    TRADING_PAIRS["kraken"] = kraken_pairs
    
    # Initialize ORDER_BOOKS for all pairs
    for pair in binance_pairs:
        ORDER_BOOKS[pair] = {"ask_price": 0.0, "bid_price": 0.0}
    
    for pair in kraken_pairs:
        ORDER_BOOKS[pair] = {"ask_price": 0.0, "bid_price": 0.0}
    
    logging.info(f"Initialized {len(binance_pairs)} Binance pairs and {len(kraken_pairs)} Kraken pairs")


##################################################################################################
# WebSocket market data functions for individual pairs
##################################################################################################
async def fetch_market_data_for_pair(exchange: str, symbol: str):
    """
    Function to fetch market data for a specific pair via a specific exchange.
    """
    # Generate a unique key for this pair
    pair_key = f"{exchange}_{symbol}"
    
    # Check if we're already monitoring this pair
    if pair_key in active_websockets and not active_websockets[pair_key].done():
        return
    
    # Create tasks for either Kraken or Binance
    if exchange == "binance":
        active_websockets[pair_key] = asyncio.create_task(
            fetch_binance_pair_data(symbol)
        )
    elif exchange == "kraken":
        active_websockets[pair_key] = asyncio.create_task(
            fetch_kraken_pair_data(symbol)
        )

async def fetch_binance_pair_data(symbol: str):
    """
    Function to fetch market data from Binance for a specific pair.
    """
    stream = f"{symbol.lower()}@bookTicker"
    websocket_url = f"wss://stream.binance.com:9443/ws/{stream}"
    
    while True:
        try:
            # Websocket connection
            async with websockets.connect(websocket_url) as ws:
                logging.info(f"Connected to Binance WebSocket for {symbol}")
                
                while True:
                    response = await ws.recv()
                    
                    # Get real-time trading book prices
                    try:
                        data = json.loads(response)
                        if "s" in data:
                            ORDER_BOOKS[symbol] = {
                                "bid_price": float(data["b"]),
                                "ask_price": float(data["a"])
                            }
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        logging.error(f"Error processing Binance data: {e}")
        except Exception as e:
            logging.error(f"Binance WebSocket error for {symbol}: {e}")
            await asyncio.sleep(5)  # Wait before reconnecting

async def fetch_kraken_pair_data(symbol: str):
    """
    Function to fetch market data from Kraken for a specific pair using Websocket connection.  
    It uses the Websocket format.
    """
    websocket_url = "wss://ws.kraken.com/"
    
    while True:
        try:
            async with websockets.connect(websocket_url) as ws:
                logging.info(f"Connected to Kraken WebSocket for {symbol}")
                
                # Subscribe to this specific pair (already in WebSocket format)
                subscription_request = {
                    "event": "subscribe",
                    "reqid": 1,
                    "pair": [symbol],
                    "subscription": {"name": "ticker"}
                }
                logging.info(f"Sending Kraken subscription: {json.dumps(subscription_request)}")
                await ws.send(json.dumps(subscription_request))
                
                while True:
                    response = await ws.recv()
                    
                    try:
                        data = json.loads(response)
                        
                        # Check if it's an error or status message
                        if isinstance(data, dict) and "event" in data:
                            if data.get("event") == "subscriptionStatus":
                                status = data.get("status")
                                pair_id = data.get("pair", "")
                                if status == "error":
                                    error_msg = data.get("errorMessage", "Unknown error")
                                    logging.error(f"Kraken subscription error: {error_msg} for pair {pair_id}")
                                else:
                                    logging.info(f"Kraken subscription status: {status} for pair {pair_id}")
                        
                        # Check if it's ticker data (which comes as an array)
                        elif isinstance(data, list):
                            # In Kraken's WebSocket API, ticker data usually comes as:
                            # [channelID, tickerData, "ticker", pairName]
                            if len(data) >= 4 and data[2] == "ticker" and isinstance(data[1], dict):
                                ticker_data = data[1]
                                received_pair = data[3]
                                
                                # Prices extraction
                                if received_pair == symbol:
                                    if "b" in ticker_data and "a" in ticker_data:
                                        try:
                                            bid_price = float(ticker_data["b"][0])
                                            ask_price = float(ticker_data["a"][0])
                                            
                                            ORDER_BOOKS[symbol] = {
                                                "bid_price": bid_price,
                                                "ask_price": ask_price
                                            }
                                            
                                            logging.info(f"Updated Kraken prices for {symbol}: Bid={bid_price}, Ask={ask_price}")
                                        except (IndexError, ValueError) as e:
                                            logging.error(f"Error parsing Kraken price data: {e}")
                    except json.JSONDecodeError as e:
                        logging.warning(f"Failed to decode JSON from Kraken WebSocket: {e}")
                    except Exception as e:
                        logging.error(f"Error processing Kraken data: {e}")
        except Exception as e:
            logging.error(f"Kraken WebSocket error for {symbol}: {e}")
            await asyncio.sleep(5)  # Wait before reconnecting


##################################################################################################
# Order models 
##################################################################################################
class OrderBase(BaseModel):
    """
    Base model class that initialize the order. 
    We verify that the order type is correct.
    """
    token_id: str
    exchange: str
    symbol: str
    quantity: float
    price: float
    order_type: str

    @validator('order_type')
    def validate_order_type(cls, v):
        if v not in ["buy", "sell"]:
            raise ValueError("Order type must be 'buy' or 'sell'!")
        return v

class Order(OrderBase):
    """
    Herits from OrderBase and add some elements like the status, the current executed quantity of the TWAP and the list of orders executed. 
    """
    status: str = "open"
    executed_quantity: float = 0.0
    executions: list = []

ORDERS = []  # Saved orders list
connected_clients = []  # Websocket connected clients


##################################################################################################
# API endpoints
##################################################################################################
"""
Endpoint to make sure the server is running.
We limit the number of requests per minute to 20.
"""
@app.get("/",
         tags = ['General'],
         summary = "API Root",
         description= "Returns a simple welcome message to confirm the API is running")
@limiter.limit("20/minute")
async def root(request: Request):
    return {"message": "The Cryptocurrency TWAP paper trading API is running !"}

"""
Endpoint to get the list of supported exchanges (binance and kraken).
We limit the number of requests per minute to 15.
"""
@app.get("/exchanges",
         tags = ["Exchanges"],
         summary = "List supported exchanges")
@limiter.limit("15/minute")
async def get_exchanges(request: Request):
    return {"exchanges": SUPPORTED_EXCHANGES}

"""
Endpoint to get the trading pairs (websocket format) for a given exchange.
We limit the number of requests per minute to 15.
"""
@app.get("/exchanges/{exchange}/pairs",
         tags = ["Exchanges"],
         summary = "Retrieve trading pairs (websocket format) for a given exchange",
          responses={
            200: {
                "description": "Successful response",
                "content": {"application/json": {"example": {"exchange": "binance", "pairs": ["BTCUSDT", "ETHUSDT", "..."]}}}
            },
            404: {
                "description": "Exchange not found",
                "content": {"application/json": {"example": {"detail": "Exchange 'unknown' not found"}}}
            }})
@limiter.limit("15/minute")
async def get_trading_pairs(exchange: str, request: Request):
    if exchange not in SUPPORTED_EXCHANGES:
        raise HTTPException(status_code=404, detail=f"Exchange '{exchange}' not found")
    return {"exchange": exchange, "pairs": TRADING_PAIRS[exchange]}

"""
Endpoint to get Restpoint formatted trading pairs for Kraken.
Useful for the klines. 
We limit the number of requests per minute to 15.
"""
@app.get("/exchanges/kraken/pairs_restpoint",
         tags=["Exchanges"],
         summary="Retrieve Kraken trading pairs in REST API format, which are used to get klines.",
         responses={
             200: {
                 "description": "Successful response",
                 "content": {"application/json": {"example": {"exchange": "kraken", "pairs": ["XBTUSD", "ETHUSD", "..."]}}}
             },
             404: {
                 "description": "Error fetching pairs",
                 "content": {"application/json": {"example": {"detail": "Failed to fetch Kraken pairs"}}}
             }})
@limiter.limit("15/minute")
async def get_kraken_restpoint_pairs(request: Request):
    try:
        # Get pairs specifically in Restpoint format
        kraken_pairs = await fetch_kraken_pairs(format_type="restpoint")
        return {"exchange": "kraken", "pairs": kraken_pairs}
    except Exception as e:
        logging.error(f"Error fetching Kraken REST pairs: {e}")
        raise HTTPException(status_code=404, detail=f"Failed to fetch Kraken pairs: {str(e)}")

"""
Endpoint to list the current orders.
We limit the number of requests per minute to 10.
"""
@app.get("/orders", 
         dependencies=[Depends(get_current_user)],
         tags = ["Orders"],
         summary = "List all orders", 
         description = 
            """
            Retrives all orders, with optional filtering by token_id.
            """,
        responses={
        200: {
            "description": "Returns the list of orders",
            "content": {"application/json": {"example": {"orders": [{"token_id": "twap_btc", "status": "open"}]}}}
        },
        401: {
            "description": "Unauthorized",
            "content": {"application/json": {"example": {"detail": "Unauthorized"}}}
        }   
        })
@limiter.limit("10/minute")
async def list_orders(request: Request, token_id: Optional[str] = None):
    filtered_orders = [order for order in ORDERS if not token_id or order.token_id == token_id]
    return {"orders": filtered_orders}

"""
Endpoint to retrieve the status of a specific order.
We limit the number of requests per minute to 10.
"""
@app.get(
    "/orders/{token_id}",
    dependencies=[Depends(get_current_user)],
    tags=["Orders"],
    summary="Get order status",
    description=
        """
        Retrieves the status of a specific order based on the token_id.

            - token_id : Unique identifier of the order.
            - Returns : Order details including execution status.
        """,
    responses={
        200: {
            "description": "Successful response",
            "content": {"application/json": {"example": {"token_id": "twap_btc", "status": "completed"}}}
        },
        404: {
            "description": "Order not found",
            "content": {"application/json": {"example": {"detail": "Order with token_id 'twap_btc' not found"}}}
        }
    }
)
@limiter.limit("10/minute") 
async def get_order_status(token_id: str, request: Request):
    order = next((order for order in ORDERS if order.token_id == token_id), None)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order with token_id '{token_id}' not found")
    return order.dict()

"""
Endpoint to get candlesticks data.
We limit the number of requests per minute to 10.
"""
@app.get("/klines/{exchange}/{symbol}", 
            tags=["Klines"], summary="Get historical candlestick data",
            description=
            """
            Retrieves historical candlestick data for a given exchange and symbol.
            Symbol should be at the Restpoint format (given by the endpoint to get trading pairs).
            Interval should be one of the follwing : 
                - for Binance : ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"]
                - for Kraken : ["1", "5", "15", "30", "60", "240", "1440", "10080", "21600"]
            Limit shoud be between 0 and 1000.
            """,
            responses={
             200: {
                 "description": "Successful response",
                 "content": {"application/json": {"example": {"klines": [["1609459200000", "33000.00", "33500.00", "32500.00", "33200.00", "1.500"]]}}}
             },
             400: {
                 "description": "Invalid request",
                 "content": {"application/json": {"example": {"detail": "Invalid interval or limit"}}}
             },
             404: {
                 "description": "Exchange or symbol not found",
                 "content": {"application/json": {"example": {"detail": "Exchange or symbol not found"}}}
             }
         })
@limiter.limit("10/minute")
async def get_klines(exchange: str, symbol: str, interval: str, limit: int, request: Request):
    valid_intervals = {
        "binance": ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"],
        "kraken": ["1", "5", "15", "30", "60", "240", "1440", "10080", "21600"]
    }
    # We get the Restpoint format trading pairs. 
    restpoint_pairs = TRADING_PAIRS[exchange] if exchange == "binance" else await fetch_kraken_pairs(format_type="restpoint")
    if exchange not in SUPPORTED_EXCHANGES:
        raise HTTPException(status_code=404, detail="Exchange not found")
    if symbol not in restpoint_pairs:
        raise HTTPException(status_code=404, detail="Symbol not found")
    if interval not in valid_intervals[exchange]:
        raise HTTPException(status_code=400, detail="Invalid interval")
    if limit <= 0 or limit > 1000:
        raise HTTPException(status_code=400, detail="Invalid limit. Limit must be between 1 and 1000.")

    # Initiate market data connection for this pair
    await fetch_market_data_for_pair(exchange, symbol)
    if exchange == "binance":
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    elif exchange == "kraken":
        kraken_interval = interval 
        url = f"https://api.kraken.com/0/public/OHLC?pair={symbol}&interval={kraken_interval}&since=0"

    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Error fetching klines data")

        data = response.json()
        if exchange == "binance":
            klines = [
                [
                    kline[0],  # Open time
                    kline[1],  # Open
                    kline[2],  # High
                    kline[3],  # Low
                    kline[4],  # Close
                    kline[5]   # Volume
                ]
                for kline in data
            ]
        elif exchange == "kraken":
            result_keys = list(data["result"].keys())
            if result_keys and not data.get("error"):
                klines = [
                    [
                        int(kline[0]) * 1000,  # Open time (converted in milliseconds)
                        kline[1],  # Open
                        kline[2],  # High
                        kline[3],  # Low
                        kline[4],  # Close
                        kline[6]   # Volume
                    ]
                    for kline in data["result"][result_keys[0]]
                ][:limit]  
            else:
                error_msg = data.get("error", ["Unknown error"])[0]
                raise HTTPException(status_code=400, detail=f"Kraken API error: {error_msg}")

    return {"klines": klines}

"""
Endpoint to submit TWAP orders to the given exchange.
We limit the number of requests per minute to 10.
"""
@app.post(
    "/orders/twap",
    dependencies=[Depends(get_current_user)],
    tags=["Orders"],
    summary="Submit a TWAP order",
    description=
    """
    Submits a TWAP (Time-Weighted Average Price) order to be executed over a given time.

    - order_data : Contains details such as symbol, quantity, price, and order type.
    - execution_time : Total duration for TWAP execution (default: 600s).
    - interval : Interval between partial executions (default: 60s).
    """,
    responses={
        201: {
            "description": "TWAP order accepted",
            "content": {"application/json": {"example": {"message": "TWAP order accepted", "order_id": "twap_btc"}}}
        },
        400: {
            "description": "Invalid order request",
            "content": {"application/json": {"example": {"detail": "Symbol 'XYZUSD' not supported"}}}
        },
        401: {
            "description": "Unauthorized",
            "content": {"application/json": {"example": {"detail": "Unauthorized"}}}
        }
    }
)
@limiter.limit("10/minute")
async def submit_twap_order(request: Request, order_data: OrderBase, execution_time: int = 600, interval: int = 60):
    # Basic checking
    if order_data.exchange not in SUPPORTED_EXCHANGES:
        raise HTTPException(status_code=400, detail=f"Exchange '{order_data.exchange}' not supported")
    if order_data.symbol not in TRADING_PAIRS[order_data.exchange]:
        raise HTTPException(status_code=400, detail=f"Symbol '{order_data.symbol}' not supported")

    # Initiate market data connection for this pair
    await fetch_market_data_for_pair(order_data.exchange, order_data.symbol)

    # Wait for market data to be available
    # Indeed, it can cause problems if we don't wait, as the initial prices are 0.0
    max_wait_time = 30  
    elapsed_time = 0
    while elapsed_time < max_wait_time:
        if order_data.symbol in ORDER_BOOKS:
            market_price = ORDER_BOOKS[order_data.symbol]["ask_price"] if order_data.order_type == "buy" else ORDER_BOOKS[order_data.symbol]["bid_price"]
            # If the condition is respected, it means that market data has arrived
            if market_price != 0.0:
                break
        await asyncio.sleep(1)
        elapsed_time += 1
        
        if elapsed_time % 5 == 0:
            logging.info(f"Waiting for market data for {order_data.symbol}, elapsed time: {elapsed_time}s")
            if order_data.symbol in ORDER_BOOKS:
                logging.info(f"Current prices: {ORDER_BOOKS[order_data.symbol]}")
            else:
                logging.info(f"{order_data.symbol} not yet in ORDER_BOOKS")

    # Verify if market data are valid. 
    if order_data.symbol not in ORDER_BOOKS or ORDER_BOOKS[order_data.symbol]["ask_price"] == 0.0:
        raise HTTPException(status_code=400, detail=f"No valid market data available for {order_data.symbol} after {max_wait_time}s")

    # Aggressive orders
    market_price = ORDER_BOOKS[order_data.symbol]["ask_price"] if order_data.order_type == "buy" else ORDER_BOOKS[order_data.symbol]["bid_price"]
    order_data.price = market_price if order_data.price == 0.0 else order_data.price
    
    # Formatting the order in an acceptable class
    order = Order(**order_data.dict())
    ORDERS.append(order)

    # Create a task to execute the TWAP order
    asyncio.create_task(execute_twap_order(order, execution_time, interval))

    return {"message": "TWAP order accepted", "order_id": order.token_id, "order_details": order.dict()}


##################################################################################################
# TWAP execution engine 
##################################################################################################
async def execute_twap_order(order: Order, execution_time: int, interval: int):
    """
    Executes a TWAP order by dividing it into smaller chunks over a specified time period to minimize market impact.
    To do so, we slice the original order into equal-sized sub-orders, execute each sub-order
    at regular intervals (checking market conditions each time), and we execute the sub order only if 
    the market price is favourable regarding the order price and the order type. We update status and execution
    history after each step and mark as completed or partial once the full time period has passed.
    
    Arguments :
    -----------
        order (Order): The Order object containing trading pair, quantity, price, and direction
        execution_time (int): Total execution time in seconds for the TWAP order
        interval (int): Time interval in seconds between each execution step
        
    Remarks :
    -----------
        - Order execution is simulated for paper trading purposes
        - Execution only occurs if market price meets limit price conditions
        - Real-time market data is retrieved from the ORDER_BOOKS global dictionary
    """
    number_of_steps = execution_time // interval     # Number of steps = orders to be submitted
    quantity_per_step = order.quantity / number_of_steps    # Quantity per order

    for step in range(number_of_steps):
        # We wait for the specified interval before processing the next execution step
        await asyncio.sleep(interval)

        # Current market price 
        if order.symbol in ORDER_BOOKS:
            market_price = ORDER_BOOKS[order.symbol]["ask_price"] if order.order_type == "buy" else ORDER_BOOKS[order.symbol]["bid_price"]
            print(f" TWAP - Step {step+1}: Market Price = {market_price}, Order Price = {order.price}")
            
            # Order execution (agressive order is supposed)
            # At each time we update the information about the total order
            if (order.order_type == "buy" and market_price <= order.price) or (order.order_type == "sell" and market_price >= order.price):
                order.executed_quantity += quantity_per_step
                order.executions.append({"step": step + 1, "price": market_price, "quantity": quantity_per_step})
                print(f"TWAP exécuté - Step {step+1}: {quantity_per_step} exécuté à {market_price}")
            else:
                print(f"TWAP NON exécuté - Prix marché ({market_price}) > {order.price}")
        else:
            print(f"TWAP NON exécuté - Symbol {order.symbol} not in ORDER_BOOKS")

    order.status = "completed" if order.executed_quantity >= order.quantity else "partial"

##################################################################################################
# WebSocket price update
##################################################################################################
async def send_order_book_update()-> None:
    """
    Function that aims to diffuse the trading book updates
    """
    data = {"order_book": ORDER_BOOKS}
    for client in connected_clients:
        try:
            await client.send_json(data)
        except:
            connected_clients.remove(client)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Establishes a WebSocket connection to receive real-time updates of the order book. It :
    - Accepts the WebSocket connection.
    - Adds the client to the list of connected clients.
    - Continuously sends the latest order book updates every second.
    - Prints order book updates to the terminal.
    """
    await websocket.accept()
    connected_clients.append(websocket)
    logging.info(f"WebSocket client connected. Total clients: {len(connected_clients)}")

    try:
        while True:
            # Print real-time prices in the terminal
            for symbol, prices in ORDER_BOOKS.items():
                if prices["bid_price"] > 0 or prices["ask_price"] > 0:
                    print(f"[OrderBook] {symbol}: Bid={prices['bid_price']}, Ask={prices['ask_price']}")
            
            await send_order_book_update()
            await asyncio.sleep(1)
    except Exception as e:
        logging.error(f"WebSocket error: {e}")
    finally:
        connected_clients.remove(websocket)
        logging.info(f"WebSocket client disconnected. Remaining clients: {len(connected_clients)}")

if __name__ == "__main__":
    """
    Launcher
    """
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
