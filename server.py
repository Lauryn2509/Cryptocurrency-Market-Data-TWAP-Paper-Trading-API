"""
Crypto Trading API - Server
Manages real market data, TWAP execution, and WebSocket price updates.
"""

from fastapi import FastAPI, HTTPException, Query, Depends, Header, WebSocket
import asyncio
import json
import websockets
import requests
from pydantic import BaseModel, validator
from typing import List, Optional

# Initialisation du serveur FastAPI
app = FastAPI(
    title = "TWAP Paper trading API using Binance or Kraken cryptocurrencies market data",
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
    - `GET /exchanges`: List of supported exchanges.
    - `GET /orders`: List all orders (requires authentication).
    - `GET /orders/{token_id}`: Status of a specific order.
    - `GET /exchanges/{exchange}/pairs`: Trading pairs for an exchange.
    - `POST /orders/twap`: Submit a TWAP order.

    # 6. Usage :
    - Simulates trading without risking real capital, ideal for testing strategies.
    """,
    version = "1.0.0",
    contact = {
        "name": "Giovanni MANCHE",
        "email": "giovanni.manche@dauphine.eu"},
        license_info={"name": "MIT"})

# Exchanges et paires supportés
SUPPORTED_EXCHANGES = ["binance", "kraken"]
TRADING_PAIRS = {
    "binance": ["BTCUSDT", "ETHUSDT"],
    "kraken": ["XBT/USD", "ETH/USD"]  
}


# Stockage des carnets d'ordres en temps réel
ORDER_BOOKS = {
    "BTCUSDT": {"ask_price": 0.0, "bid_price": 0.0},
    "ETHUSDT": {"ask_price": 0.0, "bid_price": 0.0},
    "XBT/USD": {"ask_price": 0.0, "bid_price": 0.0},
    "ETH/USD": {"ask_price": 0.0, "bid_price": 0.0}
}

# Authentification
AUTH_TOKEN = "TaniaEstKo"

def get_auth_token(x_token: str = Header(...)):
    if x_token != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return x_token

# Modèles d'ordres
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

ORDERS = []
connected_clients = []

# Les endpoints REST restent les mêmes...

### **WEBSOCKET PRICE UPDATES** ###

async def send_order_book_update():
    data = {"order_book": ORDER_BOOKS}
    for client in connected_clients:
        try:
            await client.send_json(data)
        except:
            connected_clients.remove(client)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)

    try:
        while True:
            await send_order_book_update()
            await asyncio.sleep(1)
    except:
        connected_clients.remove(websocket)

### **MARKET DATA COLLECTION** ###

async def fetch_binance_market_data():
    while True:
        try:
            async with websockets.connect("wss://stream.binance.com:9443/ws/btcusdt@bookTicker/ethusdt@bookTicker") as ws:
                while True:
                    response = await ws.recv()
                    data = json.loads(response)
                    symbol = data["s"]
                    ORDER_BOOKS[symbol] = {"bid_price": float(data["b"]), "ask_price": float(data["a"])}
                    await send_order_book_update()
        except:
            await asyncio.sleep(5)

async def fetch_kraken_market_data():
    while True:
        try:
            async with websockets.connect("wss://ws.kraken.com") as ws:
                # Subscribe to XBT/USD and ETH/USD book
                subscribe_message = {
                    "event": "subscribe",
                    "pair": ["XBT/USD", "ETH/USD"],
                    "subscription": {
                        "name": "book",
                        "depth": 1
                    }
                }
                await ws.send(json.dumps(subscribe_message))

                while True:
                    response = await ws.recv()
                    data = json.loads(response)
                    
                    # Vérification des messages de type "event"
                    if isinstance(data, dict) and "event" in data:
                        continue
                    
                    # Vérification des mises à jour du carnet d'ordres
                    if isinstance(data, list) and len(data) >= 4:
                        pair_name = data[3]  # Le nom de la paire
                        
                        if "b" in data[1] or "a" in data[1]:  # Vérifie si on a des mises à jour bid/ask
                            bid_price = float(data[1]["b"][0][0]) if "b" in data[1] else ORDER_BOOKS[pair_name]["bid_price"]
                            ask_price = float(data[1]["a"][0][0]) if "a" in data[1] else ORDER_BOOKS[pair_name]["ask_price"]
                            
                            ORDER_BOOKS[pair_name] = {
                                "bid_price": bid_price,
                                "ask_price": ask_price
                            }
                            await send_order_book_update()
        except Exception as e:
            print(f"Kraken WebSocket error: {e}")
            await asyncio.sleep(5)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(fetch_binance_market_data())
    asyncio.create_task(fetch_kraken_market_data())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
