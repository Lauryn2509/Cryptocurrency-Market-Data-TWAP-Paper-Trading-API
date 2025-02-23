import requests
import time
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
        self.access_token = self._get_access_token()  # Fetch access token on initialization
        self.headers = {"Authorization": f"Bearer {self.access_token}"}  # Use Bearer token for authentication
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

    def submit_twap_order(self, symbol="BTCUSDT", quantity=10, execution_time=600, interval=60):
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
            "order_type": "buy"
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

async def listen_to_order_book(client, symbol="BTCUSDT"):
    """Connect to the server's WebSocket and listen for order book updates."""
    uri = "ws://localhost:8000/ws"

    while True:
        try:
            async with websockets.connect(uri) as websocket:
                print(f" Connected to the WebSocket server! Waiting for {symbol} updates...")

                while True:
                    message = await websocket.recv()
                    data = json.loads(message)

                    if symbol in data["order_book"]:
                        bid = data["order_book"][symbol]["bid_price"]
                        ask = data["order_book"][symbol]["ask_price"]

                        if symbol not in client.last_printed_prices or \
                           client.last_printed_prices[symbol]["bid_price"] != bid or \
                           client.last_printed_prices[symbol]["ask_price"] != ask:

                            client.latest_prices[symbol] = {"bid_price": bid, "ask_price": ask}
                            client.last_printed_prices[symbol] = {"bid_price": bid, "ask_price": ask}

                            print(f" {symbol} - Bid: {bid} | Ask: {ask}")

        except websockets.exceptions.ConnectionClosed:
            print("WebSocket disconnected. Attempting to reconnect...")
            await asyncio.sleep(5)

def start_websocket_listener(client, symbol="BTCUSDT"):
    """Start the WebSocket in a separate thread to avoid blocking the main program."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(listen_to_order_book(client, symbol))

def main():
    print("\n Select an exchange:")
    print("1 Binance")
    print("2 Kraken")

    while True:
        choice = input("\n Enter 1 or 2: ").strip()
        if choice == "1":
            exchange = "binance"
            break
        elif choice == "2":
            exchange = "kraken"
            break
        else:
            print("Invalid choice. Please enter 1 or 2.")

    print(f"\n You have selected {exchange.upper()}!")

    client = TradingClient(exchange=exchange)

    # Retrieve initial market data
    exchanges = client.fetch_exchanges()
    print("\n Supported Exchanges:", exchanges)

    trading_pairs = client.fetch_trading_pairs()
    print(f" Trading Pairs for {exchange}:", trading_pairs)

    # User selects a trading pair
    print("\n Select a trading pair:")
    for idx, pair in enumerate(trading_pairs["pairs"], start=1):
        print(f"{idx}. {pair}")

    while True:
        try:
            pair_choice = int(input("\n Enter the number of the desired pair: ").strip())
            if 1 <= pair_choice <= len(trading_pairs["pairs"]):
                symbol = trading_pairs["pairs"][pair_choice - 1]
                break
            else:
                print("Invalid choice. Please enter a valid number.")
        except ValueError:
            print("Invalid input. Please enter a number.")

    print(f"\n You have selected to trade {symbol} on {exchange.upper()}!")

    # Start listening to real-time market prices in a separate thread
    websocket_thread = threading.Thread(target=start_websocket_listener, args=(client, symbol), daemon=True)
    websocket_thread.start()

    time.sleep(5)  # Wait a few seconds for prices to update

    # Submit a TWAP order with live price
    client.submit_twap_order(symbol=symbol, quantity=5, execution_time=300, interval=60)

    # Real-time order tracking
    print("\n Real-time order tracking...")
    for _ in range(10):  # Check for 1 minute
        order_status = client.get_order_status(f"twap_{symbol.lower()}")
        print(" Order Status:", order_status)
        time.sleep(6)

if __name__ == "__main__":
    main()
