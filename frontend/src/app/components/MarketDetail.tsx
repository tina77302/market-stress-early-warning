'use client';

import { LocalizedText, useI18n } from '../i18n/provider';


import { useMemo, useState } from 'react';
import Link from 'next/link';
import { CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { finite, modelAvailable, fmt, HistoryPoint, Market, signal, useMarket } from './market-data';
import DataHealthNotice from './DataHealthNotice';
import { KoreaMonitorHero, KoreaSignals, KoreaIndustryResearch } from './KoreaMonitor';
import MarketRiskTimeline from './MarketRiskTimeline';
import { ShieldAlert } from 'lucide-react';
import MarketMonitorCard from './MarketMonitorCard';
import { ModelDisclaimer } from './CrossMarketSnapshot';
import MonitoringConsole from './MonitoringConsole';

export function HistoryChart({ data, fields, sharedScale = false }: { data: HistoryPoint[]; sharedScale?: boolean; fields: { key: string; label: string; color: string }[] }) {
  const { t, locale } = useI18n();

  if (!data.some(row => fields.some(field => finite(row[field.key])))) return <div className="chart-empty"><LocalizedText id="historical_data_unavailable_for_these_indicators_ee1177"/></div>;
  return <ResponsiveContainer width="100%" height="100%"><ComposedChart data={data}><CartesianGrid stroke="#203445" vertical={false}/><XAxis dataKey="date" minTickGap={55} tick={{ fill: '#8ba2b7', fontSize: 12 }}/>{fields.filter((_, i) => !sharedScale || i === 0).map((field, i) => <YAxis key={field.key} yAxisId={i} orientation={i === 1 ? 'right' : 'left'} domain={field.key === 'risk_score_xgboost' ? [0, 100] : ['auto', 'auto']} tick={{ fill: field.color, fontSize: 12 }}/>) }<Tooltip contentStyle={{ background: '#0b1a27', border: '1px solid #3c5b70', borderRadius: 10 }} formatter={(value: number) => fmt(value, 3)}/>{fields.map((field, i) => <Line key={field.key} yAxisId={sharedScale ? 0 : i} dataKey={field.key} name={t(String(field.label))} stroke={field.color} dot={false} strokeWidth={1.7} isAnimationActive={false}/>)}</ComposedChart></ResponsiveContainer>;
}
export default function MarketDetail({market}:{market:Market}) {
  const state=useMarket(market);
  return <MonitoringConsole market={market} {...state}/>;
}
