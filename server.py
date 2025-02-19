"""
Libraries import
Rq : commentaires en anglais = fixe normalement
en fr = à changer à l'avenir
"""
from fastapi import FastAPI, HTTPException, Query, Depends, Header
from typing import List, Optional
import asyncio
import json
from pydantic import BaseModel, validator, ValidationError
import random 

# Initialisation
app = FastAPI()

# Supported exchanges and trading pairs
# On devra peut-être en ajouter ? 
SUPPORTED_EXCHANGES = ["binance", "kraken"]  

TRADING_PAIRS = {
    "binance": ["BTCUSDT", "ETHUSDT"],
    "kraken": ["XXBTZUSD", "XETHZUSD"]
}

"""
Simulation d'un historique pour chaque paire de trading et simulation d'un carnet d'ordre
Cela sera à changer quand on utilisera les API Websocket de Binance / Kraken
"""
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

ORDERS = []  # List containing the orders to be passed
SIMULATED_ORDER_BOOK = {
    "BTCUSDT": {
        "ask_price": round(50000 + random.uniform(-50, 50), 2),  # Prix de vente
        "bid_price": round(49900 + random.uniform(-50, 50), 2)   # Prix d'achat
    },
    "ETHUSDT": {
        "ask_price": round(3500 + random.uniform(-10, 10), 2),   # Prix de vente
        "bid_price": round(3490 + random.uniform(-10, 10), 2)    # Prix d'achat
    }
}

"""
Authentification (probablement à modif à l'avenir ?)
"""
AUTH_TOKEN = "crytobrodu59"

def get_auth_token(x_token: str = Header(...)):
    if x_token != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return x_token

class OrderBase(BaseModel):
    """
    Base model for an acceptable order. 
    It herits from BaseModel from the Pydantic library so it can validate the inputs
    thanks to the Python type hinting
    """
    token_id: str       # Name / Reference of the order
    exchange: str       # Name of the exchange where the order should be executed
    symbol: str         # Symbol of the pair to be traded 
    quantity: float     # Quantity to buy or sell
    price: float        # Price at which the order should be executed
    order_type: str 

    @validator('order_type')
    # Moyen de s'assurer que le type d'ordre est correct
    def validate_order_type(cls, v):
        if v not in ["buy", "sell"]:
            raise ValueError("Order type must be either 'buy' or 'sell'!")
        return v
class Order(OrderBase):
    """
    Herits from OrderBase and extend it so that the dynamic attributes are clearly distinct from
    what is initially passed
    """
    status: str = "open"                # Status of the order (open, executed,...)
    executed_quantity: float = 0.0      # Quantity of the order that has been executed
    executions: list = []               # List that save the details of each partial execution of the order 

"""
API endpoints
"""
# Si on veut tester : 
# lancer uvicorn server:app --reload dans le terminal
# puis sur edge : écrire la requête HTTP

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
    Returns list of all supported exchanges
    """
    return {"exchanges": SUPPORTED_EXCHANGES}

@app.get("/exchanges/{exchange}/pairs")
async def get_trading_pairs(exchange: str):
    """
    Returns available trading pairs for a specific exchange
    """
    if exchange not in SUPPORTED_EXCHANGES:
        raise HTTPException(status_code=404, detail=f"Exchange '{exchange}' not found")
    return {"pairs": TRADING_PAIRS[exchange]}

@app.get("/klines/{exchange}/{symbol}")
async def get_klines(
    exchange: str, 
    symbol: str, 
    interval: str = Query(..., pattern="^[1-9][0-9]*[mhd]$"), 
    limit: Optional[int] = 100
):
    """
    Returns historical candlestick data for a specific exchange and symbol
    """
    # Pour l'instant c'est fixé dans historical data
    if exchange not in SUPPORTED_EXCHANGES:
        raise HTTPException(status_code=404, detail=f"Exchange '{exchange}' not found")
    if symbol not in TRADING_PAIRS[exchange]:
        raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found")
    return {"klines": HISTORICAL_DATA[exchange].get(symbol, [])[:limit]}


# PARTIE AUTHENTIFICATION : là il faut une sorte de mdp pour pouvoir accéder aux données
@app.get("/orders", dependencies=[Depends(get_auth_token)])
async def list_orders(token_id: Optional[str] = None):
    """
    Returns the list of orders
    """
    filtered_orders = [order for order in ORDERS if not token_id or order.token_id == token_id]
    return {"orders": filtered_orders}

@app.get("/orders/{token_id}", dependencies=[Depends(get_auth_token)])
async def get_order_status(token_id: str):
    """
    Returns the status of a given order
    """
    order = next((order for order in ORDERS if order.token_id == token_id), None)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order with token_id '{token_id}' not found")
    return {
        "order_id": order.token_id,
        "symbol": order.symbol,
        "status": order.status,
        "executed_quantity": order.executed_quantity,
        "executions": order.executions
    }

@app.post("/orders/twap", dependencies=[Depends(get_auth_token)])
async def submit_twap_order(order_data: OrderBase, execution_time: int = 600, interval: int = 60):
    """
    Accepts (or refuse) a new order and add it to the list of orders
    We convert the order (passed as a dictionnary) to a useable class by the server
    """
    if order_data.exchange not in SUPPORTED_EXCHANGES:
        raise HTTPException(status_code=400, detail=f"Exchange '{order_data.exchange}' not supported")
    if order_data.symbol not in TRADING_PAIRS[order_data.exchange]:
        raise HTTPException(status_code=400, detail=f"Symbol '{order_data.symbol}' not supported")
    
    # On va "unpack" le dictionnaire (chaque paire clé-valeur devient un attribut de la classe)
    # Forcément, au départ, l'ordre est ouvert avec 0 qté exécutée
    order = Order(**order_data.dict())
    ORDERS.append(order)
    
    # Creation of an asychrone task to execute a TWAP order in the background 
    task = asyncio.create_task(execute_twap_order(order, execution_time, interval))
    # We stock the task to avoid garbage collector problems
    app.state.tasks = getattr(app.state, 'tasks', [])
    app.state.tasks.append(task)
    
    return {
        "message": "TWAP order accepted",
        "order_id": order.token_id,
        "order_details": order.dict()
    }

async def execute_twap_order(order: Order, execution_time: int, interval: int):
    """
    Executes the TWAP order by breaking it down into smaller steps executed at
    regular intervals (TWAP definition).
    """
    # Number of steps required to execute the order over the specified time 
    number_of_steps = execution_time // interval 
    # Quantity of the asset to be traded at each step 
    quantity_per_step = order.quantity / number_of_steps
    
    print(f"[TWAP] Starting execution for {order.token_id}: {order.quantity} units over {number_of_steps} steps")
    
    # Execution loop
    # Pour l'instant sur données simulées, après avec Websocket
    for step in range(number_of_steps):
        # Pausing the execution for the specified interval to allow other tasks to run 
        # (simulates the passage of time between each step of the order execution)
        await asyncio.sleep(interval)
        
        # Simulation du prix de marché pour l'instant 
        if order.order_type == "buy":
            market_price = SIMULATED_ORDER_BOOK[order.symbol]["ask_price"]
        elif order.order_type == "sell":
            market_price = SIMULATED_ORDER_BOOK[order.symbol]["bid_price"]

        market_price = round(market_price * (1 + random.uniform(-0.01, 0.01)), 2)

        # Execution of the limit order
        if (order.order_type == "buy" and market_price <= order.price) or \
           (order.order_type == "sell" and market_price >= order.price):
            order.executed_quantity += quantity_per_step
            order.executions.append({
                "step": step + 1,
                "price": market_price,
                "quantity": quantity_per_step
            })
            print(f"Étape {step + 1}: Exécuté {quantity_per_step} {order.symbol} à {market_price}")
        else:
            print(f"Étape {step + 1}: Pas d'exécution - prix du marché ({market_price}) non favorable pour {order.order_type}")

    order.status = "completed" if order.executed_quantity >= order.quantity else "partial"
    print(f"Ordre TWAP {order.token_id} terminé: {order.executed_quantity}/{order.quantity} unités exécutées")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
