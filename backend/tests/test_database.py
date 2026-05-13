"""Tests for database operations"""
import pytest
from services.database_service import get_signals


def test_get_signals():
    """Test retrieving signals"""
    signals = get_signals(limit=5)
    assert isinstance(signals, list)
    assert len(signals) <= 5

    # Check signal structure if any exist
    if signals:
        signal = signals[0]
        assert "pair" in signal
        assert "decision" in signal
        assert "confidence" in signal


def test_get_signals_large_limit():
    """Test signal retrieval with large limit"""
    signals = get_signals(limit=100)
    assert isinstance(signals, list)
    # Should never exceed requested limit
    assert len(signals) <= 100


def test_get_signals_zero_limit():
    """Test with zero limit returns empty"""
    signals = get_signals(limit=0)
    assert isinstance(signals, list)
    assert len(signals) == 0
