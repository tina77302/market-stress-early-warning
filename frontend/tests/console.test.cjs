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
 const h=harness();h.paint();h.find(n=>n.type==='tr'&&find(n,c=>c.type==='button'&&c.props.children==='2026-10-14')).props.onClick();let html=h.paint();assert.ok(html.includes('Frozen-model replay'));assert.ok(html.includes('Not recorded · no publication-time claim'));assert.ok(html.includes('32.3'));
 h.find(n=>n.type==='tr'&&find(n,c=>c.type==='button'&&c.props.children==='2026-10-15')).props.onClick();html=h.paint();assert.ok(html.includes('10/16/2026, 16:58 KST'));assert.ok(html.includes('40.5'));assert.ok(html.includes('+8.2'));
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
 const original=React.useState;let html;
 React.useState=initial=>initial===null?['oos-us-2026-09-16',()=>{}]:original(initial);
 try{html=render(Console,{market:'us',latest:{...latest,spy_price:771.79,vix_level:16.46},history,shap:null});}finally{React.useState=original;}
 const points=data.historicalPoints(history,'us');assert.deepEqual(points[0].inputs,{index:700,volatility:21.2,credit:1.65});
 assert.ok(html.includes('700.00'));assert.ok(html.includes('21.20'));assert.ok(html.includes('1.65'));assert.ok(!data.archivePoints('korea').some(p=>p.inputs));
});

function current(market='us',score=52.6) {
 const latest={last_updated:'2026-10-19',risk_score_10d:score,warning_active:score>=50,market_stress_index:.743,source_provenance:'provider-validated',data_health:{status:'CURRENT',is_current:true,model_available:true,snapshot_id:market+'-snapshot',expected_observation_date:'2026-10-19',input_series:[]}};
 const publication={market,current_data_health:{status:'CURRENT'},record:{market,record_type:'LIVE',record_id:market+'-latest',snapshot_id:market+'-snapshot',observation_date:'2026-10-19',publication_sequence:4,risk_score:score,operational_warning:score>=50,data_status:'CURRENT',generated_at:'2026-10-20T00:40:17+00:00'}};
 return {market,latest,publication};
}
test('one date representative picks latest publication without removing underlying records or crossing markets',()=>{
 const old={...current('korea',31.6).publication.record,record_id:'old',observation_date:'2026-10-16',publication_sequence:29};
 const next={...old,record_id:'next',publication_sequence:30};const newest={...old,record_id:'newest',publication_sequence:31};const today=current('korea',38.6).publication.record;
 const raw=[old,next,newest,today];const before=JSON.stringify(raw);
 const all=data.combinedPoints(data.availablePoints([],'korea',raw,[]));const dates=data.datedPoints(all);
 assert.equal(all.filter(p=>p.date==='2026-10-16').length,3);assert.equal(dates.filter(p=>p.date==='2026-10-16').length,1);assert.equal(dates.find(p=>p.date==='2026-10-16').id,'newest');assert.equal(dates.at(-1).date,'2026-10-19');assert.equal(JSON.stringify(raw),before);
 assert.equal(data.recordsForMarket(raw,'us','LIVE').length,0);
});
test('console primary chart/table group republications while details retain every publication',()=>{
 const hook=require('../src/app/components/use-monitoring.ts'),original=hook.useMonitoring;
 const today=current('korea',38.6);const live=[29,30,31].map(sequence=>({...today.publication.record,record_id:'pub-'+sequence,publication_sequence:sequence,observation_date:'2026-10-16',risk_score:31.6,msi:.788,generated_at:`2026-10-20T0${sequence-29}:09:20+00:00`}));
 live.push({...today.publication.record,msi:.743});const baseline=JSON.stringify(live);
 hook.useMonitoring=()=>({latest:today.publication,live,retrospective:[],loading:false,error:false,cursors:{LIVE:null,RETROSPECTIVE:null},loadMore:()=>{},retry:()=>{}});
 try{
  const html=render(Console,{market:'korea',latest:today.latest,history:[],shap:null});
  assert.equal((html.match(/data-date="2026-10-16"/g)||[]).length,1);
  assert.ok(html.includes('data-record-id="pub-31"'));assert.ok(!html.includes('data-record-id="pub-29"'));assert.ok(html.includes('3 publications'));assert.ok(html.includes('2026-10-19'));
  assert.equal(JSON.stringify(live),baseline);
 }finally{hook.useMonitoring=original;}
});

test('independent chart layers preserve same-date OOS, original values and publication identity',()=>{
 const history=[{date:'2026-09-16',risk_score_xgboost:21,msi:-.2,spy:100},{date:'2026-10-16',risk_score_xgboost:35,msi:.8,spy:99}];
 const live=[{...current().publication.record,record_id:'same-date-1',publication_sequence:10,observation_date:'2026-10-16',risk_score:61.2,msi:1.2},{...current().publication.record,record_id:'same-date-2',publication_sequence:11,observation_date:'2026-10-16',risk_score:62.3,msi:1.3}];
 const before=JSON.stringify({history,live});const all=data.combinedPoints(data.availablePoints(history,'us',live,[]));
 const chart=data.chartContext(all,20);assert.equal(chart.filter(p=>p.date==='2026-10-16').length,2);assert.equal(chart.find(p=>p.source==='OOS'&&p.date==='2026-10-16').score,35);assert.equal(chart.find(p=>p.source==='LIVE').id,'same-date-2');assert.equal(all.filter(p=>p.record).length,2);
 assert.equal(JSON.stringify({history,live}),before);
});
test('both markets/languages render provenance gap, independent paths, actual monitoring start and unavailable inputs',()=>{
 const hook=require('../src/app/components/use-monitoring.ts'),original=hook.useMonitoring;
 try{for(const market of ['us','korea'])for(const language of ['en','ko']){
  const history=[{date:'2026-09-15',risk_score_xgboost:25,msi:.1,[market==='us'?'spy':'kospi200']:100},{date:'2026-09-16',risk_score_xgboost:30,msi:.2,[market==='us'?'spy':'kospi200']:99}];
  const live=[{...current(market,61.2).publication.record,record_id:'first',observation_date:'2026-10-16',publication_sequence:10,generated_at:'2026-10-19T00:00:00Z',msi:.7},{...current(market,38.4).publication.record,record_id:'last',observation_date:'2026-10-19',publication_sequence:11,msi:.5}];
  hook.useMonitoring=()=>({latest:{record:live[1]},live,retrospective:[],loading:false,error:false,cursors:{LIVE:null,RETROSPECTIVE:null}});
  for(const Component of [Console,BuildUpPreview]){
   const html=render(Component,{market,history,latest:null,shap:null},language);
   assert.ok(html.includes('data-gap-start="2026-09-16"'));assert.ok(html.includes('data-gap-end="2026-10-16"'));
   assert.ok(html.includes(language==='ko'?'실제 LIVE 예측 기록 없음':'No LIVE forecast records'));
   assert.ok(html.includes('mc-monitoring-start'));assert.ok(html.includes('data-series-provenance="OOS"'));assert.ok(!html.includes('data-series-provenance="LIVE"'));
   assert.ok(html.includes('data-record-id="first"'));assert.ok(html.includes('data-record-id="last"'));
   assert.ok(html.includes('-22.8'));assert.ok(html.includes(language==='ko'?'운영 경고 해제':'Operational warning cleared'));
   assert.ok(!html.includes('>SAFE<'));
   if(Component===Console)assert.ok(html.includes(language==='ko'?'Publication API에서 제공되지 않음':'Not provided by publication API'));
  }
 }}finally{hook.useMonitoring=original;}
});
test('LIVE trend respects publication ordering, excludes republications as steps and never fills unknown scores',()=>{
 const a={...current('us',61.2).publication.record,record_id:'a',publication_sequence:10,observation_date:'2026-10-16'};
 const b={...current('us',38.4).publication.record,record_id:'b',publication_sequence:11};
 const rep={...b,record_id:'rep',publication_sequence:12};const before=JSON.stringify([a,b,rep]);
 const trend=data.liveRiskTrend([rep,a,b]);assert.equal(trend.previous.record_id,'a');assert.equal(trend.current.record_id,'rep');assert.ok(Math.abs(trend.change+22.8)<1e-9);assert.equal(trend.cleared,true);
 assert.equal(data.liveRiskTrend([a]),null);assert.equal(data.liveRiskTrend([b,rep]),null);assert.equal(data.liveRiskTrend([a,{...b,risk_score:null}]),null);
 assert.equal(data.liveRiskTrend([a,{...b,operational_warning:null}]).cleared,false);assert.equal(JSON.stringify([a,b,rep]),before);
});
test('unknown ledger coverage never claims a complete LIVE gap or monitoring start',()=>{
 const points=data.combinedPoints([...data.historicalPoints([{date:'2026-09-16',risk_score_xgboost:20}],'us'),...data.publicationPoints([{...current().publication.record,msi:.5}])]);
 const html=render(ConsoleChart,{points,selected:'',onSelect:()=>{},ledgerComplete:false});assert.ok(!html.includes('data-gap-start'));assert.ok(!html.includes('class="mc-monitoring-start"'));
});

test('US replay is bounded, explicitly PIT-unverified and cannot become a publication',()=>{
 const json=require('../src/app/components/us-retrospective-observations.json');const baseline=JSON.stringify(json);
 const points=data.archivePoints('us');assert.equal(points.length,17);assert.equal(points[0].date,'2026-09-17');assert.equal(points.at(-1).date,'2026-10-09');
 assert.ok(points.every(p=>p.source==='RETROSPECTIVE'&&p.record===null&&p.published===null&&p.health===null&&p.archive.pitVerified===false));
 assert.deepEqual(points.map(p=>p.score),json.observations.map(p=>p.score));assert.deepEqual(points.map(p=>p.msi),json.observations.map(p=>p.msi));
 assert.ok(points.every(p=>p.archive.modelSha256===json.model_sha256&&p.archive.sourceSha256===json.source_history_sha256));
 for(const date of ['2026-10-12','2026-10-13','2026-10-14','2026-10-15'])assert.ok(!points.some(p=>p.date===date));
 assert.equal(data.recordsForMarket(points,'us','LIVE').length,0);assert.equal(JSON.stringify(json),baseline);
});
test('US Overview/detail separate all three provenances, preserve missing sessions and localize PIT limits',()=>{
 const hook=require('../src/app/components/use-monitoring.ts'),original=hook.useMonitoring;
 const live=[{...current('us',16.9).publication.record,record_id:'us-existing-live',publication_sequence:1,observation_date:'2026-10-15',generated_at:'2026-10-19T07:00:18Z'}];const before=JSON.stringify(live);
 const history=[{date:'2026-09-16',risk_score_xgboost:29.7,msi:-.591,spy:752.18}];
 hook.useMonitoring=()=>({latest:{record:live[0]},live,retrospective:[],loading:false,error:false,cursors:{LIVE:null,RETROSPECTIVE:null}});
 try{for(const language of ['en','ko'])for(const Component of [Console,BuildUpPreview]){
  const html=render(Component,{market:'us',history,latest:null,shap:null},language);
  assert.ok(html.includes(language==='ko'?'사후 재계산 (PIT 미검증)':'Retrospective · PIT not verified'));
  assert.ok(html.includes('data-provenance="OOS"'));assert.equal((html.match(/data-provenance="RETROSPECTIVE"/g)||[]).length,17);assert.equal((html.match(/data-provenance="LIVE"/g)||[]).length,1);
  assert.ok(html.includes('data-record-id="us-existing-live"'));assert.ok(html.includes('data-gap-start="2026-09-16"'));
  assert.ok(html.includes('data-unavailable-dates="2026-10-12,2026-10-13,2026-10-14"'));
  for(const date of ['2026-10-12','2026-10-13','2026-10-14'])assert.ok(!html.includes(`data-date="${date}"`));
  const oos=html.match(/data-series-provenance="OOS"[\s\S]*?<path d="([^"]*)" class="mc-score-path/)[1];
  const retro=html.match(/data-series-provenance="RETROSPECTIVE"[\s\S]*?<path d="([^"]*)" class="mc-score-path/)[1];
  assert.equal((oos.match(/M/g)||[]).length,1);assert.ok(!oos.includes('L'));assert.equal((retro.match(/L/g)||[]).length,16);
  assert.ok(!html.includes('data-series-provenance="LIVE"'));
 }
 const all=data.combinedPoints(data.availablePoints(history,'us',live,[]));assert.equal(data.pointTrajectory(all,'archive-us-2026-09-17').change,null);assert.equal(data.pointTrajectory(all,'us-existing-live').change,null);
 assert.equal(JSON.stringify(live),before);
 }finally{hook.useMonitoring=original;}
});
