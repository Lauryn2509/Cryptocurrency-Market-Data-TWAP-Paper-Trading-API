import requests
import time

class TradingClient:
    def __init__(self, base_url="http://localhost:8000", auth_token="crytobrodu59"):
        self.base_url = base_url
        self.headers = {"x-token": auth_token}

    def fetch_exchanges(self):
        response = requests.get(f"{self.base_url}/exchanges")
        return response.json()

    def fetch_trading_pairs(self, exchange: str):
        response = requests.get(f"{self.base_url}/exchanges/{exchange}/pairs")
        return response.json()

    def fetch_klines(self, exchange: str, symbol: str, interval: str = "1m", limit: int = 100):
        response = requests.get(
            f"{self.base_url}/klines/{exchange}/{symbol}",
            params={"interval": interval, "limit": limit}
        )
        return response.json()

    def submit_twap_order(self, order_data: dict, execution_time: int = 600, interval: int = 60):
        response = requests.post(
            f"{self.base_url}/orders/twap",
            json=order_data,
            headers=self.headers,
            params={"execution_time": execution_time, "interval": interval}
        )
        if response.status_code != 200:
            print(f"Error {response.status_code}: {response.json()}")
        return response.json()

    def get_order_status(self, token_id: str):
        response = requests.get(
            f"{self.base_url}/orders/{token_id}",
            headers=self.headers
        )
        if response.status_code != 200:
            print(f"Error {response.status_code}: {response.json()}")
        return response.json()

def main():
    client = TradingClient()

    # Fetch basic market data
    exchanges = client.fetch_exchanges()
    print("Supported Exchanges:", exchanges)

    exchange = "binance"
    trading_pairs = client.fetch_trading_pairs(exchange)
    print(f"Trading Pairs for {exchange}:", trading_pairs)

    symbol = "BTCUSDT"
    klines = client.fetch_klines(exchange, symbol, interval="1m", limit=10)
    print(f"Klines for {symbol} on {exchange}:", klines)

    # Submit TWAP order
    order_data = {
        "token_id": "order1",
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "quantity": 10,
        "price": 51000, 
        "order_type": "buy"
    }

    print("Submitting TWAP order...")
    response = client.submit_twap_order(order_data, execution_time=300, interval=60)
    print("Server response:", response)

    # Monitor order status
    print("\nMonitoring order status...")
    for _ in range(6):  # Monitor for 30 seconds
        order_status = client.get_order_status("order1")
        print("Order status:", order_status)
        time.sleep(6)

if __name__ == "__main__":
    main()
