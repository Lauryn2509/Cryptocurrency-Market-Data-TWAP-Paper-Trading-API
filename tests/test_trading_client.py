import pytest
import threading
import asyncio
import json
import requests_mock
from unittest.mock import AsyncMock
from client.trading_client import TradingClient, start_websocket_listener

@pytest.fixture
def mock_client():
    """Fixture to create a mock TradingClient instance with a mocked authentication token."""
    with requests_mock.Mocker() as m:
        m.post("http://localhost:8000/token", json={"access_token": "mock_token"})
        yield TradingClient()

def test_fetch_exchanges(mock_client, requests_mock):
    """Test fetching exchanges from the API."""
    requests_mock.get("http://localhost:8000/exchanges", json={"exchanges": ["binance", "kraken"]})
    
    result = mock_client.fetch_exchanges()
    assert result == {"exchanges": ["binance", "kraken"]}

def test_fetch_trading_pairs(mock_client, requests_mock):
    """Test fetching trading pairs for a given exchange."""
    requests_mock.get("http://localhost:8000/exchanges/binance/pairs", json={"pairs": ["BTCUSDT", "ETHUSDT"]})

    result = mock_client.fetch_trading_pairs()
    assert result == {"pairs": ["BTCUSDT", "ETHUSDT"]}

def test_submit_twap_order(mock_client, requests_mock):
    """Test submitting a TWAP order with mock API response."""
    requests_mock.post(
        "http://localhost:8000/orders/twap",
        json={"message": "TWAP order accepted", "order_id": "twap_btcusdt"}
    )

    mock_client.latest_prices["BTCUSDT"] = {"ask_price": 50000}  # Mock price data
    mock_client.submit_twap_order(symbol="BTCUSDT", quantity=5, execution_time=300, interval=60)

    assert "BTCUSDT" in mock_client.latest_prices  # Ensure market data is available

def test_get_order_status(mock_client, requests_mock):
    """Test fetching order status from the API."""
    requests_mock.get("http://localhost:8000/orders/twap_btcusdt", json={"status": "open"})

    response = mock_client.get_order_status("twap_btcusdt")
    assert response == {"status": "open"}

@pytest.mark.asyncio
async def test_websocket_connection(mock_client, mocker):
    """Test WebSocket connection and order book updates."""

    # Mock the WebSocket connection
    mock_websocket = AsyncMock()
    async def mock_recv():
        return json.dumps({"order_book": {"BTCUSDT": {"bid_price": 50000, "ask_price": 50100}}})

    mock_websocket.__aenter__.return_value.recv = mock_recv

    # Patch `websockets.connect` with the mocked WebSocket
    mocker.patch("websockets.connect", return_value=mock_websocket)

    # Start the WebSocket listener in a separate thread
    stop_event = threading.Event()
    websocket_thread = threading.Thread(target=start_websocket_listener, args=(mock_client, "BTCUSDT", stop_event), daemon=True)
    websocket_thread.start()

    # Allow time for connection and data processing
    await asyncio.sleep(1)

    # Ensure the WebSocket mock has updated prices
    assert "BTCUSDT" in mock_client.latest_prices
    assert mock_client.latest_prices["BTCUSDT"]["bid_price"] == 50000
    assert mock_client.latest_prices["BTCUSDT"]["ask_price"] == 50100

    # Stop the WebSocket listener
    stop_event.set()
    websocket_thread.join(timeout=2)