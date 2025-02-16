import requests

def fetch_exchanges():
    response = requests.get("http://localhost:8000/exchanges")
    return response.json()

def fetch_trading_pairs(exchange: str):
    response = requests.get(f"http://localhost:8000/exchanges/{exchange}/pairs")
    return response.json()

def fetch_klines(exchange: str, symbol: str, interval: str = "1m", limit: int = 100):
    response = requests.get(f"http://localhost:8000/klines/{exchange}/{symbol}", params={"interval": interval, "limit": limit})
    return response.json()

def main():
    # On essaye de récupérer les différentes plateformes dispo
    exchanges = fetch_exchanges()
    print("Supported Exchanges:", exchanges)

    # On récupère une paire de trading
    exchange = "binance"
    trading_pairs = fetch_trading_pairs(exchange)
    print(f"Trading Pairs for {exchange}:", trading_pairs)

    # Fetch historical candlestick data for a specific symbol
    symbol = "BTCUSDT"
    interval = "1m"
    limit = 10
    klines = fetch_klines(exchange, symbol, interval, limit)
    print(f"Klines for {symbol} on {exchange}:", klines)

# Run the main function
if __name__ == "__main__":
    main()
