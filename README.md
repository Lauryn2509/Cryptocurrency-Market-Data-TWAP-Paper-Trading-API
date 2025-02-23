# Cryptocurrency TWAP Paper Trading System

This project implements a paper trading system for cryptocurrency markets, specifically focusing on TWAP (Time-Weighted Average Price) order execution. This project provides a full simulation environment for TWAP paper trading on cryptocurrency markets, consisting of an API server built with FastAPI, a Python client package and a PyQt5-based GUI for a user-friendly experience.

---

## 1. Overview : what is a TWAP and what achieves this API

### What is a TWAP ?
TWAP is a trading strategy used to execute large orders by breaking them into smaller parts that are executed evenly over a specified period. This approach minimizes market impact and helps achieve an average price close to the overall market rate.

### Aim of the API
The primary goal of this API is to simulate cryptocurrency trading using TWAP orders without risking real capital. It achieves this by allowing users to:
- Monitor real-time cryptocurrency prices from Binance or Kraken (choice given to the user)
- Execute TWAP orders for supported trading pairs
- Track order execution progress
- Access market data through WebSocket connections

### Architecture
This project is based around the following architecture
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
```
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
  - `GET /exchanges`: Lists supported exchanges (Binance and Kraken).  
  - `GET /exchanges/{exchange}/pairs`: Returns trading pairs for the specified exchange.

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
- Swagger UI at `http://localhost:8000/docs`
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
  - **Initialization**: Authenticates using preset credentials and retrieves a JWT token.
  - **Market Data**: Stores the latest market prices fetched via WebSocket.
  - **Methods**:
    - `fetch_exchanges()`: Retrieves the list of supported exchanges.
    - `fetch_trading_pairs()`: Gets available trading pairs for the selected exchange.
    - `submit_twap_order()`: Submits a TWAP order using the current market price (if available).
    - `get_order_status()`: Checks the current status of an order by its token ID.
- **WebSocket Listener**:  
  The `start_websocket_listener()` function launches an asynchronous WebSocket listener to update market prices in real time.

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
Or just run the file in VSCode or anything else. 
