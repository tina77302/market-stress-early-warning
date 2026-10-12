import en from './en.json';
import ko from './ko.json';

export type MessageKey = keyof typeof en;
export type Language = 'en' | 'ko';
export const catalogs: Record<Language, Record<MessageKey, string>> = { en, ko };
export const localeCodes: Record<Language, string> = { en: 'en-US', ko: 'ko-KR' };
export const languageCookie = 'mri_ui_language';
export function normalize(text: string) { return text.replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&apos;/g,"'").replace(/&quot;/g,'"').replace(/\s+/g,' ').trim().toLowerCase(); }
const aliases = new Map<string, MessageKey>(Object.entries(en).map(([key, value]) => [normalize(value), key as MessageKey]));
const escape = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const patterns = Object.entries(en).filter(([,value]) => /\{v\d+\}/.test(value)).map(([key, value]) => {
  const names: string[] = [];
  const parts = value.split(/(\{v\d+\})/g);
  const pattern = parts.map(part => /^\{v\d+\}$/.test(part) ? (names.push(part.slice(1,-1)), '(.+?)') : escape(part)).join('');
  return { key: key as MessageKey, names, regex: new RegExp(`^${pattern}$`, 'i'), specificity: value.replace(/\{v\d+\}/g,'').length };
}).sort((a,b) => b.specificity-a.specificity);
export function message(language: Language, key: MessageKey, params: Record<string, string | number> = {}) {
  return catalogs[language][key].replace(/\{(v\d+)\}/g, (_,name: string) => String(params[name] ?? `{${name}}`));
}
export function translateText(language: Language, source: string, depth = 0): string {
  if (language === 'en' || !source.trim() || depth > 5) return source;
  const clean = source.replace(/\s+/g,' ').trim();
  const paddingBefore = /^\s/.test(source) ? ' ' : '', paddingAfter = /\s$/.test(source) ? ' ' : '';
  const key = aliases.get(normalize(clean));
  if (key) return paddingBefore + message(language,key) + paddingAfter;
  for (const pattern of patterns) {
    const match = pattern.regex.exec(clean);
    if (match) {
      const params = Object.fromEntries(pattern.names.map((name,index) => [name,translateText(language,match[index+1],depth+1)]));
      return paddingBefore+message(language,pattern.key,params)+paddingAfter;
    }
  }
  if (/^[135]Y$/.test(clean)) return `${clean[0]}년`;
  // Presentation-only composition of API labels, status values, and feature names.
  if (/[·;|]/.test(clean)) return clean.split(/([·;|])/).map(part => translateText(language,part,depth+1)).join('');
  if (clean.includes(':')) return clean.split(/(:)/).map(part => translateText(language,part,depth+1)).join('');
  if (/^[A-Z]+_/.test(clean)) return source; // Raw identifiers are never changed.
  if (/[.!]$/.test(clean)) {
    const inner = translateText(language,clean.slice(0,-1),depth+1);
    if (inner !== clean.slice(0,-1)) return paddingBefore+inner+clean.slice(-1)+paddingAfter;
  }
  // Model feature labels use stable technical prefixes with translated descriptions.
  const suffixes: Record<string,string> = { Return:'수익률', Momentum:'모멘텀', Volatility:'변동성', Vol:'변동성', Drawdown:'고점 대비 하락률', Level:'수준', Change:'변화', ZScore:'Z-Score' };
  const feature = /^(SPY|VIX|VKOSPI|KOSPI200|Credit|BAA)\s+(.*)$/.exec(clean);
  if (feature) return `${feature[1]==='Credit' ? '신용' : feature[1]} ${feature[2].replace(/\b(Return|Momentum|Volatility|Vol|Drawdown|Level|Change|ZScore)\b/g,word=>suffixes[word])}`;
  return source;
}
