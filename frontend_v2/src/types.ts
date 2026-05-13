/**
 * API Response Types
 */

export interface PipCalculation {
  target_pips: number
  stop_loss_pips: number
  risk_reward_ratio: number
  pip_value: number
}

export interface PositionSizing {
  recommended_lot_size: number
  max_loss_amount: number
  expected_profit_amount: number
  margin_required: number
  leverage_used: number
}

export interface ProfitSimulation {
  estimated_profit_usd: number
  estimated_loss_usd: number
  roi_percentage: number
  margin_usage_percentage: number
  breakeven_price: number
}

export interface MultiTargetPlan {
  tp1_price: number
  tp1_pips: number
  tp1_profit: number
  tp2_price: number
  tp2_pips: number
  tp2_profit: number
  tp3_price: number
  tp3_pips: number
  tp3_profit: number
  total_expected_profit: number
}

export interface TradeQuality {
  quality_score: number
  strength_rating: 'WEAK' | 'MODERATE' | 'STRONG' | 'VERY_STRONG'
  volatility_level: 'LOW' | 'MEDIUM' | 'HIGH'
  trend_confirmation: boolean
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'EXTREME'
}

export interface EnhancedSignal {
  pair: string
  entry: number
  target: number
  stop_loss: number
  confidence: number
  pips: PipCalculation
  position: PositionSizing
  profit: ProfitSimulation
  targets: MultiTargetPlan
  quality: TradeQuality
}

export interface HistoricalSignal {
  id: number
  pair: string
  price_at_signal: number
  target?: number
  stop_loss?: number
  decision: string
  confidence: number
  timestamp: string
  pips: PipCalculation
  rr_ratio: number
}
