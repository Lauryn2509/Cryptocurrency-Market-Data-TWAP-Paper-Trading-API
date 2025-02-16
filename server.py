from fastapi import FastAPI, HTTPException, Query, Depends, Header
from typing import List, Optional
import asyncio
import websockets
import json
from pydantic import BaseModel

app = FastAPI()

# Mock data for supported exchanges and trading pairs
SUPPORTED_EXCHANGES = ["binance", "kraken"]
TRADING_PAIRS = {
    "binance": ["BTCUSDT", "ETHUSDT"],
    "kraken": ["XXBTZUSD", "XETHZUSD"]
}

# Mock data for historical candlestick data
HISTORICAL_DATA = {
    "binance": {
        "BTCUSDT": [
            {"open": 50000, "high": 51000, "low": 49000, "close": 50500, "volume": 100},
            {"open": 50500, "high": 51500, "low": 50000, "close": 51000, "volume": 150}
        ]
    },
    "kraken": {
        "XXBTZUSD": [
            {"open": 50000, "high": 51000, "low": 49000, "close": 50500, "volume": 100},
            {"open": 50500, "high": 51500, "low": 50000, "close": 51000, "volume": 150}
        ]
    }
}

# Mock data for orders
ORDERS = []

# Authentication token = c'est notre mot de passe
AUTH_TOKEN = "crytobrodu59"

# méthode qui permet de vérifier si on a le bon mdp, cf la partie AUTHENTIFICATION
def get_auth_token(x_token: str = Header(...)):
    if x_token != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return x_token

class Order(BaseModel):
    token_id: str
    exchange: str
    symbol: str
    quantity: float
    price: float
    status: str = "open"

# PARTIE PUBLIQUE : pas besoin d'authentification pour faire ces requêtes
@app.get("/")
async def root():
    """
    Root endpoint returning a welcome message.
    This helps clients verify the API is working.
    """
    return {"message": "Welcome to the M2 272 Crypto API"}

@app.get("/exchanges")
async def get_exchanges():
    """
    Returns list of all supported exchanges.
    """
    return {"exchanges": SUPPORTED_EXCHANGES}

@app.get("/exchanges/{exchange}/pairs")
async def get_trading_pairs(exchange: str):
    """
    Returns available trading pairs for a specific exchange.
    """
    if exchange not in SUPPORTED_EXCHANGES:
        raise HTTPException(status_code=404, detail=f"Exchange '{exchange}' not found")
    return {"pairs": TRADING_PAIRS[exchange]}

@app.get("/klines/{exchange}/{symbol}")
async def get_klines(exchange: str, symbol: str, interval: str = Query(..., regex="^[1-9][0-9]*[mhd]$"), limit: Optional[int] = 100):
    """
    Returns historical candlestick data for a specific exchange and symbol.
    """
    if exchange not in SUPPORTED_EXCHANGES:
        raise HTTPException(status_code=404, detail=f"Exchange '{exchange}' not found")
    if symbol not in TRADING_PAIRS[exchange]:
        raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found for exchange '{exchange}'")

    # Fetch historical data 
    data = HISTORICAL_DATA[exchange].get(symbol, [])
    return {"klines": data[:limit]}

# PARTIE AUTHENTIFICATION : là il faut une sorte de mdp pour pouvoir accéder aux données
@app.post("/orders/twap", dependencies=[Depends(get_auth_token)])
async def submit_twap_order(order: Order):
    """
    Méthode POST : donc on va "poster"/ajouter de la data
    Ici on rajoute un ordre TWAP (?)
    Un peu comme une sorte de book, on ajoute les ordres
    """
    if order.exchange not in SUPPORTED_EXCHANGES:
        raise HTTPException(status_code=400, detail=f"Exchange '{order.exchange}' not supported")
    if order.symbol not in TRADING_PAIRS[order.exchange]:
        raise HTTPException(status_code=400, detail=f"Symbol '{order.symbol}' not supported for exchange '{order.exchange}'")

    ORDERS.append(order)
    return {"message": "Order accepted", "order_id": order.token_id}

@app.get("/orders", dependencies=[Depends(get_auth_token)])
async def list_orders(token_id: Optional[str] = None):
    """
    Retourne la liste des ordres (open, closed, or both).
    Possibe de filtrer pgrâce à token_id si on veut voir que les ordres d'un token
    """
    if token_id:
        orders = [order for order in ORDERS if order.token_id == token_id]
    else:
        orders = ORDERS
    return {"orders": orders}

@app.get("/orders/{token_id}", dependencies=[Depends(get_auth_token)])
async def get_order_status(token_id: str):
    """
    On veut les infos d'un token en particulier 
    """
    for order in ORDERS:
        if order.token_id == token_id:
            return {"order": order}
    raise HTTPException(status_code=404, detail=f"Order with token_id '{token_id}' not found")

async def collect_order_book_data(exchange: str, symbol: str):
    """
    Fonction qui prend en arguments
    - exchange : la plateforme de crypto à laquelle on souhaite être connectés
    - symbols : les tickers des cryptos qu'on veut collecter

    Ici à remplacer URI etc par de vraies Websockets pour être réellement relié au web
    """
    # lien url - partie à modifier lorsque WEBSOCKETS
    uri = f"wss://{exchange}.com/ws/{symbol}"

    # On se connecte, puis tant qu'on est connecté, on récupère les données
    async with websockets.connect(uri) as websocket:
        while True:
            data = await websocket.recv()
            order_book = json.loads(data)
            print(f"Received order book data for {symbol} on {exchange}: {order_book}")

async def main():
    # Start WebSocket connections to collect order book data
    tasks = [
        collect_order_book_data("binance", "BTCUSDT"),
        collect_order_book_data("kraken", "XXBTZUSD")
    ]
    #les connexions WebSocket pour collecter les données de
    # "binance" et "kraken" seront établies et exécutées simultanément.
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    import uvicorn
    # Run the FastAPI app
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
    # Run the WebSocket data collection
    asyncio.run(main())
