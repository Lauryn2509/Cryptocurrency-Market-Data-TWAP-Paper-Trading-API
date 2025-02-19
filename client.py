import requests
import time
import asyncio
import websockets
import json
import threading

class TradingClient:
    def __init__(self, base_url="http://localhost:8000", auth_token="TaniaEstKo"):
        self.base_url = base_url
        self.headers = {"x-token": auth_token}
        self.latest_prices = {}  # Stocke les derniers prix reçus
        self.last_printed_prices = {}  # Stocke les derniers prix affichés

    def fetch_exchanges(self):
        response = requests.get(f"{self.base_url}/exchanges")
        return response.json()

    def fetch_trading_pairs(self, exchange: str):
        response = requests.get(f"{self.base_url}/exchanges/{exchange}/pairs")
        return response.json()

    def submit_twap_order(self, symbol="BTCUSDT", quantity=10, execution_time=600, interval=60):
        """
        Envoie un ordre TWAP en utilisant le dernier prix du marché en temps réel.
        """
        if symbol not in self.latest_prices:
            print("Aucune donnée de marché disponible, impossible d'envoyer l'ordre.")
            return

        order_data = {
            "token_id": f"twap_{symbol.lower()}",
            "exchange": "binance",
            "symbol": symbol,
            "quantity": quantity,
            "price": self.latest_prices[symbol]["ask_price"],  # Utilise le dernier prix ask
            "order_type": "buy"
        }

        response = requests.post(
            f"{self.base_url}/orders/twap",
            json=order_data,
            headers=self.headers,
            params={"execution_time": execution_time, "interval": interval}
        )

        print("\n Envoi de l'ordre TWAP...")
        print(" Réponse du serveur :", response.json())

    def get_order_status(self, token_id: str):
        response = requests.get(
            f"{self.base_url}/orders/{token_id}",
            headers=self.headers
        )
        return response.json()

async def listen_to_order_book(client, symbol="BTCUSDT"):
    """
    Se connecte au WebSocket du serveur et écoute les mises à jour du carnet d'ordres.
    """
    uri = "ws://localhost:8000/ws"

    while True:
        try:
            async with websockets.connect(uri) as websocket:
                print(f"Connecté au WebSocket du serveur ! En attente des mises à jour de {symbol}...")

                while True:
                    message = await websocket.recv()
                    data = json.loads(message)

                    if symbol in data["order_book"]:
                        bid = data["order_book"][symbol]["bid_price"]
                        ask = data["order_book"][symbol]["ask_price"]

                        # Vérifier si les prix ont changé avant d'afficher
                        if symbol not in client.last_printed_prices or \
                           client.last_printed_prices[symbol]["bid_price"] != bid or \
                           client.last_printed_prices[symbol]["ask_price"] != ask:

                            client.latest_prices[symbol] = {"bid_price": bid, "ask_price": ask}
                            client.last_printed_prices[symbol] = {"bid_price": bid, "ask_price": ask}

                            print(f" {symbol} - Bid: {bid} | Ask: {ask}")

        except websockets.exceptions.ConnectionClosed:
            print(" WebSocket déconnecté. Tentative de reconnexion...")
            await asyncio.sleep(5)  # Attendre avant de réessayer

def start_websocket_listener(client, symbol="BTCUSDT"):
    """
    Démarre le WebSocket dans un thread séparé pour éviter de bloquer le programme principal.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(listen_to_order_book(client, symbol))

def main():
    client = TradingClient()

    # Récupérer les données de marché initiales
    exchanges = client.fetch_exchanges()
    print("Supported Exchanges:", exchanges)

    exchange = "binance"
    trading_pairs = client.fetch_trading_pairs(exchange)
    print(f"Trading Pairs for {exchange}:", trading_pairs)

    symbol = "BTCUSDT"

    # Lancer l'écoute des prix du marché en temps réel dans un thread séparé
    websocket_thread = threading.Thread(target=start_websocket_listener, args=(client, symbol), daemon=True)
    websocket_thread.start()

    time.sleep(5)  # Attendre quelques secondes que les prix soient mis à jour

    # Soumettre un ordre TWAP avec le prix en direct
    client.submit_twap_order(symbol=symbol, quantity=5, execution_time=300, interval=60)

    # Suivi de l'ordre en temps réel
    print("\n Suivi de l'ordre en temps réel...")
    for _ in range(10):  # Vérifier pendant 1 minute
        order_status = client.get_order_status(f"twap_{symbol.lower()}")
        print(" Order Status:", order_status)
        time.sleep(6)

if __name__ == "__main__":
    main()
