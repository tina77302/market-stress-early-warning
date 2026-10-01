'use client';

import React, { useEffect, useState } from 'react';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, LineChart, Line, CartesianGrid } from 'recharts';
import { TrendingUp, TrendingDown, AlertTriangle, ShieldCheck, Clock } from 'lucide-react';

interface LatestData {
  last_updated: string;
  spy_price: number;
  vix_level: number;
  hy_spread: number;
  market_stress_index: number;
  risk_probability_10d: number;
  risk_status: string;
}

interface HistoricalPoint {
  date: string;
  spy: number;
  vix: number;
  hy_spread: number;
  msi: number;
  prob_logistic: number;
  prob_xgboost: number;
  target: number;
}

export default function MarketRiskPage() {
  const [latest, setLatest] = useState<LatestData | null>(null);
  const [history, setHistory] = useState<HistoricalPoint[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        const [resLatest, resHist] = await Promise.all([
          fetch('http://127.0.0.1:8000/api/latest'),
          fetch('http://127.0.0.1:8000/api/historical?days=500')
        ]);
        if (resLatest.ok && resHist.ok) {
          const dataLatest = await resLatest.json();
          const dataHist = await resHist.json();
          setLatest(dataLatest);
          setHistory(dataHist.data);
        }
      } catch (err) {
        console.error('API connection failed, loading fallback data', err);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  return (
    <div className="space-y-6">
      {/* Top Ticker Header Bar */}
      <div className="flex items-center justify-between bg-dark-card border border-dark-border p-4 rounded-lg">
        <div className="flex items-center space-x-2 text-xs text-gray-400">
          <Clock className="w-4 h-4 text-gray-500" />
          <span>LAST UPDATED:</span>
          <span className="font-mono text-gray-200">{latest?.last_updated || 'LOADING...'}</span>
        </div>
        <div className="flex items-center space-x-8 text-sm">
          <div>
            <span className="text-gray-400 mr-2">SPY:</span>
            <span className="font-mono font-bold text-white">${latest?.spy_price ?? '---'}</span>
          </div>
          <div>
            <span className="text-gray-400 mr-2">VIX:</span>
            <span className="font-mono font-bold text-financial-amber">{latest?.vix_level ?? '---'}</span>
          </div>
          <div>
            <span className="text-gray-400 mr-2">CREDIT SPREAD:</span>
            <span className="font-mono font-bold text-financial-blue">{latest?.hy_spread ?? '---'}%</span>
          </div>
        </div>
      </div>

      {/* Hero Metric Section: 10D Risk Probability & Status */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Metric 1: 10-Day Risk Probability */}
        <div className="bg-dark-card border border-dark-border p-6 rounded-lg relative overflow-hidden flex flex-col justify-between">
          <div>
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
              10-DAY MARKET STRESS RISK
            </h3>
            <div className="flex items-baseline space-x-3">
              <span className={`text-5xl font-black font-mono ${
                (latest?.risk_probability_10d ?? 0) >= 50 ? 'text-financial-red' : 'text-financial-green'
              }`}>
                {latest?.risk_probability_10d ?? '--'}%
              </span>
              <span className="text-xs text-gray-400">Probability</span>
            </div>
          </div>
          
          <div className="mt-4 pt-4 border-t border-dark-border flex items-center justify-between text-xs">
            <span className="text-gray-400">Status Level:</span>
            <span className={`px-2 py-1 rounded font-bold uppercase ${
              latest?.risk_status === 'HIGH_STRESS' ? 'bg-red-950 text-red-400 border border-red-800' :
              latest?.risk_status === 'ELEVATED_STRESS' ? 'bg-amber-950 text-amber-400 border border-amber-800' :
              'bg-emerald-950 text-emerald-400 border border-emerald-800'
            }`}>
              {latest?.risk_status ?? 'NORMAL'}
            </span>
          </div>
        </div>

        {/* Metric 2: Composite Market Stress Index (MSI) */}
        <div className="bg-dark-card border border-dark-border p-6 rounded-lg flex flex-col justify-between">
          <div>
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
              COMPOSITE MARKET STRESS INDEX (MSI)
            </h3>
            <div className="flex items-baseline space-x-3">
              <span className="text-5xl font-black font-mono text-gray-100">
                {latest?.market_stress_index ?? '0.00'}
              </span>
              <span className="text-xs text-gray-400">Z-Score</span>
            </div>
          </div>
          <p className="text-xs text-gray-500 mt-2">
            Equal-weighted composite of Stock Momentum, Volatility & Credit Spread.
          </p>
        </div>

        {/* Metric 3: System Status & Model Info */}
        <div className="bg-dark-card border border-dark-border p-6 rounded-lg flex flex-col justify-between">
          <div>
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
              ACTIVE AI MODEL ENGINE
            </h3>
            <div className="flex items-center space-x-2 text-lg font-bold text-white mb-1">
              <ShieldCheck className="w-5 h-5 text-financial-green" />
              <span>XGBoost Classifier + Walk-Forward</span>
            </div>
            <p className="text-xs text-gray-400">
              Expanding Window OOS Validated across 2000–2026 dataset.
            </p>
          </div>
          <div className="text-xs text-gray-500">
            Target Horizon: Next 10 Trading Days
          </div>
        </div>
      </div>

      {/* Main Interactive Charts Section */}
      <div className="grid grid-cols-1 gap-6">
        {/* Chart 1: SPY Price Chart & 10D Stress Risk Probability */}
        <div className="bg-dark-card border border-dark-border p-6 rounded-lg space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-gray-200 tracking-wider">
              HISTORICAL 10-DAY OOS RISK PROBABILITY vs S&P 500 (SPY)
            </h3>
            <span className="text-xs text-gray-400">Walk-Forward Out-of-Sample Predictions</span>
          </div>
          <div className="h-[320px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={history}>
                <defs>
                  <linearGradient id="riskGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#F23645" stopOpacity={0.6}/>
                    <stop offset="95%" stopColor="#F23645" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#2A2F3D" />
                <XAxis dataKey="date" stroke="#6B7280" tick={{fontSize: 10}} />
                <YAxis yAxisId="risk" domain={[0, 100]} stroke="#F23645" tick={{fontSize: 10}} unit="%" />
                <YAxis yAxisId="spy" orientation="right" stroke="#2962FF" tick={{fontSize: 10}} domain={['auto', 'auto']} />
                <Tooltip contentStyle={{backgroundColor: '#151921', borderColor: '#2A2F3D', color: '#fff'}} />
                <Area yAxisId="risk" type="monotone" dataKey="prob_xgboost" name="10D Risk Prob (%)" stroke="#F23645" fillOpacity={1} fill="url(#riskGrad)" />
                <Line yAxisId="spy" type="monotone" dataKey="spy" name="SPY Price ($)" stroke="#2962FF" dot={false} strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Chart 2: Composite Market Stress Index (MSI) */}
        <div className="bg-dark-card border border-dark-border p-6 rounded-lg space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-gray-200 tracking-wider">
              MARKET STRESS INDEX (MSI) & ACTUAL STRESS EVENTS
            </h3>
            <span className="text-xs text-gray-400">Top 10% Percentile Events Flagged</span>
          </div>
          <div className="h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={history}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2A2F3D" />
                <XAxis dataKey="date" stroke="#6B7280" tick={{fontSize: 10}} />
                <YAxis stroke="#9CA3AF" tick={{fontSize: 10}} />
                <Tooltip contentStyle={{backgroundColor: '#151921', borderColor: '#2A2F3D', color: '#fff'}} />
                <Line type="monotone" dataKey="msi" name="MSI Z-Score" stroke="#F59E0B" dot={false} strokeWidth={1.5} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}
