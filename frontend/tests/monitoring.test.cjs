const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');const test=require('node:test');const ts=require('typescript');
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,file)=>m._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true,jsx:ts.JsxEmit.ReactJSX}}).outputText,file);
const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');
const {I18nProvider}=require('../src/app/i18n/provider.tsx');const {translateText}=require('../src/app/i18n/messages.ts');
const data=require('../src/app/components/monitoring-data.ts');const {LivePublication,RiskTrajectory}=require('../src/app/components/MarketRiskTimeline.tsx');
const marketData=require('../src/app/components/market-data.ts');
const hash='a'.repeat(64);
const record=(seq=1,overrides={})=>({record_id:'fixture-'+seq,publication_sequence:seq,market:'korea',generated_at:'2026-10-16T07:58:51+00:00',observation_date:'2026-10-15',record_type:'LIVE',risk_score:40.5,operational_warning:false,msi:1.049,msi_stress_event:false,data_status:'CURRENT',data_freshness_status:'CURRENT',model_sha256:hash,input_snapshot_sha256:hash,source_history_sha256:hash,...overrides});
const history=[12.1,15.6,37.8,32.3,40.5].map((score,i)=>({date:['2026-10-08','2026-10-12','2026-10-13','2026-10-14','2026-10-15'][i],risk_score_xgboost:score,msi:[.298,.496,.744,.720,1.049][i],kospi200:[1044.52,1004.92,942.07,936.82,860.7][i]}));
function render(Component,props,language='en'){return renderToStaticMarkup(React.createElement(I18nProvider,{initialLanguage:language},React.createElement(Component,props)));}
function walk(value,predicate){if(!value||typeof value!=='object')return null;if(predicate(value))return value;const children=React.Children.toArray(value.props?.children);for(const child of children){const found=walk(child,predicate);if(found)return found;}return null;}
function trajectoryHarness(props,initial=['ALL',5,null],language='en'){
 let states=[...initial],tree;
 const original=React.useState;
 function paint(){let cursor=0;React.useState=initial=>{if(initial==='en'||initial==='ko')return original(initial);const index=cursor++;if(index<3)return [states[index],value=>{states[index]=typeof value==='function'?value(states[index]):value;}];return original(initial);};
  function Capture(){tree=RiskTrajectory(props);return tree;}
  try{return render(Capture,{},language);}finally{React.useState=original;}}
 return {paint,find:predicate=>walk(tree,predicate),states};
}
const props={market:'korea',history,live:[],retrospective:[],loadMore:()=>{},cursors:{LIVE:null,RETROSPECTIVE:null}};

test('strict market/type and timezone checks never promote retrospective observations',()=>{
 const rows=[record(),record(2,{market:'us'}),record(3,{record_type:'RETROSPECTIVE'}),record(4,{generated_at:'2026-10-16T07:58:51'})];
 assert.deepEqual(data.recordsForMarket(rows,'korea','LIVE').map(r=>r.record_id),['fixture-1']);
 assert.deepEqual(data.recordsForMarket(rows,'korea','RETROSPECTIVE').map(r=>r.record_id),['fixture-3']);
 assert.equal(data.historicalPoints(history,'korea')[0].source,'OOS');
});
test('latest per date uses publication sequence and preserves every republication separately',()=>{
 const all=data.publicationPoints([record(8,{risk_score:38}),record(2,{risk_score:40.5})]);
 assert.equal(all.length,2);assert.equal(data.datedPoints(all)[0].score,38);
});
test('historical prices calculate adjacent returns but never invent publication times or event flags',()=>{
 const points=data.historicalPoints(history,'korea');assert.equal(points[0].movement,null);
 assert.ok(Math.abs(points.at(-1).movement-(-8.1253602613))<1e-7);
 for(const p of points){assert.equal(p.warning,null);assert.equal(p.stress,null);assert.equal(p.published,null);assert.equal(p.health,null);}
 assert.equal(data.historicalPoints([{date:'2020-01-01',spy:null},{date:'2020-01-02',spy:100}],'us')[1].movement,null);
 assert.equal(data.publicationPoints([record()])[0].movement,null);
});
test('score direction, speed and persistence are observations, not alert categories',()=>{
 const points=data.historicalPoints(history,'korea');assert.ok(Math.abs(data.trajectory(points,'2026-10-13').change-22.2)<1e-9);
 assert.equal(data.trajectory(points,'2026-10-13').increases,2);
 assert.equal(data.trajectory(points,'2026-10-14').increases,0);
 assert.ok(Math.abs(data.trajectory(points,'2026-10-15').change-8.2)<1e-9);
 assert.equal(data.trajectory(points,'2026-10-08').change,null);
});
test('October15 observation always exposes October16 publication in KST',()=>{
 assert.match(data.publicationTime(record().generated_at,'en-US'),/10\/16\/2026, 16:58 KST/);
 assert.equal(data.publicationTime('2026-10-15','en-US'),'—');
});
for(const language of ['en','ko']){
 test(language+': empty live ledger is truthful, distinct from unavailable fetch',()=>{
  const empty=render(LivePublication,{latest:{market:'korea',record:null,current_data_health:{status:'UNAVAILABLE'}},loading:false,error:false,retry:()=>{}},language);
  assert.ok(empty.includes(translateText(language,'LIVE Monitoring — Awaiting first prospective publication')));
  const failed=render(LivePublication,{latest:null,loading:false,error:true,retry:()=>{}},language);
  assert.ok(failed.includes(translateText(language,'Publication ledger unavailable')));
  assert.ok(!failed.includes(translateText(language,'LIVE Monitoring — Awaiting first prospective publication')));
 });
 test(language+': populated live record keeps stale health independent of warning and original dates',()=>{
  const markup=render(LivePublication,{latest:{market:'korea',record:record(),current_data_health:{status:'STALE'}},loading:false,error:false,retry:()=>{}},language);
  for(const value of ['2026-10-15','16:58 KST','40.5','1.049',translateText(language,'Not triggered'),translateText(language,'STALE')])assert.ok(markup.includes(value),value);
  assert.ok(markup.includes(translateText(language,'Fingerprints recorded · not independently verified')));
 });
 test(language+': date controls select observations and retain retrospective publication timing',()=>{
  const retrospective=history.map((r,i)=>record(i+1,{record_id:'retro-'+i,record_type:'RETROSPECTIVE',observation_date:r.date,risk_score:r.risk_score_xgboost,msi:r.msi}));
  const harness=trajectoryHarness({...props,retrospective},['RETROSPECTIVE',60,null],language);
  let markup=harness.paint();assert.ok(markup.includes('40.5'));
  const select=harness.find(node=>node.type==='select'&&React.Children.toArray(node.props.children).some(child=>child.props?.value==='retro-2'));
  select.props.onChange({target:{value:'retro-2'}});markup=harness.paint();
  assert.ok(markup.includes('<time dateTime="2026-10-13">2026-10-13</time>'));
  assert.ok(markup.includes('37.8'));assert.ok(markup.includes('22.2'));
  assert.ok(markup.includes(translateText(language,'Risk increasing')));
  assert.ok(markup.includes('16:58 KST'));
  assert.ok(markup.includes(translateText(language,'RETROSPECTIVE')));
  select.props.onChange({target:{value:'retro-3'}});markup=harness.paint();assert.ok(markup.includes('32.3'));assert.ok(markup.includes(translateText(language,'Risk decreasing')));
 });
 test(language+': LIVE highlight never removes verified history and OOS evidence stays selectable',()=>{
  const harness=trajectoryHarness(props,['LIVE',60,null],language);let markup=harness.paint();
  assert.ok(markup.includes('score-path'));
  for(const score of ['12.1','15.6','37.8','32.3','40.5'])assert.ok(markup.includes(score));
  const tab=harness.find(node=>node.type==='button'&&node.props.children?.props?.children==='HISTORICAL OOS');
  tab.props.onClick();markup=harness.paint();assert.ok(markup.includes('score-path'));
  assert.ok(markup.includes(translateText(language,'Not recorded · no publication-time claim')));
  assert.ok(markup.includes(translateText(language,'HISTORICAL OOS')));
 });
}
test('same-date older publication remains selectable and changes plotted score consistently',()=>{
 const harness=trajectoryHarness({...props,live:[record(2,{risk_score:38}),record(1)]},['ALL',5,'fixture-2']);harness.paint();
 const select=harness.find(node=>node.type==='select'&&node.props.value==='fixture-2');
 select.props.onChange({target:{value:'fixture-1'}});const markup=harness.paint();assert.ok(markup.includes('40.5'));
 const chart=harness.find(node=>typeof node.type==='function'&&node.type.name==='TrackChart');assert.equal(chart.props.points.find(p=>p.id==='fixture-1').score,40.5);
});
test('unknown provenance never displays independent verification',()=>{
 assert.equal(data.provenance(record(1,{model_sha256:null})),'Provenance incomplete');
 assert.equal(data.provenance(null),'Not recorded');
});
test('both markets use only operational threshold50 and preserve unrounded API warning',()=>{
 for(const market of ['us','korea'])for(const score of [12.1,29,30,37.8,49.9])assert.equal(marketData.signal(market,{last_updated:'2026-10-15',risk_score_10d:score,market_stress_index:.5}),'BELOW WARNING');
 assert.equal(marketData.signal('us',{last_updated:'2026-10-15',risk_score_10d:50,warning_active:false,market_stress_index:.5}),'BELOW WARNING');
});
test('monitoring proxies coexist with existing authenticated workspace route',async()=>{
 const config=(await import('../next.config.mjs')).default;const rewrites=await config.rewrites();
 for(const endpoint of ['monitoring/latest','monitoring/history'])assert.ok(rewrites.some(r=>r.source==='/api/'+endpoint));
 assert.ok(!rewrites.some(r=>r.source.includes('workspace')));
 const css=fs.readFileSync(path.join(__dirname,'../src/app/globals.css'),'utf8');
 assert.ok(css.includes('@media(max-width:480px)'));assert.ok(css.includes('.trajectory-chart-scroll { overflow-x:auto;'));
 assert.ok(css.includes('.publication-grid { grid-template-columns:repeat(2,minmax(0,1fr))'));
});
test('chart pointer selects the closest actual observation date',()=>{
 const harness=trajectoryHarness(props,['OOS',60,null]);harness.paint();
 const chart=harness.find(node=>typeof node.type==='function'&&node.type.name==='TrackChart');let root;
 function Capture(){root=chart.type(chart.props);return root;}
 render(Capture,{});
 const svg=walk(root,node=>node.type==='svg');
 svg.props.onClick({clientX:621,clientY:100,currentTarget:{getScreenCTM:()=>({inverse:()=>({})}),createSVGPoint:()=>({matrixTransform(){return {x:this.x,y:this.y};}})}});
 const markup=harness.paint();assert.ok(markup.includes('<time dateTime="2026-10-13">2026-10-13</time>'));
});
test('current snapshot summaries also display actual publication time independently of observation',()=>{
 const Card=require('../src/app/components/MarketMonitorCard.tsx').default;
 const {KoreaMonitorHero}=require('../src/app/components/KoreaMonitor.tsx');
 const latest={last_updated:'2026-10-15',risk_score_10d:40.5,warning_active:false,market_stress_index:1.049,stress_threshold:1.116,is_stress_event:false,data_health:{status:'CURRENT',published_at:'2026-10-16T07:58:51+00:00',input_series:[]}};
 for(const language of ['en','ko'])for(const [Component,props] of [[Card,{market:'us',latest}],[KoreaMonitorHero,{latest,status:'BELOW WARNING'}]]){
  const markup=render(Component,props,language);assert.ok(markup.includes('16:58 KST'));assert.ok(markup.includes('40.5'));assert.ok(markup.includes('2026-10-15'));
 }
});

test('default view shows the verified Korea sequence without requiring a LIVE ledger or source click',()=>{
 const markup=render(RiskTrajectory,{...props,history:[]});
 const sequence=markup.split('class="trajectory-sequence"')[1].split('class="trajectory-readout"')[0];
 assert.deepEqual([...sequence.matchAll(/<strong>([\d.]+)<\/strong>/g)].map(m=>m[1]),['12.1','15.6','37.8','32.3','40.5']);
 assert.ok(markup.includes('score-path'));assert.ok(sequence.includes('RETRO'));assert.ok(!sequence.includes('>LIVE<'));
 const archive=data.archivePoints('korea');assert.ok(archive.every(p=>p.source==='RETROSPECTIVE'&&p.record===null));assert.equal(data.archivePoints('us').length,17);
});
test('archive replay dates have no publication-time claim and snapshot dates retain actual publication times',()=>{
 const points=data.archivePoints('korea');
 for(const date of ['2026-10-12','2026-10-14']){const p=points.find(p=>p.date===date);assert.equal(p.published,null);assert.equal(p.archive.basis,'Frozen-model replay');assert.equal(p.health,null);}
 assert.match(data.publicationTime(points.at(-1).published,'en-US'),/10\/16\/2026, 16:58 KST/);
 assert.ok(points.every(p=>p.warning===false&&p.stress===false));assert.ok(Math.abs(points.at(-1).movement+8.125360261309533)<1e-12);
});
test('mixed provenance keeps publication evidence authoritative while retaining every alternative',()=>{
 const all=data.availablePoints(history,'korea',[record(10,{risk_score:41})],[record(11,{record_type:'RETROSPECTIVE',risk_score:42})]);
 const dated=data.datedPoints(all);assert.equal(dated.at(-1).score,41);assert.equal(dated.at(-1).source,'LIVE');assert.equal(all.filter(p=>p.date==='2026-10-15').length,4);
 assert.ok(data.availablePoints(history,'us',[],[]).every(p=>p.source==='OOS'||(p.source==='RETROSPECTIVE'&&p.archive?.pitVerified===false)));
});
test('default US view renders OOS scores without manufacturing publication timestamps',()=>{
 const markup=render(RiskTrajectory,{...props,market:'us',history:history.map(({kospi200,...row})=>({...row,spy:kospi200}))});assert.ok(markup.includes('score-path'));assert.ok(markup.includes('HISTORICAL OOS'));assert.ok(markup.includes('Not recorded · no publication-time claim'));assert.ok(markup.includes('Retrospective · PIT not verified'));
});
test('recent sequence buttons select replay and recorded dates with truthful details',()=>{
 const h=trajectoryHarness({...props,history:[]});h.paint();
 const replay=h.find(n=>n.type==='button'&&n.props['aria-label']==='2026-10-14 · RETROSPECTIVE · 32.3');replay.props.onClick();let markup=h.paint();assert.ok(markup.includes('Frozen-model replay'));assert.ok(markup.includes('Not recorded · no publication-time claim'));assert.ok(markup.includes('-5.5'));
 h.find(n=>n.type==='button'&&n.props['aria-label']==='2026-10-15 · RETROSPECTIVE · 40.5').props.onClick();markup=h.paint();assert.ok(markup.includes('16:58 KST'));assert.ok(markup.includes('8.2'));assert.ok(markup.includes('Stored snapshot'));
});
test('empty LIVE status remains compact and does not render a latest-publication grid',()=>{
 const markup=render(LivePublication,{latest:{market:'korea',record:null,current_data_health:{status:'UNAVAILABLE'}},loading:false,error:false,retry:()=>{}});
 assert.ok(markup.includes('live-status is-empty'));assert.ok(!markup.includes('publication-grid'));assert.ok(!markup.includes('Latest Published Observation'));
});

test('provenance transitions never imply a continuous score change or warning persistence',()=>{
 const old=data.historicalPoints([{date:'2026-10-05',risk_score_xgboost:90}],'korea')[0];const recent=data.archivePoints('korea')[0];
 const change=data.trajectory([old,recent],recent.date);assert.equal(change.change,null);assert.equal(change.steps,0);assert.equal(change.increases,0);
 const h=trajectoryHarness({...props,history:[{date:'2026-10-05',risk_score_xgboost:90}]},['ALL',0,null]);h.paint();const chart=h.find(n=>typeof n.type==='function'&&n.type.name==='TrackChart');let root;
 function Capture(){root=chart.type(chart.props);return root;}render(Capture,{});const path=walk(root,n=>n.type==='path'&&n.props.className==='score-path');assert.equal((path.props.d.match(/M/g)||[]).length,2);
 assert.equal(walk(root,n=>n.type==='line'&&n.props.className==='operational-reference').props.y1,127.5);
});

test('date metrics table selects the same observation as chart and sequence controls',()=>{
 const h=trajectoryHarness({...props,history:[]});h.paint();const row=h.find(n=>n.type==='tr'&&React.Children.toArray(n.props.children).some(c=>c.props?.children?.props?.children==='2026-10-14'));
 assert.ok(row);row.props.onClick();const markup=h.paint();assert.ok(markup.includes('32.3'));assert.ok(markup.includes('Frozen-model replay'));assert.ok(markup.includes('Not recorded · no publication-time claim'));
 const live=h.find(n=>n.type==='button'&&n.props.children?.props?.children==='LIVE');assert.equal(live.props.disabled,true);
});

test('combined chart retains same-date publications and deduplicates only repeated identities',()=>{
 const a=record(1),b=record(2,{risk_score:16.9});
 const points=data.combinedPoints(data.availablePoints([], 'korea',[a,a,b],[]));
 assert.equal(points.filter(p=>p.record).length,2);
 assert.ok(points.some(p=>p.score===40.5&&p.archive));
 assert.deepEqual(points.filter(p=>p.record).map(p=>p.id),['fixture-1','fixture-2']);
 assert.equal(data.pointTrajectory(points,'fixture-2').change,null);
});
for(const date of ['2026-10-15','2026-10-19','2026-10-01'])test('one LIVE '+date+' extends, never replaces, all five archive observations even with LIVE highlighted',()=>{
 const live=[record(9,{observation_date:date,generated_at:'2026-10-20T00:00:00Z',risk_score:44.4})];
 const all=data.combinedPoints(data.availablePoints([],'korea',live,[]));
 const points=data.buildUpWindow(all,5);
 assert.equal(points.length,6);assert.equal(points.filter(p=>p.archive).length,5);
 const h=trajectoryHarness({...props,history:[],live},['LIVE',5,null]);h.paint();
 const chart=h.find(n=>typeof n.type==='function'&&n.type.name==='TrackChart');
 assert.equal(chart.props.points.length,6);assert.ok(chart.props.points.some(p=>p.id==='fixture-9'));
});
test('Korea composition rejects US publications and US historical prices at its boundary',()=>{
 const us=record(7,{market:'us',risk_score:16.9});
 const points=data.availablePoints([{date:'2026-10-15',spy:100,risk_score_xgboost:16.9}],'korea',[us],[{...us,record_type:'RETROSPECTIVE'}]);
 assert.equal(points.length,5);assert.ok(points.every(p=>p.archive));
 assert.equal(data.historicalPoints([{date:'2026-10-15',market:'us',risk_score_xgboost:16.9}],'korea').length,0);
});
