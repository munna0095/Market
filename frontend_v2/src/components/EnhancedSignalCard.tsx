import React, { useState } from 'react'
import { motion } from 'framer-motion'
import {
  TrendingUp,
  TrendingDown,
  Target,
  Shield,
  DollarSign,
  AlertTriangle,
  Calculator,
} from 'lucide-react'
import type { EnhancedSignal } from '../types'
import { clsx } from 'clsx'

interface Props {
  signal: EnhancedSignal
}

export const EnhancedSignalCard: React.FC<Props> = ({ signal }) => {
  const [showDetails, setShowDetails] = useState(false)

  const isBuy = signal.target > signal.entry
  const qualityColor = clsx(
    signal.quality.quality_score >= 80 && 'text-emerald-400',
    signal.quality.quality_score >= 65 && signal.quality.quality_score < 80 && 'text-blue-400',
    signal.quality.quality_score >= 50 && signal.quality.quality_score < 65 && 'text-yellow-400',
    signal.quality.quality_score < 50 && 'text-red-400'
  )

  const rrColor = clsx(
    signal.pips.risk_reward_ratio >= 3 && 'text-emerald-400',
    signal.pips.risk_reward_ratio >= 2 && signal.pips.risk_reward_ratio < 3 && 'text-blue-400',
    signal.pips.risk_reward_ratio < 2 && 'text-yellow-400'
  )

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-slate-800/50 backdrop-blur-xl rounded-2xl border border-slate-700/50 p-6 hover:border-slate-600/50 transition-all"
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div
            className={clsx(
              'p-2 rounded-lg',
              isBuy ? 'bg-emerald-500/20' : 'bg-red-500/20'
            )}
          >
            {isBuy ? (
              <TrendingUp className="text-emerald-400 w-5 h-5" />
            ) : (
              <TrendingDown className="text-red-400 w-5 h-5" />
            )}
          </div>
          <div>
            <h3 className="text-xl font-bold text-white">{signal.pair}</h3>
            <p
              className={clsx(
                'text-sm font-semibold',
                isBuy ? 'text-emerald-400' : 'text-red-400'
              )}
            >
              {isBuy ? 'LONG POSITION' : 'SHORT POSITION'}
            </p>
          </div>
        </div>

        {/* Quality Badge */}
        <div className="px-4 py-2 rounded-lg bg-slate-700/50 border border-slate-600 text-center">
          <p className="text-xs text-slate-400">Quality Score</p>
          <p className={clsx('text-2xl font-bold', qualityColor)}>
            {signal.quality.quality_score.toFixed(0)}
          </p>
        </div>
      </div>

      {/* Main Metrics Grid */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <div className="bg-slate-900/50 rounded-lg p-4 border border-slate-700/30">
          <div className="flex items-center gap-2 mb-2">
            <Target className="w-4 h-4 text-blue-400" />
            <span className="text-xs text-slate-400">Risk : Reward</span>
          </div>
          <p className={clsx('text-3xl font-bold', rrColor)}>
            1 : {signal.pips.risk_reward_ratio.toFixed(1)}
          </p>
        </div>

        <div className="bg-slate-900/50 rounded-lg p-4 border border-slate-700/30">
          <div className="flex items-center gap-2 mb-2">
            <Shield className="w-4 h-4 text-purple-400" />
            <span className="text-xs text-slate-400">AI Confidence</span>
          </div>
          <p className="text-3xl font-bold text-purple-400">
            {signal.confidence}%
          </p>
        </div>
      </div>

      {/* Pip Analysis */}
      <div className="mb-6">
        <h4 className="text-sm font-semibold text-slate-400 mb-3">PIP ANALYSIS</h4>
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-slate-900/30 rounded-lg p-3">
            <p className="text-xs text-slate-500">Target Pips</p>
            <p className="text-lg font-bold text-emerald-400">
              +{signal.pips.target_pips.toFixed(1)}
            </p>
          </div>
          <div className="bg-slate-900/30 rounded-lg p-3">
            <p className="text-xs text-slate-500">Stop Loss Pips</p>
            <p className="text-lg font-bold text-red-400">
              -{signal.pips.stop_loss_pips.toFixed(1)}
            </p>
          </div>
        </div>
      </div>

      {/* Price Levels */}
      <div className="space-y-2 mb-6">
        <PriceLevel
          label="Entry"
          price={signal.entry}
          color="text-blue-400"
        />
        <PriceLevel
          label="Target"
          price={signal.target}
          color="text-emerald-400"
        />
        <PriceLevel
          label="Stop Loss"
          price={signal.stop_loss}
          color="text-red-400"
        />
      </div>

      {/* Multi-Target System */}
      <div className="mb-6">
        <h4 className="text-sm font-semibold text-slate-400 mb-3">MULTI-TARGET PLAN</h4>
        <div className="space-y-2">
          <TargetLevel
            label="TP1 (33%)"
            price={signal.targets.tp1_price}
            pips={signal.targets.tp1_pips}
            profit={signal.targets.tp1_profit}
          />
          <TargetLevel
            label="TP2 (66%)"
            price={signal.targets.tp2_price}
            pips={signal.targets.tp2_pips}
            profit={signal.targets.tp2_profit}
          />
          <TargetLevel
            label="TP3 (100%)"
            price={signal.targets.tp3_price}
            pips={signal.targets.tp3_pips}
            profit={signal.targets.tp3_profit}
          />
        </div>
      </div>

      {/* Profit/Loss Simulation */}
      <div className="bg-gradient-to-r from-emerald-900/20 to-red-900/20 rounded-lg p-4 mb-6 border border-slate-700/30">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <DollarSign className="w-4 h-4 text-emerald-400" />
              <span className="text-xs text-slate-400">Est. Profit</span>
            </div>
            <p className="text-2xl font-bold text-emerald-400">
              ${signal.profit.estimated_profit_usd.toFixed(2)}
            </p>
            <p className="text-xs text-emerald-400/60">
              +{signal.profit.roi_percentage.toFixed(1)}% ROI
            </p>
          </div>

          <div>
            <div className="flex items-center gap-2 mb-1">
              <AlertTriangle className="w-4 h-4 text-red-400" />
              <span className="text-xs text-slate-400">Max Loss</span>
            </div>
            <p className="text-2xl font-bold text-red-400">
              ${signal.profit.estimated_loss_usd.toFixed(2)}
            </p>
            <p className="text-xs text-red-400/60">
              Risk: {signal.quality.risk_level}
            </p>
          </div>
        </div>
      </div>

      {/* Position Sizing */}
      <div className="bg-slate-900/50 rounded-lg p-4 mb-4 border border-slate-700/30">
        <h4 className="text-sm font-semibold text-slate-400 mb-3">POSITION SIZING</h4>
        <div className="grid grid-cols-3 gap-4 text-center">
          <div>
            <p className="text-xs text-slate-500 mb-1">Lot Size</p>
            <p className="text-lg font-bold text-white">
              {signal.position.recommended_lot_size.toFixed(2)}
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-500 mb-1">Margin</p>
            <p className="text-lg font-bold text-white">
              ${signal.position.margin_required.toFixed(2)}
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-500 mb-1">Max Risk</p>
            <p className="text-lg font-bold text-red-400">
              ${signal.position.max_loss_amount.toFixed(2)}
            </p>
          </div>
        </div>
      </div>

      {/* Risk Warning */}
      {signal.quality.risk_level === 'HIGH' && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex items-center gap-2 bg-red-500/10 border border-red-500/30 rounded-lg p-3 mb-4"
        >
          <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0" />
          <p className="text-sm text-red-300">
            <strong>High Risk Trade:</strong> {signal.quality.volatility_level} volatility detected.
          </p>
        </motion.div>
      )}

      {/* Toggle Details */}
      <button
        onClick={() => setShowDetails(!showDetails)}
        className="w-full flex items-center justify-center gap-2 bg-blue-500/10 hover:bg-blue-500/20 border border-blue-500/30 rounded-lg py-3 transition-all"
      >
        <Calculator className="w-4 h-4 text-blue-400" />
        <span className="text-sm font-semibold text-blue-400">
          {showDetails ? 'Hide' : 'Show'} Details
        </span>
      </button>

      {/* Expandable Details */}
      {showDetails && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          className="mt-4 pt-4 border-t border-slate-700/30 space-y-3"
        >
          <div className="grid grid-cols-2 gap-4 text-xs">
            <div>
              <p className="text-slate-500">Pip Value</p>
              <p className="font-semibold text-white">${signal.pips.pip_value.toFixed(2)}</p>
            </div>
            <div>
              <p className="text-slate-500">Strength</p>
              <p className="font-semibold text-white">{signal.quality.strength_rating}</p>
            </div>
            <div>
              <p className="text-slate-500">Volatility</p>
              <p className="font-semibold text-white">{signal.quality.volatility_level}</p>
            </div>
            <div>
              <p className="text-slate-500">Trend Confirmed</p>
              <p className="font-semibold text-white">
                {signal.quality.trend_confirmation ? 'Yes' : 'No'}
              </p>
            </div>
          </div>
        </motion.div>
      )}
    </motion.div>
  )
}

// Helper Components
const PriceLevel: React.FC<{
  label: string
  price: number
  color: string
}> = ({ label, price, color }) => (
  <div className="flex items-center justify-between bg-slate-900/30 rounded-lg px-4 py-2 border border-slate-700/20">
    <span className="text-sm text-slate-400">{label}</span>
    <span className={clsx('text-lg font-bold', color)}>
      {price.toFixed(5)}
    </span>
  </div>
)

const TargetLevel: React.FC<{
  label: string
  price: number
  pips: number
  profit: number
}> = ({ label, price, pips, profit }) => (
  <div className="flex items-center justify-between bg-slate-900/30 rounded-lg px-4 py-2 border border-slate-700/20">
    <div>
      <span className="text-xs text-slate-500">{label}</span>
      <span className="text-sm font-semibold text-white ml-2">
        {price.toFixed(5)}
      </span>
    </div>
    <div className="text-right">
      <p className="text-xs text-slate-500">+{pips.toFixed(1)} pips</p>
      <p className="text-sm font-bold text-emerald-400">
        ${profit.toFixed(2)}
      </p>
    </div>
  </div>
)
