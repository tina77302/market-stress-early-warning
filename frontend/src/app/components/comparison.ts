import { finite, HistoryPoint } from './market-data';
export interface ComparisonResult { data: HistoryPoint[]; count: number; start?: string; end?: string; correlation: number | null; changeUS: number | null; changeKorea: number | null }
// Descriptive full-window z-scores, never used as model features or forecasts.
export function normalizeComparison(us: HistoryPoint[], korea: HistoryPoint[], usField: string, koreaField: string): ComparisonResult {
  const koreaByDate = new Map(korea.map(row => [row.date, row[koreaField]]));
  const pairs = us.flatMap(row => {
    const a = row[usField], b = koreaByDate.get(row.date);
    return finite(a) && finite(b) ? [{ date: row.date, a, b }] : [];
  });
  const empty: ComparisonResult = { data: [], count: pairs.length, correlation: null, changeUS: null, changeKorea: null };
  if (pairs.length < 20) return empty;
  const meanA = pairs.reduce((sum, row) => sum + row.a, 0) / pairs.length;
  const meanB = pairs.reduce((sum, row) => sum + row.b, 0) / pairs.length;
  const sdA = Math.sqrt(pairs.reduce((sum, row) => sum + (row.a - meanA) ** 2, 0) / pairs.length);
  const sdB = Math.sqrt(pairs.reduce((sum, row) => sum + (row.b - meanB) ** 2, 0) / pairs.length);
  if (!finite(sdA) || !finite(sdB) || sdA === 0 || sdB === 0) return empty;
  const data = pairs.map(row => ({ date: row.date, us: (row.a - meanA) / sdA, korea: (row.b - meanB) / sdB }));
  const correlation = data.reduce((sum, row) => sum + row.us * row.korea, 0) / data.length;
  const last = data[data.length - 1], previous = data[data.length - 21];
  return { data, count: data.length, start: data[0].date, end: last.date, correlation: finite(correlation) ? Math.max(-1, Math.min(1, correlation)) : null, changeUS: previous ? last.us - previous.us : null, changeKorea: previous ? last.korea - previous.korea : null };
}
