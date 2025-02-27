from client.trading_client import TradingClient, start_websocket_listener
import threading
import time
import uvicorn
import asyncio


"""
This example to run the server et submit a TWAP without using the GUI.
You need to define the exchange and the pair / symbol (please make sure the pair is at the Websocket format)
"""
def run_server():
    """
    Run the FastAPI server using uvicorn.
    """
    uvicorn.run("server.server:app", host="0.0.0.0", port=8000, reload=False)

# Launch the FastAPI server in a separate thread
server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()

# Wait for the server to start
time.sleep(2)

exchange = "kraken"

# Initialize the TradingClient
client = TradingClient(exchange = exchange, base_url="http://localhost:8000")

# Fetch and print supported exchanges
exchanges = client.fetch_exchanges()
print("Supported Exchanges:", exchanges)

# Select an exchange (Binance/Kraken)

trading_pairs = client.fetch_trading_pairs()
print(f"Trading Pairs for {exchange}:", trading_pairs)

# Define the symbol for trading. 
symbol = "1INCH/EUR"

# Start the WebSocket listener in a separate thread with stop_event for cleanup
stop_event = threading.Event()
websocket_thread = threading.Thread(target=start_websocket_listener, args=(client, symbol, stop_event), daemon=True)
websocket_thread.start()

# Wait for a few seconds to ensure prices are received
time.sleep(5)

# Submit a TWAP order using the updated function signature
client.submit_twap_order(symbol=symbol, quantity=5, execution_time=300, interval=60, order_type = "sell")

# Monitor the order status in real-time
print("\nMonitoring the TWAP order status...")
for _ in range(10):
    # For Kraken, symbol is in a particular format (cur1/cur2), while twap_id is "twap_cur1_cur2"
    order_status = client.get_order_status(f"twap_{symbol.lower().replace("/", "_")}")
    print("Order Status:", order_status)
    time.sleep(6)

print("\nTWAP Order monitoring completed! Exiting the program.")

# Ensure proper WebSocket shutdown
stop_event.set()
websocket_thread.join()
