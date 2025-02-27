# Cryptocurrency TWAP Paper Trading System

This project implements a paper trading system for cryptocurrency markets, specifically focusing on TWAP (Time-Weighted Average Price) order execution. This project provides a full simulation environment for TWAP paper trading on cryptocurrency markets, consisting of an API server built with FastAPI, a Python client package and a PyQt5-based GUI for a user-friendly experience.

You can check if you have all dependencies needed to run the GUI by simply running the `check_dependencies.py` file. 

---

## 1. Overview : what is a TWAP and what achieves this API

### What is a TWAP ?
TWAP is a trading strategy used to execute large orders by breaking them into smaller parts that are executed evenly over a specified period. This approach minimizes market impact and helps achieve an average price close to the overall market rate.

### Aim of the API
The primary goal of this API is to simulate cryptocurrency trading using TWAP orders without risking real capital. It achieves this by allowing users to :
- Obtain trading pairs and klines of a given pair through REST Endpoint from Binance or Kraken
- Monitor real-time cryptocurrency prices from Binance or Kraken (choice given to the user)
- Execute TWAP orders for supported trading pairs
- Track order execution progress
- Access market data through WebSocket connections

### Architecture
This project is based around the following architecture : 
```
Cryptocurrency-Market-Data-TWAP-Paper-Trading-API/
├── client/
│   ├── __init__.py
│   └── trading_client.py       # contains the TradingClient class
├── tests/
│   └── test_trading_client.py  # several unitary tests on the trading_client file
├── server/
│   └── server.py               # API server, backbone of the project
├── GUI.py                      # A GUI user-friendly implementation of the API
├── simple_example.py           # A more basic but also more flexible implementation 
├── pyproject.toml
└── README.md
└── check_dependencies.py       # Code to verify if you have all the libraires needed to run the GUI
```
**Please make sure to follow this architecture**. Failure to do so might result in unexpected errors.

---

## 2. The Server

The server (`server.py`) is the backbone of the project and is implemented using FastAPI. It manages authentication, rate limiting, market data updates, and the execution of TWAP orders.

### Authentication
- **JWT-Based Authentication**:  
  Users obtain a JWT token by posting valid credentials (username and password) to the `/token` endpoint. This token must be provided in the `Authorization` header (as `Bearer <token>`) for all protected endpoints.
- **Password Security**:  
  Passwords are hashed using bcrypt via the `passlib` library, ensuring secure storage and verification.

For the purposes of this project, valid usernames and passwords are "premium" and "CryptoTWAPpremium". Of course, in production, such credentials should stay secret.

### Rate Limiting
- **SlowAPI Integration**:  
  Rate limiting is implemented using SlowAPI. Each endpoint has defined limits (for instance, 15 requests per minute for fetching exchanges) to prevent abuse and ensure stable performance.

### Functionalities and Endpoints
- **Root Endpoint (`GET /`)**  
  Returns a simple welcome message confirming that the API is running.

- **Exchanges Endpoints**:  
  - `GET /exchanges` : Lists supported exchanges (Binance and Kraken).  
  - `GET /exchanges/{exchange}/pairs` : Returns trading pairs for the specified exchange. The format of the pairs is the Websocket API one, which is the same as the REST API format for Binance but different for Kraken.
  - `GET /exchanges/kraken/pairs_restpoint` : Returns trading pairs for Kraken at the REST API format.
  
- **Candlesticks endpoint** :
  - `GET /klines/{exchange}/{symbol}` : Returns klines for a given pair from a given exchange. **If you use Kraken, please make sure to use the REST API formatted pairs in your request**.

- **Orders Endpoints**:  
  - `GET /orders`: Lists all orders (authentication required).  
  - `GET /orders/{token_id}`: Retrieves the status of a specific order by its unique token.  
  - `POST /orders/twap`: Submits a TWAP order.  
    - **Request Body**: Includes order details such as `token_id`, `exchange`, `symbol`, `quantity`, `price`, and `order_type` (buy or sell).  
    - **Query Parameters**: `execution_time` (total duration for the TWAP order) and `interval` (time between executions).

- **WebSocket Endpoint (`/ws`)**:  
  Provides real-time updates of the order book, broadcasting live market data to all connected clients.

#### Swagger documentation 
We used FastAPI, which automatically provides a Swagger UI documentation, and have given enough information for a Swagger documentation to be understable and the user should feel free to explore it. After launching the server, navigate to : 
- Swagger UI at `http://localhost:8000/docs`. With this, you can try out HTTP endpoint, for instance to get pairs or klines. Do not hesitate to use it !
- ReDoc at `http://localhost:8000/redoc`

### Market Data and TWAP Execution Engine
- **Real-Time Data**:  
  The server fetches live market data from Binance and Kraken via WebSocket connections. This data is used to update the order book in real time.
- **TWAP Execution**:  
  When a TWAP order is submitted, the server splits the order into smaller parts based on the `execution_time` and `interval` parameters. It then attempts to execute these parts at regular intervals, updating the order status as either "completed" or "partial" based on execution success.

---

## 3. Client

The client package provides a Python interface for interacting with the API. It is designed to simplify the process of authenticating, retrieving market data, and submitting orders.

### Description
- **TradingClient Class**:  
  This class handles:
  - **Initialization**: Authenticates using credentials (defaults to "premium"/"CryptoTWAPpremium") and retrieves a JWT token.
  - **Market Data**: Maintains a cache of latest market prices fetched via WebSocket.
  - **Methods**:
    - `fetch_exchanges()`: Retrieves the list of supported exchanges.
    - `fetch_trading_pairs()`: Gets available trading pairs for the selected exchange, with special handling for Kraken.
    - `_fetch_kraken_websocket_pairs()`: Helper method to fetch Kraken pairs directly from Kraken API in WebSocket format.
    - `submit_twap_order()`: Submits a TWAP order using the current market price.
    - `get_order_status()`: Checks the current status of an order by its token ID.

- **WebSocket Functionality**:  
  The client includes two functions for real-time data:
  - `listen_to_order_book()`: Asynchronous function that connects to the server's WebSocket and listens for order book updates.
  - `start_websocket_listener()`: Helper function that starts the WebSocket listener in a separate thread, making it easy to run alongside other operations.

### TradingClient Methods

#### `__init__(self, exchange="binance", base_url="http://localhost:8000", username="premium", password="CryptoTWAPpremium")`
- Initializes the client with the specified exchange, server URL, and authentication credentials
- Sets up authentication headers and initializes price cache dictionaries

#### `_get_access_token(self)`
- Authenticates with the server and obtains a JWT access token
- Makes a POST request to the `/token` endpoint with username and password
- Returns the JWT token or raises an exception if authentication fails

#### `fetch_exchanges(self)`
- Retrieves the list of supported exchanges from the server
- Returns the JSON response from the server

#### `fetch_trading_pairs(self)`
- Fetches trading pairs for the selected exchange
- For Kraken, attempts to fetch WebSocket-formatted pairs directly from Kraken API first
- Uses cached results when available
- Falls back to server API if direct fetch fails
- Returns a dictionary with exchange name and list of pairs

#### `_fetch_kraken_websocket_pairs(self)`
- Helper method to fetch Kraken pairs directly from Kraken API in WebSocket format
- Makes request to Kraken API for asset pairs
- Extracts WebSocket-formatted pairs from the response
- Uses altname as fallback if wsname is not available
- Returns list of WebSocket pairs or empty list if fetch fails

#### `submit_twap_order(self, symbol="XBT/USD", quantity=10, execution_time=600, interval=60, order_type="buy")`
- Submits a TWAP order using the latest real-time market price
- Creates token_id based on the symbol
- Sends POST request to `/orders/twap` endpoint with order details
- Returns the JSON response from the server

#### `get_order_status(self, token_id)`
- Fetches the status of a given order by its token_id
- Makes GET request to `/orders/{token_id}` endpoint
- Returns the JSON response from the server

### WebSocket Functions

#### `listen_to_order_book(client, symbol="XBT/USD", stop_event=None)`
- Asynchronous function that connects to the server's WebSocket
- Listens for order book updates for the specified symbol
- Updates the client's latest_prices dictionary with new price data
- Continues running until the stop_event is set
- Only prints price updates when they change

#### `start_websocket_listener(client, symbol="BTCUSDT", stop_event=None)`
- Creates a new asyncio event loop in a separate thread
- Runs the listen_to_order_book coroutine in this loop
- Makes it easy to integrate WebSocket listening with other synchronous code

### Key Features
- **Automatic Authentication**: The client handles JWT authentication seamlessly.
- **Real-Time Price Updates**: WebSocket integration provides continuous market data.
- **Exchange-Specific Handling**: Special handling for Kraken pairs, with direct API fallback if needed.
- **Price Caching**: Maintains latest prices in memory for quick access when submitting orders.
- **Efficient WebSocket Management**: Thread-based implementation with support for graceful shutdown.

### Installation
The project is managed using Poetry. To install and set up the client package:
- **Install Dependencies via poetry**:
    ```bash
    poetry install
    ```
- **Install the package via pip**:
    ```bash
    pip install "path/to/the/package/" 
    ```

### Tests and Quality Tools
- **Testing Framework**:  
  The tests are written using `pytest` and `pytest-asyncio`. They can be found in the `tests` directory (e.g., `test_trading_client.py`).
- **Running Tests**:
    ```bash
    poetry run pytest
    ```
- **Mocking and Code Quality**:  
  The tests use tools like `requests_mock` and `pytest-mock` for simulating API responses. Code quality is maintained using `black`, `flake8`, and `isort`.

### Poetry Configuration
- **pyproject.toml**:  
  This file includes the package metadata, dependencies (e.g., `requests`, `websockets`, `asyncio`), and development dependencies (e.g., `pytest`, `black`, `flake8`). It serves as the central configuration for building and packaging the project.

---


## 4. GUI

A graphical user interface (GUI) is provided to allow users to interact with the TWAP trading API without using the command line.

### Features
- **Exchange and Trading Pair Selection**:  
  Users can choose between Binance and Kraken, and the corresponding trading pairs are updated dynamically.
- **Order Parameters Input**:  
  The GUI includes fields for specifying:
  - **Quantity**: Amount to trade.
  - **Execution Time**: Total duration over which the order is executed.
  - **Interval**: Time between successive executions.
  - **Order Type**: Buy or sell.
- **Order Submission and Monitoring**:  
  A "Submit TWAP Order" button sends the order to the server. The GUI then monitors the order status in real time, displaying updates in a text area.
- **Real-Time Data via WebSocket**:  
  The GUI starts a WebSocket listener in a separate thread to receive the latest market prices and ensure orders are executed based on current data.

### Running the GUI
To launch the GUI:
```bash
python GUI.py
```
Or just run the file in VSCode or other IDE. 
