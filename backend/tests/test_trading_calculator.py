"""Tests for trading calculator module"""
import pytest
from services.trading_calculator import (
    TradingCalculator,
    PipCalculation,
    PositionSizing,
    ProfitSimulation,
    MultiTargetPlan,
    TradeQuality
)


class TestPipCalculation:
    """Test pip calculation for different pair types"""

    def test_non_jpy_pair_pips(self):
        """Test pip calculation for EUR/USD (non-JPY pair)"""
        result = TradingCalculator.calculate_pips(
            pair="EUR/USD",
            entry=1.0850,
            target=1.0950,
            stop_loss=1.0800
        )
        assert isinstance(result, PipCalculation)
        assert result.target_pips == 100.0  # (1.0950 - 1.0850) / 0.0001 = 100
        assert result.stop_loss_pips == 50.0  # (1.0850 - 1.0800) / 0.0001 = 50
        assert result.risk_reward_ratio == 2.0  # 100 / 50 = 2.0
        assert result.pip_value > 0

    def test_jpy_pair_pips(self):
        """Test pip calculation for USD/JPY (JPY pair)"""
        result = TradingCalculator.calculate_pips(
            pair="USD/JPY",
            entry=150.00,
            target=151.50,
            stop_loss=149.50
        )
        assert isinstance(result, PipCalculation)
        assert result.target_pips == 150.0  # (151.50 - 150.00) / 0.01 = 150
        assert result.stop_loss_pips == 50.0  # (150.00 - 149.50) / 0.01 = 50
        assert result.risk_reward_ratio == 3.0  # 150 / 50 = 3.0

    def test_nifty_pair_pips(self):
        """Test pip calculation for NIFTY (index)"""
        result = TradingCalculator.calculate_pips(
            pair="NIFTY",
            entry=20000,
            target=20500,
            stop_loss=19800
        )
        assert isinstance(result, PipCalculation)
        assert result.target_pips == 500.0  # (20500 - 20000) / 1.0 = 500
        assert result.stop_loss_pips == 200.0  # (20000 - 19800) / 1.0 = 200
        assert result.risk_reward_ratio == 2.5  # 500 / 200 = 2.5

    def test_bitcoin_pair_pips(self):
        """Test pip calculation for BTC/USD (crypto)"""
        result = TradingCalculator.calculate_pips(
            pair="BTC/USD",
            entry=65000,
            target=67000,
            stop_loss=63000
        )
        assert isinstance(result, PipCalculation)
        assert result.target_pips == 200000.0  # (67000 - 65000) / 0.01 = 200000 pips
        assert result.stop_loss_pips == 200000.0  # (65000 - 63000) / 0.01 = 200000 pips


class TestPositionSizing:
    """Test position size calculations"""

    def test_position_sizing_basic(self):
        """Test basic position sizing calculation"""
        result = TradingCalculator.calculate_position_size(
            account_balance=10000,
            risk_percentage=2.0,
            stop_loss_pips=500.0,
            pip_value=10.0,
            leverage=100
        )
        assert isinstance(result, PositionSizing)
        assert result.max_loss_amount == 200.0  # 10000 * 0.02 = 200
        assert result.leverage_used == 100
        assert result.recommended_lot_size > 0
        assert result.margin_required > 0

    def test_position_sizing_respects_risk(self):
        """Test that position sizing respects risk percentage"""
        # 5% risk vs 2% risk - should produce different lot sizes
        result_high_risk = TradingCalculator.calculate_position_size(
            account_balance=10000,
            risk_percentage=5.0,
            stop_loss_pips=100.0,
            pip_value=10.0,
            leverage=100
        )
        result_low_risk = TradingCalculator.calculate_position_size(
            account_balance=10000,
            risk_percentage=2.0,
            stop_loss_pips=100.0,
            pip_value=10.0,
            leverage=100
        )
        assert result_high_risk.recommended_lot_size > result_low_risk.recommended_lot_size
        assert result_high_risk.max_loss_amount == 500.0  # 5%
        assert result_low_risk.max_loss_amount == 200.0  # 2%

    def test_position_sizing_with_leverage(self):
        """Test position sizing with different leverage"""
        result_1x = TradingCalculator.calculate_position_size(
            account_balance=10000,
            risk_percentage=2.0,
            stop_loss_pips=100.0,
            pip_value=10.0,
            leverage=1
        )
        result_100x = TradingCalculator.calculate_position_size(
            account_balance=10000,
            risk_percentage=2.0,
            stop_loss_pips=100.0,
            pip_value=10.0,
            leverage=100
        )
        # Margin required should be 100x smaller with 100x leverage
        assert result_100x.margin_required < result_1x.margin_required


class TestProfitSimulation:
    """Test profit/loss simulation"""

    def test_profit_simulation_buy_position(self):
        """Test profit simulation for BUY position"""
        result = TradingCalculator.simulate_profit(
            entry=1.0850,
            target=1.0950,
            stop_loss=1.0800,
            lot_size=1.0,
            pip_value=10.0,
            target_pips=1000.0,
            stop_loss_pips=500.0,
            investment_amount=5000.0
        )
        assert isinstance(result, ProfitSimulation)
        assert result.estimated_profit_usd > 0  # 1.0 * 1000 * 10 = 10000
        assert result.estimated_loss_usd > 0  # 1.0 * 500 * 10 = 5000
        assert result.roi_percentage > 0

    def test_profit_simulation_different_lot_sizes(self):
        """Test that profit scales with lot size"""
        result_0_5 = TradingCalculator.simulate_profit(
            entry=1.0850,
            target=1.0950,
            stop_loss=1.0800,
            lot_size=0.5,
            pip_value=10.0,
            target_pips=1000.0,
            stop_loss_pips=500.0,
            investment_amount=2500.0
        )
        result_1_0 = TradingCalculator.simulate_profit(
            entry=1.0850,
            target=1.0950,
            stop_loss=1.0800,
            lot_size=1.0,
            pip_value=10.0,
            target_pips=1000.0,
            stop_loss_pips=500.0,
            investment_amount=5000.0
        )
        # Doubling lot size should double profit
        assert abs(result_1_0.estimated_profit_usd / result_0_5.estimated_profit_usd - 2.0) < 0.01


class TestMultiTargetPlan:
    """Test multi-target planning"""

    def test_multi_target_plan_non_jpy(self):
        """Test multi-target plan for non-JPY pair"""
        result = TradingCalculator.calculate_multi_targets(
            entry=1.0850,
            final_target=1.1050,
            stop_loss=1.0800,
            lot_size=1.0,
            pip_value=10.0,
            is_jpy=False
        )
        assert isinstance(result, MultiTargetPlan)
        # TP1 should be ~33% of the way
        assert 1.0850 < result.tp1_price < 1.0950
        # TP2 should be ~66% of the way
        assert 1.0950 < result.tp2_price < 1.1050
        # TP3 should be at final target
        assert result.tp3_price == 1.1050
        # Total profit should be sum of all TPs
        assert result.total_expected_profit == result.tp1_profit + result.tp2_profit + result.tp3_profit

    def test_multi_target_prices_ordered(self):
        """Test that target prices are in correct order"""
        result = TradingCalculator.calculate_multi_targets(
            entry=20000,
            final_target=21000,
            stop_loss=19800,
            lot_size=1.0,
            pip_value=50.0,
            is_jpy=False
        )
        assert result.tp1_price < result.tp2_price < result.tp3_price
        assert result.tp1_pips < result.tp2_pips < result.tp3_pips


class TestTradeQuality:
    """Test trade quality scoring"""

    def test_quality_score_high_confidence(self):
        """Test quality score with high confidence"""
        result = TradingCalculator.calculate_trade_quality(
            confidence=95,
            rr_ratio=3.0,
            volatility_indicator=1.0,
            trend_strength=90.0
        )
        assert isinstance(result, TradeQuality)
        # Quality = (95 * 0.4) + (min(3*10, 30) * 0.3) + (90 * 0.3) = 38 + 9 + 27 = 74
        assert result.quality_score == 74.0
        assert result.strength_rating == "STRONG"
        assert result.risk_level == "LOW"

    def test_quality_score_low_confidence(self):
        """Test quality score with low confidence"""
        result = TradingCalculator.calculate_trade_quality(
            confidence=40,
            rr_ratio=1.0,
            volatility_indicator=2.5,
            trend_strength=30.0
        )
        assert result.quality_score < 50
        assert result.strength_rating == "WEAK"
        assert result.risk_level == "HIGH"

    def test_quality_score_high_volatility(self):
        """Test that high volatility increases risk level"""
        result_low_vol = TradingCalculator.calculate_trade_quality(
            confidence=90,
            rr_ratio=2.5,
            volatility_indicator=0.5,
            trend_strength=80.0
        )
        result_high_vol = TradingCalculator.calculate_trade_quality(
            confidence=90,
            rr_ratio=2.5,
            volatility_indicator=2.5,
            trend_strength=80.0
        )
        # Low volatility with good metrics should be LOW risk
        assert result_low_vol.risk_level == "LOW"
        # High volatility forces HIGH risk even with good quality score
        assert result_high_vol.risk_level == "HIGH"

    def test_trend_confirmation(self):
        """Test trend confirmation threshold"""
        result_weak = TradingCalculator.calculate_trade_quality(
            confidence=50,
            rr_ratio=1.5,
            volatility_indicator=1.0,
            trend_strength=60.0
        )
        result_strong = TradingCalculator.calculate_trade_quality(
            confidence=50,
            rr_ratio=1.5,
            volatility_indicator=1.0,
            trend_strength=80.0
        )
        assert result_weak.trend_confirmation == False
        assert result_strong.trend_confirmation == True


class TestIntegration:
    """Integration tests for complete workflow"""

    def test_complete_signal_analysis(self):
        """Test complete analysis of a signal"""
        pair = "EUR/USD"
        entry = 1.0850
        target = 1.0950
        stop_loss = 1.0800
        confidence = 85

        # Step 1: Calculate pips
        pips = TradingCalculator.calculate_pips(pair, entry, target, stop_loss)
        assert pips.risk_reward_ratio >= 2.0

        # Step 2: Calculate position size
        position = TradingCalculator.calculate_position_size(
            account_balance=10000,
            risk_percentage=2.0,
            stop_loss_pips=pips.stop_loss_pips,
            pip_value=pips.pip_value,
            leverage=100
        )
        assert position.recommended_lot_size > 0

        # Step 3: Simulate profit
        profit = TradingCalculator.simulate_profit(
            entry=entry,
            target=target,
            stop_loss=stop_loss,
            lot_size=position.recommended_lot_size,
            pip_value=pips.pip_value,
            target_pips=pips.target_pips,
            stop_loss_pips=pips.stop_loss_pips,
            investment_amount=position.margin_required
        )
        assert profit.estimated_profit_usd > 0

        # Step 4: Calculate trade quality
        quality = TradingCalculator.calculate_trade_quality(
            confidence=confidence,
            rr_ratio=pips.risk_reward_ratio,
            volatility_indicator=1.2,
            trend_strength=80.0
        )
        assert quality.quality_score > 60

    def test_nifty_complete_analysis(self):
        """Test complete analysis for NIFTY index"""
        pair = "NIFTY"
        entry = 20000
        target = 20500
        stop_loss = 19800
        confidence = 75

        pips = TradingCalculator.calculate_pips(pair, entry, target, stop_loss)
        assert pips.target_pips == 500.0

        position = TradingCalculator.calculate_position_size(
            account_balance=50000,
            risk_percentage=3.0,
            stop_loss_pips=pips.stop_loss_pips,
            pip_value=pips.pip_value,
            leverage=10
        )
        assert position.recommended_lot_size > 0

        profit = TradingCalculator.simulate_profit(
            entry=entry,
            target=target,
            stop_loss=stop_loss,
            lot_size=position.recommended_lot_size,
            pip_value=pips.pip_value,
            target_pips=pips.target_pips,
            stop_loss_pips=pips.stop_loss_pips,
            investment_amount=position.margin_required
        )
        assert profit.estimated_profit_usd > 0
