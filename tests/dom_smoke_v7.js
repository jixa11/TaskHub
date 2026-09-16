/* DOM smoke test. Run with NODE_PATH pointing at a jsdom installation. */
'use strict';

const fs = require('fs');
const path = require('path');
const {JSDOM} = require('jsdom');

const root = path.resolve(__dirname, '..', 'src', 'web');
const html = fs.readFileSync(path.join(root, 'ui.html'), 'utf8');
const dom = new JSDOM(html, {url: 'http://127.0.0.1:19234/', runScripts: 'outside-only', pretendToBeVisual: true});
const w = dom.window;
w.alert = () => {};
w.confirm = () => true;
w.matchMedia = () => ({matches: false, addEventListener() {}, removeEventListener() {}});
w.URL.createObjectURL = () => 'blob:test';
w.URL.revokeObjectURL = () => {};
w.fetch = async () => ({ok: true, json: async () => ({ok: false}), blob: async () => new w.Blob()});

// The first inline script is the original application. The final inline
// script (boot) is intentionally not run because this test has no live DB.
const core = w.document.querySelector('script:not([src])').textContent;
w.eval(core + '\n' + fs.readFileSync(path.join(root, 'v7_ui.js'), 'utf8') +
  '\nwindow.V7=V7;window.initV7UI=initV7UI;window.v7RenderPlan=v7RenderPlan;window.v7RenderContracts=v7RenderContracts;window.v71CloseMore=v71CloseMore;window.v71RenderFinancialTypes=v71RenderFinancialTypes;');
w.initV7UI();

for (const id of ['pg16', 'pg17', 'pg18', 'pg19', 'pg20', 'pg21', 'v7-m-contract', 'v7-m-extension',
                  'v7-m-statement', 'v7-m-plan', 'v7-m-planned', 'v7-m-files',
                  'v7-finance-dashboard', 'v71-dash-period', 'v71-contract-more',
                  'v71-task-more', 'v71-statement-more', 'vptype', 'user-search']) {
  if (!w.document.getElementById(id)) throw new Error('missing DOM node: ' + id);
}
if (w.document.querySelectorAll('.nav-item[data-pg="16"],.nav-item[data-pg="17"],.nav-item[data-pg="18"],.nav-item[data-pg="19"],.nav-item[data-pg="20"],.nav-item[data-pg="21"]').length !== 6) {
  throw new Error('financial navigation was not installed');
}
if (!w.document.querySelector('#vurole option[value="finance"]')) throw new Error('finance role missing');
if (w.document.querySelector('#v71-dash-period').value !== 'all') throw new Error('dashboard must default to all time');
const menuOrder = Array.from(w.document.querySelectorAll('.s-nav .nav-item')).map(x => Number(x.dataset.pg));
if (!(menuOrder.indexOf(2) < menuOrder.indexOf(16) && menuOrder.indexOf(16) < menuOrder.indexOf(17) &&
      menuOrder.indexOf(17) < menuOrder.indexOf(18) && menuOrder.indexOf(18) < menuOrder.indexOf(19))) {
  throw new Error('financial menu grouping/order is incorrect');
}
for (const id of ['v7c-type', 'v7c-sajat-date-fa', 'v7s-start-fa', 'v7s-end-fa',
                  'v7s-vat-percent', 'v7-decision-confirmed']) {
  if (!w.document.getElementById(id)) throw new Error('missing v7 field: ' + id);
}

w.CU = {id: 1, role: 'manager', display_name: 'مدیر تست'};
w.V7.plan = {id: 1, annual_target: 36000000000, version_no: 1};
w.V7.planData = {
  plan: w.V7.plan,
  periods: Array.from({length: 12}, (_, i) => ({month_no: i + 1, target_amount: 3000000000, allocation_mode: 'amount'})),
  actuals: [], planned: []
};
w.v7RenderPlan();
const quarterLabels = Array.from(w.document.querySelectorAll('#v7-months .v7-kpi .label')).map(x => x.textContent);
if (quarterLabels.length !== 4 || !quarterLabels.every(x => x.startsWith('فصل '))) throw new Error('quarter summaries missing');
if (w.document.querySelectorAll('.v7-month').length !== 12) throw new Error('month cards missing');

// Contract content must render as text, not executable markup.
w.V7.contracts = [{id: 1, title: '<img src=x onerror=alert(1)>', contract_number: 'T',
  employer_name: 'کارفرما', effective_end_date: '2027-01-01', effective_end_date_fa: '1405/10/11',
  effective_price: 100, remaining_price: 100, payer_rating: 4, extension_count: 0,
  statement_count: 0, expiry_level: 'normal', days_to_end: 20, city_name: 'تهران', project_name: 'نمونه'},
  {id: 2, title: 'قرارداد بسته', contract_number: 'C', employer_name: 'قدیمی',
   effective_end_date: '2020-01-01', effective_price: 100, remaining_price: 0, payer_rating: 0,
   extension_count: 0, statement_count: 0, expiry_level: 'closed', days_to_end: -2000,
   city_name: 'تهران', project_name: 'نمونه', contract_status_name: 'بسته'}];
w.v7RenderContracts();
if (w.document.querySelector('#v7-contracts img')) throw new Error('contract HTML injection');
if (!w.document.querySelector('#v7-contracts').textContent.includes('<img')) throw new Error('escaped contract text missing');
if (!w.document.querySelector('#v7-contracts tr.exp-closed')) throw new Error('closed contract styling missing');

// Advanced sections must close every time, even if fields still hold values.
w.document.querySelector('#v7c-financial').value = 'kept-value';
w.document.querySelector('#v71-contract-more').open = true;
w.v71CloseMore();
if (w.document.querySelector('#v71-contract-more').open) throw new Error('advanced section stayed open');
if (w.document.querySelector('#v7c-financial').value !== 'kept-value') throw new Error('advanced field value was lost');

w.V7.finReport = {totals:{planned_amount:100,sent_amount:80,approved_amount:60,remaining_to_plan:40,achievement_percent:60},types:[{project_type_id:1,project_type_name:'CMS',project_count:1,contract_count:1,planned_amount:100,sent_amount:80,approved_amount:60,revenue_share_percent:100,achievement_percent:60}],projects:[],contracts:[],statements:[]};
w.v71RenderFinancialTypes();
if (!w.document.querySelector('#v71-fin-drill').textContent.includes('CMS')) throw new Error('financial type drilldown missing');

console.log('dom_smoke_ok pages=6 months=12 quarters=4 advanced=closed drilldown=ok');
w.close();
