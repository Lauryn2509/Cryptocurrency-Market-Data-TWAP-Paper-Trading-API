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
app = FastAPI()

# Exchanges et paires supportés
SUPPORTED_EXCHANGES = ["binance", "kraken"]
TRADING_PAIRS = {
    "binance": ["BTCUSDT", "ETHUSDT"],
    "kraken": ["XBTUSD", "ETHUSD"]
}

# Stockage des carnets d'ordres en temps réel
ORDER_BOOKS = {
    "BTCUSDT": {"ask_price": 0.0, "bid_price": 0.0},
    "ETHUSDT": {"ask_price": 0.0, "bid_price": 0.0}
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

ORDERS = []  # Liste des ordres enregistrés
connected_clients = []  # Clients WebSocket connectés

### **API ENDPOINTS** ###

@app.get("/")
async def root():
    return {"message": "272 API"}

@app.get("/exchanges")
async def get_exchanges():
    return {"exchanges": SUPPORTED_EXCHANGES}

@app.get("/orders", dependencies=[Depends(get_auth_token)])
async def list_orders(token_id: Optional[str] = None):
    filtered_orders = [order for order in ORDERS if not token_id or order.token_id == token_id]
    return {"orders": filtered_orders}

@app.get("/orders/{token_id}", dependencies=[Depends(get_auth_token)])
async def get_order_status(token_id: str):
    order = next((order for order in ORDERS if order.token_id == token_id), None)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order with token_id '{token_id}' not found")
    return order.dict()

@app.post("/orders/twap", dependencies=[Depends(get_auth_token)])
async def submit_twap_order(order_data: OrderBase, execution_time: int = 600, interval: int = 60):
    if order_data.exchange not in SUPPORTED_EXCHANGES:
        raise HTTPException(status_code=400, detail=f"Exchange '{order_data.exchange}' not supported")
    if order_data.symbol not in TRADING_PAIRS[order_data.exchange]:
        raise HTTPException(status_code=400, detail=f"Symbol '{order_data.symbol}' not supported")
    
    order = Order(**order_data.dict())
    ORDERS.append(order)
    
    asyncio.create_task(execute_twap_order(order, execution_time, interval))
    
    return {"message": "TWAP order accepted", "order_id": order.token_id, "order_details": order.dict()}

### **TWAP EXECUTION ENGINE** ###

async def execute_twap_order(order: Order, execution_time: int, interval: int):
    number_of_steps = execution_time // interval
    quantity_per_step = order.quantity / number_of_steps

    for step in range(number_of_steps):
        await asyncio.sleep(interval)

        market_price = ORDER_BOOKS[order.symbol]["ask_price"] if order.order_type == "buy" else ORDER_BOOKS[order.symbol]["bid_price"]

        if (order.order_type == "buy" and market_price <= order.price) or (order.order_type == "sell" and market_price >= order.price):
            order.executed_quantity += quantity_per_step
            order.executions.append({"step": step + 1, "price": market_price, "quantity": quantity_per_step})
            await send_order_book_update()

    order.status = "completed" if order.executed_quantity >= order.quantity else "partial"

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

### **MARKET DATA COLLECTION FROM BINANCE** ###

async def fetch_market_data():
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

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(fetch_market_data())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
