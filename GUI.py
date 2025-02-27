####################################################################################################################################################
# Librairies
####################################################################################################################################################
import sys
import threading
import time
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton, QTextEdit, QMessageBox
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, Qt
from client.trading_client import TradingClient, start_websocket_listener
import uvicorn
import requests

####################################################################################################################################################
# Fetching pairs to use them in the GUI
####################################################################################################################################################

class PairsFetcher(QObject):
    """
    Helper class to handle fetching pairs in a thread-safe way
    """
    pairs_fetched = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    
    def fetch_pairs(self, exchange, base_url):
        try:
            response = requests.get(f"{base_url}/exchanges/{exchange}/pairs")
            if response.status_code == 200:
                pairs = response.json().get("pairs", [])
                self.pairs_fetched.emit(pairs)
            else:
                self.error_occurred.emit(f"Failed to fetch pairs: Status code {response.status_code}")
        except Exception as e:
            self.error_occurred.emit(f"Error fetching pairs: {str(e)}")

####################################################################################################################################################
# GUI in itself
####################################################################################################################################################

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
        self.pair_combo.addItem("Loading pairs...")  # Default placeholder
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
        self.base_url = "http://localhost:8000"
        self.client = TradingClient(base_url=self.base_url)
        self.stop_event = threading.Event()
        
        # Initialize pairs fetcher 
        self.pairs_fetcher = PairsFetcher()
        self.pairs_fetcher.pairs_fetched.connect(self.update_pairs_combo)
        self.pairs_fetcher.error_occurred.connect(self.handle_fetch_error)

        # Update trading pairs based on exchange selection (see server)
        self.exchange_combo.currentTextChanged.connect(self.fetch_trading_pairs)
        
        # Fetch initial pairs for the default exchange
        self.fetch_trading_pairs(self.exchange_combo.currentText())

    def fetch_trading_pairs(self, exchange):
        """
        Fetch trading pairs for the selected exchange.
        Remind that Binance uses the same symbols for its API RestPoint and Websocket,
        whereas Kraken uses diffferent ones. The ones displayed in the GUI are the Websocket ones.
        """
        self.pair_combo.clear()
        self.pair_combo.addItem("Loading pairs...")
        self.pair_combo.setEnabled(False)
        
        # Create a thread to fetch pairs
        fetch_thread = threading.Thread(
            target=self.pairs_fetcher.fetch_pairs,
            args=(exchange, self.base_url),
            daemon=True
        )
        fetch_thread.start()
    
    @pyqtSlot(list)
    def update_pairs_combo(self, pairs):
        """
        Update the pairs combobox with fetched pairs.
        """
        self.pair_combo.clear()
        
        if pairs:
            # We sort pairs for better readability
            pairs.sort()
            self.pair_combo.addItems(pairs)
        else:
            self.pair_combo.addItem("No pairs available")
        
        self.pair_combo.setEnabled(True)
    
    @pyqtSlot(str)
    def handle_fetch_error(self, error_message):
        """
        Handle errors during pair fetching.
        """
        self.status_display.append(f"Error: {error_message}")
        QMessageBox.critical(self, "Error", error_message)
        
        # Reset the pairs combo
        self.pair_combo.clear()
        self.pair_combo.addItem("Failed to load pairs")
        self.pair_combo.setEnabled(True)

    def submit_order(self):
        """
        Submit a TWAP order based on user input.
        """
        exchange = self.exchange_combo.currentText()
        symbol = self.pair_combo.currentText()
    
        # Check if a valid pair is selected
        if symbol in ["Loading pairs...", "No pairs available", "Failed to load pairs"]:
            QMessageBox.warning(self, "Warning", "Please select a valid trading pair")
            return
        
        try:
            quantity = float(self.quantity_input.text())
            execution_time = int(self.exec_time_input.text())
            interval = int(self.interval_input.text())
        except ValueError:
            QMessageBox.warning(self, "Warning", "Please enter valid numeric values for quantity, execution time, and interval")
            return
        
        order_type = self.order_type_combo.currentText()
        self.client.exchange = exchange

        # New stop event for each order
        self.stop_event = threading.Event()

        # Start WebSocket listener in a separate thread, passing the stop event
        self.websocket_thread = threading.Thread(
            target=start_websocket_listener,
            args=(self.client, symbol, self.stop_event),
            daemon=True
        )
        self.websocket_thread.start()

        # Wait for prices to be received (in order to avoid problems like
        # prices fixed to 0)
        start_time = time.time()
        max_wait = 15  # Maximum wait time in seconds
    
        self.status_display.append(f"Starting WebSocket connection for {symbol} on {exchange}...")
    
        # Wait for price data to be available
        while symbol not in self.client.latest_prices and (time.time() - start_time) < max_wait:
            time.sleep(0.5)
            QApplication.processEvents()  # Keep GUI responsive during wait
    
        if symbol not in self.client.latest_prices:
            self.status_display.append(f"Warning: No price data received for {symbol} after {max_wait} seconds. Order may fail.")
        else:
            self.status_display.append(f"Received price data: Bid={self.client.latest_prices[symbol]['bid_price']}, Ask={self.client.latest_prices[symbol]['ask_price']}")
    
        self.status_display.append(f"Submitting TWAP order for {symbol} on {exchange}...")

        # Submit the TWAP order
        try:
            result = self.client.submit_twap_order(
                symbol=symbol,
                quantity=quantity,
                execution_time=execution_time,
                interval=interval,
                order_type=order_type
            )
        
            if isinstance(result, dict) and "order_id" in result:
                token_id = result["order_id"]
                self.status_display.append(f"Order submitted successfully with ID: {token_id}")
            
                # Monitor the order status
                self.monitor_order_status(token_id)
            else:
                self.status_display.append("Order submission response format unexpected")
                self.status_display.append(f"Response: {result}")
            
        except Exception as e:
            self.status_display.append(f"Error submitting order: {str(e)}")
            self.stop_event.set()  # Signal the WebSocket thread to stop

    def monitor_order_status(self, token_id):
        """
        Monitor the order status and display it in the GUI. directly
        """
        # Modification to directly use the token_id given by the server
        for _ in range(10):  # Monitor for a maximum of 10 iterations
            try:
                order_status = self.client.get_order_status(token_id)
                self.status_display.append(f"Order Status: {order_status}")

                # Check if the order is completed or partially completed
                if order_status.get("status") in ["completed", "partial"]:
                    self.status_display.append("Order execution completed. Closing WebSocket connection...")
                    self.stop_event.set()  # Stop the Websocket thread 
                    if hasattr(self, 'websocket_thread') and self.websocket_thread.is_alive():
                        self.websocket_thread.join(timeout=2)  # Wait for the WebSocket thread to finish with timeout
                    break  
            except Exception as e:
                self.status_display.append(f"Error getting order status: {str(e)}")
                break

            time.sleep(6)  # We wait before checking the status again
        else:
            self.status_display.append("TWAP Order monitoring completed!")

def run_server():
    """
    Run the FastAPI server using uvicorn.
    This way, lauching the GUI will automatically lauch the server. 
    No need to lauch the server alone beforehand.
    """
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
