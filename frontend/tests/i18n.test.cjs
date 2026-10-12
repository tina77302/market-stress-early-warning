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
