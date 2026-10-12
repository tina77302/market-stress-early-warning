'use client';

import React, { useEffect, useState } from 'react';
import { BarChart3, Database, ShieldCheck, AlertTriangle } from 'lucide-react';

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

interface ModelMetrics {
  roc_auc: number;
  pr_auc: number;
  brier_score: number;
  precision: number;
  recall: number;
  f1: number;
  false_alarm_rate: number;
}

interface ValidationData {
  market: string;
  forecast_horizon: string;
  validation_method: string;
  oos_start: string;
  oos_end: string;
  observations: number;
  positives: number;
  prevalence: number;
  warning_threshold: number;
  models: Record<string, ModelMetrics>;
  interpretation_note: string;
}

function fmt(v?: number, digits = 4) {
  return typeof v === 'number' ? v.toFixed(digits) : '---';
}

export default function KoreaValidationPage() {
  const [data, setData] = useState<ValidationData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetch(`${API_URL}/api/korea/validation`)
      .then((r) => {
        if (!r.ok) throw new Error('Validation API failed');
        return r.json();
      })
      .then((d) => {
        setData(d);
        setError(false);
      })
      .catch((e) => {
        console.error(e);
        setError(true);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center text-gray-400 font-mono">
        LOADING KOREA MODEL VALIDATION...
      </div>
    );
  }

  const logistic =
    data?.models?.logistic ??
    data?.models?.Logistic ??
    data?.models?.['Logistic Regression'];

  const xgb =
    data?.models?.xgboost ??
    data?.models?.XGBoost ??
    data?.models?.['XGBoost'];

  const rows = [
    ['ROC-AUC', logistic?.roc_auc, xgb?.roc_auc],
    ['PR-AUC', logistic?.pr_auc, xgb?.pr_auc],
    ['Brier Score', logistic?.brier_score, xgb?.brier_score],
    ['Precision', logistic?.precision, xgb?.precision],
    ['Recall', logistic?.recall, xgb?.recall],
    ['F1 Score', logistic?.f1, xgb?.f1],
    ['False Alarm Rate', logistic?.false_alarm_rate, xgb?.false_alarm_rate],
  ];

  return (
    <div className="space-y-6">
      <div className="bg-dark-card border border-dark-border rounded-lg p-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-xs font-mono text-financial-blue mb-2">
              KOREA MODEL VALIDATION
            </div>

            <h1 className="text-2xl font-bold text-white">
              Out-of-Sample Model Performance
            </h1>

            <p className="text-sm text-gray-500 mt-2">
              Purged walk-forward evaluation of Korea 10-trading-day
              market-stress models.
            </p>
          </div>

          <ShieldCheck className="w-9 h-9 text-financial-green" />
        </div>

        {error && (
          <div className="mt-4 text-sm text-financial-red">
            Korea validation API is unavailable.
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-dark-card border border-dark-border rounded-lg p-5">
          <div className="text-[11px] text-gray-500 uppercase">
            OOS Observations
          </div>
          <div className="text-3xl font-bold font-mono mt-2">
            {data?.observations?.toLocaleString() ?? '---'}
          </div>
        </div>

        <div className="bg-dark-card border border-dark-border rounded-lg p-5">
          <div className="text-[11px] text-gray-500 uppercase">
            Stress Positives
          </div>
          <div className="text-3xl font-bold font-mono mt-2">
            {data?.positives?.toLocaleString() ?? '---'}
          </div>
        </div>

        <div className="bg-dark-card border border-dark-border rounded-lg p-5">
          <div className="text-[11px] text-gray-500 uppercase">
            Target Prevalence
          </div>
          <div className="text-3xl font-bold font-mono mt-2">
            {typeof data?.prevalence === 'number'
              ? `${(data.prevalence * 100).toFixed(2)}%`
              : '---'}
          </div>
        </div>

        <div className="bg-dark-card border border-dark-border rounded-lg p-5">
          <div className="text-[11px] text-gray-500 uppercase">
            Warning Reference
          </div>
          <div className="text-3xl font-bold font-mono mt-2">
            {data?.warning_threshold ?? 50}
          </div>
          <div className="text-xs text-gray-600 mt-1">/ 100</div>
        </div>
      </div>

      <div className="bg-dark-card border border-dark-border rounded-lg p-6">
        <div className="flex items-center gap-2 mb-5">
          <BarChart3 className="w-5 h-5 text-financial-blue" />
          <h2 className="font-bold text-gray-200">
            LOGISTIC vs XGBOOST
          </h2>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-dark-border text-gray-500">
                <th className="text-left py-3">METRIC</th>
                <th className="text-right py-3">LOGISTIC</th>
                <th className="text-right py-3">XGBOOST</th>
              </tr>
            </thead>

            <tbody>
              {rows.map(([name, l, x]) => (
                <tr
                  key={name as string}
                  className="border-b border-dark-border/60"
                >
                  <td className="py-4 text-gray-300">
                    {name as string}
                  </td>

                  <td className="py-4 text-right font-mono text-gray-300">
                    {fmt(l as number)}
                  </td>

                  <td className="py-4 text-right font-mono text-white font-bold">
                    {fmt(x as number)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-dark-card border border-dark-border rounded-lg p-6">
          <div className="flex items-center gap-2 mb-4">
            <Database className="w-4 h-4 text-financial-blue" />
            <h2 className="font-bold text-gray-200">
              VALIDATION WINDOW
            </h2>
          </div>

          <div className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">OOS Start</span>
              <span className="font-mono">
                {data?.oos_start ?? '---'}
              </span>
            </div>

            <div className="flex justify-between">
              <span className="text-gray-500">OOS End</span>
              <span className="font-mono">
                {data?.oos_end ?? '---'}
              </span>
            </div>

            <div className="flex justify-between">
              <span className="text-gray-500">Forecast Horizon</span>
              <span>{data?.forecast_horizon ?? '10 Trading Days'}</span>
            </div>

            <div className="flex justify-between">
              <span className="text-gray-500">Method</span>
              <span className="text-right">
                {data?.validation_method ?? 'Purged Walk-Forward OOS'}
              </span>
            </div>
          </div>
        </div>

        <div className="bg-dark-card border border-dark-border rounded-lg p-6">
          <div className="flex items-center gap-2 mb-4">
            <AlertTriangle className="w-4 h-4 text-financial-amber" />
            <h2 className="font-bold text-gray-200">
              INTERPRETATION
            </h2>
          </div>

          <p className="text-sm leading-relaxed text-gray-400">
            {data?.interpretation_note ??
              'Metrics are calculated from strictly out-of-sample predictions. Model scores should not be interpreted as calibrated event probabilities.'}
          </p>

          <p className="text-xs leading-relaxed text-gray-600 mt-4">
            ROC-AUC measures ranking discrimination. PR-AUC emphasizes
            performance on stress events. Lower Brier Score and False Alarm
            Rate are preferable, while higher Precision, Recall and F1 are
            preferable.
          </p>
        </div>
      </div>
    </div>
  );
}
