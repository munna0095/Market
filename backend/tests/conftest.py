"""Pytest configuration and shared fixtures"""
import pytest
import asyncio
from datetime import datetime


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_price_data():
    """Mock price data for agent tests"""
    return {
        "price": 23500.50,
        "high": 23600.00,
        "low": 23400.00,
        "open": 23450.00,
        "volume": 1000000,
        "timestamp": datetime.now().isoformat()
    }


@pytest.fixture
def sample_indicators():
    """Mock technical indicators"""
    return {
        "rsi": 65.3,
        "macd": 1.2,
        "adx": 32.5,
        "atr": 150.0,
        "ema_9": 23480.0,
        "ema_21": 23450.0
    }
