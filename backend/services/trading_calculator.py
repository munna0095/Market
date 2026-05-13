"""
Professional trading calculations module.
Handles pip calculations, position sizing, risk-reward, profit/loss projections.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple
import math


@dataclass
class PipCalculation:
    """Pip movement calculation result"""
    target_pips: float
    stop_loss_pips: float
    risk_reward_ratio: float
    pip_value: float  # Value of 1 pip in USD


@dataclass
class PositionSizing:
    """Position size calculation result"""
    recommended_lot_size: float
    max_loss_amount: float
    expected_profit_amount: float
    margin_required: float
    leverage_used: float


@dataclass
class ProfitSimulation:
    """Real profit/loss simulation"""
    estimated_profit_usd: float
    estimated_loss_usd: float
    roi_percentage: float
    margin_usage_percentage: float
    breakeven_price: float


@dataclass
class MultiTargetPlan:
    """Multi-target profit booking plan"""
    tp1_price: float
    tp1_pips: float
    tp1_profit: float
    tp2_price: float
    tp2_pips: float
    tp2_profit: float
    tp3_price: float
    tp3_pips: float
    tp3_profit: float
    total_expected_profit: float


@dataclass
class TradeQuality:
    """Advanced trade quality metrics"""
    quality_score: float  # 0-100
    strength_rating: str  # WEAK, MODERATE, STRONG, VERY_STRONG
    volatility_level: str  # LOW, MEDIUM, HIGH
    trend_confirmation: bool
    risk_level: str  # LOW, MEDIUM, HIGH, EXTREME


class TradingCalculator:
    """Professional forex trading calculator"""

    # Pip definitions
    JPY_PAIRS = ["USD/JPY", "EUR/JPY", "GBP/JPY", "AUD/JPY"]
    NON_JPY_PAIRS = ["EUR/USD", "GBP/USD", "AUD/USD", "NZD/USD", "USD/CHF", "USD/CAD"]
    INDICES = ["NIFTY", "SENSEX", "BANKNIFTY"]
    CRYPTO = ["BTC/USD", "ETH/USD"]

    # Standard lot sizes
    STANDARD_LOT = 100000
    MINI_LOT = 10000
    MICRO_LOT = 1000

    @staticmethod
    def calculate_pips(pair: str, entry: float, target: float, stop_loss: float) -> PipCalculation:
        """
        Calculate pip movement for forex pairs.

        JPY pairs: 1 pip = 0.01 (2 decimal places)
        Non-JPY pairs: 1 pip = 0.0001 (4 decimal places)
        Indices: 1 pip = 0.5 or 1 depending on index
        Crypto: 1 pip = 0.01
        """
        # Determine pip size based on pair type
        is_jpy = any(jpy in pair for jpy in TradingCalculator.JPY_PAIRS)
        is_index = any(idx in pair for idx in TradingCalculator.INDICES)
        is_crypto = any(crypto in pair for crypto in TradingCalculator.CRYPTO)

        if is_jpy:
            pip_size = 0.01
        elif is_index:
            pip_size = 1.0  # Indices use 1 point as pip
        elif is_crypto:
            pip_size = 0.01
        else:
            pip_size = 0.0001

        # Calculate pips
        target_pips = abs(target - entry) / pip_size
        stop_loss_pips = abs(entry - stop_loss) / pip_size

        # Risk-reward ratio
        rr_ratio = target_pips / stop_loss_pips if stop_loss_pips > 0 else 0

        # Pip value (for 1 standard lot)
        if is_index:
            # For indices: 1 point = $1 per standard lot (typically 1 contract = $50-100)
            pip_value = 50.0
        elif is_crypto:
            # For crypto: price-based calculation
            pip_value = (pip_size * TradingCalculator.STANDARD_LOT) / entry if entry > 0 else 0
        elif "USD" in pair.split("/")[1]:  # XXX/USD
            pip_value = pip_size * TradingCalculator.STANDARD_LOT
        else:
            pip_value = (pip_size * TradingCalculator.STANDARD_LOT) / entry if entry > 0 else 0

        return PipCalculation(
            target_pips=round(target_pips, 1),
            stop_loss_pips=round(stop_loss_pips, 1),
            risk_reward_ratio=round(rr_ratio, 2),
            pip_value=round(pip_value, 2)
        )

    @staticmethod
    def calculate_position_size(
        account_balance: float,
        risk_percentage: float,
        stop_loss_pips: float,
        pip_value: float,
        leverage: int = 1
    ) -> PositionSizing:
        """
        Calculate optimal position size based on risk management.

        Formula:
        Position Size = (Account Balance × Risk %) / (Stop Loss Pips × Pip Value)
        """
        # Maximum loss amount
        max_loss = account_balance * (risk_percentage / 100)

        # Calculate lot size
        if stop_loss_pips > 0 and pip_value > 0:
            lot_size = max_loss / (stop_loss_pips * pip_value)
        else:
            lot_size = 0

        # Round to nearest 0.01 lot
        lot_size = round(lot_size, 2)

        # Margin required (without leverage)
        margin_required = (lot_size * TradingCalculator.STANDARD_LOT) / leverage if leverage > 0 else 0

        return PositionSizing(
            recommended_lot_size=lot_size,
            max_loss_amount=round(max_loss, 2),
            expected_profit_amount=0,  # Will be calculated separately
            margin_required=round(margin_required, 2),
            leverage_used=leverage
        )

    @staticmethod
    def simulate_profit(
        entry: float,
        target: float,
        stop_loss: float,
        lot_size: float,
        pip_value: float,
        target_pips: float,
        stop_loss_pips: float,
        investment_amount: float
    ) -> ProfitSimulation:
        """
        Simulate real profit/loss for the trade.

        Profit = Lot Size × Target Pips × Pip Value
        Loss = Lot Size × Stop Loss Pips × Pip Value
        ROI = (Profit / Investment) × 100
        """
        estimated_profit = lot_size * target_pips * pip_value
        estimated_loss = lot_size * stop_loss_pips * pip_value

        roi = (estimated_profit / investment_amount) * 100 if investment_amount > 0 else 0
        margin_usage = (investment_amount / (lot_size * TradingCalculator.STANDARD_LOT)) * 100 if (lot_size * TradingCalculator.STANDARD_LOT) > 0 else 0

        # Breakeven price
        spread_estimate = abs(entry - stop_loss) * 0.05  # 5% of SL as spread estimate
        if target > entry:
            breakeven = entry + spread_estimate
        else:
            breakeven = entry - spread_estimate

        return ProfitSimulation(
            estimated_profit_usd=round(estimated_profit, 2),
            estimated_loss_usd=round(estimated_loss, 2),
            roi_percentage=round(roi, 2),
            margin_usage_percentage=round(margin_usage, 2),
            breakeven_price=round(breakeven, 5)
        )

    @staticmethod
    def calculate_multi_targets(
        entry: float,
        final_target: float,
        stop_loss: float,
        lot_size: float,
        pip_value: float,
        is_jpy: bool
    ) -> MultiTargetPlan:
        """
        Calculate 3-tier target system (TP1: 33%, TP2: 66%, TP3: 100%).
        """
        pip_size = 0.01 if is_jpy else 0.0001
        total_move = final_target - entry

        # Calculate target prices
        tp1_price = entry + (total_move * 0.33)
        tp2_price = entry + (total_move * 0.66)
        tp3_price = final_target

        # Calculate pips for each target
        tp1_pips = abs(tp1_price - entry) / pip_size if pip_size > 0 else 0
        tp2_pips = abs(tp2_price - entry) / pip_size if pip_size > 0 else 0
        tp3_pips = abs(tp3_price - entry) / pip_size if pip_size > 0 else 0

        # Calculate profits (assuming 50% closed at TP1, 30% at TP2, 20% at TP3)
        tp1_profit = (lot_size * 0.5) * tp1_pips * pip_value
        tp2_profit = (lot_size * 0.3) * tp2_pips * pip_value
        tp3_profit = (lot_size * 0.2) * tp3_pips * pip_value

        return MultiTargetPlan(
            tp1_price=round(tp1_price, 5),
            tp1_pips=round(tp1_pips, 1),
            tp1_profit=round(tp1_profit, 2),
            tp2_price=round(tp2_price, 5),
            tp2_pips=round(tp2_pips, 1),
            tp2_profit=round(tp2_profit, 2),
            tp3_price=round(tp3_price, 5),
            tp3_pips=round(tp3_pips, 1),
            tp3_profit=round(tp3_profit, 2),
            total_expected_profit=round(tp1_profit + tp2_profit + tp3_profit, 2)
        )

    @staticmethod
    def calculate_trade_quality(
        confidence: int,
        rr_ratio: float,
        volatility_indicator: float,  # From agent data (ATR, ADX)
        trend_strength: float  # From agent data
    ) -> TradeQuality:
        """
        Calculate advanced trade quality metrics.

        Quality Score = (Confidence × 0.4) + (RR × 10 × 0.3) + (Trend × 0.3)
        """
        # Base quality from confidence
        quality_base = confidence * 0.4

        # RR contribution (capped at 30 points)
        rr_contribution = min(rr_ratio * 10, 30) * 0.3

        # Trend contribution
        trend_contribution = trend_strength * 0.3

        quality_score = quality_base + rr_contribution + trend_contribution

        # Determine strength rating
        if quality_score >= 80:
            strength = "VERY_STRONG"
        elif quality_score >= 65:
            strength = "STRONG"
        elif quality_score >= 50:
            strength = "MODERATE"
        else:
            strength = "WEAK"

        # Volatility level
        if volatility_indicator > 2.0:
            volatility = "HIGH"
        elif volatility_indicator > 1.0:
            volatility = "MEDIUM"
        else:
            volatility = "LOW"

        # Risk level based on quality and volatility
        if quality_score < 50 or volatility == "HIGH":
            risk_level = "HIGH"
        elif quality_score < 65:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        return TradeQuality(
            quality_score=round(quality_score, 1),
            strength_rating=strength,
            volatility_level=volatility,
            trend_confirmation=(trend_strength >= 70),
            risk_level=risk_level
        )


# Export for use in other modules
__all__ = [
    'TradingCalculator',
    'PipCalculation',
    'PositionSizing',
    'ProfitSimulation',
    'MultiTargetPlan',
    'TradeQuality'
]
