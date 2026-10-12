'use client';

import { useEffect, useState } from 'react';
export type Market = 'us' | 'korea';
export interface InputHealth { series: string; provider: string; status: string; latest_observation_date: string | null; retrieved_at: string | null; attempt_count: number }
export interface DataHealth { status: string; is_current: boolean; expected_observation_date: string | null; input_series: InputHealth[]; last_job?: {status: string; error_message?: string | null} | null }
export interface Latest {
  data_health?: DataHealth;
  last_updated?: string;
  risk_score_10d?: number | null;
  market_stress_index?: number | null;
  spy_price?: number | null;
  vix_level?: number | null;
  baa_treasury_spread?: number | null;
  kospi200?: number | null;
  vkospi?: number | null;
  korea_credit_spread_bp?: number | null;
  warning_active?: boolean;
  warning_threshold?: number | null;
  stress_threshold?: number | null;
  is_stress_event?: boolean;
}
export interface HistoryPoint {
  date: string;
  [field: string]: string | number | null;
}
export interface Driver { feature: string; feature_value?: number | null; shap_value: number; direction?: string }
export interface Shap { date?: string; model?: string; feature_count?: number; top_drivers: Driver[] }
export const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
export const fmt = (value: unknown, digits = 2, suffix = '') => finite(value) ? `${value.toFixed(digits)}${suffix}` : '—';
export function signal(market: Market, latest: Latest | null) {
  const score = latest?.risk_score_10d;
  if (!latest?.data_health?.is_current || !finite(score)) return 'UNAVAILABLE';
  if (market === 'korea') return (typeof latest?.warning_active === 'boolean' ? latest.warning_active : score >= 50) ? 'WARNING' : 'BELOW WARNING';
  return score >= 70 ? 'HIGH' : score >= 50 ? 'ELEVATED' : score >= 30 ? 'WATCH' : 'LOW';
}
export const tone = (status: string) => status === 'UNAVAILABLE' ? 'muted' : ['HIGH', 'ELEVATED', 'WARNING'].includes(status) ? 'red' : status === 'WATCH' ? 'amber' : 'green';
export function useMarket(market: Market) {
  const [latest, setLatest] = useState<Latest | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [shap, setShap] = useState<Shap | null>(null);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<string[]>([]);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const prefix = market === 'korea' ? '/api/korea' : '/api';
    const base = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
    setLoading(true);
    async function request(path: string) {
      const response = await fetch(`${base}${prefix}/${path}`, { signal: controller.signal });
      if (!response.ok) throw new Error(path);
      return response.json();
    }
    void Promise.allSettled([request('latest'), request('historical?days=10000'), request('shap')]).then(([current, historical, drivers]) => {
      if (controller.signal.aborted) return;
      setLatest(current.status === 'fulfilled' ? current.value : null);
      const rows: HistoryPoint[] = historical.status === 'fulfilled' && Array.isArray(historical.value.data) ? historical.value.data : [];
      setHistory(rows.filter(row => typeof row.date === 'string').map(row => Object.fromEntries(Object.entries(row).map(([key, value]) => [key, typeof value === 'number' && !finite(value) ? null : value])) as HistoryPoint).sort((a, b) => a.date.localeCompare(b.date)));
      setShap(drivers.status === 'fulfilled' && current.status === 'fulfilled' && drivers.value.date === current.value.last_updated && Array.isArray(drivers.value.top_drivers) ? { ...drivers.value, top_drivers: drivers.value.top_drivers.filter((driver: Driver) => typeof driver.feature === 'string' && finite(driver.shap_value)) } : null);
      setErrors([current, historical, drivers].flatMap((result, index) => result.status === 'rejected' ? [['Current snapshot', 'History', 'SHAP drivers'][index]] : []));
      setLoading(false);
    });
    return () => controller.abort();
  }, [market, refresh]);
  return { latest, history, shap, loading, errors, retry: () => setRefresh(value => value + 1) };
}
