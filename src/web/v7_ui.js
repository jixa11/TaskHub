/* global api,g,escHtml,toFaDigits,D,CU,TOKEN,PML,openM,closeM,toast,sOpts,j2g,showPage,loadAll,applyRole,upStats,rAll,upSelects,prepM,eTask,sTask,vTask */
'use strict';

var V7={contracts:[],taskContracts:[],extensions:[],statements:[],lookups:{},plan:null,planData:null,currentContract:null,currentEntity:null,finReport:null,finDimension:'project_type',workReport:null,dashReport:null,dashFinancial:null,dashFinancialPromise:null,dashAttribution:null,dashAttributionPromise:null,financeMonth:null,financeTeam:null,compareYear:null,compareMonth:null,pendingContractFilter:null};
var V7_MONTHS=['فروردین','اردیبهشت','خرداد','تیر','مرداد','شهریور','مهر','آبان','آذر','دی','بهمن','اسفند'];
var V7_STATUS={
  draft:'پیش‌نویس',pending:'در انتظار تایید مدیر',approved:'تایید مدیر',rejected:'رد مدیر',
  pending_internal:'در انتظار تایید مدیر',internal_approved:'تایید داخلی',internal_rejected:'رد داخلی',
  sent:'ارسال به کارفرما',employer_approved:'تایید کارفرما',employer_rejected:'رد کارفرما',
  revised:'نسخه قبلی',void:'باطل',planned:'برنامه‌ریزی‌شده',preparing:'در حال آماده‌سازی',cancelled:'لغوشده'
};

function v7Money(v){
  if(v===null||v===undefined||v==='')return '—';
  var n=Number(v);return isFinite(n)?toFaDigits(Math.round(n).toLocaleString('en-US')):'—';
}
function v7Num(v){var s=toEnDigits(String(v==null?'':v)).replace(/[^0-9.-]/g,'');return s===''?null:Number(s);}
function v7MoneyInputValue(v){var n=v7Num(v);return n==null?'':Math.round(n).toLocaleString('en-US');}
function v7FormatMoneyInput(el){if(!el)return;var raw=String(el.value||'');if(raw==='-'||raw==='')return;var n=v7Num(raw);if(n==null)return;el.value=v7MoneyInputValue(n);try{el.setSelectionRange(el.value.length,el.value.length);}catch(e){}}
function v7SetMoneyValue(id,value){var el=g(id);if(!el)return;el.value=value==null?'':v7MoneyInputValue(value);}
function v7CanEditExtension(x){return can('extensions.manage')&&(!x||['draft','rejected'].indexOf(x.internal_status)>=0||can('extensions.edit_any_status'));}
// Mirrors the server rule exactly: a statement past the employer decision is
// editable only with statements.edit_any_status, and that edit returns the
// document to draft so the approval cycle runs again.
function v7CanEditStatement(x){
  if(!can('statements.manage'))return false;
  if(!x)return true;
  var st=x.business_status;
  if(['employer_approved','employer_rejected','revised'].indexOf(st)>=0)return can('statements.edit_any_status');
  return ['draft','internal_rejected'].indexOf(st)>=0||can('statements.edit_before_employer_decision')||can('statements.edit_any_status');
}
function v7SortableValue(text){var raw=toEnDigits(String(text||'')).replace(/ /g,' ').trim(),compact=raw.replace(/,/g,'').replace(/[٪%]/g,'').replace(/\s*(ریال|تومان|روز|مورد)\s*/g,'').trim();if(/^[-+]?\d+(\.\d+)?$/.test(compact))return {kind:'number',value:Number(compact)};var dm=raw.match(/(1[34]\d{2}|20\d{2})[\/-](\d{1,2})[\/-](\d{1,2})/);if(dm)return {kind:'number',value:Number(dm[1])*10000+Number(dm[2])*100+Number(dm[3])};return {kind:'text',value:raw};}
function v7InstallTableSorting(){if(document.body.dataset.v7SortingInstalled)return;document.body.dataset.v7SortingInstalled='1';document.addEventListener('click',function(ev){var th=ev.target.closest('table thead th');if(!th||th.dataset.noSort==='1'||th.textContent.trim()==='عملیات'||!th.closest('tbody,table'))return;var table=th.closest('table'),body=table&&table.tBodies&&table.tBodies[0];if(!body||body.rows.length<2)return;var index=Array.prototype.indexOf.call(th.parentNode.children,th),next=th.dataset.sortDir==='asc'?'desc':'asc';Array.from(th.parentNode.children).forEach(function(h){delete h.dataset.sortDir;h.classList.remove('v7-sort-asc','v7-sort-desc');h.removeAttribute('aria-sort');});th.dataset.sortDir=next;th.classList.add(next==='asc'?'v7-sort-asc':'v7-sort-desc');th.setAttribute('aria-sort',next==='asc'?'ascending':'descending');var rows=Array.from(body.rows).map(function(row,pos){return {row:row,pos:pos,key:v7SortableValue(row.cells[index]?row.cells[index].innerText:'')};});rows.sort(function(a,b){var c;if(a.key.kind==='number'&&b.key.kind==='number')c=a.key.value-b.key.value;else c=String(a.key.value).localeCompare(String(b.key.value),'fa',{numeric:true,sensitivity:'base'});if(c===0)c=a.pos-b.pos;return next==='asc'?c:-c;});rows.forEach(function(x){body.appendChild(x.row);});});document.addEventListener('input',function(ev){var el=ev.target.closest&&ev.target.closest('[data-money-input]');if(el)v7FormatMoneyInput(el);});}
function v7FaDate(v){return v?toFaDigits(String(v).slice(0,10)):'—';}
function v7IsoFromJalali(v){
  if(!v)return null;var p=toEnDigits(String(v)).replace(/-/g,'/').split('/').map(Number);if(p.length!==3||!p[0])return null;
  var d=j2g(p[0],p[1],p[2]);return d[0]+'-'+String(d[1]).padStart(2,'0')+'-'+String(d[2]).padStart(2,'0');
}
function v7CanWrite(permission){return CU&&can(permission||'contracts.manage');}
function v7CanApprove(){return CU&&can('contracts.approve');}
function v7CanApproveExtension(){return CU&&can('extensions.approve');}
function v7CanApproveStatement(){return CU&&can('statements.internal_approve');}
function v7CanRecordEmployer(){return CU&&can('statements.employer_status');}
function v7CanPlan(){return CU&&can('financial_plan.manage');}
function v7RatingText(v){var n=Number(v||0),labels=['نامشخص','خیلی بد','ضعیف','متوسط','خوب','عالی'];return '<span class="v7-rating">'+('★'.repeat(n)||'☆')+'</span> '+labels[n];}
function v7StatusChip(s){var cls=(s==='approved'||s==='internal_approved'||s==='employer_approved')?'ok':((s==='rejected'||s==='internal_rejected'||s==='employer_rejected'||s==='void')?'bad':'warn');return '<span class="v7-chip '+cls+'">'+escHtml(V7_STATUS[s]||s||'—')+'</span>';}
function v7Selected(a,b){return String(a==null?'':a)===String(b==null?'':b)?' selected':'';}
function v7RoleLabel(r){return {admin:'مدیر سیستم',manager:'مدیر',planner:'پلنر',finance:'کارشناس مالی',reporter:'کارشناس اجرایی',support:'پشتیبان',lead:'سرگروه',supervisor:'راهبر',employer:'کارفرما'}[r]||r;}

function v7CurrentJalali(){var d=new Date(),j=g2j(d.getFullYear(),d.getMonth()+1,d.getDate());return {year:Number(j[0]),month:Number(j[1]),day:Number(j[2])};}
function v7MonthOptions(selected,includeAll){var html=includeAll?'<option value="0"'+(Number(selected)===0?' selected':'')+'>کل سال</option>':'';return html+V7_MONTHS.map(function(name,i){var m=i+1;return '<option value="'+m+'"'+(Number(selected)===m?' selected':'')+'>'+name+'</option>';}).join('');}
async function v7FinancialMonthChanged(){var sel=g('v7-finance-month');V7.financeMonth=sel?Number(sel.value||0):0;await v7LoadFinancialDashboard();}
// Teams this reader may look at. V8 fills V8.context after login; before that
// the picker simply does not appear.
function v7FinanceTeams(){
  try{return (window.V8&&V8.context&&V8.context.teams)||[];}catch(e){return [];}
}
function v7FinanceCanPickTeam(){return v7FinanceTeams().length>1;}
function v7FinanceTeamPicker(){
  if(!v7FinanceCanPickTeam())return '';
  var teams=v7FinanceTeams(),cur=String(V7.financeTeam||'');
  return '<label>تیم <select class="fi v7-fin-month-select" id="v7-finance-team" onchange="v7FinancialTeamChanged()">'+
    '<option value=""'+(cur?'':' selected')+'>کل شرکت</option>'+
    teams.map(function(t){return '<option value="'+t.id+'"'+(cur===String(t.id)?' selected':'')+'>'+escHtml(t.name)+'</option>';}).join('')+
    '</select></label>';
}
function v7FinanceScopeLabel(){
  if(!V7.financeTeam)return 'کل شرکت';
  var t=v7FinanceTeams().find(function(x){return String(x.id)===String(V7.financeTeam);});
  return t?('تیم '+t.name):'تیم انتخاب‌شده';
}
function v7FinancialTeamChanged(){
  var sel=g('v7-finance-team');if(!sel)return;
  V7.financeTeam=sel.value||null;
  try{localStorage.setItem('taskhub_finance_team',V7.financeTeam||'');}catch(e){}
  v7LoadFinancialDashboard();
}
async function v7LoadFinancialDashboard(){
  // The card is governed by dashboard.financial alone. Requiring
  // reports.financial as well hid it from everyone who may see the company
  // target but not the full financial report pages.
  var box=g('v7-finance-dashboard');if(!box||!CU||!can('dashboard.financial'))return;
  if(V7.financeMonth===null){V7.financeMonth=v7CurrentJalali().month;}
  if(V7.financeTeam===null){try{V7.financeTeam=localStorage.getItem('taskhub_finance_team')||'';}catch(e){V7.financeTeam='';}}
  // A stored team the reader can no longer see must not silently filter the
  // card to nothing.
  if(V7.financeTeam&&!v7FinanceTeams().some(function(t){return String(t.id)===String(V7.financeTeam);}))V7.financeTeam='';
  // The card asks for its own team, independently of the global team switcher,
  // so an admin can compare teams here without changing the rest of the app.
  var payload={jalali_month:Number(V7.financeMonth||0)||null};
  if(V7.financeTeam)payload._team_scope=V7.financeTeam;
  var r=await api('/financial_dashboard',payload);if(!r||!r.ok){box.innerHTML='<div class="v7-empty">خطا در دریافت هدف مالی: '+escHtml((r&&r.error)||'')+'</div>';return;}
  var p=r.plan;if(!p){box.innerHTML='<div class="v7-fin-head"><div><b>🎯 پایش هدف مالی</b><small>هنوز هدف سالانه‌ای تعریف نشده است.</small></div><button class="v7-mini primary" onclick="showPage(19)">تعریف هدف در برنامه مالی</button></div>';return;}
  var selected=Number(r.selected_month||V7.financeMonth||0),target=Number(r.target_amount||0),sent=Number(r.sent_amount||0),approved=Number(r.approved_amount||0);
  V7.financeMonth=selected;
  var sentPct=target?Math.round(sent/target*100):0,approvedPct=target?Math.round(approved/target*100):0;
  var sentWidth=Math.min(100,Math.max(0,sentPct)),approvedWidth=Math.min(100,Math.max(0,approvedPct));
  var remaining=Math.max(0,target-sent),ring=Math.min(100,Math.max(0,approvedPct)),targetLabel=r.target_label||(selected?('هدف '+V7_MONTHS[selected-1]):'هدف سالانه');
  // The detail button leads to a page the reader may not be allowed to open, so
// it is only offered with the permission that page needs.
  var detailBtn=can('financial_plan.view')?'<button class="v7-mini primary" onclick="showPage(25)">جزئیات و نمودارها</button>':'';
  // Anyone who can see more than one team gets a team picker; without it the
  // card could only ever report the company total.
  var teamPicker=v7FinanceTeamPicker();
  var scopeLabel=v7FinanceScopeLabel();
  box.innerHTML='<div class="v7-fin-head"><div><b>🎯 پایش هدف مالی '+toFaDigits(p.jalali_year)+'</b><small>'+escHtml(p.title||'هدف صورت‌وضعیت')+' · '+escHtml(targetLabel)+' · '+escHtml(scopeLabel)+'</small></div><div class="v7-fin-head-actions">'+teamPicker+'<label>ماه <select class="fi v7-fin-month-select" id="v7-finance-month" onchange="v7FinancialMonthChanged()">'+v7MonthOptions(selected,true)+'</select></label>'+detailBtn+'</div></div>'+ 
    '<div class="v7-fin-body"><div class="v7-fin-ring" style="--v7-ring:'+ring+'"><div><strong>'+toFaDigits(approvedPct)+'٪</strong><small>تحقق '+escHtml(targetLabel)+'</small></div></div>'+ 
    '<div class="v7-fin-metrics"><div class="v7-fin-numbers"><span><small>'+escHtml(targetLabel)+'</small><b>'+v7Money(target)+'</b></span><span><small>ارسال‌شده ('+toFaDigits(r.sent_count||0)+' مورد)</small><b>'+v7Money(sent)+'</b></span><span><small>تایید کارفرما ('+toFaDigits(r.approved_count||0)+' مورد)</small><b>'+v7Money(approved)+'</b></span><span><small>مانده تا هدف ارسال</small><b>'+v7Money(remaining)+'</b></span></div>'+ 
    '<div class="v7-fin-bar-row"><span>ارسال‌شده</span><b>'+toFaDigits(sentPct)+'٪</b><div class="v7-fin-track"><i class="sent" style="width:'+sentWidth+'%"></i></div></div>'+ 
    '<div class="v7-fin-bar-row"><span>تایید کارفرما</span><b>'+toFaDigits(approvedPct)+'٪</b><div class="v7-fin-track"><i class="approved" style="width:'+approvedWidth+'%"></i></div></div></div></div>';
}
function initV7UI(){
  v7InstallTableSorting();
  var nav=document.querySelector('.s-nav');
  nav.insertAdjacentHTML('beforeend',
    '<div class="nav-sec" data-role="admin,manager,planner,finance,reporter">مالی و قراردادها</div>'+ 
    '<div class="nav-item" data-pg="16" data-permission="contracts.view" data-role="admin,manager,planner,finance,reporter"><span class="nav-ico">📜</span>قراردادها</div>'+ 
    '<div class="nav-item" data-pg="17" data-permission="extensions.view" data-role="admin,manager,planner,finance,reporter"><span class="nav-ico">➕</span>الحاقیه‌ها</div>'+ 
    '<div class="nav-item" data-pg="18" data-permission="statements.view" data-role="admin,manager,planner,finance,reporter"><span class="nav-ico">🧾</span>صورت‌وضعیت‌ها</div>'+ 
    '<div class="nav-item" data-pg="19" data-permission="financial_plan.view" data-role="admin,manager,planner,finance,reporter"><span class="nav-ico">📅</span>برنامه صورت‌وضعیت</div>'+
    '<div class="nav-item" data-pg="20" data-permission="reports.financial" data-role="admin,manager,planner,finance,reporter"><span class="nav-ico">💹</span>درآمد پروژه‌ها</div>'+ 
    '<div class="nav-item" data-pg="21" data-permission="reports.view" data-role="admin,manager,planner,reporter,support"><span class="nav-ico">⏱</span>سهم کارکرد</div>');
  var navItems={};nav.querySelectorAll('.nav-item[data-pg]').forEach(function(x){navItems[Number(x.dataset.pg)]=x;});
  nav.querySelectorAll('.nav-sec').forEach(function(x){x.remove();});
  if(navItems[0])navItems[0].setAttribute('data-role','admin,employer,support,supervisor,manager,planner,reporter,finance');
  [1,2].forEach(function(i){if(navItems[i])navItems[i].setAttribute('data-role','admin,planner,manager,reporter,finance');});
  function section(title,roles,pages){
    var s=document.createElement('div');s.className='nav-sec';s.textContent=title;if(roles)s.setAttribute('data-role',roles);nav.appendChild(s);
    pages.forEach(function(pg){if(navItems[pg])nav.appendChild(navItems[pg]);});
  }
  section('منوی اصلی','admin,employer,support,supervisor,manager,planner,reporter,finance',[0,9]);
  section('شهر و پروژه','admin,planner,manager,reporter,finance',[1,2]);
  section('قرارداد و امور مالی','admin,manager,planner,finance,reporter',[16,17,18,19]);
  section('تسک و برنامه کاری','admin,employer,manager,planner,reporter',[5,6,13,14]);
  section('گزارش‌ها','admin,support,supervisor,reporter,manager,planner,finance',[7,8,20,21]);
  section('ارتباطات','admin,support,manager,planner,reporter,supervisor,employer',[12]);
  section('سیستم','admin,manager,planner',[10,15]);
  section('راهنما','',[11]);
  var pages=g('pages');pages.insertAdjacentHTML('beforeend',v7PagesHtml());
  g('toast-c').insertAdjacentHTML('beforebegin',v7ModalsHtml());
  var dashQuick=document.querySelector('#pg0 .qa');
  if(dashQuick)dashQuick.insertAdjacentHTML('afterend','<div data-dash-tab="org" class="v71-dashboard-filter" data-permission="dashboard.organization_analytics"><b>بازه گزارش‌های داشبورد</b><select class="fi v71-select-only" id="v71-dash-period" onchange="v71DashboardFilterChanged()"><option value="all" selected>همه زمان‌ها</option><option value="week">هفته اخیر</option><option value="month">این ماه</option><option value="quarter">این فصل</option><option value="year">امسال</option><option value="custom">بازه دلخواه</option></select><div id="v71-dash-custom" class="v71-date-pair" style="display:none"><input class="fi" id="v71-dash-from" placeholder="از تاریخ" readonly onclick="openDP(\'v71-dash-from\')"><input class="fi" id="v71-dash-to" placeholder="تا تاریخ" readonly onclick="openDP(\'v71-dash-to\')"><button class="btn btn-primary" onclick="v71ApplyDashboardFilter()">اعمال</button></div><small id="v71-dash-filter-label">نمایش همه زمان‌ها</small></div><div data-dash-tab="finance" id="v7-finance-dashboard" class="v7-fin-dash" data-permission="dashboard.financial"><div class="v7-empty">در حال دریافت وضعیت هدف مالی...</div></div>');
  var dashCharts=g('dash-charts');if(dashCharts)dashCharts.insertAdjacentHTML('beforeend',
    '<div class="dl-card chart-card" data-permission="dashboard.chart_status"><div class="dl-card-t">🧩 تسک‌ها به تفکیک نوع پروژه</div><div id="chart-project-type" class="chart-body"></div></div>'+ 
    '<div class="dl-card chart-card" data-permission="dashboard.chart_city"><div class="dl-card-t v802-dash-card-head"><span>🏙 درآمد تاییدشده بر اساس شهر</span><button class="v7-mini" onclick="v802OpenIncomeDimension(\'city\')">گزارش کامل</button></div><div id="chart-income-city" class="chart-body"><div class="chart-empty">در حال محاسبه...</div></div></div>'+ 
    '<div class="dl-card chart-card" data-permission="dashboard.chart_trend"><div class="dl-card-t v802-dash-card-head"><span>📜 درآمد بر اساس نوع قرارداد</span><button class="v7-mini" onclick="v802OpenIncomeDimension(\'contract_type\')">گزارش کامل</button></div><div id="chart-income-contract-type" class="chart-body"><div class="chart-empty">در حال محاسبه...</div></div></div>'+ 
    '<div class="dl-card chart-card" data-permission="dashboard.chart_staff"><div class="dl-card-t v802-dash-card-head"><span>💰 سهم مالی تحلیلی تیم و فرد</span><button class="v7-mini" onclick="v802OpenFinancialAttribution()">گزارش کامل / PDF</button></div><div id="chart-financial-attribution" class="chart-body"><div class="chart-empty">در حال محاسبه...</div></div></div>');
  var settings=g('pg15');if(settings)settings.insertAdjacentHTML('beforeend','<div class="hlp-card" data-role="admin,manager" style="max-width:820px;margin-top:16px"><h3>🛡 پشتیبان‌گیری و بازیابی نسخه ۷</h3><p class="v7-muted" style="line-height:1.9">هر نقطه بازیابی شامل دیتابیس، فایل‌ها، مانیفست و هش صحت است. زنجیره FULL/DIFFERENTIAL یکجا نگهداری می‌شود و Connection String داخل آن قرار نمی‌گیرد. بازیابی کامل عمداً فقط با توقف سرور و ابزار <code>restore_backup.py</code> انجام می‌شود؛ ابزار قبل از بازیابی یک نقطه نجات جدید می‌سازد.</p><div class="v7-toolbar"><button class="btn btn-add" onclick="v7RunBackup(false)">پشتیبان دوره‌ای</button><button class="btn btn-primary" onclick="v7RunBackup(true)">FULL جدید</button><button class="btn btn-ghost" onclick="v7LoadBackups()">↺ فهرست</button></div><div id="v7-storage-stats"></div><div id="v7-backup-list"></div></div>');
  var formAnchor=g('vtdesc')&&g('vtdesc').closest('.fg');
  if(formAnchor)formAnchor.insertAdjacentHTML('beforebegin','<details class="v71-more" id="v71-task-more"><summary>موارد بیشتر</summary><div class="v71-more-body"><div class="fr" id="v7-task-links"><div class="fg"><label class="fl">قرارداد مرتبط (برای گزارش سهم مالی)</label><select class="fi" id="vtcontract" onchange="v7TaskContractChanged()"></select><small class="v7-muted">برای محاسبه سهم مالی تیم و فرد، قرارداد صحیح را روی تسک انتخاب کنید. قرارداد باید متعلق به همین پروژه باشد.</small></div><div class="fg"><label class="fl">برنامه صورت‌وضعیت (اختیاری)</label><select class="fi" id="vtplanned"></select></div></div><div class="fg"><label class="fl">تصاویر راهنما (اختیاری، چند فایل)</label><input class="fi" id="vttaskimages" type="file" accept="image/jpeg,image/png,image/webp" multiple><small class="v7-muted">تصاویر خودکار کوچک و WebP می‌شوند؛ فایل تکراری دوباره فضا نمی‌گیرد.</small></div></div></details>');
  var roleSel=g('vurole');if(roleSel&&!roleSel.querySelector('option[value="finance"]'))roleSel.insertAdjacentHTML('beforeend','<option value="finance">💰 کارشناس مالی</option>');
  var ver=document.querySelector('.s-footer .ver');if(ver)ver.textContent='v 1.0.0';
  PML[16]=['قراردادها','مدیریت و پایش قراردادها'];PML[17]=['الحاقیه‌ها','سوابق زمانی و ریالی'];PML[18]=['صورت‌وضعیت‌ها','چرخه تایید و وصول'];PML[19]=['برنامه مالی صورت‌وضعیت','هدف، برنامه و عملکرد'];PML[20]=['گزارش درآمد','تحلیل درآمد بر اساس نوع پروژه، شهر و نوع قرارداد'];PML[21]=['سهم کارکرد','سهم واقعی افراد از کار پروژه‌ها'];
  document.querySelectorAll('.nav-item[data-pg="16"],.nav-item[data-pg="17"],.nav-item[data-pg="18"],.nav-item[data-pg="19"],.nav-item[data-pg="20"],.nav-item[data-pg="21"]').forEach(function(el){el.addEventListener('click',function(){var i=Number(el.dataset.pg);showPage(i);g('tbh').textContent=PML[i][0];g('tbs').textContent=PML[i][1];});});
  v7InstallOverrides();
}

function v7PagesHtml(){return `
<div class="page" id="pg16">
  <div class="ph"><h2><span>📜</span>قراردادها</h2><div class="bg"><button class="btn btn-ghost" data-permission="reports.export" onclick="v7Export('contracts','pdf')">PDF</button><button class="btn btn-green" data-permission="reports.export" onclick="v7Export('contracts','xlsx')">Excel</button><button class="btn btn-add" id="v7-add-contract" onclick="v7OpenContract()">➕ قرارداد</button></div></div>
  <div class="v7-toolbar"><input class="fi" id="v7-contract-search" placeholder="جستجوی عنوان، شماره، پروژه..." oninput="v7RenderContracts()"><label class="v7-chip"><input type="checkbox" id="v7-only-unassigned" onchange="v7LoadContracts()"> فقط قراردادهای بدون پروژه</label><button class="btn btn-ghost" id="v7-contract-archive-toggle" data-permission="archives.view" onclick="v7ToggleArchive('contract')">🗄 بایگانی‌ها</button><button class="btn btn-ghost" onclick="v7LoadContracts()">↺ به‌روزرسانی</button></div>
  <div class="v7-archive-banner" id="v7-contract-archive-banner" style="display:none">🗄 در حال نمایش قراردادهای بایگانی‌شده. این رکوردها در گزارش‌ها و مبالغ محاسبه نمی‌شوند.</div>
  <div id="v7-contracts"></div>
</div>
<div class="page" id="pg17">
  <div class="ph"><h2><span>➕</span>الحاقیه‌ها</h2><div class="bg"><button class="btn btn-ghost" data-permission="reports.export" onclick="v7Export('extensions','pdf')">PDF</button><button class="btn btn-green" data-permission="reports.export" onclick="v7Export('extensions','xlsx')">Excel</button><button class="btn btn-add" id="v7-add-extension" onclick="v7OpenExtension()">➕ الحاقیه</button></div></div>
  <div class="v7-toolbar"><select class="fi" id="v7-extension-contract" onchange="v7LoadExtensions(this.value)"><option value="">همه قراردادها</option></select><input class="fi" id="v7-extension-search" placeholder="جستجو..." oninput="v7RenderExtensions()"><button class="btn btn-ghost" id="v7-extension-archive-toggle" data-permission="archives.view" onclick="v7ToggleArchive('extension')">🗄 بایگانی‌ها</button><button class="btn btn-ghost" onclick="v7LoadExtensions(g('v7-extension-contract').value)">↺</button></div>
  <div class="v7-archive-banner" id="v7-extension-archive-banner" style="display:none">🗄 در حال نمایش الحاقیه‌های بایگانی‌شده. این رکوردها در مبلغ مؤثر قرارداد اثری ندارند.</div>
  <div id="v7-extensions"></div>
</div>
<div class="page" id="pg18">
  <div class="ph"><h2><span>🧾</span>صورت‌وضعیت‌ها</h2><div class="bg"><button class="btn btn-ghost" data-permission="reports.export" onclick="v7Export('statements','pdf')">PDF</button><button class="btn btn-green" data-permission="reports.export" onclick="v7Export('statements','xlsx')">Excel</button><button class="btn btn-add" id="v7-add-statement" onclick="v7OpenStatement()">➕ صورت‌وضعیت</button></div></div>
  <div class="v7-toolbar"><select class="fi" id="v7-statement-contract" onchange="v7LoadStatements(this.value)"><option value="">همه قراردادها</option></select><input class="fi" id="v7-statement-search" placeholder="جستجو..." oninput="v7RenderStatements()"><button class="btn btn-ghost" id="v7-statement-archive-toggle" data-permission="archives.view" onclick="v7ToggleArchive('statement')">🗄 بایگانی‌ها</button><button class="btn btn-ghost" onclick="v7LoadStatements(g('v7-statement-contract').value)">↺</button></div>
  <div class="v7-archive-banner" id="v7-statement-archive-banner" style="display:none">🗄 در حال نمایش صورت‌وضعیت‌های بایگانی‌شده. این رکوردها در هیچ گزارش مالی محاسبه نمی‌شوند.</div>
  <div id="v7-statements"></div>
</div>
<div class="page" id="pg19">
  <div class="ph"><h2><span>📅</span>برنامه صورت‌وضعیت</h2><div class="bg"><button class="btn btn-ghost" data-permission="reports.export" onclick="v7Export('plans','pdf')">PDF</button><button class="btn btn-green" data-permission="reports.export" onclick="v7Export('plans','xlsx')">Excel</button><button class="btn btn-ghost" id="v7-plan-create" onclick="showPage(25)">🎯 اهداف مالی</button></div></div>
  <div class="v7-toolbar"><input class="fi" id="v7-plan-year" type="number" value="1405" min="1390" max="1500"><button class="btn btn-primary" onclick="v7LoadPlan()">نمایش سال</button><button class="btn btn-add" id="v7-add-planned" onclick="v7OpenPlanned()">➕ برنامه صورت‌وضعیت</button></div>
  <div id="v7-plan-summary"></div><div id="v7-plan-charts"></div><div id="v7-months"></div><div id="v7-planned-list" style="margin-top:16px"></div>
  <section class="v7-group" style="margin-top:16px"><div class="v7-group-head"><span>💹 ترکیب مالی پروژه‌ها در همین برنامه</span><select class="fi v71-select-only" id="v71-plan-breakdown-month" onchange="v71LoadPlanBreakdown()" style="max-width:180px"><option value="">کل سال</option></select></div><div id="v71-plan-breakdown"><div class="v7-empty">در حال محاسبه...</div></div></section><div id="v7-recommendations"></div>
</div>
<div class="page" id="pg20">
  <div class="ph"><h2><span>💹</span>گزارش درآمد</h2><div class="bg"><button class="btn btn-ghost" data-permission="reports.export" onclick="v71ExportReport('project_revenue','pdf')">PDF</button><button class="btn btn-green" data-permission="reports.export" onclick="v71ExportReport('project_revenue','xlsx')">Excel</button></div></div>
  <div class="rb v71-report-filters"><h3>فیلتر گزارش</h3><div class="rg"><div class="fg"><label class="fl">سال مالی شمسی</label><input class="fi" id="v71-fin-year" type="number" placeholder="همه سال‌ها"></div><div class="fg"><label class="fl">ماه</label><select class="fi v71-select-only" id="v71-fin-month"><option value="">همه ماه‌ها</option></select></div><div class="fg"><label class="fl">شهر</label><select class="fi" id="v71-fin-city"><option value="">همه شهرها</option></select></div><div class="fg"><label class="fl">نوع قرارداد</label><select class="fi v71-select-only" id="v71-fin-contract-type"><option value="">همه انواع</option></select></div><div class="fg"><label class="fl">نوع پروژه</label><select class="fi v71-select-only" id="v71-fin-type" onchange="v71ReportTypeChanged('fin')"><option value="">همه نوع‌ها</option></select></div><div class="fg"><label class="fl">پروژه</label><select class="fi" id="v71-fin-project"><option value="">همه پروژه‌ها</option></select></div><div class="fg"><label class="fl">از تاریخ ارسال/تایید</label><input class="fi" id="v71-fin-from" readonly onclick="openDP('v71-fin-from')" placeholder="اختیاری"></div><div class="fg"><label class="fl">تا تاریخ ارسال/تایید</label><input class="fi" id="v71-fin-to" readonly onclick="openDP('v71-fin-to')" placeholder="اختیاری"></div></div><div class="ract"><button class="btn btn-primary" onclick="v71LoadFinancialReport()">نمایش گزارش</button><button class="btn btn-ghost" onclick="v71ResetFinancialReport()">همه زمان‌ها</button></div></div>
  <div class="v8-report-tabs v71-fin-dim"><button class="btn btn-ghost active" data-fin-dim="project_type" onclick="v71ChooseFinancialDimension('project_type',this)">نوع پروژه</button><button class="btn btn-ghost" data-fin-dim="city" onclick="v71ChooseFinancialDimension('city',this)">شهر</button><button class="btn btn-ghost" data-fin-dim="contract_type" onclick="v71ChooseFinancialDimension('contract_type',this)">نوع قرارداد</button></div>
  <div id="v71-fin-summary"></div><div id="v71-fin-drill"></div>
</div>
<div class="page" id="pg21">
  <div class="ph"><h2><span>⏱</span>گزارش سهم کارکرد</h2><div class="bg"><button class="btn btn-ghost" data-permission="reports.export" onclick="v71ExportReport('work_share','pdf')">PDF</button><button class="btn btn-green" data-permission="reports.export" onclick="v71ExportReport('work_share','xlsx')">Excel</button></div></div>
  <div class="rb v71-report-filters"><h3>فیلتر گزارش</h3><div class="rg"><div class="fg"><label class="fl">نوع پروژه</label><select class="fi v71-select-only" id="v71-work-type" onchange="v71ReportTypeChanged('work')"><option value="">همه نوع‌ها</option></select></div><div class="fg"><label class="fl">پروژه</label><select class="fi" id="v71-work-project"><option value="">همه پروژه‌ها</option></select></div><div class="fg"><label class="fl">همکار</label><select class="fi" id="v71-work-user"><option value="">همه همکاران</option></select></div><div class="fg"><label class="fl">از تاریخ</label><input class="fi" id="v71-work-from" readonly onclick="openDP('v71-work-from')" placeholder="همه زمان‌ها"></div><div class="fg"><label class="fl">تا تاریخ</label><input class="fi" id="v71-work-to" readonly onclick="openDP('v71-work-to')" placeholder="همه زمان‌ها"></div></div><div class="ract"><button class="btn btn-primary" onclick="v71LoadWorkReport()">نمایش گزارش</button><button class="btn btn-ghost" onclick="v71ResetWorkReport()">همه زمان‌ها</button></div></div>
  <div id="v71-work-summary"></div><div id="v71-work-drill"></div>
</div>`;}

function v7ModalsHtml(){return `
<div class="mo" id="v7-m-contract"><div class="md wide"><div class="mh"><span class="mi">📜</span><h3 id="v7-contract-title">قرارداد</h3><button class="mx" data-cl="v7-m-contract" onclick="closeM('v7-m-contract')">✕</button></div><div class="mb"><div class="v7-modal-grid">
  <div class="fg span2"><label class="fl">عنوان قرارداد *</label><input class="fi" id="v7c-title"></div>
  <div class="fg"><label class="fl">پروژه (می‌تواند فعلاً خالی باشد)</label><select class="fi" id="v7c-project"></select></div><div class="fg"><label class="fl">کارفرما / مشتری</label><input class="fi" id="v7c-employer"></div>
  <div class="fg"><label class="fl">شماره قرارداد</label><input class="fi" id="v7c-number"></div><div class="fg"><label class="fl">مبلغ پایه قرارداد</label><input class="fi" id="v7c-price" data-money-input inputmode="numeric" dir="ltr"></div>
  <div class="fg"><label class="fl">نوع قرارداد</label><select class="fi" id="v7c-type"></select></div><div class="fg"><label class="fl">دسته قرارداد</label><select class="fi" id="v7c-category"></select></div>
  <div class="fg"><label class="fl">وضعیت</label><select class="fi" id="v7c-status"></select></div><label class="v7-chip"><input type="checkbox" id="v7c-new"> قرارداد جدید / در دست اقدام</label>
  <div class="fg"><label class="fl">تاریخ ابلاغ</label><input class="fi" id="v7c-notify-fa" readonly onclick="openDP('v7c-notify-fa')"></div><div class="fg"><label class="fl">شماره نامه ابلاغ</label><input class="fi" id="v7c-letter"></div>
  <div class="fg"><label class="fl">تاریخ شروع</label><input class="fi" id="v7c-start-fa" readonly onclick="openDP('v7c-start-fa')"></div><div class="fg"><label class="fl">تاریخ پایان</label><input class="fi" id="v7c-end-fa" readonly onclick="openDP('v7c-end-fa')"></div>
  <details class="v71-more span2" id="v71-contract-more"><summary>موارد بیشتر</summary><div class="v71-more-grid">
  <div class="fg"><label class="fl">کد دستور کار</label><input class="fi" id="v7c-workorder"></div><div class="fg"><label class="fl">کد مالی</label><input class="fi" id="v7c-financial"></div>
  <div class="fg"><label class="fl">کد تجاری</label><input class="fi" id="v7c-commercial"></div><div class="fg"><label class="fl">شناسه مالیاتی CRN</label><input class="fi" id="v7c-crn"></div>
  <div class="fg"><label class="fl">ضریب بیمه</label><input class="fi" id="v7c-insurance" dir="ltr"></div><div class="fg"><label class="fl">ضریب ضمانت (عدد خام)</label><input class="fi" id="v7c-guarantee" dir="ltr"></div>
  <label class="v7-chip"><input type="checkbox" id="v7c-sajat"> ثبت در ساجات</label><div class="fg"><label class="fl">تاریخ ثبت در ساجات</label><input class="fi" id="v7c-sajat-date-fa" readonly onclick="openDP('v7c-sajat-date-fa')"></div>
  </div></details>
</div></div><div class="mf"><button class="btn btn-ghost" onclick="closeM('v7-m-contract')">انصراف</button><button class="btn btn-add" onclick="v7SaveContract()">ذخیره</button></div></div></div>

<div class="mo" id="v7-m-rating"><div class="md"><div class="mh"><span class="mi">⭐</span><h3>خوش‌حسابی مشتری</h3><button class="mx" onclick="closeM('v7-m-rating')">✕</button></div><div class="mb"><div class="fg"><label class="fl">امتیاز</label><select class="fi" id="v7r-score"><option value="0">نامشخص</option><option value="1">خیلی بد</option><option value="2">ضعیف</option><option value="3">متوسط</option><option value="4">خوب</option><option value="5">عالی</option></select></div><div class="fg"><label class="fl">یادداشت</label><textarea class="fi" id="v7r-note"></textarea></div><label class="v7-chip" id="v7r-lock-wrap"><input type="checkbox" id="v7r-lock"> نهایی و قفل توسط مدیر</label></div><div class="mf"><button class="btn btn-add" onclick="v7SaveRating()">ذخیره</button></div></div></div>

<div class="mo" id="v7-m-extension"><div class="md wide"><div class="mh"><span class="mi">➕</span><h3 id="v7-extension-title">الحاقیه</h3><button class="mx" onclick="closeM('v7-m-extension')">✕</button></div><div class="mb"><div class="v7-modal-grid">
  <div class="fg span2"><label class="fl">قرارداد *</label><select class="fi" id="v7e-contract"></select></div><div class="fg span2"><label class="fl">عنوان *</label><input class="fi" id="v7e-title"></div>
  <div class="fg"><label class="fl">نوع *</label><select class="fi" id="v7e-type"></select></div><div class="fg"><label class="fl">پایان تمدید</label><input class="fi" id="v7e-end-fa" readonly onclick="openDP('v7e-end-fa')"></div>
  <div class="fg"><label class="fl">روش ثبت مبلغ</label><select class="fi" id="v7e-price-mode" onchange="v7ExtensionPriceMode()"><option value="delta">مبلغ افزایش/کاهش</option><option value="final_snapshot">مبلغ نهایی پس از الحاقیه</option><option value="none">بدون اثر ریالی</option></select></div><div class="fg"><label class="fl" id="v7e-price-label">مبلغ تغییر</label><input class="fi" id="v7e-price" data-money-input dir="ltr"></div>
  <details class="v71-more span2" id="v71-extension-more"><summary>موارد بیشتر</summary><div class="v71-more-grid"><div class="fg"><label class="fl">شماره الحاقیه</label><input class="fi" id="v7e-number"></div><div class="fg"><label class="fl">شماره نامه</label><input class="fi" id="v7e-letter"></div><div class="fg"><label class="fl">تاریخ الحاقیه</label><input class="fi" id="v7e-date-fa" readonly onclick="openDP('v7e-date-fa')"></div><div class="fg"><label class="fl">شروع تمدید</label><input class="fi" id="v7e-start-fa" readonly onclick="openDP('v7e-start-fa')"></div></div></details>
</div></div><div class="mf"><button class="btn btn-ghost" onclick="closeM('v7-m-extension')">انصراف</button><button class="btn btn-add" onclick="v7SaveExtension()">ذخیره پیش‌نویس</button></div></div></div>

<div class="mo" id="v7-m-statement"><div class="md wide"><div class="mh"><span class="mi">🧾</span><h3 id="v7-statement-title">صورت‌وضعیت</h3><button class="mx" onclick="closeM('v7-m-statement')">✕</button></div><div class="mb"><div class="v7-modal-grid">
  <div class="fg span2"><label class="fl">قرارداد *</label><select class="fi" id="v7s-contract"></select></div><div class="fg"><label class="fl">نوع *</label><select class="fi" id="v7s-type"></select></div><div class="fg"><label class="fl">شماره *</label><input class="fi" id="v7s-number"></div>
  <div class="fg span2"><label class="fl">عنوان *</label><input class="fi" id="v7s-title"></div><div class="fg"><label class="fl">تاریخ</label><input class="fi" id="v7s-date-fa" readonly onclick="openDP('v7s-date-fa')"></div>
  <div class="fg"><label class="fl">سال مالی شمسی</label><input class="fi" id="v7s-year" type="number" value="1405"></div><div class="fg"><label class="fl">ماه</label><select class="fi" id="v7s-month"></select></div>
  <div class="fg"><label class="fl">مبلغ ارسالی بدون ارزش افزوده</label><input class="fi" id="v7s-requested" data-money-input dir="ltr"></div>
  <details class="v71-more span2" id="v71-statement-more"><summary>موارد بیشتر</summary><div class="v71-more-grid"><div class="fg"><label class="fl">شماره نامه</label><input class="fi" id="v7s-letter"></div><div class="fg"><label class="fl">شروع دوره کارکرد</label><input class="fi" id="v7s-start-fa" readonly onclick="openDP('v7s-start-fa')"></div><div class="fg"><label class="fl">پایان دوره کارکرد</label><input class="fi" id="v7s-end-fa" readonly onclick="openDP('v7s-end-fa')"></div><div class="fg"><label class="fl">ارزش افزوده</label><input class="fi" id="v7s-vat" data-money-input dir="ltr"></div>
  <div class="fg"><label class="fl">درصد ارزش افزوده</label><input class="fi" id="v7s-vat-percent" type="number" min="0" max="100" step="0.01"></div><div class="fg"><label class="fl">شماره فاکتور ارزش افزوده</label><input class="fi" id="v7s-vat-factor"></div>
  <div class="fg"><label class="fl">درصد پیشرفت</label><input class="fi" id="v7s-progress" type="number" min="0" max="100"></div><label class="v7-chip"><input type="checkbox" id="v7s-without-vat"> بدون ارزش افزوده</label>
  <div class="fg span2"><label class="fl">توضیحات</label><textarea class="fi" id="v7s-desc"></textarea></div>
  </div></details>
</div></div><div class="mf"><button class="btn btn-ghost" onclick="closeM('v7-m-statement')">انصراف</button><button class="btn btn-add" onclick="v7SaveStatement()">ذخیره پیش‌نویس</button></div></div></div>


<div class="mo" id="v7-m-planned"><div class="md wide"><div class="mh"><span class="mi">📅</span><h3>برنامه صورت‌وضعیت</h3><button class="mx" onclick="closeM('v7-m-planned')">✕</button></div><div class="mb"><div class="v7-modal-grid"><div class="fg span2"><label class="fl">قرارداد</label><select class="fi" id="v7ps-contract" onchange="v7RenderPlannedTasks([])"></select></div><div class="fg"><label class="fl">ماه</label><select class="fi" id="v7ps-month"></select></div><div class="fg"><label class="fl">نوع</label><select class="fi" id="v7ps-type"></select></div><div class="fg span2"><label class="fl">عنوان</label><input class="fi" id="v7ps-title"></div><div class="fg"><label class="fl">مبلغ برنامه</label><input class="fi" id="v7ps-amount" data-money-input dir="ltr"></div><div class="fg"><label class="fl">تاریخ برنامه</label><input class="fi" id="v7ps-date-fa" readonly onclick="openDP('v7ps-date-fa')"></div><div class="fg span2"><label class="fl">یادداشت</label><textarea class="fi" id="v7ps-note"></textarea></div><div class="fg span2"><label class="fl">تسک‌های مرتبط (اختیاری)</label><div id="v7ps-tasks" style="max-height:180px;overflow:auto;border:1px solid var(--border);border-radius:8px;padding:8px"></div></div></div></div><div class="mf"><button class="btn btn-add" onclick="v7SavePlanned()">ذخیره</button></div></div></div>

<div class="mo" id="v7-m-files"><div class="md wide"><div class="mh"><span class="mi">📎</span><h3 id="v7-files-title">فایل‌ها</h3><button class="mx" onclick="closeM('v7-m-files')">✕</button></div><div class="mb"><div id="v7-file-upload"><div class="fr"><input class="fi" id="v7-file-input" type="file"><input class="fi" id="v7-file-caption" placeholder="توضیح فایل"></div><button class="btn btn-add" style="margin-top:8px" onclick="v7UploadFile()">بارگذاری</button></div><div id="v7-files-list" style="margin-top:12px"></div></div></div></div>

<div class="mo" id="v7-m-decision"><div class="md v7-decision-compact"><div class="mh"><span class="mi">✅</span><h3 id="v7-decision-title">ثبت تصمیم</h3><button class="mx" onclick="closeM('v7-m-decision')">✕</button></div><div class="mb"><div id="v7-employer-summary" class="v7-employer-summary" style="display:none"></div><div class="fg"><label class="fl">توضیحات (اختیاری)</label><textarea class="fi" id="v7-decision-note" rows="3"></textarea></div></div><div class="mf" id="v7-decision-actions"></div></div></div>`;}

function v7InstallOverrides(){
  var baseShowPage=showPage;
  showPage=function(n){
    baseShowPage(n);
    if(n===16)v7LoadContracts();
    if(n===17){var pe=V7.pendingContractFilter&&V7.pendingContractFilter.kind==='extensions'?V7.pendingContractFilter.id:null;V7.pendingContractFilter=null;V7.currentContract=pe;v7LoadExtensions(pe);}
    if(n===18){var ps=V7.pendingContractFilter&&V7.pendingContractFilter.kind==='statements'?V7.pendingContractFilter.id:null;V7.pendingContractFilter=null;V7.currentContract=ps;v7LoadStatements(ps);}
    if(n===19)v7LoadPlan();
    if(n===20)v71LoadFinancialReport();
    if(n===21)v71LoadWorkReport();
  };

  loadAll=async function(opts){
    var silent=opts&&opts.silent;
    if(!CU)return true;
    var r=await api('/core_data',{});
    if(!r||!r.ok){if(!silent)toast('خطا در دریافت اطلاعات: '+((r&&r.error)||''),'err');return false;}
    D.c=r.cities||[];D.p=r.projects||[];D.pt=r.project_types||[];D.cat=r.categories||[];D.t=r.tasks||[];
    var hb={};(r.helpers||[]).forEach(function(h){(hb[h.task_id]=hb[h.task_id]||[]).push({id:h.user_id,name:h.display_name||h.username});});
    var cb={};(r.contributions||[]).forEach(function(x){(cb[x.task_id]=cb[x.task_id]||[]).push({user_id:x.user_id,seconds:x.total_seconds||0});});
    D.t.forEach(function(t){t.helpers=hb[t.id]||[];t.contributions=cb[t.id]||[];});
    try{var ur=await api('/users',{});if(ur&&ur.ok)D.u=ur.rows||[];}catch(e){}
    if(can('schedule.view')){
      try{var sr=await api('/schedule',{staff_id:CU.id});if(sr&&sr.ok)D.sched=sr.rows||[];}catch(e){D.sched=[];}
    }
    if(can('tasks.link_contract'))await v7LoadTaskContractOptions(true);
    // The contract lookups need contracts.view. Fetching them for anyone who
// merely sees the dashboard goal card produced a 403 on every poll, which the
// loader turned into a toast every few seconds.
  if(can('contracts.view')||can('financial_plan.view'))await v7LoadLookups();
  if(can('contracts.view'))await v7LoadContracts(true);
  if(can('dashboard.financial')){await v7LoadFinancialDashboard();await v802LoadDashboardFinancialCards(true);}
    upStats();rAll();upSelects();v71PopulateReportFilters();return true;
  };

  var baseApplyRole=applyRole;
  applyRole=function(){
    baseApplyRole();
    var role=CU&&CU.role;
    var top=g('topbar-user');if(top&&CU)top.innerHTML='<span class="ua">'+escHtml((CU.display_name||CU.username||'?').charAt(0))+'</span><span><b>'+escHtml(CU.display_name||CU.username)+'</b><small>'+v7RoleLabel(role)+'</small></span>';
    var addC=g('v7-add-contract'),addE=g('v7-add-extension'),addS=g('v7-add-statement');
    if(addC)addC.style.display=can('contracts.manage')?'':'none';if(addE)addE.style.display=can('extensions.manage')?'':'none';if(addS)addS.style.display=can('statements.manage')?'':'none';
    // This button only navigates to «اهداف مالی», so seeing the goals is
    // enough; managing them is not required. Creating a planned statement
    // still needs the management permission.
    if(g('v7-plan-create'))g('v7-plan-create').style.display=can('financial_plan.view')?'':'none';
    if(g('v7-add-planned'))g('v7-add-planned').style.display=v7CanPlan()?'':'none';
  };

  var baseUpSelects=upSelects;
  upSelects=function(){
    baseUpSelects();
    if(CU&&can('users.view_all')){
      sOpts('rstf','همه',D.u.filter(function(u){return u.role==='support'||u.role==='lead'||u.role==='manager';}),'id',function(u){return u.display_name||u.username;});
    }
    v7FillTaskLinks();
  };

  window.activeTaskCount=function(){
    if(CU&&can('tasks.work')&&!can('tasks.view_all')&&!can('tasks.assign'))return D.t.filter(function(t){return ['assigned','doing','paused'].indexOf(t.status)>=0;}).length;
    if(CU&&can('tasks.triage')&&!can('tasks.view_all')&&!can('tasks.assign'))return D.t.filter(function(t){return t.status==='registered';}).length;
    return D.t.filter(function(t){return t.status!=='done';}).length;
  };

  window.sCity=async function(){var n=g('vcn').value.trim();if(!n)return toast('نام شهر الزامی است','err');var r=await api('/master_save',{kind:'city',id:D.eid,name:n});if(!r.ok)return toast(r.error,'err');closeM('mc');await loadAll();toast(r.existing?(r.message||'این شهر از قبل وجود داشت و همان رکورد استفاده شد'):'ذخیره شد','ok');};
  window.sProj=async function(){var n=g('vpn').value.trim(),cid=Number(g('vpc').value),ptid=Number(g('vptype').value),teamId=Number(g('vpteam').value);if(!n||!cid||!ptid||(!D.eid&&!teamId))return toast('نام، شهر، نوع پروژه و تیم مسئول الزامی است','err');var r=await api('/master_save',{kind:'project',id:D.eid,name:n,city_id:cid,project_type_id:ptid,team_id:teamId||null});if(!r.ok)return toast(r.error,'err');if(D.eid&&can('project_notes.manage')&&g('vpnotes-wrap').style.display!=='none'&&g('vpnotes').style.display!=='none')await api('/project_notes_save',{project_id:D.eid,notes:g('vpnotes').value});closeM('mp');await loadAll();toast('ذخیره شد','ok');};
  window.sCat=async function(){var n=g('vcatn').value.trim();if(!n)return toast('نام الزامی است','err');var r=await api('/master_save',{kind:'category',id:D.eid,name:n,description:g('vcatd').value.trim()});if(!r.ok)return toast(r.error,'err');closeM('mcat');await loadAll();toast('ذخیره شد','ok');};
  window.dCity=function(id,n){v7DeleteMaster('city',id,n);};window.dProj=function(id,n){v7DeleteMaster('project',id,n);};window.dCat=function(id,n){v7DeleteMaster('category',id,n);};
  window.dTask=async function(id,n){var t=D.t.find(function(x){return x.id===id;});if(t&&!canDeleteTask(t))return toast('اجازه حذف ندارید','err');if(!confirm('حذف تسک «'+n+'»؟'))return;var r=await api('/task_delete',{id:id});if(!r.ok)return toast(r.error,'err');await loadAll();toast('تسک حذف شد','ok');};

  window.rP=function(){var tb=g('tbp');if(!tb)return;var only=g('project-only-untyped')&&g('project-only-untyped').checked,rows=(D.p||[]).filter(function(p){return !only||!Number(p.project_type_id);});if(!rows.length){tb.innerHTML='<tr><td colspan="6"><div class="emp"><div class="ei">🏢</div><p>پروژه‌ای برای نمایش وجود ندارد</p></div></td></tr>';return;}var canEdit=can('projects.edit'),canDelete=can('projects.delete');tb.innerHTML=rows.map(function(p){var nc=(D.u||[]).filter(function(u){return u.role==='employer'&&u.project_id===p.id;}).length,type=p.project_type_name||'نوع تعیین نشده',warn=!Number(p.project_type_id)?' style="background:rgba(246,169,68,.08)"':'',actions='';if(canEdit)actions+='<button class="ab ae" onclick="eProj('+p.id+',\''+esc(p.name)+'\','+p.city_id+')">✏</button>';if(canDelete)actions+='<button class="ab ad" onclick="dProj('+p.id+',\''+esc(p.name)+'\')">🗑</button>';return '<tr'+warn+'><td class="tn">'+escHtml(p.name)+(p.team_names?'<br><span class="v8-team-badge">'+escHtml(p.team_names)+'</span>':'<br><span class="badge bw">بدون تیم فعال</span>')+'</td><td><span class="badge '+(!Number(p.project_type_id)?'bw':'bc')+'">'+escHtml(type)+'</span></td><td><span class="badge bc">'+escHtml(p.cname)+'</span></td><td><span class="badge bcnt">'+toFaDigits(nc)+' کارفرما</span></td><td class="mu">'+fd(p.created_at)+'</td><td>'+(actions?'<div class="tac">'+actions+'</div>':'—')+'</td></tr>';}).join('');};
  var baseEProj=eProj;
  eProj=function(id,n,cid){baseEProj(id,n,cid);var p=(D.p||[]).find(function(x){return x.id===id;});sOpts('vptype','— انتخاب نوع پروژه —',D.pt||[],'id','name');g('vptype').value=p&&Number(p.project_type_id)>0?p.project_type_id:'';sOpts('vpteam','— انتخاب تیم —',(V8.context&&V8.context.teams)||[],'id','name');g('vpteam-wrap').style.display='none';};
  var basePrepM=prepM;
  prepM=function(id){basePrepM(id);if(id==='mp'){sOpts('vptype','— انتخاب نوع پروژه —',D.pt||[],'id','name');g('vptype').value='';sOpts('vpteam','— انتخاب تیم —',(V8.context&&V8.context.teams)||[],'id','name');g('vpteam').value=(V8.context&&V8.context.teams&&V8.context.teams.length===1)?V8.context.teams[0].id:'';g('vpteam-wrap').style.display='';}if(id==='mt'){g('vtcontract').value='';g('vtplanned').value='';v7FillTaskLinks(null);if(g('vttaskimages'))g('vttaskimages').value='';}v71CloseMore();};
  var baseETask=eTask;
  eTask=function(id){baseETask(id);var t=D.t.find(function(x){return x.id===id;});if(t){v7FillTaskLinks(t.contract_id||null);v7TaskContractChanged();g('vtplanned').value=t.planned_statement_id||'';}v71CloseMore();};
  sTask=v7SaveTask;
  var baseVTask=vTask;
  vTask=function(id){baseVTask(id);setTimeout(function(){v7AppendTaskFiles(id);},30);};
  // The help page groups its sections into tabs, so this card is registered
  // with its tab instead of being appended below whatever was rendered last.
  HELP_PROVIDERS.push(function(add){if(!CU||!can('contracts.view'))return;add('finance','<div class="hlp-card v7-help"><h3>📜 آموزش قرارداد، الحاقیه و صورت‌وضعیت</h3><p><b>ویرایش اسناد مالی:</b> دسترسی ثبت و ویرایش قرارداد، الحاقیه و صورت‌وضعیت به‌صورت مستقل از منوی مدیریت دسترسی‌ها قابل تنظیم است.</p><ul><li>دکمه‌های ثبت و ویرایش دقیقاً از دسترسی‌هایی پیروی می‌کنند که مدیر سیستم در منوی «مدیریت دسترسی‌ها» برای نقش شما فعال کرده است.</li><li>تغییر پروژه قرارداد دارای سابقه، با مجوز مستقل انجام می‌شود؛ تسک‌ها، برنامه‌ها، صورت‌وضعیت‌ها و اتصال تیمی در یک عملیات به پروژه مقصد منتقل و سابقه حسابرسی ثبت می‌شود.</li><li>صورت‌وضعیت تا قبل از ثبت «تأییدیه کارفرما» قابل ویرایش است؛ پس از تأیید یا رد قفل می‌شود و برای مورد ردشده باید نسخه اصلاحی ساخته شود.</li><li><b>فیلتر قرارداد:</b> ورود از دکمه‌های «الحاقیه‌ها» و «صورت‌وضعیت‌ها» فقط رکوردهای همان قرارداد را نشان می‌دهد؛ ورود از منوی اصلی فیلتر قبلی را پاک می‌کند.</li><li>تاریخ پایان مؤثر قرارداد، آخرین تاریخ پایان الحاقیه زمانی معتبر است و در نبود آن تاریخ پایان خود قرارداد نمایش داده می‌شود.</li><li>صورت‌وضعیت تاریخی دارای مبلغ تأییدشده، تأییدشده محسوب می‌شود؛ فقط جمع مبلغ‌های تأییدشده از مبلغ مؤثر قرارداد کم شده و درصد پیشرفت ریالی را می‌سازد. تأیید جدید همیشه به معنی تأیید کامل مبلغ است.</li></ul></div>');});
  loadActiveSessions=v7LoadActiveSessions;
  revokeUserSessions=function(userId){return v7RevokeSession(userId,null);};
  var baseSettings=initSettingsPage;
  initSettingsPage=function(){baseSettings();if(CU&&can('system.backup'))v7LoadBackups();};
  renderDashboardCharts=v71RenderDashboardReports;
  renderAnalytics=v71RenderDashboardAnalytics;
  v71InstallSelectOnly();
}

function v71CloseMore(){document.querySelectorAll('.v71-more').forEach(function(x){x.open=false;});}
function v71InstallSelectOnly(){
  var ids=['vtype','vstatus','vpri','vurole','vptype','v7c-type','v7c-category','v7c-status','v7r-score','v7e-type','v7e-price-mode','v7s-type','v7s-month','v7ps-month','v7ps-type'];
  ids.forEach(function(id){var el=g(id);if(el)el.classList.add('v71-select-only');});document.querySelectorAll('select.v71-select-only').forEach(function(el){if(el.dataset.selectOnlyInstalled)return;el.dataset.selectOnlyInstalled='1';el.setAttribute('autocomplete','off');el.addEventListener('keydown',function(ev){if(ev.key&&ev.key.length===1&&!ev.ctrlKey&&!ev.metaKey&&!ev.altKey)ev.preventDefault();});});
}

function v71Rial(v){return v7Money(v)+' ریال';}
function v71Percent(v){return toFaDigits(Number(v||0).toLocaleString('fa-IR',{maximumFractionDigits:2}))+'٪';}
function v71TypeOptions(selected){
  var list=[{id:-1,name:'بدون پروژه'},{id:0,name:'نوع تعیین نشده'}].concat(D.pt||[]);
  return '<option value="">همه نوع‌ها</option>'+list.map(function(x){return '<option value="'+x.id+'"'+v7Selected(x.id,selected)+'>'+escHtml(x.name)+'</option>';}).join('');
}
function v71ProjectOptions(typeId,selected){
  var rows=(D.p||[]).filter(function(p){return typeId===''||String(p.project_type_id||0)===String(typeId);});
  var html='<option value="">همه پروژه‌ها</option>'+(typeId===''||String(typeId)==='-1'?'<option value="-1"'+v7Selected(-1,selected)+'>بدون پروژه</option>':'');
  return html+rows.map(function(p){return '<option value="'+p.id+'"'+v7Selected(p.id,selected)+'>'+escHtml(p.name+' · '+p.cname)+'</option>';}).join('');
}
function v71PopulateReportFilters(){
  ['fin','work'].forEach(function(kind){var t=g('v71-'+kind+'-type'),p=g('v71-'+kind+'-project');if(!t||!p)return;var tv=t.value,pv=p.value;t.innerHTML=v71TypeOptions(tv);p.innerHTML=v71ProjectOptions(tv,pv);});
  var month=g('v71-fin-month');if(month&&month.options.length<2)month.innerHTML='<option value="">همه ماه‌ها</option>'+V7_MONTHS.map(function(n,i){return '<option value="'+(i+1)+'">'+n+'</option>';}).join('');
  var city=g('v71-fin-city');if(city){var cv=city.value;sOpts('v71-fin-city','همه شهرها',D.c||[],'id','name');city.value=cv;}
  var ct=g('v71-fin-contract-type');if(ct){var ctv=ct.value;sOpts('v71-fin-contract-type','همه انواع',V7.lookups.types||[],'id','name');ct.value=ctv;}
  var user=g('v71-work-user');if(user){var uv=user.value,people=(D.u||[]).filter(function(u){return ['support','lead','manager'].indexOf(u.role)>=0;});user.innerHTML='<option value="">همه همکاران</option>'+people.map(function(u){return '<option value="'+u.id+'"'+v7Selected(u.id,uv)+'>'+escHtml(u.display_name||u.username)+'</option>';}).join('');var selfOnly=CU&&!can('users.view_all')&&!can('attendance.manage');if(selfOnly){user.value=String(CU.id);user.disabled=true;}else{user.disabled=false;user.value=uv;}}
}
function v71ReportTypeChanged(kind){var t=g('v71-'+kind+'-type'),p=g('v71-'+kind+'-project');if(p)p.innerHTML=v71ProjectOptions(t?t.value:'','');}
function v71FinancialFilterPayload(){return {year:g('v71-fin-year').value||null,month:g('v71-fin-month').value||null,city_id:g('v71-fin-city').value===''?null:g('v71-fin-city').value,contract_type_id:g('v71-fin-contract-type').value===''?null:g('v71-fin-contract-type').value,project_type_id:g('v71-fin-type').value===''?null:g('v71-fin-type').value,project_id:g('v71-fin-project').value===''?null:g('v71-fin-project').value,from_date:v7IsoFromJalali(g('v71-fin-from').value),to_date:v7IsoFromJalali(g('v71-fin-to').value)};}
function v71WorkFilterPayload(){return {project_type_id:g('v71-work-type').value===''?null:g('v71-work-type').value,project_id:g('v71-work-project').value===''?null:g('v71-work-project').value,user_id:g('v71-work-user').value||null,from_date:v7IsoFromJalali(g('v71-work-from').value),to_date:v7IsoFromJalali(g('v71-work-to').value)};}
function v71ResetFinancialReport(){['v71-fin-year','v71-fin-month','v71-fin-city','v71-fin-contract-type','v71-fin-type','v71-fin-project','v71-fin-from','v71-fin-to'].forEach(function(id){if(g(id))g(id).value='';});v71PopulateReportFilters();v71LoadFinancialReport();}
function v71ResetWorkReport(){['v71-work-type','v71-work-project','v71-work-from','v71-work-to'].forEach(function(id){if(g(id))g(id).value='';});if(g('v71-work-user')&&(!CU||can('users.view_all')||can('attendance.manage')))g('v71-work-user').value='';v71PopulateReportFilters();v71LoadWorkReport();}

async function v71LoadFinancialReport(){
  var box=g('v71-fin-drill');if(!box)return;box.innerHTML='<div class="v7-empty">در حال محاسبه گزارش...</div>';v71PopulateReportFilters();var r=await api('/project_financial_report',v71FinancialFilterPayload());if(!r.ok){box.innerHTML='<div class="v7-empty">'+escHtml(r.error)+'</div>';return;}V7.finReport=r;v71RenderFinancialDimension();
}
function v71ChooseFinancialDimension(kind,button){V7.finDimension=kind||'project_type';document.querySelectorAll('[data-fin-dim]').forEach(function(x){x.classList.remove('active');});if(button)button.classList.add('active');v71RenderFinancialDimension();}
function v71RenderFinancialDimension(){if(V7.finDimension==='city')return v71RenderFinancialCities();if(V7.finDimension==='contract_type')return v71RenderFinancialContractTypes();return v71RenderFinancialTypes();}
function v71DimensionTable(rows,labelKey,labelTitle){v71FinancialSummary();var box=g('v71-fin-drill');box.innerHTML='<section class="v7-group"><div class="v7-group-head"><span>'+escHtml(labelTitle)+'</span><small>این نما بخشی از همان گزارش درآمد است و گزارش تکراری جداگانه ایجاد نشده است.</small></div>'+(rows.length?'<div class="v7-table-wrap"><table class="v7-table"><thead><tr><th>'+escHtml(labelTitle)+'</th><th>پروژه</th><th>قرارداد</th><th>برنامه</th><th>ارسال‌شده</th><th>درآمد تاییدشده</th><th>سهم درآمد</th><th>تحقق</th></tr></thead><tbody>'+rows.map(function(x){return '<tr><td><b>'+escHtml(x[labelKey]||'تعیین نشده')+'</b></td><td>'+toFaDigits(x.project_count||0)+'</td><td>'+toFaDigits(x.contract_count||0)+'</td>'+v71MoneyCells(x)+'</tr>';}).join('')+'</tbody></table></div>':'<div class="v7-empty">در این فیلتر داده مالی وجود ندارد.</div>')+'</section>';}
function v71RenderFinancialCities(){v71DimensionTable((V7.finReport&&V7.finReport.cities)||[],'city_name','درآمد بر اساس شهر');}
function v71RenderFinancialContractTypes(){v71DimensionTable((V7.finReport&&V7.finReport.contract_types)||[],'contract_type_name','درآمد بر اساس نوع قرارداد');}
function v71FinancialSummary(){var t=(V7.finReport&&V7.finReport.totals)||{};g('v71-fin-summary').innerHTML='<div class="v7-grid v71-money-summary"><div class="v7-kpi"><div class="label">برنامه تخصیص‌یافته</div><div class="value">'+v71Rial(t.planned_amount)+'</div></div><div class="v7-kpi"><div class="label">ارسال‌شده به کارفرما</div><div class="value">'+v71Rial(t.sent_amount)+'</div></div><div class="v7-kpi"><div class="label">درآمد تاییدشده</div><div class="value">'+v71Rial(t.approved_amount)+'</div><div class="sub">بدون ارزش افزوده</div></div><div class="v7-kpi"><div class="label">مانده تا برنامه</div><div class="value">'+v71Rial(t.remaining_to_plan)+'</div><div class="v7-progress"><i style="width:'+Math.min(100,Number(t.achievement_percent||0))+'%"></i></div><div class="sub">تحقق '+v71Percent(t.achievement_percent)+'</div></div></div>';}
function v71MoneyCells(x){return '<td class="v7-money">'+v71Rial(x.planned_amount)+'</td><td class="v7-money">'+v71Rial(x.sent_amount)+'</td><td class="v7-money">'+v71Rial(x.approved_amount)+'</td><td>'+v71Percent(x.revenue_share_percent)+'</td><td>'+v71Percent(x.achievement_percent)+'</td>';}
function v71RenderFinancialTypes(){
  v71FinancialSummary();var rows=(V7.finReport&&V7.finReport.types)||[],box=g('v71-fin-drill');box.innerHTML='<section class="v7-group"><div class="v7-group-head"><span>۱. نوع پروژه</span><small>برای دیدن پروژه‌ها روی یک ردیف کلیک کنید</small></div>'+(rows.length?'<div class="v7-table-wrap"><table class="v7-table v71-click-table"><thead><tr><th>نوع پروژه</th><th>پروژه</th><th>قرارداد</th><th>برنامه</th><th>ارسال‌شده</th><th>درآمد تاییدشده</th><th>سهم درآمد</th><th>تحقق</th></tr></thead><tbody>'+rows.map(function(x){return '<tr onclick="v71ShowFinancialType('+x.project_type_id+')"><td><b>'+escHtml(x.project_type_name)+'</b></td><td>'+toFaDigits(x.project_count||0)+'</td><td>'+toFaDigits(x.contract_count||0)+'</td>'+v71MoneyCells(x)+'</tr>';}).join('')+'</tbody></table></div>':'<div class="v7-empty">در این فیلتر، داده مالی وجود ندارد.</div>')+'</section>';
}
function v71ShowFinancialType(typeId){
  var data=V7.finReport||{},type=(data.types||[]).find(function(x){return Number(x.project_type_id)===Number(typeId);})||{},rows=(data.projects||[]).filter(function(x){return Number(x.project_type_id)===Number(typeId);}),box=g('v71-fin-drill');box.innerHTML='<div class="v71-breadcrumb"><button class="v7-mini" onclick="v71RenderFinancialTypes()">همه نوع‌ها</button><span>←</span><b>'+escHtml(type.project_type_name||'نوع پروژه')+'</b></div><section class="v7-group"><div class="v7-group-head"><span>۲. پروژه‌های '+escHtml(type.project_type_name||'')+'</span><small>جمع درآمد تاییدشده: '+v71Rial(type.approved_amount)+'</small></div>'+(rows.length?'<div class="v7-table-wrap"><table class="v7-table v71-click-table"><thead><tr><th>شهر / پروژه</th><th>قرارداد</th><th>برنامه</th><th>ارسال‌شده</th><th>درآمد تاییدشده</th><th>سهم درآمد</th><th>تحقق</th></tr></thead><tbody>'+rows.map(function(x){return '<tr onclick="v71ShowFinancialProject('+x.project_id+','+typeId+')"><td><small>'+escHtml(x.city_name)+'</small><br><b>'+escHtml(x.project_name)+'</b></td><td>'+toFaDigits(x.contract_count||0)+'</td>'+v71MoneyCells(x)+'</tr>';}).join('')+'</tbody></table></div>':'<div class="v7-empty">پروژه‌ای وجود ندارد.</div>')+'</section>';
}
function v71ShowFinancialProject(projectId,typeId){
  var data=V7.finReport||{},project=(data.projects||[]).find(function(x){return Number(x.project_id)===Number(projectId);})||{},rows=(data.contracts||[]).filter(function(x){return Number(x.project_id==null?-1:x.project_id)===Number(projectId);}),statements=(data.statements||[]).filter(function(x){return Number(x.project_id==null?-1:x.project_id)===Number(projectId);}),box=g('v71-fin-drill');var contractHtml='<section class="v7-group"><div class="v7-group-head"><span>۳. قراردادهای پروژه</span><small>جمع کل ریالی: '+v71Rial(project.approved_amount)+'</small></div>'+(rows.length?'<div class="v7-table-wrap"><table class="v7-table v71-click-table"><thead><tr><th>قرارداد</th><th>مبلغ مؤثر</th><th>مانده قرارداد</th><th>برنامه</th><th>ارسال‌شده</th><th>درآمد تاییدشده</th><th>سهم درآمد</th><th>تحقق</th></tr></thead><tbody>'+rows.map(function(x){return '<tr onclick="v71ShowFinancialContract('+x.id+','+projectId+','+typeId+')"><td><b>'+escHtml(x.title)+'</b><br><small>'+escHtml(x.contract_number||'بدون شماره')+'</small></td><td class="v7-money">'+v71Rial(x.effective_price)+'</td><td class="v7-money">'+v71Rial(x.remaining_price)+'</td>'+v71MoneyCells(x)+'</tr>';}).join('')+'</tbody></table></div>':'<div class="v7-empty">قراردادی وجود ندارد.</div>')+'</section>';var statementHtml='<section class="v7-group"><div class="v7-group-head"><span>صورت‌وضعیت‌های همین پروژه</span><small>'+toFaDigits(statements.length)+' مورد · ارسال '+v71Rial(project.sent_amount)+' · تایید '+v71Rial(project.approved_amount)+'</small></div>'+(statements.length?'<div class="v7-table-wrap"><table class="v7-table"><thead><tr><th>قرارداد</th><th>صورت‌وضعیت</th><th>دوره</th><th>وضعیت</th><th>ارسال‌شده</th><th>درآمد تاییدشده</th></tr></thead><tbody>'+statements.map(function(x){return '<tr><td>'+escHtml(x.contract_title||'—')+'</td><td><b>'+escHtml(x.title)+'</b><br><small>'+escHtml(x.statement_number||'')+'</small></td><td>'+toFaDigits(x.period_year||'—')+' / '+toFaDigits(x.period_month||'—')+'</td><td>'+v7StatusChip(x.business_status)+'</td><td class="v7-money">'+v71Rial(x.sent_amount)+'</td><td class="v7-money">'+v71Rial(x.approved_amount)+'</td></tr>';}).join('')+'</tbody></table></div>':'<div class="v7-empty">در این فیلتر صورت‌وضعیتی برای پروژه وجود ندارد.</div>')+'</section>';box.innerHTML='<div class="v71-breadcrumb"><button class="v7-mini" onclick="v71RenderFinancialTypes()">همه نوع‌ها</button><span>←</span><button class="v7-mini" onclick="v71ShowFinancialType('+typeId+')">'+escHtml(project.project_type_name||'نوع')+'</button><span>←</span><b>'+escHtml(project.project_name||'پروژه')+'</b></div>'+contractHtml+statementHtml;
}
function v71ShowFinancialContract(contractId,projectId,typeId){
  var data=V7.finReport||{},co=(data.contracts||[]).find(function(x){return Number(x.id)===Number(contractId);})||{},rows=(data.statements||[]).filter(function(x){return Number(x.contract_id)===Number(contractId);}),box=g('v71-fin-drill');box.innerHTML='<div class="v71-breadcrumb"><button class="v7-mini" onclick="v71ShowFinancialProject('+projectId+','+typeId+')">بازگشت به قراردادها</button><span>←</span><b>'+escHtml(co.title||'قرارداد')+'</b></div><div class="v7-grid v71-money-summary"><div class="v7-kpi"><div class="label">مبلغ مؤثر قرارداد</div><div class="value">'+v71Rial(co.effective_price)+'</div></div><div class="v7-kpi"><div class="label">مانده قرارداد</div><div class="value">'+v71Rial(co.remaining_price)+'</div></div><div class="v7-kpi"><div class="label">ارسال‌شده در فیلتر</div><div class="value">'+v71Rial(co.sent_amount)+'</div></div><div class="v7-kpi"><div class="label">درآمد تاییدشده در فیلتر</div><div class="value">'+v71Rial(co.approved_amount)+'</div></div></div><section class="v7-group"><div class="v7-group-head"><span>۴. صورت‌وضعیت‌ها</span><small>'+toFaDigits(rows.length)+' مورد</small></div>'+(rows.length?'<div class="v7-table-wrap"><table class="v7-table"><thead><tr><th>صورت‌وضعیت</th><th>دوره</th><th>وضعیت</th><th>ارسال‌شده</th><th>درآمد تاییدشده</th></tr></thead><tbody>'+rows.map(function(x){return '<tr><td><b>'+escHtml(x.title)+'</b><br><small>'+escHtml(x.statement_number||'')+'</small></td><td>'+toFaDigits(x.period_year||'—')+' / '+toFaDigits(x.period_month||'—')+'</td><td>'+v7StatusChip(x.business_status)+'</td><td class="v7-money">'+v71Rial(x.sent_amount)+'</td><td class="v7-money">'+v71Rial(x.approved_amount)+'</td></tr>';}).join('')+'</tbody></table></div>':'<div class="v7-empty">در این فیلتر صورت‌وضعیتی وجود ندارد.</div>')+'</section>';
}

async function v71LoadWorkReport(){var box=g('v71-work-drill');if(!box)return;v71PopulateReportFilters();box.innerHTML='<div class="v7-empty">در حال محاسبه کارکرد واقعی...</div>';var r=await api('/project_work_report',v71WorkFilterPayload());if(!r.ok){box.innerHTML='<div class="v7-empty">'+escHtml(r.error)+'</div>';return;}V7.workReport=r;var t=r.totals||{};g('v71-work-summary').innerHTML='<div class="v7-grid"><div class="v7-kpi"><div class="label">کل کارکرد ثبت‌شده</div><div class="value">'+fmtDur(t.seconds||0)+'</div></div><div class="v7-kpi"><div class="label">همکار فعال</div><div class="value">'+toFaDigits(t.user_count||0)+'</div></div><div class="v7-kpi"><div class="label">پروژه دارای کارکرد</div><div class="value">'+toFaDigits(t.project_count||0)+'</div></div></div>';var rows=r.rows||[];box.innerHTML='<section class="v7-group"><div class="v7-group-head"><span>کارکرد واقعی بر اساس تایمر تسک</span><small>برای دیدن ریز تسک‌ها روی ردیف کلیک کنید</small></div>'+(rows.length?'<div class="v7-table-wrap"><table class="v7-table v71-click-table"><thead><tr><th>همکار</th><th>نوع / پروژه</th><th>تسک</th><th>زمان واقعی</th><th>سهم فرد از کار پروژه</th><th>تمرکز فرد روی پروژه</th><th>سهم از کل</th></tr></thead><tbody>'+rows.map(function(x){return '<tr onclick="v71ShowWorkTasks('+x.user_id+','+x.project_id+')"><td><b>'+escHtml(x.display_name)+'</b></td><td><small>'+escHtml(x.project_type_name)+'</small><br>'+escHtml(x.project_name)+'</td><td>'+toFaDigits(x.task_count||0)+'</td><td>'+fmtDur(x.seconds||0)+'</td><td>'+v71Percent(x.project_share_percent)+'</td><td>'+v71Percent(x.person_focus_percent)+'</td><td>'+v71Percent(x.overall_percent)+'</td></tr>';}).join('')+'</tbody></table></div>':'<div class="v7-empty">در این بازه کارکردی ثبت نشده است.</div>')+'</section>';}
function v71ShowWorkTasks(userId,projectId){var data=V7.workReport||{},pair=(data.rows||[]).find(function(x){return Number(x.user_id)===Number(userId)&&Number(x.project_id)===Number(projectId);})||{},rows=(data.tasks||[]).filter(function(x){return Number(x.user_id)===Number(userId)&&Number(x.project_id)===Number(projectId);}),box=g('v71-work-drill');box.innerHTML='<div class="v71-breadcrumb"><button class="v7-mini" onclick="v71LoadWorkReport()">بازگشت به گزارش</button><span>←</span><b>'+escHtml(pair.display_name||'')+' / '+escHtml(pair.project_name||'')+'</b></div><section class="v7-group"><div class="v7-group-head"><span>ریز تسک‌های دارای تایمر</span><small>کل: '+fmtDur(pair.seconds||0)+'</small></div><div class="v7-table-wrap"><table class="v7-table"><thead><tr><th>تسک</th><th>وضعیت</th><th>کارکرد واقعی</th><th>سهم از کار این فرد روی پروژه</th></tr></thead><tbody>'+rows.map(function(x){var pct=pair.seconds?x.seconds*100/pair.seconds:0;return '<tr><td>'+escHtml(x.task_title)+'</td><td>'+escHtml(STATUS_LABELS_FA[x.status]||x.status||'—')+'</td><td>'+fmtDur(x.seconds||0)+'</td><td>'+v71Percent(pct)+'</td></tr>';}).join('')+'</tbody></table></div></section>';}

async function v71LoadPlanBreakdown(){var box=g('v71-plan-breakdown');if(!box||!V7.plan)return;var month=g('v71-plan-breakdown-month'),cur=month.value;if(month.options.length<2)month.innerHTML='<option value="">کل سال</option>'+V7_MONTHS.map(function(n,i){return '<option value="'+(i+1)+'">'+n+'</option>';}).join('');month.value=cur;var r=await api('/project_financial_report',{year:V7.plan.jalali_year,month:month.value||null});if(!r.ok){box.innerHTML='<div class="v7-empty">'+escHtml(r.error)+'</div>';return;}var total=r.totals||{},rows=r.types||[];box.innerHTML='<div class="v71-plan-total"><b>جمع کل:</b><span>برنامه '+v71Rial(total.planned_amount)+'</span><span>ارسال '+v71Rial(total.sent_amount)+'</span><span>تایید '+v71Rial(total.approved_amount)+'</span></div>'+rows.map(function(x){return '<button class="v71-type-card" onclick="showPage(20);setTimeout(function(){g(\'v71-fin-year\').value='+V7.plan.jalali_year+';g(\'v71-fin-month\').value=\''+(month.value||'')+'\';g(\'v71-fin-type\').value=\''+x.project_type_id+'\';v71ReportTypeChanged(\'fin\');v71LoadFinancialReport();},50)"><b>'+escHtml(x.project_type_name)+'</b><span>برنامه '+v71Rial(x.planned_amount)+'</span><span>ارسال '+v71Rial(x.sent_amount)+'</span><span>تایید '+v71Rial(x.approved_amount)+' ('+v71Percent(x.revenue_share_percent)+')</span></button>';}).join('')||'<div class="v7-empty">برای این دوره داده‌ای وجود ندارد.</div>';}

async function v71ExportReport(kind,format){var payload=kind==='work_share'?v71WorkFilterPayload():v71FinancialFilterPayload(),headers={'Content-Type':'application/json'};payload.kind=kind;payload.format=format;if(kind==='project_revenue')payload.dimension=V7.finDimension||'project_type';if(TOKEN)headers['X-Token']=TOKEN;var r=await fetch('/api/v7_export',{method:'POST',headers:headers,body:JSON.stringify(payload)});if(!r.ok)return toast('ساخت خروجی ناموفق بود','err');var b=await r.blob(),url=URL.createObjectURL(b),a=document.createElement('a');a.href=url;a.download='TaskHub_'+kind+'.'+format;document.body.appendChild(a);a.click();a.remove();setTimeout(function(){URL.revokeObjectURL(url);},1000);}

function v71DateIso(date){return date.getFullYear()+'-'+String(date.getMonth()+1).padStart(2,'0')+'-'+String(date.getDate()).padStart(2,'0');}
function v71DateJalali(date){var j=g2j(date.getFullYear(),date.getMonth()+1,date.getDate());return j[0]+'/'+String(j[1]).padStart(2,'0')+'/'+String(j[2]).padStart(2,'0');}
function v71JalaliToDate(value){var iso=v7IsoFromJalali(value);return iso?new Date(iso+'T00:00:00'):null;}
function v71DashboardRange(){
  var mode=(g('v71-dash-period')&&g('v71-dash-period').value)||'all',today=new Date(),start=null,end=new Date(today.getFullYear(),today.getMonth(),today.getDate());
  if(mode==='all')return {mode:mode,start:null,end:null,label:'نمایش همه زمان‌ها'};
  if(mode==='week'){start=new Date(end);start.setDate(start.getDate()-6);}
  else if(mode==='month'||mode==='quarter'||mode==='year'){var j=g2j(end.getFullYear(),end.getMonth()+1,end.getDate()),jm=mode==='month'?j[1]:(mode==='quarter'?(Math.floor((j[1]-1)/3)*3+1):1),gdate=j2g(j[0],jm,1);start=new Date(gdate[0],gdate[1]-1,gdate[2]);}
  else if(mode==='custom'){start=v71JalaliToDate(g('v71-dash-from').value);end=v71JalaliToDate(g('v71-dash-to').value);if(!start||!end)return {mode:mode,start:null,end:null,label:'بازه دلخواه را کامل کنید',invalid:true};}
  var names={week:'هفته اخیر',month:'این ماه',quarter:'این فصل',year:'امسال',custom:'بازه دلخواه'};
  return {mode:mode,start:start,end:end,label:names[mode]+' · '+toFaDigits(v71DateJalali(start))+' تا '+toFaDigits(v71DateJalali(end))};
}
function v71EnsureComparisonJalali(){if(V7.compareYear&&V7.compareMonth)return;var now=v7CurrentJalali();V7.compareYear=now.year;V7.compareMonth=now.month;}
function v71DashboardFilterPayload(){v71EnsureComparisonJalali();var r=v71DashboardRange(),payload={comparison_jalali_year:V7.compareYear,comparison_jalali_month:V7.compareMonth};if(r.invalid||!r.start)return payload;payload.from_date=v71DateIso(r.start);payload.to_date=v71DateIso(r.end);payload.from_jalali=v71DateJalali(r.start);payload.to_jalali=v71DateJalali(r.end);payload.period=r.mode;return payload;}
function v71ComparisonChanged(){var y=g('v71-compare-year'),m=g('v71-compare-month');V7.compareYear=Number(y&&y.value)||v7CurrentJalali().year;V7.compareMonth=Number(m&&m.value)||v7CurrentJalali().month;V7.dashReport=null;V7.dashReportPromise=null;v71RenderDashboardAnalytics();}
function v71FilterDashboardTasks(tasks){
  var r=v71DashboardRange();if(!r||r.invalid||!r.start)return tasks||[];
  var from=v71DateJalali(r.start).replace(/\//g,''),to=v71DateJalali(r.end).replace(/\//g,'');
  return (tasks||[]).filter(function(t){var d=String(t.date_recv||'').replace(/[^0-9۰-۹٠-٩]/g,'');d=toEnDigits(d);return d&&d>=from&&d<=to;});
}
function v71DashboardFilterChanged(){var custom=g('v71-dash-period').value==='custom';g('v71-dash-custom').style.display=custom?'flex':'none';if(!custom)v71ApplyDashboardFilter();}
function v71ApplyDashboardFilter(){var r=v71DashboardRange();g('v71-dash-filter-label').textContent=r.label;if(r.invalid)return toast('تاریخ شروع و پایان را انتخاب کنید','err');if(r.start&&r.end&&r.end<r.start)return toast('تاریخ پایان قبل از تاریخ شروع است','err');V7.dashReport=null;V7.dashReportPromise=null;V7.dashFinancial=null;V7.dashFinancialPromise=null;V7.dashAttribution=null;V7.dashAttributionPromise=null;if(can('dashboard.organization_analytics')){v71RenderDashboardReports();v71RenderDashboardAnalytics();}if(can('dashboard.financial')){v7LoadFinancialDashboard();v802LoadDashboardFinancialCards(true);}if(typeof upDashLists==='function')upDashLists();}

function v802DashboardMoneyRows(rows,labelKey){
  rows=(rows||[]).slice().sort(function(a,b){return Number(b.approved_amount||0)-Number(a.approved_amount||0);}).slice(0,6);
  if(!rows.length)return '<div class="chart-empty">در این بازه درآمد تاییدشده‌ای وجود ندارد</div>';
  var max=Math.max.apply(null,rows.map(function(x){return Number(x.approved_amount||0);}))||1;
  return '<div class="v802-money-list">'+rows.map(function(x){var value=Number(x.approved_amount||0),pct=Math.max(2,Math.round(value/max*100));return '<div class="v802-money-row"><div class="v802-money-meta"><span title="'+escHtml(x[labelKey]||'تعیین نشده')+'">'+escHtml(x[labelKey]||'تعیین نشده')+'</span><b>'+v7Money(value)+'</b></div><div class="v802-money-track"><i style="width:'+pct+'%"></i></div><small>'+toFaDigits(x.contract_count||0)+' قرارداد · '+toFaDigits(x.revenue_share_percent||0)+'٪ از درآمد</small></div>';}).join('')+'</div>';
}
function v802DashboardAttributionHtml(r){
  var t=(r&&r.totals)||{},q=(r&&r.quality)||{},team=(r&&r.teams&&r.teams[0])||null,person=(r&&r.people&&r.people[0])||null;
  var warnings=Number(q.completed_without_contract||0)+Number(q.completed_without_team||0)+Number(q.multi_assignee_without_time||0)+Number(q.contracts_without_completed_task||0);
  return '<div class="v802-dash-kpis"><div><small>درآمد تاییدشده</small><b>'+v7Money(t.approved_amount||0)+'</b></div><div><small>منتسب به تیم‌ها</small><b>'+v7Money(t.team_attributed_amount||0)+'</b></div><div><small>منتسب به افراد</small><b>'+v7Money(t.person_attributed_amount||0)+'</b></div><div class="'+(warnings?'warn':'ok')+'"><small>هشدار کیفیت داده</small><b>'+toFaDigits(warnings)+'</b></div></div>'+((team||person)?'<div class="v802-dash-leaders">'+(team?'<span>تیم برتر: <b>'+escHtml(team.team_name||'—')+'</b> · '+v7Money(team.financial_share_amount||0)+'</span>':'')+(person?'<span>فرد برتر: <b>'+escHtml(person.display_name||'—')+'</b> · '+v7Money(person.financial_share_amount||0)+'</span>':'')+'</div>':'<div class="chart-empty">هنوز سهم قابل محاسبه‌ای وجود ندارد</div>');
}
async function v802LoadDashboardFinancialCards(force){
  if(!CU||!can('dashboard.financial')||!can('reports.financial'))return;
  var cityBox=g('chart-income-city'),typeBox=g('chart-income-contract-type'),shareBox=g('chart-financial-attribution');
  if(!cityBox&&!typeBox&&!shareBox)return;
  var payload=v71DashboardFilterPayload();
  if(force){V7.dashFinancial=null;V7.dashFinancialPromise=null;V7.dashAttribution=null;V7.dashAttributionPromise=null;}
  if(!V7.dashFinancialPromise)V7.dashFinancialPromise=api('/project_financial_report',payload);
  if(!V7.dashAttributionPromise)V7.dashAttributionPromise=api('/v8/financial_attribution',payload);
  var results=await Promise.all([V7.dashFinancialPromise,V7.dashAttributionPromise]);
  var fin=results[0],attr=results[1];
  if(fin&&fin.ok){V7.dashFinancial=fin;if(cityBox)cityBox.innerHTML=v802DashboardMoneyRows(fin.cities||[],'city_name');if(typeBox)typeBox.innerHTML=v802DashboardMoneyRows(fin.contract_types||[],'contract_type_name');}
  else {var msg='<div class="chart-empty">خطا در دریافت گزارش درآمد</div>';if(cityBox)cityBox.innerHTML=msg;if(typeBox)typeBox.innerHTML=msg;}
  if(attr&&attr.ok){V7.dashAttribution=attr;if(shareBox)shareBox.innerHTML=v802DashboardAttributionHtml(attr);}
  else if(shareBox)shareBox.innerHTML='<div class="chart-empty">خطا در دریافت سهم مالی</div>';
}
function v802OpenIncomeDimension(kind){
  showPage(20);V7.finDimension=kind||'city';
  var button=document.querySelector('[data-fin-dim="'+V7.finDimension+'"]');
  document.querySelectorAll('[data-fin-dim]').forEach(function(x){x.classList.remove('active');});if(button)button.classList.add('active');
  v71LoadFinancialReport();
}
function v802OpenFinancialAttribution(){
  showPage(23);var button=document.querySelector('[data-v8-report="financial_attribution"]');
  if(typeof v8ChooseReport==='function')v8ChooseReport('financial_attribution',button);
}

async function v71GetDashboardReport(){if(V7.dashReport)return V7.dashReport;if(!V7.dashReportPromise)V7.dashReportPromise=api('/dashboard_reports',v71DashboardFilterPayload());var r=await V7.dashReportPromise;if(r&&r.ok)V7.dashReport=r;return r;}
async function v71RenderDashboardReports(){
  if(!CU||!can('dashboard.organization_analytics'))return;var r=await v71GetDashboardReport();if(!r||!r.ok)return;
  var statusSegs=Object.keys(r.by_status||{}).map(function(k){return {label:STATUS_LABELS_FA[k]||k,value:r.by_status[k],color:STATUS_COLORS[k]||'#8892b0'};});if(g('chart-status'))g('chart-status').innerHTML=donutSvg(statusSegs);if(g('chart-city'))g('chart-city').innerHTML=hbars(r.by_city||[]);if(g('chart-project'))g('chart-project').innerHTML=hbars(r.by_project||[]);if(g('chart-project-type'))g('chart-project-type').innerHTML=hbars(r.by_project_type||[]);
  if(g('chart-staff')){var staff=r.by_staff||[];if(!staff.length)g('chart-staff').innerHTML='<div class="chart-empty">داده‌ای برای نمایش نیست</div>';else{var max=Math.max.apply(null,staff.map(function(x){return Number(x.open||0)+Number(x.done||0);} ))||1;g('chart-staff').innerHTML=staff.slice(0,8).map(function(x){var op=Math.round(Number(x.open||0)/max*100),dp=Math.round(Number(x.done||0)/max*100);return '<div class="chart-bar-row"><span class="chart-bar-label">'+escHtml(x.label)+'</span><span class="chart-bar-track"><span class="chart-bar-fill" style="width:'+op+'%;background:#19C4EC;border-radius:0"></span><span class="chart-bar-fill" style="width:'+dp+'%;background:#10b981;border-radius:0"></span></span><span class="chart-bar-val">'+toFaDigits(Number(x.open||0)+Number(x.done||0))+'</span></div>';}).join('')+'<div class="chart-legend"><span><i style="background:#19C4EC"></i>باز</span><span><i style="background:#10b981"></i>انجام‌شده</span></div>';}}  v802LoadDashboardFinancialCards(false);
}
async function v71RenderDashboardAnalytics(){
  if(!CU||!can('dashboard.organization_analytics'))return;v71EnsureComparisonJalali();var r=await v71GetDashboardReport();if(!r||!r.ok)return;
  V7.compareYear=Number(r.comparison_jalali_year||V7.compareYear);V7.compareMonth=Number(r.comparison_jalali_month||V7.compareMonth);
  var current=Number(r.selected_count||0),previous=Number(r.previous_count||0),diff=current-previous,pct=previous?Math.round(diff/previous*100):(current?100:0),arrow=diff>0?'▲':(diff<0?'▼':'■'),color=diff>0?'var(--green)':(diff<0?'var(--coral)':'var(--txt2)'),max=Math.max(current,previous,1),box=g('analytics-month');
  if(box){var title=box.closest('.dl-card').querySelector('.dl-card-t');if(title)title.textContent='📈 مقایسه پیشرفت تسک‌ها (شمسی)';var now=v7CurrentJalali(),years=[];for(var yy=now.year+1;yy>=now.year-5;yy--)years.push(yy);if(years.indexOf(V7.compareYear)<0)years.push(V7.compareYear);years.sort(function(a,b){return b-a;});box.innerHTML='<div class="v71-compare-filter"><label>سال <select class="fi" id="v71-compare-year" onchange="v71ComparisonChanged()">'+years.map(function(y){return '<option value="'+y+'"'+(y===V7.compareYear?' selected':'')+'>'+toFaDigits(y)+'</option>';}).join('')+'</select></label><label>ماه <select class="fi" id="v71-compare-month" onchange="v71ComparisonChanged()">'+v7MonthOptions(V7.compareMonth,false)+'</select></label></div>'+ 
    '<div class="v71-month-chart"><div class="v71-month-bars"><div class="v71-month-column"><b>'+toFaDigits(current)+'</b><div class="v71-month-bar current" style="height:'+Math.max(8,Math.round(current/max*118))+'px"></div><small>'+escHtml(r.selected_label)+'</small></div><div class="v71-month-column"><b>'+toFaDigits(previous)+'</b><div class="v71-month-bar previous" style="height:'+Math.max(8,Math.round(previous/max*118))+'px"></div><small>'+escHtml(r.previous_label)+'</small></div></div><div class="v71-month-change" style="color:'+color+'"><strong>'+arrow+' '+toFaDigits(Math.abs(pct))+'٪</strong><span>'+toFaDigits(Math.abs(diff))+' تسک '+(diff>=0?'بیشتر':'کمتر')+' از ماه قبل</span></div></div>';
  }
  var sb=g('analytics-staff'),rows=(r.analytics_staff||[]).slice(0,6);if(sb)sb.innerHTML=rows.length?rows.map(function(x){return '<div class="chart-bar-row"><span class="chart-bar-label">'+escHtml(x.label)+'</span><span class="chart-bar-track"><span class="chart-bar-fill" style="width:'+Math.min(100,Math.max(5,Math.round(Number(x.avg_seconds||0)/Math.max.apply(null,rows.map(function(z){return Number(z.avg_seconds||0);}).concat([1]))*100)))+'%;background:var(--purple)"></span></span><span class="chart-bar-val">'+fmtDur(x.avg_seconds||0)+'</span></div>';}).join(''):'<div class="chart-empty">تسک تکمیل‌شده‌ای در این بازه وجود ندارد</div>';
}
async function v7DeleteMaster(kind,id,name){if(!confirm('حذف «'+name+'»؟'))return;var r=await api('/master_delete',{kind:kind,id:id});if(!r.ok)return toast(r.error,'err');await loadAll();toast('حذف شد','ok');}

function v7TaskContractText(value){return String(value||'').replace(/[\u200c\u200f\u202a-\u202e]/g,' ').replace(/\s+/g,' ').trim().toLowerCase();}
function v7TaskContractMatchesType(row,type){
  var text=v7TaskContractText([row.title,row.contract_type_name,row.category_name].join(' '));
  if(type==='dev'||type==='devminor')return text.indexOf('توسعه')>=0;
  if(type==='bug')return ['پشتیبانی','نگهداری','رفع'].some(function(k){return text.indexOf(k)>=0;});
  return false;
}
function v7FillTaskLinks(selectedId){
  var select=g('vtcontract'),wrap=g('v7-task-links');if(!select)return;
  var allowed=can('tasks.link_contract');if(wrap)wrap.style.display=allowed?'':'none';
  if(!allowed){select.innerHTML='<option value="">— بدون قرارداد —</option>';if(g('vtplanned'))g('vtplanned').innerHTML='<option value="">— بدون برنامه صورت‌وضعیت —</option>';return;}
  var cur=selectedId!==undefined&&selectedId!==null?String(selectedId):String(select.value||'');
  var pid=Number(g('vtproj')&&g('vtproj').value)||0,type=(g('vtype')&&g('vtype').value)||'bug';
  var rows=(V7.taskContracts||[]).filter(function(x){
    return pid&&Number(x.project_id)===pid&&(!x.is_closed||String(x.id)===cur);
  });
  var preferred=rows.filter(function(x){return !x.is_closed&&v7TaskContractMatchesType(x,type);});
  if(preferred.length)rows=preferred.concat(rows.filter(function(x){return preferred.indexOf(x)<0&&String(x.id)===cur;}));
  sOpts('vtcontract','— بدون قرارداد —',rows,'id',function(x){
    return x.title+(x.contract_number?' · '+x.contract_number:'')+(x.contract_type_name?' · '+x.contract_type_name:'')+(x.contract_status_name?' · '+x.contract_status_name:'');
  });
  if(cur&&rows.some(function(x){return String(x.id)===cur;}))select.value=cur;
  else if(rows.length===1)select.value=String(rows[0].id);
  else select.value='';
  v7TaskContractChanged();
}
function v7TaskContractChanged(){
  if(!g('vtplanned'))return;var cid=g('vtcontract').value,items=((V7.planData&&V7.planData.planned)||[]).filter(function(x){return !cid||String(x.contract_id)===String(cid);});sOpts('vtplanned','— بدون برنامه صورت‌وضعیت —',items,'id',function(x){return (V7_MONTHS[(x.month_no||1)-1]||'')+' · '+x.title;});
}

async function v7SaveTask(){
  var title=g('vtitle').value.trim(),pid=Number(g('vtproj').value)||null;if(!title||!pid)return toast('عنوان و پروژه الزامی است','err');
  var status=g('vstatus').value,sid=g('vtstaff').value||null,cid=g('vtcont').value||null;
  if(can('tasks.self_manage')&&!can('tasks.edit')){pid=CU.project_id;sid=null;if(!D.eid){status='registered';cid=CU.id;}}
  if(can('tasks.assign')&&!D.eid&&sid)status='assigned';
  var body={id:D.eid,title:title,type:g('vtype').value,status:status,category_id:g('vcat').value||null,project_id:pid,contact_id:cid,staff_id:sid,date_recv:g('vtrecv').value||null,date_delivery:g('vtdel').value||null,description:g('vtdesc').value.trim()||null,solution:g('vtsol').value.trim()||null,priority:Number(g('vpri').value)||2,contract_id:g('vtcontract').value||null,planned_statement_id:g('vtplanned').value||null,project_team_id:g('vtteam')&&g('vtteam').value||null,progress_weight:g('vtweight')?v7Num(g('vtweight').value):1};
  var btn=g('vtsavebtn');btn.disabled=true;try{var r=await api('/task_save',body);if(!r.ok)return toast(r.error,'err');var files=Array.from((g('vttaskimages')&&g('vttaskimages').files)||[]);for(var i=0;i<files.length;i++)await v7UploadRaw('task',r.id,files[i],'');closeM('mt');await loadAll();renderKanban();toast('تسک ذخیره شد','ok');}finally{btn.disabled=false;btn.textContent='✔ ذخیره';}
}

async function v7LoadLookups(){
  if(Object.keys(V7.lookups||{}).length)return true;
  // Called from the background refresh as well as from screens, so a denial
  // must stay silent - a toast here repeats on every poll.
  var r=await api('/contract_lookups',{});if(!r||!r.ok)return false;V7.lookups=r;return true;
}
async function v7LoadTaskContractOptions(silent){
  if(!CU||!can('tasks.link_contract')){V7.taskContracts=[];v7FillTaskLinks();return;}
  var r=await api('/task_contract_options',{});
  if(!r||!r.ok){V7.taskContracts=[];if(!silent)toast((r&&r.error)||'خطا در دریافت قراردادهای تسک','err');v7FillTaskLinks();return;}
  V7.taskContracts=r.rows||[];v7FillTaskLinks();
}
// Archive browsing is a per-page view toggle, not a filter that survives a
// reload: leaving the page always returns to the live records so nobody edits
// an archived row believing it is current.
var V7Archive={contract:false,extension:false,statement:false};
function v7ArchiveOn(kind){return !!V7Archive[kind]&&can('archives.view');}
function v7ToggleArchive(kind){
  if(!can('archives.view'))return toast('دسترسی مشاهده بایگانی را ندارید','err');
  V7Archive[kind]=!V7Archive[kind];
  var btn=g('v7-'+kind+'-archive-toggle'),banner=g('v7-'+kind+'-archive-banner');
  if(btn){btn.classList.toggle('active',V7Archive[kind]);btn.textContent=V7Archive[kind]?'↩ فهرست فعال':'🗄 بایگانی‌ها';}
  if(banner)banner.style.display=V7Archive[kind]?'':'none';
  if(kind==='contract')v7LoadContracts();
  else if(kind==='extension')v7LoadExtensions(g('v7-extension-contract').value);
  else v7LoadStatements(g('v7-statement-contract').value);
}
async function v7RestoreRecord(kind,id){
  var label={contract:'قرارداد',extension:'الحاقیه',statement:'صورت‌وضعیت'}[kind];
  if(!confirm(label+' به فهرست فعال بازگردانده شود؟'))return;
  var r=await api('/'+kind+'_restore',{id:id});if(!r.ok)return toast(r.error,'err');
  if(kind==='contract')await v7LoadContracts();
  else if(kind==='extension')await v7LoadExtensions(g('v7-extension-contract').value);
  else await v7LoadStatements(g('v7-statement-contract').value);
  toast(label+' بازگردانده شد','ok');
}
async function v7LoadContracts(silent){
  if(!CU||!can('contracts.view'))return;
  await v7LoadLookups();var r=await api('/contracts',{only_without_project:!!(g('v7-only-unassigned')&&g('v7-only-unassigned').checked),archived:v7ArchiveOn('contract')});
  if(!r.ok){if(!silent)toast(r.error,'err');return;}V7.contracts=r.rows||[];D.contracts=V7.contracts;if(can('tasks.link_contract'))await v7LoadTaskContractOptions(true);v7FillContractSelects();v7RenderContracts();v7FillTaskLinks();
}
function v7FillContractSelects(){
  ['v7-extension-contract','v7-statement-contract','v7e-contract','v7s-contract','v7ps-contract'].forEach(function(id){var e=g(id);if(!e)return;var cur=e.value;sOpts(id,id.indexOf('-contract')>=0&&id.indexOf('v7e')!==0&&id.indexOf('v7s')!==0&&id.indexOf('v7ps')!==0?'همه قراردادها':'— انتخاب قرارداد —',V7.contracts,'id',function(x){return x.title+(x.contract_number?' · '+x.contract_number:'')+(x.project_name?' · '+x.project_name:' · بدون پروژه');});if(cur)e.value=cur;});
}
function v7GroupRows(rows,renderer){
  if(!rows.length)return '<div class="v7-empty">رکوردی برای نمایش وجود ندارد.</div>';
  var groups={};rows.forEach(function(x){var key=(x.city_name||'پروژه تعیین‌نشده')+'|'+(x.project_name||'پروژه تعیین‌نشده');(groups[key]=groups[key]||[]).push(x);});
  return Object.keys(groups).sort().map(function(key){var p=key.split('|'),arr=groups[key];return '<section class="v7-group"><div class="v7-group-head">🏙 '+escHtml(p[0])+' <span>←</span> 🏢 '+escHtml(p[1])+'<small>'+toFaDigits(arr.length)+' مورد</small></div>'+renderer(arr)+'</section>';}).join('');
}
function v7RenderContracts(){
  var box=g('v7-contracts');if(!box)return;var q=(g('v7-contract-search').value||'').trim().toLowerCase();var rows=V7.contracts.filter(function(x){return !q||[x.title,x.contract_number,x.project_name,x.city_name,x.employer_name].join(' ').toLowerCase().indexOf(q)>=0;});
  box.innerHTML=v7GroupRows(rows,function(arr){return '<div class="v7-table-wrap"><table class="v7-table"><thead><tr><th>قرارداد</th><th>کارفرما</th><th>پایان مؤثر</th><th>مبلغ مؤثر</th><th>مانده ریالی</th><th>پیشرفت ریالی</th><th>خوش‌حسابی</th><th>وضعیت</th><th>عملیات</th></tr></thead><tbody>'+arr.map(function(x){
    var exp=x.expiry_level==='closed'?'exp-closed':((Number(x.remaining_price)<0||x.expiry_level==='red')?'exp-red':(x.expiry_level==='yellow'?'exp-yellow':''));var day=x.expiry_level==='closed'?'قرارداد بسته‌شده':(x.days_to_end==null?'بدون تاریخ':(x.days_to_end<0?toFaDigits(Math.abs(x.days_to_end))+' روز گذشته':toFaDigits(x.days_to_end)+' روز مانده'));
    if(v7ArchiveOn('contract')){
      var rest=(can('archives.restore')&&can('contracts.archive'))?'<button class="v7-mini primary" onclick="v7RestoreRecord(\'contract\','+x.id+')">↩ بازگردانی</button>':'';
      return '<tr class="v7-archived-row"><td><b>'+escHtml(x.title)+'</b><br><small class="v7-muted">'+escHtml(x.contract_number||'بدون شماره')+'</small></td><td>'+escHtml(x.employer_name||'—')+'</td><td>'+v7FaDate(x.effective_end_date_fa||x.effective_end_date)+'</td><td class="v7-money">'+v7Money(x.effective_price)+'</td><td class="v7-money">'+v7Money(x.remaining_price)+'</td><td>—</td><td>'+v7RatingText(x.payer_rating)+'</td><td><span class="v7-archived-chip">بایگانی‌شده</span></td><td><div class="v7-actions">'+rest+'</div></td></tr>';
    }
    var actions='';if(can('extensions.view'))actions+='<button class="v7-mini primary" onclick="v7OpenContractChildren('+x.id+',\'extensions\')">الحاقیه‌ها ('+toFaDigits(x.extension_count||0)+')</button>';if(can('statements.view'))actions+='<button class="v7-mini primary" onclick="v7OpenContractChildren('+x.id+',\'statements\')">صورت‌وضعیت‌ها ('+toFaDigits(x.statement_count||0)+')</button>';if(can('contracts.approve'))actions+='<button class="v7-mini" onclick="v7OpenRating('+x.id+')">⭐ امتیاز</button>';
    if(can('contracts.manage'))actions+='<button class="v7-mini" onclick="v7OpenContract('+x.id+')">✏ ویرایش</button>';
    if(can('contracts.archive'))actions+='<button class="v7-mini danger" onclick="v7ArchiveContract('+x.id+')">بایگانی</button>';
    return '<tr class="'+exp+'"><td><b>'+escHtml(x.title)+'</b><br><small class="v7-muted">'+escHtml(x.contract_number||'بدون شماره')+'</small>'+(x.team_names?'<br><span class="v8-team-badge">'+escHtml(x.team_names)+'</span>':'')+'</td><td>'+escHtml(x.employer_name||'—')+'</td><td>'+v7FaDate(x.effective_end_date_fa||x.effective_end_date)+'<br><small>'+day+'</small></td><td class="v7-money">'+v7Money(x.effective_price)+'</td><td class="v7-money">'+v7Money(x.remaining_price)+'</td><td><span class="v7-financial-progress">'+toFaDigits(Number(x.financial_progress_percent||0).toFixed(2))+'٪</span></td><td>'+v7RatingText(x.payer_rating)+'</td><td>'+escHtml(x.contract_status_name||'—')+'</td><td><div class="v7-actions">'+actions+'</div></td></tr>';
  }).join('')+'</tbody></table></div>';});
}
function v7OpenContractChildren(id,kind){var permission=kind==='extensions'?'extensions.view':'statements.view';if(!can(permission))return toast('دسترسی مشاهده این بخش را ندارید','err');V7.pendingContractFilter={id:Number(id),kind:kind};showPage(kind==='extensions'?17:18);}

async function v7OpenContract(id){
  if(!can('contracts.manage'))return toast('دسترسی ثبت یا ویرایش قرارداد را ندارید','err');await v7LoadLookups();if(!V7.contracts.length)await v7LoadContracts(true);
  var x=id?V7.contracts.find(function(a){return a.id===id;}):null;V7.currentEntity=x||{id:null};g('v7-contract-title').textContent=x?'ویرایش قرارداد':'قرارداد جدید';
  sOpts('v7c-project','— پروژه تعیین‌نشده —',D.p,'id',function(p){return p.name+' · '+p.cname;});g('v7c-project').value=x&&x.project_id||'';
  sOpts('v7c-type','— بدون نوع —',V7.lookups.types||[],'id','name');g('v7c-type').value=x&&x.contract_type_id||'';
  sOpts('v7c-category','— بدون دسته —',V7.lookups.categories||[],'id','name');g('v7c-category').value=x&&x.category_id||'';
  sOpts('v7c-status','— بدون وضعیت —',V7.lookups.statuses||[],'id','name');g('v7c-status').value=x&&x.contract_status_id||'';
  [['v7c-title','title'],['v7c-employer','employer_name'],['v7c-number','contract_number'],['v7c-price','base_price'],['v7c-notify-fa','notification_date_fa'],['v7c-letter','notification_letter_number'],['v7c-start-fa','start_date_fa'],['v7c-end-fa','end_date_fa'],['v7c-workorder','work_order_code'],['v7c-financial','financial_code'],['v7c-commercial','commercial_code'],['v7c-crn','tax_info_crn'],['v7c-insurance','insurance_coefficient'],['v7c-guarantee','guarantee_coefficient'],['v7c-sajat-date-fa','register_date_sajat_fa']].forEach(function(a){g(a[0]).value=x&&x[a[1]]!=null?x[a[1]]:'';});v7FormatMoneyInput(g('v7c-price'));g('v7c-sajat').checked=!!(x&&x.register_in_sajat);g('v7c-new').checked=!!(x&&x.is_new);v71CloseMore();openM('v7-m-contract');
}
async function v7SaveContract(){
  var title=g('v7c-title').value.trim();if(!title)return toast('عنوان قرارداد الزامی است','err');var x=V7.currentEntity||{};
  var newProject=g('v7c-project').value||null,projectChanged=!!x.id&&String(x.project_id||'')!==String(newProject||'');
  if(projectChanged&&!confirm('پروژه قرارداد تغییر کند؟ اگر قرارداد سابقه داشته باشد، تمام تسک‌ها، برنامه‌ها، صورت‌وضعیت‌ها و اتصال تیمی آن به پروژه جدید منتقل می‌شوند و سابقه حسابرسی ثبت خواهد شد.'))return;
  var body={id:x.id,project_id:newProject,confirm_project_relink:projectChanged&&can('contracts.relink_project'),title:title,employer_name:g('v7c-employer').value.trim(),contract_number:g('v7c-number').value.trim(),base_price:v7Num(g('v7c-price').value),notification_date_fa:g('v7c-notify-fa').value,notification_date:v7IsoFromJalali(g('v7c-notify-fa').value),notification_letter_number:g('v7c-letter').value.trim(),start_date_fa:g('v7c-start-fa').value,start_date:v7IsoFromJalali(g('v7c-start-fa').value),end_date_fa:g('v7c-end-fa').value,end_date:v7IsoFromJalali(g('v7c-end-fa').value),contract_type_id:g('v7c-type').value||null,category_id:g('v7c-category').value||null,contract_status_id:g('v7c-status').value||null,work_order_code:g('v7c-workorder').value.trim(),financial_code:g('v7c-financial').value.trim(),commercial_code:g('v7c-commercial').value.trim(),tax_info_crn:g('v7c-crn').value.trim(),insurance_coefficient:v7Num(g('v7c-insurance').value),guarantee_coefficient:v7Num(g('v7c-guarantee').value),register_in_sajat:g('v7c-sajat').checked,register_date_sajat_fa:g('v7c-sajat-date-fa').value,register_date_sajat:v7IsoFromJalali(g('v7c-sajat-date-fa').value),is_new:g('v7c-new').checked,project_teams:typeof v8ContractTeamEntries==='function'?v8ContractTeamEntries():[]};
  var r=await api('/contract_save',body);if(!r.ok)return toast(r.error,'err');closeM('v7-m-contract');await v7LoadContracts();toast('قرارداد ذخیره شد','ok');
}
async function v7ArchiveContract(id){if(!can('contracts.archive'))return toast('دسترسی بایگانی قرارداد را ندارید','err');if(!confirm('قرارداد بایگانی شود؟ اطلاعات وابسته حذف فیزیکی نمی‌شوند.'))return;var r=await api('/contract_archive',{id:id});if(!r.ok)return toast(r.error,'err');await v7LoadContracts();toast('قرارداد بایگانی شد','ok');}
function v7OpenRating(id){var x=V7.contracts.find(function(a){return a.id===id;});if(!x)return;V7.currentEntity=x;g('v7r-score').value=x.payer_rating||0;g('v7r-note').value=x.payer_note||'';g('v7r-lock').checked=!!x.payer_locked;g('v7r-lock-wrap').style.display=v7CanApprove()?'':'none';g('v7r-score').disabled=!can('contracts.approve');openM('v7-m-rating');}
async function v7SaveRating(){var x=V7.currentEntity,r=await api('/contract_rating',{id:x.id,rating:Number(g('v7r-score').value),note:g('v7r-note').value,lock:g('v7r-lock').checked});if(!r.ok)return toast(r.error,'err');closeM('v7-m-rating');await v7LoadContracts();toast('امتیاز ذخیره شد','ok');}

async function v7LoadExtensions(contractId){
  if(!can('extensions.view'))return;await v7LoadLookups();if(!V7.contracts.length)await v7LoadContracts(true);var r=await api('/extensions',{contract_id:contractId||null,archived:v7ArchiveOn('extension')});if(!r.ok)return toast(r.error,'err');V7.extensions=r.rows||[];v7FillContractSelects();g('v7-extension-contract').value=contractId?String(contractId):'';v7RenderExtensions();
}
function v7RenderExtensions(){
  var box=g('v7-extensions');if(!box)return;var q=(g('v7-extension-search').value||'').toLowerCase();var rows=V7.extensions.filter(function(x){return !q||[x.title,x.extension_number,x.contract_title,x.letter_number].join(' ').toLowerCase().indexOf(q)>=0;});
  box.innerHTML=v7GroupRows(rows,function(arr){return '<div class="v7-table-wrap"><table class="v7-table"><thead><tr><th>قرارداد</th><th>الحاقیه</th><th>نوع</th><th>پایان جدید</th><th>اثر ریالی</th><th>تایید داخلی</th><th>عملیات</th></tr></thead><tbody>'+arr.map(function(x){
    var actions=can('attachments.view')?'<button class="v7-mini" onclick="v7OpenFiles(\'extension\','+x.id+',\'الحاقیه\')">📎 فایل</button>':'';
    if(v7ArchiveOn('extension')){
      // An archived row is read-only until it is brought back, so the only
      // action offered is the one that makes it editable again.
      if(can('archives.restore')&&can('extensions.archive'))actions+='<button class="v7-mini primary" onclick="v7RestoreRecord(\'extension\','+x.id+')">↩ بازگردانی</button>';
      return '<tr class="v7-archived-row"><td><b>'+escHtml(x.contract_title)+'</b><br><small>'+escHtml(x.contract_number||'')+'</small></td><td><b>'+escHtml(x.title)+'</b><br><small>'+escHtml(x.extension_number||'بدون شماره')+' · '+v7FaDate(x.extension_date_fa||x.extension_date)+'</small></td><td>'+escHtml(x.extension_type_name||'—')+'</td><td>'+v7FaDate(x.end_date_fa||x.end_date)+'</td><td class="v7-money">'+v7Money(x.price_delta!=null?x.price_delta:(x.resulting_price!=null?x.resulting_price:x.legacy_price))+'</td><td><span class="v7-archived-chip">بایگانی‌شده</span></td><td><div class="v7-actions">'+actions+'</div></td></tr>';
    }
    if(v7CanEditExtension(x))actions+='<button class="v7-mini" onclick="v7OpenExtension('+x.id+')">✏ ویرایش</button>';if(can('extensions.manage')&&['draft','rejected'].indexOf(x.internal_status)>=0)actions+='<button class="v7-mini primary" onclick="v7ExtensionSubmit('+x.id+')">ارسال برای مدیر</button>';
    if(v7CanApproveExtension()&&x.internal_status==='pending')actions+='<button class="v7-mini primary" onclick="v7Decision(\'extension\','+x.id+',\'approve\')">تایید</button><button class="v7-mini danger" onclick="v7Decision(\'extension\','+x.id+',\'reject\')">رد</button>';
    if(can('extensions.archive'))actions+='<button class="v7-mini danger" onclick="v7ArchiveExtension('+x.id+')">بایگانی</button>';
    var money=x.price_delta!=null?x.price_delta:(x.resulting_price!=null?x.resulting_price:x.legacy_price),moneyNote=(x.price_delta==null&&x.resulting_price==null&&x.legacy_price!=null)?'<br><small class="v7-muted">نیازمند تعیین نوع مبلغ</small>':'';
    return '<tr><td><b>'+escHtml(x.contract_title)+'</b><br><small>'+escHtml(x.contract_number||'')+'</small>'+(x.team_names?'<br><span class="v8-team-badge">'+escHtml(x.team_names)+'</span>':'')+'</td><td><b>'+escHtml(x.title)+'</b><br><small>'+escHtml(x.extension_number||'بدون شماره')+' · '+v7FaDate(x.extension_date_fa||x.extension_date)+'</small></td><td>'+escHtml(x.extension_type_name||'—')+'</td><td>'+v7FaDate(x.end_date_fa||x.end_date)+'</td><td class="v7-money">'+v7Money(money)+moneyNote+'</td><td>'+v7StatusChip(x.internal_status)+'</td><td><div class="v7-actions">'+actions+'</div></td></tr>';
  }).join('')+'</tbody></table></div>';});
}
async function v7OpenExtension(id){
  if(!can('extensions.manage'))return toast('دسترسی ثبت یا ویرایش الحاقیه را ندارید','err');await v7LoadLookups();if(!V7.contracts.length)await v7LoadContracts(true);var x=id?V7.extensions.find(function(a){return a.id===id;}):null;if(x&&!v7CanEditExtension(x))return toast('مجوز ویرایش الحاقیه در این وضعیت را ندارید','err');if(x&&['draft','rejected'].indexOf(x.internal_status)<0&&!confirm('ویرایش این الحاقیه، وضعیت آن را به پیش‌نویس برمی‌گرداند و تأیید قبلی باید دوباره انجام شود. ادامه می‌دهید؟'))return;V7.currentEntity=x||{id:null};
  v7FillContractSelects();g('v7e-contract').value=(x&&x.contract_id)||(V7.currentContract||g('v7-extension-contract').value)||'';sOpts('v7e-type','— نوع —',V7.lookups.extension_types||[],'id','name');g('v7e-type').value=x&&x.extension_type_id||'';
  [['v7e-title','title'],['v7e-number','extension_number'],['v7e-letter','letter_number'],['v7e-date-fa','extension_date_fa'],['v7e-start-fa','start_date_fa'],['v7e-end-fa','end_date_fa']].forEach(function(a){g(a[0]).value=x&&x[a[1]]||'';});g('v7e-price-mode').value=x&&x.price_mode||'delta';g('v7e-price').value=x?(x.price_mode==='final_snapshot'?(x.resulting_price||x.legacy_price||''):(x.price_delta||x.legacy_price||'')):'';v7FormatMoneyInput(g('v7e-price'));v7ExtensionPriceMode();v71CloseMore();openM('v7-m-extension');
}
function v7ExtensionPriceMode(){var m=g('v7e-price-mode').value;g('v7e-price-label').textContent=m==='final_snapshot'?'مبلغ نهایی قرارداد بعد از الحاقیه':'مبلغ افزایش/کاهش';g('v7e-price').disabled=m==='none';}
async function v7SaveExtension(){
  var x=V7.currentEntity||{},mode=g('v7e-price-mode').value,body={id:x.id,contract_id:g('v7e-contract').value,title:g('v7e-title').value.trim(),extension_type_id:g('v7e-type').value,extension_number:g('v7e-number').value.trim(),letter_number:g('v7e-letter').value.trim(),extension_date_fa:g('v7e-date-fa').value,extension_date:v7IsoFromJalali(g('v7e-date-fa').value),start_date_fa:g('v7e-start-fa').value,start_date:v7IsoFromJalali(g('v7e-start-fa').value),end_date_fa:g('v7e-end-fa').value,end_date:v7IsoFromJalali(g('v7e-end-fa').value),price_mode:mode,price_delta:mode==='delta'?v7Num(g('v7e-price').value):null,resulting_price:mode==='final_snapshot'?v7Num(g('v7e-price').value):null};
  var r=await api('/extension_save',body);if(!r.ok)return toast(r.error,'err');closeM('v7-m-extension');await v7LoadExtensions(g('v7-extension-contract').value);await v7LoadContracts(true);toast('الحاقیه به صورت پیش‌نویس ذخیره شد','ok');
}
async function v7ExtensionSubmit(id){if(!confirm('برای تایید مدیر ارسال شود؟'))return;var r=await api('/extension_submit',{id:id});if(!r.ok)return toast(r.error,'err');await v7LoadExtensions(g('v7-extension-contract').value);toast('ارسال شد','ok');}
async function v7ArchiveExtension(id){if(!can('extensions.archive'))return toast('دسترسی بایگانی الحاقیه را ندارید','err');if(!confirm('الحاقیه بایگانی شود؟'))return;var r=await api('/extension_archive',{id:id});if(!r.ok)return toast(r.error,'err');await v7LoadExtensions(g('v7-extension-contract').value);await v7LoadContracts(true);toast('الحاقیه بایگانی شد','ok');}

async function v7LoadStatements(contractId){
  if(!can('statements.view'))return;await v7LoadLookups();if(!V7.contracts.length)await v7LoadContracts(true);var r=await api('/statements',{contract_id:contractId||null,archived:v7ArchiveOn('statement')});if(!r.ok)return toast(r.error,'err');V7.statements=r.rows||[];v7FillContractSelects();g('v7-statement-contract').value=contractId?String(contractId):'';v7RenderStatements();
}
function v7RenderStatements(){
  var box=g('v7-statements');if(!box)return;var q=(g('v7-statement-search').value||'').toLowerCase();var rows=V7.statements.filter(function(x){return !q||[x.title,x.statement_number,x.contract_title,x.letter_number].join(' ').toLowerCase().indexOf(q)>=0;});
  box.innerHTML=v7GroupRows(rows,function(arr){return '<div class="v7-table-wrap"><table class="v7-table"><thead><tr><th>قرارداد</th><th>صورت‌وضعیت</th><th>دوره</th><th>مبلغ ارسالی</th><th>مبلغ تاییدشده</th><th>وضعیت</th><th>عملیات</th></tr></thead><tbody>'+arr.map(function(x){
    var actions=can('attachments.view')?'<button class="v7-mini" onclick="v7OpenFiles(\'statement\','+x.id+',\'صورت‌وضعیت\')">📎 فایل</button>':'';
    if(v7ArchiveOn('statement')){
      if(can('archives.restore')&&can('statements.archive'))actions+='<button class="v7-mini primary" onclick="v7RestoreRecord(\'statement\','+x.id+')">↩ بازگردانی</button>';
      return '<tr class="v7-archived-row"><td><b>'+escHtml(x.contract_title)+'</b><br><small>'+escHtml(x.contract_number||'')+'</small></td><td><b>'+escHtml(x.title)+'</b><br><small>'+escHtml(x.statement_number||'بدون شماره')+'</small></td><td>'+toFaDigits(x.period_year||'')+'/'+toFaDigits(x.period_month||'')+'</td><td class="v7-money">'+v7Money(x.requested_without_vat||x.requested_price)+'</td><td class="v7-money">'+v7Money(x.confirmed_without_vat||x.confirmed_price)+'</td><td><span class="v7-archived-chip">بایگانی‌شده</span></td><td><div class="v7-actions">'+actions+'</div></td></tr>';
    }
    if(typeof v8CanAdjustStatementTeams==='function'&&v8CanAdjustStatementTeams())actions+='<button class="v7-mini" onclick="v8OpenStatementTeams('+x.id+')">👥 تقسیم تیمی</button>';
    if(v7CanEditStatement(x))actions+='<button class="v7-mini" onclick="v7OpenStatement('+x.id+')">✏ ویرایش</button>';if(can('statements.manage')&&['draft','internal_rejected'].indexOf(x.business_status)>=0)actions+='<button class="v7-mini primary" onclick="v7StatementSubmit('+x.id+')">ارسال برای مدیر</button>';
    if(v7CanApproveStatement()&&x.business_status==='pending_internal')actions+='<button class="v7-mini primary" onclick="v7Decision(\'statement_internal\','+x.id+',\'approve\')">تایید داخلی</button><button class="v7-mini danger" onclick="v7Decision(\'statement_internal\','+x.id+',\'reject\')">رد داخلی</button>';
    if(v7CanRecordEmployer()&&x.business_status==='internal_approved')actions+='<button class="v7-mini primary" onclick="v7StatementSent('+x.id+')">ثبت ارسال</button>';
    if(v7CanRecordEmployer()&&x.business_status==='sent')actions+='<button class="v7-mini primary" onclick="v7Decision(\'statement_employer\','+x.id+',\'approve\')">تأییدیه کارفرما</button>';
    if(can('statements.manage')&&x.business_status==='employer_rejected')actions+='<button class="v7-mini" onclick="v7StatementRevision('+x.id+')">نسخه اصلاحی</button>';
    if(can('statements.archive'))actions+='<button class="v7-mini danger" onclick="v7ArchiveStatement('+x.id+')">بایگانی</button>';
    return '<tr><td><b>'+escHtml(x.contract_title)+'</b><br><small>'+escHtml(x.contract_number||'')+'</small>'+((x.team_names||x.team_name)?'<br><span class="v8-team-badge">'+escHtml(x.team_names||x.team_name)+'</span>':'')+'</td><td><b>'+escHtml(x.title)+'</b><br><small>'+escHtml(x.statement_type_name||'')+' · '+escHtml(x.statement_number)+'</small></td><td>'+toFaDigits(x.period_year||'—')+' / '+toFaDigits(x.period_month||'—')+'</td><td class="v7-money">'+v7Money(x.requested_without_vat!=null?x.requested_without_vat:x.requested_price)+'</td><td class="v7-money">'+v7Money(x.confirmed_without_vat!=null?x.confirmed_without_vat:x.confirmed_price)+'</td><td>'+v7StatusChip(x.business_status)+'</td><td><div class="v7-actions">'+actions+'</div></td></tr>';
  }).join('')+'</tbody></table></div>';});
}

async function v7OpenStatement(id){
  if(!can('statements.manage'))return toast('دسترسی ثبت یا ویرایش صورت‌وضعیت را ندارید','err');await v7LoadLookups();if(!V7.contracts.length)await v7LoadContracts(true);var x=id?V7.statements.find(function(a){return a.id===id;}):null;
  if(x&&!v7CanEditStatement(x))return toast('پس از ثبت تأییدیه کارفرما، ویرایش صورت‌وضعیت دسترسی «ویرایش در همه وضعیت‌ها» می‌خواهد.','err');
  // Editing after the employer decision voids that decision, which changes
  // approved revenue - the user has to acknowledge that before the form opens.
  if(x&&['employer_approved','employer_rejected','revised'].indexOf(x.business_status)>=0&&
     !confirm('این صورت‌وضعیت تأییدیه کارفرما دارد. با ذخیره ویرایش، تأییدیه کارفرما و تأیید داخلی پاک می‌شود، سند به پیش‌نویس برمی‌گردد و مبلغ آن از گزارش‌های تأییدشده خارج می‌شود تا چرخه تأیید دوباره انجام شود. ادامه می‌دهید؟'))return;
  V7.currentEntity=x||{id:null};v7FillContractSelects();g('v7s-contract').value=(x&&x.contract_id)||(V7.currentContract||g('v7-statement-contract').value)||'';
  sOpts('v7s-type','— نوع —',V7.lookups.statement_types||[],'id','name');g('v7s-type').value=x&&x.statement_type_id||'';g('v7s-month').innerHTML='<option value="">— ماه —</option>'+V7_MONTHS.map(function(m,i){return '<option value="'+(i+1)+'">'+m+'</option>';}).join('');
  [['v7s-title','title'],['v7s-number','statement_number'],['v7s-date-fa','statement_date_fa'],['v7s-letter','letter_number'],['v7s-start-fa','start_date_fa'],['v7s-end-fa','end_date_fa'],['v7s-year','period_year'],['v7s-month','period_month'],['v7s-requested','requested_without_vat'],['v7s-vat','requested_vat'],['v7s-vat-percent','vat_percentage_value'],['v7s-vat-factor','vat_factor_number'],['v7s-progress','progress_percentage'],['v7s-desc','description']].forEach(function(a){g(a[0]).value=x&&x[a[1]]!=null?x[a[1]]:(a[0]==='v7s-year'?g('v7-plan-year').value:'');});v7FormatMoneyInput(g('v7s-requested'));v7FormatMoneyInput(g('v7s-vat'));g('v7s-without-vat').checked=!!(x&&x.without_vat);v71CloseMore();openM('v7-m-statement');
}
async function v7SaveStatement(){
  var x=V7.currentEntity||{},without=v7Num(g('v7s-requested').value),vat=v7Num(g('v7s-vat').value),allocations=typeof v8StatementTeamEntries==='function'?v8StatementTeamEntries():[],body={id:x.id,contract_id:g('v7s-contract').value,statement_type_id:g('v7s-type').value,statement_number:g('v7s-number').value.trim(),title:g('v7s-title').value.trim(),statement_date_fa:g('v7s-date-fa').value,statement_date:v7IsoFromJalali(g('v7s-date-fa').value),letter_number:g('v7s-letter').value.trim(),start_date_fa:g('v7s-start-fa').value,start_date:v7IsoFromJalali(g('v7s-start-fa').value),end_date_fa:g('v7s-end-fa').value,end_date:v7IsoFromJalali(g('v7s-end-fa').value),period_year:g('v7s-year').value,period_month:g('v7s-month').value||null,requested_price:without==null?null:without+(vat||0),requested_without_vat:without,requested_vat:vat,vat_percentage_value:v7Num(g('v7s-vat-percent').value),vat_factor_number:g('v7s-vat-factor').value.trim(),without_vat:g('v7s-without-vat').checked,progress_percentage:g('v7s-progress').value||null,description:g('v7s-desc').value,statement_teams:allocations,project_team_id:allocations.length?allocations[0].project_team_id:null};
  var r=await api('/statement_save',body);if(!r.ok)return toast(r.error,'err');closeM('v7-m-statement');await v7LoadStatements(g('v7-statement-contract').value);toast(x.id?'تغییرات صورت‌وضعیت ذخیره شد':'صورت‌وضعیت به صورت پیش‌نویس ذخیره شد','ok');
}
async function v7StatementSubmit(id){if(!confirm('برای تایید داخلی مدیر ارسال شود؟'))return;var r=await api('/statement_submit',{id:id});if(!r.ok)return toast(r.error,'err');await v7LoadStatements(g('v7-statement-contract').value);toast('ارسال شد','ok');}
async function v7StatementSent(id){if(!confirm('ارسال این صورت‌وضعیت به کارفرما ثبت شود؟'))return;var r=await api('/statement_mark_sent',{id:id});if(!r.ok)return toast(r.error,'err');await v7LoadStatements(g('v7-statement-contract').value);await v7LoadFinancialDashboard();toast('ارسال به کارفرما ثبت شد','ok');}
async function v7StatementRevision(id){if(!confirm('نسخه اصلاحی از صورت‌وضعیت ردشده ساخته شود؟ نسخه قبلی در تاریخچه باقی می‌ماند.'))return;var r=await api('/statement_revision',{id:id});if(!r.ok)return toast(r.error,'err');await v7LoadStatements(g('v7-statement-contract').value);v7OpenStatement(r.id);}
async function v7ArchiveStatement(id){if(!can('statements.archive'))return toast('دسترسی بایگانی صورت‌وضعیت را ندارید','err');if(!confirm('صورت‌وضعیت بایگانی شود؟ سابقه حسابرسی باقی می‌ماند.'))return;var r=await api('/statement_archive',{id:id});if(!r.ok)return toast(r.error,'err');await v7LoadStatements(g('v7-statement-contract').value);await v7LoadContracts(true);toast('صورت‌وضعیت بایگانی شد','ok');}

function v7Decision(kind,id,action){
  V7.decision={kind:kind,id:id};g('v7-decision-note').value='';var employer=kind==='statement_employer';g('v7-decision-title').textContent=employer?'تأییدیه کارفرما':'تایید داخلی مدیر';
  var summary=g('v7-employer-summary');summary.style.display=employer?'block':'none';if(employer){var s=V7.statements.find(function(x){return x.id===id;})||{},base=s.requested_without_vat!=null?s.requested_without_vat:s.requested_price;summary.innerHTML='<b>'+escHtml(s.title||'صورت‌وضعیت')+'</b><span>مبلغ کامل قابل تأیید: '+v7Money(base)+'</span><small>تأیید یعنی کل مبلغ صورت‌وضعیت پذیرفته شده است. رد هیچ اثری روی مانده قرارداد ندارد.</small>';}
  var okText=employer?'تأیید کامل':'تایید',badText=employer?'رد':'رد';g('v7-decision-actions').innerHTML='<button class="btn btn-green" onclick="v7DoDecision(\'approved\')">'+okText+'</button><button class="btn btn-danger" onclick="v7DoDecision(\'rejected\')">'+badText+'</button>';openM('v7-m-decision');
}
async function v7DoDecision(decision){
  var d=V7.decision,ep=d.kind==='extension'?'/extension_decide':(d.kind==='statement_internal'?'/statement_internal_decide':'/statement_employer_decide'),body={id:d.id,decision:decision,note:g('v7-decision-note').value};var r=await api(ep,body);if(!r.ok)return toast(r.error,'err');closeM('v7-m-decision');if(d.kind==='extension'){await v7LoadExtensions(g('v7-extension-contract').value);await v7LoadContracts(true);}else{await v7LoadStatements(g('v7-statement-contract').value);await v7LoadContracts(true);await v7LoadFinancialDashboard();}toast(d.kind==='statement_employer'?(decision==='approved'?'صورت‌وضعیت به‌طور کامل تأیید شد':'صورت‌وضعیت رد شد'):'تصمیم ثبت شد','ok');
}

async function v7LoadPlan(){
  var year=Number(g('v7-plan-year').value)||1405;var r=await api('/financial_plan',{year:year});if(!r.ok)return toast(r.error,'err');V7.planData=r;V7.plan=r.plan||null;v7RenderPlan();v7LoadRecommendations();if(V7.plan)v71LoadPlanBreakdown();
}
function v7PlanChartsHtml(periods,actuals){
  var byTarget={},byActual={};(periods||[]).forEach(function(x){byTarget[Number(x.month_no)]=Number(x.target_amount||0);});(actuals||[]).forEach(function(x){byActual[Number(x.month_no)]={sent:Number(x.sent_amount||0),approved:Number(x.approved_amount||0)};});
  var rows=V7_MONTHS.map(function(name,i){var m=i+1,a=byActual[m]||{};return {month:m,name:name,target:Number(byTarget[m]||0),sent:Number(a.sent||0),approved:Number(a.approved||0)};}),max=Math.max.apply(null,rows.reduce(function(a,x){return a.concat([x.target,x.sent,x.approved]);},[1]));
  var bars=rows.map(function(x){function h(v){return Math.max(v?5:0,Math.round(v/max*145));}return '<div class="v7-plan-chart-month"><div class="v7-plan-chart-bars"><i class="target" style="height:'+h(x.target)+'px" title="هدف: '+v7Money(x.target)+'"></i><i class="sent" style="height:'+h(x.sent)+'px" title="ارسال: '+v7Money(x.sent)+'"></i><i class="approved" style="height:'+h(x.approved)+'px" title="تایید: '+v7Money(x.approved)+'"></i></div><small>'+x.name.slice(0,3)+'</small></div>';}).join('');
  var cumTarget=0,cumApproved=0,targetPts=[],approvedPts=[],w=720,h=220,pad=28,cumMax=1;rows.forEach(function(x){cumTarget+=x.target;cumApproved+=x.approved;cumMax=Math.max(cumMax,cumTarget,cumApproved);targetPts.push(cumTarget);approvedPts.push(cumApproved);});
  function points(values){return values.map(function(v,i){var x=pad+i*((w-pad*2)/11),y=h-pad-(v/cumMax)*(h-pad*2);return x.toFixed(1)+','+y.toFixed(1);}).join(' ');}
  var dots=approvedPts.map(function(v,i){var x=pad+i*((w-pad*2)/11),y=h-pad-(v/cumMax)*(h-pad*2);return '<circle cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="3"><title>'+V7_MONTHS[i]+' · '+v7Money(v)+'</title></circle>';}).join('');
  return '<div class="v7-plan-charts"><section class="v7-plan-chart-card"><div class="v7-plan-chart-head"><b>نمودار ماهانه هدف و عملکرد</b><span class="v7-plan-legend"><em class="target"></em>هدف <em class="sent"></em>ارسال <em class="approved"></em>تایید</span></div><div class="v7-plan-bar-chart">'+bars+'</div></section><section class="v7-plan-chart-card"><div class="v7-plan-chart-head"><b>روند تجمعی تحقق هدف</b><span class="v7-plan-legend"><em class="target-line"></em>هدف تجمعی <em class="approved-line"></em>تایید تجمعی</span></div><svg class="v7-plan-line-chart" viewBox="0 0 '+w+' '+h+'" role="img" aria-label="روند تجمعی هدف و تایید"><line x1="'+pad+'" y1="'+(h-pad)+'" x2="'+(w-pad)+'" y2="'+(h-pad)+'" class="axis"></line><polyline class="target-line" points="'+points(targetPts)+'"></polyline><polyline class="approved-line" points="'+points(approvedPts)+'"></polyline><g class="approved-dots">'+dots+'</g></svg></section></div>';
}
function v7RenderPlan(){
  var d=V7.planData||{},plan=d.plan,periods=d.periods||[],actualMap={};(d.actuals||[]).forEach(function(x){actualMap[x.month_no]=x;});
  var annual=Number(plan&&plan.annual_target||0),target=periods.reduce(function(s,x){return s+Number(x.target_amount||0);},0),sent=(d.actuals||[]).reduce(function(s,x){return s+Number(x.sent_amount||0);},0),approved=(d.actuals||[]).reduce(function(s,x){return s+Number(x.approved_amount||0);},0),pct=annual?Math.min(100,Math.round(approved/annual*100)):0;
  // The annual figure and the monthly split are both rolled up from the team
  // goals now, so this page reports them and sends editing to «اهداف مالی».
  g('v7-plan-summary').innerHTML='<div class="v7-grid"><div class="v7-kpi"><div class="label">هدف سالانه شرکت</div><div class="value">'+v7Money(annual)+'</div><div class="sub">جمع اهداف تیم‌ها</div></div><div class="v7-kpi"><div class="label">هدف تخصیص‌یافته ماهانه</div><div class="value">'+v7Money(target)+'</div><div class="sub">جمع تقسیم ماهانه تیم‌ها</div></div><div class="v7-kpi"><div class="label">ارسال‌شده به کارفرما</div><div class="value">'+v7Money(sent)+'</div></div><div class="v7-kpi"><div class="label">تایید کارفرما</div><div class="value">'+v7Money(approved)+'</div><div class="v7-progress"><i style="width:'+pct+'%"></i></div><div class="sub">'+toFaDigits(pct)+'٪ هدف سالانه</div></div></div>';
  g('v7-plan-charts').innerHTML=plan?v7PlanChartsHtml(periods,d.actuals||[]):'';
  if(!plan){g('v7-months').innerHTML='<div class="v7-empty">برای این سال هنوز هدفی ثبت نشده است. هدف هر تیم را در صفحه «اهداف مالی» ثبت کنید.</div>';g('v7-planned-list').innerHTML='';return;}
  var byMonth={};periods.forEach(function(x){byMonth[x.month_no]=x;});
  var quarters=['بهار','تابستان','پاییز','زمستان'].map(function(name,q){var qt=0,qs=0,qa=0;for(var m=q*3+1;m<=q*3+3;m++){qt+=Number((byMonth[m]||{}).target_amount||0);qs+=Number((actualMap[m]||{}).sent_amount||0);qa+=Number((actualMap[m]||{}).approved_amount||0);}return '<div class="v7-kpi"><div class="label">فصل '+name+'</div><div class="value">'+v7Money(qt)+'</div><div class="sub">ارسال '+v7Money(qs)+' · تایید '+v7Money(qa)+'</div></div>';}).join('');
  g('v7-months').innerHTML='<div class="v7-grid" style="margin-top:12px">'+quarters+'</div><div class="v7-month-grid">'+V7_MONTHS.map(function(name,i){var m=i+1,x=byMonth[m]||{month_no:m,target_amount:0},a=actualMap[m]||{},t=Number(x.target_amount||0),sp=t?Math.min(100,Math.round(Number(a.sent_amount||0)/t*100)):0,ap=t?Math.min(100,Math.round(Number(a.approved_amount||0)/t*100)):0;return '<div class="v7-month"><div class="v7-month-title"><span>'+name+'</span><span class="v7-month-target">'+v7Money(t)+'</span></div><div class="month-bars"><span>ارسال '+v7Money(a.sent_amount||0)+'</span><div class="bar"><i style="width:'+sp+'%"></i></div><span>تایید '+v7Money(a.approved_amount||0)+'</span><div class="bar approved"><i style="width:'+ap+'%"></i></div></div></div>';}).join('')+'</div>'+(v7CanPlan()?'<div class="v7-info-strip">تقسیم ماهانه شرکت از جمع تقسیم ماهانه تیم‌ها ساخته می‌شود. برای تغییر، هدف همان تیم را در صفحه «اهداف مالی» ویرایش کنید. <button class="v7-mini primary" onclick="showPage(25)">رفتن به اهداف مالی</button></div>':'');
  var planned=d.planned||[];g('v7-planned-list').innerHTML='<section class="v7-group"><div class="v7-group-head">📅 برنامه‌های صورت‌وضعیت<small>'+toFaDigits(planned.length)+' مورد</small></div>'+(planned.length?'<div class="v7-table-wrap"><table class="v7-table"><thead><tr><th>ماه</th><th>قرارداد</th><th>عنوان</th><th>مبلغ برنامه</th><th>تسک مرتبط</th><th>وضعیت</th><th>عملیات</th></tr></thead><tbody>'+planned.map(function(x){var actions=v7CanPlan()?'<button class="v7-mini" onclick="v7OpenPlanned('+x.id+')">ویرایش</button><button class="v7-mini danger" onclick="v7ArchivePlanned('+x.id+')">بایگانی</button>':'';return '<tr><td>'+V7_MONTHS[(x.month_no||1)-1]+'</td><td>'+escHtml(x.contract_title)+'</td><td>'+escHtml(x.title)+'</td><td class="v7-money">'+v7Money(x.planned_amount)+'</td><td>'+toFaDigits(x.task_count||0)+'</td><td>'+escHtml(x.status||'planned')+'</td><td><div class="v7-actions">'+actions+'</div></td></tr>';}).join('')+'</tbody></table></div>':'<div class="v7-empty">برنامه‌ای ثبت نشده است.</div>')+'</section>';
}

function v7OpenPlan(){showPage(25);}
async function v7SavePlan(){showPage(25);}

function v7RenderPlannedTasks(selected){var cid=g('v7ps-contract').value,team=g('v8-planned-team')&&g('v8-planned-team').value;selected=selected||[];var tasks=(D.t||[]).filter(function(t){return (!t.contract_id||String(t.contract_id)===String(cid))&&(!team||!t.project_team_id||String(t.project_team_id)===String(team));});g('v7ps-tasks').innerHTML=tasks.map(function(t){return '<label class="v7-file-row"><input type="checkbox" value="'+t.id+'" '+(selected.indexOf(t.id)>=0?'checked':'')+'><span><b>'+escHtml(t.title)+'</b><br><small>'+escHtml(t.pname||'')+(t.team_name?' · '+escHtml(t.team_name):'')+'</small></span></label>';}).join('')||'<span class="v7-muted">برای این قرارداد و تیم، تسک قابل پیوندی وجود ندارد.</span>';}
function v7OpenPlanned(id){
  if(!v7CanPlan())return;if(!V7.plan)return toast('ابتدا هدف سالانه را بسازید','err');var x=id?((V7.planData&&V7.planData.planned)||[]).find(function(p){return p.id===id;}):null;V7.currentPlanned=x||null;v7FillContractSelects();g('v7ps-contract').value=x&&x.contract_id||'';g('v7ps-month').innerHTML=V7_MONTHS.map(function(n,i){return '<option value="'+(i+1)+'">'+n+'</option>';}).join('');g('v7ps-month').value=x&&x.month_no||1;sOpts('v7ps-type','— نوع —',V7.lookups.statement_types||[],'id','name');g('v7ps-type').value=x&&x.statement_type_id||'';g('v7ps-title').value=x&&x.title||'';g('v7ps-amount').value=x&&x.planned_amount||'';v7FormatMoneyInput(g('v7ps-amount'));g('v7ps-date-fa').value=x&&x.planned_date_fa||'';g('v7ps-note').value=x&&x.note||'';v7RenderPlannedTasks(x&&x.task_ids||[]);openM('v7-m-planned');
}
async function v7SavePlanned(){var r=await api('/planned_statement_save',{id:V7.currentPlanned&&V7.currentPlanned.id,plan_id:V7.plan.id,contract_id:g('v7ps-contract').value,month_no:g('v7ps-month').value,statement_type_id:g('v7ps-type').value||null,title:g('v7ps-title').value,planned_amount:v7Num(g('v7ps-amount').value),planned_date_fa:g('v7ps-date-fa').value,planned_date:v7IsoFromJalali(g('v7ps-date-fa').value),note:g('v7ps-note').value,project_team_id:g('v8-planned-team')&&g('v8-planned-team').value||null});if(!r.ok)return toast(r.error,'err');var ids=Array.from(g('v7ps-tasks').querySelectorAll('input:checked')).map(function(x){return Number(x.value);});var lr=await api('/planned_statement_link_tasks',{planned_statement_id:r.id,task_ids:ids});if(!lr.ok)return toast(lr.error,'err');closeM('v7-m-planned');await v7LoadPlan();await loadAll({silent:true});toast('برنامه صورت‌وضعیت ذخیره شد','ok');}
async function v7ArchivePlanned(id){if(!confirm('این برنامه بایگانی و پیوندش از تسک‌ها برداشته شود؟'))return;var r=await api('/planned_statement_archive',{id:id});if(!r.ok)return toast(r.error,'err');await v7LoadPlan();await loadAll({silent:true});toast('برنامه بایگانی شد','ok');}

async function v7LoadRecommendations(){
  var box=g('v7-recommendations');if(!box)return;var r=await api('/contract_recommendations',{});if(!r.ok)return;
  function rows(a,critical){return (a||[]).slice(0,12).map(function(x){var remaining=x.requires_team_allocation?'سهم ریالی تیم تعیین نشده (مانده کل شرکت: '+v7Money(x.company_remaining_price)+')':v7Money(x.remaining_price),burn=x.requires_team_allocation?'پس از تعیین سهم تیم محاسبه می‌شود':v7Money(x.required_monthly_burn||0);return '<div class="v7-alert-row"><b>'+escHtml(x.title)+'</b><br><span>'+escHtml(x.city_name||'بدون شهر')+' / '+escHtml(x.project_name||'بدون پروژه')+'</span><br><span>مانده: '+remaining+' · '+(x.days_to_end==null?'بدون تاریخ پایان':(toFaDigits(x.days_to_end)+' روز تا پایان'))+'</span>'+(critical?'':'<br><span>خوش‌حسابی: '+v7RatingText(x.payer_rating)+' · تسک آماده: '+toFaDigits(x.ready_task_count||0)+' · کار باز: '+toFaDigits(x.open_task_count||0)+'</span><br><span>نیاز ماهانه تقریبی: '+burn+' · آخرین صورت‌وضعیت: '+v7FaDate(x.last_statement_date)+'</span>')+'</div>';}).join('')||'<div class="v7-empty">موردی نیست.</div>';}
  box.innerHTML='<div class="v7-alerts"><div class="v7-alert-box"><h3 style="color:var(--coral)">🚨 هشدارهای بحرانی مستقل از خوش‌حسابی</h3>'+rows(r.critical_alerts,true)+'</div><div class="v7-alert-box"><h3 style="color:var(--sky)">💡 پیشنهاد برنامه‌ریزی (اولویت با خوش‌حسابی)</h3>'+rows(r.rows,false)+'</div></div>';
}

function v7CanWriteTaskFile(id){if(!CU)return false;if(!can('attachments.upload'))return false;if(can('tasks.edit'))return true;var t=(D.t||[]).find(function(x){return x.id===id;});if(!t)return false;if(can('tasks.work')&&isOnTask(t,CU.id))return true;return can('tasks.self_manage')&&t.created_by===CU.id&&t.project_id===CU.project_id;}
async function v7OpenFiles(type,id,title){if(!can('attachments.view'))return toast('دسترسی مشاهده فایل‌ها را ندارید','err');V7.currentFileEntity={type:type,id:id};g('v7-files-title').textContent='فایل‌های '+title;g('v7-file-input').accept=type==='task'?'image/jpeg,image/png,image/webp':'.pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png,.webp';g('v7-file-upload').style.display=(type==='task'?v7CanWriteTaskFile(id):can('attachments.upload'))?'':'none';openM('v7-m-files');await v7LoadFiles();}
async function v7LoadFiles(){if(!can('attachments.view'))return;var e=V7.currentFileEntity,r=await api('/attachments',{entity_type:e.type,entity_id:e.id});if(!r.ok){g('v7-files-list').innerHTML='<div class="v7-empty">'+escHtml(r.error)+'</div>';return;}V7.attachments=r.rows||[];var canEdit=can('attachments.edit'),canArchive=can('attachments.archive');g('v7-files-list').innerHTML=V7.attachments.map(function(x){var preview=x.has_thumbnail?'<img data-attachment="'+x.id+'" alt="تصویر">':'<span style="font-size:28px">📄</span>',controls=canEdit?'<button class="v7-mini" onclick="v7EditFileCaption('+x.id+')">توضیح</button><button class="v7-mini" onclick="v7MoveFile('+x.id+',-1)">↑</button><button class="v7-mini" onclick="v7MoveFile('+x.id+',1)">↓</button>':'';if(canArchive)controls+='<button class="v7-mini danger" onclick="v7ArchiveFile('+x.id+')">حذف</button>';return '<div class="v7-file-row">'+preview+'<div class="v7-file-info"><div class="v7-file-name">'+escHtml(x.original_name)+'</div><small class="v7-muted">'+escHtml(x.caption||'بدون توضیح')+' · '+v7Money(x.size_bytes)+' بایت · نسخه '+toFaDigits(x.version_no)+'</small></div>'+controls+'<button class="v7-mini primary" onclick="v7DownloadFile('+x.id+')">دانلود</button></div>';}).join('')||'<div class="v7-empty">فایلی ثبت نشده است.</div>';g('v7-files-list').querySelectorAll('img[data-attachment]').forEach(function(img){v7FetchFile(Number(img.dataset.attachment),true).then(function(url){img.src=url;});});}
async function v7UploadRaw(type,id,file,caption){var fd=new FormData();fd.append('entity_type',type);fd.append('entity_id',id);fd.append('caption',caption||'');fd.append('file',file);var headers={};if(TOKEN)headers['X-Token']=TOKEN;try{var res=await fetch('/api/attachment_upload',{method:'POST',headers:headers,body:fd});return await res.json();}catch(e){return {ok:false,error:e.message};}}
async function v7UploadFile(){var f=g('v7-file-input').files[0];if(!f)return toast('فایل را انتخاب کنید','err');var e=V7.currentFileEntity,r=await v7UploadRaw(e.type,e.id,f,g('v7-file-caption').value);if(!r.ok)return toast(r.error,'err');g('v7-file-input').value='';g('v7-file-caption').value='';await v7LoadFiles();toast(r.deduplicated?'فایل با استفاده از نسخه موجود ثبت شد':'فایل بارگذاری و بهینه شد','ok');}
async function v7FetchFile(id,thumb){var headers={};if(TOKEN)headers['X-Token']=TOKEN;var r=await fetch('/api/attachment_download/'+id+(thumb?'?thumb=1':''),{headers:headers});if(!r.ok)throw new Error('download');var b=await r.blob();return URL.createObjectURL(b);}
async function v7DownloadFile(id){try{var f=(V7.attachments||[]).find(function(x){return x.id===id;})||{},url=await v7FetchFile(id,false),a=document.createElement('a');a.href=url;a.download=f.original_name||'file';document.body.appendChild(a);a.click();a.remove();setTimeout(function(){URL.revokeObjectURL(url);},1000);}catch(e){toast('دریافت فایل ناموفق بود','err');}}
async function v7ArchiveFile(id){if(!can('attachments.archive'))return toast('دسترسی بایگانی فایل را ندارید','err');if(!confirm('فایل از فهرست فعال حذف شود؟ نسخه فیزیکی برای بازیابی باقی می‌ماند.'))return;var r=await api('/attachment_archive',{id:id});if(!r.ok)return toast(r.error,'err');await v7LoadFiles();}
async function v7EditFileCaption(id){if(!can('attachments.edit'))return toast('دسترسی ویرایش فایل را ندارید','err');var f=(V7.attachments||[]).find(function(x){return x.id===id;})||{},value=prompt('توضیح فایل:',f.caption||'');if(value===null)return;var r=await api('/attachment_update',{id:id,caption:value});if(!r.ok)return toast(r.error,'err');await v7LoadFiles();}
async function v7MoveFile(id,move){if(!can('attachments.edit'))return toast('دسترسی ویرایش فایل را ندارید','err');var r=await api('/attachment_update',{id:id,move:move});if(!r.ok)return toast(r.error,'err');await v7LoadFiles();}
async function v7AppendTaskFiles(id){if(!can('attachments.view'))return;var box=g('tvb');if(!box)return;var holder=document.createElement('div');holder.className='hlp-card';holder.style.marginTop='12px';holder.innerHTML='<h3>📷 تصاویر و فایل‌های تسک</h3><button class="v7-mini primary" onclick="v7OpenFiles(\'task\','+id+',\'تسک\')">مشاهده / افزودن تصاویر</button>';box.appendChild(holder);}

async function v7Export(kind,format){var headers={'Content-Type':'application/json'};if(TOKEN)headers['X-Token']=TOKEN;var r=await fetch('/api/v7_export',{method:'POST',headers:headers,body:JSON.stringify({kind:kind,format:format,contract_id:kind==='extensions'?g('v7-extension-contract').value:(kind==='statements'?g('v7-statement-contract').value:null)})});if(!r.ok)return toast('خروجی ناموفق بود','err');var b=await r.blob(),url=URL.createObjectURL(b),a=document.createElement('a');a.href=url;a.download='TaskHub_'+kind+'.'+format;document.body.appendChild(a);a.click();a.remove();setTimeout(function(){URL.revokeObjectURL(url);},1000);}

async function v7LoadActiveSessions(){
  var box=g('active-sessions-box');if(!box)return;box.innerHTML='<span class="v7-muted">در حال دریافت...</span>';var r=await api('/active_sessions',{});if(!r.ok){box.textContent=r.error||'خطا';return;}if(!r.rows.length){box.innerHTML='<span class="v7-muted">نشست فعالی وجود ندارد.</span>';return;}
  box.innerHTML=r.rows.map(function(x){var details=(x.sessions||[]).map(function(s,i){return '<div class="v7-file-row"><div class="v7-file-info"><b>دستگاه '+toFaDigits(i+1)+'</b><br><small dir="ltr">IP: '+escHtml(s.ip_address||'—')+' · last: '+escHtml(s.last_seen||s.created_at||'—')+'</small><br><small class="v7-muted">'+escHtml(s.device||'مرورگر نامشخص')+'</small></div><button class="v7-mini danger" onclick="v7RevokeSession('+x.user_id+',\''+s.session_key+'\')">بستن همین نشست</button></div>';}).join('');return '<details class="v7-group"><summary class="v7-group-head" style="cursor:pointer"><span><b>'+escHtml(x.display_name||x.username)+'</b> · '+escHtml(v7RoleLabel(x.role))+'</span><small>'+toFaDigits(x.session_count)+' نشست · آخرین فعالیت '+escHtml(x.last_seen||'—')+'</small><button class="v7-mini danger" onclick="event.preventDefault();event.stopPropagation();v7RevokeSession('+x.user_id+',null)">بستن همه</button></summary>'+details+'</details>';}).join('');
}
async function v7RevokeSession(userId,key){if(!confirm(key?'همین نشست بسته شود؟':'همه نشست‌های این کاربر بسته شود؟'))return;var r=await api('/session_revoke',{user_id:userId,session_key:key||null});toast(r.ok?toFaDigits(r.count||0)+' نشست بسته شد':r.error,r.ok?'ok':'err');if(r.ok)v7LoadActiveSessions();}

async function v7LoadBackups(){
  var box=g('v7-backup-list');if(!box)return;var r=await api('/backups',{}),s=await api('/storage_stats',{});if(s.ok&&g('v7-storage-stats'))g('v7-storage-stats').innerHTML='<div class="v7-chip">فضای فیزیکی فایل‌ها: '+v7Money(s.physical_bytes)+' بایت · '+toFaDigits(s.attachment_count||0)+' پیوند روی '+toFaDigits(s.blob_count||0)+' فایل یکتا</div>';
  if(!r.ok){box.textContent=r.error;return;}box.innerHTML=(r.rows||[]).map(function(x){return '<div class="v7-file-row"><span style="font-size:24px">🛡</span><div class="v7-file-info"><b>'+escHtml(x.name)+'</b><br><small>'+escHtml(x.kind||'')+' · '+escHtml(x.created_at||'')+' · '+v7Money(x.size_bytes)+' بایت</small></div><button class="v7-mini" onclick="v7VerifyBackup(\''+x.name+'\')">بررسی صحت</button><button class="v7-mini primary" onclick="v7DownloadBackup(\''+x.name+'\')">دانلود</button></div>';}).join('')||'<div class="v7-empty">هنوز نقطه بازیابی ساخته نشده است.</div>';
}
async function v7RunBackup(full){if(!confirm((full?'پشتیبان FULL':'پشتیبان دوره‌ای')+' ساخته شود؟ ممکن است چند دقیقه طول بکشد.'))return;toast('ساخت پشتیبان شروع شد؛ فایل‌ها موقتاً قفل می‌شوند','inf');var r=await api('/backup_run',{full:full});toast(r.ok?'نقطه بازیابی تاییدشده ساخته شد: '+r.name:r.error,r.ok?'ok':'err');if(r.ok)v7LoadBackups();}
async function v7VerifyBackup(name){var r=await api('/backup_verify',{name:name});toast(r.ok&&r.valid?'صحت آرشیو و همه هش‌ها تایید شد':((r.errors||[]).join('، ')||r.error),(r.ok&&r.valid)?'ok':'err');}
async function v7DownloadBackup(name){var headers={};if(TOKEN)headers['X-Token']=TOKEN;var r=await fetch('/api/backup_download/'+encodeURIComponent(name),{headers:headers});if(!r.ok)return toast('دانلود ناموفق بود','err');var b=await r.blob(),url=URL.createObjectURL(b),a=document.createElement('a');a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(function(){URL.revokeObjectURL(url);},1000);}
