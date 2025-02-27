import requests
import asyncio
import websockets
import json
import threading

class TradingClient:
    """
    Client for interacting with the TWAP Paper Trading API. This class provides methods to connect to the trading server,
    fetch market data, and submit trading orders.
    
    Attributes :
        exchange (str): The exchange to use (binance or kraken), given by the user. Default is Kraken.
        base_url (str): The URL of the TWAP trading server, given by the user. Default is user localhost
        username (str): Username for authentication. For our purposes, it should not be changed. 
                        In production, it should correspond to the user.
        password (str): Password for authentication. Same as the username.
        access_token (str): JWT token for API authorization
        headers (dict): HTTP headers with authorization token
        latest_prices (dict): Cache of current market prices
        last_printed_prices (dict): Previously displayed prices
        _websocket_pairs_cache (dict): Cache of trading pairs by exchange
    """
    def __init__(self, exchange="binance", base_url="http://localhost:8000", username="premium", password="CryptoTWAPpremium"):
        self.exchange = exchange.lower()
        self.base_url = base_url
        self.username = username
        self.password = password
        self.access_token = self._get_access_token()
        self.headers = {"Authorization": f"Bearer {self.access_token}"}
        self.latest_prices = {}
        self.last_printed_prices = {}
        self._websocket_pairs_cache = {}

    def _get_access_token(self):
        """
        Authenticate with the server and obtain a JWT access token. 
        Makes a POST request to the /token endpoint with username and password.
        It returns the JWT access token for API authorization, and raises a failed authentication error if it happens.
        """
        response = requests.post(
            f"{self.base_url}/token",
            data={"username": self.username, "password": self.password}
        )
        if response.status_code == 200:
            return response.json()["access_token"]
        else:
            raise Exception("Failed to authenticate. Check username and password.")

    def fetch_exchanges(self):
        """
        Retrieve the list of supported exchanges from the server
        """
        response = requests.get(f"{self.base_url}/exchanges", headers=self.headers)
        return response.json()

    def fetch_trading_pairs(self):
        """
        Fetch trading pairs for the selected exchange.
        For Kraken, we fetch pairs in WebSocket format directly from Kraken API.
        For others, we use the server API.
        """
        if self.exchange == "kraken":
            # Check if we have cached results
            if "kraken" in self._websocket_pairs_cache:
                return {"exchange": "kraken", "pairs": self._websocket_pairs_cache["kraken"]}
            
            # Fetch from Kraken API
            ws_pairs = self._fetch_kraken_websocket_pairs()
            if ws_pairs:
                self._websocket_pairs_cache["kraken"] = ws_pairs
                return {"exchange": "kraken", "pairs": ws_pairs}
            else:
                # Fallback to server if direct fetch fails
                print("Warning: Failed to fetch Kraken WebSocket pairs. Falling back to server API.")
        
        # For all other exchanges or as fallback
        response = requests.get(f"{self.base_url}/exchanges/{self.exchange}/pairs", headers=self.headers)
        return response.json()

    def _fetch_kraken_websocket_pairs(self):
        """
        Fetch Kraken pairs directly from Kraken API in WebSocket format
        """
        try:
            # Make request to Kraken API for asset pairs
            response = requests.get("https://api.kraken.com/0/public/AssetPairs")
            if response.status_code != 200:
                print(f"Failed to fetch Kraken pairs: Status code {response.status_code}")
                return []
            
            data = response.json()
            if data.get("error"):
                print(f"Kraken API error: {data['error']}")
                return []
            
            # Extract WebSocket formatted pairs
            ws_pairs = []
            for pair_info in data["result"].values():
                if "wsname" in pair_info:
                    ws_pairs.append(pair_info["wsname"])
            
            # Use altname as fallback if wsname is not available
            for pair_key, pair_info in data["result"].items():
                if "wsname" not in pair_info and "altname" in pair_info:
                    # Format altname to match WebSocket format if needed
                    altname = pair_info["altname"]
                    if "/" not in altname and len(altname) >= 6:
                        # Try to split into base/quote (simple approach)
                        mid = len(altname) // 2
                        formatted_altname = f"{altname[:mid]}/{altname[mid:]}"
                        ws_pairs.append(formatted_altname)
            
            print(f"Fetched {len(ws_pairs)} Kraken WebSocket pairs")
            return ws_pairs
        
        except Exception as e:
            print(f"Error fetching Kraken WebSocket pairs: {e}")
            return []

    def submit_twap_order(self, symbol="XBT/USD", quantity=10, execution_time=600, interval=60, order_type:str = "buy"):
        """
        Submit a TWAP order using the latest real-time market price.
        """
        if symbol not in self.latest_prices:
            print(f"No market data available for {symbol}, unable to send the order.")
            return

        # We create token_id based on the symbol (replace / by _ for Kraken pairs)
        token_id = f"twap_{symbol.lower().replace('/', '_')}"
    
        order_data = {
            "token_id": token_id,
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
        return response.json()

    def get_order_status(self, token_id: str):
        """
        Fetch the status of a given order by its token_id.
        """
        response = requests.get(
            f"{self.base_url}/orders/{token_id}",
            headers=self.headers
        )
        return response.json()

async def listen_to_order_book(client, symbol="XBT/USD", stop_event=None):
    """
    Connect to the server's WebSocket and listen for order book updates.
    """
    uri = "ws://localhost:8000/ws"

    try:
        async with websockets.connect(uri) as websocket:
            print(f" Connected to WebSocket. Listening for {symbol} updates...")
            
            while not stop_event.is_set():
                message = await websocket.recv()
                data = json.loads(message)

                if symbol in data["order_book"]:
                    bid = data["order_book"][symbol]["bid_price"]
                    ask = data["order_book"][symbol]["ask_price"]

                    client.latest_prices[symbol] = {"bid_price": bid, "ask_price": ask}
                    
                    # Only display prices if they have changed
                    if symbol not in client.last_printed_prices or \
                       client.last_printed_prices[symbol]["bid_price"] != bid or \
                       client.last_printed_prices[symbol]["ask_price"] != ask:
                        print(f" {symbol} - Bid: {bid} | Ask: {ask}")
                        client.last_printed_prices[symbol] = {"bid_price": bid, "ask_price": ask}

    except websockets.exceptions.ConnectionClosed:
        print("WebSocket disconnected.")

def start_websocket_listener(client, symbol="BTCUSDT", stop_event=None):
    """
    Start WebSocket in a separate thread and allow stopping.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(listen_to_order_book(client, symbol, stop_event))
