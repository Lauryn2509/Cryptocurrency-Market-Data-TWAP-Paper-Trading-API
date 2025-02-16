from fastapi import FastAPI, HTTPException, Query
from typing import List, Optional
import asyncio
import websockets
import json

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

    # Fetch historical data (mock data in this example)
    data = HISTORICAL_DATA[exchange].get(symbol, [])
    return {"klines": data[:limit]}

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
    uvicorn.run("server_corrected:app", host="0.0.0.0", port=8000, reload=True)
    # Run the WebSocket data collection
    asyncio.run(main())
