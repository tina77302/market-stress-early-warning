'use client';

import React, { useEffect, useState } from 'react';
import { BarChart3 } from 'lucide-react';
import {
  ComposedChart,
  LineChart,
  Area,
  Line,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

interface MetricRow {
  Model: string;
  'ROC-AUC': number;
  'PR-AUC (AP)': number;
  'Brier Score': number;
  Threshold: number;
  TP: number;
  FP: number;
  TN: number;
  FN: number;
  Precision: number;
  Recall: number;
  F1: number;
  'False Alarm Rate': number;
  'Missed Event Rate': number;
}

interface EventRow {
  Event: string;
  Start: string;
  End: string;
  Days: number;
  'Actual Stress Days': number;
  'Logistic Avg Prob': number;
  'Logistic Max Prob': number;
  'Logistic >= 0.5 Days': number;
  'XGB Avg Prob': number;
  'XGB Max Prob': number;
  'XGB >= 0.5 Days': number;
}

interface HistoricalRow {
  date: string;
  spy: number;
  risk_score_xgboost: number;
  risk_score_logistic: number;
  target: number;
}
const fmt = (value: number | undefined, digits = 3) =>
  typeof value === 'number' && Number.isFinite(value)
    ? value.toFixed(digits)
    : '—';

const pct = (value: number | undefined, digits = 1) =>
  typeof value === 'number' && Number.isFinite(value)
    ? `${(value * 100).toFixed(digits)}`
    : '—';
interface MultiHorizonApiRow {
  Horizon: string;
  Model: string;
  OOS_Observations: number;
  Positive_Rate: number;
  ROC_AUC: number;
  PR_AUC: number;
  Brier: number;
  'Precision_0.5': number;
  'Recall_0.5': number;
  'F1_0.5': number;
  'FAR_0.5': number;
  'Missed_Rate_0.5': number;
  TP: number;
  FP: number;
  TN: number;
  FN: number;
  OOS_Start: string;
  OOS_End: string;
}

const horizonDefinitions = [
  {
    horizon: '1D',
    period: 'NEXT TRADING DAY',
    question: 'Will a market Stress Event occur on the next trading day?',
    strongest: true,
  },
  {
    horizon: '5D',
    period: '≈ 1 TRADING WEEK',
    question:
      'Will a Stress Event occur at least once within the next 5 trading days?',
    strongest: false,
  },
  {
    horizon: '10D',
    period: '≈ 2 TRADING WEEKS',
    question:
      'Will a Stress Event occur at least once within the next 10 trading days?',
    strongest: false,
  },
  {
    horizon: '20D',
    period: '≈ 1 TRADING MONTH',
    question:
      'Will a Stress Event occur at least once within the next 20 trading days?',
    strongest: false,
  },
];
const earlyWarningData = [
  {
    window: '20–11D',
    label: 'EARLY SIGNAL',
    logistic: 69.0,
    xgboost: 48.3,
    description: 'Exploratory pre-stress signal',
  },
  {
    window: '10–6D',
    label: 'RISK BUILD-UP',
    logistic: 72.4,
    xgboost: 62.1,
    description: 'Risk signal becomes more frequent',
  },
  {
    window: '5–1D',
    label: 'IMMINENT WARNING',
    logistic: 100.0,
    xgboost: 86.2,
    description: 'Historical OOS stress episodes with ≥1 warning',
  },
];

const warningPersistence = [
  {
    duration: '1+ DAYS',
    precision: 38.0,
  },
  {
    duration: '2+ DAYS',
    precision: 48.2,
  },
  {
    duration: '3+ DAYS',
    precision: 57.1,
  },
];

const signalImportance = [
  {
    signal: 'VIX Relative Level',
    technical: 'VIX_252D_ZScore',
    logistic: 0.030058,
    xgboost: 0.055981,
  },
  {
    signal: 'Credit Spread Relative Level',
    technical: 'Credit_252D_ZScore',
    logistic: 0.019533,
    xgboost: 0.018851,
  },
  {
    signal: 'SPY Drawdown',
    technical: 'SPY_Drawdown',
    logistic: 0.013852,
    xgboost: -0.003830,
  },
  {
    signal: 'SPY 20D Volatility',
    technical: 'SPY_20D_Vol',
    logistic: 0.006462,
    xgboost: -0.000791,
  },
  {
    signal: 'SPY 20D Momentum',
    technical: 'SPY_20D_Momentum',
    logistic: 0.002570,
    xgboost: 0.000925,
  },
];

export default function ModelValidationPage() {

  const [metrics, setMetrics] = useState<MetricRow[]>([]);
  const [events, setEvents] = useState<EventRow[]>([]);
  const [history, setHistory] = useState<HistoricalRow[]>([]);
  const [multiHorizon, setMultiHorizon] =
    useState<MultiHorizonApiRow[]>([]);

  const horizonPerformance = ['1D', '5D', '10D', '20D'].map((horizon) => {
    const logistic = multiHorizon.find(
      (row) => row.Horizon === horizon && row.Model === 'Logistic'
    );

    const xgb = multiHorizon.find(
      (row) => row.Horizon === horizon && row.Model === 'XGBoost'
    );

    return {
      horizon,
      logisticRoc: logistic?.ROC_AUC ?? 0,
      xgbRoc: xgb?.ROC_AUC ?? 0,
      logisticPr: logistic?.PR_AUC ?? 0,
      xgbPr: xgb?.PR_AUC ?? 0,
      strongest: horizon === '1D',
    };
  });
  const [selectedEvent, setSelectedEvent] =
   useState<string>('2008 Financial Crisis');

  useEffect(() => {
    async function fetchValidationData() {
      try {
        const res = await fetch(`${API_URL}/api/validation`);

        if (!res.ok) {
          throw new Error(`Validation API returned ${res.status}`);
        }

        const data = await res.json();

        setMetrics(data.overall_metrics ?? []);
        setEvents(data.historical_events ?? []);
              const multiRes = await fetch(
        `${API_URL}/api/multi-horizon-validation`
      );

      if (!multiRes.ok) {
        throw new Error(
          `Multi-horizon API returned ${multiRes.status}`
        );
      }

      const multiData = await multiRes.json();
      setMultiHorizon(multiData.data ?? []);
      } catch (err) {
        console.error('Failed to fetch validation metrics:', err);
      }
    }
    fetchValidationData();
  }, []);

  useEffect(() => {
    async function fetchHistoricalData() {
      try {
        const res = await fetch(
          `${API_URL}/api/historical?days=10000`
        );

      if (!res.ok) {
        throw new Error(`Historical API returned ${res.status}`);
      }

      const data = await res.json();
      setHistory(data.data ?? []);
    } catch (err) {
      console.error('Failed to fetch historical OOS data:', err);
    }
  }

  fetchHistoricalData();
}, []);

  const currentEvent =
    events.find((e) => e.Event === selectedEvent) || events[0];

  const eventHistory = currentEvent
  ? history.filter(
      (row) =>
        row.date >= currentEvent.Start &&
        row.date <= currentEvent.End
    )
  : [];
  return (
    <div className="space-y-8">
      {/* Section Header */}
      <div>
        <h1 className="text-xl font-bold text-white tracking-wider flex items-center space-x-2">
          <BarChart3 className="w-5 h-5 text-financial-green" />
          <span>PAGE 02 — MODEL VALIDATION & HISTORICAL BACKTEST</span>
        </h1>

        <p className="text-xs text-gray-400 mt-1">
          Purged walk-forward out-of-sample validation with horizon-specific
          label-overlap gaps.
        </p>
      </div>
      {/* Multi-Horizon Forecast Definition */}
      <div className="bg-dark-card border border-dark-border p-6 rounded-lg space-y-5">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold text-gray-200 tracking-wider">
              WHAT DO THE FORECAST HORIZONS PREDICT?
            </h3>

            <span className="text-[10px] font-mono text-gray-500 border border-dark-border rounded px-2 py-1">
              MULTI-HORIZON
            </span>
          </div>

          <p className="text-xs text-gray-500 mt-2">
            Each horizon is trained as a separate prediction task with its own
            forward label window and matching purge period.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          {horizonDefinitions.map((item) => (
            <div
              key={item.horizon}
              className={`relative p-5 rounded-lg border ${
                item.strongest
                  ? 'border-financial-green bg-dark-bg'
                  : 'border-dark-border bg-dark-bg'
              }`}
            >
              {item.strongest && (
                <div className="absolute top-3 right-3">
                  <span className="text-[9px] font-bold tracking-wider text-financial-green border border-financial-green/40 rounded px-2 py-1">
                    STRONGEST OOS
                  </span>
                </div>
              )}

              <div
                className={`text-2xl font-bold font-mono ${
                  item.strongest ? 'text-financial-green' : 'text-white'
                }`}
              >
                {item.horizon}
              </div>

              <div className="text-[10px] tracking-wider text-gray-500 mt-1">
                {item.period}
              </div>

              <p className="text-xs text-gray-300 leading-relaxed mt-4">
                {item.question}
              </p>

              {item.strongest && (
                <div className="mt-4 pt-3 border-t border-dark-border">
                  <div className="text-[10px] text-gray-500">
                    LOGISTIC ROC-AUC
                  </div>
                  <div className="text-lg font-bold font-mono text-financial-green">
                    0.9886
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="text-[11px] text-gray-500 border-t border-dark-border pt-3">
          1D asks about the next trading day, while 5D, 10D and 20D ask
          whether at least one market Stress Event occurs anywhere within
          their respective forward windows.
        </div>
      </div>
      {/* Multi-Horizon OOS Performance */}
      <div className="bg-dark-card border border-dark-border p-6 rounded-lg space-y-6">
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold text-gray-200 tracking-wider">
              MULTI-HORIZON OUT-OF-SAMPLE PERFORMANCE
            </h3>
            <p className="text-xs text-gray-500 mt-1">
              Purged walk-forward OOS discrimination across four independently
              trained forecast horizons.
            </p>
          </div>

          <div className="text-[10px] font-mono text-financial-green border border-financial-green/40 rounded px-3 py-1.5">
            BEST OOS DISCRIMINATION · 1D
          </div>
        </div>

        {/* Performance Chart */}
        <div className="h-[320px] bg-dark-bg border border-dark-border rounded-lg p-4">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={horizonPerformance}
              margin={{ top: 15, right: 20, left: 0, bottom: 5 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#26303d"
                vertical={false}
              />

              <XAxis
                dataKey="horizon"
                stroke="#6b7280"
                tick={{ fontSize: 11 }}
              />

              <YAxis
                domain={[0.65, 1]}
                stroke="#6b7280"
                tick={{ fontSize: 11 }}
                tickFormatter={(value) => value.toFixed(2)}
              />

              <Tooltip
                contentStyle={{
                  backgroundColor: '#0b0f14',
                  border: '1px solid #26303d',
                  borderRadius: '6px',
                  fontSize: '11px',
                }}
                formatter={(value: number) => value.toFixed(4)}
              />

              <Line
                type="monotone"
                dataKey="logisticRoc"
                name="Logistic ROC-AUC"
                stroke="#22c55e"
                strokeWidth={2.5}
                dot={{ r: 4 }}
                activeDot={{ r: 6 }}
              />

              <Line
                type="monotone"
                dataKey="xgbRoc"
                name="XGBoost ROC-AUC"
                stroke="#3b82f6"
                strokeWidth={2.5}
                dot={{ r: 4 }}
                activeDot={{ r: 6 }}
              />

              <Line
                type="monotone"
                dataKey="logisticPr"
                name="Logistic PR-AUC"
                stroke="#a855f7"
                strokeWidth={2}
                strokeDasharray="5 4"
                dot={{ r: 3 }}
              />

              <Line
                type="monotone"
                dataKey="xgbPr"
                name="XGBoost PR-AUC"
                stroke="#f59e0b"
                strokeWidth={2}
                strokeDasharray="5 4"
                dot={{ r: 3 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="flex flex-wrap gap-x-6 gap-y-2 text-[10px] font-mono text-gray-400">
          <span>
            <span className="text-green-400">●</span> Logistic ROC-AUC
          </span>
          <span>
            <span className="text-blue-400">●</span> XGBoost ROC-AUC
          </span>
          <span>
            <span className="text-purple-400">●</span> Logistic PR-AUC
          </span>
          <span>
            <span className="text-amber-400">●</span> XGBoost PR-AUC
          </span>
        </div>

        {/* Exact Performance Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs font-mono">
            <thead>
              <tr className="border-b border-dark-border bg-dark-bg text-gray-400">
                <th className="p-3">HORIZON</th>
                <th className="p-3">LOGISTIC ROC</th>
                <th className="p-3">XGB ROC</th>
                <th className="p-3">LOGISTIC PR</th>
                <th className="p-3">XGB PR</th>
              </tr>
            </thead>

            <tbody>
              {horizonPerformance.map((row) => (
                <tr
                  key={row.horizon}
                  className={`border-b border-dark-border ${
                    row.strongest ? 'bg-emerald-500/5' : ''
                  }`}
                >
                  <td className="p-3">
                    <div className="flex items-center gap-2">
                      <span
                        className={`font-bold ${
                          row.strongest
                            ? 'text-financial-green'
                            : 'text-white'
                        }`}
                      >
                        {row.horizon}
                      </span>

                      {row.strongest && (
                        <span className="text-[9px] text-financial-green border border-financial-green/40 rounded px-1.5 py-0.5">
                          STRONGEST
                        </span>
                      )}
                    </div>
                  </td>

                  <td className="p-3 text-green-400 font-bold">
                    {row.logisticRoc.toFixed(4)}
                  </td>
                  <td className="p-3 text-blue-400">
                    {row.xgbRoc.toFixed(4)}
                  </td>
                  <td className="p-3 text-purple-400 font-bold">
                    {row.logisticPr.toFixed(4)}
                  </td>
                  <td className="p-3 text-amber-400">
                    {row.xgbPr.toFixed(4)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Key Findings */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="bg-dark-bg border border-financial-green/40 rounded-lg p-4">
            <div className="text-[10px] tracking-wider text-financial-green font-bold">
              STRONGEST HORIZON
            </div>
            <div className="text-2xl text-white font-bold font-mono mt-2">
              1 DAY
            </div>
            <div className="text-xs text-gray-400 mt-2 leading-relaxed">
              Logistic ROC-AUC 0.9886 and PR-AUC 0.9247 — the strongest
              out-of-sample discrimination among the four tested horizons.
            </div>
          </div>

          <div className="bg-dark-bg border border-dark-border rounded-lg p-4">
            <div className="text-[10px] tracking-wider text-financial-blue font-bold">
              EARLY-WARNING REACH
            </div>
            <div className="text-2xl text-white font-bold font-mono mt-2">
              UP TO 20 DAYS
            </div>
            <div className="text-xs text-gray-400 mt-2 leading-relaxed">
              Logistic ROC-AUC remains 0.9220 at 10D and 0.8555 at 20D,
              indicating that useful ranking information remains detectable
              beyond the immediate horizon.
            </div>
          </div>

          <div className="bg-dark-bg border border-dark-border rounded-lg p-4">
            <div className="text-[10px] tracking-wider text-purple-400 font-bold">
              MODEL TRADE-OFF
            </div>
            <div className="text-lg text-white font-bold mt-2">
              LOGISTIC vs XGBOOST
            </div>
            <div className="text-xs text-gray-400 mt-2 leading-relaxed">
              Logistic provides stronger ROC/PR discrimination across all
              horizons. XGBoost produces fewer false alarms at the fixed 0.50
              threshold, but misses more stress events.
            </div>
          </div>
        </div>

       {/* Conclusion */}
      <div className="border-l-2 border-financial-green bg-dark-bg px-5 py-4">
        <div className="text-[10px] tracking-wider text-gray-500 font-bold">
          CONCLUSION
        </div>

        <div className="mt-2">
          <p className="text-sm text-white font-semibold leading-relaxed">
            Near-term stress provides the strongest warning signal, while useful
            predictive information remains detectable up to 20 trading days ahead.
          </p>

          <p className="text-xs text-gray-400 mt-2 leading-relaxed">
            Logistic Regression provides stronger discrimination and event sensitivity,
            while XGBoost offers a more conservative operating profile with fewer
            false alarms.
          </p>
        </div>
      </div>

        <div className="text-[10px] text-gray-500 font-mono">
          PURGED WALK-FORWARD OOS · 17 FEATURES · HORIZON-SPECIFIC PURGE · NO RANDOM SPLIT
        </div>
      </div>
            {/* Early Warning Analysis */}
      <div className="bg-dark-card border border-dark-border p-6 rounded-lg space-y-6">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-bold text-gray-200 tracking-wider">
              HOW EARLY DOES IT WARN?
            </h3>

            <span className="text-[10px] font-mono text-gray-500 border border-dark-border rounded px-2 py-1">
              OOS PRE-STRESS ANALYSIS
            </span>
          </div>

          <p className="text-xs text-gray-500 mt-2 max-w-3xl leading-relaxed">
            How often did the models show a warning before a broad U.S.
            market Stress Event began?
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {earlyWarningData.map((item, index) => (
            <div
              key={item.window}
              className={`bg-dark-bg border rounded-lg p-5 ${
                index === 2
                  ? 'border-financial-green/50'
                  : 'border-dark-border'
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-[10px] font-bold tracking-wider text-gray-500">
                    {item.label}
                  </div>

                  <div className="text-2xl font-bold font-mono text-white mt-1">
                    {item.window}
                  </div>
                </div>

                {index === 2 && (
                  <span className="text-[9px] text-financial-green border border-financial-green/40 rounded px-2 py-1">
                    STRONGEST
                  </span>
                )}
              </div>

              <div className="mt-5 space-y-4">
                <div>
                  <div className="flex justify-between text-[11px] mb-1">
                    <span className="text-gray-400">Logistic</span>
                    <span className="font-mono font-bold text-green-400">
                      {item.logistic.toFixed(1)}%
                    </span>
                  </div>

                  <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-green-500 rounded-full"
                      style={{ width: `${item.logistic}%` }}
                    />
                  </div>
                </div>

                <div>
                  <div className="flex justify-between text-[11px] mb-1">
                    <span className="text-gray-400">XGBoost</span>
                    <span className="font-mono font-bold text-blue-400">
                      {item.xgboost.toFixed(1)}%
                    </span>
                  </div>

                  <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-500 rounded-full"
                      style={{ width: `${item.xgboost}%` }}
                    />
                  </div>
                </div>
              </div>

              <p className="text-[11px] text-gray-500 mt-4 leading-relaxed">
                {item.description}
              </p>
            </div>
          ))}
        </div>

        <div className="border-l-2 border-financial-amber bg-dark-bg px-5 py-4">
          <div className="text-[10px] tracking-wider text-financial-amber font-bold">
            EARLY WARNING DOES NOT MEAN A STRESS EVENT IS CERTAIN
          </div>

          <p className="text-xs text-gray-400 mt-2 leading-relaxed">
            Some early warnings are false alarms. The 20–11D result is
            exploratory because it extends beyond the primary 10-day
            model&apos;s intended forecast horizon.
          </p>
        </div>
      </div>

            {/* Warning Persistence */}
      <div className="bg-dark-card border border-dark-border p-6 rounded-lg space-y-6">
        <div>
          <h3 className="text-sm font-bold text-gray-200 tracking-wider">
            WHEN DOES A WARNING BECOME MORE RELIABLE?
          </h3>

          <p className="text-xs text-gray-500 mt-2">
            XGBoost warnings became more informative when elevated risk
            persisted across multiple trading days.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {warningPersistence.map((item, index) => (
            <div
              key={item.duration}
              className={`bg-dark-bg border rounded-lg p-5 ${
                index === 2
                  ? 'border-financial-green/50'
                  : 'border-dark-border'
              }`}
            >
              <div className="text-[10px] tracking-wider text-gray-500">
                WARNING PERSISTENCE
              </div>

              <div className="text-lg font-bold text-white mt-1">
                {item.duration}
              </div>

              <div className="text-3xl font-bold font-mono text-financial-green mt-4">
                {item.precision.toFixed(1)}%
              </div>

              <p className="text-[11px] text-gray-500 mt-2 leading-relaxed">
                of these warning episodes were followed by broad-market stress
                within the next 20 trading days
              </p>
            </div>
          ))}
        </div>

        <div className="border-l-2 border-financial-green bg-dark-bg px-5 py-4">
          <div className="text-[10px] tracking-wider text-gray-500 font-bold">
            KEY TAKEAWAY
          </div>

          <p className="text-sm text-white font-semibold mt-2">
            Persistent warnings were more reliable than one-day warning signals.
          </p>

          <p className="text-xs text-gray-400 mt-2 leading-relaxed">
            For XGBoost, the share of warning episodes followed by broad-market
            stress within 20 trading days increased from 38.0% for all warnings
            to 57.1% when the warning persisted for at least three trading days.
          </p>
        </div>

        <div className="text-[10px] text-gray-500 border-t border-dark-border pt-4 leading-relaxed">
          Warning episodes are anchored to the first day the OOS Risk Score
          crosses 0.50. The 20-day follow-up is an exploratory warning-reliability
          analysis and should not be interpreted as a 20-day forecast from the
          10-day model.
        </div>
      </div>
      
            {/* OOS Signal Importance */}
      <div className="bg-dark-card border border-dark-border p-6 rounded-lg space-y-6">
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold text-gray-200 tracking-wider">
              WHICH SIGNALS MATTER MOST?
            </h3>

            <p className="text-xs text-gray-500 mt-2 max-w-3xl leading-relaxed">
              Each signal was removed one at a time and the full purged
              walk-forward validation was rerun. A larger positive ΔPR-AUC means
              performance deteriorated more when that signal was removed.
            </p>
          </div>

          <span className="text-[10px] font-mono text-financial-green border border-financial-green/40 rounded px-3 py-1.5 whitespace-nowrap">
            LOFO · 10D OOS
          </span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="bg-dark-bg border border-financial-green/40 rounded-lg p-5">
            <div className="text-[10px] tracking-wider text-financial-green font-bold">
              #1 CONSISTENT SIGNAL
            </div>

            <div className="text-xl text-white font-bold mt-2">
              VIX Relative Level
            </div>

            <p className="text-xs text-gray-400 mt-2 leading-relaxed">
              How unusual current market volatility is compared with its own
              recent history.
            </p>

            <div className="grid grid-cols-2 gap-3 mt-5">
              <div>
                <div className="text-[10px] text-gray-500">
                  LOGISTIC ΔPR-AUC
                </div>
                <div className="font-mono text-lg font-bold text-green-400 mt-1">
                  +0.0301
                </div>
              </div>

              <div>
                <div className="text-[10px] text-gray-500">
                  XGBOOST ΔPR-AUC
                </div>
                <div className="font-mono text-lg font-bold text-blue-400 mt-1">
                  +0.0560
                </div>
              </div>
            </div>
          </div>

          <div className="bg-dark-bg border border-dark-border rounded-lg p-5">
            <div className="text-[10px] tracking-wider text-purple-400 font-bold">
              #2 CONSISTENT SIGNAL
            </div>

            <div className="text-xl text-white font-bold mt-2">
              Credit Spread Relative Level
            </div>

            <p className="text-xs text-gray-400 mt-2 leading-relaxed">
              How unusual corporate-credit stress is compared with its own
              recent history.
            </p>

            <div className="grid grid-cols-2 gap-3 mt-5">
              <div>
                <div className="text-[10px] text-gray-500">
                  LOGISTIC ΔPR-AUC
                </div>
                <div className="font-mono text-lg font-bold text-green-400 mt-1">
                  +0.0195
                </div>
              </div>

              <div>
                <div className="text-[10px] text-gray-500">
                  XGBOOST ΔPR-AUC
                </div>
                <div className="font-mono text-lg font-bold text-blue-400 mt-1">
                  +0.0189
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="h-[330px] bg-dark-bg border border-dark-border rounded-lg p-4">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={signalImportance}
              layout="vertical"
              margin={{ top: 10, right: 25, left: 35, bottom: 10 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#26303d"
                horizontal={false}
              />

              <XAxis
                type="number"
                stroke="#6b7280"
                tick={{ fontSize: 10 }}
                tickFormatter={(value) => value.toFixed(2)}
              />

              <YAxis
                type="category"
                dataKey="signal"
                width={155}
                stroke="#6b7280"
                tick={{ fontSize: 10 }}
              />

              <Tooltip
                contentStyle={{
                  backgroundColor: '#0b0f14',
                  border: '1px solid #26303d',
                  borderRadius: '6px',
                  fontSize: '11px',
                }}
                formatter={(value: number) => value.toFixed(4)}
              />

              <ReferenceLine x={0} stroke="#6b7280" />

              <Bar
                dataKey="logistic"
                name="Logistic ΔPR-AUC"
                fill="#22c55e"
                barSize={8}
              />

              <Bar
                dataKey="xgboost"
                name="XGBoost ΔPR-AUC"
                fill="#3b82f6"
                barSize={8}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div className="border-l-2 border-financial-green bg-dark-bg px-5 py-4">
          <div className="text-[10px] tracking-wider text-gray-500 font-bold">
            WHAT DID THE MODEL LEARN?
          </div>

          <p className="text-sm text-white font-semibold mt-2 leading-relaxed">
            Relative volatility and credit stress provided the most consistent
            unique out-of-sample predictive information.
          </p>

          <p className="text-xs text-gray-400 mt-2 leading-relaxed">
            In simple terms, the model benefits more from knowing how unusual
            current VIX and credit conditions are relative to their recent
            history than from relying only on their absolute levels.
          </p>
        </div>

        <div className="text-[10px] text-gray-500 leading-relaxed border-t border-dark-border pt-4">
          LOFO measures incremental predictive contribution conditional on the
          other 16 signals. Negative or near-zero values may reflect overlapping
          information rather than an intrinsically uninformative variable. This
          is a diagnostic analysis, not causal importance or post-hoc feature
          selection. The Core 17-feature specification remains unchanged.
        </div>
      </div>

      {/* Model Performance */}
      <div className="bg-dark-card border border-dark-border p-6 rounded-lg space-y-4">
        <div>
          <h3 className="text-sm font-bold text-gray-200 tracking-wider">
            10-DAY DETAILED MODEL PERFORMANCE
          </h3>
          <p className="text-xs text-gray-500 mt-1">
            OOS period: 2006-08-09 — 2026-09-21
          </p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs font-mono">
            <thead>
              <tr className="border-b border-dark-border bg-dark-bg text-gray-400">
                <th className="p-3">MODEL</th>
                <th className="p-3">ROC-AUC</th>
                <th className="p-3">PR-AUC</th>
                <th className="p-3">BRIER</th>
                <th className="p-3">PRECISION</th>
                <th className="p-3">RECALL</th>
                <th className="p-3">F1</th>
                <th className="p-3 text-financial-amber">
                  FALSE ALARM
                </th>
                <th className="p-3 text-financial-red">
                  MISSED EVENT
                </th>
              </tr>
            </thead>

            <tbody>
              {metrics.map((row, idx) => (
                <tr
                  key={idx}
                  className="border-b border-dark-border hover:bg-dark-hover transition-colors"
                >
                    <td className="p-3 font-bold text-white">
                      <div className="flex items-center space-x-2">
                        <div className="w-2 h-2 rounded-full bg-gray-500" />
                        <span>{row.Model}</span>
                      </div>
                    </td>

                    <td className="p-3 font-bold text-financial-blue">
                    {fmt(row['ROC-AUC'])}
                  </td>

                  <td className="p-3 font-bold text-purple-400">
                    {fmt(row['PR-AUC (AP)'])}
                  </td>

                  <td className="p-3">
                    {fmt(row['Brier Score'])}
                  </td>

                  <td className="p-3">
                    {fmt(row.Precision)}
                  </td>

                  <td className="p-3">
                    {fmt(row.Recall)}
                  </td>

                  <td className="p-3 font-bold text-emerald-400">
                    {fmt(row.F1)}
                  </td>

                  <td className="p-3 text-financial-amber">
                    {fmt(row['False Alarm Rate'])}
                  </td>

                  <td className="p-3 text-financial-red">
                    {fmt(row['Missed Event Rate'])}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="border-t border-dark-border pt-3 text-[11px] text-gray-500 leading-relaxed">
          ROC-AUC and PR-AUC evaluate ranking performance using continuous
          out-of-sample model scores. Precision, Recall, F1, False Alarm Rate,
          and Missed Event Rate are reported at a fixed 0.50 reference
          threshold. The threshold was not selected using the OOS results.
        </div>
      </div>

      {/* Historical Crisis Validation */}
      <div className="bg-dark-card border border-dark-border p-6 rounded-lg space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h3 className="text-sm font-bold text-gray-200 tracking-wider">
              HISTORICAL STRESS CASE STUDIES
            </h3>

            <p className="text-xs text-gray-400 mt-1">
              Descriptive analysis of XGBoost walk-forward OOS risk scores
              during predefined historical market-stress windows.
            </p>
          </div>

          <select
            value={selectedEvent}
            onChange={(e) => setSelectedEvent(e.target.value)}
            className="bg-dark-bg border border-dark-border text-gray-200 text-xs rounded px-3 py-2 focus:outline-none focus:border-financial-blue font-mono"
          >
            {events.map((evt, idx) => (
              <option key={idx} value={evt.Event}>
                {evt.Event}
              </option>
            ))}
          </select>
        </div>

        {currentEvent && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-5 gap-4 pt-2">
              <div className="bg-dark-bg border border-dark-border p-4 rounded">
                <span className="text-xs text-gray-500 uppercase">
                  Period
                </span>

                <p className="text-sm font-bold font-mono text-gray-200 mt-2">
                  {currentEvent.Start}
                </p>

                <p className="text-xs font-mono text-gray-500">
                  to {currentEvent.End}
                </p>
              </div>

              <div className="bg-dark-bg border border-dark-border p-4 rounded">
                <span className="text-xs text-gray-500 uppercase">
                  Event Window
                </span>

                <p className="text-lg font-bold font-mono text-white mt-2">
                  {currentEvent.Days}
                </p>

                <p className="text-xs text-gray-500">
                  trading days
                </p>
              </div>

              <div className="bg-dark-bg border border-dark-border p-4 rounded">
                <span className="text-xs text-gray-500 uppercase">
                  10D Stress-Window Days
                </span>

                <p className="text-lg font-bold font-mono text-white mt-2">
                  {currentEvent['Actual Stress Days']}
                </p>

                <p className="text-xs text-gray-500">
                  target-defined days
                </p>
              </div>

              <div className="bg-dark-bg border border-dark-border p-4 rounded">
                <span className="text-xs text-gray-500 uppercase">
                  Max XGB Risk Score
                </span>

                <p className="text-lg font-bold font-mono text-financial-red mt-2">
                  {pct(currentEvent['XGB Max Prob'])}
                  <span className="text-xs text-gray-500 ml-1">/ 100</span>
                </p>
              </div>

              <div className="bg-dark-bg border border-dark-border p-4 rounded">
                <span className="text-xs text-gray-500 uppercase">
                  Score ≥ 50 Days
                </span>

                <p className="text-lg font-bold font-mono text-financial-amber mt-2">
                  {currentEvent['XGB >= 0.5 Days']}
                  <span className="text-xs text-gray-500 ml-1">
                    / {currentEvent.Days}
                  </span>
                </p>
              </div>
            </div>

            <div className="border-t border-dark-border pt-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                <div>
                  <span className="text-gray-500">
                    XGBoost average OOS risk score
                  </span>
                  <span className="font-mono text-gray-200 ml-2">
                    {pct(currentEvent['XGB Avg Prob'])} / 100
                  </span>
                </div>

                <div>
                  <span className="text-gray-500">
                    Logistic average OOS risk score
                  </span>
                  <span className="font-mono text-gray-200 ml-2">
                    {pct(currentEvent['Logistic Avg Prob'])} / 100
                  </span>
                </div>
              </div>
            </div>
                          {/* Historical OOS Risk Trajectory */}
              <div className="border-t border-dark-border pt-6 space-y-4">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                  <div>
                    <h4 className="text-xs font-bold text-gray-200 tracking-wider">
                      HISTORICAL OOS RISK TRAJECTORY
                    </h4>
                    <p className="text-[11px] text-gray-500 mt-1">
                      XGBoost walk-forward OOS risk score versus SPY during the
                      selected historical window.
                    </p>
                  </div>

                  <div className="flex items-center gap-5 text-[11px] font-mono">
                    <div className="flex items-center gap-2 text-gray-400">
                      <span className="w-5 h-[2px] bg-financial-red" />
                      XGBoost 10D Risk Score
                    </div>

                    <div className="flex items-center gap-2 text-gray-400">
                      <span className="w-5 h-[2px] bg-financial-blue" />
                      SPY Price
                    </div>
                  </div>
                </div>

                <div className="h-[360px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart
                      data={eventHistory}
                      margin={{
                        top: 10,
                        right: 20,
                        left: 0,
                        bottom: 5,
                      }}
                    >
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="#1f2937"
                        vertical={false}
                      />

                      <XAxis
                        dataKey="date"
                        stroke="#6b7280"
                        tick={{ fontSize: 10 }}
                        minTickGap={40}
                      />

                      <YAxis
                        yAxisId="risk"
                        domain={[0, 100]}
                        stroke="#F23645"
                        tick={{ fontSize: 10 }}
                        width={42}
                      />

                      <YAxis
                        yAxisId="spy"
                        orientation="right"
                        domain={['auto', 'auto']}
                        stroke="#4DA3FF"
                        tick={{ fontSize: 10 }}
                        width={55}
                      />

                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#111827',
                          border: '1px solid #374151',
                          borderRadius: '6px',
                          fontSize: '12px',
                        }}
                        labelStyle={{ color: '#9ca3af' }}
                        formatter={(value: number, name: string) => {
                          if (name === 'XGBoost 10D Risk Score') {
                            return [`${value.toFixed(1)} / 100`, name];
                          }

                          if (name === 'SPY Price') {
                            return [`$${value.toFixed(2)}`, name];
                          }

                          return [value, name];
                        }}
                      />

                      <ReferenceLine
                        yAxisId="risk"
                        y={50}
                        stroke="#6b7280"
                        strokeDasharray="5 5"
                        label={{
                          value: '50',
                          position: 'insideTopLeft',
                          fill: '#6b7280',
                          fontSize: 10,
                        }}
                      />

                      <Area
                        yAxisId="risk"
                        type="monotone"
                        dataKey="risk_score_xgboost"
                        name="XGBoost 10D Risk Score"
                        stroke="#F23645"
                        fill="#F23645"
                        fillOpacity={0.18}
                        strokeWidth={1.8}
                        dot={false}
                        isAnimationActive={false}
                      />

                      <Line
                        yAxisId="spy"
                        type="monotone"
                        dataKey="spy"
                        name="SPY Price"
                        stroke="#4DA3FF"
                        strokeWidth={2.2}
                        dot={false}
                        isAnimationActive={false}
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>

                <p className="text-[11px] text-gray-500 leading-relaxed">
                  The dashed 50 line is a fixed reference operating threshold,
                  not a threshold selected from out-of-sample results. The chart
                  is descriptive and does not imply prediction of SPY direction.
                </p>
              </div>

            {currentEvent.Event === '2023 US Banking Stress' && (
              <div className="bg-dark-bg border border-dark-border rounded p-4 text-xs text-gray-400 leading-relaxed">
                The March–April 2023 banking turmoil produced elevated model
                scores on several days, but this predefined window contained
                no positive broad-market stress days under the study&apos;s
                target definition. It is therefore treated as a special case
                rather than a positive stress-event validation period.
              </div>
            )}
          </>
        )}

        <p className="text-[11px] text-gray-500 leading-relaxed">
          Historical windows are descriptive case studies based strictly on
          walk-forward out-of-sample scores. They are not reported as
          independently clustered crisis-detection rates.
        </p>
      </div>
    </div>
  );
}