const fs=require('node:fs'),ts=require('typescript'),assert=require('node:assert/strict');
const {test}=require('node:test');
require.extensions['.ts']=(module,file)=>module._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true,jsx:ts.JsxEmit.ReactJSX}}).outputText,file);
require.extensions['.tsx']=require.extensions['.ts'];
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const {I18nProvider}=require('../src/app/i18n/provider.tsx');
const {PathnameContext}=require('next/dist/shared/lib/hooks-client-context.shared-runtime');
const {StressAnalysisView,histogram}=require('../src/app/paper-trading/StressAnalytics.tsx');
function render(language,data){return renderToStaticMarkup(React.createElement(PathnameContext.Provider,{value:'/paper-trading'},React.createElement(I18nProvider,{initialLanguage:language},React.createElement(StressAnalysisView,{data}))));}
const empty={methodology_version:'conditional-history-v1',valuation_at:'2026-10-15T00:00:00Z',markets:{us:{status:'AVAILABLE',regime:'LOW',observation_date:'2026-10-14',risk_score:10,sectors:[]},korea:{status:'UNAVAILABLE',sectors:[]}},exposure:{status:'AVAILABLE',cash_weight:1,largest_security_weight:0,groups:{market:[],sector:[{label:'us:UNKNOWN',weight:.2}],industry:[],currency:[{label:'USD',weight:1}],symbol:[]}},sensitivity:[{market:'us',weight:0,evidence:[],status:'NO_HOLDINGS',distribution:null},{market:'korea',weight:0,evidence:[],status:'NO_HOLDINGS',distribution:null}],outlook:{status:'NO_HOLDINGS',distribution:null}};
const dist={status:'AVAILABLE',n:20,median_pct:1,q25_pct:-2,q75_pct:3,downside_q10_pct:null,negative_frequency:.4,dispersion_iqr_pct:5,events:Array.from({length:20},(_,i)=>({date:'2010-01-01',end_date:'2010-01-15',return_pct:i-8}))};
test('histogram preserves every observation including maximum and constant outcomes',()=>{
 assert.equal(histogram(dist.events).reduce((n,b)=>n+b.count,0),20);
 assert.equal(histogram([{return_pct:2},{return_pct:2}])[0].count,2);
 assert.deepEqual(histogram([]),[]);
});
for(const language of ['en','ko'])test(`${language}: all five stages, honest missing data, unknown classification and no paywall`,()=>{
 const html=render(language,empty);
 assert.ok(html.includes(language==='en'?'Current Market Stress':'현재 시장 스트레스'));
 assert.ok(html.includes(language==='en'?'Sector / Industry Stress':'업종 / 산업별 스트레스'));
 assert.ok(html.includes(language==='en'?'Conditional 10D Outlook':'과거 조건부 10거래일 시나리오'));
 assert.ok(html.includes(language==='en'?'classification unverified':'분류 정보 미검증'));
 assert.ok(html.includes(language==='en'?'No invested holdings':'투자 중인 종목이 없습니다'));
 assert.ok(!html.includes('Pro-only')&&!html.includes('Upgrade'));
});
test('available portfolio distribution and provenance are distinct from actual performance',()=>{
 const data=structuredClone(empty);data.outlook={status:'AVAILABLE',distribution:dist};
 data.markets.us.sectors=[{...dist,symbol:'TECH',sector:'Technology',kind:'sector',source:'https://example.org/evidence'}];
 const html=render('en',data);
 for(const text of ['Negative-return frequency','Central scenario','Downside quantile withheld','separate from Actual Performance','https://example.org/evidence'])assert.ok(html.includes(text),text);
 assert.ok(html.includes('stress-histogram'));
});
test('mixed markets withhold aggregate range rather than inventing a combined distribution',()=>{
 const data=structuredClone(empty);data.outlook.status='SEPARATE_MARKET_EVIDENCE_REQUIRED';
 const html=render('en',data);assert.ok(html.includes('combined portfolio range is withheld'));
});
test('insufficient sample withholds chart and includes sample count',()=>{
 const data=structuredClone(empty);data.outlook={status:'INSUFFICIENT_SAMPLE',distribution:{...dist,status:'INSUFFICIENT_SAMPLE',n:3,median_pct:null,q25_pct:null,q75_pct:null,negative_frequency:null,dispersion_iqr_pct:null}};
 const html=render('en',data);assert.ok(html.includes('Insufficient sample'));assert.ok(!html.includes('role="img"'));
});

test('Korea-only holdings open their own evidence without applying U.S. regimes',()=>{
 const data=structuredClone(empty);
 data.markets.korea={status:'AVAILABLE',regime:'BELOW_WARNING',risk_score:32.3,observation_date:'2026-10-14',sectors:[]};
 data.sensitivity[1].evidence=[{symbol:'000660.KS',weight:.1,level:'security',instrument:'000660.KS',n:187}];
 const html=render('en',data);
 assert.ok(html.includes('BELOW_WARNING'));assert.ok(html.includes('000660.KS'));
 assert.ok(!html.includes('LOW ·'));
});
