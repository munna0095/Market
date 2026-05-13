"""Integration tests for trading calculation API endpoints"""
import pytest
from fastapi.testclient import TestClient
import sys
import os

# Add parent directory to path to import main
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import after path is set
from main import app

client = TestClient(app)


class TestCalculationEndpoints:
    """Test trading calculation endpoints"""

    def test_calculate_pips_endpoint(self):
        """Test /api/calculate/pips endpoint"""
        response = client.post("/api/calculate/pips", json={
            "pair": "EUR/USD",
            "entry": 1.0850,
            "target": 1.0950,
            "stop_loss": 1.0800
        })
        assert response.status_code == 200
        data = response.json()
        assert data["target_pips"] == 100.0
        assert data["stop_loss_pips"] == 50.0
        assert data["risk_reward_ratio"] == 2.0

    def test_calculate_position_size_endpoint(self):
        """Test /api/calculate/position-size endpoint"""
        response = client.post("/api/calculate/position-size", json={
            "account_balance": 10000,
            "risk_percentage": 2.0,
            "stop_loss_pips": 100.0,
            "pip_value": 10.0,
            "leverage": 100
        })
        assert response.status_code == 200
        data = response.json()
        assert data["max_loss_amount"] == 200.0
        assert data["recommended_lot_size"] > 0
        assert data["margin_required"] > 0

    def test_simulate_profit_endpoint(self):
        """Test /api/calculate/profit-simulation endpoint"""
        response = client.post("/api/calculate/profit-simulation", json={
            "pair": "EUR/USD",
            "entry": 1.0850,
            "target": 1.0950,
            "stop_loss": 1.0800,
            "lot_size": 1.0,
            "investment_amount": 5000.0
        })
        assert response.status_code == 200
        data = response.json()
        assert data["estimated_profit_usd"] > 0
        assert data["estimated_loss_usd"] > 0
        assert "roi_percentage" in data

    def test_enhanced_signal_endpoint(self):
        """Test /api/calculate/enhanced-signal endpoint"""
        response = client.post("/api/calculate/enhanced-signal", json={
            "pair": "EUR/USD",
            "entry": 1.0850,
            "target": 1.0950,
            "stop_loss": 1.0800,
            "confidence": 85,
            "account_balance": 10000.0,
            "risk_percentage": 2.0,
            "leverage": 100
        })
        assert response.status_code == 200
        data = response.json()

        # Verify all components are present
        assert data["pair"] == "EUR/USD"
        assert data["confidence"] == 85
        assert "pips" in data
        assert "position" in data
        assert "profit" in data
        assert "targets" in data
        assert "quality" in data

        # Verify pip calculations
        assert data["pips"]["target_pips"] == 100.0
        assert data["pips"]["risk_reward_ratio"] == 2.0

        # Verify quality metrics
        assert 0 <= data["quality"]["quality_score"] <= 100
        assert data["quality"]["strength_rating"] in ["WEAK", "MODERATE", "STRONG", "VERY_STRONG"]
        assert data["quality"]["risk_level"] in ["LOW", "MEDIUM", "HIGH", "EXTREME"]

        # Verify multi-target plan
        assert data["targets"]["tp1_price"] < data["targets"]["tp2_price"] < data["targets"]["tp3_price"]

    def test_enhanced_signal_nifty(self):
        """Test enhanced signal for NIFTY index"""
        response = client.post("/api/calculate/enhanced-signal", json={
            "pair": "NIFTY",
            "entry": 20000,
            "target": 20500,
            "stop_loss": 19800,
            "confidence": 75,
            "account_balance": 50000.0,
            "risk_percentage": 3.0,
            "leverage": 10
        })
        assert response.status_code == 200
        data = response.json()
        assert data["pair"] == "NIFTY"
        assert data["pips"]["target_pips"] == 500.0

    def test_enhanced_signal_endpoint_error_handling(self):
        """Test error handling in enhanced signal endpoint"""
        # Invalid pair should still work but with 0 pip_value
        response = client.post("/api/calculate/enhanced-signal", json={
            "pair": "INVALID",
            "entry": 1.0,
            "target": 1.1,
            "stop_loss": 0.9,
            "confidence": 50,
            "account_balance": 10000.0,
            "risk_percentage": 2.0,
            "leverage": 100
        })
        # Should still return 200 as the calculation is valid
        assert response.status_code == 200


class TestOpenAPIDocumentation:
    """Test OpenAPI documentation for new endpoints"""

    def test_openapi_schema_includes_calculations(self):
        """Test that OpenAPI schema includes calculation endpoints"""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()

        # Check that calculation paths are documented
        assert "/api/calculate/pips" in schema["paths"]
        assert "/api/calculate/position-size" in schema["paths"]
        assert "/api/calculate/profit-simulation" in schema["paths"]
        assert "/api/calculate/enhanced-signal" in schema["paths"]
        assert "/api/signals/enhanced-history" in schema["paths"]

    def test_calculation_endpoints_have_tags(self):
        """Test that calculation endpoints have proper tags"""
        response = client.get("/openapi.json")
        schema = response.json()

        # Check tags
        pips_endpoint = schema["paths"]["/api/calculate/pips"]["post"]
        assert "calculations" in pips_endpoint.get("tags", [])

        enhanced_endpoint = schema["paths"]["/api/calculate/enhanced-signal"]["post"]
        assert "calculations" in enhanced_endpoint.get("tags", [])
