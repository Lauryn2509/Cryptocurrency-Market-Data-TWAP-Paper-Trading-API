import pytest
import threading
import asyncio
import json
import requests_mock
from unittest.mock import AsyncMock, patch
from client.trading_client import TradingClient, start_websocket_listener, listen_to_order_book

@pytest.fixture
def mock_client():
    """
    Fixture to create a mock TradingClient instance with a mocked authentication token.
    """
    with requests_mock.Mocker() as m:
        m.post("http://localhost:8000/token", json={"access_token": "mock_token", "token_type": "bearer"})
        yield TradingClient()

def test_fetch_exchanges(mock_client, requests_mock):
    """
    Test fetching exchanges from the API.
    """
    requests_mock.get("http://localhost:8000/exchanges", json={"exchanges": ["binance", "kraken"]})
    
    result = mock_client.fetch_exchanges()
    assert result == {"exchanges": ["binance", "kraken"]}

def test_fetch_trading_pairs_binance(mock_client, requests_mock):
    """
    Test fetching trading pairs for binance.
    """
    # Correct response structure with 'exchange' and 'pairs' fields
    requests_mock.get(
        "http://localhost:8000/exchanges/binance/pairs", 
        json={"exchange": "binance", "pairs": ["BTCUSDT", "ETHUSDT"]}
    )

    result = mock_client.fetch_trading_pairs()
    assert result == {"exchange": "binance", "pairs": ["BTCUSDT", "ETHUSDT"]}

def test_fetch_kraken_pairs_from_cache(requests_mock):
    """
    Test fetching Kraken pairs from cache when available.
    """
    # Mock the token request
    requests_mock.post("http://localhost:8000/token", json={"access_token": "mock_token", "token_type": "bearer"})
    
    # Create client and pre-populate cache
    client = TradingClient(exchange="kraken")
    client._websocket_pairs_cache["kraken"] = ["XBT/USD", "ETH/USD"]
    
    # Test the function
    result = client.fetch_trading_pairs()
    assert result == {"exchange": "kraken", "pairs": ["XBT/USD", "ETH/USD"]}

def test_submit_twap_order(mock_client, requests_mock):
    """
    Test submitting a TWAP order with mock API response.
    """
    mock_response = {
        "message": "TWAP order accepted", 
        "order_id": "twap_btcusdt",
        "order_details": {
            "token_id": "twap_btcusdt",
            "exchange": "binance",
            "symbol": "BTCUSDT",
            "quantity": 5,
            "price": 50000,
            "order_type": "buy",
            "status": "open",
            "executed_quantity": 0.0,
            "executions": []
        }
    }
    
    requests_mock.post(
        "http://localhost:8000/orders/twap",
        json=mock_response
    )

    # Mock price data
    mock_client.latest_prices["BTCUSDT"] = {"bid_price": 49900, "ask_price": 50000}
    
    response = mock_client.submit_twap_order(
        symbol="BTCUSDT", 
        quantity=5, 
        execution_time=300, 
        interval=60
    )
    
    assert response == mock_response
    assert "BTCUSDT" in mock_client.latest_prices

def test_get_order_status(mock_client, requests_mock):
    """
    Test fetching order status from the API.
    """
    mock_order = {
        "token_id": "twap_btcusdt",
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "quantity": 5,
        "price": 50000,
        "order_type": "buy",
        "status": "open",
        "executed_quantity": 0.0,
        "executions": []
    }
    
    requests_mock.get(
        "http://localhost:8000/orders/twap_btcusdt", 
        json=mock_order
    )

    response = mock_client.get_order_status("twap_btcusdt")
    assert response == mock_order
    assert response["status"] == "open"

@pytest.mark.asyncio
async def test_listen_to_order_book(mocker):
    """
    Test the listen_to_order_book function directly.
    """
    # Create a proper mock for the POST request with a successful response
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"access_token": "mock_token", "token_type": "bearer"}
    
    # Patch requests.post to return our mock response
    mocker.patch('requests.post', return_value=mock_response)
    
    # Now we can create the client which will use our mocked authentication
    client = TradingClient()
    
    # Create a mock websocket
    mock_websocket = AsyncMock()
    mock_websocket.__aenter__.return_value.recv.side_effect = [
        json.dumps({
            "order_book": {
                "XBT/USD": {"bid_price": 49000, "ask_price": 49100}
            }
        }),
        Exception("WebSocket closed")  # Force exit from the loop
    ]
    
    # Create a stop event
    stop_event = threading.Event()
    
    # Patch websockets.connect
    with patch("websockets.connect", return_value=mock_websocket):
        try:
            await listen_to_order_book(client, "XBT/USD", stop_event)
        except Exception:
            pass  # Expected exception to exit the loop
    
    # Check that the client's latest_prices was updated
    assert "XBT/USD" in client.latest_prices
    assert client.latest_prices["XBT/USD"]["bid_price"] == 49000
    assert client.latest_prices["XBT/USD"]["ask_price"] == 49100

@pytest.mark.asyncio
async def test_websocket_listener_thread():
    """
    Test the WebSocket listener thread function.
    """
    # Create a mock client
    with requests_mock.Mocker() as m:
        m.post("http://localhost:8000/token", json={"access_token": "mock_token", "token_type": "bearer"})
        client = TradingClient()
    
    # Mock the listen_to_order_book function
    async def mock_listen(client, symbol, stop_event):
        client.latest_prices[symbol] = {"bid_price": 50000, "ask_price": 50100}
        await asyncio.sleep(0.5)
    
    # Create a stop event
    stop_event = threading.Event()
    
    # Patch the listen_to_order_book function
    with patch("client.trading_client.listen_to_order_book", mock_listen):
        # Start the websocket listener thread
        thread = threading.Thread(
            target=start_websocket_listener, 
            args=(client, "BTCUSDT", stop_event),
            daemon=True
        )
        thread.start()
        
        # Give the thread a moment to execute
        await asyncio.sleep(1)
        
        # Check that the client's latest_prices was updated
        assert "BTCUSDT" in client.latest_prices
        assert client.latest_prices["BTCUSDT"]["bid_price"] == 50000
        assert client.latest_prices["BTCUSDT"]["ask_price"] == 50100
        
        # Stop the thread
        stop_event.set()
        thread.join(timeout=2)
