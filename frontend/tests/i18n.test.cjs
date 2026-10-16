const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const ts = require('typescript');
const root = path.resolve(__dirname, '..');
require.extensions['.css'] = () => {}; // Page-local styles are bundled by Next.js.
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
assert.ok(translateText('ko','String should have at least 8 characters').includes('8'));
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
const koreaFixture={is_stress_event:false,warning_active:false,stress_threshold:1.116,last_updated:'2026-10-13',risk_score_10d:37.8,market_stress_index:0.744,data_health:{status:'CURRENT',is_current:true,input_series:[]}};
const crossKorean=render('ko',CrossSnapshot,{us:usFixture,korea:koreaFixture});
for(const label of ['데이터 업데이트 오류','최신 데이터 반영','11.9','37.8','2026년 10월 9일','2026년 10월 13일'])assert.ok(crossKorean.includes(label),label);
assert.ok(render('en',CrossSnapshot,{us:usFixture,korea:koreaFixture}).includes('ERROR'));
console.log('Populated validation/comparison rendering preserves all fixture values and independent market dates.');

// Freshness is independent of committed model availability, on every market page.
const marketData=require('../src/app/components/market-data.ts');
for(const status of ['CURRENT','DELAYED','STALE','PARTIAL','ERROR']) {
 const delayed={...usFixture,data_health:{status,is_current:status==='CURRENT',model_available:true,input_series:[]}};
 assert.equal(marketData.modelAvailable(delayed),true,status);
 assert.equal(marketData.signal('us',delayed),'LOW',status);
 assert.equal(marketData.signal('korea',{...delayed,risk_score_10d:65,warning_active:false}),'BELOW WARNING');
 for(const language of ['en','ko']) {
  const notice=render(language,Notice,{market:'us',latest:delayed});
  assert.ok(!notice.includes(language==='en'?'Current market risk unavailable':'현재 시장 위험 데이터를'));
  const markup=render(language,CrossSnapshot,{us:delayed,korea:koreaFixture});
  assert.ok(markup.includes('11.9 / 100') && markup.includes('-1.159'));
  assert.ok(!markup.includes('UNAVAILABLE'));
 }
}
for(const value of [null,{...usFixture,risk_score_10d:NaN},{...usFixture,data_health:{model_available:false}},{...usFixture,risk_score_10d:101}])assert.equal(marketData.signal('us',value),'UNAVAILABLE');
const delayedFixture={...usFixture,spy_price:778.57,vix_level:14.84,baa_treasury_spread:1.45,data_health:{status:'DELAYED',is_current:false,model_available:true,input_series:[]}};
const originalUseMarket=marketData.useMarket;
marketData.useMarket=market=>({latest:market==='us'?delayedFixture:koreaFixture,history:[],shap:null,loading:false,errors:[],retry:()=>{}});
try {
 for(const file of ['../src/app/us/page.tsx','../src/app/korea/page.tsx','../src/app/compare/page.tsx'])for(const language of ['en','ko']) {
  const markup=render(language,require(file).default);
  assert.ok(markup.includes(file.includes('/korea/')?'37.8':'11.9'));
  assert.ok(!markup.includes('UNAVAILABLE'));
 }
} finally {marketData.useMarket=originalUseMarket;}
// Inject Overview's existing state while allowing child components' own hooks.
const Overview=require('../src/app/page.tsx').default;
const useStateBefore=React.useState;
for(const language of ['en','ko']) {
 const states=[delayedFixture,koreaFixture,[],null,false,[],'3Y',false,0];let index=0;
 React.useState=initial=>{
  // I18nProvider's state must remain the real locale.
  if(initial==='en'||initial==='ko')return useStateBefore(initial);
  return index<states.length?[states[index++],()=>{}]:useStateBefore(initial);
 };
 try {
  const markup=render(language,Overview);
  const usCard=markup.match(/<article class="market-card us-card[\s\S]*?<\/article>/)[0];
  assert.ok(usCard.includes('11.9') && usCard.includes('-1.159'));
  assert.ok(!markup.includes('UNAVAILABLE'));
  assert.ok(markup.includes(language==='ko'?'일부 지표 업데이트 대기':'Some indicators are awaiting updates.'));
 } finally {React.useState=useStateBefore;}
}
console.log('Freshness/availability: all five freshness states retain valid scores; missing/invalid models unavailable; Overview/U.S./Korea/Compare bilingual rendering passed.');

// Factor cards: available-driver sums determine direction; largest absolute
// contribution supplies the label, even when its sign differs from the net.
const MarketDetail=require('../src/app/components/MarketDetail.tsx').default;
function factorCards(markup) {
 return [...markup.matchAll(/<div class="driver factor-summary [\s\S]*?<\/div><\/div>/g)].map(match=>match[0]);
}
try {
 for(const market of ['us','korea'])for(const language of ['en','ko']) {
  const equity=market==='us'?'SPY':'KOSPI200';
  const volatility=market==='us'?'VIX':'VKOSPI';
  const driver=(feature,value)=>({feature,shap_value:value});
  const fixtures=[
   driver(`${equity}_1D_Return`,3),driver(`${equity}_5D_Return`,3),driver(`${equity}_60D_Vol`,-5),
   driver(`${volatility}_Level`,-1),driver(`${volatility}_252D_ZScore`,-2),
   driver('Credit_Level',2),driver('Credit_5D_Change',-2),
  ];
  marketData.useMarket=()=>({latest:market==='us'?delayedFixture:koreaFixture,history:[],shap:{date:'2026-10-13',feature_count:17,top_drivers:fixtures},loading:false,errors:[],retry:()=>{}});
  const markup=render(language,MarketDetail,{market});
  const cards=factorCards(markup);
  assert.equal(cards.length,3);
  for(const [index,label] of (language==='ko'?['주식 요인','변동성 요인','신용 요인']:['Equity factors','Volatility factors','Credit factors']).entries())assert.ok(cards[index].includes(label));
  const directions=market==='korea' ? (language==='ko'?['향후 Risk Score를 높이는 방향으로 기여 ↑','향후 Risk Score를 낮추는 방향으로 기여 ↓','향후 Risk Score에 대한 기여 중립']:['Contributes toward a higher forward Risk Score ↑','Contributes toward a lower forward Risk Score ↓','Neutral contribution to the forward Risk Score']) : (language==='ko'?['현재 모델 위험 확대 ↑','현재 모델 위험 완화 ↓','현재 모델 위험 기여 중립']:['Model risk contribution: Higher ↑','Model risk contribution: Lower ↓','Model risk contribution: Neutral']);
  for(const [index,direction] of directions.entries())assert.ok(cards[index].includes(direction));
  for(const [index,feature] of [`${equity} 60D Vol`,`${volatility} 252D ZScore`,'Credit Level'].entries()) {
   assert.ok(cards[index].includes(translateText(language,feature)),feature);
   assert.ok(cards[index].includes(language==='ko'?'주요 영향:':'Main influence:'));
  }
  assert.ok(markup.includes(language==='ko'?'인과관계를 뜻하지 않습니다':'not causal effects'));
  assert.ok(markup.includes('shap-grid'),'Detailed SHAP evidence remains');
  if(market==='korea') {
   for(const copy of ['Operational warning not triggered','Being below the warning threshold does not rule out market shocks.','Stress Event threshold not reached','SHAP explains how inputs contribute to the 10-trading-day Risk Score, not whether the current market is safe.'])assert.ok(markup.includes(translateText(language,copy)),copy);
   assert.ok(markup.indexOf('research-status-panel') < markup.indexOf('korea-trend-panel'));
   assert.ok(markup.includes(koreaFixture.last_updated));
   assert.ok(markup.includes('monitor-hero') && markup.includes('monitor-signal-grid'));
   assert.ok(markup.includes(`stroke-dasharray="${koreaFixture.risk_score_10d} 100"`),'Gauge preserves API score');
   assert.ok(markup.includes(translateText(language,'Observed model inputs · not independent alerts')));
   assert.ok(markup.includes(translateText(language,'Operational warning transitions are not supplied by this API.')));
   assert.ok(markup.includes(translateText(language,'No validated live industry matrix is available.')));
  }
  // Reverse every nonzero category to check the opposite directions too.
  fixtures.forEach(d=>{d.shap_value=-d.shap_value;});
  const reversed=factorCards(render(language,MarketDetail,{market}));
  assert.ok(reversed[0].includes(directions[1]));
  assert.ok(reversed[1].includes(directions[0]));
  // A missing category has no invented representative or direction.
  fixtures.splice(0,fixtures.length,driver(`${equity}_20D_Momentum`,0));
  const missing=factorCards(render(language,MarketDetail,{market}));
  assert.ok(missing[0].includes(directions[2]));
  for(const card of missing.slice(1)) {
   assert.ok(card.includes(language==='ko'?'모델 기여도 조회 불가':'Model contribution unavailable'));
   assert.ok(!card.includes(language==='ko'?'주요 영향:':'Main influence:'));
  }
 }
} finally {marketData.useMarket=originalUseMarket;}
console.log('U.S./Korea factor cards: bilingual labels, mixed-sign sums, strongest absolute driver, ties, neutral, unavailable and detailed SHAP rendering passed.');
// Shared console preserves API warning state separately from score bands and MSI.
const MarketMonitorCard=require('../src/app/components/MarketMonitorCard.tsx').default;
for(const market of ['us','korea'])for(const language of ['en','ko']) {
 const latest={...(market==='us'?usFixture:koreaFixture),risk_score_10d:64.2,warning_threshold:50,warning_active:false,market_stress_index:1.05,stress_threshold:1.2,is_stress_event:false,data_health:{status:'STALE',is_current:false,model_available:true,input_series:[]}};
 const before=JSON.stringify(latest);
 const markup=render(language,MarketMonitorCard,{market,latest});
 for(const value of ['64.2','1.050','1.200','50 / 100',latest.last_updated])assert.ok(markup.includes(value),value);
 assert.ok(markup.includes(translateText(language,'Operational warning not triggered')));
 assert.ok(markup.includes(translateText(language,'Stress Event threshold not reached')));
 assert.ok(markup.includes(translateText(language,'Being below the warning threshold does not rule out market shocks.')));
 assert.equal(JSON.stringify(latest),before);
 const missing=render(language,MarketMonitorCard,{market,latest:null});
 assert.ok(!missing.includes('NaN')&&!missing.includes('undefined'));
}
console.log('Shared monitoring cards preserve API warning flags, independent MSI thresholds, stale valid values and both languages.');


// Username login preserves email signup and displays persisted roles explicitly.
for(const language of ['en','ko']) {
 const loginMarkup=render(language,Account,{onAuthenticated:()=>{}});
 assert.ok(loginMarkup.includes(language==='ko'?'이메일 또는 사용자 ID':'Email or User ID'));
 assert.match(loginMarkup, /minLength="8"/);
 assert.ok(loginMarkup.includes(language==='ko'?'비밀번호는 8자 이상':'Use at least 8 characters.'));
 assert.match(loginMarkup, /<input(?=[^>]*name="email")(?=[^>]*type="text")[^>]*>/);
 assert.ok(!loginMarkup.includes('<select'));
 React.useState=initial=>initial==='login'?['register',()=>{}]:useStateBefore(initial);
 try {
  const signup=render(language,Account,{onAuthenticated:()=>{}});
  assert.match(signup,/minLength="8"/);
  assert.match(signup,/<input(?=[^>]*name="email")(?=[^>]*type="email")[^>]*>/);
  assert.ok(!signup.includes(language==='ko'?'이메일 또는 사용자 ID':'Email or User ID'));
  assert.ok(!signup.includes('<select'));
 } finally {React.useState=useStateBefore;}
 const Menu=require('../src/app/components/AccountMenu.tsx').default;
 for(const role of ['admin','user']) {
  const fixture={id:role==='admin'?1:2,email:null,username:role==='admin'?'admin1':'user1',role};
  let injected=false;
  React.useState=initial=>{
   if(initial===null&&!injected){injected=true;return [fixture,()=>{}];}
   return useStateBefore(initial);
  };
  try {
   const menu=render(language,Menu);
   assert.ok(menu.includes(fixture.username), menu);
   assert.ok(menu.includes(language==='ko'?(role==='admin'?'관리자':'일반 사용자'):(role==='admin'?'Administrator':'User')));
   assert.equal(menu.includes('href="/admin"'),role==='admin');
  } finally {React.useState=useStateBefore;}
 }
}
console.log('Account identity: bilingual username/email login, email signup, persisted-role labels and admin-only navigation passed.');

// Risk-aware Paper Trading uses only recorded account fields and independent market semantics.
const paperComponents=require('../src/app/paper-trading/PortfolioWorkspace.tsx');
const {MarketRiskPanel}=require('../src/app/paper-trading/MarketRiskPanel.tsx');
const PaperPage=require('../src/app/paper-trading/page.tsx').default;
const observed='2026-10-14T08:00:00+00:00';
const priceObserved='2026-10-13T20:00:00+00:00';
function paperFixture(market,sign=1,positions=true) {
 const korea=market==='korea';const unit=korea?1000:1;
 const pnl=sign*125*unit;
 return {market,currency:korea?'KRW':'USD',starting_cash:10000*unit,cash:(8000+sign*25)*unit,
  portfolio_value:(10000+sign*125)*unit,realized_pnl:sign*25*unit,unrealized_pnl:sign*100*unit,
  total_return_pct:sign*1.25,today_pnl:null,today_pnl_note:'Today’s P&L requires a prior-day recorded valuation.',valuation_complete:true,
  positions:positions?[{symbol:korea?'005930.KS':'SPY',market,quantity:2,average_cost:1000*unit,latest_price:(1000+sign*50)*unit,
   market_value:(2000+sign*100)*unit,unrealized_pnl:sign*100*unit,return_pct:sign*5,price_observed_at:priceObserved}]:[]};
}
function investmentFixture(portfolio,orders=[],performance=[]) {
 const empty=market=>({...paperFixture(market,0,false),starting_cash:market==='us'?100000:0,cash:market==='us'?100000:0,portfolio_value:market==='us'?100000:0,realized_pnl:0,unrealized_pnl:0,total_return_pct:null});
 const native={us:empty('us'),korea:empty('korea')};
 if(portfolio)native[portfolio.market]=portfolio;
 const total=(native.us.portfolio_value??0)+(native.korea.portfolio_value??0)/1000;
 const complete=Object.values(native).every(p=>p.valuation_complete);
 const cash=native.us.cash+native.korea.cash/1000;
 return {base_currency:'USD',initial_capital:100000,portfolio_value:complete?total:null,cash,invested_value:complete?total-cash:null,total_pnl:complete?total-100000:null,total_return_pct:complete?(total-100000)/1000:null,valuation_complete:complete,observed_at:observed,cash_balances:{USD:native.us.cash,KRW:native.korea.cash},fx:{id:'test-fx',rate:1000,source:'Fixture FX',observation_date:'2026-10-14',retrieved_at:observed,status:'AVAILABLE'},fx_error:null,books:native,performance};
}
function renderPaper(language,user,market,portfolio,orders=[],performance=[]) {
 const investment=portfolio?investmentFixture(portfolio,orders,performance):null;
 const states=[user,'fixture-csrf',false,market,portfolio?{[market]:{portfolio,orders,performance}}:{},investment,false,'',0];let index=0;
 React.useState=initial=>{
  if(initial==='en'||initial==='ko')return useStateBefore(initial);
  return index<states.length?[states[index++],()=>{}]:useStateBefore(initial);
 };
 try{return render(language,PaperPage);}finally{React.useState=useStateBefore;}
}
for(const language of ['en','ko']) {
 const anonymous=renderPaper(language,null,'us',null);
 assert.ok(anonymous.includes(language==='ko'?'이메일 또는 사용자 ID':'Email or User ID'));
 assert.ok(!anonymous.includes('class="rw-workspace"'));
 assert.ok(!anonymous.includes('class="paper-summary"'));
 for(const market of ['us','korea'])for(const role of ['admin','user'])for(const sign of [-1,1]) {
  const user={id:role==='admin'?11:22,username:role==='admin'?'admin1':'user1',email:null,role};
  const portfolio=paperFixture(market,sign);
  const order={id:1,market,symbol:portfolio.positions[0].symbol,side:sign>0?'BUY':'SELL',quantity:2,execution_price:1000*(market==='us'?1:1000),realized_pnl:portfolio.realized_pnl,executed_at:observed,price_observed_at:priceObserved};
  const history=[{observed_at:observed,value:portfolio.portfolio_value,cash:portfolio.cash}];
  const before=JSON.stringify({portfolio,order,history});
  const markup=renderPaper(language,user,market,portfolio,[order],history);
  assert.ok(markup.includes(user.username),'Literal usernames remain verbatim');
  assert.ok(!markup.includes('관리자 1'));
  assert.ok(!markup.includes('href="/admin"'),'No role-based portfolio overrides');
  const investment=investmentFixture(portfolio,[order],history);
  for(const amount of [investment.portfolio_value,investment.cash,investment.total_pnl,investment.invested_value])assert.ok(markup.includes(require('../src/app/paper-trading/types.ts').value(amount,'USD',language==='ko'?'ko-KR':'en-US')));
  assert.ok(markup.includes(sign>0?'paper-gain':'paper-loss'));
  assert.ok(markup.includes(require('../src/app/paper-trading/types.ts').displaySymbol(market,portfolio.positions[0].symbol)));
  assert.ok(markup.includes(language==='ko'?'실제 자금 사용 없음':'NO REAL MONEY'));
  assert.ok(markup.includes(language==='ko'?ko.stress_identity:en.stress_identity));
  assert.ok(markup.includes(language==='ko'?ko.stress_loading:en.stress_loading));
  assert.ok(markup.indexOf('class="paper-summary"')<markup.indexOf('rw-analytics-grid'));
  assert.ok(markup.includes('command-market-status') && markup.includes('command-trade-rail'));
  const catalog=language==='ko'?ko:en;
  assert.ok(markup.includes(catalog.command_motto));
  assert.ok(markup.includes(catalog.stress_identity));
  assert.ok(markup.includes('second_history_insufficient'));
  assert.ok(markup.indexOf(catalog.rw_available_cash)<markup.indexOf(catalog.capital_invested));
  assert.ok(markup.indexOf(catalog.capital_invested)<markup.indexOf(catalog.rw_total_pnl.replaceAll('&','&amp;')));
  assert.ok(markup.indexOf('command-order-context')<markup.indexOf(catalog.review_simulated_order_fd4ef9));
  assert.ok(markup.indexOf('paper-holdings')<markup.indexOf('trade-ticket'));
  assert.ok(markup.indexOf('rw-activity')<markup.indexOf('command-trade-rail'));
  assert.ok(markup.includes('step="1"')&&markup.includes('max="1000000"'));
  assert.equal(JSON.stringify({portfolio,order,history}),before,'Presentation changed source data');
 }
 for(const market of ['us','korea']) {
  const user={id:22,username:'user1',email:null,role:'user'};
  const empty={...paperFixture(market,0,false),cash:10000*(market==='us'?1:1000)};
  const markup=renderPaper(language,user,market,empty);
  assert.ok(markup.includes(language==='ko'?'이 계좌에 보유한 종목이 없습니다':'No positions in this account'));
  assert.ok(markup.includes((language==='ko'?ko:en).additional_visits_and_fills_record_actual_observations_no_histori_7c82f9));
  const incomplete={...paperFixture(market),valuation_complete:false,portfolio_value:null,unrealized_pnl:null,total_return_pct:null};
  const summary=render(language,paperComponents.InvestmentSummary,{investment:investmentFixture(incomplete)});
  assert.ok(summary.includes(language==='ko'?'조회 불가':'Unavailable'));
 }
 for(const status of ['CURRENT','DELAYED','STALE','PARTIAL','ERROR']) {
  for(const market of ['us','korea']) {
   const latest={...(market==='us'?usFixture:koreaFixture),data_health:{status,is_current:status==='CURRENT',model_available:true,input_series:[]}};
   const markup=render(language,MarketRiskPanel,{market,latest});
   assert.ok(markup.includes(market==='us'?'11.9':'37.8'));
   assert.ok(markup.includes(language==='ko'?'개별 종목의 기대수익률을 예측하지 않습니다':'not the expected return of an individual security'));
   if(market==='korea')assert.ok(markup.includes(language==='ko'?translateText('ko','BELOW WARNING'):'BELOW WARNING'));
  }
 }
 for (const market of ['us','korea']) {
  const latest=market==='us'?usFixture:koreaFixture;
  const compact=render(language,MarketRiskPanel,{market,latest,compact:true});
  assert.ok(compact.includes('rw-risk-compact'));
  assert.ok(compact.includes(latest.last_updated));
  assert.ok(compact.includes(market==='us'?'11.9':'37.8'));
  assert.ok(!compact.includes('rw-text-link'));
 }
 const unavailable=render(language,MarketRiskPanel,{market:'us',latest:null});
 assert.ok(!unavailable.includes('undefined'));
}
// A sparse or unchanging completed-close history must not masquerade as a performance curve.
for (const language of ['en','ko']) {
 const catalog=language==='ko'?ko:en;
 const first={observed_at:observed,value:10000,cash:10000};
 const second={observed_at:'2026-10-15T08:00:00+00:00',value:10100,cash:8000};
 for (const [history,state] of [
  [[], 'second_history_empty'],
  [[first], 'second_history_insufficient'],
  [[first,{...first,value:10100}], 'second_history_insufficient'],
  [[first,{...first,observed_at:'2026-10-14T09:00:00+00:00',value:9999}], 'second_history_insufficient'],
  [[first,{...second,value:first.value}], 'second_history_unchanged'],
  [[{...first,value:NaN},{...second,observed_at:'invalid'}], 'second_history_empty'],
  [[first,second], 'chart'],
 ]) {
  const before=JSON.stringify(history);
  const markup=render(language,paperComponents.PortfolioPerformance,{performance:history,portfolio:paperFixture('us'),currency:'USD',loading:false});
  assert.ok(markup.includes(`data-history-state="${state}"`));
  if(state!=='chart') {
   assert.ok(markup.includes(catalog[state]));
   assert.ok(!markup.includes('recharts-responsive-container'));
   assert.ok(!markup.includes('NaN'));
  } else assert.ok(markup.includes('recharts-responsive-container'));
  assert.equal(JSON.stringify(history),before,'Performance presentation mutated recorded valuations');
 }
 const loading=render(language,paperComponents.PortfolioPerformance,{performance:[first,second],portfolio:null,currency:'KRW',loading:true});
 assert.ok(loading.includes(catalog.second_history_loading));
 assert.ok(!loading.includes('recharts-responsive-container'));
}
console.log('Performance history: empty, single observation, duplicate times, unchanged equity, invalid values/dates, loading and genuine changing history passed in both languages.');

console.log('Risk-aware Paper Trading: anonymous/admin1/user1, USD/KRW, gains/losses, empty/incomplete accounts, recorded data, future modules and five model-freshness states passed in both languages.');

// Ticket presentation retains completed-close evidence, review and safe pending-order controls.
const Ticket=require('../src/app/paper-trading/TradeTicket.tsx').default;
for(const language of ['en','ko'])for(const market of ['us','korea'])for(const reviewing of [false,true]) {
 const portfolio=paperFixture(market);const symbol=portfolio.positions[0].symbol;
 const quote={id:'fixture-quote',market,symbol,price:portfolio.positions[0].latest_price,currency:portfolio.currency,
  observed_at:priceObserved,source:'Fixture completed close',expires_at:Math.floor(Date.now()/1000)+120};
 const review=reviewing?{market,symbol,side:'BUY',quantity:2,quote_id:quote.id,request_key:'fixture-request'}:null;
 const selected={market,symbol,ticker:require('../src/app/paper-trading/types.ts').displaySymbol(market,symbol),name:symbol,exchange:market==='us'?'NYSE Arca':'KOSPI',security_type:'ETF',currency:portfolio.currency};
 const states=[selected,symbol,'BUY','2',quote,review,false,'',''];let index=0;
 React.useState=initial=>{
  if(initial==='en'||initial==='ko')return useStateBefore(initial);
  return index<states.length?[states[index++],()=>{}]:useStateBefore(initial);
 };
 try {
  const markup=render(language,Ticket,{market,portfolio,csrf:'fixture-csrf',userId:22,onExecuted:()=>{}});
  assert.ok(markup.includes(symbol));
  assert.ok(markup.includes('Fixture completed close'));
  assert.ok(markup.includes(require('../src/app/paper-trading/types.ts').value(quote.price*2,portfolio.currency,language==='ko'?'ko-KR':'en-US')));
  assert.ok(markup.includes(language==='ko'?'모의 주문':'SIMULATED ORDER'));
  if(reviewing) {
   assert.ok(markup.includes(language==='ko'?translateText('ko','Submit paper trade'):'Submit paper trade'));
   assert.ok(markup.includes(translateText(language,'Cancel review')));
  } else assert.ok(markup.includes(translateText(language,'Review simulated order')));
 } finally {React.useState=useStateBefore;}
}
console.log('Paper order ticket: USD/KRW quote evidence, estimated value and review/submit/cancel presentation passed in Korean and English.');

// Discovery stays market-scoped, neutral, bounded and separate from quote approval.
const {SearchResults}=require('../src/app/paper-trading/SecurityPicker.tsx');
const Picker=require('../src/app/paper-trading/SecurityPicker.tsx').default;
for(const language of ['en','ko'])for(const market of ['us','korea']) {
 const items=market==='us'?[
  {symbol:'NVDA',ticker:'NVDA',name:'NVIDIA Corporation',exchange:'Nasdaq',market,currency:'USD',security_type:'Stock'},
  {symbol:'VOO',ticker:'VOO',name:'Vanguard S&P 500 ETF',exchange:'NYSE Arca',market,currency:'USD',security_type:'ETF'}
 ]:[
  {symbol:'005930.KS',ticker:'005930',name:'삼성전자',exchange:'KOSPI',market,currency:'KRW',security_type:'Stock'},
  {symbol:'069500.KS',ticker:'069500',name:'KODEX 200',exchange:'KOSPI',market,currency:'KRW',security_type:'ETF'}
 ];
 const results=render(language,SearchResults,{items,active:0,listId:'fixture-list',onSelect:()=>{},onActive:()=>{}});
 assert.ok(results.includes('role="listbox"'));
 assert.equal((results.match(/role="option"/g)||[]).length,2);
 assert.ok(results.includes('aria-selected="true"'));
 for(const item of items)for(const text of [item.ticker,item.name,item.exchange])assert.ok(results.includes(text.replace(/&/g,'&amp;')));
 assert.ok(!results.includes('.KS'));
 assert.ok(results.includes(language==='ko'?'주식':'Stock'));
 assert.ok(results.includes('ETF'));
 for(const disabled of [false,true]) {
  const picker=render(language,Picker,{market,disabled,onSelect:()=>{},onSearchStart:()=>{}});
  assert.ok(picker.includes('role="combobox"'));
  assert.ok(picker.includes('aria-autocomplete="list"'));
  assert.ok(picker.includes(language==='ko'?'종목명 또는 티커 검색':'Search by company name or ticker'));
  assert.ok(picker.includes('maxLength="100"'));
  assert.equal(/<input[^>]*disabled=""/.test(picker),disabled);
  assert.ok(!picker.includes('<select'));
 }
}
console.log('Security discovery: bilingual market/type metadata, canonical Korean tickers, combobox/listbox semantics and disabled order-review state passed.');

for(const language of ['en','ko'])for(const view of ['all','us','korea']) {
 const books={us:{portfolio:paperFixture('us'),orders:[],performance:[]},korea:{portfolio:paperFixture('korea'),orders:[],performance:[]}};
 const html=render(language,paperComponents.default,{view,user:{id:22,username:'user1',role:'user'},books,investment:investmentFixture(books.us.portfolio),loading:false,csrf:'fixture-csrf',onExecuted:()=>{}});
 assert.equal((html.match(/class="paper-summary"/g)||[]).length,1);
 assert.ok(html.includes((language==='ko'?ko:en).unified_search_scope));
 assert.ok(html.includes('capital-native-balances'));
 assert.ok(html.includes((language==='ko'?ko:en).capital_usd_base));
}
console.log('Unified books: All/U.S./Korea are display filters; independent USD/KRW values and unified search preserved in both languages.');

// Render the reconciled currency evidence and immutable execution details in both languages.
const {FxExposure,ExecutionConditions}=require('../src/app/paper-trading/PortfolioWorkspace.tsx');
const fxEvidence={fx_attribution:{available:true,native_investment_effect_usd:50,fx_translation_effect_usd:-250,trading_costs_usd:0,fx_conversion_costs_usd:0,rounding_residual_usd:0,reconciled_total_usd_pnl:-200,krw_exposure_usd:300,krw_exposure_pct:0.3,krw_cash_fx_unrealized_usd:0,positions:[{market:'korea',symbol:'005930.KS',quantity:10,average_purchase_price:50000,average_acquisition_fx:1000,current_fx:2000,fx_change_pct:100,native_stock_pnl:100000,native_effect_usd:50,fx_effect_usd:-250,purchase_costs_usd:0,total_usd_pnl:-200}]},books:{korea:{positions:[{symbol:'005930.KS',latest_price:60000}]}}};
const historicalDetail={market:'korea',side:'BUY',currency:'KRW',costs:{gross_minor:500000,commission_minor:75,transaction_tax_minor:0,regulatory_fee_minor:0},fx:{rate:1000,source:'Historical FRED reference',observation_date:'2026-10-14',retrieved_at:'2026-10-15T00:00:00Z',status:'AVAILABLE'},fx_spread_bps:'10',effective_fx_rate:'999',fx_usd_cents:50058,fx_krw:500079,from_currency:'USD',to_currency:'KRW',fx_cost_usd_exact:'0.501',execution_attribution:{available:true,gross_usd:'500'}};
for(const lang of ['en','ko']){
 const exposure=render(lang,FxExposure,{investment:fxEvidence});
 assert.ok(exposure.includes('005930'));assert.ok(exposure.includes('2,000'));assert.ok(exposure.includes('-$250.00')||exposure.includes('-US$250.00'));
 assert.ok(exposure.includes(lang==='ko'?'시장 스트레스 노출':'Market-stress exposure'));
 const unavailable=render(lang,FxExposure,{investment:{fx_attribution:{available:false,positions:[]}}});
 assert.ok(unavailable.includes(lang==='ko'?'모두 확보':'unavailable until'));
 const historic=render(lang,ExecutionConditions,{detail:historicalDetail});
 assert.ok(historic.includes('Historical FRED reference'));assert.ok(historic.includes('1,000'));assert.ok(historic.includes('2026-10-14'));assert.ok(!historic.includes('2,000'));
}
console.log('FX exposure reconciliation, unavailable evidence and immutable trade conditions render in both languages.');
