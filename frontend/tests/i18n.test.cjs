const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const ts = require('typescript');
const root = path.resolve(__dirname, '..');
require.extensions['.ts'] = (module, file) => module._compile(ts.transpileModule(fs.readFileSync(file,'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText,file);
const en = require('../src/app/i18n/en.json');
const ko = require('../src/app/i18n/ko.json');
const { translateText } = require('../src/app/i18n/messages.ts');
assert.deepEqual(Object.keys(en).sort(),Object.keys(ko).sort());
for (const key of Object.keys(en)) {
  assert.ok(ko[key].trim(),key);
  const parameters = value => [...value.matchAll(/\{v\d+\}/g)].map(match=>match[0]).sort();
  assert.deepEqual(parameters(en[key]),parameters(ko[key]),key);
}
for (const [source, translation] of [['Overview','종합 현황'],['Paper Trading','모의투자'],['BUY','매수'],['SELL','매도'],['Unrealized P&L','평가손익'],['Insufficient virtual cash.','가상 현금이 부족합니다.']]) assert.equal(translateText('ko',source),translation);
for (const symbol of ['SPY','VIX','KOSPI 200','VKOSPI','XGBoost','Logistic Regression','ROC-AUC','PR-AUC','Target₁₀D(t) = 1']) assert.equal(translateText('ko',symbol),symbol);
assert.ok(translateText('ko','String should have at least 10 characters').includes('10'));
assert.ok(translateText('ko','U.S. is LOW with a model score of 13.2 / 100. Current MSI is 0.123.').includes('13.2 / 100'));
assert.equal(translateText('en','Insufficient virtual cash.'),'Insufficient virtual cash.');
function check(dir) {
 for(const name of fs.readdirSync(dir)) {
  const file=path.join(dir,name);
  if(fs.statSync(file).isDirectory()){if(!file.includes('/i18n'))check(file);continue;}
  if(!file.endsWith('.tsx'))continue;
  const source=fs.readFileSync(file,'utf8');const ast=ts.createSourceFile(file,source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  function visit(node) {
   if(ts.isJsxText(node)&&node.text.trim()&&/[A-Za-z]{2}/.test(node.text)) assert.fail(`Unlocalized static JSX: ${file}: ${node.text.trim()}`);
   if(ts.isJsxAttribute(node)&&node.name.getText(ast)==='id'&&ts.isStringLiteral(node.initializer)&&node.parent.tagName?.getText(ast)==='LocalizedText')assert.ok(en[node.initializer.text],node.initializer.text);
   ts.forEachChild(node,visit);
  }
  visit(ast);
 }
}
check(root+'/src/app');
console.log(`${Object.keys(en).length} bilingual messages: key/parameter parity, symbols/formulas, errors, interpolation, and static JSX coverage passed.`);

// Copy-only regressions: status meaning, reordered Korean sentences, and real React rendering.
for (const [source,translation] of [
 ['CURRENT','최신 데이터 반영'],['DELAYED','일부 지표 업데이트 대기'],['STALE','데이터 갱신 필요'],
 ['PARTIAL','일부 데이터 확인 필요'],['No warning','경고 없음'],
 ['Available cash','주문 가능 금액'],['Market Value','평가금액'],['Average Cost','평균 매입가'],
 ['Realized P&L','실현손익'],['HOLDINGS','보유 종목'],['RECENT ACTIVITY / ORDER HISTORY','거래 내역'],
 ['Status','상태'],['Validation market','검증 대상 시장'],['Methodology market','분석 대상 시장'],
]) assert.equal(translateText('ko',source),translation);
assert.equal(require('../src/app/i18n/messages.ts').message('ko','error_data_health'),'데이터 업데이트 오류');
assert.equal(translateText('ko','BUY 3 shares of SPY.'),'SPY 3주 매수');
assert.equal(translateText('ko','SELL 10 shares of 005930.KS.'),'005930.KS 10주 매도');
assert.equal(translateText('en','BUY 3 shares of SPY.'),'BUY 3 shares of SPY.');
assert.match(translateText('ko','No increasing contributions available.'),/위험을 높이는 요인이 없습니다/);
assert.match(translateText('ko','Equity stress is the negative 21-trading-day SPY return; volatility stress is the VIX level; credit stress is the Baa–Treasury spread.'),/SPY의 21거래일 수익률에 −1을 곱한/);
assert.match(translateText('ko','The displayed score is at or above the fixed 50 / 100 warning reference; the API warning state uses the unrounded model output.'),/50 \/ 100 이상/);
assert.match(translateText('ko','Last validated observation: 2026-10-09'),/시장 위험 데이터 기준일: 2026-10-09/);
for (const key of Object.keys(en)) {
 assert.equal(translateText('en',en[key]),en[key],`English source changed: ${key}`);
 assert.ok(!/^\w+_[a-z0-9]{6}$/.test(ko[key]),`Raw message key: ${key}`);
}
// JSX IDs, including optional empty states, are validated independently of raw-text coverage.
function checkKeys(dir) {
 for(const name of fs.readdirSync(dir)) {
  const file=path.join(dir,name);
  if(fs.statSync(file).isDirectory()){checkKeys(file);continue;}
  if(!file.endsWith('.tsx'))continue;
  const source=fs.readFileSync(file,'utf8');
  for(const match of source.matchAll(/<LocalizedText\b[^>]*\bid="([^"]+)"/g))assert.ok(en[match[1]],`${file}: ${match[1]}`);
 }
}
checkKeys(root+'/src/app');
require.extensions['.tsx']=(module,file)=>module._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true,jsx:ts.JsxEmit.ReactJSX}}).outputText,file);
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const {I18nProvider}=require('../src/app/i18n/provider.tsx');
const {PathnameContext}=require('next/dist/shared/lib/hooks-client-context.shared-runtime');
function render(language,Component,props={}) {
 const markup=renderToStaticMarkup(React.createElement(I18nProvider,{initialLanguage:language},React.createElement(PathnameContext.Provider,{value:'/'},React.createElement(Component,props))));
 assert.ok(!/\{v\d+\}/.test(markup),'Unresolved interpolation in React output');
 assert.ok(!/\b[a-z][a-z0-9_]+_[0-9a-f]{6}\b/.test(markup),'Raw translation key in React output');
 return markup;
}
const Header=require('../src/app/MarketHeader.tsx').default;
const koreanHeader=render('ko',Header);
for(const text of ['종합 현황','미국 시장','한국 시장','시장 비교','모의투자','모델 검증','분석 방법'])assert.ok(koreanHeader.includes(text),text);
const englishHeader=render('en',Header);
for(const text of ['Overview','U.S. Market','Korea Market','Compare','Paper Trading','Validation','Methodology'])assert.ok(englishHeader.includes(text),text);
const Account=require('../src/app/paper-trading/AccountPanel.tsx').default;
const koreanAccount=render('ko',Account,{onAuthenticated:()=>{}});
for(const text of ['모의투자 로그인','이메일','비밀번호','회원가입','1주 단위'])assert.ok(koreanAccount.includes(text),text);
assert.ok(render('en',Account,{onAuthenticated:()=>{}}).includes('Welcome back'));
const Notice=require('../src/app/components/DataHealthNotice.tsx').default;
for(const [status,label] of [['CURRENT','최신 데이터 반영'],['DELAYED','일부 지표 업데이트 대기'],['STALE','데이터 갱신 필요'],['PARTIAL','일부 데이터 확인 필요'],['ERROR','데이터 업데이트 오류']]) {
 const latest={last_updated:'2026-10-09',data_health:{status,is_current:status==='CURRENT',input_series:[{series:'DBAA',status:'DELAYED',latest_observation_date:'2026-10-08'}]}};
 const korean=render('ko',Notice,{market:'us',latest});assert.ok(korean.includes(label));assert.ok(korean.includes('시장 위험 데이터 기준일'));
 assert.ok(render('en',Notice,{market:'us',latest}).includes(status));
}
for(const file of ['../src/app/methodology/page.tsx','../src/app/korea/methodology/page.tsx']) {
 const Page=require(file).default;const korean=render('ko',Page);const english=render('en',Page);
 assert.ok(korean.includes('21거래일 수익률에 −1을 곱한'));
 for(const technical of ['XGBoost','Logistic Regression','ROC-AUC','PR-AUC','Target₁₀D(t) = 1'])assert.ok(korean.includes(technical),technical);
 assert.ok(english.includes('Equity stress is the negative 21-trading-day'));
 assert.ok(!korean.includes('through t+10'));
}
for(const file of ['../src/app/page.tsx','../src/app/us/page.tsx','../src/app/korea/page.tsx','../src/app/compare/page.tsx','../src/app/validation/page.tsx','../src/app/korea/validation/page.tsx','../src/app/paper-trading/page.tsx','../src/app/admin/page.tsx']) {
 const Page=require(file).default;
 for(const language of ['ko','en'])assert.ok(render(language,Page).length>100,file);
}
console.log('Korean copy: freshness labels, trading terms, sentence order, numeric/model preservation, navigation/forms and all page rendering paths passed in both languages.');
assert.equal(translateText('ko','Largest available contributions: SPY 20D Vol (+0.123); Credit 252D ZScore (-0.048).'),'주요 기여 요인: SPY 20거래일 변동성 (+0.123) · 신용 스프레드 252거래일 Z-Score (-0.048)');
assert.equal(translateText('ko','Largest available contributions: SPY 1D Return (+0.123); Credit Level (-0.048); VIX 252D ZScore (+0.004).'),'주요 기여 요인: SPY 1거래일 수익률 (+0.123) · 신용 스프레드 수준 (-0.048) · VIX 252거래일 Z-Score (+0.004)');
for(const name of ['SPY_20D_Vol','Credit_252D_ZScore','KOSPI200_1D_Return'])assert.equal(translateText('ko',name),name,'Raw model identifier changed');
// Every decimal research metric/threshold remains exactly represented in Korean.
for(const [key,source] of Object.entries(en)) {
 for(const number of new Set(source.match(/\b\d+\.\d+\b/g)||[]))assert.ok(ko[key].includes(number),`Research number changed: ${key}: ${number}`);
}
console.log('SHAP feature labels, raw model identifiers, and all decimal research metrics/thresholds preserved.');
const {ValidationContent}=require('../src/app/components/ValidationOverview.tsx');
const validationFixture={models:[
 {model:'Logistic Regression',roc_auc:0.922,pr_auc:0.807,f1:0.7,brier_score:0.2,precision:0.6,recall:0.8,false_alarm_rate:0.3,missed_event_rate:0.2,threshold:0.5,tp:80,fp:40,tn:90,fn:20},
 {model:'XGBoost',roc_auc:0.899,pr_auc:0.779,f1:0.6,brier_score:0.1,precision:0.7,recall:0.6,false_alarm_rate:0.2,missed_event_rate:0.4,threshold:0.5,tp:60,fp:30,tn:100,fn:40},
],observations:230,positives:100,prevalence:100/230,start:'2020-01-01',end:'2026-10-09',horizon:'10 Trading Days',method:'Purged expanding walk-forward OOS',threshold:0.5};
const fixtureBefore=JSON.stringify(validationFixture);
for(const language of ['ko','en']) {
 const markup=render(language,ValidationContent,{data:validationFixture});
 for(const unchanged of ['0.9220','0.8990','ROC-AUC','PR-AUC','XGBoost','Logistic Regression'])assert.ok(markup.includes(unchanged),unchanged);
 if(language==='ko')for(const label of ['분류 성능','경고 없음','오경보율']) {
  assert.ok(markup.includes(label),label);
 }
}
assert.equal(JSON.stringify(validationFixture),fixtureBefore,'Rendering changed validation data');
const CrossSnapshot=require('../src/app/components/CrossMarketSnapshot.tsx').default;
const usFixture={last_updated:'2026-10-09',risk_score_10d:11.9,market_stress_index:-1.159,data_health:{status:'ERROR',is_current:false,input_series:[]}};
const koreaFixture={last_updated:'2026-10-13',risk_score_10d:37.8,market_stress_index:0.744,data_health:{status:'CURRENT',is_current:true,input_series:[]}};
const crossKorean=render('ko',CrossSnapshot,{us:usFixture,korea:koreaFixture});
for(const label of ['데이터 업데이트 오류','최신 데이터 반영','11.9','37.8','2026년 10월 9일','2026년 10월 13일'])assert.ok(crossKorean.includes(label),label);
assert.ok(render('en',CrossSnapshot,{us:usFixture,korea:koreaFixture}).includes('ERROR'));
console.log('Populated validation/comparison rendering preserves all fixture values and independent market dates.');
