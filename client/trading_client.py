import requests
import asyncio
import websockets
import json
import threading

class TradingClient:
    def __init__(self, exchange="binance", base_url="http://localhost:8000", username="premium", password="CryptoTWAPpremium"):
        self.exchange = exchange.lower()
        self.base_url = base_url
        self.username = username
        self.password = password
        self.access_token = self._get_access_token()
        self.headers = {"Authorization": f"Bearer {self.access_token}"}
        self.latest_prices = {}
        self.last_printed_prices = {}

    def _get_access_token(self):
        """Fetch access token using username and password."""
        response = requests.post(
            f"{self.base_url}/token",
            data={"username": self.username, "password": self.password}
        )
        if response.status_code == 200:
            return response.json()["access_token"]
        else:
            raise Exception("Failed to authenticate. Check username and password.")

    def fetch_exchanges(self):
        response = requests.get(f"{self.base_url}/exchanges", headers=self.headers)
        return response.json()

    def fetch_trading_pairs(self):
        response = requests.get(f"{self.base_url}/exchanges/{self.exchange}/pairs", headers=self.headers)
        return response.json()

    def submit_twap_order(self, symbol="BTCUSDT", quantity=10, execution_time=600, interval=60, order_type:str = "buy"):
        """Submit a TWAP order using the latest real-time market price."""
        if symbol not in self.latest_prices:
            print("No market data available, unable to send the order.")
            return

        order_data = {
            "token_id": f"twap_{symbol.lower()}",
            "exchange": self.exchange,
            "symbol": symbol,
            "quantity": quantity,
            "price": self.latest_prices[symbol]["ask_price"],
            "order_type": order_type
        }

        response = requests.post(
            f"{self.base_url}/orders/twap",
            json=order_data,
            headers=self.headers,
            params={"execution_time": execution_time, "interval": interval}
        )

        print("\n Sending TWAP order...")
        print(" Server response:", response.json())

    def get_order_status(self, token_id: str):
        """Fetch the status of a given order by its token_id."""
        response = requests.get(
            f"{self.base_url}/orders/{token_id}",
            headers=self.headers
        )
        return response.json()

async def listen_to_order_book(client, symbol="BTCUSDT", stop_event=None):
    """Connect to the server's WebSocket and listen for order book updates."""
    uri = "ws://localhost:8000/ws"

    try:
        async with websockets.connect(uri) as websocket:
            while not stop_event.is_set():
                message = await websocket.recv()
                data = json.loads(message)

                if symbol in data["order_book"]:
                    bid = data["order_book"][symbol]["bid_price"]
                    ask = data["order_book"][symbol]["ask_price"]

                    client.latest_prices[symbol] = {"bid_price": bid, "ask_price": ask}
                    print(f" {symbol} - Bid: {bid} | Ask: {ask}")

    except websockets.exceptions.ConnectionClosed:
        print("WebSocket disconnected.")

def start_websocket_listener(client, symbol="BTCUSDT", stop_event=None):
    """Start WebSocket in a separate thread and allow stopping."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(listen_to_order_book(client, symbol, stop_event))
