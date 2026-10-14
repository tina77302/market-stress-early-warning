'use client';

import { LocalizedText, useI18n } from '../i18n/provider';


import { ReactNode, useEffect, useState } from 'react';
import Link from 'next/link';
import Disclosure from './Disclosure';
import MarketSwitcher from './MarketSwitcher';
import { ModelDisclaimer } from './CrossMarketSnapshot';
import { finite, Market } from './market-data';

interface Model {
  model: string;
  roc_auc?: number; pr_auc?: number; brier_score?: number; f1?: number;
  precision?: number; recall?: number; false_alarm_rate?: number; missed_event_rate?: number;
  threshold?: number; tp?: number; fp?: number; tn?: number; fn?: number;
}
interface KoreaResponse {
  models: Model[]; oos_observations: number; positive_observations: number; target_prevalence: number;
  oos_start: string; oos_end: string; forecast_horizon: string; validation_method: string;
  warning_threshold: number; interpretation_note: string;
}
interface USModel {
  Model: string; 'ROC-AUC': number; 'PR-AUC (AP)': number; 'Brier Score': number;
  F1: number; Precision: number; Recall: number; 'False Alarm Rate': number; 'Missed Event Rate': number;
  Threshold: number; TP: number; FP: number; TN: number; FN: number;
}
interface USResponse { overall_metrics: USModel[] }
interface USMetadataResponse { data: { Horizon: string; Model: string; OOS_Observations: number; OOS_Start: string; OOS_End: string; ROC_AUC: number; PR_AUC: number; Brier: number; 'F1_0.5': number }[] }
export interface ValidationSummary {
  models: Model[]; observations?: number; positives?: number; prevalence?: number;
  start?: string; end?: string; horizon: string; method: string; threshold?: number; note?: string;
}
export function mapKoreaValidation(response: KoreaResponse): ValidationSummary {
  if (!response || !Array.isArray(response.models) || response.models.some(model => !model || typeof model.model !== 'string')) throw new Error('Invalid Korea validation response');
  return { models: response.models, observations: response.oos_observations, positives: response.positive_observations, prevalence: response.target_prevalence, start: response.oos_start, end: response.oos_end, horizon: response.forecast_horizon === '10D' ? '10 Trading Days' : response.forecast_horizon, method: response.validation_method, threshold: response.warning_threshold, note: response.interpretation_note };
}
export function mapUSValidation(response: USResponse, metadata: USMetadataResponse | null): ValidationSummary {
  if (!response || !Array.isArray(response.overall_metrics) || response.overall_metrics.some(model => !model || typeof model.Model !== 'string')) throw new Error('Invalid U.S. validation response');
  const models = response.overall_metrics.map(row => ({ model: row.Model, roc_auc: row['ROC-AUC'], pr_auc: row['PR-AUC (AP)'], brier_score: row['Brier Score'], f1: row.F1, precision: row.Precision, recall: row.Recall, false_alarm_rate: row['False Alarm Rate'], missed_event_rate: row['Missed Event Rate'], threshold: row.Threshold, tp: row.TP, fp: row.FP, tn: row.TN, fn: row.FN }));
  const reference = models.find(model => model.model === 'XGBoost');
  const counts = reference ? [reference.tp, reference.fp, reference.tn, reference.fn] : [];
  const observations = counts.length === 4 && counts.every(finite) ? counts.reduce<number>((sum, value) => sum + (value as number), 0) : undefined;
  const positives = reference && finite(reference.tp) && finite(reference.fn) ? reference.tp + reference.fn : undefined;
  const period = Array.isArray(metadata?.data) ? metadata.data.find(row => row.Horizon === '10D' && row.Model === 'XGBoost' && row.OOS_Observations === observations && [[row.ROC_AUC, reference?.roc_auc], [row.PR_AUC, reference?.pr_auc], [row.Brier, reference?.brier_score], [row['F1_0.5'], reference?.f1]].every(([a, b]) => finite(a) && finite(b) && Math.abs(a - b) < 1e-8)) : undefined;
  return { models, observations, positives, prevalence: finite(positives) && finite(observations) && observations > 0 ? positives / observations : undefined, start: period?.OOS_Start, end: period?.OOS_End, horizon: '10 Trading Days', method: 'Purged expanding walk-forward OOS', threshold: reference?.threshold };
}
type Key = Exclude<keyof Model, 'model'>;
const primary: [string, Key][] = [['ROC-AUC', 'roc_auc'], ['PR-AUC', 'pr_auc'], ['F1 Score', 'f1'], ['Brier Score', 'brier_score']];
const secondary: [string, Key][] = [['Precision', 'precision'], ['Recall', 'recall'], ['False Alarm Rate', 'false_alarm_rate'], ['Missed Event Rate', 'missed_event_rate'], ['True Positives (TP)', 'tp'], ['False Positives (FP)', 'fp'], ['True Negatives (TN)', 'tn'], ['False Negatives (FN)', 'fn']];
const behavior: [string, Key][] = [['Precision', 'precision'], ['Recall', 'recall'], ['False Alarm Rate', 'false_alarm_rate'], ['Missed Event Rate', 'missed_event_rate']];
const lowerPreferred = (key: Key) => ['brier_score', 'false_alarm_rate', 'missed_event_rate'].includes(key);
const format = (value: unknown, digits = 4) => finite(value) ? value.toFixed(digits) : 'Unavailable';
const scale = (value: unknown) => finite(value) ? `${(value * 100).toFixed(0)} / 100` : 'Unavailable';
function MetricTable({ models, metrics }: { models: Model[]; metrics: [string, Key][] }) {
  const { t, locale } = useI18n();

  const selected = ['Logistic Regression', 'XGBoost'].map(name => models.find(model => model.model === name));
  return <div className="table-scroll"><table className="research-table"><thead><tr><th scope="col"><LocalizedText id="metric_b2bb76"/></th><th scope="col"><LocalizedText id="logistic_regression_32ac4d" after/><span className="deployment-label"><LocalizedText id="baseline_e6ab79"/></span></th><th scope="col"><LocalizedText id="xgboost_e63bae" after/><span className="deployment-label"><LocalizedText id="deployment_327a55"/></span></th></tr></thead><tbody>{metrics.map(([label, key]) => <tr key={key}><th scope="row"><LocalizedText>{label}</LocalizedText></th>{selected.map((model, index) => <td key={index} className={index === 1 ? 'deployment-value' : undefined}><LocalizedText>{format(model?.[key], ['tp', 'fp', 'tn', 'fn'].includes(key) ? 0 : 4)}</LocalizedText></td>)}</tr>)}</tbody></table></div>;
}
export function performanceInterpretation(models: Model[]): string {
  const baseline = models.find(model => model.model === 'Logistic Regression');
  const deployed = models.find(model => model.model === 'XGBoost');
  if (!baseline || !deployed) return 'A complete model comparison is unavailable.';
  const comparisons: [string, Key, boolean][] = [['ROC-AUC', 'roc_auc', false], ['PR-AUC', 'pr_auc', false], ['Brier loss', 'brier_score', true], ['F1', 'f1', false]];
  const findings = comparisons.flatMap(([label, key, lower]) => {
    const a = baseline[key], b = deployed[key];
    if (!finite(a) || !finite(b)) return [];
    if (a.toFixed(4) === b.toFixed(4)) return [`${label} is equal at displayed precision`];
    const winner = (lower ? b < a : b > a) ? 'XGBoost' : 'Logistic Regression';
    return [`${winner} has ${lower ? 'lower' : 'higher'} ${label}`];
  });
  return findings.length ? `${findings.join('; ')} in this 10D OOS sample.` : 'Model comparison metrics are unavailable.';
}
function MetricComparison({ models, metrics = primary }: { models: Model[]; metrics?: [string, Key][] }) {
  const { t, locale } = useI18n();

  const selected = models.filter(model => ['Logistic Regression', 'XGBoost'].includes(model.model));
  return <div className="metric-comparison">
    <div className="comparison-model-labels">{selected.map(model => <span key={model.model}><LocalizedText>{model.model}</LocalizedText><small><LocalizedText>{model.model === 'XGBoost' ? 'Deployment' : 'Baseline'}</LocalizedText></small></span>)}</div>
    {metrics.map(([label, key]) => <div className="metric-comparison-row" key={key}><div className="metric-comparison-title"><h3><LocalizedText>{label}</LocalizedText></h3><small><LocalizedText>{lowerPreferred(key) ? 'Lower is better' : 'Higher is better'}</LocalizedText><LocalizedText id="0_1_scale_9a6ba9" before/></small></div><div className="metric-bar-pair">{selected.map(model => <div className={`metric-bar-row ${model.model === 'XGBoost' ? 'deployed' : 'baseline'}`} key={model.model}><span className="metric-bar-model"><LocalizedText>{model.model}</LocalizedText></span><div className="metric-bar-track" aria-hidden="true">{finite(model[key]) && <span style={{ width: `${Math.max(0, Math.min(1, model[key])) * 100}%` }}/>}</div><strong><LocalizedText>{format(model[key])}</LocalizedText></strong></div>)}</div></div>)}
    {!selected.length && <p><LocalizedText id="model_performance_unavailable_88107b"/></p>}
  </div>;
}
function ConfusionMatrices({ models }: { models: Model[] }) {
  const { t, locale } = useI18n();

  const selected = models.filter(model => ['Logistic Regression', 'XGBoost'].includes(model.model));
  return <div className="confusion-matrices">{selected.map(model => <figure className="confusion-figure" key={model.model}>
    <figcaption><strong><LocalizedText>{model.model}</LocalizedText></strong><span><LocalizedText>{model.model === 'XGBoost' ? 'Deployment' : 'Baseline'}</LocalizedText></span></figcaption>
    <table className="confusion-matrix"><caption><LocalizedText id="actual_10_day_target_predicted_warning_37e145"/></caption><thead><tr><td/><th scope="col"><LocalizedText id="no_warning_134451"/></th><th scope="col"><LocalizedText id="warning_e9c455"/></th></tr></thead><tbody>
      <tr><th scope="row"><LocalizedText id="no_stress_target_0e2dac"/></th><td className="outcome-tn"><strong><LocalizedText>{finite(model.tn) ? model.tn.toLocaleString(locale) : 'Unavailable'}</LocalizedText></strong><span><LocalizedText id="tn_correct_non_warning_a6111d"/></span></td><td className="outcome-fp"><strong><LocalizedText>{finite(model.fp) ? model.fp.toLocaleString(locale) : 'Unavailable'}</LocalizedText></strong><span><LocalizedText id="fp_false_alarm_9c4603"/></span></td></tr>
      <tr><th scope="row"><LocalizedText id="stress_target_c5acc2"/></th><td className="outcome-fn"><strong><LocalizedText>{finite(model.fn) ? model.fn.toLocaleString(locale) : 'Unavailable'}</LocalizedText></strong><span><LocalizedText id="fn_missed_stress_e9ceea"/></span></td><td className="outcome-tp"><strong><LocalizedText>{finite(model.tp) ? model.tp.toLocaleString(locale) : 'Unavailable'}</LocalizedText></strong><span><LocalizedText id="tp_detected_stress_2d3bba"/></span></td></tr>
    </tbody></table>
  </figure>)}</div>;
}
export function modelTradeoffs(models: Model[]): { deployment: string[]; baseline: string[]; equal: string[] } {
  const baseline = models.find(model => model.model === 'Logistic Regression');
  const deployment = models.find(model => model.model === 'XGBoost');
  const result: { deployment: string[]; baseline: string[]; equal: string[] } = { deployment: [], baseline: [], equal: [] };
  if (!baseline || !deployment) return result;
  for (const [label, key] of [...primary, ...behavior]) {
    const a = baseline[key], b = deployment[key];
    if (!finite(a) || !finite(b)) continue;
    if (a.toFixed(4) === b.toFixed(4)) { result.equal.push(label); continue; }
    const benefit = `${lowerPreferred(key) ? 'Lower' : 'Higher'} ${label}`;
    (lowerPreferred(key) ? b < a : b > a) ? result.deployment.push(benefit) : result.baseline.push(benefit);
  }
  return result;
}
function ModelSelectionSummary({ models }: { models: Model[] }) {
  const { t, locale } = useI18n();

  const tradeoffs = modelTradeoffs(models);
  return <div className="selection-summary"><div className="selection-summary-heading"><span className="deployment-label"><LocalizedText id="configured_deployment_19df80"/></span><strong><LocalizedText id="xgboost_e63bae"/></strong><p><LocalizedText id="validation_evidence_for_the_deployed_model_s_operating_trade_offs_368d87"/></p></div><div className="selection-tradeoffs">
    <div><h3><LocalizedText id="xgboost_advantages_269e49"/></h3>{tradeoffs.deployment.length ? <ul>{tradeoffs.deployment.map(label => <li key={label}><LocalizedText>{label}</LocalizedText></li>)}</ul> : <p><LocalizedText id="no_measurable_advantage_in_available_metrics_b7e559"/></p>}</div>
    <div><h3><LocalizedText id="logistic_regression_advantages_ee2ac8"/></h3>{tradeoffs.baseline.length ? <ul>{tradeoffs.baseline.map(label => <li key={label}><LocalizedText>{label}</LocalizedText></li>)}</ul> : <p><LocalizedText id="no_measurable_advantage_in_available_metrics_b7e559"/></p>}</div>
  </div>{!!tradeoffs.equal.length && <p><LocalizedText id="equal_at_displayed_precision_d6ebb4" after/><LocalizedText>{tradeoffs.equal.join(', ')}</LocalizedText>.</p>}<p className="selection-caveat"><LocalizedText id="the_configured_model_choice_is_unchanged_these_oos_trade_offs_do__1387d9"/></p></div>;
}
export function ValidationContent({ data }: { data: ValidationSummary }) {
  const { t, locale } = useI18n();

  return <>
    <section className="research-section"><h2><span>01</span><LocalizedText id="oos_sample_16a910"/></h2><dl className="sample-summary validation-sample">
      <div className="validation-period"><dt><LocalizedText id="validation_period_f56783"/></dt><dd className="sample-period"><LocalizedText>{data.start || 'Unavailable'}</LocalizedText> – <LocalizedText>{data.end || 'Unavailable'}</LocalizedText></dd></div>
      <div><dt><LocalizedText id="oos_observations_fd94ed"/></dt><dd><LocalizedText>{finite(data.observations) ? data.observations.toLocaleString(locale) : 'Unavailable'}</LocalizedText></dd></div>
      <div><dt><LocalizedText id="stress_positives_aff361"/></dt><dd><LocalizedText>{finite(data.positives) ? data.positives.toLocaleString(locale) : 'Unavailable'}</LocalizedText></dd></div>
      <div><dt><LocalizedText id="target_prevalence_dd056d"/></dt><dd><LocalizedText>{finite(data.prevalence) ? `${(data.prevalence * 100).toFixed(2)}%` : 'Unavailable'}</LocalizedText></dd></div>
      <div><dt><LocalizedText id="forecast_horizon_817734"/></dt><dd className="sample-period"><LocalizedText>{data.horizon || 'Unavailable'}</LocalizedText></dd></div>
    </dl></section>
    <section className="research-section"><h2><span>02</span><LocalizedText id="model_performance_66f59a"/></h2><MetricComparison models={data.models}/><p className="comparison-note"><LocalizedText id="all_bars_use_the_full_0_1_scale_exact_values_appear_alongside_eac_2f80d3"/></p></section>
    <section className="research-section"><h2><span>03</span><LocalizedText id="classification_performance_5490bd"/></h2><p><LocalizedText id="fixed_warning_reference_ec6fcc" after/><strong><LocalizedText>{scale(data.threshold)}</LocalizedText></strong><LocalizedText id="counts_refer_to_the_next_10_trading_days_stress_target_dcfbfb" before/></p><ConfusionMatrices models={data.models}/><div className="classification-behavior"><h3><LocalizedText id="classification_behavior_8a6eda"/></h3><MetricComparison models={data.models} metrics={behavior}/></div>
      <Disclosure label={t("View detailed metrics")}><MetricTable models={data.models} metrics={[...primary, ...secondary, ['Reference Threshold (raw score)', 'threshold']]}/><p><LocalizedText id="rates_use_a_0_1_scale_tp_fp_tn_and_fn_are_observation_counts_stre_1d69a0"/></p><p><LocalizedText id="api_reported_classification_thresholds_2d739c" after/><LocalizedText>{data.models.map(model => `${model.model}: ${scale(model.threshold)}`).join(' · ')}</LocalizedText>.</p><p><LocalizedText id="the_0_50_raw_score_reference_equals_50_100_on_the_dashboard_scale_fa8485"/></p><p><LocalizedText id="roc_auc_measures_ranking_discrimination_pr_auc_emphasizes_stress__43f4c5"/></p><p><LocalizedText id="precision_tp_tp_fp_recall_tp_tp_fn_false_alarm_rate_fp_fp_tn_miss_0da18c"/></p></Disclosure>
    </section>
    <section className="research-section"><h2><span>04</span><LocalizedText id="model_selection_interpretation_dc8ab6"/></h2><ModelSelectionSummary models={data.models}/><ul className="validation-interpretation"><li><LocalizedText id="purged_expanding_walk_forward_oos_evaluation_d381c0"/></li><li><LocalizedText id="fixed_reference_threshold_not_optimized_on_oos_results_af3e7a"/></li><li><LocalizedText id="historical_oos_performance_does_not_guarantee_future_performance_b14daf"/></li></ul><Disclosure label={t("Validation design & limitations")}><p><LocalizedText>{data.method}</LocalizedText><LocalizedText id="forecast_horizon_504075" after/><LocalizedText>{data.horizon}</LocalizedText>.</p>{data.note && <p><LocalizedText>{data.note}</LocalizedText></p>}<p><LocalizedText id="expanding_training_windows_preserve_chronological_evaluation_rand_e8001e"/></p><p><LocalizedText id="model_scores_are_not_calibrated_event_probabilities_threshold_bas_194364"/></p></Disclosure></section>
  </>;
}
export default function ValidationOverview({ market, children }: { market: Market; children?: ReactNode }) {
  const { t, locale } = useI18n();

  const [data, setData] = useState<ValidationSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const korea = market === 'korea', name = korea ? 'Korea' : 'U.S.';
  useEffect(() => {
    const controller = new AbortController();
    setData(null); setLoading(true); setError(false);
    const base = '';
    async function request(path: string) { const response = await fetch(`${base}${path}`, { signal: controller.signal }); if (!response.ok) throw new Error(path); return response.json(); }
    async function load() {
      try {
        let summary: ValidationSummary;
        if (korea) summary = mapKoreaValidation(await request('/api/korea/validation'));
        else {
          const [metrics, metadata] = await Promise.allSettled([request('/api/validation'), request('/api/multi-horizon-validation')]);
          if (metrics.status === 'rejected') throw new Error('Validation unavailable');
          summary = mapUSValidation(metrics.value, metadata.status === 'fulfilled' ? metadata.value : null);
        }
        if (!controller.signal.aborted) setData(summary);
      } catch { if (!controller.signal.aborted) setError(true); }
      finally { if (!controller.signal.aborted) setLoading(false); }
    }
    void load(); return () => controller.abort();
  }, [korea, refresh]);
  return <div className="risk-home detail-page research-page"><div className="home-content"><header className="detail-heading"><div className="eyebrow"><LocalizedText id="model_validation_78b3dc"/></div><MarketSwitcher market={market} section="validation"/><h1><LocalizedText id="10_day_out_of_sample_performance_7c91cc"/></h1><p><LocalizedText>{name}</LocalizedText><LocalizedText id="independent_market_model_10_trading_days_purged_walk_forward_oos_fad161" before/></p><div className="market-subnav"><Link href={korea ? '/korea' : '/us'}><LocalizedText>{name}</LocalizedText><LocalizedText id="market_8ab31f" before/></Link><Link href={korea ? '/korea/methodology' : '/methodology'}><LocalizedText>{name}</LocalizedText><LocalizedText id="methodology_964e6e" before/></Link></div></header><LocalizedText>{loading && <div className="api-notice" role="status"><LocalizedText id="loading_8f26c6" after/><LocalizedText>{name}</LocalizedText><LocalizedText id="validation_25680e" before/></div>}<LocalizedText></LocalizedText>{error && <div className="api-notice" role="alert"><LocalizedText>{name}</LocalizedText><LocalizedText id="validation_is_unavailable_d7a705" before after/><button onClick={() => setRefresh(value => value + 1)}><LocalizedText id="retry_validation_525026"/></button></div>}<LocalizedText></LocalizedText>{data && <ValidationContent data={data}/>}<LocalizedText></LocalizedText>{children && <section className="validation-research research-section"><h2><LocalizedText id="additional_research_ec7401"/></h2><LocalizedText>{children}</LocalizedText></section>}</LocalizedText><ModelDisclaimer/></div></div>;
}
