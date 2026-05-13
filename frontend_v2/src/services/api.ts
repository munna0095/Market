import axios from 'axios'
import type { EnhancedSignal, HistoricalSignal } from '../types'

const API_BASE = 'http://localhost:8000'

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
})

/**
 * Calculate enhanced signal with all metrics
 */
export async function getEnhancedSignal(
  pair: string,
  entry: number,
  target: number,
  stopLoss: number,
  confidence: number,
  accountBalance: number = 10000,
  riskPercentage: number = 2.0,
  leverage: number = 100
): Promise<EnhancedSignal> {
  const response = await api.post('/api/calculate/enhanced-signal', {
    pair,
    entry,
    target,
    stop_loss: stopLoss,
    confidence,
    account_balance: accountBalance,
    risk_percentage: riskPercentage,
    leverage,
  })
  return response.data
}

/**
 * Get historical signals with enhanced calculations
 */
export async function getEnhancedSignalsHistory(
  limit: number = 10
): Promise<HistoricalSignal[]> {
  const response = await api.get('/api/signals/enhanced-history', {
    params: { limit },
  })
  return response.data
}

/**
 * Get current prices for multiple pairs
 */
export async function getPrices(pairs: string[]): Promise<Record<string, number>> {
  const response = await api.get('/api/prices', {
    params: { pairs: pairs.join(',') },
  })
  return response.data
}

/**
 * Health check
 */
export async function healthCheck(): Promise<boolean> {
  try {
    const response = await api.get('/')
    return response.status === 200
  } catch {
    return false
  }
}
