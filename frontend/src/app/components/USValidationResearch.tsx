'use client';

import { LocalizedText, useI18n } from '../i18n/provider';


import React, { useEffect, useState } from 'react';
import Disclosure from './Disclosure';
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

export default function USValidationResearch() {
  const { t, locale } = useI18n();


  const [errors, setErrors] = useState<string[]>([]);
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
      logisticRoc: logistic?.ROC_AUC,
      xgbRoc: xgb?.ROC_AUC,
      logisticPr: logistic?.PR_AUC,
      xgbPr: xgb?.PR_AUC,
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
        setErrors(value => [...value, 'Validation or multi-horizon data unavailable.']);
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
      setErrors(value => [...value, 'Historical OOS chart data unavailable.']);
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
    <div className="legacy-research">
      {errors.map(message => <p key={message} className="comparison-note" role="status"><LocalizedText>{message}</LocalizedText></p>)}
      {/* Section Header */}
      
      {/* Multi-Horizon Forecast Definition */}
      
      <Disclosure label={t("U.S. Multi-Horizon Experiment")} lazy><div className="bg-dark-card border border-dark-border p-6 rounded-lg space-y-5">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold text-gray-200 tracking-wider"><LocalizedText id="what_do_the_forecast_horizons_predict_02d2bf" before after/></h3>

            <span className="text-[12px] font-mono text-gray-500 border border-dark-border rounded px-2 py-1"><LocalizedText id="multi_horizon_4afa2c" before after/></span>
          </div>

          <p className="text-xs text-gray-500 mt-2"><LocalizedText id="each_horizon_is_trained_as_a_separate_prediction_task_with_its_ow_e296aa" before after/></p>
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
                  <span className="text-[12px] font-bold tracking-wider text-financial-green border border-financial-green/40 rounded px-2 py-1"><LocalizedText id="strongest_oos_12ef48" before after/></span>
                </div>
              )}

              <div
                className={`text-2xl font-bold font-mono ${
                  item.strongest ? 'text-financial-green' : 'text-white'
                }`}
              >
                <LocalizedText>{item.horizon}</LocalizedText>
              </div>

              <div className="text-[12px] tracking-wider text-gray-500 mt-1">
                <LocalizedText>{item.period}</LocalizedText>
              </div>

              <p className="text-xs text-gray-300 leading-relaxed mt-4">
                <LocalizedText>{item.question}</LocalizedText>
              </p>

              {item.strongest && (
                <div className="mt-4 pt-3 border-t border-dark-border">
                  <div className="text-[12px] text-gray-500"><LocalizedText id="logistic_roc_auc_2e744c" before after/></div>
                  <div className="text-lg font-bold font-mono text-financial-green">
                    0.9886
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="text-[12px] text-gray-500 border-t border-dark-border pt-3"><LocalizedText id="1d_asks_about_the_next_trading_day_while_5d_10d_and_20d_ask_wheth_f4cc36" before after/></div>
      </div>
      {/* Multi-Horizon OOS Performance */}
      
      <div className="bg-dark-card border border-dark-border p-6 rounded-lg space-y-6">
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold text-gray-200 tracking-wider"><LocalizedText id="multi_horizon_out_of_sample_performance_c05bd7" before after/></h3>
            <p className="text-xs text-gray-500 mt-1"><LocalizedText id="purged_walk_forward_oos_discrimination_across_four_independently__76a275" before after/></p>
          </div>

          <div className="text-[12px] font-mono text-financial-green border border-financial-green/40 rounded px-3 py-1.5"><LocalizedText id="best_oos_discrimination_1d_1114d9" before after/></div>
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
                tick={{ fontSize: 12 }}
              />

              <YAxis
                domain={[0.65, 1]}
                stroke="#6b7280"
                tick={{ fontSize: 12 }}
                tickFormatter={(value) => value.toFixed(2)}
              />

              <Tooltip
                contentStyle={{
                  backgroundColor: '#0b0f14',
                  border: '1px solid #26303d',
                  borderRadius: '6px',
                  fontSize: '14px',
                }}
                formatter={(value: number) => value.toFixed(4)}
              />

              <Line
                type="monotone"
                dataKey="logisticRoc"
                name={t("Logistic ROC-AUC")}
                stroke="#22c55e"
                strokeWidth={2.5}
                dot={{ r: 4 }}
                activeDot={{ r: 6 }}
              />

              <Line
                type="monotone"
                dataKey="xgbRoc"
                name={t("XGBoost ROC-AUC")}
                stroke="#3b82f6"
                strokeWidth={2.5}
                dot={{ r: 4 }}
                activeDot={{ r: 6 }}
              />

              <Line
                type="monotone"
                dataKey="logisticPr"
                name={t("Logistic PR-AUC")}
                stroke="#a855f7"
                strokeWidth={2}
                strokeDasharray="5 4"
                dot={{ r: 3 }}
              />

              <Line
                type="monotone"
                dataKey="xgbPr"
                name={t("XGBoost PR-AUC")}
                stroke="#f59e0b"
                strokeWidth={2}
                strokeDasharray="5 4"
                dot={{ r: 3 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="flex flex-wrap gap-x-6 gap-y-2 text-[12px] font-mono text-gray-400">
          <span>
            <span className="text-green-400">●</span><LocalizedText id="logistic_roc_auc_2e744c" before after/></span>
          <span>
            <span className="text-blue-400">●</span><LocalizedText id="xgboost_roc_auc_06c907" before after/></span>
          <span>
            <span className="text-purple-400">●</span><LocalizedText id="logistic_pr_auc_a6c803" before after/></span>
          <span>
            <span className="text-amber-400">●</span><LocalizedText id="xgboost_pr_auc_2cdc25" before after/></span>
        </div>

        {/* Exact Performance Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs font-mono">
            <thead>
              <tr className="border-b border-dark-border bg-dark-bg text-gray-400">
                <th className="p-3"><LocalizedText id="horizon_c0d273"/></th>
                <th className="p-3"><LocalizedText id="logistic_roc_40673b"/></th>
                <th className="p-3"><LocalizedText id="xgb_roc_d78c3c"/></th>
                <th className="p-3"><LocalizedText id="logistic_pr_a17a9a"/></th>
                <th className="p-3"><LocalizedText id="xgb_pr_a0c1ba"/></th>
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
                        <LocalizedText>{row.horizon}</LocalizedText>
                      </span>

                      {row.strongest && (
                        <span className="text-[12px] text-financial-green border border-financial-green/40 rounded px-1.5 py-0.5"><LocalizedText id="strongest_0a4fb9" before after/></span>
                      )}
                    </div>
                  </td>

                  <td className="p-3 text-green-400 font-bold">
                    <LocalizedText>{fmt(row.logisticRoc, 4)}</LocalizedText>
                  </td>
                  <td className="p-3 text-blue-400">
                    <LocalizedText>{fmt(row.xgbRoc, 4)}</LocalizedText>
                  </td>
                  <td className="p-3 text-purple-400 font-bold">
                    <LocalizedText>{fmt(row.logisticPr, 4)}</LocalizedText>
                  </td>
                  <td className="p-3 text-amber-400">
                    <LocalizedText>{fmt(row.xgbPr, 4)}</LocalizedText>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Key Findings */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="bg-dark-bg border border-financial-green/40 rounded-lg p-4">
            <div className="text-[12px] tracking-wider text-financial-green font-bold"><LocalizedText id="strongest_horizon_25b73a" before after/></div>
            <div className="text-2xl text-white font-bold font-mono mt-2"><LocalizedText id="1_day_4677b5" before after/></div>
            <div className="text-xs text-gray-400 mt-2 leading-relaxed"><LocalizedText id="logistic_roc_auc_0_9886_and_pr_auc_0_9247_the_strongest_out_of_sa_bbb49f" before after/></div>
          </div>

          <div className="bg-dark-bg border border-dark-border rounded-lg p-4">
            <div className="text-[12px] tracking-wider text-financial-blue font-bold"><LocalizedText id="early_warning_reach_37dc74" before after/></div>
            <div className="text-2xl text-white font-bold font-mono mt-2"><LocalizedText id="up_to_20_days_4ad758" before after/></div>
            <div className="text-xs text-gray-400 mt-2 leading-relaxed"><LocalizedText id="logistic_roc_auc_remains_0_9220_at_10d_and_0_8555_at_20d_indicati_ee82c0" before after/></div>
          </div>

          <div className="bg-dark-bg border border-dark-border rounded-lg p-4">
            <div className="text-[12px] tracking-wider text-purple-400 font-bold"><LocalizedText id="model_trade_off_0e1d0c" before after/></div>
            <div className="text-lg text-white font-bold mt-2"><LocalizedText id="logistic_vs_xgboost_6fe505" before after/></div>
            <div className="text-xs text-gray-400 mt-2 leading-relaxed"><LocalizedText id="logistic_provides_stronger_roc_pr_discrimination_across_all_horiz_2f44b1" before after/></div>
          </div>
        </div>

       {/* Conclusion */}
      <div className="border-l-2 border-financial-green bg-dark-bg px-5 py-4">
        <div className="text-[12px] tracking-wider text-gray-500 font-bold"><LocalizedText id="conclusion_ce2288" before after/></div>

        <div className="mt-2">
          <p className="text-sm text-white font-semibold leading-relaxed"><LocalizedText id="near_term_stress_provides_the_strongest_warning_signal_while_usef_f37a25" before after/></p>

          <p className="text-xs text-gray-400 mt-2 leading-relaxed"><LocalizedText id="logistic_regression_provides_stronger_discrimination_and_event_se_50a5d1" before after/></p>
        </div>
      </div>

        <div className="text-[12px] text-gray-500 font-mono"><LocalizedText id="purged_walk_forward_oos_17_features_horizon_specific_purge_no_ran_b07123" before after/></div>
      </div></Disclosure>
            {/* Early Warning Analysis */}
      
      <Disclosure label={t("Early-warning analysis")} lazy><div className="bg-dark-card border border-dark-border p-6 rounded-lg space-y-6">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-bold text-gray-200 tracking-wider"><LocalizedText id="how_early_does_it_warn_6192cf" before after/></h3>

            <span className="text-[12px] font-mono text-gray-500 border border-dark-border rounded px-2 py-1"><LocalizedText id="oos_pre_stress_analysis_21d35d" before after/></span>
          </div>

          <p className="text-xs text-gray-500 mt-2 max-w-3xl leading-relaxed"><LocalizedText id="how_often_did_the_models_show_a_warning_before_a_broad_u_s_market_b99508" before after/></p>
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
                  <div className="text-[12px] font-bold tracking-wider text-gray-500">
                    <LocalizedText>{item.label}</LocalizedText>
                  </div>

                  <div className="text-2xl font-bold font-mono text-white mt-1">
                    <LocalizedText>{item.window}</LocalizedText>
                  </div>
                </div>

                {index === 2 && (
                  <span className="text-[12px] text-financial-green border border-financial-green/40 rounded px-2 py-1"><LocalizedText id="strongest_0a4fb9" before after/></span>
                )}
              </div>

              <div className="mt-5 space-y-4">
                <div>
                  <div className="flex justify-between text-[12px] mb-1">
                    <span className="text-gray-400"><LocalizedText id="logistic_fb6cdd"/></span>
                    <span className="font-mono font-bold text-green-400">
                      <LocalizedText>{item.logistic.toFixed(1)}</LocalizedText>%
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
                  <div className="flex justify-between text-[12px] mb-1">
                    <span className="text-gray-400"><LocalizedText id="xgboost_e63bae"/></span>
                    <span className="font-mono font-bold text-blue-400">
                      <LocalizedText>{item.xgboost.toFixed(1)}</LocalizedText>%
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

              <p className="text-[12px] text-gray-500 mt-4 leading-relaxed">
                <LocalizedText>{item.description}</LocalizedText>
              </p>
            </div>
          ))}
        </div>

        <div className="border-l-2 border-financial-amber bg-dark-bg px-5 py-4">
          <div className="text-[12px] tracking-wider text-financial-amber font-bold"><LocalizedText id="early_warning_does_not_mean_a_stress_event_is_certain_d5c9d0" before after/></div>

          <p className="text-xs text-gray-400 mt-2 leading-relaxed"><LocalizedText id="some_early_warnings_are_false_alarms_the_20_11d_result_is_explora_18649e" before after/></p>
        </div>
      </div></Disclosure>

            {/* Warning Persistence */}
      
      <Disclosure label={t("Warning persistence")} lazy><div className="bg-dark-card border border-dark-border p-6 rounded-lg space-y-6">
        <div>
          <h3 className="text-sm font-bold text-gray-200 tracking-wider"><LocalizedText id="when_does_a_warning_become_more_reliable_8c33a4" before after/></h3>

          <p className="text-xs text-gray-500 mt-2"><LocalizedText id="xgboost_warnings_became_more_informative_when_elevated_risk_persi_4a8508" before after/></p>
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
              <div className="text-[12px] tracking-wider text-gray-500"><LocalizedText id="warning_persistence_4e1e36" before after/></div>

              <div className="text-lg font-bold text-white mt-1">
                <LocalizedText>{item.duration}</LocalizedText>
              </div>

              <div className="text-3xl font-bold font-mono text-financial-green mt-4">
                <LocalizedText>{item.precision.toFixed(1)}</LocalizedText>%
              </div>

              <p className="text-[12px] text-gray-500 mt-2 leading-relaxed"><LocalizedText id="of_these_warning_episodes_were_followed_by_broad_market_stress_wi_71260a" before after/></p>
            </div>
          ))}
        </div>

        <div className="border-l-2 border-financial-green bg-dark-bg px-5 py-4">
          <div className="text-[12px] tracking-wider text-gray-500 font-bold"><LocalizedText id="key_takeaway_90f5ba" before after/></div>

          <p className="text-sm text-white font-semibold mt-2"><LocalizedText id="persistent_warnings_were_more_reliable_than_one_day_warning_signa_090780" before after/></p>

          <p className="text-xs text-gray-400 mt-2 leading-relaxed"><LocalizedText id="for_xgboost_the_share_of_warning_episodes_followed_by_broad_marke_0a9222" before after/></p>
        </div>

        <div className="text-[12px] text-gray-500 border-t border-dark-border pt-4 leading-relaxed"><LocalizedText id="warning_episodes_are_anchored_to_the_first_day_the_oos_risk_score_aa2578" before after/></div>
      </div></Disclosure>
      
            {/* OOS Signal Importance */}
      
      <Disclosure label={t("OOS signal importance")} lazy><div className="bg-dark-card border border-dark-border p-6 rounded-lg space-y-6">
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold text-gray-200 tracking-wider"><LocalizedText id="which_signals_matter_most_919a25" before after/></h3>

            <p className="text-xs text-gray-500 mt-2 max-w-3xl leading-relaxed"><LocalizedText id="each_signal_was_removed_one_at_a_time_and_the_full_purged_walk_fo_c7855c" before after/></p>
          </div>

          <span className="text-[12px] font-mono text-financial-green border border-financial-green/40 rounded px-3 py-1.5 whitespace-nowrap"><LocalizedText id="lofo_10d_oos_e7b0cc" before after/></span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="bg-dark-bg border border-financial-green/40 rounded-lg p-5">
            <div className="text-[12px] tracking-wider text-financial-green font-bold"><LocalizedText id="1_consistent_signal_245dc1" before after/></div>

            <div className="text-xl text-white font-bold mt-2"><LocalizedText id="vix_relative_level_652754" before after/></div>

            <p className="text-xs text-gray-400 mt-2 leading-relaxed"><LocalizedText id="how_unusual_current_market_volatility_is_compared_with_its_own_re_ef4839" before after/></p>

            <div className="grid grid-cols-2 gap-3 mt-5">
              <div>
                <div className="text-[12px] text-gray-500"><LocalizedText id="logistic_pr_auc_232cec" before after/></div>
                <div className="font-mono text-lg font-bold text-green-400 mt-1">
                  +0.0301
                </div>
              </div>

              <div>
                <div className="text-[12px] text-gray-500"><LocalizedText id="xgboost_pr_auc_4ddffe" before after/></div>
                <div className="font-mono text-lg font-bold text-blue-400 mt-1">
                  +0.0560
                </div>
              </div>
            </div>
          </div>

          <div className="bg-dark-bg border border-dark-border rounded-lg p-5">
            <div className="text-[12px] tracking-wider text-purple-400 font-bold"><LocalizedText id="2_consistent_signal_bd5f57" before after/></div>

            <div className="text-xl text-white font-bold mt-2"><LocalizedText id="credit_spread_relative_level_bcf294" before after/></div>

            <p className="text-xs text-gray-400 mt-2 leading-relaxed"><LocalizedText id="how_unusual_corporate_credit_stress_is_compared_with_its_own_rece_007142" before after/></p>

            <div className="grid grid-cols-2 gap-3 mt-5">
              <div>
                <div className="text-[12px] text-gray-500"><LocalizedText id="logistic_pr_auc_232cec" before after/></div>
                <div className="font-mono text-lg font-bold text-green-400 mt-1">
                  +0.0195
                </div>
              </div>

              <div>
                <div className="text-[12px] text-gray-500"><LocalizedText id="xgboost_pr_auc_4ddffe" before after/></div>
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
                tick={{ fontSize: 12 }}
                tickFormatter={(value) => value.toFixed(2)}
              />

              <YAxis
                type="category"
                dataKey="signal"
                width={155}
                stroke="#6b7280"
                tick={{ fontSize: 12 }}
              />

              <Tooltip
                contentStyle={{
                  backgroundColor: '#0b0f14',
                  border: '1px solid #26303d',
                  borderRadius: '6px',
                  fontSize: '14px',
                }}
                formatter={(value: number) => value.toFixed(4)}
              />

              <ReferenceLine x={0} stroke="#6b7280" />

              <Bar
                dataKey="logistic"
                name={t("Logistic ΔPR-AUC")}
                fill="#22c55e"
                barSize={8}
              />

              <Bar
                dataKey="xgboost"
                name={t("XGBoost ΔPR-AUC")}
                fill="#3b82f6"
                barSize={8}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div className="border-l-2 border-financial-green bg-dark-bg px-5 py-4">
          <div className="text-[12px] tracking-wider text-gray-500 font-bold"><LocalizedText id="what_did_the_model_learn_46553e" before after/></div>

          <p className="text-sm text-white font-semibold mt-2 leading-relaxed"><LocalizedText id="relative_volatility_and_credit_stress_provided_the_most_consisten_a3c66c" before after/></p>

          <p className="text-xs text-gray-400 mt-2 leading-relaxed"><LocalizedText id="in_simple_terms_the_model_benefits_more_from_knowing_how_unusual__b14ee1" before after/></p>
        </div>

        <div className="text-[12px] text-gray-500 leading-relaxed border-t border-dark-border pt-4"><LocalizedText id="lofo_measures_incremental_predictive_contribution_conditional_on__ac654a" before after/></div>
      </div></Disclosure>

      {/* Model Performance */}
      

      {/* Historical Crisis Validation */}
      
      <Disclosure label={t("Historical event case studies")} lazy><div className="bg-dark-card border border-dark-border p-6 rounded-lg space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h3 className="text-sm font-bold text-gray-200 tracking-wider"><LocalizedText id="historical_stress_case_studies_274444" before after/></h3>

            <p className="text-xs text-gray-400 mt-1"><LocalizedText id="descriptive_analysis_of_xgboost_walk_forward_oos_risk_scores_duri_a24e8c" before after/></p>
          </div>

          <select
            value={selectedEvent}
            onChange={(e) => setSelectedEvent(e.target.value)}
            className="bg-dark-bg border border-dark-border text-gray-200 text-xs rounded px-3 py-2 focus:outline-none focus:border-financial-blue font-mono"
          >
            {events.map((evt, idx) => (
              <option key={idx} value={evt.Event}>
                <LocalizedText>{evt.Event}</LocalizedText>
              </option>
            ))}
          </select>
        </div>

        {currentEvent && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-5 gap-4 pt-2">
              <div className="bg-dark-bg border border-dark-border p-4 rounded">
                <span className="text-xs text-gray-500 uppercase"><LocalizedText id="period_170a28" before after/></span>

                <p className="text-sm font-bold font-mono text-gray-200 mt-2">
                  <LocalizedText>{currentEvent.Start}</LocalizedText>
                </p>

                <p className="text-xs font-mono text-gray-500"><LocalizedText id="to_4374aa" before after/><LocalizedText>{currentEvent.End}</LocalizedText>
                </p>
              </div>

              <div className="bg-dark-bg border border-dark-border p-4 rounded">
                <span className="text-xs text-gray-500 uppercase"><LocalizedText id="event_window_679262" before after/></span>

                <p className="text-lg font-bold font-mono text-white mt-2">
                  <LocalizedText>{currentEvent.Days}</LocalizedText>
                </p>

                <p className="text-xs text-gray-500"><LocalizedText id="trading_days_ff1460" before after/></p>
              </div>

              <div className="bg-dark-bg border border-dark-border p-4 rounded">
                <span className="text-xs text-gray-500 uppercase"><LocalizedText id="10d_stress_window_days_83bb77" before after/></span>

                <p className="text-lg font-bold font-mono text-white mt-2">
                  <LocalizedText>{currentEvent['Actual Stress Days']}</LocalizedText>
                </p>

                <p className="text-xs text-gray-500"><LocalizedText id="target_defined_days_992962" before after/></p>
              </div>

              <div className="bg-dark-bg border border-dark-border p-4 rounded">
                <span className="text-xs text-gray-500 uppercase"><LocalizedText id="max_xgb_risk_score_9f92d8" before after/></span>

                <p className="text-lg font-bold font-mono text-financial-red mt-2">
                  <LocalizedText>{pct(currentEvent['XGB Max Prob'])}</LocalizedText>
                  <span className="text-xs text-gray-500 ml-1">/ 100</span>
                </p>
              </div>

              <div className="bg-dark-bg border border-dark-border p-4 rounded">
                <span className="text-xs text-gray-500 uppercase"><LocalizedText id="score_50_days_02b513" before after/></span>

                <p className="text-lg font-bold font-mono text-financial-amber mt-2">
                  <LocalizedText>{currentEvent['XGB >= 0.5 Days']}</LocalizedText>
                  <span className="text-xs text-gray-500 ml-1">
                    / <LocalizedText>{currentEvent.Days}</LocalizedText>
                  </span>
                </p>
              </div>
            </div>

            <div className="border-t border-dark-border pt-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                <div>
                  <span className="text-gray-500"><LocalizedText id="xgboost_average_oos_risk_score_bb2458" before after/></span>
                  <span className="font-mono text-gray-200 ml-2">
                    <LocalizedText>{pct(currentEvent['XGB Avg Prob'])}</LocalizedText> / 100
                  </span>
                </div>

                <div>
                  <span className="text-gray-500"><LocalizedText id="logistic_average_oos_risk_score_cbfc9a" before after/></span>
                  <span className="font-mono text-gray-200 ml-2">
                    <LocalizedText>{pct(currentEvent['Logistic Avg Prob'])}</LocalizedText> / 100
                  </span>
                </div>
              </div>
            </div>
                          {/* Historical OOS Risk Trajectory */}
              <div className="border-t border-dark-border pt-6 space-y-4">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                  <div>
                    <h4 className="text-xs font-bold text-gray-200 tracking-wider"><LocalizedText id="historical_oos_risk_trajectory_f07c1b" before after/></h4>
                    <p className="text-[12px] text-gray-500 mt-1"><LocalizedText id="xgboost_walk_forward_oos_risk_score_versus_spy_during_the_selecte_20ee77" before after/></p>
                  </div>

                  <div className="flex items-center gap-5 text-[12px] font-mono">
                    <div className="flex items-center gap-2 text-gray-400">
                      <span className="w-5 h-[2px] bg-financial-red" /><LocalizedText id="xgboost_10d_risk_score_3a0144" before after/></div>

                    <div className="flex items-center gap-2 text-gray-400">
                      <span className="w-5 h-[2px] bg-financial-blue" /><LocalizedText id="spy_price_899e31" before after/></div>
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
                        tick={{ fontSize: 12 }}
                        minTickGap={40}
                      />

                      <YAxis
                        yAxisId="risk"
                        domain={[0, 100]}
                        stroke="#F23645"
                        tick={{ fontSize: 12 }}
                        width={42}
                      />

                      <YAxis
                        yAxisId="spy"
                        orientation="right"
                        domain={['auto', 'auto']}
                        stroke="#4DA3FF"
                        tick={{ fontSize: 12 }}
                        width={55}
                      />

                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#111827',
                          border: '1px solid #374151',
                          borderRadius: '6px',
                          fontSize: '14px',
                        }}
                        labelStyle={{ color: '#9ca3af' }}
                        formatter={(value: number, name: string) => {
                          if (name === t('XGBoost 10D Risk Score')) {
                            return [`${value.toFixed(1)} / 100`, name];
                          }

                          if (name === t('SPY Price')) {
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
                          fontSize: 12,
                        }}
                      />

                      <Area
                        yAxisId="risk"
                        type="monotone"
                        dataKey="risk_score_xgboost"
                        name={t("XGBoost 10D Risk Score")}
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
                        name={t("SPY Price")}
                        stroke="#4DA3FF"
                        strokeWidth={2.2}
                        dot={false}
                        isAnimationActive={false}
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>

                <p className="text-[12px] text-gray-500 leading-relaxed"><LocalizedText id="the_dashed_50_line_is_a_fixed_reference_operating_threshold_not_a_1e5851" before after/></p>
              </div>

            {currentEvent.Event === '2023 US Banking Stress' && (
              <div className="bg-dark-bg border border-dark-border rounded p-4 text-xs text-gray-400 leading-relaxed"><LocalizedText id="the_march_april_2023_banking_turmoil_produced_elevated_model_scor_273aa3" before after/></div>
            )}
          </>
        )}

        <p className="text-[12px] text-gray-500 leading-relaxed"><LocalizedText id="historical_windows_are_descriptive_case_studies_based_strictly_on_8f2859" before after/></p>
      </div></Disclosure>
    </div>
  );
}