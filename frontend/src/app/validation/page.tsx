'use client';

import React, { useEffect, useState } from 'react';
import { BarChart3, AlertOctagon, CheckCircle2, ShieldAlert } from 'lucide-react';

interface MetricRow {
  Model: string;
  'ROC-AUC': number;
  'PR-AUC': number;
  Precision: number;
  Recall: number;
  'F1 Score': number;
  'False Alarm Rate': number;
  'Missed Event Rate': number;
}

interface EventRow {
  Event: string;
  'Start-End': string;
  'Total Days': number;
  'XGB High Risk Days': number;
  'XGB Max Risk Prob': string;
  'XGB Avg Risk Prob': string;
}

export default function ModelValidationPage() {
  const [metrics, setMetrics] = useState<MetricRow[]>([]);
  const [events, setEvents] = useState<EventRow[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<string>('2008 Financial Crisis');

  useEffect(() => {
    async function fetchValidationData() {
      try {
        const res = await fetch('http://127.0.0.1:8000/api/validation');
        if (res.ok) {
          const data = await res.json();
          setMetrics(data.overall_metrics);
          setEvents(data.historical_events);
        }
      } catch (err) {
        console.error('Failed to fetch validation metrics:', err);
      }
    }
    fetchValidationData();
  }, []);

  const currentEvent = events.find(e => e.Event === selectedEvent) || events[0];

  return (
    <div className="space-y-8">
      {/* Section Header */}
      <div>
        <h1 className="text-xl font-bold text-white tracking-wider flex items-center space-x-2">
          <BarChart3 className="w-5 h-5 text-financial-green" />
          <span>PAGE 02 — MODEL VALIDATION & HISTORICAL BACKTEST</span>
        </h1>
        <p className="text-xs text-gray-400 mt-1">
          Rigorous Out-of-Sample Walk-Forward Validation without Data Leakage (2000–2026 Dataset).
        </p>
      </div>

      {/* Model Performance Comparison Table */}
      <div className="bg-dark-card border border-dark-border p-6 rounded-lg space-y-4">
        <h3 className="text-sm font-bold text-gray-200 tracking-wider">
          OVERALL OUT-OF-SAMPLE PERFORMANCE METRICS
        </h3>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs font-mono">
            <thead>
              <tr className="border-b border-dark-border bg-dark-bg text-gray-400">
                <th className="p-3">MODEL</th>
                <th className="p-3">ROC-AUC</th>
                <th className="p-3">PR-AUC</th>
                <th className="p-3">PRECISION</th>
                <th className="p-3">RECALL</th>
                <th className="p-3">F1 SCORE</th>
                <th className="p-3 text-financial-amber">FALSE ALARM RATE</th>
                <th className="p-3 text-financial-red">MISSED EVENT RATE</th>
              </tr>
            </thead>
            <tbody>
              {metrics.map((row, idx) => (
                <tr key={idx} className="border-b border-dark-border hover:bg-dark-hover transition-colors">
                  <td className="p-3 font-bold text-white flex items-center space-x-2">
                    {row.Model.includes('XGBoost') ? (
                      <CheckCircle2 className="w-4 h-4 text-financial-green" />
                    ) : (
                      <div className="w-4 h-4 rounded-full bg-gray-600" />
                    )}
                    <span>{row.Model}</span>
                  </td>
                  <td className="p-3 font-bold text-financial-blue">{row['ROC-AUC']}</td>
                  <td className="p-3 font-bold text-purple-400">{row['PR-AUC']}</td>
                  <td className="p-3">{row.Precision}</td>
                  <td className="p-3">{row.Recall}</td>
                  <td className="p-3 font-bold text-emerald-400">{row['F1 Score']}</td>
                  <td className="p-3 text-financial-amber">{row['False Alarm Rate']}</td>
                  <td className="p-3 text-financial-red">{row['Missed Event Rate']}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Historical Crisis Event Backtest Section */}
      <div className="bg-dark-card border border-dark-border p-6 rounded-lg space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h3 className="text-sm font-bold text-gray-200 tracking-wider">
              HISTORICAL CRISIS EVENT VALIDATION
            </h3>
            <p className="text-xs text-gray-400">
              Check how the XGBoost AI model responded during major past market shocks.
            </p>
          </div>

          {/* Crisis Dropdown Selector */}
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

        {/* Selected Crisis Summary Cards */}
        {currentEvent && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 pt-2">
            <div className="bg-dark-bg border border-dark-border p-4 rounded">
              <span className="text-xs text-gray-500 uppercase">Period</span>
              <p className="text-sm font-bold font-mono text-gray-200 mt-1">{currentEvent['Start-End']}</p>
            </div>
            <div className="bg-dark-bg border border-dark-border p-4 rounded">
              <span className="text-xs text-gray-500 uppercase">Total Event Window</span>
              <p className="text-lg font-bold font-mono text-white mt-1">{currentEvent['Total Days']} Trading Days</p>
            </div>
            <div className="bg-dark-bg border border-dark-border p-4 rounded">
              <span className="text-xs text-gray-500 uppercase">Max Risk Probability</span>
              <p className="text-lg font-bold font-mono text-financial-red mt-1">{currentEvent['XGB Max Risk Prob']}</p>
            </div>
            <div className="bg-dark-bg border border-dark-border p-4 rounded">
              <span className="text-xs text-gray-500 uppercase">High Risk Days (Prob &gt; 50%)</span>
              <p className="text-lg font-bold font-mono text-financial-amber mt-1">
                {currentEvent['XGB High Risk Days']} / {currentEvent['Total Days']} Days
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
