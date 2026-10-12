'use client';

import React, { useEffect, useState } from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  LineChart,
  Line,
  CartesianGrid,
} from 'recharts';
import { Activity, Clock, Database, ShieldCheck } from 'lucide-react';

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

interface LatestData {
  market: string;
  last_updated: string;
  kospi200: number;
  vkospi: number;
  korea_credit_spread: number;
  korea_credit_spread_bp: number;
  market_stress_index: number;
  stress_threshold: number;
  is_stress_event: boolean;
  risk_score_10d: number;
  warning_threshold: number;
  warning_active: boolean;
}

interface HistoricalPoint {
  date: string;
  kospi200: number;
  vkospi: number;
  spread: number;
  spread_bp: number;
  msi: number;
  risk_score_logistic: number;
  risk_score_xgboost: number;
  target: number;
}

interface ShapDriver {
  feature: string;
  feature_value: number;
  shap_value: number;
  direction: 'risk_up' | 'risk_down';
}

interface ShapData {
  date: string;
  market: string;
  model: string;
  target_horizon: string;
  feature_count: number;
  top_drivers: ShapDriver[];
  interpretation_note: string;
}

export default function KoreaMarketRiskPage() {
  const [latest, setLatest] = useState<LatestData | null>(null);
  const [history, setHistory] = useState<HistoricalPoint[]>([]);
  const [shapData, setShapData] = useState<ShapData | null>(null);
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState(false);
  const [timeRange, setTimeRange] =
    useState<'1Y' | '3Y' | '5Y' | 'ALL'>('3Y');

  useEffect(() => {
    async function fetchData() {
      try {
        const [a, b, c] = await Promise.all([
          fetch(`${API_URL}/api/korea/latest`),
          fetch(`${API_URL}/api/korea/historical?days=10000`),
          fetch(`${API_URL}/api/korea/shap`),
        ]);

        if (!a.ok || !b.ok || !c.ok) throw new Error('Korea API failed');

        const [latestData, histData, shap] = await Promise.all([
          a.json(),
          b.json(),
          c.json(),
        ]);

        setLatest(latestData);
        setHistory(histData.data ?? []);
        setShapData(shap);
        setApiError(false);
      } catch (e) {
        console.error(e);
        setApiError(true);
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, []);

  const filteredHistory = React.useMemo(() => {
    if (timeRange === 'ALL' || !history.length) return history;

    const end = new Date(history[history.length - 1].date);
    const start = new Date(end);
    const years = timeRange === '1Y' ? 1 : timeRange === '3Y' ? 3 : 5;
    start.setFullYear(start.getFullYear() - years);

    return history.filter((x) => new Date(x.date) >= start);
  }, [history, timeRange]);

  const featureLabel = (feature: string) => {
    const labels: Record<string, string> = {
      KOSPI200_1D_Return: 'KOSPI 200 1D Return',
      KOSPI200_5D_Return: 'KOSPI 200 5D Return',
      KOSPI200_20D_Return: 'KOSPI 200 20D Return',
      KOSPI200_20D_Vol: 'KOSPI 200 20D Volatility',
      KOSPI200_60D_Vol: 'KOSPI 200 60D Volatility',
      KOSPI200_Drawdown: 'KOSPI 200 Drawdown',
      KOSPI200_20D_Momentum: 'KOSPI 200 20D Momentum',
      VKOSPI_Level: 'VKOSPI Level',
      VKOSPI_1D_Change: 'VKOSPI 1D Change',
      VKOSPI_5D_Change: 'VKOSPI 5D Change',
      VKOSPI_20D_Momentum: 'VKOSPI 20D Momentum',
      VKOSPI_252D_ZScore: 'VKOSPI Relative Level',
      Credit_Level: 'Credit Spread Level',
      Credit_1D_Change: 'Credit Spread 1D Change',
      Credit_5D_Change: 'Credit Spread 5D Change',
      Credit_20D_Momentum: 'Credit Spread Momentum',
      Credit_252D_ZScore: 'Credit Spread Relative Level',
    };

    return labels[feature] ?? feature.replaceAll('_', ' ');
  };

  const up =
    shapData?.top_drivers.filter((x) => x.direction === 'risk_up') ?? [];

  const down =
    shapData?.top_drivers.filter((x) => x.direction === 'risk_down') ?? [];

  const warning =
    latest?.warning_active ??
    (latest
      ? latest.risk_score_10d >= latest.warning_threshold
      : false);

  if (loading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="text-sm text-gray-400 font-mono">
          LOADING KOREA MARKET RISK DATA...
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">

      <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-4 bg-dark-card border border-dark-border p-4 rounded-lg">
        <div className="flex items-center space-x-2 text-xs text-gray-400">
          <Clock className="w-4 h-4" />
          <span>KOREA · LAST MARKET OBSERVATION:</span>
          <span className="font-mono text-gray-200">
            {latest?.last_updated ?? '---'}
          </span>

          {apiError && (
            <span className="text-financial-red">KOREA API OFFLINE</span>
          )}
        </div>

        <div className="flex flex-wrap gap-8 text-sm">

          <div>
            <span className="text-gray-400 mr-2">KOSPI 200</span>
            <span className="font-mono font-bold text-white">
              {latest?.kospi200?.toLocaleString() ?? '---'}
            </span>
          </div>

          <div>
            <span className="text-gray-400 mr-2">VKOSPI</span>
            <span className="font-mono font-bold text-financial-amber">
              {latest?.vkospi?.toFixed(2) ?? '---'}
            </span>
          </div>

          <div>
            <span className="text-gray-400 mr-2">
              AA− CORP − GOVT 3Y
            </span>
            <span className="font-mono font-bold text-financial-blue">
              {latest?.korea_credit_spread_bp?.toFixed(1) ?? '---'} bp
            </span>
          </div>

        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        <div className="bg-dark-card border border-dark-border p-6 rounded-lg">
          <div className="flex justify-between">
            <h3 className="text-xs text-gray-400 uppercase">
              10-Day Market Stress Risk
            </h3>
            <Activity className="w-4 h-4 text-financial-green" />
          </div>

          <div className="flex items-center gap-3 mt-4">
            <span className="text-5xl font-black font-mono">
              {latest?.risk_score_10d ?? '--'}
            </span>
            <span className="text-gray-500">/ 100</span>

            <span
              className={`text-xs font-bold border rounded px-3 py-1 ${
                warning
                  ? 'text-financial-red border-financial-red/40'
                  : 'text-financial-green border-financial-green/40'
              }`}
            >
              {warning ? 'WARNING ACTIVE' : 'BELOW WARNING'}
            </span>
          </div>

          <p className="text-xs text-gray-500 mt-5">
            Fixed warning reference: {latest?.warning_threshold ?? 50}/100.
            This score is not a calibrated event probability.
          </p>
        </div>

        <div className="bg-dark-card border border-dark-border p-6 rounded-lg">
          <h3 className="text-xs text-gray-400 uppercase">
            Korea Market Stress Index
          </h3>

          <div className="text-5xl font-black font-mono mt-4">
            {latest?.market_stress_index?.toFixed(3) ?? '--'}
          </div>

          <div className="mt-5 text-xs text-gray-500 space-y-2">
            <div>
              Stress Threshold:{' '}
              <span className="text-gray-300 font-mono">
                {latest?.stress_threshold?.toFixed(3) ?? '---'}
              </span>
            </div>

            <div>
              Current Stress Event:{' '}
              <span
                className={
                  latest?.is_stress_event
                    ? 'text-financial-red'
                    : 'text-emerald-400'
                }
              >
                {latest?.is_stress_event ? 'YES' : 'NO'}
              </span>
            </div>
          </div>
        </div>

        <div className="bg-dark-card border border-dark-border p-6 rounded-lg">
          <h3 className="text-xs text-gray-400 uppercase">
            Deployment Model
          </h3>

          <div className="flex items-center gap-2 mt-4 text-lg font-bold">
            <ShieldCheck className="w-5 h-5" />
            XGBoost · Korea
          </div>

          <div className="mt-5 text-xs text-gray-500 space-y-1">
            <div>Forecast Horizon: 10 Trading Days</div>
            <div>Validation: Purged Walk-Forward OOS</div>
            <div>Warning Reference: 50 / 100</div>
          </div>
        </div>

      </div>

      <div className="bg-dark-card border border-dark-border p-6 rounded-lg">
        <h3 className="text-sm font-bold text-gray-200">
          KOREA MARKET STRESS DRIVERS
        </h3>

        <p className="text-xs text-gray-500 mt-1 mb-4">
          VKOSPI and Korean credit-market conditions
        </p>

        <div className="h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={filteredHistory}>

              <CartesianGrid strokeDasharray="3 3" stroke="#2A2F3D" />

              <XAxis
                dataKey="date"
                stroke="#6B7280"
                tick={{ fontSize: 10 }}
              />

              <YAxis
                yAxisId="v"
                stroke="#F59E0B"
                tick={{ fontSize: 10 }}
              />

              <YAxis
                yAxisId="c"
                orientation="right"
                stroke="#A78BFA"
                tick={{ fontSize: 10 }}
              />

              <Tooltip />

              <Line
                yAxisId="v"
                dataKey="vkospi"
                name="VKOSPI"
                stroke="#F59E0B"
                dot={false}
              />

              <Line
                yAxisId="c"
                dataKey="spread_bp"
                name="Credit Spread (bp)"
                stroke="#A78BFA"
                dot={false}
              />

            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="bg-dark-card border border-dark-border p-6 rounded-lg">
        <h3 className="text-sm font-bold text-gray-200">
          KOREA MODEL RISK DRIVERS
        </h3>

        <p className="text-xs text-gray-500 mt-1 mb-5">
          Latest XGBoost explanation using SHAP
        </p>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

          <div className="border border-dark-border rounded-lg p-4">
            <div className="text-financial-red text-xs font-bold mb-4">
              RISK INCREASING
            </div>

            <div className="space-y-3">
              {up.map((x) => (
                <div
                  key={x.feature}
                  className="flex justify-between text-xs"
                >
                  <span>{featureLabel(x.feature)}</span>
                  <span className="text-financial-red font-mono">
                    ↑ {Math.abs(x.shap_value).toFixed(3)}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="border border-dark-border rounded-lg p-4">
            <div className="text-emerald-400 text-xs font-bold mb-4">
              RISK REDUCING
            </div>

            <div className="space-y-3">
              {down.map((x) => (
                <div
                  key={x.feature}
                  className="flex justify-between text-xs"
                >
                  <span>{featureLabel(x.feature)}</span>
                  <span className="text-emerald-400 font-mono">
                    ↓ {Math.abs(x.shap_value).toFixed(3)}
                  </span>
                </div>
              ))}
            </div>
          </div>

        </div>

        <div className="flex gap-2 text-[11px] text-gray-500 mt-5">
          <Database className="w-4 h-4" />
          SHAP values represent model-output contributions, not probability-point changes.
        </div>
      </div>

      <div className="bg-dark-card border border-dark-border p-6 rounded-lg">

        <div className="flex justify-between mb-4">

          <div>
            <h3 className="text-sm font-bold text-gray-200">
              HISTORICAL 10-DAY OOS RISK SCORE vs KOSPI 200
            </h3>

            <p className="text-xs text-gray-500 mt-1">
              Korea XGBoost walk-forward OOS scores
            </p>
          </div>

          <div className="flex gap-1">
            {(['1Y','3Y','5Y','ALL'] as const).map((r) => (
              <button
                key={r}
                onClick={() => setTimeRange(r)}
                className={`px-3 py-1 text-xs rounded ${
                  timeRange === r
                    ? 'bg-gray-700 text-white'
                    : 'text-gray-500'
                }`}
              >
                {r}
              </button>
            ))}
          </div>

        </div>

        <div className="h-[340px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={filteredHistory}>

              <CartesianGrid strokeDasharray="3 3" stroke="#2A2F3D" />

              <XAxis
                dataKey="date"
                stroke="#6B7280"
                tick={{ fontSize: 10 }}
              />

              <YAxis
                yAxisId="risk"
                domain={[0,100]}
                stroke="#F23645"
              />

              <YAxis
                yAxisId="kospi"
                orientation="right"
                stroke="#2962FF"
              />

              <Tooltip />

              <Area
                yAxisId="risk"
                dataKey="risk_score_xgboost"
                name="10D Risk Score"
                stroke="#F23645"
                fill="#F23645"
                fillOpacity={0.15}
              />

              <Line
                yAxisId="kospi"
                dataKey="kospi200"
                name="KOSPI 200"
                stroke="#2962FF"
                dot={false}
              />

            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="bg-dark-card border border-dark-border p-6 rounded-lg">
        <h3 className="text-sm font-bold text-gray-200">
          KOREA MARKET STRESS INDEX
        </h3>

        <p className="text-xs text-gray-500 mt-1 mb-4">
          KOSPI 200 + VKOSPI + Korean credit stress composite
        </p>

        <div className="h-[240px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={filteredHistory}>

              <CartesianGrid strokeDasharray="3 3" stroke="#2A2F3D" />

              <XAxis
                dataKey="date"
                stroke="#6B7280"
                tick={{ fontSize: 10 }}
              />

              <YAxis stroke="#9CA3AF" />

              <Tooltip />

              <Line
                dataKey="msi"
                name="Korea Market Stress Index"
                stroke="#22D3EE"
                dot={false}
              />

            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

    </div>
  );
}
