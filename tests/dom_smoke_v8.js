/* DOM smoke test for v8 team/report/chat composition. */
'use strict';

const fs = require('fs');
const path = require('path');
const {JSDOM} = require('jsdom');

const root = path.resolve(__dirname, '..', 'src', 'web');
const html = fs.readFileSync(path.join(root, 'ui.html'), 'utf8');
const dom = new JSDOM(html, {
  url: 'http://127.0.0.1:19234/',
  runScripts: 'outside-only',
  pretendToBeVisual: true
});
const w = dom.window;
w.alert = () => {};
w.confirm = () => true;
w.matchMedia = () => ({
  matches: false, addEventListener() {}, removeEventListener() {}
});
w.URL.createObjectURL = () => 'blob:test';
w.URL.revokeObjectURL = () => {};
w.fetch = async () => ({
  ok: true, json: async () => ({ok: false}), blob: async () => new w.Blob()
});

const core = w.document.querySelector('script:not([src])').textContent;
const v7 = fs.readFileSync(path.join(root, 'v7_ui.js'), 'utf8');
const v8 = fs.readFileSync(path.join(root, 'v8_ui.js'), 'utf8');
w.eval(
  core + '\n' + v7 + '\n' + v8 +
  '\nwindow.initV7UI=initV7UI;window.initV8UI=initV8UI;' +
  'window.V8=V8;window.v8RenderDashboardReport=v8RenderDashboardReport;' +
  'window.v8RenderContribution=v8RenderContribution;' +
  'window.v8RenderCapacity=v8RenderCapacity;' +
  'window.v8RenderShared=v8RenderShared;' +
  'window.v8RenderQuality=v8RenderQuality;'
);
w.initV7UI();
w.initV8UI();

for (const id of [
  'pg22', 'pg23', 'pg24', 'pg25', 'v8-m-team', 'v8-m-workstream',
  'v8-m-target', 'v8-m-statement-teams', 'v8-m-chat-create',
  'v8-m-chat-members',
  'v8-team-switch', 'vtteam', 'vtweight', 'v8-contract-teams',
  'v8-statement-team', 'v8-planned-team', 'v8-chat-manage-members'
]) {
  if (!w.document.getElementById(id)) throw new Error('missing v8 DOM node: ' + id);
}
if (!v8.includes('function v8SaveStatementTeams') ||
    !v8.includes('/statement_teams_save')) {
  throw new Error('approved/legacy statement team allocation editor missing');
}

const menuOrder = Array.from(
  w.document.querySelectorAll('.s-nav .nav-item[data-pg]')
).map(x => Number(x.dataset.pg));
for (const page of [22, 23, 24, 25]) {
  if (!menuOrder.includes(page)) throw new Error('missing v8 menu page ' + page);
}
if (!(menuOrder.indexOf(2) < menuOrder.indexOf(22) &&
      menuOrder.indexOf(18) < menuOrder.indexOf(19) &&
      menuOrder.indexOf(19) < menuOrder.indexOf(25) &&
      menuOrder.indexOf(12) < menuOrder.indexOf(24))) {
  throw new Error('v8 sidebar grouping/order is incorrect');
}

// Report renderers must safely escape labels and expose both financial totals.
w.v8RenderDashboardReport({
  totals: {
    task_count: 3, done_count: 2, work_seconds: 3600,
    sent_amount: 500, approved_amount: 300
  },
  teams: [{
    team_name: '<img src=x onerror=alert(1)>', task_count: 3,
    done_count: 2, returned_count: 0, progress_percent: 66.67,
    task_seconds: 3600, sent_amount: 500, approved_amount: 300
  }]
});
const report = w.document.getElementById('v8-report-box');
if (report.querySelector('img')) throw new Error('team report HTML injection');
if (!report.textContent.includes('صورت‌وضعیت ارسال‌شده') ||
    !report.textContent.includes('تایید کارفرما')) {
  throw new Error('sent/approved team totals missing');
}

w.v8RenderContribution({
  incomplete_task_ids: [9],
  people: [{
    display_name: 'همکار تست', work_seconds: 120,
    time_share_percent: 100, output_weight: 2,
    output_share_percent: 100
  }],
  projects: [{
    project_name: 'پروژه تست', team_name: 'تیم تست',
    task_count: 1, done_count: 1, progress_percent: 100
  }]
});
if (!report.textContent.includes('سهم خروجی آن‌ها حدس زده نشده است')) {
  throw new Error('ambiguous contribution warning missing');
}

w.v8RenderCapacity([{
  display_name: 'همکار چندتیمی', team_count: 2, open_tasks: 4,
  doing_tasks: 2, work_seconds: 600, capacity_warning: true
}]);
if (!report.querySelector('.v8-warn-row')) throw new Error('capacity warning missing');

w.v8RenderShared([{
  city_name: 'تهران', project_name: 'مشترک', project_type_name: 'CMS',
  team_count: 2, task_count: 4, contract_count: 1,
  statement_count: 2, sent_amount: 1000, approved_amount: 900
}]);
if (!report.textContent.includes('مشترک')) throw new Error('shared project report missing');

w.v8RenderQuality([{
  title: 'صورت‌وضعیت بدون تیم', count: 1, severity: 'critical'
}]);
if (!report.querySelector('.v8-critical-row')) throw new Error('quality severity missing');

const chatText = w.document.getElementById('pg24').textContent;
if (!chatText.includes('پیام خصوصی') || !chatText.includes('گروه') ||
    !chatText.includes('جستجو فقط روی همین دستگاه') ||
    !v8.includes("announcement:'📢'")) {
  throw new Error('secure chat modes/local search guidance missing');
}

console.log(
  'dom_v8_smoke_ok pages=4 team_fields=6 reports=5 chat_modes=4 menu=ordered'
);
w.close();
