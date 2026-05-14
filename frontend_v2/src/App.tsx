import React, { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Settings, RefreshCw, AlertCircle } from 'lucide-react'
import { clsx } from 'clsx'
import { EnhancedSignalCard } from './components/EnhancedSignalCard'
import { getEnhancedSignal, getEnhancedSignalsHistory, healthCheck } from './services/api'
import type { EnhancedSignal, HistoricalSignal } from './types'
import './index.css'

export const App: React.FC = () => {
  const [signal, setSignal] = useState<EnhancedSignal | null>(null)
  const [history, setHistory] = useState<HistoricalSignal[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [apiHealth, setApiHealth] = useState(false)

  // Form state
  const [formData, setFormData] = useState({
    pair: 'EUR/USD',
    entry: 1.0850,
    target: 1.0950,
    stopLoss: 1.0800,
    confidence: 85,
    accountBalance: 10000,
    riskPercentage: 2.0,
    leverage: 100,
  })

  // Check API health on mount
  useEffect(() => {
    const checkHealth = async () => {
      const healthy = await healthCheck()
      setApiHealth(healthy)
    }
    checkHealth()
  }, [])

  // Load initial signal
  useEffect(() => {
    loadSignal()
  }, [])

  const loadSignal = async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await getEnhancedSignal(
        formData.pair,
        formData.entry,
        formData.target,
        formData.stopLoss,
        formData.confidence,
        formData.accountBalance,
        formData.riskPercentage,
        formData.leverage
      )
      setSignal(result)

      // Load history
      const historyData = await getEnhancedSignalsHistory(5)
      setHistory(historyData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load signal')
    } finally {
      setLoading(false)
    }
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({
      ...prev,
      [name]: name === 'confidence' || name === 'leverage' ? parseInt(value) : parseFloat(value),
    }))
  }

  const handleSelectChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setFormData(prev => ({
      ...prev,
      pair: e.target.value,
    }))
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-slate-700/50 bg-slate-900/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-white">Strategic War Room</h1>
              <p className="text-sm text-slate-400">Professional Trading Analytics Dashboard v2.0</p>
            </div>
            <div className="flex items-center gap-4">
              {apiHealth ? (
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse"></div>
                  <span className="text-xs text-emerald-400">API Connected</span>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 text-red-400" />
                  <span className="text-xs text-red-400">API Offline</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Input Panel */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-slate-800/50 backdrop-blur-xl rounded-2xl border border-slate-700/50 p-6 mb-8"
        >
          <div className="flex items-center gap-2 mb-4">
            <Settings className="w-5 h-5 text-blue-400" />
            <h2 className="text-xl font-bold text-white">Trade Analysis</h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Pair */}
            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-2">Trading Pair</label>
              <select
                value={formData.pair}
                onChange={handleSelectChange}
                className="w-full bg-slate-900/50 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm"
              >
                <option>EUR/USD</option>
                <option>USD/JPY</option>
                <option>NIFTY</option>
                <option>SENSEX</option>
                <option>BTC/USD</option>
              </select>
            </div>

            {/* Entry */}
            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-2">Entry Price</label>
              <input
                type="number"
                step="0.0001"
                name="entry"
                value={formData.entry}
                onChange={handleInputChange}
                className="w-full bg-slate-900/50 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm"
              />
            </div>

            {/* Target */}
            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-2">Target Price</label>
              <input
                type="number"
                step="0.0001"
                name="target"
                value={formData.target}
                onChange={handleInputChange}
                className="w-full bg-slate-900/50 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm"
              />
            </div>

            {/* Stop Loss */}
            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-2">Stop Loss</label>
              <input
                type="number"
                step="0.0001"
                name="stopLoss"
                value={formData.stopLoss}
                onChange={handleInputChange}
                className="w-full bg-slate-900/50 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm"
              />
            </div>

            {/* Confidence */}
            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-2">Confidence (%)</label>
              <input
                type="number"
                min="0"
                max="100"
                name="confidence"
                value={formData.confidence}
                onChange={handleInputChange}
                className="w-full bg-slate-900/50 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm"
              />
            </div>

            {/* Account Balance */}
            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-2">Account Balance</label>
              <input
                type="number"
                name="accountBalance"
                value={formData.accountBalance}
                onChange={handleInputChange}
                className="w-full bg-slate-900/50 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm"
              />
            </div>

            {/* Risk Percentage */}
            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-2">Risk (%)</label>
              <input
                type="number"
                step="0.1"
                min="0.1"
                max="10"
                name="riskPercentage"
                value={formData.riskPercentage}
                onChange={handleInputChange}
                className="w-full bg-slate-900/50 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm"
              />
            </div>

            {/* Leverage */}
            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-2">Leverage</label>
              <input
                type="number"
                name="leverage"
                value={formData.leverage}
                onChange={handleInputChange}
                className="w-full bg-slate-900/50 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm"
              />
            </div>
          </div>

          {/* Submit Button */}
          <button
            onClick={loadSignal}
            disabled={loading}
            className="mt-4 w-full bg-blue-600 hover:bg-blue-700 disabled:bg-slate-600 text-white font-semibold py-2 rounded-lg transition-all flex items-center justify-center gap-2"
          >
            <RefreshCw className={clsx('w-4 h-4', loading && 'animate-spin')} />
            {loading ? 'Analyzing...' : 'Analyze Trade'}
          </button>
        </motion.div>

        {/* Error Message */}
        {error && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-8 flex items-center gap-2"
          >
            <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
            <p className="text-red-300 text-sm">{error}</p>
          </motion.div>
        )}

        {/* Current Signal */}
        {signal && (
          <div className="mb-8">
            <h2 className="text-2xl font-bold text-white mb-4">Current Analysis</h2>
            <EnhancedSignalCard signal={signal} />
          </div>
        )}

        {/* Historical Signals */}
        {history.length > 0 && (
          <div>
            <h2 className="text-2xl font-bold text-white mb-4">Recent Signals</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {history.map((sig, idx) => (
                <motion.div
                  key={idx}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: idx * 0.1 }}
                  className="bg-slate-800/50 backdrop-blur-xl rounded-lg border border-slate-700/50 p-4"
                >
                  <div className="flex justify-between items-start mb-2">
                    <h3 className="font-bold text-white">{sig.pair}</h3>
                    <span className="text-xs bg-blue-500/20 text-blue-400 px-2 py-1 rounded">
                      {sig.decision}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mb-3">{sig.timestamp}</p>
                  <div className="space-y-1 text-sm">
                    <p className="text-slate-300">Entry: <span className="font-semibold text-white">{sig.price_at_signal}</span></p>
                    <p className="text-slate-300">RR Ratio: <span className="font-semibold text-emerald-400">{sig.rr_ratio.toFixed(2)}</span></p>
                    <p className="text-slate-300">Confidence: <span className="font-semibold text-purple-400">{sig.confidence}%</span></p>
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-700/50 bg-slate-900/50 backdrop-blur-xl mt-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 text-center text-sm text-slate-400">
          <p>Strategic War Room v2.0 - Professional Trading Analytics Dashboard</p>
          <p className="mt-1">Powered by advanced AI analysis and real-time market data</p>
        </div>
      </footer>
    </div>
  )
}
