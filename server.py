##################################################################################################
# Librairies
##################################################################################################
from fastapi import FastAPI, HTTPException, Depends, Request, Header, WebSocket, status
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
from typing import Dict, Optional
from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import jwt, JWTError

##################################################################################################
# FastAPI server initialisation
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
    - Binance: BTCUSDT, ETHUSDT
    - Kraken: XBTUSD, ETHUSD

    # 4. Authentication :
    - Uses an authentication token to access protected endpoints.

    # 5. Key Endpoints :
    - GET /exchanges: List of supported exchanges.
    - GET /orders: List all orders (requires authentication).
    - GET /orders/{token_id}: Status of a specific order.
    - GET /exchanges/{exchange}/pairs: Trading pairs for an exchange.
    - POST /orders/twap: Submit a TWAP order.

    # 6. Usage :
    - Simulates trading without risking real capital, ideal for testing strategies.
    """,
    version="1.0.0",
    contact={
        "name": "Tania ADMANE, Antonin DEVALLAND, Fanny GAUDUCHEAU, Lauryn LETACONNOUX, Giovanni MANCHE, \
            Cherine RHELLAB, Ariane TRUSSANT",
        "email": "giovanni.manche@dauphine.eu"},
    license_info={"name": "MIT"}
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
users_db = {
    "premium": {
        "username": "premium",
        "hashed_password": pwd_context.hash("CryptoTWAPpremium"),  # Hashed version of "TaniaEstKo"
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
    Décode le token JWT et récupère l'utilisateur correspondant.
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
    "binance": ["BTCUSDT", "ETHUSDT"],
    "kraken": ["XBTUSD", "ETHUSD"]
}

# Real-time trading books
ORDER_BOOKS = {
    "BTCUSDT": {"ask_price": 0.0, "bid_price": 0.0},
    "ETHUSDT": {"ask_price": 0.0, "bid_price": 0.0},
    "XBTUSD": {"ask_price": 0.0, "bid_price": 0.0},
    "ETHUSD": {"ask_price": 0.0, "bid_price": 0.0}
}

##################################################################################################
# Order models 
##################################################################################################
class OrderBase(BaseModel):
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
    status: str = "open"
    executed_quantity: float = 0.0
    executions: list = []

ORDERS = []  # Saved orders list
connected_clients = []  # Websocket connected clients

##################################################################################################
# API endpoints
##################################################################################################

@app.get("/",
         tags = ['General'],
         summary = "API Root",
         description= "Returns a simple welcome message to confirm the API is running")
@limiter.limit("20/minute")
async def root(request: Request):
    return {"message": "The Cryptocurrency TWAP paper trading API is running !"}

@app.get("/exchanges",
         tags = ["Exchanges"],
         summary = "List supported exchanges")
@limiter.limit("15/minute")
async def get_exchanges(request: Request):
    return {"exchanges": SUPPORTED_EXCHANGES}

@app.get("/exchanges/{exchange}/pairs",
         tags = ["Exchanges"],
         summary = "Retrieve trading pairs for a given exchange",
          responses={
            200: {
                "description": "Successful response",
                "content": {"application/json": {"example": {"exchange": "binance", "pairs": ["BTCUSDT", "ETHUSDT"]}}}
            },
            404: {
                "description": "Exchange not found",
                "content": {"application/json": {"example": {"detail": "Exchange 'unknown' not found"}}}
            }})
@limiter.limit("15/minute")
async def get_trading_pairs(exchange: str, request: Request):
    if exchange not in SUPPORTED_EXCHANGES:
        raise HTTPException(status_code=404, detail=f"Exchange '{exchange}' not found")
    return {"pairs": TRADING_PAIRS[exchange]}

@app.get("/orders", 
         dependencies=[Depends(get_current_user)],
         tags = ["Orders"],
         summary = "List all orders", 
         description = """
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

@app.get(
    "/orders/{token_id}",
    dependencies=[Depends(get_current_user)],
    tags=["Orders"],
    summary="Get order status",
    description="""
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

@app.post(
    "/orders/twap",
    dependencies=[Depends(get_current_user)],
    tags=["Orders"],
    summary="Submit a TWAP order",
    description="""
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
    if order_data.exchange not in SUPPORTED_EXCHANGES:
        raise HTTPException(status_code=400, detail=f"Exchange '{order_data.exchange}' not supported")
    if order_data.symbol not in TRADING_PAIRS[order_data.exchange]:
        raise HTTPException(status_code=400, detail=f"Symbol '{order_data.symbol}' not supported")

    order = Order(**order_data.dict())
    ORDERS.append(order)

    asyncio.create_task(execute_twap_order(order, execution_time, interval))

    return {"message": "TWAP order accepted", "order_id": order.token_id, "order_details": order.dict()}

##################################################################################################
# TWAP execution engine 
##################################################################################################
async def execute_twap_order(order: Order, execution_time: int, interval: int):
    number_of_steps = execution_time // interval     # Number of steps = orders to be submitted
    quantity_per_step = order.quantity / number_of_steps    # Quantity per order

    for step in range(number_of_steps):
        # We wait for the specified interval before processing the next execution step
        await asyncio.sleep(interval)

        # Current market price 
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
    """
    await websocket.accept()
    connected_clients.append(websocket)

    try:
        while True:
            await send_order_book_update()
            await asyncio.sleep(1)
    except:
        connected_clients.remove(websocket)

async def fetch_market_data():
    """
    Function that continuously fetch market data from Binance and Kraken
    Connection via Websocket
    """
    while True:
        try:
            # Websocket connection to Binance (for BTCUSDT and ETHUSDT pairs)
            async with websockets.connect("wss://stream.binance.com:9443/ws/btcusdt@bookTicker/ethusdt@bookTicker") as ws_binance:
                # Websocket connection to Kraken (for XBTUSD and ETHUSD pairs)
                async with websockets.connect("wss://ws.kraken.com/") as ws_kraken:
                    await ws_kraken.send(json.dumps({
                        "event": "subscribe",
                        "pair": ["XBT/USD", "ETH/USD"],
                        "subscription": {"name": "ticker"}
                    }))

                    # loop to continuously receive data
                    while True:
                        binance_response = await ws_binance.recv()
                        kraken_response = await ws_kraken.recv()

                        # Passing the responses as JSON
                        try:
                            binance_data = json.loads(binance_response)
                        except json.JSONDecodeError:
                            continue

                        try:
                            kraken_data = json.loads(kraken_response)
                        except json.JSONDecodeError:
                            continue

                        # Process Binance data if it contains symbol + bid + ask information and update the order book.
                        if isinstance(binance_data, dict) and "s" in binance_data and "b" in binance_data and "a" in binance_data:
                            symbol = binance_data["s"]
                            ORDER_BOOKS[symbol] = {
                                "bid_price": float(binance_data["b"]),
                                "ask_price": float(binance_data["a"])
                            }

                        # Process Kraken data if it is a list with sufficient information and ticker data is present.
                        if isinstance(kraken_data, list) and len(kraken_data) > 2 and isinstance(kraken_data[1], dict):
                            ticker_data = kraken_data[1]
                            symbol = kraken_data[3]

                            if "a" in ticker_data and "b" in ticker_data:
                                if symbol == "XBT/USD":
                                    ORDER_BOOKS["XBTUSD"] = {
                                        "bid_price": float(ticker_data["b"][0]),
                                        "ask_price": float(ticker_data["a"][0])
                                    }
                                elif symbol == "ETH/USD":
                                    ORDER_BOOKS["ETHUSD"] = {
                                        "bid_price": float(ticker_data["b"][0]),
                                        "ask_price": float(ticker_data["a"][0])
                                    }

                        await send_order_book_update()
        except Exception as e:
            print(f"Erreur lors de la récupération des données de marché : {e}")
            await asyncio.sleep(5)

@app.on_event("startup")
async def startup_event():
    # Creation and scheduling of asyncrhonous task to continuously fetch market data
    asyncio.create_task(fetch_market_data())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
