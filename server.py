##################################################################################################
# Librairies
##################################################################################################
from fastapi import FastAPI, HTTPException, Depends, Request, Header, WebSocket
from fastapi.responses import JSONResponse
from fastapi.security.api_key import APIKeyHeader
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import logging 
import asyncio
import json
import websockets
from pydantic import BaseModel, validator
from typing import Dict, Optional

##################################################################################################
# FastAPI server initialisation
##################################################################################################
app = FastAPI(
    title = "TWAP Paper trading API using Binance or Kraken cryptocurrencies market data",
    description=
    """
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
    version = "1.0.0",
    contact = {
        "name": "Tania ADMANE, Antonin DEVALLAND, Fanny GAUDUCHEAU, Lauryn LETACONNOUX, Giovanni MANCHE, \
            Cherine RHELLAB, Ariane TRUSSANT",
        "email": "giovanni.manche@dauphine.eu"},
        license_info={"name": "MIT"}
)

##################################################################################################
# API Key configuaration - authentication
##################################################################################################
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# Clés API et leurs infos (pour l'exemple, seules les clés sont utilisées pour l'identification)
API_KEYS: Dict[str, Dict] = {
    "TaniaEstKo": {
        "client_name": "default_client",
        # Les paramètres de rate limit custom ne sont plus utilisés ici
    },
    # D'autres clés peuvent être ajoutées
}

AUTH_TOKEN = "TaniaEstKo"

def get_auth_token(x_token: str = Header(...)) -> str:
    if x_token != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return x_token

##################################################################################################
# Rate limiting using SlowAPI
##################################################################################################
def custom_rate_limit_key(request: Request) -> str:
    api_key = request.headers.get(API_KEY_NAME)
    if api_key and api_key in API_KEYS:
        return f"apikey_{api_key}"
    return request.client.host

limiter = Limiter(key_func=custom_rate_limit_key)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
@limiter.limit("20/minute")  # 20 requests per minute are allowed
async def root(request: Request):
    return {"message": "272 API"}


@app.get("/exchanges",
         tags = ["Exchanges"],
         summary = "List supported exchanges")
@limiter.limit("15/minute") # 15 requests per minute are allowed
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
@limiter.limit("15/minute") # 15 requests per minute are allowed
async def get_trading_pairs(exchange: str, request: Request):
    if exchange not in SUPPORTED_EXCHANGES:
        raise HTTPException(status_code=404, detail=f"Exchange '{exchange}' not found")
    return {"pairs": TRADING_PAIRS[exchange]}

@app.get("/orders", 
         dependencies=[Depends(get_auth_token)],
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
@limiter.limit("10/minute") # 15 requests per minute are allowed
async def list_orders(request: Request, token_id: Optional[str] = None):
    filtered_orders = [order for order in ORDERS if not token_id or order.token_id == token_id]
    return {"orders": filtered_orders}

@app.get(
    "/orders/{token_id}",
    dependencies=[Depends(get_auth_token)],
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
@limiter.limit("10/minute") # 10 requests per minute are allowed
async def get_order_status(token_id: str, request: Request):
    order = next((order for order in ORDERS if order.token_id == token_id), None)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order with token_id '{token_id}' not found")
    return order.dict()

@app.post(
    "/orders/twap",
    dependencies=[Depends(get_auth_token)],
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
@limiter.limit("10/minute") # 10 requests per minute are allowed
async def submit_twap_order(order_data: OrderBase, request: Request, execution_time: int = 600, interval: int = 60) -> dict:
    if order_data.exchange not in SUPPORTED_EXCHANGES:
        raise HTTPException(status_code=400, detail=f"Exchange '{order_data.exchange}' not supported")
    if order_data.symbol not in TRADING_PAIRS[order_data.exchange]:
        raise HTTPException(status_code=400, detail=f"Symbol '{order_data.symbol}' not supported")

    order = Order(**order_data.dict())
    ORDERS.append(order)

    asyncio.create_task(execute_twap_order(order, execution_time, interval))

    return {"message": "TWAP order accepted", "order_id": order.token_id, "order_details": order.dict()}

@app.websocket("/ws")
@limiter.limit("15/minute")
async def websocket_endpoint(websocket: WebSocket) -> None:
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

##################################################################################################
# TWAP execution engine 
##################################################################################################
async def execute_twap_order(order: Order, execution_time: int, interval: int) -> None:
    number_of_steps = execution_time // interval   # Number of steps = orders to be submitted
    quantity_per_step = order.quantity / number_of_steps # Quantity per order

    for step in range(number_of_steps):
        # We wait for the specified interval before processing the next execution step
        await asyncio.sleep(interval)

        # Current market price 
        market_price = ORDER_BOOKS[order.symbol]["ask_price"] if order.order_type == "buy" else ORDER_BOOKS[order.symbol]["bid_price"]
        logging.debug(f"TWAP - Step {step+1}: Market Price = {market_price}, Order Price = {order.price}")

        # Order execution (agressive order is supposed)
        # At each time we update the information about the total order
        if (order.order_type == "buy" and market_price <= order.price) or (order.order_type == "sell" and market_price >= order.price):
            order.executed_quantity += quantity_per_step
            order.executions.append({"step": step + 1, "price": market_price, "quantity": quantity_per_step})
            logging.debug(f"TWAP exécuté - Step {step+1}: {quantity_per_step} exécuté à {market_price}")
        else:
            logging.debug(f"TWAP NON exécuté - Prix marché ({market_price}) > {order.price}")

    order.status = "completed" if order.executed_quantity >= order.quantity else "partial"

##################################################################################################
# WebSocket price update
##################################################################################################

async def send_order_book_update() -> None:
    """
    Function that aims to diffuse the trading book updates
    """
    data = {"order_book": ORDER_BOOKS}
    for client in connected_clients:
        try:
            await client.send_json(data)
        except:
            connected_clients.remove(client)



async def fetch_market_data() -> None:
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
                    
                        # Passign the responses as JSON
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
            logging.debug(f"Erreur lors de la récupération des données de marché : {e}")
            await asyncio.sleep(5)

@app.on_event("startup")
async def startup_event():
    # Creation and schedulong of asyncrhonous task to continuously fetch market data
    asyncio.create_task(fetch_market_data())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
