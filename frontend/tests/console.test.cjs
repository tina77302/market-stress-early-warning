const fs=require('node:fs'),assert=require('node:assert/strict'),test=require('node:test'),ts=require('typescript');
require.extensions['.css']=()=>{};
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,p)=>m._compile(ts.transpileModule(fs.readFileSync(p,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,p);
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server'),{I18nProvider}=require('../src/app/i18n/provider.tsx');
const {default:Console,ConsoleChart,CurrentConsole,BuildUpPreview}=require('../src/app/components/MonitoringConsole.tsx');
const data=require('../src/app/components/monitoring-data.ts');
const latest={last_updated:'2026-10-16',risk_score_10d:49.99,warning_active:false,market_stress_index:.788,stress_threshold:1.116,is_stress_event:false,kospi200:878.16,vkospi:48.89,data_health:{status:'STALE',model_available:true,is_current:false,published_at:'2026-10-19T00:41:00+00:00',input_series:[]}};
const props={market:'korea',latest,history:[],shap:null};
const render=(Component,props,language='en')=>renderToStaticMarkup(React.createElement(I18nProvider,{initialLanguage:language},React.createElement(Component,props)));
function find(node,predicate){if(!node||typeof node!=='object')return null;if(predicate(node))return node;for(const child of React.Children.toArray(node.props?.children)){const found=find(child,predicate);if(found)return found;}return null;}
function harness(){let selection=null,tree;const original=React.useState;return {paint(){React.useState=initial=>initial===null?[selection,value=>{selection=value}]:original(initial);function Capture(){tree=Console(props);return tree;}try{return render(Capture,{});}finally{React.useState=original;}},find:predicate=>find(tree,predicate)};}
for(const lang of ['en','ko'])test(lang+': Korea console shows verified build-up without LIVE ledger or provenance click',()=>{
 const html=render(Console,props,lang);for(const value of ['12.1','15.6','37.8','32.3','40.5'])assert.ok(html.includes(value));assert.equal((html.match(/class="mc-operational-reference"/g)||[]).length,1);assert.ok(html.includes('data-provenance="RETROSPECTIVE"'));assert.ok(html.indexOf('mc-current')<html.indexOf('mc-buildup'));assert.ok(html.indexOf('mc-buildup')<html.indexOf('mc-evidence-row'));assert.ok(html.indexOf('mc-evidence-row')<html.indexOf('mc-secondary'));
});
test('current card preserves authoritative API warning and freshness without classifying below-50 as SAFE',()=>{
 const before=JSON.stringify(latest);const html=render(CurrentConsole,{market:'korea',latest});assert.ok(html.includes('50.0'));assert.ok(html.includes('data-warning="false"'));assert.ok(html.includes('Not triggered'));assert.ok(!html.includes('>SAFE<'));assert.equal(JSON.stringify(latest),before);
});
test('table date selection retains replay timestamp unavailability and recorded snapshot publication time',()=>{
 const h=harness();h.paint();h.find(n=>n.type==='tr'&&React.Children.toArray(n.props.children)[0]?.props?.children?.props?.children==='2026-10-14').props.onClick();let html=h.paint();assert.ok(html.includes('Frozen-model replay'));assert.ok(html.includes('Not recorded · no publication-time claim'));assert.ok(html.includes('32.3'));
 h.find(n=>n.type==='tr'&&React.Children.toArray(n.props.children)[0]?.props?.children?.props?.children==='2026-10-15').props.onClick();html=h.paint();assert.ok(html.includes('10/16/2026, 16:58 KST'));assert.ok(html.includes('40.5'));assert.ok(html.includes('+8.2'));
});
test('chart pointer selects the nearest actual observation and annotations remain visible',()=>{
 let tree,selected=null;const points=data.archivePoints('korea');function Capture(){tree=ConsoleChart({points,selected:'2026-10-15',onSelect:date=>{selected=date}});return tree;}render(Capture,{});
 const svg=find(tree,n=>n.type==='svg');svg.props.onClick({clientX:622,clientY:100,currentTarget:{getScreenCTM:()=>({inverse:()=>({})}),createSVGPoint:()=>({matrixTransform(){return {x:this.x,y:this.y}}})}});assert.equal(selected,'archive-korea-2026-10-13');assert.ok(find(tree,n=>n.type==='text'&&n.props.className==='mc-point-label'));
});
test('empty LIVE filter is disabled while full historical chart remains visible',()=>{
 const h=harness();h.paint();const group=h.find(n=>typeof n.type==='function'&&n.type.name==='SourceControls');const tree=group.type;
 const html=render(Console,props);assert.ok(/disabled=""[^>]*aria-pressed="false"[\s\S]*?LIVE/.test(html));assert.ok(html.includes('mc-score-path'));
});
test('US chart uses available US history without Korea archive contamination',()=>{
 const history=[{date:'2026-09-15',risk_score_xgboost:21,msi:.1,spy:100},{date:'2026-09-16',risk_score_xgboost:29,msi:.2,spy:99}];const html=render(BuildUpPreview,{market:'us',history});assert.ok(html.includes('data-date="2026-09-16"'));assert.ok(html.includes('HISTORICAL OOS'));assert.ok(!html.includes('data-date="2026-10-15"'));
});

test('global command hero uses independent API indicators and health, with explicitly decorative local geography',()=>{
 const {GlobalHero}=require('../src/app/components/GlobalCommand.tsx');
 const us={...latest,risk_score_10d:16.9,spy_price:771.79,vix_level:16.46,baa_treasury_spread:1.44,data_health:{...latest.data_health,status:'DELAYED'}};
 const korea={...latest,risk_score_10d:31.6,kospi200:878.16,vkospi:48.89,data_health:{...latest.data_health,status:'CURRENT'}};
 const html=render(GlobalHero,{us,korea});
 for(const value of ['771.79','16.46','878.16','48.89','DELAYED','CURRENT','/monitoring/globe.svg'])assert.ok(html.includes(value),value);
 assert.ok(html.includes('not analytical evidence'));assert.ok(!html.includes('LIVE publications'));assert.ok(!html.includes('>SAFE<'));
});
test('geographic market cards preserve each market snapshot and its independent timeline',()=>{
 const {CommandMarketCard}=require('../src/app/components/GlobalCommand.tsx');
 const korea=render(CommandMarketCard,{market:'korea',latest:{...latest,risk_score_10d:31.6},history:[]});
 const us=render(CommandMarketCard,{market:'us',latest:{...latest,risk_score_10d:16.9},history:[{date:'2026-09-16',risk_score_xgboost:29.7,msi:-.59,spy:700}]});
 assert.ok(korea.includes('mc-city-korea'));assert.ok(korea.includes('31.6'));for(const n of ['12.1','15.6','37.8','32.3','40.5'])assert.ok(korea.includes(n));
 assert.ok(us.includes('mc-city-us'));assert.ok(us.includes('16.9'));assert.ok(us.includes('29.7'));assert.ok(!us.includes('data-date="2026-10-15"'));
});

test('dated input values come only from the selected historical row, never the current snapshot',()=>{
 const history=[{date:'2026-09-16',risk_score_xgboost:29.7,msi:-.591,spy:700,vix:21.2,baa_treasury_spread:1.65}];
 const html=render(Console,{market:'us',latest:{...latest,spy_price:771.79,vix_level:16.46},history,shap:null});
 const table=html.split('class="mc-date-table')[0];
 const points=data.historicalPoints(history,'us');assert.deepEqual(points[0].inputs,{index:700,volatility:21.2,credit:1.65});
 assert.ok(html.includes('700.00'));assert.ok(html.includes('21.20'));assert.ok(html.includes('1.65'));assert.ok(!data.archivePoints('korea').some(p=>p.inputs));
});
