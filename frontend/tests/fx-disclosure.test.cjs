const fs=require('node:fs'),ts=require('typescript'),assert=require('node:assert/strict');
const {test}=require('node:test');
require.extensions['.ts']=(module,file)=>module._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true,jsx:ts.JsxEmit.ReactJSX}}).outputText,file);
require.extensions['.tsx']=require.extensions['.ts'];
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const {I18nProvider}=require('../src/app/i18n/provider.tsx');
const {PathnameContext}=require('next/dist/shared/lib/hooks-client-context.shared-runtime');
const {InvestmentSummary,ExecutionConditions,FxHistory}=require('../src/app/paper-trading/PortfolioWorkspace.tsx');
const {FxAttribution}=require('../src/app/paper-trading/FxDisclosure.tsx');
const source='exchangerate.dev Free / USD/KRW (15-minute delayed)';
const fx={id:'immutable-rate',source,rate:1350,observation_date:'2026-10-15',observation_timestamp:'2026-10-15T00:00:00+00:00',retrieved_at:'2026-10-15T00:15:30+00:00',selection_role:'primary',freshness_status:'DELAYED'};
function render(language,Component,props){return renderToStaticMarkup(React.createElement(I18nProvider,{initialLanguage:language},React.createElement(PathnameContext.Provider,{value:'/paper-trading'},React.createElement(Component,props))))}
for(const language of ['en','ko'])test(`${language}: current delayed source, timestamps and visible correct attribution`,()=>{
 const investment={portfolio_value:100000,cash:100000,invested_value:0,total_pnl:0,cash_balances:{USD:100000,KRW:0},books:{us:{cash:100000,portfolio_value:100000},korea:{cash:0,portfolio_value:0}},fx};
 const html=render(language,InvestmentSummary,{investment});
 assert.ok(html.includes(language==='en'?'Delayed · ~15 minutes':'약 15분 지연'));
 assert.ok(html.includes(language==='en'?'not real-time':'실시간이 아닙니다'));
 assert.ok(html.includes(fx.observation_timestamp));
 assert.ok(html.includes('Rates by Exchangerate.dev')&&html.includes('https://exchangerate.dev'));
 assert.ok(html.indexOf('Rates by Exchangerate.dev')>html.indexOf('</details>'),'Attribution must be visible outside the collapsed summary');
 assert.ok(!html.includes('twelvedata.com'));
});
test('historical execution preserves recorded timestamp and provider disclosure',()=>{
 const detail={market:'korea',side:'BUY',currency:'KRW',costs:{gross_minor:135000,commission_minor:0,transaction_tax_minor:0,regulatory_fee_minor:0},fx};
 const html=render('en',ExecutionConditions,{detail});
 assert.ok(html.includes(fx.observation_timestamp)&&html.includes('Rates by Exchangerate.dev'));
 assert.ok(html.includes('Delayed indicative FX'));
 const history=render('en',FxHistory,{events:[{order_id:1,executed_at:'2026-10-15T01:00:00Z',symbol:'005930.KS',market:'korea',execution_price:50000,source,observation_date:'2026-10-15',from_currency:'USD',to_currency:'KRW',from_minor:10000,to_minor:135000,usd_cash_after:9990000,krw_cash_after:0,quantity_after:1,rate:1350}]});
 assert.ok(history.includes('Rates by Exchangerate.dev'));
});
test('legacy source keeps its attribution and FRED does not receive a false one',()=>{
 assert.ok(render('en',FxAttribution,{source:'Twelve Data / USD/KRW'}).includes('twelvedata.com'));
 assert.equal(render('en',FxAttribution,{source:'FRED / Federal Reserve H.10 / DEXKOUS'}),'');
});
