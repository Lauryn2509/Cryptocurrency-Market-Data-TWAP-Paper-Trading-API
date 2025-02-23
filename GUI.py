import sys
import threading
import time
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton, QTextEdit
from client.trading_client import TradingClient, start_websocket_listener
import uvicorn

class TradingClientGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle('TWAP Trading Client')
        self.setGeometry(100, 100, 400, 400)

        # Layout
        layout = QVBoxLayout()

        # Exchange Selection
        self.exchange_label = QLabel('Select Exchange:')
        self.exchange_combo = QComboBox()
        self.exchange_combo.addItems(['binance', 'kraken'])
        layout.addWidget(self.exchange_label)
        layout.addWidget(self.exchange_combo)

        # Trading Pair Selection
        self.pair_label = QLabel('Select Trading Pair:')
        self.pair_combo = QComboBox()
        self.pair_combo.addItems(['BTCUSDT', 'ETHUSDT'])  # Default to Binance pairs
        layout.addWidget(self.pair_label)
        layout.addWidget(self.pair_combo)

        # Quantity Input
        self.quantity_label = QLabel('Quantity:')
        self.quantity_input = QLineEdit()
        layout.addWidget(self.quantity_label)
        layout.addWidget(self.quantity_input)

        # Execution Time Input
        self.exec_time_label = QLabel('Execution Time (seconds):')
        self.exec_time_input = QLineEdit()
        layout.addWidget(self.exec_time_label)
        layout.addWidget(self.exec_time_input)

        # Interval Input
        self.interval_label = QLabel('Interval (seconds):')
        self.interval_input = QLineEdit()
        layout.addWidget(self.interval_label)
        layout.addWidget(self.interval_input)

        # Order Type Selection
        self.order_type_label = QLabel('Order Type:')
        self.order_type_combo = QComboBox()
        self.order_type_combo.addItems(['buy', 'sell'])
        layout.addWidget(self.order_type_label)
        layout.addWidget(self.order_type_combo)

        # Submit Button
        self.submit_button = QPushButton('Submit TWAP Order')
        self.submit_button.clicked.connect(self.submit_order)
        layout.addWidget(self.submit_button)

        # Order Status Display
        self.status_label = QLabel('Order Status:')
        self.status_display = QTextEdit()
        self.status_display.setReadOnly(True)
        layout.addWidget(self.status_label)
        layout.addWidget(self.status_display)

        # Set layout
        self.setLayout(layout)

        # Initialize TradingClient
        self.client = TradingClient(base_url="http://localhost:8000")
        self.stop_event = threading.Event()

        # Update trading pairs based on exchange selection
        self.exchange_combo.currentTextChanged.connect(self.update_trading_pairs)

    def update_trading_pairs(self):
        """Update trading pairs based on selected exchange."""
        exchange = self.exchange_combo.currentText()
        if exchange == 'binance':
            self.pair_combo.clear()
            self.pair_combo.addItems(['BTCUSDT', 'ETHUSDT'])
        elif exchange == 'kraken':
            self.pair_combo.clear()
            self.pair_combo.addItems(['XBTUSD', 'ETHUSD'])

    def submit_order(self):
        """Submit a TWAP order based on user input."""
        exchange = self.exchange_combo.currentText()
        symbol = self.pair_combo.currentText()
        quantity = float(self.quantity_input.text())
        execution_time = int(self.exec_time_input.text())
        interval = int(self.interval_input.text())
        order_type = self.order_type_combo.currentText()
        self.client.exchange = exchange

        # Create a new stop event for each order
        self.stop_event = threading.Event()

        # Start WebSocket listener in a separate thread, passing the stop event
        self.websocket_thread = threading.Thread(
            target=start_websocket_listener,
            args=(self.client, symbol, self.stop_event),
            daemon=True
        )
        self.websocket_thread.start()

        # Wait for prices to be received
        time.sleep(5)

        # Submit the TWAP order
        self.client.submit_twap_order(
            symbol=symbol,
            quantity=quantity,
            execution_time=execution_time,
            interval=interval,
            order_type=order_type
        )

        # Monitor the order status
        self.monitor_order_status(symbol)


    def monitor_order_status(self, symbol):
        """Monitor the order status and display it in the GUI."""
        token_id = f"twap_{symbol.lower()}"
        for _ in range(10):  # Monitor for a maximum of 10 iterations
            order_status = self.client.get_order_status(token_id)
            self.status_display.append(f"Order Status: {order_status}")

            # Check if the order is completed or partially completed
            if order_status.get("status") in ["completed", "partial"]:
                self.status_display.append("Order execution completed. Closing WebSocket connection...")
                self.stop_event.set()  # Signal the WebSocket thread to stop
                self.websocket_thread.join()  # Wait for the WebSocket thread to finish
                break  # Exit the monitoring loop

            time.sleep(6)  # Wait before checking the status again
        else:
            self.status_display.append("TWAP Order monitoring completed!")
def run_server():
    """Run the FastAPI server using uvicorn."""
    uvicorn.run("server.server:app", host="0.0.0.0", port=8000, reload=False)

if __name__ == '__main__':
    # Launch the FastAPI server in a separate thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Wait for the server to start
    time.sleep(2)

    # Start the PyQt application
    app = QApplication(sys.argv)
    gui = TradingClientGUI()
    gui.show()
    sys.exit(app.exec_())