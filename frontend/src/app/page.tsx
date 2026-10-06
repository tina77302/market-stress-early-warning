'use client';

import React, { useEffect, useState } from 'react';
import {
  ResponsiveContainer,
  AreaChart,
  ComposedChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  LineChart,
  Line,
  CartesianGrid,
} from 'recharts';
import {
  Activity,
  Clock,
  Database,
  ShieldCheck,
} from 'lucide-react';


const API_URL =
  process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

interface LatestData {
  last_updated: string;
  spy_price: number;
  vix_level: number;
  baa_treasury_spread: number;
  market_stress_index: number;
  risk_score_10d: number;
  risk_score_note: string;
}


interface HistoricalPoint {
  date: string;
  spy: number;
  vix: number;
  baa_treasury_spread: number;
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
  model: string;
  feature_count: number;
  top_drivers: ShapDriver[];
  interpretation_note: string;
}


export default function MarketRiskPage() {
  const [latest, setLatest] = useState<LatestData | null>(null);
  const [history, setHistory] = useState<HistoricalPoint[]>([]);
  const [shapData, setShapData] = useState<ShapData | null>(null);
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState(false);
  const [timeRange, setTimeRange] = useState<'1Y' | '3Y' | '5Y' | 'ALL'>('3Y');

  const filteredHistory = React.useMemo(() => {
    if (timeRange === 'ALL') return history;
    if (history.length === 0) return [];

    const lastDate = new Date(history[history.length - 1].date);
    const startDate = new Date(lastDate);

    const years =
      timeRange === '1Y' ? 1 :
      timeRange === '3Y' ? 3 :
      5;

    startDate.setFullYear(startDate.getFullYear() - years);

    return history.filter(
      (point) => new Date(point.date) >= startDate
    );
  }, [history, timeRange]);


  useEffect(() => {
    async function fetchData() {
      try {
        const [resLatest, resHist, resShap] = await Promise.all([
          fetch(`${API_URL}/api/latest`),
          fetch(`${API_URL}/api/historical?days=10000`),
          fetch(`${API_URL}/api/shap`),
        ]);

        if (!resLatest.ok || !resHist.ok || !resShap.ok) {
          throw new Error('API request failed');
        }

        const dataLatest = await resLatest.json();
        const dataHist = await resHist.json();
        const dataShap = await resShap.json();

        setLatest(dataLatest);
        setHistory(dataHist.data);
        setShapData(dataShap);
        setApiError(false);
      } catch (err) {
        console.error('API connection failed', err);
        setApiError(true);
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, []);


  const featureLabel = (feature: string) => {
    const labels: Record<string, string> = {
      VIX_252D_ZScore: 'VIX Relative Level',
      Credit_252D_ZScore: 'Credit Spread Relative Level',
      SPY_Drawdown: 'SPY Drawdown',
      SPY_20D_Vol: 'SPY 20D Volatility',
      Credit_Level: 'Credit Spread Level',
      SPY_20D_Momentum: 'SPY 20D Momentum',
      SPY_20D_Return: 'SPY 20D Return',
      Credit_20D_Momentum: 'Credit Spread Momentum',
      SPY_60D_Vol: 'SPY 60D Volatility',
      VIX_20D_Momentum: 'VIX 20D Momentum',
    };

    return labels[feature] ?? feature.replaceAll('_', ' ');
  };

  const riskIncreasing =
    shapData?.top_drivers.filter(
      (driver) => driver.direction === 'risk_up'
    ) ?? [];

  const riskReducing =
    shapData?.top_drivers.filter(
      (driver) => driver.direction === 'risk_down'
    ) ?? [];


  if (loading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="text-sm text-gray-400 font-mono">
          LOADING MARKET RISK DATA...
        </div>
        {/* ==================================================
            Market Stress Drivers
        ================================================== */}

        <div className="bg-dark-card border border-dark-border p-6 rounded-lg space-y-4">

          <div className="flex flex-col md:flex-row md:items-center justify-between gap-2">

            <div>
              <h3 className="text-sm font-bold text-gray-200 tracking-wider">
                MARKET STRESS DRIVERS
              </h3>

              <p className="text-xs text-gray-500 mt-1">
                Volatility and credit-market conditions
              </p>
            </div>

            <div className="flex items-center gap-4 text-[11px] font-mono">
              <span className="flex items-center gap-1.5 text-gray-400">
                <span className="inline-block w-3 h-[2px] bg-[#F59E0B]" />
                VIX
              </span>

              <span className="flex items-center gap-1.5 text-gray-400">
                <span className="inline-block w-3 h-[2px] bg-[#A78BFA]" />
                BAA-Treasury Spread
              </span>
            </div>

          </div>

          <div className="h-[260px]">

            <ResponsiveContainer width="100%" height="100%">

              <ComposedChart data={filteredHistory}>

                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="#2A2F3D"
                />

                <XAxis
                  dataKey="date"
                  stroke="#6B7280"
                  tick={{ fontSize: 10 }}
                />

                <YAxis
                  yAxisId="vix"
                  stroke="#F59E0B"
                  tick={{ fontSize: 10, fill: '#F59E0B' }}
                  domain={['auto', 'auto']}
                />

                <YAxis
                  yAxisId="credit"
                  orientation="right"
                  stroke="#A78BFA"
                  tick={{ fontSize: 10, fill: '#A78BFA' }}
                  domain={['auto', 'auto']}
                />

                <Tooltip
                  contentStyle={{
                    backgroundColor: '#151921',
                    borderColor: '#2A2F3D',
                    color: '#fff',
                  }}
                />

                <Line
                  yAxisId="vix"
                  type="monotone"
                  dataKey="vix"
                  name="VIX"
                  stroke="#F59E0B"
                  dot={false}
                  strokeWidth={1.8}
                  isAnimationActive={false}
                />

                <Line
                  yAxisId="credit"
                  type="monotone"
                  dataKey="baa_treasury_spread"
                  name="BAA-Treasury Spread"
                  stroke="#A78BFA"
                  dot={false}
                  strokeWidth={1.8}
                  isAnimationActive={false}
                />

              </ComposedChart>

            </ResponsiveContainer>

          </div>

          <div className="flex items-center gap-2 text-[11px] text-gray-500">
            <Database className="w-3.5 h-3.5" />

            <span>
              VIX captures equity-market volatility while the BAA-Treasury spread
              serves as the long-history credit-stress proxy.
            </span>
          </div>

        </div>

      </div>
    );
  }


  return (
    <div className="space-y-6">

      {/* ==================================================
          Header / Market Snapshot
      ================================================== */}

      <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-4 bg-dark-card border border-dark-border p-4 rounded-lg">

        <div className="flex items-center space-x-2 text-xs text-gray-400">
          <Clock className="w-4 h-4 text-gray-500" />

          <span>LAST MARKET OBSERVATION:</span>

          <span className="font-mono text-gray-200">
            {latest?.last_updated ?? '---'}
          </span>

          {apiError && (
            <span className="ml-3 text-financial-red">
              API OFFLINE
            </span>
          )}
        </div>


        <div className="flex flex-wrap items-center gap-x-8 gap-y-2 text-sm">

          <div>
            <span className="text-gray-400 mr-2">
              SPY
            </span>

            <span className="font-mono font-bold text-white">
              ${latest?.spy_price ?? '---'}
            </span>
          </div>


          <div>
            <span className="text-gray-400 mr-2">
              VIX
            </span>

            <span className="font-mono font-bold text-financial-amber">
              {latest?.vix_level ?? '---'}
            </span>
          </div>


          <div>
            <span className="text-gray-400 mr-2">
              BAA–TREASURY
            </span>

            <span className="font-mono font-bold text-financial-blue">
              {latest?.baa_treasury_spread ?? '---'}%
            </span>
          </div>

        </div>
      </div>


      {/* ==================================================
          Main Metrics
      ================================================== */}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* 10-Day Risk Score */}

        <div className="bg-dark-card border border-dark-border p-6 rounded-lg flex flex-col justify-between">

          <div>
            <div className="flex items-center justify-between mb-3">

              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                10-Day Market Stress Risk Score
              </h3>

              <Activity className="w-4 h-4 text-financial-red" />
            </div>


            <div className="flex items-baseline space-x-2">

              <span className="text-5xl font-black font-mono text-gray-100">
                {latest?.risk_score_10d ?? '--'}
              </span>

              <span className="text-sm text-gray-500">
                / 100
              </span>

            </div>
          </div>


          <div className="mt-5 pt-4 border-t border-dark-border">

            <p className="text-xs leading-relaxed text-gray-500">
              Model-estimated stress risk score for the next
              10 trading days. The score is not interpreted as
              a calibrated event probability.
            </p>

          </div>
        </div>


        {/* MSI */}

        <div className="bg-dark-card border border-dark-border p-6 rounded-lg flex flex-col justify-between">

          <div>
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
              Market Stress Index
            </h3>

            <div className="flex items-baseline space-x-3">

              <span className="text-5xl font-black font-mono text-gray-100">
                {latest?.market_stress_index ?? '--'}
              </span>

              <span className="text-xs text-gray-500">
                Composite Score
              </span>

            </div>
          </div>


          <p className="text-xs text-gray-500 mt-5">
            Equal-weighted composite of equity,
            volatility and credit stress.
          </p>

        </div>


        {/* Model Engine */}

        <div className="bg-dark-card border border-dark-border p-6 rounded-lg flex flex-col justify-between">

          <div>

            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
              Deployment Model
            </h3>


            <div className="flex items-center space-x-2 text-lg font-bold text-white">

              <ShieldCheck className="w-5 h-5 text-gray-400" />

              <span>
                XGBoost
              </span>

            </div>


            <p className="text-xs text-gray-400 mt-2">
              Deployment model trained on currently
              observable labeled data.
            </p>

          </div>


          <div className="pt-4 mt-4 border-t border-dark-border text-xs text-gray-500 space-y-1">

            <div>
              Forecast Horizon: 10 Trading Days
            </div>

            <div>
              Validation: Purged Walk-Forward OOS
            </div>

          </div>

        </div>

      </div>


      {/* ==================================================
          Model Risk Drivers - SHAP
      ================================================== */}

      <div className="bg-dark-card border border-dark-border p-6 rounded-lg space-y-5">

        <div className="flex flex-col md:flex-row md:items-center justify-between gap-2">
          <div>
            <h3 className="text-sm font-bold text-gray-200 tracking-wider">
              MODEL RISK DRIVERS
            </h3>

            <p className="text-xs text-gray-500 mt-1">
              Latest XGBoost explanation using SHAP
            </p>
          </div>

          <div className="text-[11px] font-mono text-gray-500">
            {shapData
              ? `${shapData.date} · ${shapData.feature_count} FEATURES`
              : 'SHAP DATA UNAVAILABLE'}
          </div>
        </div>


        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

          <div className="border border-dark-border rounded-lg p-4">
            <div className="text-[11px] font-semibold tracking-wider text-financial-red mb-4">
              RISK INCREASING
            </div>

            <div className="space-y-3">
              {riskIncreasing.length > 0 ? (
                riskIncreasing.map((driver) => (
                  <div
                    key={driver.feature}
                    className="flex items-center justify-between gap-4"
                  >
                    <span className="text-xs text-gray-300">
                      {featureLabel(driver.feature)}
                    </span>

                    <span className="text-xs font-mono text-financial-red">
                      ↑
                    </span>
                  </div>
                ))
              ) : (
                <div className="text-xs text-gray-500">
                  No increasing drivers among the leading SHAP factors.
                </div>
              )}
            </div>
          </div>


          <div className="border border-dark-border rounded-lg p-4">
            <div className="text-[11px] font-semibold tracking-wider text-emerald-400 mb-4">
              RISK REDUCING
            </div>

            <div className="space-y-3">
              {riskReducing.length > 0 ? (
                riskReducing.map((driver) => (
                  <div
                    key={driver.feature}
                    className="flex items-center justify-between gap-4"
                  >
                    <span className="text-xs text-gray-300">
                      {featureLabel(driver.feature)}
                    </span>

                    <span className="text-xs font-mono text-emerald-400">
                      ↓
                    </span>
                  </div>
                ))
              ) : (
                <div className="text-xs text-gray-500">
                  No reducing drivers among the leading SHAP factors.
                </div>
              )}
            </div>
          </div>

        </div>


        <div className="flex items-start gap-2 text-[11px] leading-relaxed text-gray-500">
          <Database className="w-3.5 h-3.5 mt-0.5 shrink-0" />

          <span>
            SHAP explains the direction and relative contribution of each
            feature to the latest XGBoost risk score. Contributions are
            model-output effects, not percentage-point changes in event probability.
          </span>
        </div>

      </div>


      {/* ==================================================
          Historical OOS Risk
      ================================================== */}

      <div className="bg-dark-card border border-dark-border p-6 rounded-lg space-y-4">

        <div className="flex flex-col md:flex-row md:items-center justify-between gap-2">

          <div>
            <h3 className="text-sm font-bold text-gray-200 tracking-wider">
              HISTORICAL 10-DAY OOS RISK SCORE vs SPY
            </h3>

            <p className="text-xs text-gray-500 mt-1">
              XGBoost walk-forward out-of-sample scores
            </p>
          </div>


          <div className="flex items-center gap-4">
            <div className="hidden lg:flex items-center gap-4 text-[11px] font-mono">
              <span className="flex items-center gap-1.5 text-gray-400">
                <span className="inline-block w-3 h-[2px] bg-[#F23645]" />
                10D Risk Score
              </span>
              <span className="flex items-center gap-1.5 text-gray-400">
                <span className="inline-block w-3 h-[2px] bg-[#4DA3FF]" />
                SPY Price
              </span>
            </div>

            <div className="flex items-center gap-1 bg-dark-bg border border-dark-border rounded p-1">
              {(['1Y', '3Y', '5Y', 'ALL'] as const).map((range) => (
              <button
                key={range}
                onClick={() => setTimeRange(range)}
                className={`px-3 py-1.5 rounded text-[11px] font-mono transition-colors ${
                  timeRange === range
                    ? 'bg-gray-700 text-white'
                    : 'text-gray-500 hover:text-gray-200'
                }`}
              >
                {range}
              </button>
              ))}
            </div>
          </div>

        </div>


        <div className="h-[340px]">

          <ResponsiveContainer width="100%" height="100%">

            <ComposedChart data={filteredHistory}>

              <defs>
                <linearGradient
                  id="riskGrad"
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop
                    offset="5%"
                    stopColor="#F23645"
                    stopOpacity={0.55}
                  />

                  <stop
                    offset="95%"
                    stopColor="#F23645"
                    stopOpacity={0}
                  />
                </linearGradient>
              </defs>


              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#2A2F3D"
              />


              <XAxis
                dataKey="date"
                stroke="#6B7280"
                tick={{ fontSize: 10 }}
              />


              <YAxis
                yAxisId="risk"
                domain={[0, 100]}
                stroke="#F23645"
                tick={{ fontSize: 10 }}
              />


              <YAxis
                yAxisId="spy"
                orientation="right"
                stroke="#2962FF"
                tick={{ fontSize: 10 }}
                domain={['auto', 'auto']}
              />


              <Tooltip
                contentStyle={{
                  backgroundColor: '#151921',
                  borderColor: '#2A2F3D',
                  color: '#fff',
                }}
              />


              <Area
                yAxisId="risk"
                type="monotone"
                dataKey="risk_score_xgboost"
                name="10D Risk Score"
                stroke="#F23645"
                fillOpacity={1}
                fill="url(#riskGrad)"
              />


              <Line
                yAxisId="spy"
                type="monotone"
                dataKey="spy"
                name="SPY Price"
                stroke="#2962FF"
                dot={false}
                strokeWidth={2}
              />

            </ComposedChart>

          </ResponsiveContainer>

        </div>


        <div className="flex items-center gap-2 text-[11px] text-gray-500">

          <Database className="w-3.5 h-3.5" />

          <span>
            Historical scores are generated strictly from
            walk-forward out-of-sample predictions.
          </span>

        </div>

      </div>


      {/* ==================================================
          MSI History
      ================================================== */}

      <div className="bg-dark-card border border-dark-border p-6 rounded-lg space-y-4">

        <div className="flex flex-col md:flex-row md:items-center justify-between gap-2">

          <div>

            <h3 className="text-sm font-bold text-gray-200 tracking-wider">
              MARKET STRESS INDEX
            </h3>

            <p className="text-xs text-gray-500 mt-1">
              Equity + volatility + credit stress composite
            </p>

          </div>


          <span className="text-xs text-gray-400">
            Historical OOS window
          </span>

        </div>


        <div className="h-[240px]">

          <ResponsiveContainer width="100%" height="100%">

            <LineChart data={filteredHistory}>

              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#2A2F3D"
              />


              <XAxis
                dataKey="date"
                stroke="#6B7280"
                tick={{ fontSize: 10 }}
              />


              <YAxis
                stroke="#9CA3AF"
                tick={{ fontSize: 10 }}
              />


              <Tooltip
                contentStyle={{
                  backgroundColor: '#151921',
                  borderColor: '#2A2F3D',
                  color: '#fff',
                }}
              />


              <Line
                type="monotone"
                dataKey="msi"
                name="Market Stress Index"
                stroke="#22D3EE"
                dot={false}
                strokeWidth={1.5}
              />

            </LineChart>

          </ResponsiveContainer>

        </div>

      </div>

    </div>
  );
}