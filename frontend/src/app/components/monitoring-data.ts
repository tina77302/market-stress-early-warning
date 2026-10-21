import type { HistoryPoint, Market } from './market-data';
import retrospectiveArchive from './retrospective-observations.json';
import usRetrospectiveArchive from './us-retrospective-observations.json';

export type Health = 'CURRENT' | 'STALE' | 'INCOMPLETE' | 'UNAVAILABLE';
export interface MonitoringRecord {
  record_id: string; publication_sequence: number; market: Market;
  generated_at: string; observation_date: string; record_type: 'LIVE' | 'RETROSPECTIVE';
  risk_score: number | null; operational_warning: boolean | null;
  msi: number | null; msi_stress_event: boolean | null;
  data_status: Health; data_freshness_status: Health;
  model_sha256: string | null; input_snapshot_sha256: string | null; source_history_sha256: string | null;
}
export interface MonitoringLatest { market: Market; record: MonitoringRecord | null; archive?: ArchiveEvidence;
  inputs?: {index:number|null; volatility:number|null; credit:number|null}; current_data_health: { status: Health } }
export interface MonitoringHistory { records: MonitoringRecord[]; next_before_sequence: number | null }
export type TimelineSource = 'LIVE' | 'RETROSPECTIVE' | 'OOS';
export interface TimelinePoint {
  id: string; date: string; score: number | null; msi: number | null;
  movement: number | null; warning: boolean | null; stress: boolean | null;
  published: string | null; health: Health | null; source: TimelineSource;
  record: MonitoringRecord | null; archive?: ArchiveEvidence;
  inputs?: {index:number|null; volatility:number|null; credit:number|null};
}
const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
const numeric = (value: unknown) => finite(value) ? value : null;
export function recordsForMarket(rows: unknown, market: Market, type: 'LIVE' | 'RETROSPECTIVE'): MonitoringRecord[] {
  return Array.isArray(rows) ? rows.filter((row): row is MonitoringRecord => !!row && row.market === market && row.record_type === type &&
    typeof row.record_id === 'string' && Number.isSafeInteger(row.publication_sequence) &&
    /^\d{4}-\d{2}-\d{2}$/.test(row.observation_date) && typeof row.generated_at === 'string' &&
    /(?:Z|[+-]\d{2}:\d{2})$/.test(row.generated_at) && Number.isFinite(Date.parse(row.generated_at))) : [];
}
export function publicationPoints(rows: MonitoringRecord[]): TimelinePoint[] {
  return rows.map(row => ({id: row.record_id, date: row.observation_date, score: numeric(row.risk_score), msi: numeric(row.msi),
    movement: null, warning: typeof row.operational_warning === 'boolean' ? row.operational_warning : null,
    stress: typeof row.msi_stress_event === 'boolean' ? row.msi_stress_event : null, published: row.generated_at,
    health: row.data_status, source: row.record_type, record: row}));
}
export function historicalPoints(rows: HistoryPoint[], market: Market): TimelinePoint[] {
  const sorted = rows.filter(row => (!row.market || row.market === market) && !(market === 'korea' ? row.spy != null && row.kospi200 == null : row.kospi200 != null && row.spy == null)).sort((a,b) => a.date.localeCompare(b.date));
  return sorted.map((row, i) => {
    const close = numeric(row[market === 'korea' ? 'kospi200' : 'spy']);
    const previous = i ? numeric(sorted[i-1][market === 'korea' ? 'kospi200' : 'spy']) : null;
    return {id:`oos-${market}-${row.date}`, date:row.date, score:numeric(row.risk_score_xgboost), msi:numeric(row.msi),
      movement:close !== null && previous !== null && previous > 0 ? (close / previous - 1) * 100 : null,
      warning:null, stress:null, published:null, health:null, source:'OOS', record:null,
      inputs:{index:close,volatility:numeric(row[market==='korea'?'vkospi':'vix']),credit:numeric(row[market==='korea'?'korea_credit_spread_bp':'baa_treasury_spread'])}};
  });
}
/** One primary observation per date. All publication identities remain in combinedPoints. */
export function datedPoints(points: TimelinePoint[]): TimelinePoint[] {
  const dates = new Map<string, TimelinePoint>();
  for (const point of points) {
    const previous = dates.get(point.date);
    const priority = (p: TimelinePoint) => p.source === 'LIVE' ? 3 : p.record ? 2 : p.archive ? 1 : 0;
    if (!previous || priority(point) > priority(previous) || (priority(point) === priority(previous) && ((point.record?.publication_sequence ?? 0) > (previous.record?.publication_sequence ?? 0) || (!(point.record && previous.record) && Date.parse(point.published ?? '') > Date.parse(previous.published ?? ''))))) dates.set(point.date, point);
  }
  return Array.from(dates.values()).sort((a,b) => a.date.localeCompare(b.date));
}
export function trajectory(points: TimelinePoint[], selectedDate: string) {
  const index = points.findIndex(point => point.date === selectedDate);
  const current = points[index]; const previous = points[index-1];
  const change = current?.score != null && previous?.score != null && current.source === previous.source ? current.score - previous.score : null;
  let increases = 0;
  for (let i=index; i>0 && points[i].score !== null && points[i-1].score !== null && points[i].score! > points[i-1].score! && points[i].source === points[i-1].source; i--) increases++;
  const older = points[index-5];
  const speed = current?.score != null && older?.score != null && points.slice(index-5,index+1).every(p=>p.source===current.source) ? (current.score - older.score)/5 : null;
  const recent = points.slice(Math.max(0,index-4),index+1);
  const steps = recent.slice(1).filter((p,i)=>p.score!==null && recent[i].score!==null && p.source===recent[i].source);
  const risingSteps = steps.filter(p=>p.score! > recent[recent.indexOf(p)-1].score!).length;
  return {change, speed, increases, risingSteps, steps:steps.length};
}
export function publicationTime(value: string | null, locale: string) {
  if (!value || !/(?:Z|[+-]\d{2}:\d{2})$/.test(value) || !Number.isFinite(Date.parse(value))) return '—';
  return new Intl.DateTimeFormat(locale, {year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23',timeZone:'Asia/Seoul'}).format(new Date(value)) + ' KST';
}
/** Hash presence is provenance availability, never independent verification. */
export function provenance(record: MonitoringRecord | null) {
  if (!record) return 'Not recorded';
  const hash = (value: unknown) => typeof value === 'string' && /^[a-f0-9]{64}$/i.test(value);
  return [record.model_sha256, record.input_snapshot_sha256, record.source_history_sha256].every(hash) ? 'Fingerprints recorded · not independently verified' : 'Provenance incomplete';
}

/** Frontend display evidence only: never promoted to publication-ledger records. */
export interface ArchiveEvidence { basis: string; snapshotId: string | null; modelSha256: string; sourceSha256: string; pitVerified?: boolean }

export function pointSourceLabel(point: TimelinePoint): string {
  return point.archive?.pitVerified === false ? 'Retrospective · PIT not verified' : point.source === 'OOS' ? 'HISTORICAL OOS' : point.source;
}

export const usReplayUnavailableDates = usRetrospectiveArchive.unavailable_dates;

export function archivePoints(market: Market): TimelinePoint[] {
  if (market === 'us') return usRetrospectiveArchive.observations.map(row => ({
    id:`archive-us-${row.date}`,date:row.date,score:row.score,msi:row.msi,movement:null,
    warning:row.warning,stress:row.stress,published:null,health:null,source:'RETROSPECTIVE',record:null,
    archive:{basis:row.basis,snapshotId:null,modelSha256:usRetrospectiveArchive.model_sha256,
      sourceSha256:usRetrospectiveArchive.source_history_sha256,pitVerified:false},
  }));
  if (market !== retrospectiveArchive.market) return [];
  return retrospectiveArchive.observations.map(row=>({id:`archive-${market}-${row.date}`,date:row.date,score:row.score,msi:row.msi,movement:row.movement,
    warning:row.warning,stress:row.stress,published:row.published,health:null,source:'RETROSPECTIVE',record:null,
    archive:{basis:row.basis,snapshotId:row.snapshot_id,modelSha256:retrospectiveArchive.model_sha256,sourceSha256:retrospectiveArchive.replay_csv_sha256}}));
}
export function availablePoints(history: HistoryPoint[], market: Market, live: MonitoringRecord[], retrospective: MonitoringRecord[]): TimelinePoint[] {
  return [...historicalPoints(history,market),...archivePoints(market),...publicationPoints(recordsForMarket(retrospective,market,'RETROSPECTIVE')),...publicationPoints(recordsForMarket(live,market,'LIVE'))];
}

/** Identity, never observation date, determines duplication. Distinct publications survive. */
export function combinedPoints(points: TimelinePoint[]): TimelinePoint[] {
  const unique = new Map<string, TimelinePoint>();
  for (const point of points) {
    const identity = point.record ? `publication:${point.record.market}:${point.record.record_id}` : `${point.source}:${point.id}`;
    if (!unique.has(identity)) unique.set(identity, point);
  }
  return Array.from(unique.values()).sort((a,b) => a.date.localeCompare(b.date) ||
    ((a.published ? Date.parse(a.published) : 0)-(b.published ? Date.parse(b.published) : 0)) || a.id.localeCompare(b.id));
}
/** A recent historical context is extended by LIVE evidence, never replaced by it. */
export function buildUpWindow(points: TimelinePoint[], count: number): TimelinePoint[] {
  if (!count) return points;
  const context = points.filter(p => p.source !== 'LIVE');
  const dates = Array.from(new Set((context.length ? context : points).map(p => p.date)));
  const start = dates[Math.max(0, dates.length-count)];
  return points.filter(p => p.date >= start || p.source === 'LIVE');
}
/** Compare with an earlier observation of the same provenance, never a same-day republication. */
export function pointTrajectory(points: TimelinePoint[], id: string) {
  const selected = points.find(p => p.id === id);
  const prior = selected ? datedPoints(points.filter(p => p.source === selected.source && p.date < selected.date)) : [];
  return trajectory(selected ? [...prior, selected] : [], selected?.date ?? '');
}

/** Independent context layers: same-date LIVE precedence must not erase OOS context. */
export function chartContext(points: TimelinePoint[], count: number): TimelinePoint[] {
  const historical = datedPoints(points.filter(p => p.source === 'OOS'));
  const context = count ? historical.slice(-count) : historical;
  const evidence = buildUpWindow(datedPoints(points.filter(p => p.source !== 'OOS')), count);
  return combinedPoints([...context, ...evidence]);
}

/** Publication order is authoritative; a same-date republication is not a risk step. */
export function liveRiskTrend(records: MonitoringRecord[]) {
  const ordered = [...records].filter(r => r.record_type === 'LIVE').sort((a,b) => b.publication_sequence-a.publication_sequence);
  const current = ordered[0];
  const previous = current && ordered.find(r => r.market === current.market && r.observation_date < current.observation_date);
  if (!current || !previous || !finite(current.risk_score) || !finite(previous.risk_score)) return null;
  return {current, previous, change: current.risk_score-previous.risk_score,
    cleared: previous.operational_warning === true && current.operational_warning === false &&
      previous.risk_score >= 50 && current.risk_score < 50};
}
