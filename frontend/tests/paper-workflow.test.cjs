const fs=require('node:fs');
const ts=require('typescript');
const assert=require('node:assert/strict');
const {test}=require('node:test');
require.extensions['.ts']=(module,file)=>module._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText,file);
require.extensions['.tsx']=require.extensions['.ts'];
// Include JSX transformation for component interaction tests without a browser dependency.
require.extensions['.tsx']=(module,file)=>module._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true,jsx:ts.JsxEmit.ReactJSX}}).outputText,file);
const {rankSecurities,searchSecurities,settlementPortfolio,selectedQuote,estimatedOrder,quoteFailure}=require('../src/app/paper-trading/workflow.ts');
const {ApiError}=require('../src/app/paper-trading/types.ts');
const securities=[
 ['us','AAPL','Apple Inc.','USD'],['us','QQQ','Invesco QQQ','USD'],['us','PLTR','Palantir Technologies','USD'],
 ['korea','005930','삼성전자','KRW'],['korea','000660','SK하이닉스','KRW'],
].map(([market,ticker,name,currency])=>({market,ticker,symbol:market==='us'?ticker:`${ticker}.KS`,name,currency,exchange:market==='us'?'Nasdaq':'KOSPI',security_type:ticker==='QQQ'?'ETF':'Stock'}));
const quoteFor=(security,extra={})=>({id:'test-quote',market:security.market,symbol:security.symbol,currency:security.currency,price:security.market==='us'?100.25:75000,observed_at:'2026-10-14T15:30:00+09:00',source:'Mock validated close',expires_at:Math.floor(Date.now()/1000)+120,...extra});
const reply=(data,status=200)=>{
 if(data.quote_id && data.market && status===200)data={settlement_id:'fixture-preview',currency:data.market==='us'?'USD':'KRW',costs:{gross_minor:0,commission_minor:0,transaction_tax_minor:0,regulatory_fee_minor:0,total_fees_minor:0,net_minor:0,trade_date:'2026-10-15',policy_version:'fixture-zero-cost',components:[]},remaining_cash:{USD:100000,KRW:0},total_cash_effect:0,...data};
 return {ok:status===200,status,json:async()=>data};
};
for(const query of ['AAPL','QQQ','PLTR','005930','삼성전자','000660'])test(`unified search: ${query}`,async()=>{
 const calls=[];
 global.fetch=async url=>{calls.push(url);const parsed=new URL(url,'http://test');const market=parsed.searchParams.get('market');return reply({data:securities.filter(s=>s.market===market&&(s.ticker===query||s.name===query))});};
 const result=await searchSecurities(query,'all',new AbortController().signal);
 assert.equal(result.data.length,1);assert.ok(result.data[0].ticker===query||result.data[0].name===query);
 assert.equal(calls.length,2);assert.ok(calls.every(url=>url.includes('/paper/securities?')));
});
test('mixed market ranking, duplicates and Unicode normalization',()=>{
 const original=securities[0];const prefix={...original,symbol:'AAPLX',ticker:'AAPLX'};
 const exactName={...securities[3],name:'AAPL'};const namePrefix={...securities[4],name:'AAPL Korea'};
 const partial={...securities[2],name:'Test AAPL stock'};
 assert.deepEqual(rankSecurities([partial,namePrefix,exactName,prefix,original,original],'ＡＡＰＬ').map(s=>s.symbol),[original.symbol,prefix.symbol,exactName.symbol,namePrefix.symbol,partial.symbol]);
 assert.equal(rankSecurities(securities,'').length,0);
});
test('market-specific search remains one request; partial market failure is explicit',async()=>{
 let calls=0;global.fetch=async url=>{calls++;return url.includes('market=us')?reply({data:[securities[0]],directory_status:'STALE'}):reply({detail:'Unavailable'},503);};
 const us=await searchSecurities('AAPL','us',new AbortController().signal);assert.equal(calls,1);assert.equal(us.stale,true);
 const all=await searchSecurities('AAPL','all',new AbortController().signal);assert.equal(all.partial,true);assert.equal(all.data[0].market,'us');
 global.fetch=async()=>reply({detail:'Unavailable'},503);await assert.rejects(searchSecurities('AAPL','all',new AbortController().signal));
});
for(const security of [securities[0],securities[1],securities[3]])test(`${security.ticker}: explicit selection loads a validated quote and estimates quantity 5`,async()=>{
 let called;global.fetch=async url=>{called=url;return reply(quoteFor(security));};
 const quote=await selectedQuote(security,new AbortController().signal);
 assert.ok(called.includes(`market=${security.market}&symbol=${encodeURIComponent(security.symbol)}`));
 assert.equal(estimatedOrder(quote,'5'),quote.price*5);
 for(const invalid of ['0','-1','1.5','1000001','NaN'])assert.equal(estimatedOrder(quote,invalid),null);
});
for(const patch of [{expires_at:0},{price:NaN},{price:-1},{market:'korea'},{currency:'KRW'},{symbol:'WRONG'},{observed_at:'invalid'}])test(`unusable quote rejected: ${JSON.stringify(patch)}`,async()=>{
 global.fetch=async()=>reply(quoteFor(securities[1],patch));await assert.rejects(selectedQuote(securities[1],new AbortController().signal),/unusable/);
});
test('quote failure: provider, unavailable/stale and network errors are safe and explainable',async()=>{
 for(const message of ['Price source unavailable. No simulated trade can be executed without a valid price.','A sufficiently recent valid completed close is unavailable. Trading is disabled for this security.']) {
  global.fetch=async()=>reply({detail:message},503);
  await assert.rejects(selectedQuote(securities[0],new AbortController().signal),error=>{assert.ok(quoteFailure(error).includes(message.startsWith('A sufficiently')?'recent':'temporarily'));return true;});
 }
 assert.ok(!quoteFailure(new Error('secret internal stack')).includes('secret'));
});
test('cancelled quote cannot be accepted even if provider ignores abort',async()=>{
 const controller=new AbortController();global.fetch=async()=>{controller.abort();return reply(quoteFor(securities[0]));};
 await assert.rejects(selectedQuote(securities[0],controller.signal),{name:'AbortError'});
});
test('settlement book selection rejects cross-market or cross-currency books',()=>{
 const us={market:'us',currency:'USD',cash:1000},korea={market:'korea',currency:'KRW',cash:10000000};
 assert.equal(settlementPortfolio('us',{us,korea}),us);assert.equal(settlementPortfolio('korea',{us,korea}),korea);
 assert.equal(settlementPortfolio('us',{us:korea}),null);assert.equal(settlementPortfolio('korea',{korea:{...korea,currency:'USD'}}),null);
 assert.equal(settlementPortfolio('us',{}),null);
});

// Exercise actual ticket handlers, not a copy of its selection/quote/quantity logic.
const React=require('react');const i18n=require('../src/app/i18n/provider.tsx');
const Ticket=require('../src/app/paper-trading/TradeTicket.tsx').default;
const Picker=require('../src/app/paper-trading/SecurityPicker.tsx').default;
const Risk=require('../src/app/paper-trading/MarketRiskPanel.tsx').default;
function nodes(node,predicate) {
 if(!node||typeof node!=='object')return [];
 if(Array.isArray(node))return node.flatMap(n=>nodes(n,predicate));
 return [...(predicate(node)?[node]:[]),...nodes(node.props?.children,predicate)];
}
function harness() {
 const original={useState:React.useState,useRef:React.useRef,useEffect:React.useEffect,useI18n:i18n.useI18n};
 const previousStorage=global.sessionStorage;global.sessionStorage=previousStorage||{getItem:()=>null};
 const state=[],refs=[],effects=[];let index=0,refIndex=0,effectIndex=0;
 React.useState=initial=>{const key=index++;if(!(key in state))state[key]=typeof initial==='function'?initial():initial;return[state[key],value=>{state[key]=typeof value==='function'?value(state[key]):value;}];};
 React.useRef=initial=>{const key=refIndex++;return refs[key]??(refs[key]={current:initial});};React.useEffect=(callback,deps)=>{const key=effectIndex++;const previous=effects[key];if(!previous||deps.some((dep,i)=>!Object.is(dep,previous.deps[i])))effects[key]={callback,deps,pending:true,cleanup:previous?.cleanup};};i18n.useI18n=()=>({locale:'en-US',t:s=>s});
 const us={market:'us',currency:'USD',cash:100000,positions:[]};const korea={market:'korea',currency:'KRW',cash:10000000,positions:[]};
 const render=()=>{index=0;refIndex=0;effectIndex=0;return Ticket({portfolios:{us,korea},userId:22,csrf:'test-csrf',onExecuted:()=>{}});};
 return {render,state,flushEffects:()=>{for(const effect of effects)if(effect.pending){effect.cleanup?.();effect.pending=false;effect.cleanup=effect.callback();}},restore:()=>{global.sessionStorage=previousStorage;React.useState=original.useState;React.useRef=original.useRef;React.useEffect=original.useEffect;i18n.useI18n=original.useI18n;}};
}
for(const security of [securities[0],securities[1],securities[3]])test(`ticket interaction: ${security.ticker} -> auto quote -> quantity -> correct book, risk and review`,async()=>{
 const h=harness();try {
  const calls=[];global.fetch=async url=>{calls.push(url);if(url.includes('/paper/settlement?'))return reply({quote_id:'test-quote',market:security.market,symbol:security.symbol,side:'BUY',quantity:5,fx_usd_cents:0,fx_krw:0,fx:null});return reply(quoteFor(security));};
  let tree=h.render();const picker=nodes(tree,n=>n.type===Picker)[0];assert.equal(picker.props.market,'all');
  picker.props.onSelect(security);await new Promise(resolve=>setImmediate(resolve));tree=h.render();
  nodes(tree,n=>n.type==='input'&&n.props.type==='number')[0].props.onChange({target:{value:'5'}});tree=h.render();h.flushEffects();await new Promise(resolve=>setTimeout(resolve,220));tree=h.render();
  const text=JSON.stringify(tree);assert.ok(text.includes(security.currency));assert.ok(text.includes((quoteFor(security).price*5).toLocaleString('en-US',{style:'currency',currency:security.currency,currencyDisplay:'narrowSymbol',maximumFractionDigits:security.currency==='KRW'?0:2})));
  assert.equal(nodes(tree,n=>n.type===Risk)[0].props.market,security.market);
  const review=nodes(tree,n=>n.type==='button'&&n.props.onClick?.name==='prepare')[0];assert.equal(review.props.disabled,false);review.props.onClick();
  tree=h.render();assert.ok(nodes(tree,n=>n.props?.className==='order-review').length);
  assert.equal(calls.filter(url=>url.includes('/paper/quote?')).length,1);assert.ok(calls.some(url=>url.includes('/paper/settlement?')));
 }finally{h.restore();}
});
test('ticket rapid selection ignores an obsolete quote and remains on the new currency book',async()=>{
 const h=harness();try {
  let finishUS;
  global.fetch=async url=>url.includes('market=us')?await new Promise(resolve=>finishUS=()=>resolve(reply(quoteFor(securities[0])))):reply(quoteFor(securities[3]));
  nodes(h.render(),n=>n.type===Picker)[0].props.onSelect(securities[0]);
  nodes(h.render(),n=>n.type===Picker)[0].props.onSelect(securities[3]);
  await new Promise(resolve=>setImmediate(resolve));finishUS();await new Promise(resolve=>setImmediate(resolve));
  const tree=h.render();assert.equal(nodes(tree,n=>n.type===Risk)[0].props.market,'korea');assert.ok(JSON.stringify(tree).includes('₩75,000'));
 }finally{h.restore();}
});

for(const failure of ['provider','stale','expired'])test(`ticket quote failure ${failure}: explanation shown and review disabled`,async()=>{
 const h=harness();try {
  global.fetch=async()=>failure==='expired'?reply(quoteFor(securities[1],{expires_at:0})):reply({detail:failure==='stale'?'A sufficiently recent valid completed close is unavailable. Trading is disabled for this security.':'Price source unavailable. No simulated trade can be executed without a valid price.'},503);
  nodes(h.render(),n=>n.type===Picker)[0].props.onSelect(securities[1]);await new Promise(resolve=>setImmediate(resolve));
  const tree=h.render();assert.equal(nodes(tree,n=>n.type==='button'&&n.props.onClick?.name==='prepare')[0].props.disabled,true);
  const error=nodes(tree,n=>n.props?.role==='alert')[0];assert.ok(error);
  assert.ok(JSON.stringify(error).includes(failure==='stale'?'recent':failure==='expired'?'unusable':'temporarily'));
 }finally{h.restore();}
});
test('typing/search reset never retrieves quotes and clears an existing estimate',async()=>{
 const h=harness();try {
  let calls=0;global.fetch=async()=>{calls++;return reply(quoteFor(securities[1]));};
  nodes(h.render(),n=>n.type===Picker)[0].props.onSelect(securities[1]);await new Promise(resolve=>setImmediate(resolve));
  nodes(h.render(),n=>n.type===Picker)[0].props.onSearchStart();const tree=h.render();assert.equal(calls,1);
  assert.equal(nodes(tree,n=>n.type==='button'&&n.props.onClick?.name==='prepare')[0].props.disabled,true);
 }finally{h.restore();}
});

for(const book of ['us','korea'])test(`pending ${book} order is restored from its own book after unified reload`,()=>{
 const h=harness();const previous=global.sessionStorage;
 const request={market:book,symbol:book==='us'?'QQQ':'005930.KS',side:'BUY',quantity:5,quote_id:'existing-server-quote',request_key:'existing-idempotency-key'};
 const key=`mri-pending-order:22:${book}`;
 global.sessionStorage={getItem:lookup=>lookup===key?JSON.stringify(request):null,removeItem:()=>assert.fail('Valid pending request must be preserved')};
 try {
  h.render();h.flushEffects();h.render();h.flushEffects();const tree=h.render();
  assert.deepEqual(h.state[5],request);assert.equal(nodes(tree,n=>n.type===Risk)[0].props.market,book);
  assert.equal(nodes(tree,n=>n.type===Picker)[0].props.disabled,true);
 }finally{global.sessionStorage=previous;h.restore();}
});

test('Korean review explicitly includes FX funding consent and USD equivalent',async()=>{
 const h=harness();try {
  const security=securities[3];
  global.fetch=async url=>url.includes('/paper/settlement?')?reply({quote_id:'test-quote',market:'korea',symbol:security.symbol,side:'BUY',quantity:5,fx_usd_cents:37500,fx_krw:375000,from_currency:'USD',to_currency:'KRW',base_order_value_usd:375,fx:{rate:1000,source:'Fixture FRED',observation_date:'2026-10-14'}}):reply(quoteFor(security));
  nodes(h.render(),n=>n.type===Picker)[0].props.onSelect(security);await new Promise(resolve=>setImmediate(resolve));
  nodes(h.render(),n=>n.type==='input'&&n.props.type==='number')[0].props.onChange({target:{value:'5'}});
  h.render();h.flushEffects();await new Promise(resolve=>setTimeout(resolve,220));let tree=h.render();
  assert.ok(JSON.stringify(tree).includes('capital_conversion_consent'));
  assert.ok(JSON.stringify(tree).includes('$375.00'));
  const review=nodes(tree,n=>n.type==='button'&&n.props.onClick?.name==='prepare')[0];assert.equal(review.props.disabled,false);review.props.onClick();
  assert.equal(h.state[5].fx_usd_cents,37500);assert.equal(h.state[5].fx_krw,375000);assert.ok(h.state[5].settlement_id);
 }finally{h.restore();}
});
test('unavailable FX settlement leaves stock quote visible but blocks order review',async()=>{
 const h=harness();try {
  const security=securities[3];
  global.fetch=async url=>url.includes('/paper/settlement?')?reply({detail:'Validated USD/KRW FX is required to cover the settlement currency shortfall. Refresh the quote.'},503):reply(quoteFor(security));
  nodes(h.render(),n=>n.type===Picker)[0].props.onSelect(security);await new Promise(resolve=>setImmediate(resolve));
  h.render();h.flushEffects();await new Promise(resolve=>setTimeout(resolve,220));const tree=h.render();
  assert.ok(JSON.stringify(tree).includes('₩75,000'));assert.ok(nodes(tree,n=>n.props?.role==='alert').length>0);
  assert.equal(nodes(tree,n=>n.type==='button'&&n.props.onClick?.name==='prepare')[0].props.disabled,true);
 }finally{h.restore();}
});

const {NextRequest}=require('next/server');
const workspaceProxy=require('../src/app/api/workspace/[...path]/route.ts');
for(const path of ['paper/investment','paper/settlement','paper/fx-ledger','paper/fx'])test(`workspace proxy forwards ${path} with session and query intact`,async()=>{
 let forwarded;global.fetch=async(url,options)=>{forwarded={url,options};return new Response('{"ok":true}',{status:200,headers:{'content-type':'application/json'}});};
 const request=new NextRequest(`http://localhost:3000/api/workspace/${path}?quantity=5`,{headers:{cookie:'mri_paper_session=fixture-session'}});
 const result=await workspaceProxy.GET(request,{params:Promise.resolve({path:path.split('/')})});
 assert.equal(result.status,200);assert.ok(forwarded.url.endsWith(`/api/${path}?quantity=5`));
 assert.equal(forwarded.options.headers.get('cookie'),'mri_paper_session=fixture-session');assert.equal(forwarded.options.cache,'no-store');
});
test('FX order approval traverses proxy unchanged with CSRF and same-origin enforcement',async()=>{
 const body={market:'korea',symbol:'005930.KS',quantity:5,fx_usd_cents:37500,fx_krw:375000};let forwarded;
 global.fetch=async(url,options)=>{forwarded={url,options};return new Response('{}',{status:201});};
 const headers={host:'localhost:3000',origin:'http://localhost:3000','content-type':'application/json','x-csrf-token':'fixture-csrf',cookie:'mri_paper_session=fixture-session'};
 const good=new NextRequest('http://localhost:3000/api/workspace/paper/orders',{method:'POST',headers,body:JSON.stringify(body)});
 assert.equal((await workspaceProxy.POST(good,{params:Promise.resolve({path:['paper','orders']})})).status,201);
 assert.deepEqual(JSON.parse(forwarded.options.body),body);assert.equal(forwarded.options.headers.get('x-csrf-token'),'fixture-csrf');
 const bad=new NextRequest('http://localhost:3000/api/workspace/paper/orders',{method:'POST',headers:{...headers,origin:'https://evil.invalid'},body:JSON.stringify(body)});
 assert.equal((await workspaceProxy.POST(bad,{params:Promise.resolve({path:['paper','orders']})})).status,403);
});
test('workspace proxy continues to reject arbitrary upstream paths',async()=>{
 global.fetch=()=>assert.fail('Unknown paths must never reach the API');
 const request=new NextRequest('http://localhost:3000/api/workspace/paper/arbitrary');
 assert.equal((await workspaceProxy.GET(request,{params:Promise.resolve({path:['paper','arbitrary']})})).status,404);
});

test('complete cost preview renders fees, net cash and preserves server approval token',async()=>{
 const h=harness();try {
  const security=securities[3];
  const costs={gross_minor:375000,commission_minor:56,transaction_tax_minor:0,regulatory_fee_minor:0,total_fees_minor:56,net_minor:375056,trade_date:'2026-10-15',policy_version:'production-fee-fixture',components:[]};
  global.fetch=async url=>url.includes('/paper/settlement?')?reply({settlement_id:'reviewed-cost-token',quote_id:'test-quote',market:'korea',symbol:security.symbol,side:'BUY',quantity:5,currency:'KRW',fx_usd_cents:37544,fx_krw:375064,from_currency:'USD',to_currency:'KRW',costs,total_cash_effect:375056,remaining_cash:{USD:99624.56,KRW:8},fx_spread_bps:'10',effective_fx_rate:'999',fx_cost_usd_exact:'0.376'}):reply(quoteFor(security));
  nodes(h.render(),n=>n.type===Picker)[0].props.onSelect(security);await new Promise(resolve=>setImmediate(resolve));
  nodes(h.render(),n=>n.type==='input'&&n.props.type==='number')[0].props.onChange({target:{value:'5'}});
  h.render();h.flushEffects();await new Promise(resolve=>setTimeout(resolve,220));const tree=h.render();const rendered=JSON.stringify(tree);
  for(const label of ['cost_commission','cost_transaction_tax','cost_regulatory','cost_remaining_usd','cost_remaining_krw','cost_assumptions'])assert.ok(rendered.includes(label),label);
  for(const amount of ['₩56','₩375,056','$99,624.56','production-fee-fixture'])assert.ok(rendered.includes(amount),amount);
  nodes(tree,n=>n.type==='button'&&n.props.onClick?.name==='prepare')[0].props.onClick();
  assert.equal(h.state[5].settlement_id,'reviewed-cost-token');assert.equal(h.state[5].fx_usd_cents,37544);
  h.render();h.flushEffects();const confirmedTree=h.render();const confirmation=JSON.stringify(confirmedTree);
  const nearby=nodes(confirmedTree,n=>n.props?.className==='review-settlement')[0];assert.ok(nearby,'Final submit needs the approved cost summary beside it');
  for(const label of ['cost_commission','cost_total_debit','cost_fx_cost','fx_estimated_total_usd'])assert.ok(JSON.stringify(nearby).includes(label),label);
  for(const label of ['cost_commission','cost_remaining_usd','cost_remaining_krw','cost_assumptions'])assert.ok(confirmation.includes(label),`Final confirmation lost ${label}`);
 }finally{h.restore();}
});
