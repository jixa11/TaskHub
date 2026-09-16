/* global api,g,escHtml,toFaDigits,toEnDigits,D,CU,TOKEN,PML,openM,closeM,toast,sOpts,showPage,loadAll,applyRole,prepM,eTask,tkPC,v7Money,v7Num,v7Selected,V7,V7_MONTHS,v7LoadContracts,v7LoadStatements,v7LoadPlan,v7FaDate,openDP */
'use strict';

var V8={
  context:{teams:[],project_teams:[],can_all_teams:false},
  scope:'mine',teams:[],currentTeam:null,currentReport:'dashboard',
  teamPlan:null,chat:{mode:null,device:null,conversations:[],current:null,messages:[],keys:{},initializing:false,rotating:false,polling:false,lastError:null,
   hasMore:false,loadingOlder:false,stickBottom:true,unreadTotal:0,lastAlertId:0,unreadSeeded:false,unreadTimer:null,unreadBusy:false}
};

function v8Money(v){return typeof v7Money==='function'?v7Money(v):(v==null?'—':toFaDigits(Number(v).toLocaleString('en-US')));}
function v8RoleFa(v){return {manager:'مدیر تیم',planner:'پلنر تیم',member:'عضو'}[v]||v;}
function v8FmtSeconds(v){var s=Number(v||0),h=Math.floor(s/3600),m=Math.floor((s%3600)/60);return toFaDigits(h)+' ساعت و '+toFaDigits(m)+' دقیقه';}
function v8ScopePayload(){return {_team_scope:V8.scope||'mine'};}
function v8CanManageTeam(t){return !!(CU&&can('teams.edit'));}
function v8CanPlanTeam(teamId){return !!(CU&&can('team_financial.manage'));}

function v8NormalizeText(v){return String(v||'').replace(/\s+/g,' ').trim();}
function v8RenderTopbarUser(){
  var chip=g('topbar-user');if(!chip||!CU)return;
  var role=v8RoleFaGlobal(CU.role),position=v8NormalizeText(CU.position),display=v8NormalizeText(CU.display_name),username=v8NormalizeText(CU.username);
  var primary=display&&display!==position&&display!==role?display:(username||display||role||'کاربر');
  var secondary=position&&position!==primary?position:(role&&role!==primary?role:(username&&username!==primary?'@'+username:'حساب کاربری'));
  chip.innerHTML='<div class="v8-user-chip"><div class="v8-user-avatar">'+escHtml((primary||'?').charAt(0))+'</div><div class="v8-user-copy"><b>'+escHtml(primary)+'</b><small>'+escHtml(secondary)+'</small></div><span class="v8-user-edit">✏</span></div>';
}
function v8RoleFaGlobal(v){return {admin:'مدیر سیستم',employer:'کارفرما',support:'پشتیبان',lead:'سرگروه',supervisor:'راهبر',reporter:'کارشناس اجرایی',finance:'کارشناس مالی',manager:'مدیر',planner:'پلنر'}[v]||v||'';}

function initV8UI(){
  var nav=document.querySelector('.s-nav');
  nav.insertAdjacentHTML('beforeend',
    '<div class="nav-item" data-pg="22" data-permission="teams.view" data-role="admin,manager,planner,finance,reporter"><span class="nav-ico">👥</span>تیم‌ها</div>'+
    '<div class="nav-item" data-pg="23" data-permission="reports.view" data-role="admin,manager,planner,finance,reporter,support"><span class="nav-ico">📈</span>گزارش‌های تیمی</div>'+
    '<div class="nav-item" data-pg="24" data-permission="chat.use" data-role="admin,manager,planner,finance,reporter,support,supervisor,employer"><span class="nav-ico">💬</span>پیامرسان<span class="nav-badge org" id="v8-chat-badge" style="display:none">0</span></div>'+
    '<div class="nav-item" data-pg="25" data-permission="financial_plan.view" data-role="admin,manager,planner,finance,reporter"><span class="nav-ico">🎯</span>اهداف مالی</div>'+
    '<div class="nav-item" data-pg="26" data-permission="access_control.manage"><span class="nav-ico">🔐</span>مدیریت دسترسی‌ها</div>'+
    '<div class="nav-item" data-pg="29" data-permission="groups.view"><span class="nav-ico">🧩</span>گروه‌ها</div>');
  var items={};nav.querySelectorAll('.nav-item[data-pg]').forEach(function(x){items[Number(x.dataset.pg)]=x;});
  if(items[1])items[1].setAttribute('data-role','admin,manager,planner,finance,reporter');
  if(items[2])items[2].setAttribute('data-role','admin,manager,planner,finance,reporter');
  if(items[5])items[5].setAttribute('data-role','admin');
  if(items[10])items[10].setAttribute('data-role','admin');
  if(items[15])items[15].setAttribute('data-role','admin');
  // pg19 keeps only the statement-planning half of the old page and is
  // labelled at its source in v7_ui.js; every goal - company and team - now
  // lives on pg25 «اهداف مالی».
  nav.querySelectorAll('.nav-sec').forEach(function(x){x.remove();});
  function section(title,roles,pages){
    var s=document.createElement('div');s.className='nav-sec';s.textContent=title;
    if(roles)s.setAttribute('data-role',roles);nav.appendChild(s);
    pages.forEach(function(i){if(items[i])nav.appendChild(items[i]);});
  }
  section('خانه','admin,employer,support,supervisor,manager,planner,reporter,finance',[0,9]);
  section('سازمان و پروژه','admin,manager,planner,finance,reporter,lead',[1,2,22,29]);
  section('تسک و برنامه کاری','admin,employer,support,supervisor,manager,planner,reporter',[5,6,13,14]);
  section('قرارداد و امور مالی','admin,manager,planner,finance,reporter',[16,17,18,19,25]);
  section('گزارش‌ها','admin,support,supervisor,manager,planner,finance,reporter',[7,8,20,21,23]);
  section('ارتباطات','admin,support,manager,planner,finance,reporter,supervisor,employer',[12,24]);
  section('سیستم','admin',[10,15,26]);
  section('راهنما','',[11]);

  g('pages').insertAdjacentHTML('beforeend',v8PagesHtml()+v8AccessControlPageHtml());
  g('toast-c').insertAdjacentHTML('beforebegin',v8ModalsHtml());
  var topUser=g('topbar-user');
  if(topUser)topUser.insertAdjacentHTML('beforebegin','<div class="v8-team-switch" id="v8-team-switch" style="display:none"><label>نمای تیم</label><select class="fi" id="v8-scope" onchange="v8ScopeChanged()"></select></div>');

  var projectRow=g('vtproj')&&g('vtproj').closest('.fr');
  if(projectRow)projectRow.insertAdjacentHTML('afterend','<div class="fr"><div class="fg"><label class="fl">تیم مسئول روی پروژه <span class="r">*</span></label><select class="fi" id="vtteam"></select><small class="v8-scope-note">برای پروژه مشترک، این انتخاب مانع تداخل گزارش دو تیم می‌شود.</small></div></div>');
  if(g('vtteam'))g('vtteam').addEventListener('change',v8FilterTaskStaff);
  var taskMore=g('v71-task-more')&&g('v71-task-more').querySelector('.v71-more-body');
  if(taskMore)taskMore.insertAdjacentHTML('afterbegin','<div class="fg"><label class="fl">وزن پیشرفت (غیرریالی)</label><input class="fi" id="vtweight" type="number" min="0.01" max="1000" step="0.25" value="1"><small class="v8-scope-note">برای محاسبه سهم خروجی و درصد پیشرفت؛ هیچ مبلغی روی تسک ذخیره نمی‌شود.</small></div>');
  var contractProject=g('v7c-project')&&g('v7c-project').closest('.fg');
  if(contractProject)contractProject.insertAdjacentHTML('afterend','<div class="fg span2"><label class="fl">تیم‌های فعال قرارداد</label><div class="v8-check-list" id="v8-contract-teams"></div><small class="v8-scope-note">قرارداد می‌تواند مشترک باشد؛ سهم ریالی تیم اختیاری است.</small></div>');
  if(g('v7c-project'))g('v7c-project').addEventListener('change',function(){v8RenderContractTeams(null);});
  var statementContract=g('v7s-contract')&&g('v7s-contract').closest('.fg');
  if(statementContract)statementContract.insertAdjacentHTML('afterend','<div class="fg span2"><label class="fl">تیم‌های صورت‌وضعیت <span class="r">*</span></label><div class="v8-check-list" id="v8-statement-team"></div><div class="v7-toolbar"><button type="button" class="v7-mini" onclick="v8StatementEqualSplit()">تقسیم مساوی</button><small class="v8-scope-note">برای صورت‌وضعیت مشترک، جمع سهم تیم‌ها باید ۱۰۰٪ باشد؛ جمع شرکت فقط یک‌بار محاسبه می‌شود.</small></div></div>');
  var plannedContract=g('v7ps-contract')&&g('v7ps-contract').closest('.fg');
  if(plannedContract)plannedContract.insertAdjacentHTML('afterend','<div class="fg"><label class="fl">تیم برنامه <span class="r">*</span></label><select class="fi" id="v8-planned-team" onchange="v7RenderPlannedTasks([])"></select></div>');

  var ver=document.querySelector('.s-footer .ver');if(ver)ver.textContent='v 1.0.0';
  PML[22]=['تیم‌ها','عضویت چندتیمی و جریان کاری پروژه‌ها'];
  PML[23]=['گزارش‌های تیمی','زمان، خروجی، ظرفیت و کنترل کیفیت'];
  PML[19]=['هدف مالی کل شرکت','هدف سالانه و تقسیم ماهانه سراسری'];
  PML[24]=['پیامرسان','پیام خصوصی و گروهی در شبکه داخلی'];
  PML[25]=['هدف مالی تیم‌ها','تقسیم هدف شرکت بین تیم‌ها و ماه‌ها'];
  PML[26]=['مدیریت دسترسی‌ها','کنترل منوها، دکمه‌ها و عملیات هر نقش'];
  PML[29]=['گروه‌ها','سرگروه، اعضا و پروژه‌های مسئول هر گروه'];
  [22,23,24,25,26,29].forEach(function(i){
    if(!items[i])return;items[i].addEventListener('click',function(){showPage(i);g('tbh').textContent=PML[i][0];g('tbs').textContent=PML[i][1];});
  });
  v8InstallOverrides();
}

function v8PagesHtml(){return `
<div class="page" id="pg22">
  <div class="ph"><h2><span>👥</span>تیم‌ها و جریان‌های پروژه</h2><div class="bg"><button class="btn btn-ghost" onclick="v8LoadTeams()">↺ به‌روزرسانی</button><button class="btn btn-add" id="v8-add-team" onclick="v8OpenTeam()">➕ تیم جدید</button></div></div>
  <p class="v8-scope-note">هر کاربر می‌تواند عضو چند تیم باشد و در هر تیم نقش متفاوت داشته باشد. هر نوع پروژه هم می‌تواند بین چند تیم مشترک شود.</p>
  <div id="v8-teams"></div>
</div>
<div class="page" id="pg29">
  <div class="ph"><h2><span>🧩</span>گروه‌ها</h2><div class="bg"><button class="btn btn-ghost" onclick="v8LoadGroups()">↺ به‌روزرسانی</button><button class="btn btn-add" id="v8-add-group" data-permission="groups.create" onclick="v8OpenGroup()">➕ گروه جدید</button></div></div>
  <p class="v8-scope-note">هر گروه بخشی از یک تیم است: یک سرگروه، اعضا و پروژه‌هایی که گروه مسئول آن‌هاست. اعضای گروهی که پروژه دارد هنگام ثبت تسک و در فهرست‌ها فقط همان پروژه‌ها را می‌بینند. هر نفر فقط در یک گروه است.</p>
  <div class="v7-toolbar"><select class="fi" id="v8-group-team" onchange="v8RenderGroups()"><option value="">همه تیم‌ها</option></select><input class="fi" id="v8-group-search" placeholder="جستجوی گروه، سرگروه یا عضو..." oninput="v8RenderGroups()"></div>
  <div id="v8-groups"></div>
</div>
<div class="page" id="pg23">
  <div class="ph"><h2><span>📈</span>گزارش‌های تیمی</h2><div class="bg"><button class="btn btn-ghost" data-permission="reports.export" onclick="v8ExportReport('pdf')">PDF</button><button class="btn btn-green" data-permission="reports.export" onclick="v8ExportReport('xlsx')">Excel</button></div></div>
  <div class="v7-toolbar"><input class="fi" id="v8-report-from" readonly onclick="openDP('v8-report-from')" placeholder="از تاریخ (همه زمان‌ها)"><input class="fi" id="v8-report-to" readonly onclick="openDP('v8-report-to')" placeholder="تا تاریخ (همه زمان‌ها)"><button class="btn btn-primary" onclick="v8LoadReport()">اعمال بازه</button><button class="btn btn-ghost" onclick="v8ResetReportDates()">همه زمان‌ها</button></div>
  <div class="v8-report-tabs"><button class="btn btn-ghost active" data-permission="reports.team_dashboard" data-v8-report="dashboard" onclick="v8ChooseReport('dashboard',this)">داشبورد تیم</button><button class="btn btn-ghost" data-permission="reports.contribution" data-v8-report="contribution" onclick="v8ChooseReport('contribution',this)">سهم زمان و خروجی</button><button class="btn btn-ghost" data-permission="reports.groups" data-v8-report="groups" onclick="v8ChooseReport('groups',this)">گروه‌ها</button><button class="btn btn-ghost" data-permission="reports.capacity" data-v8-report="capacity" onclick="v8ChooseReport('capacity',this)">ظرفیت چندتیمی</button><button class="btn btn-ghost" data-permission="reports.shared_projects" data-v8-report="shared_projects" onclick="v8ChooseReport('shared_projects',this)">پروژه‌های مشترک</button><button class="btn btn-ghost" data-permission="reports.data_quality" data-v8-report="data_quality" onclick="v8ChooseReport('data_quality',this)">کیفیت داده</button><button class="btn btn-ghost" data-permission="reports.financial_attribution" data-v8-report="financial_attribution" onclick="v8ChooseReport('financial_attribution',this)">سهم مالی قراردادها</button></div>
  <div id="v8-financial-filters" class="v7-toolbar" style="display:none"><select class="fi" id="v8-fin-city"><option value="">همه شهرها</option></select><select class="fi" id="v8-fin-contract-type"><option value="">همه انواع قرارداد</option></select><select class="fi" id="v8-fin-user"><option value="">همه همکاران</option></select><button class="btn btn-primary" onclick="v8LoadReport()">اعمال فیلتر</button><button class="btn btn-ghost" data-role="admin" data-permission="contract_weights.manage" onclick="v802OpenWeights()">تنظیم وزن نوع تسک</button></div>
  <div id="v8-report-box"></div>
</div>
<div class="page" id="pg24">
  <div class="ph v8-messenger-page-head"><h2><span>💬</span>پیامرسان</h2><div class="bg"><button class="btn btn-add" data-permission="chat.manage_groups" onclick="v8ChatOpenCreate('group')">➕ گروه جدید</button><button class="btn btn-primary" onclick="v8ChatOpenCreate('direct')">پیام خصوصی</button></div></div>
  <div class="v8-device-state" id="v8-chat-device-state"><span class="v8-device-dot pending"></span><span>در حال آماده‌سازی رمزگذاری این دستگاه...</span></div>
  <div class="v8-chat-shell" id="v8-chat-shell">
    <aside class="v8-chat-side">
      <div class="v8-chat-side-head"><div><b>پیام‌ها</b><small>گفتگوهای خصوصی و گروهی</small></div><button class="v7-mini" onclick="v8ChatLoadConversations()" title="به‌روزرسانی">↺</button></div>
      <div class="v8-chat-list-search"><input class="fi" id="v8-chat-list-search" placeholder="جستجوی نام یا گروه..." oninput="v8ChatRenderConversations()"></div>
      <div class="v8-conversations" id="v8-conversations"></div>
    </aside>
    <section class="v8-chat-main">
      <div class="v8-chat-empty" id="v8-chat-empty"><div><div class="v8-chat-empty-icon">💬</div><b>یک گفتگو را انتخاب کنید</b><p>پیامرسان شبکه داخلی بدون نصب برنامه، گواهی یا ثبت دستگاه آماده است.</p></div></div>
      <div id="v8-chat-active" style="display:none;flex:1;min-height:0;flex-direction:column">
        <div class="v8-chat-head"><button class="v8-chat-back" onclick="v8ChatBackToList()" aria-label="بازگشت به پیام‌ها">‹</button><span class="v8-avatar v8-head-avatar" id="v8-chat-avatar"></span><div class="v8-chat-heading"><b id="v8-chat-title"></b><small id="v8-chat-members"></small></div><div class="v8-chat-tools"><button class="v7-mini" id="v8-chat-edit" style="display:none" onclick="v8ChatOpenEdit()">ویرایش</button><button class="v7-mini" id="v8-chat-manage-members" style="display:none" onclick="v8ChatOpenMembers()">اعضا</button><button class="v7-mini danger" id="v8-chat-delete" style="display:none" onclick="v8ChatDeleteConversation()">حذف</button><input class="fi v8-local-search" id="v8-chat-search" placeholder="جستجو در همین گفتگو" oninput="v8ChatRenderMessages()"></div></div>
        <div class="v8-chat-security">🔒 پیام‌ها و فایل‌ها روی سرور به‌صورت رمز‌شده نگهداری می‌شوند و روی همه دستگاه‌های شبکه قابل استفاده‌اند.</div>
        <div id="v8-chat-member-warning"></div>
        <div class="v8-messages" id="v8-messages" onscroll="v8ChatOnScroll()"></div>
        <button type="button" class="v8-jump-bottom" id="v8-chat-jump" onclick="v8ChatScrollToBottom()" title="آخرین پیام">↓</button>
        <div id="v8-chat-key-alert"></div>
        <div class="v8-chat-compose" id="v8-chat-compose"><input type="file" id="v8-chat-file" style="display:none" onchange="v8ChatSendFile(this.files[0])"><button class="btn btn-ghost v8-attach-btn" id="v8-chat-attach" data-permission="chat.file_upload" onclick="g('v8-chat-file').click()" title="ارسال عکس یا فایل">📎</button><textarea class="fi" id="v8-chat-text" rows="1" placeholder="پیام بنویسید..." onkeydown="v8ChatKeydown(event)" oninput="v8ChatAutoGrow()"></textarea><button class="btn btn-primary v8-send-btn" id="v8-chat-send" onclick="v8ChatSend()" title="ارسال (Enter)"><span class="v8-send-ico">➤</span><span class="v8-send-label">ارسال</span></button></div>
      </div>
    </section>
  </div>
</div>
<div class="page" id="pg25">
  <div class="ph"><h2><span>🎯</span>اهداف مالی شرکت و تیم‌ها</h2><div class="bg"><button class="btn btn-ghost" data-permission="financial_plan.manage" onclick="v8OpenApprovedTarget()">هدف مصوب شرکت</button><button class="btn btn-ghost" onclick="v8LoadTeamPlan()">↺ به‌روزرسانی</button></div></div>
  <div class="v7-toolbar"><input class="fi" id="v8-plan-year" type="number" value="1405" min="1300" max="1600"><button class="btn btn-primary" onclick="v8LoadTeamPlan()">نمایش سال</button><select class="fi" id="v8-plan-from-month"></select><select class="fi" id="v8-plan-to-month"></select><button class="btn btn-ghost" onclick="v8PlanRangeYtd()">از ابتدای سال تا الان</button><button class="btn btn-ghost" onclick="v8PlanRangeAll()">کل سال</button></div>
  <div id="v8-team-plan"></div>
  <div id="v8-team-detail"></div>
</div>`;}

function v8ModalsHtml(){return `
<div class="mo" id="v8-m-team"><div class="md wide"><div class="mh"><span class="mi">👥</span><h3 id="v8-team-modal-title">تیم</h3><button class="mx" onclick="closeM('v8-m-team')">✕</button></div><div class="mb">
  <div id="v8-team-details"><div class="fr"><div class="fg"><label class="fl">نام تیم <span class="r">*</span></label><input class="fi" id="v8-team-name"></div><div class="fg"><label class="fl">کد کوتاه</label><input class="fi" id="v8-team-code"></div></div>
  <div class="fg"><label class="fl">توضیح</label><textarea class="fi" id="v8-team-desc"></textarea></div></div>
  <div class="fr"><div class="fg" id="v8-team-members-wrap"><label class="fl">اعضا و نقش داخل تیم</label><div id="v8-team-members" class="v8-check-list"></div></div><div class="fg" id="v8-team-types-wrap"><label class="fl">نوع پروژه‌های زیرمجموعه</label><div id="v8-team-types" class="v8-check-list"></div></div></div>
  </div><div class="mf"><button class="btn btn-ghost" onclick="closeM('v8-m-team')">انصراف</button><button class="btn btn-add" id="v8-team-save" onclick="v8SaveTeam()">ذخیره تیم</button></div></div></div>
<div class="mo" id="v8-m-group"><div class="md wide"><div class="mh"><span class="mi">🧩</span><h3 id="v8-group-modal-title">گروه</h3><button class="mx" onclick="closeM('v8-m-group')">✕</button></div><div class="mb">
  <div class="fr"><div class="fg"><label class="fl">نام گروه <span class="r">*</span></label><input class="fi" id="v8-group-name" maxlength="160"></div><div class="fg"><label class="fl">تیم <span class="r">*</span></label><select class="fi" id="v8-group-team-sel" onchange="v8GroupTeamChanged(false)"></select></div></div>
  <div class="fr"><div class="fg"><label class="fl">سرگروه</label><select class="fi" id="v8-group-lead" onchange="v8GroupRenderMembers(null)"></select><small class="v8-scope-note">کاربران با نقش «سرگروه» در همین تیم. نقش در «مدیریت کاربران» تعیین می‌شود.</small></div><div class="fg"><label class="fl">توضیح</label><input class="fi" id="v8-group-desc" maxlength="1000"></div></div>
  <div class="fr"><div class="fg" id="v8-group-members-wrap"><label class="fl">اعضای گروه</label><input class="fi" id="v8-group-member-search" placeholder="جستجوی نام..." oninput="v8GroupFilterList('v8-group-members',this.value)"><div id="v8-group-members" class="v8-check-list"></div><small class="v8-scope-note">پشتیبان‌ها و سرگروه‌های همین تیم. کسی که در گروه دیگری است کم‌رنگ است؛ اول از آن گروه خارجش کنید.</small></div>
  <div class="fg" id="v8-group-projects-wrap"><label class="fl">پروژه‌های مسئول گروه</label><input class="fi" id="v8-group-project-search" placeholder="جستجوی پروژه یا شهر..." oninput="v8GroupFilterList('v8-group-projects',this.value)"><div id="v8-group-projects" class="v8-check-list"></div><small class="v8-scope-note">اگر پروژه‌ای انتخاب نشود، اعضا همه پروژه‌های تیم را می‌بینند.</small></div></div>
  </div><div class="mf"><button class="btn btn-ghost" onclick="closeM('v8-m-group')">انصراف</button><button class="btn btn-add" id="v8-group-save" onclick="v8SaveGroup()">ذخیره گروه</button></div></div></div>
<div class="mo" id="v8-m-workstream"><div class="md"><div class="mh"><span class="mi">🔗</span><h3>اتصال تیم به پروژه</h3><button class="mx" onclick="closeM('v8-m-workstream')">✕</button></div><div class="mb">
  <div class="fg"><label class="fl">تیم</label><select class="fi" id="v8-ws-team"></select></div><div class="fg"><label class="fl">پروژه</label><select class="fi" id="v8-ws-project"></select></div><div class="fg"><label class="fl">عنوان جریان کاری (اختیاری)</label><input class="fi" id="v8-ws-title"></div><label class="v7-chip"><input type="checkbox" id="v8-ws-primary"> تیم اصلی این پروژه</label>
  </div><div class="mf"><button class="btn btn-add" onclick="v8SaveWorkstream()">ذخیره</button></div></div></div>
<div class="mo" id="v8-m-target"><div class="md wide"><div class="mh"><span class="mi">🎯</span><h3 id="v8-target-title">هدف تیم</h3><button class="mx" onclick="closeM('v8-m-target')">✕</button></div><div class="mb">
  <div class="fr"><div class="fg"><label class="fl">هدف سالانه تیم</label><input class="fi" id="v8-target-annual" data-money-input dir="ltr" oninput="v8TargetEqualHint()"></div><div class="fg"><label class="fl">دلیل تغییر</label><input class="fi" id="v8-target-reason"></div></div><div class="v7-toolbar"><button class="btn btn-ghost" onclick="v8TargetEqualSplit()">تقسیم مساوی کمکی</button><small class="v8-scope-note">کسری ماه خودکار به ماه بعد منتقل نمی‌شود.</small></div><div class="v8-months" id="v8-target-months"></div>
  </div><div class="mf"><button class="btn btn-add" onclick="v8SaveTarget()">ذخیره هدف تیم</button></div></div></div>
<div class="mo" id="v8-m-statement-teams"><div class="md wide"><div class="mh"><span class="mi">🧾</span><h3 id="v8-statement-team-title">تقسیم تیمی صورت‌وضعیت</h3><button class="mx" onclick="closeM('v8-m-statement-teams')">✕</button></div><div class="mb">
  <p class="v8-scope-note">این بخش فقط اتصال تیمی را اصلاح می‌کند و مبلغ، وضعیت تأیید و سایر اطلاعات مالی را تغییر نمی‌دهد.</p><div class="v8-check-list" id="v8-statement-team-edit"></div><div class="v7-toolbar"><button type="button" class="v7-mini" onclick="v8StatementEditEqualSplit()">تقسیم مساوی</button><small class="v8-scope-note">جمع سهم تیم‌ها باید دقیقاً ۱۰۰٪ باشد.</small></div>
  </div><div class="mf"><button class="btn btn-ghost" onclick="closeM('v8-m-statement-teams')">انصراف</button><button class="btn btn-add" onclick="v8SaveStatementTeams()">ذخیره اتصال تیمی</button></div></div></div>
<div class="mo" id="v8-m-approved"><div class="md"><div class="mh"><span class="mi">🏢</span><h3>هدف مصوب شرکت</h3><button class="mx" onclick="closeM('v8-m-approved')">✕</button></div><div class="mb">
  <div class="v8-info-note">هدف کل شرکت از جمع اهداف تیم‌ها ساخته می‌شود و اینجا قابل تغییر نیست. عدد زیر فقط رقم مصوب هیئت‌مدیره است تا اختلاف آن با جمع اهداف تیم‌ها دیده شود و هیچ‌وقت مانع ثبت هدف یک تیم نمی‌شود.</div>
  <div class="fr"><div class="fg"><label class="fl">سال شمسی</label><div class="v8-readonly-value" id="v8-approved-year">—</div></div><div class="fg"><label class="fl">جمع اهداف تیم‌ها (محاسبه‌شده)</label><div class="v8-readonly-value" id="v8-approved-rollup">—</div></div></div>
  <div class="fg"><label class="fl">عنوان برنامه</label><input class="fi" id="v8-approved-title"></div>
  <div class="fg"><label class="fl">هدف مصوب شرکت</label><input class="fi" id="v8-approved-target" data-money-input dir="ltr"></div>
  <div class="fg"><label class="fl">دلیل تغییر (برای ویرایش الزامی)</label><textarea class="fi" id="v8-approved-reason"></textarea></div>
  </div><div class="mf"><button class="btn btn-ghost" onclick="closeM('v8-m-approved')">انصراف</button><button class="btn btn-add" onclick="v8SaveApprovedTarget()">ذخیره</button></div></div></div>
<div class="mo" id="v8-m-chat-create"><div class="md wide"><div class="mh"><span class="mi">💬</span><h3 id="v8-chat-create-title">گفتگو</h3><button class="mx" onclick="closeM('v8-m-chat-create')">✕</button></div><div class="mb">
  <div class="fg" id="v8-chat-group-title-wrap"><label class="fl">نام گروه</label><input class="fi" id="v8-chat-group-title"></div><div class="fg"><label class="fl">اعضا</label><input class="fi" id="v8-chat-user-search" placeholder="جستجوی نام یا تیم..." oninput="v8ChatRenderUserPicker()"><div class="v8-check-list" id="v8-chat-users"></div></div><div class="v8-info-note">رمزگذاری و ساخت کلید کاملاً خودکار است. هیچ برنامه یا کلیدی را دستی نصب یا وارد نمی‌کنید. کلید رمزگذاری به‌صورت پایدار در سرور نگهداری می‌شود؛ ورود مجدد یا راه‌اندازی مجدد سامانه پیام‌های قابل‌خواندن را قفل نمی‌کند.</div>
  </div><div class="mf"><button class="btn btn-ghost" onclick="closeM('v8-m-chat-create')">انصراف</button><button class="btn btn-add" onclick="v8ChatCreate()">شروع گفتگو</button></div></div></div>
<div class="mo" id="v8-m-chat-edit"><div class="md"><div class="mh"><span class="mi">✏️</span><h3>ویرایش گروه</h3><button class="mx" onclick="closeM('v8-m-chat-edit')">✕</button></div><div class="mb"><div class="fg"><label class="fl">نام گروه</label><input class="fi" id="v8-chat-edit-title" maxlength="200"></div></div><div class="mf"><button class="btn btn-ghost" onclick="closeM('v8-m-chat-edit')">انصراف</button><button class="btn btn-add" onclick="v8ChatSaveEdit()">ذخیره نام</button></div></div></div>
<div class="mo" id="v8-m-chat-members"><div class="md wide"><div class="mh"><span class="mi">👥</span><h3>اعضای گروه</h3><button class="mx" onclick="closeM('v8-m-chat-members')">✕</button></div><div class="mb">
  <div class="fg"><label class="fl">اعضا</label><input class="fi" id="v8-chat-member-search" placeholder="جستجوی نام یا تیم..." oninput="v8ChatRenderMemberEditor()"><div class="v8-check-list" id="v8-chat-member-editor"></div></div><div class="v8-info-note">پس از تغییر اعضا، کلید پیام‌های آینده خودکار نوسازی و فقط برای دستگاه‌های فعال اعضای جدید توزیع می‌شود.</div>
  </div><div class="mf"><button class="btn btn-ghost" onclick="closeM('v8-m-chat-members')">انصراف</button><button class="btn btn-add" onclick="v8ChatSaveMembers()">ذخیره اعضا</button></div></div></div>
<div class="mo" id="v802-m-weights"><div class="md wide"><div class="mh"><span class="mi">⚖️</span><h3>وزن نوع تسک برای انواع قرارداد</h3><button class="mx" onclick="closeM('v802-m-weights')">✕</button></div><div class="mb"><p class="v8-scope-note">امتیاز هر تسک تکمیل‌شده برابر است با وزن پیشرفت تسک × وزن نوع تسک در نوع قرارداد. مقدار ۱ خنثی است.</p><div id="v802-weights-box"></div></div><div class="mf"><button class="btn btn-ghost" onclick="closeM('v802-m-weights')">بستن</button><button class="btn btn-add" id="v802-save-weights" onclick="v802SaveWeights()">ذخیره وزن‌ها</button></div></div></div>
<div class="mo" id="v8-m-chat-devices"><div class="md wide"><div class="mh"><span class="mi">📱</span><h3>دستگاه‌های پیامرسان</h3><button class="mx" onclick="closeM('v8-m-chat-devices')">✕</button></div><div class="mb"><p class="v8-scope-note">در نسخه شبکه داخلی، پیام‌ها با کلید پایدار ذخیره‌شده در دیتابیس رمزگذاری می‌شوند و پس از ورود مجدد یا راه‌اندازی دوباره سرور قابل خواندن باقی می‌مانند.</p><div id="v8-chat-devices-list" class="v8-device-list"></div></div><div class="mf"><button class="btn btn-primary" onclick="closeM('v8-m-chat-devices')">بستن</button></div></div></div>`;}


var V8Access={roles:[],groups:[],current:null,nonDelegable:[],defaults:{},
  saved:new Set(),draft:new Set(),filter:'all'};
function v8AccessControlPageHtml(){return `
<div class="page" id="pg26">
  <div class="ph"><h2><span>🔐</span>مدیریت دسترسی نقش‌ها</h2><div class="bg">
    <span class="v8-access-dirty" id="v8-access-dirty" style="display:none">۰ تغییر ذخیره‌نشده</span>
    <button class="btn btn-ghost" id="v8-access-revert" onclick="v8AccessRevert()" disabled>↺ لغو تغییرات</button>
    <button class="btn btn-add" id="v8-access-save" onclick="v8AccessSave()" disabled>ذخیره دسترسی‌ها</button>
  </div></div>
  <div class="v8-access-shell">
    <aside class="v8-access-side">
      <div class="v8-access-side-head"><b>نقش‌ها</b><small>برای ویرایش، نقش را انتخاب کنید</small></div>
      <div class="v8-access-roles" id="v8-access-roles"></div>
    </aside>
    <section class="v8-access-main">
      <div class="v8-access-toolbar">
        <input class="fi v8-access-search" id="v8-access-search" placeholder="جستجوی نام یا کلید دسترسی..." oninput="v8AccessRenderMatrix()">
        <div class="v8-access-filters">
          <button type="button" class="v8-access-filter active" data-access-filter="all" onclick="v8AccessSetFilter('all')">همه</button>
          <button type="button" class="v8-access-filter" data-access-filter="on" onclick="v8AccessSetFilter('on')">فعال</button>
          <button type="button" class="v8-access-filter" data-access-filter="off" onclick="v8AccessSetFilter('off')">غیرفعال</button>
          <button type="button" class="v8-access-filter" data-access-filter="changed" onclick="v8AccessSetFilter('changed')">تغییرکرده</button>
          <button type="button" class="v8-access-filter" data-access-filter="custom" onclick="v8AccessSetFilter('custom')">متفاوت با پیش‌فرض</button>
        </div>
        <div class="v8-access-bulk">
          <select class="fi" id="v8-access-copy" onchange="v8AccessCopyFrom(this.value);this.value='';">
            <option value="">کپی از نقش دیگر...</option>
          </select>
          <button class="btn btn-ghost" onclick="v8AccessResetDefault()">بازگشت به پیش‌فرض نقش</button>
          <button class="btn btn-ghost" onclick="v8AccessSelectAll(true)">انتخاب همه</button>
          <button class="btn btn-ghost" onclick="v8AccessSelectAll(false)">لغو همه</button>
        </div>
      </div>
      <div class="v8-access-summary" id="v8-access-summary"></div>
      <section class="v7-group" id="v8-sensitive-access-card">
        <div class="v7-group-head"><span>📝 دسترسی اطلاعات حساس پروژه</span><small style="color:var(--txt3)">میان‌بر همین دو مجوز</small></div>
        <div class="v8-check-list v8-access-group-grid">
          <label class="v7-chip" style="justify-content:flex-start"><input id="v8-sensitive-view" type="checkbox" onchange="v8AccessSensitiveChanged('project_notes.view',this.checked)"> مشاهده VPN / ریموت / اطلاعات ورود</label>
          <label class="v7-chip" style="justify-content:flex-start"><input id="v8-sensitive-manage" type="checkbox" onchange="v8AccessSensitiveChanged('project_notes.manage',this.checked)"> ویرایش VPN / ریموت / اطلاعات ورود</label>
        </div>
        <p class="v8-scope-note" style="margin-top:10px">این گزینه‌ها از داخل دکمه 📝 کارتابل استفاده می‌شوند و نیازی به فعال‌کردن منوی پروژه‌ها ندارند. کاربر همچنان فقط پروژه متصل به تیم خودش را می‌بیند.</p>
      </section>
      <div id="v8-access-groups"><div class="v7-empty">برای دریافت فهرست دسترسی‌ها، نقش را انتخاب کنید.</div></div>
      <details class="v8-access-help"><summary>راهنمای لایه‌های دسترسی</summary>
        <p class="v8-scope-note">منوی مدیریت دسترسی‌ها فقط برای مدیر سیستم است. دسترسی «نمایش منو» مستقل از جزئیات همان منو است. هر عملیات به سه لایه مستقل نیاز دارد: نمایش منو، مشاهده جزئیات و مجوز همان عملیات؛ برای نمونه «بایگانی قرارداد» با فعال‌بودن «قراردادها»، «مشاهده قراردادها» و «بایگانی قرارداد» قابل واگذاری است و نیازی به مجوز ثبت و ویرایش قرارداد ندارد. در گروه «جزئیات داشبورد» نیز کارت‌های شخصی، تیمی، سازمانی و مالی جداگانه کنترل می‌شوند. کنترل‌ها هم‌زمان در رابط کاربری و API اعمال می‌شوند.</p>
      </details>
    </section>
  </div>
</div>`;}
/* The matrix is 144 permissions across 7 roles. The previous screen rendered
   one long checkbox wall and read the answer straight back out of the DOM,
   which meant no search, no way to tell an edit from a saved value, and a
   silent loss of work whenever the role changed. State now lives in
   V8Access.draft, the DOM is a pure projection of it, and every destructive
   action is reversible before it is saved. */
function v8AccessRoleLabel(role){var x=V8Access.roles.find(function(a){return a.role===role;});return (x&&x.label)||role||'';}
function v8AccessLocked(key){return (V8Access.nonDelegable||[]).indexOf(key)>=0;}
function v8AccessAllKeys(){
  var keys=[];
  (V8Access.groups||[]).forEach(function(gr){(gr.permissions||[]).forEach(function(p){if(!v8AccessLocked(p.key))keys.push(p.key);});});
  return keys;
}
function v8AccessSavedSet(role){
  var row=V8Access.roles.find(function(x){return x.role===role;});
  return new Set((row&&row.permissions)||[]);
}
function v8AccessChangedKeys(){
  var saved=V8Access.saved||new Set(),draft=V8Access.draft||new Set(),out=[];
  v8AccessAllKeys().forEach(function(k){if(saved.has(k)!==draft.has(k))out.push(k);});
  return out;
}
async function v8AccessLoad(){
  if(!can('access_control.manage'))return;
  var r=await api('/role_permissions',{});if(!r.ok)return toast('خطا: '+r.error,'err');
  V8Access.roles=r.roles||[];V8Access.groups=r.groups||[];V8Access.nonDelegable=r.non_delegable||[];
  V8Access.defaults=r.defaults||{};
  var first=V8Access.current&&V8Access.roles.some(function(x){return x.role===V8Access.current;})
    ?V8Access.current:(V8Access.roles[0]&&V8Access.roles[0].role||'');
  v8AccessRenderRoles();
  v8AccessSelectRole(first,true);
}
function v8AccessRenderRoles(){
  var box=g('v8-access-roles');
  var copy=g('v8-access-copy');
  if(copy)copy.innerHTML='<option value="">کپی از نقش دیگر...</option>'+V8Access.roles.filter(function(x){return x.role!==V8Access.current;}).map(function(x){return '<option value="'+escHtml(x.role)+'">'+escHtml(x.label)+'</option>';}).join('');
  if(!box)return;
  var total=v8AccessAllKeys().length;
  box.innerHTML=V8Access.roles.map(function(x){
    var active=x.role===V8Access.current,
        count=active?(V8Access.draft?V8Access.draft.size:0):((x.permissions||[]).length),
        dirty=active&&v8AccessChangedKeys().length;
    return '<button type="button" class="v8-access-role-row'+(active?' active':'')+'" onclick="v8AccessSelectRole(\''+escHtml(x.role)+'\')">'+
      '<span class="v8-access-role-name">'+escHtml(x.label)+(dirty?'<i class="v8-access-dot" title="تغییر ذخیره‌نشده"></i>':'')+'</span>'+
      '<span class="v8-access-role-count">'+toFaDigits(count)+' از '+toFaDigits(total)+'</span></button>';
  }).join('');
}
function v8AccessSelectRole(role,force){
  if(!role)return;
  if(!force&&role!==V8Access.current&&v8AccessChangedKeys().length&&
     !confirm('تغییرات ذخیره‌نشده «'+v8AccessRoleLabel(V8Access.current)+'» از بین می‌رود. ادامه می‌دهید؟')){
    return;
  }
  V8Access.current=role;
  V8Access.saved=v8AccessSavedSet(role);
  V8Access.draft=new Set(V8Access.saved);
  v8AccessRenderRoles();
  v8AccessRenderMatrix();
}
function v8AccessSetFilter(mode){
  V8Access.filter=mode;
  document.querySelectorAll('[data-access-filter]').forEach(function(b){
    b.classList.toggle('active',b.getAttribute('data-access-filter')===mode);
  });
  v8AccessRenderMatrix();
}
function v8AccessRenderMatrix(){
  var box=g('v8-access-groups');if(!box)return;
  if(!V8Access.current){box.innerHTML='<div class="v7-empty">نقشی انتخاب نشده است.</div>';return;}
  var draft=V8Access.draft||new Set(),saved=V8Access.saved||new Set(),
      defaults=new Set((V8Access.defaults||{})[V8Access.current]||[]),
      q=((g('v8-access-search')&&g('v8-access-search').value)||'').trim().toLowerCase(),
      mode=V8Access.filter||'all',hidden=0,shown=0;
  var html=(V8Access.groups||[]).map(function(gr){
    var rows=(gr.permissions||[]).map(function(p){
      var locked=v8AccessLocked(p.key),on=draft.has(p.key),
          changed=!locked&&saved.has(p.key)!==on,
          custom=!locked&&defaults.has(p.key)!==on;
      var visible=true;
      if(q&&(p.label+' '+p.key).toLowerCase().indexOf(q)<0)visible=false;
      else if(mode==='on'&&!on)visible=false;
      else if(mode==='off'&&on)visible=false;
      else if(mode==='changed'&&!changed)visible=false;
      else if(mode==='custom'&&!custom)visible=false;
      if(!visible){hidden++;return '';}
      shown++;
      if(locked){
        return '<label class="v7-chip v8-access-row locked" title="این مجوز قابل واگذاری نیست"><input type="checkbox" disabled checked>'+
          '<span class="v8-access-label">'+escHtml(p.label)+'<code>'+escHtml(p.key)+'</code></span>'+
          '<span class="v8-access-tag lock">فقط مدیر سیستم</span></label>';
      }
      return '<label class="v7-chip v8-access-row'+(changed?' changed':'')+'">'+
        '<input class="v8-access-check" type="checkbox" value="'+escHtml(p.key)+'" '+(on?'checked':'')+' onchange="v8AccessToggle(this.value,this.checked)">'+
        '<span class="v8-access-label">'+escHtml(p.label)+'<code>'+escHtml(p.key)+'</code></span>'+
        (changed?'<span class="v8-access-tag changed">تغییرکرده</span>':(custom?'<span class="v8-access-tag custom">متفاوت با پیش‌فرض</span>':''))+
        '</label>';
    }).join('');
    if(!rows)return '';
    var all=(gr.permissions||[]).filter(function(p){return !v8AccessLocked(p.key);}),
        onCount=all.filter(function(p){return draft.has(p.key);}).length;
    return '<section class="v7-group v8-access-group"><div class="v7-group-head">'+
      '<span>'+escHtml(gr.label)+'</span>'+
      '<span class="v8-access-group-tools"><small>'+toFaDigits(onCount)+' از '+toFaDigits(all.length)+'</small>'+
      '<button type="button" class="v7-mini" onclick="v8AccessToggleGroup(\''+escHtml(gr.key)+'\',true)">همه</button>'+
      '<button type="button" class="v7-mini" onclick="v8AccessToggleGroup(\''+escHtml(gr.key)+'\',false)">هیچ</button></span></div>'+
      (gr.hint?'<div class="v8-access-hint'+(gr.hint.indexOf('⚠')===0?' warn':'')+'">'+escHtml(gr.hint)+'</div>':'')+
      '<div class="v8-check-list v8-access-group-grid" data-access-group="'+escHtml(gr.key)+'">'+rows+'</div></section>';
  }).join('');
  box.innerHTML=html||'<div class="v7-empty">با این جستجو یا فیلتر، دسترسی‌ای پیدا نشد.</div>';
  v8AccessRenderSummary(shown,hidden);
  v8AccessShortcutSyncFromMatrix();
}
function v8AccessRenderSummary(shown,hidden){
  var box=g('v8-access-summary');if(!box)return;
  var draft=V8Access.draft||new Set(),total=v8AccessAllKeys().length,changed=v8AccessChangedKeys().length;
  box.innerHTML='<span class="v8-access-stat"><b>'+escHtml(v8AccessRoleLabel(V8Access.current))+'</b></span>'+
    '<span class="v8-access-stat">فعال: <b>'+toFaDigits(draft.size)+'</b> از '+toFaDigits(total)+'</span>'+
    (changed?'<span class="v8-access-stat warn">تغییر ذخیره‌نشده: <b>'+toFaDigits(changed)+'</b></span>':'')+
    (hidden?'<span class="v8-access-stat muted">'+toFaDigits(hidden)+' مورد با فیلتر پنهان شده</span>':'')+
    '<span class="v8-access-stat muted">نمایش '+toFaDigits(shown)+' مورد</span>';
  var dirty=g('v8-access-dirty'),save=g('v8-access-save'),revert=g('v8-access-revert');
  if(dirty){dirty.textContent=toFaDigits(changed)+' تغییر ذخیره‌نشده';dirty.style.display=changed?'':'none';}
  if(save)save.disabled=!changed;
  if(revert)revert.disabled=!changed;
  v8AccessRenderRoles();
}
function v8AccessToggle(key,on){
  if(!V8Access.draft||v8AccessLocked(key))return;
  if(on)V8Access.draft.add(key);else V8Access.draft.delete(key);
  // Editing sensitive project data without being able to see it is
  // meaningless, so the pair is kept coherent wherever it is toggled.
  if(key==='project_notes.manage'&&on)V8Access.draft.add('project_notes.view');
  if(key==='project_notes.view'&&!on)V8Access.draft.delete('project_notes.manage');
  v8AccessRenderMatrix();
}
function v8AccessToggleGroup(key,on){
  var gr=(V8Access.groups||[]).find(function(x){return x.key===key;});if(!gr)return;
  (gr.permissions||[]).forEach(function(p){
    if(v8AccessLocked(p.key))return;
    if(on)V8Access.draft.add(p.key);else V8Access.draft.delete(p.key);
  });
  if(!V8Access.draft.has('project_notes.view'))V8Access.draft.delete('project_notes.manage');
  v8AccessRenderMatrix();
}
function v8AccessSelectAll(value){
  if(!V8Access.draft)return;
  if(!confirm(value?'همه '+toFaDigits(v8AccessAllKeys().length)+' دسترسی برای «'+v8AccessRoleLabel(V8Access.current)+'» فعال شود؟'
                   :'همه دسترسی‌های «'+v8AccessRoleLabel(V8Access.current)+'» غیرفعال شود؟'))return;
  V8Access.draft=value?new Set(v8AccessAllKeys()):new Set();
  v8AccessRenderMatrix();
}
function v8AccessResetDefault(){
  var def=(V8Access.defaults||{})[V8Access.current];
  if(!def)return toast('پیش‌فرض این نقش در دسترس نیست','err');
  if(!confirm('دسترسی‌های «'+v8AccessRoleLabel(V8Access.current)+'» به پیش‌فرض نسخه بازگردد؟ تا زمانی که ذخیره نکنید اعمال نمی‌شود.'))return;
  V8Access.draft=new Set(def.filter(function(k){return !v8AccessLocked(k);}));
  v8AccessRenderMatrix();
}
function v8AccessCopyFrom(role){
  if(!role)return;
  var row=V8Access.roles.find(function(x){return x.role===role;});if(!row)return;
  if(!confirm('دسترسی‌های «'+v8AccessRoleLabel(role)+'» روی «'+v8AccessRoleLabel(V8Access.current)+'» کپی شود؟ تا زمانی که ذخیره نکنید اعمال نمی‌شود.'))return;
  V8Access.draft=new Set((row.permissions||[]).filter(function(k){return !v8AccessLocked(k);}));
  v8AccessRenderMatrix();
}
function v8AccessRevert(){
  if(!v8AccessChangedKeys().length)return;
  V8Access.draft=new Set(V8Access.saved);
  v8AccessRenderMatrix();
  toast('تغییرات ذخیره‌نشده لغو شد','ok');
}
function v8AccessSensitiveChanged(key,value){v8AccessToggle(key,!!value);}
function v8AccessShortcutSyncFromMatrix(){
  var draft=V8Access.draft||new Set();
  if(g('v8-sensitive-view'))g('v8-sensitive-view').checked=draft.has('project_notes.view');
  if(g('v8-sensitive-manage'))g('v8-sensitive-manage').checked=draft.has('project_notes.manage');
}
async function v8AccessSave(){
  var role=V8Access.current;if(!role||!V8Access.draft)return;
  var changed=v8AccessChangedKeys();if(!changed.length)return;
  var permissions=Array.from(V8Access.draft);
  var r=await api('/role_permissions_save',{role:role,permissions:permissions});if(!r.ok)return toast('خطا: '+r.error,'err');
  var row=V8Access.roles.find(function(x){return x.role===role;});
  if(row)row.permissions=r.permissions||permissions;
  // The server is the authority on what was actually stored, so the saved
  // baseline is rebuilt from its answer rather than from what we sent.
  V8Access.saved=v8AccessSavedSet(role);
  V8Access.draft=new Set(V8Access.saved);
  v8AccessRenderMatrix();
  toast(toFaDigits(changed.length)+' تغییر ذخیره شد؛ کاربران آن نقش صفحه را یک‌بار بارگذاری مجدد کنند.','ok');
}

function v8InstallOverrides(){
  var baseApi=api;
  api=async function(endpoint,body){
    body=body||{};if(body instanceof FormData)return baseApi(endpoint,body);
    if(endpoint.indexOf('/v8/context')<0&&body._team_scope===undefined)body._team_scope=V8.scope||'mine';
    return baseApi(endpoint,body);
  };
  var baseLoad=loadAll;
  loadAll=async function(opts){
    if(CU)await v8LoadContext();
    var result=await baseLoad(opts);
    if(CU){v8RenderScopeOptions();v8DecorateData();}
    return result;
  };
  var baseApply=applyRole;
  applyRole=function(){
    baseApply();v8RenderTopbarUser();v8RenderScopeOptions();
    // Login/permission changes are the only moments the unread watcher has to
    // be (re)armed; it then runs for the whole session, on every page.
    v8ChatStartUnreadWatch();
    if(g('v8-add-team'))g('v8-add-team').style.display=can('teams.create')?'':'none';
    if(g('v7-plan-create'))g('v7-plan-create').style.display=can('financial_plan.manage')?'':'none';
    document.querySelectorAll('[data-open="mc"],[data-open="mp"],[data-open="mu"]').forEach(function(el){
      var m={mc:'cities.create',mp:'projects.create',mu:'users.create'};el.style.display=can(m[el.getAttribute('data-open')])?'':'none';
    });
  };
  var baseShow=showPage;
  showPage=function(n){
    // Leaving the access screen with unsaved permission edits used to discard
    // them without a word; the admin gets the choice now.
    if(n!==26&&document.querySelector('#pg26.page.active')&&typeof v8AccessChangedKeys==='function'&&
       V8Access.current&&v8AccessChangedKeys().length&&
       !confirm('تغییرات ذخیره‌نشده دسترسی‌ها از بین می‌رود. از این صفحه خارج می‌شوید؟'))return;
    baseShow(n);if(n===22)v8LoadTeams();if(n===23)v8OpenReports();if(n===24)v8ChatInit();if(n===25)v8LoadTeamPlan();if(n===26)v8AccessLoad();if(n===29)v8LoadGroups();
  };
  var basePrep=prepM;
  prepM=function(id){basePrep(id);if(id==='mt'){if(g('vtweight'))g('vtweight').value='1';v8FillTaskTeams(null);}};
  var baseEdit=eTask;
  eTask=function(id){baseEdit(id);var t=(D.t||[]).find(function(x){return Number(x.id)===Number(id);});if(t){v8FillTaskTeams(t.project_team_id);if(g('vtweight'))g('vtweight').value=t.progress_weight||1;}};
  if(typeof vTask==='function'){var baseViewTask=vTask;vTask=function(id){baseViewTask(id);var t=(D.t||[]).find(function(x){return Number(x.id)===Number(id);}),box=g('tvb');if(t&&box)box.insertAdjacentHTML('afterbegin','<div style="margin-bottom:10px"><span class="v8-team-badge">'+escHtml(t.team_name||'بدون تیم')+'</span> <span class="v8-team-badge">وزن پیشرفت: '+toFaDigits(t.progress_weight||1)+'</span></div>');};}
  var baseTkPC=tkPC;
  tkPC=function(){baseTkPC();v8FillTaskTeams(null);if(typeof v7FillTaskLinks==='function')v7FillTaskLinks();};

  var baseOpenContract=v7OpenContract;
  v7OpenContract=async function(id){await baseOpenContract(id);var x=id?(V7.contracts||[]).find(function(a){return Number(a.id)===Number(id);}):null;v8RenderContractTeams(x);};
  var baseOpenStatement=v7OpenStatement;
  v7OpenStatement=async function(id){await baseOpenStatement(id);var x=id?(V7.statements||[]).find(function(a){return Number(a.id)===Number(id);}):null;v8FillStatementTeams(x);};
  var baseOpenPlanned=v7OpenPlanned;
  v7OpenPlanned=function(id){baseOpenPlanned(id);var x=id?((V7.planData&&V7.planData.planned)||[]).find(function(a){return Number(a.id)===Number(id);}):null;v8FillPlannedTeams(x&&x.project_team_id);};
  var contractChanged=g('v7s-contract');if(contractChanged)contractChanged.addEventListener('change',function(){v8FillStatementTeams(null);});
  var plannedChanged=g('v7ps-contract');if(plannedChanged)plannedChanged.addEventListener('change',function(){v8FillPlannedTeams(null);});

  // Help is a set of tabs; these cards are registered with their tab instead
  // of being appended below whatever the page rendered last.
  HELP_PROVIDERS.push(function(add){add('team',v8HelpHtml());});
  HELP_PROVIDERS.push(function(add){add('team',v8GroupsHelpHtml());});
}

async function v8LoadContext(){
  var r=await api('/v8/context',{});if(!r||!r.ok)return false;
  V8.context=r;D.project_teams=r.project_teams||[];D.team_members=r.team_members||[];
  D.groups=r.groups||[];if(typeof groupFilterOptions==='function')groupFilterOptions();
  var stored='';try{stored=localStorage.getItem('taskhub_team_scope')||'';}catch(e){}
  var valid=(r.teams||[]).some(function(t){return String(t.id)===stored;});
  if(stored==='all'&&r.can_all_teams)V8.scope='all';
  else if(stored==='mine'&&!r.can_all_teams)V8.scope='mine';
  else if(valid)V8.scope=stored;
  else V8.scope=r.can_all_teams?'all':'mine';
  return true;
}
function v8RenderScopeOptions(){
  var wrap=g('v8-team-switch'),sel=g('v8-scope');if(!wrap||!CU)return;
  if(!can('teams.view')){wrap.style.display='none';return;}
  wrap.style.display='';var html=V8.context.can_all_teams?'<option value="all">همه تیم‌ها</option>':'<option value="mine">همه تیم‌های من</option>';
  html+=(V8.context.teams||[]).map(function(t){return '<option value="'+t.id+'">'+escHtml(t.name)+'</option>';}).join('');
  sel.innerHTML=html;sel.value=V8.scope;if(sel.value!==String(V8.scope)){V8.scope=V8.context.can_all_teams?'all':'mine';sel.value=V8.scope;}
}
async function v8ScopeChanged(){
  V8.scope=g('v8-scope').value;try{localStorage.setItem('taskhub_team_scope',V8.scope);}catch(e){}
  await loadAll({silent:true});var current=document.querySelector('.page.active');var n=current?Number(current.id.replace('pg','')):0;
  if(n===22)await v8LoadTeams();if(n===23)await v8LoadReport();if(n===25)await v8LoadTeamPlan();if(n===29)await v8LoadGroups();
  if(n===16)await v7LoadContracts();if(n===18)await v7LoadStatements();toast('نمای تیم به‌روزرسانی شد','ok');
}
function v8DecorateData(){
  (D.t||[]).forEach(function(t){if(!t.team_name&&t.project_team_id){var w=(D.project_teams||[]).find(function(x){return Number(x.project_team_id)===Number(t.project_team_id);});if(w){t.team_id=w.team_id;t.team_name=w.team_name;}}});
}
function v8ProjectWorkstreams(projectId){
  return (D.project_teams||[]).filter(function(x){return Number(x.project_id)===Number(projectId);});
}
function v8FillTaskTeams(selected){
  var el=g('vtteam');if(!el)return;var pid=Number(g('vtproj').value)||0,rows=v8ProjectWorkstreams(pid);
  sOpts('vtteam','— انتخاب تیم —',rows,'project_team_id',function(x){return x.team_name+(x.title?' · '+x.title:'');});
  if(selected)el.value=String(selected);else if(rows.length===1)el.value=String(rows[0].project_team_id);v8FilterTaskStaff();
}
function v8FilterTaskStaff(){
  var ws=(D.project_teams||[]).find(function(x){return String(x.project_team_id)===String(g('vtteam')&&g('vtteam').value);});if(!ws||!g('vtstaff'))return;
  var ids=(D.team_members||[]).filter(function(x){return Number(x.team_id)===Number(ws.team_id);}).map(function(x){return Number(x.user_id);}),current=g('vtstaff').value;
  var users=(D.u||[]).filter(function(u){return ids.indexOf(Number(u.id))>=0&&['support','lead','manager'].indexOf(u.role)>=0;});sOpts('vtstaff','— انتخاب کنید —',users,'id',function(u){return u.display_name||u.username;});if(ids.indexOf(Number(current))>=0)g('vtstaff').value=current;if(typeof leadRestrictStaff==='function')leadRestrictStaff();
}
function v8ContractProjectTeams(contractId){
  var x=(V7.contracts||[]).find(function(a){return Number(a.id)===Number(contractId);});var pid=x&&x.project_id;
  var rows=v8ProjectWorkstreams(pid),ids=String(x&&x.project_team_ids||'').split(',').filter(Boolean).map(Number);
  return ids.length?rows.filter(function(w){return ids.indexOf(Number(w.project_team_id))>=0;}):rows;
}
function v8RenderContractTeams(contract){
  var box=g('v8-contract-teams');if(!box)return;var pid=Number(g('v7c-project').value)||0,rows=v8ProjectWorkstreams(pid);
  var selected=String(contract&&contract.project_team_ids||'').split(',').filter(Boolean);
  box.innerHTML=rows.map(function(x){var on=selected.indexOf(String(x.project_team_id))>=0;return '<label class="v8-check-row"><input type="checkbox" data-v8-contract-team="'+x.project_team_id+'" '+(on?'checked':'')+'><span><b>'+escHtml(x.team_name)+'</b><small class="v8-scope-note">'+escHtml(x.title||x.project_name||'')+'</small></span><input class="fi" data-money-input data-v8-contract-allocation="'+x.project_team_id+'" dir="ltr" placeholder="سهم ریالی اختیاری"></label>';}).join('')||'<div class="v7-empty">برای این پروژه تیم فعالی تعریف نشده است.</div>';
  if(contract&&contract.id)api('/v8/contract_teams',{contract_id:contract.id}).then(function(r){if(!r.ok)return;(r.rows||[]).forEach(function(v){var input=document.querySelector('[data-v8-contract-allocation="'+v.project_team_id+'"]');if(input&&v.allocation_amount!=null){input.value=v.allocation_amount;v7FormatMoneyInput(input);}});});
}
function v8ContractTeamEntries(){
  return Array.from(document.querySelectorAll('[data-v8-contract-team]:checked')).map(function(ch){var id=Number(ch.dataset.v8ContractTeam),inp=document.querySelector('[data-v8-contract-allocation="'+id+'"]');return {project_team_id:id,allocation_amount:v7Num(inp&&inp.value)};});
}
function v8FillStatementTeams(statement){
  var cid=Number(g('v7s-contract').value)||0,rows=v8ContractProjectTeams(cid),box=g('v8-statement-team');if(!box)return;
  var selected={};if(statement&&typeof statement==='object'){(statement.team_allocations||[]).forEach(function(x){selected[Number(x.project_team_id)]=Number(x.allocation_percent||0);});if(!Object.keys(selected).length&&statement.project_team_id)selected[Number(statement.project_team_id)]=100;}else if(statement)selected[Number(statement)]=100;
  if(rows.length===1&&!Object.keys(selected).length)selected[Number(rows[0].project_team_id)]=100;
  box.innerHTML=rows.map(function(x){var id=Number(x.project_team_id),on=Object.prototype.hasOwnProperty.call(selected,id);return '<label class="v8-check-row"><input type="checkbox" data-v8-statement-team="'+id+'" '+(on?'checked':'')+'><span><b>'+escHtml(x.team_name)+'</b><small class="v8-scope-note">'+escHtml(x.title||x.project_name||'')+'</small></span><input class="fi" data-v8-statement-share="'+id+'" type="number" min="0.01" max="100" step="0.01" value="'+(on?selected[id]:'')+'" placeholder="سهم ٪"></label>';}).join('')||'<div class="v7-empty">برای قرارداد انتخاب‌شده تیم فعالی وجود ندارد.</div>';
}
function v8StatementTeamEntries(){
  return Array.from(document.querySelectorAll('[data-v8-statement-team]:checked')).map(function(ch){var id=Number(ch.dataset.v8StatementTeam),input=document.querySelector('[data-v8-statement-share="'+id+'"]');return {project_team_id:id,allocation_percent:v7Num(input&&input.value)};});
}
function v8StatementEqualSplit(){
  var checked=Array.from(document.querySelectorAll('[data-v8-statement-team]:checked'));if(!checked.length)return toast('حداقل یک تیم را انتخاب کنید','err');var base=Math.floor(10000/checked.length)/100,used=0;checked.forEach(function(ch,i){var id=Number(ch.dataset.v8StatementTeam),value=i===checked.length-1?Number((100-used).toFixed(2)):base,input=document.querySelector('[data-v8-statement-share="'+id+'"]');if(input)input.value=value;used+=value;});
}
function v8CanAdjustStatementTeams(){return !!(CU&&can('statements.manage'));}
function v8OpenStatementTeams(id){
  if(!v8CanAdjustStatementTeams())return toast('فقط امور مالی یا مدیر سیستم اجازه اصلاح اتصال تیمی را دارد','err');
  var statement=(V7.statements||[]).find(function(x){return Number(x.id)===Number(id);});if(!statement)return;
  V8.statementAllocation=statement;g('v8-statement-team-title').textContent='تقسیم تیمی · '+(statement.title||statement.statement_number||'صورت‌وضعیت');
  var rows=v8ContractProjectTeams(statement.contract_id),selected={};(statement.team_allocations||[]).forEach(function(x){selected[Number(x.project_team_id)]=Number(x.allocation_percent||0);});if(!Object.keys(selected).length&&statement.project_team_id)selected[Number(statement.project_team_id)]=100;if(rows.length===1&&!Object.keys(selected).length)selected[Number(rows[0].project_team_id)]=100;
  g('v8-statement-team-edit').innerHTML=rows.map(function(x){var id=Number(x.project_team_id),on=Object.prototype.hasOwnProperty.call(selected,id);return '<label class="v8-check-row"><input type="checkbox" data-v8-statement-team-edit="'+id+'" '+(on?'checked':'')+'><span><b>'+escHtml(x.team_name)+'</b><small class="v8-scope-note">'+escHtml(x.title||x.project_name||'')+'</small></span><input class="fi" data-v8-statement-share-edit="'+id+'" type="number" min="0.01" max="100" step="0.01" value="'+(on?selected[id]:'')+'" placeholder="سهم ٪"></label>';}).join('')||'<div class="v7-empty">ابتدا قرارداد را به حداقل یک تیم فعال متصل کنید.</div>';
  openM('v8-m-statement-teams');
}
function v8StatementEditEntries(){return Array.from(document.querySelectorAll('[data-v8-statement-team-edit]:checked')).map(function(ch){var id=Number(ch.dataset.v8StatementTeamEdit),input=document.querySelector('[data-v8-statement-share-edit="'+id+'"]');return {project_team_id:id,allocation_percent:v7Num(input&&input.value)};});}
function v8StatementEditEqualSplit(){
  var checked=Array.from(document.querySelectorAll('[data-v8-statement-team-edit]:checked'));if(!checked.length)return toast('حداقل یک تیم را انتخاب کنید','err');var base=Math.floor(10000/checked.length)/100,used=0;checked.forEach(function(ch,i){var id=Number(ch.dataset.v8StatementTeamEdit),value=i===checked.length-1?Number((100-used).toFixed(2)):base,input=document.querySelector('[data-v8-statement-share-edit="'+id+'"]');if(input)input.value=value;used+=value;});
}
async function v8SaveStatementTeams(){
  var statement=V8.statementAllocation,entries=v8StatementEditEntries();if(!statement||!entries.length)return toast('حداقل یک تیم را انتخاب کنید','err');var r=await api('/statement_teams_save',{id:statement.id,statement_teams:entries});if(!r.ok)return toast(r.error,'err');closeM('v8-m-statement-teams');await v7LoadStatements(g('v7-statement-contract').value);toast('اتصال تیمی صورت‌وضعیت ذخیره شد','ok');
}
function v8FillPlannedTeams(selected){
  var cid=Number(g('v7ps-contract').value)||0,rows=v8ContractProjectTeams(cid),el=g('v8-planned-team');if(!el)return;
  sOpts('v8-planned-team','— انتخاب تیم —',rows,'project_team_id',function(x){return x.team_name;});if(selected)el.value=String(selected);else if(rows.length===1)el.value=String(rows[0].project_team_id);
}

async function v8LoadTeams(){
  var box=g('v8-teams');if(!box)return;box.innerHTML='<div class="v7-empty">در حال دریافت تیم‌ها...</div>';
  var r=await api('/v8/teams',{});if(!r.ok){box.innerHTML='<div class="v7-empty">'+escHtml(r.error)+'</div>';return;}
  V8.teams=r.rows||[];v8RenderTeams();
}
function v8RenderTeams(){
  var box=g('v8-teams'),rows=V8.teams||[];if(!rows.length){box.innerHTML='<div class="v7-empty">تیمی در محدوده دسترسی شما نیست.</div>';return;}
  box.innerHTML='<div class="v8-team-grid">'+rows.map(function(t){
    var manage=(can('teams.edit')||can('teams.members_manage')||can('teams.project_types_manage')),members=(t.members||[]).map(function(m){return '<div class="v8-list-row"><span>'+escHtml(m.display_name||m.username)+'</span><span class="v8-team-badge">'+v8RoleFa(m.team_role)+'</span></div>';}).join('');
    var types=(t.project_types||[]).map(function(x){return '<span class="v8-team-badge '+(x.assignment_role==='primary'?'primary':'')+'">'+escHtml(x.project_type_name)+' · '+(x.assignment_role==='primary'?'اصلی':'همکار')+'</span>';}).join(' ');
    var projects=(t.projects||[]).map(function(p){var archive=can('teams.archive')?'<button class="v7-mini danger" onclick="v8ArchiveWorkstream('+p.id+')">بایگانی اتصال</button>':'';return '<div class="v8-list-row"><span>'+escHtml(p.city_name)+' / '+escHtml(p.project_name)+'</span><small>'+escHtml(p.project_type_name)+'</small>'+archive+'</div>';}).join('');
    var actions='';if(manage)actions+='<button class="v7-mini" onclick="v8OpenTeam('+t.id+')">ویرایش تیم</button>';if(can('teams.project_assign'))actions+='<button class="v7-mini primary" onclick="v8OpenWorkstream('+t.id+')">اتصال پروژه</button>';if(can('teams.archive'))actions+='<button class="v7-mini danger" onclick="v8ArchiveTeam('+t.id+')">بایگانی تیم</button>';
    return '<article class="v8-team-card"><div class="v8-team-head"><div><h3>'+escHtml(t.name)+'</h3><small>'+escHtml(t.description||'بدون توضیح')+'</small></div><div class="v7-actions">'+actions+'</div></div><div class="v8-team-stats"><span><b>'+toFaDigits(t.member_count||0)+'</b><small>عضو</small></span><span><b>'+toFaDigits(t.type_count||0)+'</b><small>نوع پروژه</small></span><span><b>'+toFaDigits(t.project_count||0)+'</b><small>پروژه فعال</small></span></div><h4>حوزه پروژه</h4><div style="display:flex;gap:5px;flex-wrap:wrap">'+(types||'<span class="v8-scope-note">تعیین نشده</span>')+'</div><details style="margin-top:10px"><summary>اعضا</summary><div class="v8-list" style="margin-top:7px">'+members+'</div></details><details style="margin-top:8px"><summary>پروژه‌ها</summary><div class="v8-list" style="margin-top:7px">'+(projects||'<span class="v8-scope-note">پروژه‌ای متصل نیست</span>')+'</div></details></article>';
  }).join('')+'</div>';
}
function v8OpenTeam(id){
  var t=id?(V8.teams||[]).find(function(x){return Number(x.id)===Number(id);}):null;V8.currentTeam=t||null;
  var canEdit=can('teams.edit'),canMembers=can('teams.members_manage'),canTypes=can('teams.project_types_manage');if(t&&!canEdit&&!canMembers&&!canTypes)return toast('اجازه مدیریت این تیم را ندارید','err');
  g('v8-team-modal-title').textContent=t?'مدیریت '+t.name:'تیم جدید';g('v8-team-name').value=t&&t.name||'';g('v8-team-code').value=t&&t.code||'';g('v8-team-desc').value=t&&t.description||'';['v8-team-name','v8-team-code','v8-team-desc'].forEach(function(id){g(id).disabled=!!t&&!canEdit;});g('v8-team-members-wrap').style.display=canMembers?'':'none';g('v8-team-types-wrap').style.display=canTypes?'':'none';
  var byUser={};(t&&t.members||[]).forEach(function(x){byUser[x.user_id]=x;});
  if(!t&&CU)byUser[CU.id]={user_id:CU.id,team_role:'manager',is_primary:true};
  var candidates=(V8.context.user_candidates||[]).map(function(u){return {id:u.id,username:u.username,display_name:u.display_name,role:u.global_role||u.role};});if(!candidates.length)candidates=(D.u||[]).filter(function(u){return ['admin','manager','planner','finance','reporter','support','lead'].indexOf(u.role)>=0;});
  g('v8-team-members').innerHTML=candidates.map(function(u){var m=byUser[u.id],opts='<option value="member"'+v7Selected(m&&m.team_role,'member')+'>عضو</option>';if(['admin','manager','planner'].indexOf(u.role)>=0)opts+='<option value="planner"'+v7Selected(m&&m.team_role,'planner')+'>پلنر تیم</option>';if(['admin','manager'].indexOf(u.role)>=0)opts+='<option value="manager"'+v7Selected(m&&m.team_role,'manager')+'>مدیر تیم</option>';return '<label class="v8-check-row"><input type="checkbox" data-v8-member="'+u.id+'" '+(m?'checked':'')+'><span>'+escHtml(u.display_name||u.username)+'<small class="v8-scope-note">'+escHtml(u.role)+'</small></span><select class="fi" data-v8-member-role="'+u.id+'">'+opts+'</select></label>';}).join('');
  var byType={};(t&&t.project_types||[]).forEach(function(x){byType[x.project_type_id]=x;});
  g('v8-team-types').innerHTML=(D.pt||[]).map(function(pt){var x=byType[pt.id];return '<label class="v8-check-row"><input type="checkbox" data-v8-type="'+pt.id+'" '+(x?'checked':'')+'><span>'+escHtml(pt.name)+'</span><select class="fi" data-v8-type-role="'+pt.id+'"><option value="primary"'+v7Selected(x&&x.assignment_role,'primary')+'>اصلی</option><option value="collaborator"'+v7Selected(x&&x.assignment_role,'collaborator')+'>همکار</option></select></label>';}).join('');
  openM('v8-m-team');
}
async function v8SaveTeam(){
  var t=V8.currentTeam||{},canEdit=can('teams.edit'),canMembers=can('teams.members_manage'),canTypes=can('teams.project_types_manage');
  var members=Array.from(document.querySelectorAll('[data-v8-member]:checked')).map(function(x){var id=Number(x.dataset.v8Member);return {user_id:id,team_role:document.querySelector('[data-v8-member-role="'+id+'"]').value,is_primary:false};});
  var types=Array.from(document.querySelectorAll('[data-v8-type]:checked')).map(function(x){var id=Number(x.dataset.v8Type);return {project_type_id:id,assignment_role:document.querySelector('[data-v8-type-role="'+id+'"]').value};});
  if(!t.id&&!g('v8-team-name').value.trim())return toast('نام تیم الزامی است','err');
  if(t.id&&canEdit&&!g('v8-team-name').value.trim())return toast('نام تیم الزامی است','err');
  if(canMembers&&!members.some(function(x){return x.team_role==='manager';}))return toast('حداقل یک مدیر تیم انتخاب کنید','err');
  if(canTypes&&!types.length)return toast('حداقل یک نوع پروژه برای تیم انتخاب کنید','err');
  var teamId=t.id;
  if(!teamId||canEdit){var r=await api('/v8/team_save',{id:teamId,name:g('v8-team-name').value,code:g('v8-team-code').value,description:g('v8-team-desc').value});if(!r.ok)return toast(r.error,'err');teamId=r.id;}
  if(canMembers){var mr=await api('/v8/team_members_save',{team_id:teamId,members:members});if(!mr.ok)return toast('مشخصات تیم ذخیره شد ولی اعضا ذخیره نشدند: '+mr.error,'err');}
  if(canTypes){var tr=await api('/v8/team_types_save',{team_id:teamId,project_types:types});if(!tr.ok)return toast('اعضا ذخیره شدند ولی حوزه پروژه ذخیره نشد: '+tr.error,'err');}
  closeM('v8-m-team');await v8LoadContext();await v8LoadTeams();toast('تیم و دسترسی‌های آن ذخیره شد','ok');
}
function v8OpenWorkstream(teamId){
  V8.currentWorkstream=null;sOpts('v8-ws-team','— تیم —',V8.teams,'id','name');g('v8-ws-team').value=teamId;
  sOpts('v8-ws-project','— پروژه —',D.p,'id',function(p){return p.cname+' / '+p.name+' · '+p.project_type_name;});g('v8-ws-title').value='';g('v8-ws-primary').checked=false;openM('v8-m-workstream');
}
async function v8ArchiveTeam(id){if(!can('teams.archive'))return toast('دسترسی بایگانی تیم را ندارید','err');if(!confirm('تیم بایگانی شود؟ سابقه عملیاتی باقی می‌ماند.'))return;var r=await api('/v8/team_archive',{id:id});if(!r.ok)return toast(r.error,'err');await v8LoadContext();await v8LoadTeams();toast('تیم بایگانی شد','ok');}
async function v8ArchiveWorkstream(id){if(!can('teams.archive'))return toast('دسترسی بایگانی اتصال پروژه را ندارید','err');if(!confirm('اتصال این تیم به پروژه بایگانی شود؟'))return;var r=await api('/v8/project_team_archive',{id:id});if(!r.ok)return toast(r.error,'err');await loadAll({silent:true});await v8LoadTeams();toast('اتصال پروژه بایگانی شد','ok');}
async function v8SaveWorkstream(){
  var r=await api('/v8/project_team_save',{team_id:g('v8-ws-team').value,project_id:g('v8-ws-project').value,title:g('v8-ws-title').value,is_primary:g('v8-ws-primary').checked});if(!r.ok)return toast(r.error,'err');closeM('v8-m-workstream');await loadAll({silent:true});await v8LoadTeams();toast('تیم به پروژه متصل شد','ok');
}

// ── R16 groups (گروه) ─────────────────────────────────────────────
// A group lives inside one team: a lead, members, and the projects it answers
// for. The people of a group with projects see only those projects.
async function v8LoadGroups(){
  var box=g('v8-groups');if(!box)return;box.innerHTML='<div class="v7-empty">در حال دریافت گروه‌ها...</div>';
  var r=await api('/v8/groups',{});if(!r.ok){box.innerHTML='<div class="v7-empty">'+escHtml(r.error)+'</div>';return;}
  V8.groups=r.rows||[];
  var teams=(V8.context&&V8.context.teams)||[],sel=g('v8-group-team');
  if(sel){var keep=sel.value;sOpts('v8-group-team','همه تیم‌ها',teams,'id','name');sel.value=keep;if(sel.value!==keep)sel.value='';sel.style.display=teams.length>1?'':'none';}
  v8RenderGroups();
}
function v8RenderGroups(){
  var box=g('v8-groups');if(!box)return;
  var team=(g('v8-group-team')||{}).value||'',q=((g('v8-group-search')||{}).value||'').trim().toLowerCase(),all=V8.groups||[];
  var rows=all.filter(function(x){
    if(team&&String(x.team_id)!==String(team))return false;
    if(!q)return true;
    return [x.name,x.team_name,x.lead_name,x.description].concat((x.members||[]).map(function(m){return m.display_name||m.username;})).join(' ').toLowerCase().indexOf(q)>=0;
  });
  if(!rows.length){box.innerHTML='<div class="v7-empty">'+(all.length?'گروهی با این جستجو پیدا نشد.':'هنوز گروهی تعریف نشده است.'+(can('groups.create')?' با «گروه جدید» اولین گروه را بسازید.':''))+'</div>';return;}
  var manage=can('groups.edit')||can('groups.members_manage')||can('groups.projects_manage');
  box.innerHTML='<div class="v8-team-grid">'+rows.map(function(x){
    var members=(x.members||[]).map(function(m){return '<div class="v8-list-row"><span>'+escHtml(m.display_name||m.username)+'</span><span class="v8-team-badge">'+(m.role==='lead'?'سرگروه':'پشتیبان')+'</span></div>';}).join('');
    var projects=(x.projects||[]).map(function(p){return '<div class="v8-list-row"><span>'+escHtml(p.city_name)+' / '+escHtml(p.project_name)+'</span></div>';}).join('');
    var pcount=(x.projects||[]).length,actions='';
    if(manage)actions+='<button class="v7-mini" onclick="v8OpenGroup('+x.id+')">ویرایش</button>';
    if(can('reports.groups'))actions+='<button class="v7-mini primary" onclick="v8OpenGroupReport()">گزارش</button>';
    if(can('groups.archive'))actions+='<button class="v7-mini danger" onclick="v8ArchiveGroup('+x.id+')">بایگانی</button>';
    return '<article class="v8-team-card"><div class="v8-team-head"><div><h3>'+escHtml(x.name)+'</h3><small>'+escHtml(x.team_name||'')+(x.description?' · '+escHtml(x.description):'')+'</small></div><div class="v7-actions">'+actions+'</div></div>'+
      '<div class="v8-group-lead">سرگروه: <b>'+escHtml(x.lead_name||x.lead_username||'تعیین نشده')+'</b></div>'+
      '<div class="v8-team-stats"><span><b>'+toFaDigits((x.lead_id?1:0)+(x.members||[]).length)+'</b><small>نفر</small></span><span><b>'+toFaDigits(pcount)+'</b><small>پروژه مسئول</small></span><span><b>'+(pcount?'محدود':'کل تیم')+'</b><small>دید پروژه‌ها</small></span></div>'+
      '<details style="margin-top:10px"><summary>اعضا</summary><div class="v8-list" style="margin-top:7px">'+(members||'<span class="v8-scope-note">هنوز عضوی ندارد</span>')+'</div></details>'+
      '<details style="margin-top:8px"><summary>پروژه‌ها</summary><div class="v8-list" style="margin-top:7px">'+(projects||'<span class="v8-scope-note">پروژه‌ای تعیین نشده؛ اعضا همه پروژه‌های تیم را می‌بینند.</span>')+'</div></details></article>';
  }).join('')+'</div>';
}
// Support staff and leads of one team, from the context the server scoped.
function v8GroupTeamPeople(teamId){
  var seen={};
  return (D.team_members||[]).filter(function(m){
    if(Number(m.team_id)!==Number(teamId)||seen[m.user_id]||['support','lead'].indexOf(m.global_role)<0)return false;
    seen[m.user_id]=1;return true;
  });
}
// Who already leads or belongs to another group: one group per person.
function v8GroupTaken(groupId){
  var map={};
  (V8.groups||[]).forEach(function(x){
    if(Number(x.id)===Number(groupId))return;
    if(x.lead_id)map[Number(x.lead_id)]=x.name;
    (x.member_ids||[]).forEach(function(u){map[Number(u)]=x.name;});
  });
  return map;
}
function v8OpenGroup(id){
  var x=id?(V8.groups||[]).find(function(a){return Number(a.id)===Number(id);}):null;
  var canEdit=x?can('groups.edit'):can('groups.create'),canMembers=can('groups.members_manage'),canProjects=can('groups.projects_manage');
  if(x&&!canEdit&&!canMembers&&!canProjects)return toast('اجازه مدیریت این گروه را ندارید','err');
  V8.currentGroup=x||null;
  var teams=(V8.context&&V8.context.teams)||[],teamSel=g('v8-group-team-sel');
  g('v8-group-modal-title').textContent=x?'مدیریت '+x.name:'گروه جدید';
  sOpts('v8-group-team-sel','— انتخاب تیم —',teams,'id','name');
  teamSel.value=x?String(x.team_id):(teams.length===1?String(teams[0].id):((g('v8-group-team')||{}).value||''));
  if(x&&teamSel.value!==String(x.team_id)){teamSel.insertAdjacentHTML('beforeend','<option value="'+x.team_id+'">'+escHtml(x.team_name||'')+'</option>');teamSel.value=String(x.team_id);}
  teamSel.disabled=!!x;
  g('v8-group-name').value=x&&x.name||'';g('v8-group-desc').value=x&&x.description||'';
  ['v8-group-name','v8-group-desc','v8-group-lead'].forEach(function(k){g(k).disabled=!canEdit;});
  g('v8-group-members-wrap').style.display=canMembers?'':'none';
  g('v8-group-projects-wrap').style.display=canProjects?'':'none';
  ['v8-group-member-search','v8-group-project-search'].forEach(function(k){if(g(k))g(k).value='';});
  v8GroupTeamChanged(true);
  openM('v8-m-group');
}
function v8GroupTeamChanged(initial){
  var x=V8.currentGroup,team=Number(g('v8-group-team-sel').value)||0,taken=v8GroupTaken(x&&x.id);
  var leads=(team?v8GroupTeamPeople(team):[]).filter(function(m){return m.global_role==='lead';});
  var current=initial&&x&&x.lead_id?Number(x.lead_id):0;
  var html='<option value="">— بدون سرگروه —</option>'+leads.map(function(m){var t=taken[Number(m.user_id)];return '<option value="'+m.user_id+'"'+(t?' disabled':'')+'>'+escHtml(m.display_name||m.username)+(t?' — در گروه «'+escHtml(t)+'»':'')+'</option>';}).join('');
  if(current&&!leads.some(function(m){return Number(m.user_id)===current;}))html+='<option value="'+current+'">'+escHtml(x.lead_name||x.lead_username||('#'+current))+'</option>';
  g('v8-group-lead').innerHTML=html;g('v8-group-lead').value=current?String(current):'';
  v8GroupRenderMembers(initial&&x?(x.member_ids||[]).map(Number):[]);
  var chosen=initial&&x?(x.project_ids||[]).map(Number):[],seen={};
  var projects=(D.project_teams||[]).filter(function(w){if(Number(w.team_id)!==team||seen[w.project_id])return false;seen[w.project_id]=1;return true;});
  // A project that has since left the team stays listed while the group still has it.
  (initial&&x?(x.projects||[]):[]).forEach(function(p){if(!seen[p.project_id]){seen[p.project_id]=1;projects.push({project_id:p.project_id,project_name:p.project_name,city_name:p.city_name});}});
  g('v8-group-projects').innerHTML=projects.map(function(p){var on=chosen.indexOf(Number(p.project_id))>=0,label=(p.city_name?p.city_name+' / ':'')+(p.project_name||'');return '<label class="v8-check-row v8-row2" data-v8-search="'+escHtml(label.toLowerCase())+'"><input type="checkbox" data-v8-group-project="'+p.project_id+'"'+(on?' checked':'')+'><span>'+escHtml(label)+(p.project_type_name?'<small class="v8-scope-note">'+escHtml(p.project_type_name)+'</small>':'')+'</span></label>';}).join('')||'<div class="v7-empty">'+(team?'این تیم هنوز پروژه متصلی ندارد.':'اول تیم را انتخاب کنید.')+'</div>';
}
function v8GroupRenderMembers(checked){
  var x=V8.currentGroup,team=Number(g('v8-group-team-sel').value)||0,lead=Number(g('v8-group-lead').value)||0,taken=v8GroupTaken(x&&x.id);
  if(checked==null)checked=Array.from(document.querySelectorAll('[data-v8-group-member]:checked')).map(function(c){return Number(c.dataset.v8GroupMember);});
  var people=(team?v8GroupTeamPeople(team):[]).filter(function(m){return Number(m.user_id)!==lead;});
  g('v8-group-members').innerHTML=people.map(function(m){
    var id=Number(m.user_id),t=taken[id],on=checked.indexOf(id)>=0,name=m.display_name||m.username||'';
    return '<label class="v8-check-row v8-row2'+(t&&!on?' v8-taken':'')+'" data-v8-search="'+escHtml(name.toLowerCase())+'"><input type="checkbox" data-v8-group-member="'+id+'"'+(on?' checked':'')+(t&&!on?' disabled':'')+'><span>'+escHtml(name)+'<small class="v8-scope-note">'+(m.global_role==='lead'?'سرگروه':'پشتیبان')+(t?' · در گروه «'+escHtml(t)+'»':'')+'</small></span></label>';
  }).join('')||'<div class="v7-empty">'+(team?'پشتیبان یا سرگروهی در این تیم نیست.':'اول تیم را انتخاب کنید.')+'</div>';
  var q=g('v8-group-member-search');if(q&&q.value)v8GroupFilterList('v8-group-members',q.value);
}
function v8GroupFilterList(id,q){
  q=String(q||'').trim().toLowerCase();
  document.querySelectorAll('#'+id+' [data-v8-search]').forEach(function(row){row.style.display=!q||row.getAttribute('data-v8-search').indexOf(q)>=0?'':'none';});
}
async function v8SaveGroup(){
  var x=V8.currentGroup||{},name=g('v8-group-name').value.trim(),team=Number(g('v8-group-team-sel').value)||0;
  var canEdit=x.id?can('groups.edit'):can('groups.create'),canMembers=can('groups.members_manage'),canProjects=can('groups.projects_manage');
  if(!x.id&&!team)return toast('تیم گروه را انتخاب کنید','err');
  if(canEdit&&!name)return toast('نام گروه الزامی است','err');
  var id=x.id,btn=g('v8-group-save');if(btn)btn.disabled=true;
  try{
    if(canEdit){
      var r=await api('/v8/group_save',{id:id||null,team_id:team,name:name,description:g('v8-group-desc').value,lead_id:Number(g('v8-group-lead').value)||null});
      if(!r.ok)return toast(r.error,'err');
      // A retry after a failed second step edits this group instead of making another.
      if(!id)V8.currentGroup=Object.assign({},x,{id:r.id,team_id:team,name:name});
      id=r.id;
    }
    if(canMembers){
      var members=Array.from(document.querySelectorAll('[data-v8-group-member]:checked')).map(function(c){return Number(c.dataset.v8GroupMember);});
      var mr=await api('/v8/group_members_save',{group_id:id,member_ids:members});
      if(!mr.ok)return toast((canEdit?'مشخصات گروه ذخیره شد، ولی اعضا نه: ':'')+mr.error,'err');
    }
    if(canProjects){
      var projects=Array.from(document.querySelectorAll('[data-v8-group-project]:checked')).map(function(c){return Number(c.dataset.v8GroupProject);});
      var pr=await api('/v8/group_projects_save',{group_id:id,project_ids:projects});
      if(!pr.ok)return toast('اعضا ذخیره شدند، ولی پروژه‌های گروه نه: '+pr.error,'err');
    }
    closeM('v8-m-group');await v8LoadContext();await v8LoadGroups();toast(x.id?'گروه ذخیره شد':'گروه ساخته شد','ok');
  }finally{if(btn)btn.disabled=false;}
}
async function v8ArchiveGroup(id){
  if(!can('groups.archive'))return toast('دسترسی بایگانی گروه را ندارید','err');
  var x=(V8.groups||[]).find(function(a){return Number(a.id)===Number(id);});
  if(!confirm('گروه «'+((x&&x.name)||'')+'» بایگانی شود؟ اعضا دوباره همه پروژه‌های تیم را می‌بینند و سابقه تسک‌ها باقی می‌ماند.'))return;
  var r=await api('/v8/group_archive',{id:id});if(!r.ok)return toast(r.error,'err');
  await v8LoadContext();await v8LoadGroups();toast('گروه بایگانی شد','ok');
}
function v8OpenGroupReport(){
  V8.currentReport='groups';showPage(23);
  if(PML[23]){g('tbh').textContent=PML[23][0];g('tbs').textContent=PML[23][1];}
  document.querySelectorAll('.nav-item[data-pg]').forEach(function(x){x.classList.toggle('active',Number(x.dataset.pg)===23);});
}
// Roles see different report tabs, so the page opens on the first tab the role
// actually has instead of a dashboard it may not be allowed to load.
function v8SyncReportTab(){
  var tabs=Array.from(document.querySelectorAll('[data-v8-report]')),
      visible=tabs.filter(function(b){return b.style.display!=='none';}),
      current=visible.find(function(b){return b.getAttribute('data-v8-report')===V8.currentReport;})||visible[0]||null;
  tabs.forEach(function(b){b.classList.toggle('active',b===current);});
  if(!current)return false;
  V8.currentReport=current.getAttribute('data-v8-report');
  var ff=g('v8-financial-filters');if(ff)ff.style.display=V8.currentReport==='financial_attribution'?'flex':'none';
  if(V8.currentReport==='financial_attribution')v802PopulateFinancialFilters();
  return true;
}
function v8OpenReports(){
  if(v8SyncReportTab())v8LoadReport();
  else{var box=g('v8-report-box');if(box)box.innerHTML='<div class="v7-empty">هیچ گزارشی برای نقش شما فعال نیست.</div>';}
}
function v8RenderGroupsReport(r){
  var groups=r.groups||[],box=g('v8-report-box');
  if(!groups.length){box.innerHTML='<div class="v7-empty">گروهی در محدوده شما نیست. گروه‌ها در منوی «گروه‌ها» تعریف می‌شوند.</div>';return;}
  function pct(v){return v==null?'—':toFaDigits(v)+'٪';}
  function num(v){return toFaDigits(v||0);}
  var t={done:0,active:0,overdue:0,returned:0,hours:0};
  groups.forEach(function(x){t.done+=Number(x.done_count||0);t.active+=Number(x.active_count||0);t.overdue+=Number(x.overdue_count||0);t.returned+=Number(x.returned_count||0);t.hours+=Number(x.work_hours||0);});
  var note='<div class="v8-info-note">«انجام‌شده»، «برگشتی» و «ساعت کار» در بازه انتخابی شمرده می‌شوند؛ «باز» و «معوق» وضعیت امروز است و «سروقت» یعنی پایان تا موعد نهایی. کار هر گروه، کار سرگروه و اعضای فعلی آن است.</div>';
  var kpis='<div class="v8-kpis"><div class="v8-kpi"><small>گروه</small><b>'+num(groups.length)+'</b></div><div class="v8-kpi"><small>انجام‌شده در بازه</small><b class="good">'+num(t.done)+'</b></div><div class="v8-kpi"><small>تسک باز</small><b>'+num(t.active)+'</b></div><div class="v8-kpi"><small>معوق</small><b class="'+(t.overdue?'bad':'good')+'">'+num(t.overdue)+'</b></div><div class="v8-kpi"><small>برگشتی در بازه</small><b>'+num(t.returned)+'</b></div><div class="v8-kpi"><small>ساعت کار</small><b>'+toFaDigits(Math.round(t.hours*10)/10)+'</b></div></div>';
  var compare=groups.length>1?'<h3>مقایسه گروه‌ها</h3><div class="v7-table-wrap"><table class="v7-table"><thead><tr><th>گروه</th><th>تیم</th><th>سرگروه</th><th>نفر</th><th>انجام‌شده</th><th>باز</th><th>معوق</th><th>منتظر تأیید</th><th>برگشتی</th><th>سروقت</th><th>ساعت کار</th></tr></thead><tbody>'+groups.map(function(x){return '<tr class="'+(x.overdue_count?'v8-warn-row':'')+'"><td><b>'+escHtml(x.group_name)+'</b></td><td>'+escHtml(x.team_name||'')+'</td><td>'+escHtml(x.lead_name||'—')+'</td><td>'+num(x.member_count)+'</td><td>'+num(x.done_count)+'</td><td>'+num(x.active_count)+'</td><td>'+num(x.overdue_count)+'</td><td>'+num(x.pending_count)+'</td><td>'+num(x.returned_count)+'</td><td>'+pct(x.on_time_percent)+'</td><td>'+toFaDigits(x.work_hours||0)+'</td></tr>';}).join('')+'</tbody></table></div>':'';
  var detail=groups.map(function(x){
    var people='<div class="v7-table-wrap"><table class="v7-table"><thead><tr><th>همکار</th><th>جایگاه</th><th>انجام‌شده</th><th>باز</th><th>معوق</th><th>برگشتی</th><th>سروقت</th><th>ساعت کار</th></tr></thead><tbody>'+(x.people||[]).map(function(p){return '<tr class="'+(p.overdue_count?'v8-warn-row':'')+'"><td><b>'+escHtml(p.display_name)+'</b></td><td>'+escHtml(p.member_role)+'</td><td>'+num(p.done_count)+'</td><td>'+num(p.active_count)+'</td><td>'+num(p.overdue_count)+'</td><td>'+num(p.returned_count)+'</td><td>'+pct(p.on_time_percent)+'</td><td>'+toFaDigits(p.work_hours||0)+'</td></tr>';}).join('')+'</tbody></table></div>';
    var projects=(x.projects||[]).length?'<div class="v7-table-wrap"><table class="v7-table"><thead><tr><th>پروژه</th><th>انجام‌شده</th><th>باز</th></tr></thead><tbody>'+x.projects.map(function(p){return '<tr><td>'+escHtml(p.project_name)+(p.in_scope?'':'<span class="v8-out-scope">خارج از پروژه‌های گروه</span>')+'</td><td>'+num(p.done)+'</td><td>'+num(p.active)+'</td></tr>';}).join('')+'</tbody></table></div>':'<div class="v8-scope-note">در این بازه کاری ثبت نشده است.</div>';
    var recent=(x.recent||[]).length?'<div class="v8-group-recent">'+x.recent.map(function(k){return '<div>✅ '+escHtml(k.title)+' <small>· '+escHtml(k.staff_name)+(k.project_name?' · '+escHtml(k.project_name):'')+' · '+escHtml(toFaDigits(k.completed))+'</small></div>';}).join('')+'</div>':'<div class="v8-scope-note">تسکی در این بازه تمام نشده است.</div>';
    return '<section class="v8-group-report"><div class="v8-team-head"><div><h3>'+escHtml(x.group_name)+'</h3><small>'+escHtml(x.team_name||'')+' · سرگروه: '+escHtml(x.lead_name||'تعیین نشده')+' · '+num(x.project_count)+' پروژه مسئول</small></div></div>'+
      '<div class="v8-kpis"><div class="v8-kpi"><small>انجام‌شده</small><b class="good">'+num(x.done_count)+'</b></div><div class="v8-kpi"><small>باز</small><b>'+num(x.active_count)+'</b></div><div class="v8-kpi"><small>معوق</small><b class="'+(x.overdue_count?'bad':'good')+'">'+num(x.overdue_count)+'</b></div><div class="v8-kpi"><small>سروقت</small><b>'+pct(x.on_time_percent)+'</b></div>'+(x.in_scope_percent==null?'':'<div class="v8-kpi"><small>روی پروژه‌های گروه</small><b>'+pct(x.in_scope_percent)+'</b></div>')+'<div class="v8-kpi"><small>ساعت کار</small><b>'+toFaDigits(x.work_hours||0)+'</b></div></div>'+
      '<h4>سهم هر نفر</h4>'+people+'<h4>کار روی پروژه‌ها</h4>'+projects+'<h4>آخرین کارهای تمام‌شده</h4>'+recent+'</section>';
  }).join('');
  box.innerHTML=note+kpis+compare+detail;
}
function v8GroupsHelpHtml(){return '<div class="hlp-card v7-help"><h3>🧩 گروه‌ها</h3><ul>'+
  '<li>گروه بخشی از یک تیم است: یک سرگروه، اعضا (پشتیبان یا سرگروه همان تیم) و پروژه‌هایی که گروه مسئول آن‌هاست. هر نفر فقط در یک گروه است.</li>'+
  '<li>ساخت و ویرایش گروه در منوی «گروه‌ها» با مدیر یا پلنر همان تیم است. نقش «سرگروه» را اول در «مدیریت کاربران» روی حساب فرد بگذارید.</li>'+
  '<li>اگر برای گروه پروژه تعیین شود، سرگروه و اعضا هنگام ثبت تسک، در فیلترها و در فهرست پروژه‌ها فقط همان پروژه‌ها را می‌بینند و سرور هم تسک روی پروژه دیگر را نمی‌پذیرد. گروه بدون پروژه همان محدوده تیم را دارد. مدیر، پلنر و نقش‌های سراسری محدود نمی‌شوند.</li>'+
  '<li>سرگروه برای خودش و اعضای گروهش تسک ثبت، ویرایش، حذف و تأیید می‌کند.</li>'+
  '<li>در «گزارش‌های تیمی»، تب «گروه‌ها» کارهای انجام‌شده، باز و معوق، برگشتی‌ها، درصد سروقت، ساعت کار و سهم هر نفر و هر پروژه را نشان می‌دهد و خروجی Excel و PDF دارد. در «تسک‌ها» و «گزارش‌گیری» هم فیلتر «گروه» هست.</li>'+
  '</ul><h3>🔐 مدیریت دسترسی</h3><ul><li>صفحه دسترسی‌ها بر اساس بخش‌های برنامه مرتب شده است: هر بخش منوی خودش، مشاهده و عملیاتش را کنار هم دارد و زیر هر بخش توضیح کوتاهی آمده است.</li>'+
  '<li>ثبت تعطیلات، ثبت ماموریت و تأیید مرخصی حالا مجوز جدا دارند؛ منوها هم فقط از روی همین صفحه باز یا بسته می‌شوند.</li>'+
  '<li>ابزارهای SQL، پشتیبان‌گیری، خروجی کامل داده، نشست‌ها، اجرای خودکار و خود صفحه دسترسی‌ها فقط برای مدیر سیستم است و قفل‌شده نمایش داده می‌شود.</li></ul></div>';}

function v8ReportPayload(){var p={kind:V8.currentReport,from_date:v8Iso(g('v8-report-from').value),to_date:v8Iso(g('v8-report-to').value)};if(V8.currentReport==='financial_attribution'){p.city_id=g('v8-fin-city').value||null;p.contract_type_id=g('v8-fin-contract-type').value||null;p.user_id=g('v8-fin-user').value||null;}return p;}
function v8Iso(v){return v&&typeof v7IsoFromJalali==='function'?v7IsoFromJalali(v):null;}
function v8ChooseReport(kind,button){V8.currentReport=kind;document.querySelectorAll('[data-v8-report]').forEach(function(x){x.classList.remove('active');});if(button)button.classList.add('active');var ff=g('v8-financial-filters');if(ff)ff.style.display=kind==='financial_attribution'?'flex':'none';if(kind==='financial_attribution')v802PopulateFinancialFilters();v8LoadReport();}
function v8ResetReportDates(){g('v8-report-from').value='';g('v8-report-to').value='';v8LoadReport();}
async function v8LoadReport(){
  var box=g('v8-report-box');if(!box)return;box.innerHTML='<div class="v7-empty">در حال محاسبه گزارش...</div>';
  var endpoint=V8.currentReport==='financial_attribution'?'/v8/financial_attribution':'/v8/reports';
  var r=await api(endpoint,v8ReportPayload());if(!r.ok){box.innerHTML='<div class="v7-empty">'+escHtml(r.error)+'</div>';return;}
  if(V8.currentReport==='dashboard')v8RenderDashboardReport(r);else if(V8.currentReport==='contribution')v8RenderContribution(r);else if(V8.currentReport==='capacity')v8RenderCapacity(r.rows||[]);else if(V8.currentReport==='shared_projects')v8RenderShared(r.rows||[]);else if(V8.currentReport==='financial_attribution')v802RenderFinancialAttribution(r);else if(V8.currentReport==='groups')v8RenderGroupsReport(r);else v8RenderQuality(r.rows||[]);
}
function v8RenderDashboardReport(r){
  var t=r.totals||{},rows=r.teams||[],financial=r.financial_visible!==false;
  var moneyKpis=financial?'<div class="v8-kpi"><small>صورت‌وضعیت ارسال‌شده</small><b>'+v8Money(t.sent_amount)+'</b></div><div class="v8-kpi"><small>تایید کارفرما</small><b class="good">'+v8Money(t.approved_amount)+'</b></div>':'';
  var moneyHeads=financial?'<th>ارسال</th><th>تایید</th>':'';
  var body=rows.map(function(x){var money=financial?'<td class="v7-money">'+v8Money(x.sent_amount)+'</td><td class="v7-money">'+v8Money(x.approved_amount)+'</td>':'';return '<tr><td><b>'+escHtml(x.team_name)+'</b></td><td>'+toFaDigits(x.task_count||0)+'</td><td>'+toFaDigits(x.done_count||0)+'</td><td>'+toFaDigits(x.returned_count||0)+'</td><td>'+toFaDigits(x.progress_percent||0)+'٪<div class="v8-progress"><i style="width:'+Math.min(100,Number(x.progress_percent||0))+'%"></i></div></td><td>'+v8FmtSeconds(x.task_seconds)+'</td>'+money+'</tr>';}).join('');
  g('v8-report-box').innerHTML='<div class="v8-kpis"><div class="v8-kpi"><small>کل تسک</small><b>'+toFaDigits(t.task_count||0)+'</b></div><div class="v8-kpi"><small>تکمیل‌شده</small><b class="good">'+toFaDigits(t.done_count||0)+'</b></div><div class="v8-kpi"><small>زمان واقعی</small><b>'+v8FmtSeconds(t.work_seconds)+'</b></div>'+moneyKpis+'</div><div class="v7-table-wrap"><table class="v7-table"><thead><tr><th>تیم</th><th>تسک</th><th>انجام</th><th>برگشتی</th><th>پیشرفت وزنی</th><th>زمان</th>'+moneyHeads+'</tr></thead><tbody>'+body+'</tbody></table></div>';
}
function v8RenderContribution(r){
  var warning=(r.incomplete_task_ids||[]).length?'<div class="v8-lock-alert">⚠ '+toFaDigits(r.incomplete_task_ids.length)+' تسک تکمیل‌شده چند مسئول دارد ولی ثبت زمان ندارد؛ سهم خروجی آن‌ها حدس زده نشده است.</div>':'';
  g('v8-report-box').innerHTML=warning+'<h3>سهم افراد — دو معیار مستقل</h3><div class="v7-table-wrap"><table class="v7-table"><thead><tr><th>همکار</th><th>زمان واقعی</th><th>سهم زمانی</th><th>خروجی وزنی</th><th>سهم خروجی</th></tr></thead><tbody>'+(r.people||[]).map(function(x){return '<tr><td><b>'+escHtml(x.display_name)+'</b></td><td>'+v8FmtSeconds(x.work_seconds)+'</td><td>'+toFaDigits(x.time_share_percent||0)+'٪</td><td>'+toFaDigits(x.output_weight||0)+'</td><td>'+toFaDigits(x.output_share_percent||0)+'٪</td></tr>';}).join('')+'</tbody></table></div><h3 style="margin-top:16px">پیشرفت پروژه به تفکیک تیم</h3><div class="v7-table-wrap"><table class="v7-table"><thead><tr><th>پروژه</th><th>تیم</th><th>تسک</th><th>تکمیل</th><th>پیشرفت وزنی</th></tr></thead><tbody>'+(r.projects||[]).map(function(x){return '<tr><td>'+escHtml(x.project_name)+'</td><td><span class="v8-team-badge">'+escHtml(x.team_name)+'</span></td><td>'+toFaDigits(x.task_count)+'</td><td>'+toFaDigits(x.done_count)+'</td><td>'+toFaDigits(x.progress_percent)+'٪</td></tr>';}).join('')+'</tbody></table></div>';
}
function v8RenderCapacity(rows){g('v8-report-box').innerHTML='<div class="v7-table-wrap"><table class="v7-table"><thead><tr><th>همکار</th><th>تعداد تیم</th><th>تسک باز</th><th>درحال انجام</th><th>زمان ثبت‌شده</th><th>کنترل ظرفیت</th></tr></thead><tbody>'+rows.map(function(x){return '<tr class="'+(x.capacity_warning?'v8-warn-row':'')+'"><td>'+escHtml(x.display_name||x.username)+'</td><td>'+toFaDigits(x.team_count)+'</td><td>'+toFaDigits(x.open_tasks)+'</td><td>'+toFaDigits(x.doing_tasks)+'</td><td>'+v8FmtSeconds(x.work_seconds)+'</td><td>'+(x.capacity_warning?'<span class="v7-chip bad">احتمال تداخل ظرفیت</span>':'<span class="v7-chip ok">عادی</span>')+'</td></tr>';}).join('')+'</tbody></table></div>';}
function v8RenderShared(rows){g('v8-report-box').innerHTML=rows.length?'<div class="v7-table-wrap"><table class="v7-table"><thead><tr><th>شهر / پروژه</th><th>نوع</th><th>تیم‌ها</th><th>تسک</th><th>قرارداد</th><th>صورت‌وضعیت</th><th>ارسال کل</th><th>تایید کل</th></tr></thead><tbody>'+rows.map(function(x){return '<tr><td>'+escHtml(x.city_name)+' / <b>'+escHtml(x.project_name)+'</b></td><td>'+escHtml(x.project_type_name)+'</td><td>'+toFaDigits(x.team_count)+'</td><td>'+toFaDigits(x.task_count)+'</td><td>'+toFaDigits(x.contract_count)+'</td><td>'+toFaDigits(x.statement_count)+'</td><td class="v7-money">'+v8Money(x.sent_amount)+'</td><td class="v7-money">'+v8Money(x.approved_amount)+'</td></tr>';}).join('')+'</tbody></table></div>':'<div class="v7-empty">پروژه مشترکی در این محدوده وجود ندارد.</div>';}
function v8RenderQuality(rows){g('v8-report-box').innerHTML='<div class="v8-team-grid">'+rows.map(function(x){return '<div class="v8-team-card '+(x.severity==='critical'?'v8-critical-row':(x.severity==='warning'?'v8-warn-row':'v8-ok-row'))+'"><div class="v8-team-head"><h3>'+escHtml(x.title)+'</h3><b>'+toFaDigits(x.count)+'</b></div><small>'+(x.count?'نیازمند بررسی':'بدون مشکل')+'</small></div>';}).join('')+'</div>';}
async function v8ExportReport(format){format=format||'xlsx';var payload=v8ReportPayload(),headers={'Content-Type':'application/json'};payload.format=format;if(TOKEN)headers['X-Token']=TOKEN;var endpoint=V8.currentReport==='financial_attribution'?'/api/v8/financial_attribution_export':'/api/v8/report_export';var res=await fetch(endpoint,{method:'POST',headers:headers,body:JSON.stringify(Object.assign(payload,v8ScopePayload()))});if(!res.ok)return toast('خروجی گزارش ناموفق بود','err');var b=await res.blob(),url=URL.createObjectURL(b),a=document.createElement('a');a.href=url;a.download='TaskHub_v8_'+V8.currentReport+'.'+format;a.click();setTimeout(function(){URL.revokeObjectURL(url);},1000);}

async function v802PopulateFinancialFilters(){
  if(typeof v7LoadLookups==='function')await v7LoadLookups();
  var city=g('v8-fin-city'),ct=g('v8-fin-contract-type'),usr=g('v8-fin-user');if(!city||!ct||!usr)return;
  var cv=city.value,ctv=ct.value,uv=usr.value;sOpts('v8-fin-city','همه شهرها',D.c||[],'id','name');city.value=cv;
  sOpts('v8-fin-contract-type','همه انواع قرارداد',(V7.lookups&&V7.lookups.types)||[],'id','name');ct.value=ctv;
  var people=(D.u||[]).filter(function(x){return ['support','lead','manager','planner','finance','reporter'].indexOf(x.role)>=0;});sOpts('v8-fin-user','همه همکاران',people,'id',function(x){return x.display_name||x.username;});usr.value=uv;
}
function v802QualityWarnings(q){var items=[];if(Number(q.completed_without_contract||0))items.push(toFaDigits(q.completed_without_contract)+' تسک تکمیل‌شده قرارداد ندارد');if(Number(q.completed_without_team||0))items.push(toFaDigits(q.completed_without_team)+' تسک تکمیل‌شده تیم ندارد');if(Number(q.multi_assignee_without_time||0))items.push(toFaDigits(q.multi_assignee_without_time)+' تسک چندمسئوله ثبت زمان ندارد و سهم فردی آن حدس زده نشده');if(Number(q.mapping_missing||0))items.push(toFaDigits(q.mapping_missing)+' تسک نگاشت وزن ندارد و وزن خنثی ۱ گرفته است');if(Number(q.contracts_without_completed_task||0))items.push(toFaDigits(q.contracts_without_completed_task)+' قرارداد درآمد دارد ولی تسک تکمیل‌شده ندارد');return items.length?'<div class="v8-lock-alert">⚠ '+items.map(escHtml).join(' · ')+'</div>':'';}
function v802RenderFinancialAttribution(r){
  var t=r.totals||{},box=g('v8-report-box');
  var scope=(r.access_scope||{}).limited?'<div class="v8-info-note">این گزارش فقط در محدوده تیم‌های مجاز شماست. مبلغ تخصیص‌نیافته ممکن است شامل سهم تیم‌های خارج از محدوده دسترسی باشد.</div>':'';
  var k='<div class="v8-kpis"><div class="v8-kpi"><small>درآمد تاییدشده</small><b>'+v8Money(t.approved_amount)+'</b></div><div class="v8-kpi"><small>سهم تحلیلی تیم‌ها</small><b>'+v8Money(t.team_attributed_amount)+'</b></div><div class="v8-kpi"><small>سهم تحلیلی افراد</small><b>'+v8Money(t.person_attributed_amount)+'</b></div><div class="v8-kpi"><small>تسک تکمیل‌شده</small><b>'+toFaDigits(t.completed_task_count||0)+'</b></div></div>';
  function summary(rows,labelKey,title){return '<h3>'+title+'</h3><div class="v7-table-wrap"><table class="v7-table"><thead><tr><th>'+title+'</th><th>قرارداد</th><th>تسک</th><th>درآمد تاییدشده</th><th>سهم تیمی</th><th>سهم فردی</th><th>سهم درآمد</th></tr></thead><tbody>'+rows.map(function(x){return '<tr><td><b>'+escHtml(x[labelKey]||'تعیین نشده')+'</b></td><td>'+toFaDigits(x.contract_count||0)+'</td><td>'+toFaDigits(x.completed_task_count||0)+'</td><td class="v7-money">'+v8Money(x.approved_amount)+'</td><td class="v7-money">'+v8Money(x.team_attributed_amount)+'</td><td class="v7-money">'+v8Money(x.person_attributed_amount)+'</td><td>'+toFaDigits(x.revenue_share_percent||0)+'٪</td></tr>';}).join('')+'</tbody></table></div>';}
  var contracts='<h3>خلاصه قراردادها</h3><div class="v7-table-wrap"><table class="v7-table"><thead><tr><th>شهر</th><th>نوع</th><th>قرارداد</th><th>تسک</th><th>درآمد تاییدشده</th><th>سهم تیمی</th><th>سهم فردی</th><th>تخصیص‌نیافته فردی</th></tr></thead><tbody>'+(r.contracts||[]).map(function(x){return '<tr><td>'+escHtml(x.city_name||'بدون شهر')+'</td><td>'+escHtml(x.contract_type_name||'نوع تعیین نشده')+'</td><td><b>'+escHtml(x.contract_title||'')+'</b><small class="v8-scope-note">'+escHtml(x.contract_number||'')+'</small></td><td>'+toFaDigits(x.completed_task_count||0)+'</td><td class="v7-money">'+v8Money(x.approved_amount)+'</td><td class="v7-money">'+v8Money(x.team_attributed_amount)+'</td><td class="v7-money">'+v8Money(x.person_attributed_amount)+'</td><td class="v7-money">'+v8Money(x.unallocated_person_amount)+'</td></tr>';}).join('')+'</tbody></table></div>';
  var teams='<h3>سهم تیمی بر اساس تسک‌های تکمیل‌شده</h3><div class="v7-table-wrap"><table class="v7-table"><thead><tr><th>شهر</th><th>نوع قرارداد</th><th>قرارداد</th><th>تیم</th><th>تسک</th><th>امتیاز وزنی</th><th>درصد سهم</th><th>سهم مالی</th></tr></thead><tbody>'+(r.teams||[]).map(function(x){return '<tr><td>'+escHtml(x.city_name)+'</td><td>'+escHtml(x.contract_type_name)+'</td><td>'+escHtml(x.contract_title)+'</td><td><b>'+escHtml(x.team_name)+'</b></td><td>'+toFaDigits(x.completed_task_count||0)+'</td><td>'+toFaDigits(x.weighted_score||0)+'</td><td>'+toFaDigits(x.share_percent||0)+'٪</td><td class="v7-money">'+v8Money(x.financial_share_amount)+'</td></tr>';}).join('')+'</tbody></table></div>';
  var people='<h3>سهم فردی تحلیلی</h3><div class="v7-table-wrap"><table class="v7-table"><thead><tr><th>شهر</th><th>نوع قرارداد</th><th>قرارداد</th><th>تیم</th><th>همکار</th><th>تسک</th><th>درصد سهم</th><th>سهم مالی تحلیلی</th></tr></thead><tbody>'+(r.people||[]).map(function(x){return '<tr><td>'+escHtml(x.city_name)+'</td><td>'+escHtml(x.contract_type_name)+'</td><td>'+escHtml(x.contract_title)+'</td><td>'+escHtml(x.team_name)+'</td><td><b>'+escHtml(x.display_name)+'</b></td><td>'+toFaDigits(x.completed_task_count||0)+'</td><td>'+toFaDigits(x.share_percent||0)+'٪</td><td class="v7-money">'+v8Money(x.financial_share_amount)+'</td></tr>';}).join('')+'</tbody></table></div>';
  box.innerHTML=scope+v802QualityWarnings(r.quality||{})+k+summary(r.cities||[],'city_name','شهر')+summary(r.contract_types||[],'contract_type_name','نوع قرارداد')+contracts+teams+people+'<div class="v8-info-note">این مبالغ «سهم تحلیلی از درآمد» هستند و حقوق، پاداش یا بدهی شرکت به فرد محسوب نمی‌شوند. تسک‌های هر قرارداد با وزن نوع تسک و وزن پیشرفت محاسبه می‌شوند.</div>';
}

async function v802OpenWeights(){var r=await api('/v8/contract_task_weights',{action:'read'});if(!r.ok)return toast(r.error,'err');V8.weightRows=r.rows||[];var groups={};V8.weightRows.forEach(function(x){(groups[x.contract_type_name]=groups[x.contract_type_name]||[]).push(x);});g('v802-weights-box').innerHTML=Object.keys(groups).map(function(name){return '<section class="v7-group"><div class="v7-group-head"><span>'+escHtml(name)+'</span></div><div class="v8-weight-grid">'+groups[name].map(function(x){return '<label class="v8-weight-row"><span>'+escHtml(x.task_category_name)+'</span><input class="fi" type="number" min="0.01" max="1000" step="0.25" data-v802-weight="'+x.contract_type_id+':'+x.task_category_id+'" value="'+x.weight+'"></label>';}).join('')+'</div></section>';}).join('')||'<div class="v7-empty">ابتدا نوع تسک تعریف کنید.</div>';g('v802-save-weights').style.display=r.can_edit?'':'none';openM('v802-m-weights');}
async function v802SaveWeights(){var rows=Array.from(document.querySelectorAll('[data-v802-weight]')).map(function(el){var p=el.dataset.v802Weight.split(':');return {contract_type_id:Number(p[0]),task_category_id:Number(p[1]),weight:Number(el.value)};});var r=await api('/v8/contract_task_weights',{action:'save',rows:rows});if(!r.ok)return toast(r.error,'err');closeM('v802-m-weights');toast('وزن‌ها ذخیره شد','ok');if(V8.currentReport==='financial_attribution')v8LoadReport();}

function v8PlanMonthSelects(){
  ['v8-plan-from-month','v8-plan-to-month'].forEach(function(id,idx){
    var el=g(id);if(!el||el.options.length)return;
    el.innerHTML=V7_MONTHS.map(function(name,i){return '<option value="'+(i+1)+'">'+(idx?'تا ':'از ')+name+'</option>';}).join('');
    el.value=idx?12:1;el.onchange=v8LoadTeamPlan;
  });
}
function v8PlanRange(){
  var from=Number((g('v8-plan-from-month')||{}).value)||1,to=Number((g('v8-plan-to-month')||{}).value)||12;
  if(to<from)to=from;
  return {from_month:from,to_month:to};
}
// "From the start of the year until now" was the exact question the old screen
// could not answer, so it gets its own button rather than hiding in two selects.
function v8PlanRangeYtd(){
  var year=Number(g('v8-plan-year').value)||1405,now=v7CurrentJalali(),
      to=(now.year===year)?now.month:12;
  g('v8-plan-from-month').value=1;g('v8-plan-to-month').value=to;v8LoadTeamPlan();
}
function v8PlanRangeAll(){g('v8-plan-from-month').value=1;g('v8-plan-to-month').value=12;v8LoadTeamPlan();}
async function v8LoadTeamPlan(){
  var box=g('v8-team-plan');if(!box)return;v8PlanMonthSelects();
  box.innerHTML='<div class="v7-empty">در حال دریافت اهداف مالی...</div>';
  var year=Number(g('v8-plan-year').value)||1405,r=await api('/v8/team_financial_plan',{year:year,action:'read'});
  if(!r.ok){box.innerHTML='<div class="v7-empty">'+escHtml(r.error)+'</div>';return;}
  V8.teamPlan=r;v8RenderTeamPlan();
  if(V8.planDetailTeam)v8OpenTeamDetail(V8.planDetailTeam);
}
function v8RenderTeamPlan(){
  var r=V8.teamPlan||{},rows=r.teams||[],
      rollup=Number(r.company_rollup||0),
      approved=(r.company_approved===null||r.company_approved===undefined)?null:Number(r.company_approved),
      gap=Number(r.company_unallocated||0),
      sent=rows.reduce(function(a,x){return a+Number(x.sent_amount||0);},0),
      done=rows.reduce(function(a,x){return a+Number(x.approved_amount||0);},0),
      withTarget=Number(r.company_teams_with_target||0);
  // The company figure is now a roll-up, so it is presented as one: the total,
  // what the board approved, and the gap between them.
  var head='<section class="v8-goal-summary"><div class="v8-goal-summary-head"><b>🏢 هدف کل شرکت '+toFaDigits(Number(g('v8-plan-year').value)||1405)+'</b>'+
    '<small>از جمع اهداف '+toFaDigits(withTarget)+' تیم ساخته می‌شود</small></div>'+
    '<div class="v8-kpis"><div class="v8-kpi"><small>هدف کل شرکت (جمع تیم‌ها)</small><b>'+v8Money(rollup)+'</b></div>'+
    '<div class="v8-kpi"><small>هدف مصوب شرکت</small><b>'+(approved===null?'<span class="v8-muted">ثبت نشده</span>':v8Money(approved))+'</b></div>'+
    (approved===null?'':'<div class="v8-kpi"><small>'+(gap<0?'بیش از مصوب':'تخصیص‌نیافته')+'</small><b class="'+(gap<0?'bad':(gap>0?'warn':'good'))+'">'+v8Money(Math.abs(gap))+'</b></div>')+
    '<div class="v8-kpi"><small>ارسال‌شده</small><b>'+v8Money(sent)+'</b></div>'+
    '<div class="v8-kpi"><small>تأییدشده</small><b class="good">'+v8Money(done)+'</b></div></div>'+
    (rollup?'':'<div class="v8-info-note">هنوز برای هیچ تیمی هدف ثبت نشده است. با ثبت هدف هر تیم، هدف کل شرکت خودکار ساخته می‌شود.</div>')+
    '</section>';
  if(!rows.length){g('v8-team-plan').innerHTML=head+'<div class="v7-empty">تیمی در دسترس شما نیست.</div>';return;}
  g('v8-team-plan').innerHTML=head+'<div class="v8-team-grid">'+rows.map(function(x){
    var target=Number(x.annual_target||0),sw=Math.min(100,Number(x.sent_percent||0)),aw=Math.min(100,Number(x.approved_percent||0)),
        share=rollup?Math.round(target/rollup*100):0,
        open=Number(V8.planDetailTeam)===Number(x.team_id);
    return '<article class="v8-team-card'+(open?' open':'')+'"><div class="v8-team-head"><div><h3>'+escHtml(x.team_name)+'</h3>'+
      '<small>'+(target?('سهم '+toFaDigits(share)+'٪ از هدف شرکت · نسخه '+toFaDigits(x.version_no||1)):'هنوز هدفی ثبت نشده')+'</small></div>'+
      (v8CanPlanTeam(x.team_id)?'<button class="v7-mini primary" onclick="v8OpenTarget('+x.team_id+')">تنظیم هدف</button>':'')+
      '<button class="v7-mini" onclick="v8OpenTeamDetail('+x.team_id+')">'+(open?'بستن جزئیات':'جزئیات')+'</button></div>'+
      '<div class="v8-kpis"><div class="v8-kpi"><small>هدف</small><b>'+v8Money(target)+'</b></div>'+
      '<div class="v8-kpi"><small>ارسال</small><b>'+v8Money(x.sent_amount)+'</b></div>'+
      '<div class="v8-kpi"><small>تایید</small><b class="good">'+v8Money(x.approved_amount)+'</b></div></div>'+
      '<small>ارسال '+toFaDigits(x.sent_percent||0)+'٪</small><div class="v8-progress"><i style="width:'+sw+'%"></i></div>'+
      '<small>تایید '+toFaDigits(x.approved_percent||0)+'٪</small><div class="v8-progress"><i style="width:'+aw+'%;background:var(--green)"></i></div>'+
      '<div class="v8-scope-note">مانده تا هدف ارسال: '+v8Money(x.remaining_to_send)+'</div></article>';
  }).join('')+'</div>';
}
async function v8OpenTeamDetail(teamId){
  var box=g('v8-team-detail');if(!box)return;
  if(Number(V8.planDetailTeam)===Number(teamId)&&box.innerHTML){V8.planDetailTeam=null;box.innerHTML='';v8RenderTeamPlan();return;}
  V8.planDetailTeam=Number(teamId);v8RenderTeamPlan();
  box.innerHTML='<div class="v7-empty">در حال دریافت جزئیات تیم...</div>';
  var range=v8PlanRange(),
      r=await api('/v8/team_financial_detail',Object.assign({year:Number(g('v8-plan-year').value)||1405,team_id:teamId},range));
  if(!r.ok){box.innerHTML='<div class="v8-lock-alert">'+escHtml(r.error)+'</div>';return;}
  V8.planDetail=r;v8RenderTeamDetail();
}
function v8RenderTeamDetail(){
  var r=V8.planDetail||{},box=g('v8-team-detail');if(!box||!r.team)return;
  var t=r.totals||{},months=r.months||[],rows=r.statements||[],
      rangeLabel=V7_MONTHS[(r.from_month||1)-1]+' تا '+V7_MONTHS[(r.to_month||12)-1],
      max=Math.max.apply(null,[1].concat(months.map(function(m){return Math.max(Number(m.target_amount||0),Number(m.sent_amount||0),Number(m.approved_amount||0));})));
  var chart=months.map(function(m){
    function h(v){return Math.max(Number(v)?4:0,Math.round(Number(v||0)/max*120));}
    return '<div class="v8-detail-month"><div class="v8-detail-bars">'+
      '<i class="t" style="height:'+h(m.target_amount)+'px" title="هدف"></i>'+
      '<i class="s" style="height:'+h(m.sent_amount)+'px" title="ارسال"></i>'+
      '<i class="a" style="height:'+h(m.approved_amount)+'px" title="تأیید"></i></div>'+
      '<span>'+V7_MONTHS[m.month_no-1]+'</span></div>';
  }).join('');
  var table='<div class="v8-detail-table-wrap"><table class="v8-detail-table"><thead><tr><th>ماه</th><th>هدف</th><th>ارسال‌شده</th><th>تأییدشده</th><th>تحقق</th><th>فاصله تا هدف</th><th>صورت‌وضعیت</th></tr></thead><tbody>'+
    months.map(function(m){
      var pct=Number(m.approved_percent||0);
      return '<tr><td>'+V7_MONTHS[m.month_no-1]+'</td><td>'+v8Money(m.target_amount)+'</td><td>'+v8Money(m.sent_amount)+'</td>'+
        '<td class="good">'+v8Money(m.approved_amount)+'</td><td>'+toFaDigits(pct)+'٪</td>'+
        '<td class="'+(Number(m.gap)>0?'warn':'good')+'">'+v8Money(m.gap)+'</td><td>'+toFaDigits(m.statement_count||0)+'</td></tr>';
    }).join('')+
    '<tr class="v8-detail-total"><td>جمع بازه</td><td>'+v8Money(t.range_target)+'</td><td>'+v8Money(t.sent_amount)+'</td>'+
    '<td class="good">'+v8Money(t.approved_amount)+'</td><td>'+toFaDigits(t.approved_percent||0)+'٪</td>'+
    '<td class="'+(Number(t.gap)>0?'warn':'good')+'">'+v8Money(t.gap)+'</td><td>'+toFaDigits(t.statement_count||0)+'</td></tr></tbody></table></div>';
  var list=rows.length?('<div class="v8-detail-table-wrap"><table class="v8-detail-table"><thead><tr><th>ماه</th><th>عنوان</th><th>قرارداد</th><th>پروژه</th><th>سهم تیم</th><th>مبلغ ارسال تیم</th><th>مبلغ تأیید تیم</th><th>وضعیت</th></tr></thead><tbody>'+
    rows.map(function(s){
      return '<tr><td>'+V7_MONTHS[(Number(s.period_month)||1)-1]+'</td><td>'+escHtml(s.title||'—')+'</td>'+
        '<td>'+escHtml(s.contract_number||s.contract_title||'—')+'</td><td>'+escHtml(s.project_name||'—')+'</td>'+
        '<td>'+toFaDigits(Number(s.allocation_percent||0))+'٪</td><td>'+v8Money(s.team_requested_amount)+'</td>'+
        '<td class="good">'+v8Money(s.team_approved_amount)+'</td><td>'+escHtml(v8StatementStatusFa(s.business_status))+'</td></tr>';
    }).join('')+'</tbody></table></div>'):'<div class="v7-empty">در این بازه صورت‌وضعیتی برای این تیم ثبت نشده است.</div>';
  box.innerHTML='<section class="v8-detail-panel"><div class="v8-detail-head"><div><b>📊 جزئیات مالی '+escHtml(r.team.name)+'</b>'+
    '<small>'+escHtml(rangeLabel)+' سال '+toFaDigits(r.year)+'</small></div>'+
    '<button class="v7-mini" onclick="v8OpenTeamDetail('+r.team.id+')">بستن</button></div>'+
    (r.has_target?'':'<div class="v8-info-note">برای این تیم هنوز هدف سالانه ثبت نشده است؛ ستون هدف صفر نمایش داده می‌شود.</div>')+
    '<div class="v8-kpis"><div class="v8-kpi"><small>هدف سالانه تیم</small><b>'+v8Money(t.annual_target)+'</b></div>'+
    '<div class="v8-kpi"><small>هدف همین بازه</small><b>'+v8Money(t.range_target)+'</b></div>'+
    '<div class="v8-kpi"><small>ارسال‌شده</small><b>'+v8Money(t.sent_amount)+'</b></div>'+
    '<div class="v8-kpi"><small>تأییدشده</small><b class="good">'+v8Money(t.approved_amount)+'</b></div>'+
    '<div class="v8-kpi"><small>تحقق بازه</small><b>'+toFaDigits(t.approved_percent||0)+'٪</b></div>'+
    '<div class="v8-kpi"><small>تحقق از هدف سالانه</small><b>'+toFaDigits(t.annual_approved_percent||0)+'٪</b></div></div>'+
    '<div class="v8-detail-chart-legend"><span><i class="t"></i>هدف</span><span><i class="s"></i>ارسال</span><span><i class="a"></i>تأیید</span></div>'+
    '<div class="v8-detail-chart">'+chart+'</div>'+
    '<h4 class="v8-detail-sub">روند ماهانه</h4>'+table+
    '<h4 class="v8-detail-sub">صورت‌وضعیت‌های این بازه ('+toFaDigits(rows.length)+')</h4>'+list+'</section>';
}
function v8StatementStatusFa(v){
  return {draft:'پیش‌نویس',internal_approved:'تأیید داخلی',sent:'ارسال‌شده',
          employer_approved:'تأیید کارفرما',employer_rejected:'رد کارفرما',
          revised:'اصلاح‌شده',void:'باطل'}[v]||(v||'—');
}
function v8OpenApprovedTarget(){
  if(!can('financial_plan.manage'))return;
  var r=V8.teamPlan||{},p=r.plan||{};
  g('v8-approved-year').textContent=toFaDigits(Number(g('v8-plan-year').value)||1405);
  g('v8-approved-rollup').textContent=v8Money(r.company_rollup||0);
  g('v8-approved-target').value=v7MoneyInputValue(r.company_approved||0);
  g('v8-approved-title').value=p.title||'';
  g('v8-approved-reason').value='';
  openM('v8-m-approved');
}
async function v8SaveApprovedTarget(){
  var year=Number(g('v8-plan-year').value)||1405,
      r=await api('/financial_plan_save',{year:year,approved_target:v7Num(g('v8-approved-target').value)||0,
        title:g('v8-approved-title').value,reason:g('v8-approved-reason').value});
  if(!r.ok)return toast(r.error,'err');
  closeM('v8-m-approved');await v8LoadTeamPlan();toast('هدف مصوب شرکت ذخیره شد','ok');
}
function v8OpenTarget(teamId){
  var x=(V8.teamPlan.teams||[]).find(function(a){return Number(a.team_id)===Number(teamId);});if(!x||!v8CanPlanTeam(teamId))return;
  V8.currentTarget=x;g('v8-target-title').textContent='هدف مالی '+x.team_name;g('v8-target-annual').value=x.annual_target||0;v7FormatMoneyInput(g('v8-target-annual'));g('v8-target-reason').value='';
  var map={};(x.periods||[]).forEach(function(p){map[p.month_no]=p;});g('v8-target-months').innerHTML=V7_MONTHS.map(function(name,i){var m=i+1,p=map[m]||{};return '<div class="v8-month-box"><label>'+name+'</label><input class="fi" data-money-input data-v8-target-month="'+m+'" dir="ltr" value="'+v7MoneyInputValue(p.target_amount||0)+'"></div>';}).join('');openM('v8-m-target');
}
function v8TargetEqualHint(){}
function v8TargetEqualSplit(){var total=v7Num(g('v8-target-annual').value)||0,each=Math.floor(total/12),rem=total-each*12;document.querySelectorAll('[data-v8-target-month]').forEach(function(x,i){x.value=v7MoneyInputValue(each+(i===11?rem:0));});}
async function v8SaveTarget(){
  var x=V8.currentTarget,periods=Array.from(document.querySelectorAll('[data-v8-target-month]')).map(function(el){return {month_no:Number(el.dataset.v8TargetMonth),target_amount:v7Num(el.value)||0,allocation_mode:'amount'};});
  var r=await api('/v8/team_financial_plan',{action:'save',year:Number(g('v8-plan-year').value),team_id:x.team_id,annual_target:v7Num(g('v8-target-annual').value),reason:g('v8-target-reason').value,periods:periods});if(!r.ok)return toast(r.error,'err');closeM('v8-m-target');await v8LoadTeamPlan();toast('هدف تیم ذخیره شد و به هدف کل شرکت اضافه شد','ok');
}

function v8HelpHtml(){return '<div class="hlp-card v7-help"><h3>👥 تیم‌ها</h3><ul><li>انتخاب‌گر تیم برای محدودکردن گزارش یا عملیات به یک تیم مشخص است؛ مدیر و پلنر در حالت عادی همه پروژه‌ها، قراردادها و کاربران را می‌بینند.</li><li>تسک، قرارداد و صورت‌وضعیت می‌توانند به یک یا چند جریان کاری تیمی متصل شوند.</li></ul><h3>💬 پیامرسان</h3><ul><li>از منوی پیامرسان، گفتگوی خصوصی یا گروهی بسازید و پیام ارسال کنید.</li><li>در نسخه LAN، پیام‌های جدید روی سرور مدیریت می‌شوند و برای استفاده روی کامپیوتر یا موبایل نیاز به نصب کلید یا افزونه نیست.</li></ul><h3>📈 گزارش‌ها</h3><ul><li>سهم زمان از تایمر واقعی و سهم خروجی از وزن تسک محاسبه می‌شود و این دو شاخص جدا هستند.</li><li>مبالغ سهم مالی فقط برای تحلیل مدیریتی‌اند و به معنی حقوق یا بدهی قابل پرداخت نیستند.</li></ul></div>';}



/* ── Browser-side E2EE messenger ──────────────────────────────────────── */
function v8B64(bytes){
  var u=bytes instanceof Uint8Array?bytes:new Uint8Array(bytes),out='',chunk=0x8000;
  for(var i=0;i<u.length;i+=chunk)out+=String.fromCharCode.apply(null,u.subarray(i,i+chunk));
  return btoa(out);
}
function v8Unb64(text){var s=atob(text||''),u=new Uint8Array(s.length);for(var i=0;i<s.length;i++)u[i]=s.charCodeAt(i);return u;}
function v8RandomId(){return (crypto.randomUUID?crypto.randomUUID():Array.from(crypto.getRandomValues(new Uint8Array(16))).map(function(x){return x.toString(16).padStart(2,'0');}).join(''));}
function v8ChatUserPrefix(){return 'user:'+(CU&&CU.id?CU.id:'anonymous')+':';}
function v8ChatDeviceKeyId(){return v8ChatUserPrefix()+'device-rsa';}
function v8ChatConversationKeyId(cid,version){return v8ChatUserPrefix()+'conv:'+cid+':'+version;}
function v8ChatDb(){
  if(V8.chat.dbPromise)return V8.chat.dbPromise;
  V8.chat.dbPromise=new Promise(function(resolve,reject){var req=indexedDB.open('TaskHubChatCryptoV8',1);req.onupgradeneeded=function(){if(!req.result.objectStoreNames.contains('keys'))req.result.createObjectStore('keys',{keyPath:'id'});};req.onsuccess=function(){resolve(req.result);};req.onerror=function(){reject(req.error);};});
  return V8.chat.dbPromise;
}
async function v8ChatStoreGet(id){var db=await v8ChatDb();return new Promise(function(resolve,reject){var r=db.transaction('keys','readonly').objectStore('keys').get(id);r.onsuccess=function(){resolve(r.result||null);};r.onerror=function(){reject(r.error);};});}
async function v8ChatStorePut(row){var db=await v8ChatDb();return new Promise(function(resolve,reject){var r=db.transaction('keys','readwrite').objectStore('keys').put(row);r.onsuccess=function(){resolve(true);};r.onerror=function(){reject(r.error);};});}
function v8ChatLocalhost(){return ['localhost','127.0.0.1','::1'].indexOf(location.hostname)>=0;}
function v8ChatServerMode(){return V8.chat.mode==='server';}
async function v8ChatGetMode(){
  if(V8.chat.mode)return V8.chat.mode;
  var r=await api('/v8/chat/config',{});if(!r||!r.ok)throw new Error(r&&r.error||'تنظیمات پیامرسان دریافت نشد');
  V8.chat.mode=r.mode||'e2e';v8ChatApplyModeUi();return V8.chat.mode;
}
function v8ChatApplyModeUi(){
  if(!v8ChatServerMode())return;
  var security=document.querySelector('.v8-chat-security');
  if(security)security.textContent='🔒 پیام‌ها و فایل‌ها روی سرور به‌صورت رمز‌شده نگهداری می‌شوند. این نسخه برای اجرای ساده در شبکه داخلی و موبایل طراحی شده است.';
  v8ChatSetDeviceState('ready','پیامرسان شبکه داخلی آماده است · بدون نیاز به ثبت دستگاه یا گواهی');
}
function v8ChatCryptoSupported(){return !!(window.crypto&&crypto.subtle&&window.indexedDB&&(window.isSecureContext||v8ChatLocalhost()));}
function v8ChatDeviceLabel(){
  var ua=navigator.userAgent||'',os=/Android/i.test(ua)?'Android':(/iPhone|iPad|iPod/i.test(ua)?'iPhone/iPad':(/Windows/i.test(ua)?'Windows':(/Mac OS/i.test(ua)?'macOS':'دستگاه'))),browser=/Edg/i.test(ua)?'Edge':(/Chrome/i.test(ua)?'Chrome':(/Safari/i.test(ua)?'Safari':(/Firefox/i.test(ua)?'Firefox':'مرورگر')));
  return browser+' روی '+os;
}
function v8ChatSetDeviceState(kind,text,actionHtml){
  var box=g('v8-chat-device-state');if(!box)return;box.className='v8-device-state '+(kind||'pending');box.innerHTML='<span class="v8-device-dot '+(kind||'pending')+'"></span><span class="v8-device-state-text">'+escHtml(text||'')+'</span>'+(actionHtml||'');
}
function v8ChatPendingCodeKey(){return v8ChatUserPrefix()+'pending-approval-code';}
async function v8ChatDeviceKeys(){
  var id=v8ChatDeviceKeyId(),row=await v8ChatStoreGet(id);
  if(row&&row.privateKey&&row.publicJwk)return {privateKey:row.privateKey,publicJwk:row.publicJwk};
  if(row&&row.privatePkcs8&&row.publicJwk){
    var migrated=await crypto.subtle.importKey('pkcs8',v8Unb64(row.privatePkcs8),{name:'RSA-OAEP',hash:'SHA-256'},false,['decrypt']);
    await v8ChatStorePut({id:id,privateKey:migrated,publicJwk:row.publicJwk,createdAt:row.createdAt||Date.now(),migratedAt:Date.now()});
    return {privateKey:migrated,publicJwk:row.publicJwk};
  }
  var pair=await crypto.subtle.generateKey({name:'RSA-OAEP',modulusLength:2048,publicExponent:new Uint8Array([1,0,1]),hash:'SHA-256'},true,['encrypt','decrypt']);
  var publicJwk=await crypto.subtle.exportKey('jwk',pair.publicKey),pkcs8=await crypto.subtle.exportKey('pkcs8',pair.privateKey),privateKey=await crypto.subtle.importKey('pkcs8',pkcs8,{name:'RSA-OAEP',hash:'SHA-256'},false,['decrypt']);
  await v8ChatStorePut({id:id,privateKey:privateKey,publicJwk:publicJwk,createdAt:Date.now()});
  return {privateKey:privateKey,publicJwk:publicJwk};
}
async function v8ChatEnsureDevice(force,uuidResetTried){
  if(V8.chat.device&&Number(V8.chat.device.userId)!==Number(CU&&CU.id)){
    V8.chat.device=null;V8.chat.current=null;V8.chat.conversations=[];V8.chat.messages=[];V8.chat.lastError=null;
    if(V8.chat.poll){clearInterval(V8.chat.poll);V8.chat.poll=null;}if(V8.chat.pendingPoll){clearInterval(V8.chat.pendingPoll);V8.chat.pendingPoll=null;}
  }
  if(V8.chat.device&&!force)return V8.chat.device;
  if(!v8ChatCryptoSupported()){
    if(!window.isSecureContext&&!v8ChatLocalhost())throw new Error('برای استفاده از پیامرسان روی موبایل باید سامانه را با آدرس HTTPS باز کنید. آدرس HTTP شبکه محلی اجازه ساخت کلید امن مرورگر را نمی‌دهد.');
    throw new Error('این مرورگر قابلیت رمزگذاری امن و IndexedDB موردنیاز پیامرسان را پشتیبانی نمی‌کند. مرورگر را به‌روز کنید.');
  }
  v8ChatSetDeviceState('pending','در حال ساخت یا بازیابی کلید این دستگاه...');
  var storageKey='taskhub_chat_device_uuid_'+(CU&&CU.id?CU.id:'0'),uuid='',approvalCode='';
  try{uuid=localStorage.getItem(storageKey)||'';approvalCode=localStorage.getItem(v8ChatPendingCodeKey())||'';}catch(e){}
  if(!uuid){uuid=v8RandomId();try{localStorage.setItem(storageKey,uuid);}catch(e){}}
  var keys=await v8ChatDeviceKeys(),r=await api('/v8/chat/device',{device_uuid:uuid,label:v8ChatDeviceLabel(),public_key_jwk:keys.publicJwk,approval_code:approvalCode});
  if(!r.ok&&r.reset_device_uuid&&!uuidResetTried){
    try{localStorage.removeItem(storageKey);localStorage.removeItem(v8ChatPendingCodeKey());}catch(e){}
    V8.chat.device=null;
    return v8ChatEnsureDevice(true,true);
  }
  if(!r.ok)throw new Error(r.error);
  if(r.approval_code){approvalCode=String(r.approval_code);try{localStorage.setItem(v8ChatPendingCodeKey(),approvalCode);}catch(e){}}
  if(!r.pending){try{localStorage.removeItem(v8ChatPendingCodeKey());}catch(e){}}
  V8.chat.device={id:r.device_id,userId:CU.id,uuid:uuid,privateKey:keys.privateKey,publicJwk:keys.publicJwk,label:v8ChatDeviceLabel(),pending:!!r.pending,approvalCode:approvalCode};
  if(V8.chat.device.pending){
    v8ChatSetDeviceState('pending','این دستگاه منتظر تأیید از یکی از دستگاه‌های قبلی شماست. کد تأیید: '+approvalCode,'<button type="button" class="v7-mini primary" onclick="v8ChatCopyApprovalCode()">کپی کد</button>');
  }else{
    v8ChatSetDeviceState('ready','این دستگاه برای پیامرسان آماده است · '+V8.chat.device.label);
  }
  return V8.chat.device;
}
function v8ChatCopyApprovalCode(){var code=V8.chat.device&&V8.chat.device.approvalCode||'';if(!code)return;try{navigator.clipboard.writeText(code);toast('کد تأیید کپی شد','ok');}catch(e){toast('کد تأیید: '+code,'inf');}}
function v8ChatRenderPendingDevice(){
  var box=g('v8-conversations');if(!box)return;var code=V8.chat.device&&V8.chat.device.approvalCode||'';
  box.innerHTML='<div class="v8-pending-device"><div class="v8-chat-empty-icon">📱</div><b>تأیید این دستگاه لازم است</b><p>در یک کامپیوتر یا موبایل که قبلاً پیامرسان روی آن فعال بوده، وارد همین حساب شوید، «دستگاه‌های من» را باز کنید و کد زیر را وارد کنید.</p><strong>'+escHtml(code)+'</strong><small>پس از تأیید، این صفحه خودکار آماده می‌شود. پیام‌های قدیمی فقط وقتی نمایش داده می‌شوند که کلید نسخه قبلی روی این دستگاه موجود باشد.</small></div>';
}
async function v8ChatRefreshDeviceApprovals(){
  if(!V8.chat.device||V8.chat.device.pending)return;
  var r=await api('/v8/chat/devices',{current_device_id:V8.chat.device.id});if(!r.ok)return;
  V8.chat.myDevices=r.rows||[];var pending=Number(r.pending_count||0);
  v8ChatSetDeviceState('ready','این دستگاه برای پیامرسان آماده است · '+V8.chat.device.label,pending?'<button type="button" class="v7-mini primary" onclick="v8ChatOpenDevices()">'+toFaDigits(pending)+' دستگاه در انتظار</button>':'<button type="button" class="v7-mini" onclick="v8ChatOpenDevices()">دستگاه‌های من</button>');
}
async function v8ChatOpenDevices(){
  try{await v8ChatRefreshDeviceApprovals();v8ChatRenderDevices();openM('v8-m-chat-devices');}catch(e){toast(e.message||String(e),'err');}
}
function v8ChatRenderDevices(){
  var box=g('v8-chat-devices-list');if(!box)return;var rows=V8.chat.myDevices||[];
  box.innerHTML=rows.map(function(d){var pending=!d.is_active;return '<div class="v8-device-row"><div><b>'+escHtml(d.label||'مرورگر')+'</b><small>'+(pending?'در انتظار تأیید':'تأییدشده')+(Number(d.id)===Number(V8.chat.device.id)?' · این دستگاه':'')+'</small></div>'+(pending?'<div class="v8-device-approve"><input class="fi" inputmode="numeric" maxlength="6" id="v8-device-code-'+d.id+'" placeholder="کد ۶ رقمی"><button type="button" class="v7-mini primary" onclick="v8ChatApproveDevice('+d.id+')">تأیید</button></div>':'<span class="v8-device-ok">✓</span>')+'</div>';}).join('')||'<div class="v7-empty">دستگاهی ثبت نشده است.</div>';
}
async function v8ChatApproveDevice(pendingId){
  try{
    var input=g('v8-device-code-'+pendingId),code=(input&&input.value||'').replace(/\D/g,'');if(code.length!==6)throw new Error('کد شش‌رقمی نمایش‌داده‌شده روی دستگاه جدید را وارد کنید');
    var r=await api('/v8/chat/device_approval_challenge',{current_device_id:V8.chat.device.id,pending_device_id:pendingId,approval_code:code});if(!r.ok)throw new Error(r.error);
    var plain=await crypto.subtle.decrypt({name:'RSA-OAEP'},V8.chat.device.privateKey,v8Unb64(r.encrypted_challenge)),approved=await api('/v8/chat/device_approve',{current_device_id:V8.chat.device.id,pending_device_id:pendingId,challenge:v8B64(plain)});if(!approved.ok)throw new Error(approved.error);
    toast('دستگاه جدید تأیید شد. کلید پیام‌های آینده خودکار نوسازی می‌شود.','ok');await v8ChatRefreshDeviceApprovals();v8ChatRenderDevices();
  }catch(e){toast(e.message||String(e),'err');}
}
async function v8ChatGetKeyRow(cid,version){return await v8ChatStoreGet(v8ChatConversationKeyId(cid,version));}
async function v8ChatGetRawKey(cid,version){var row=await v8ChatGetKeyRow(cid,version);return row&&row.raw?v8Unb64(row.raw):null;}
async function v8ChatEnvelopeHash(text){var raw=new TextEncoder().encode(String(text||'')),hash=await crypto.subtle.digest('SHA-256',raw);return Array.from(new Uint8Array(hash)).map(function(x){return x.toString(16).padStart(2,'0');}).join('');}
async function v8ChatSaveRawKey(cid,version,raw,envelopeHash){await v8ChatStorePut({id:v8ChatConversationKeyId(cid,version),raw:v8B64(raw),envelopeHash:envelopeHash||'',savedAt:Date.now()});V8.chat.keys[cid+':'+version]=true;}
async function v8ChatImportAes(raw){return crypto.subtle.importKey('raw',raw,{name:'AES-GCM'},false,['encrypt','decrypt']);}
async function v8ChatUnwrapKeys(cid,wrapped){
  var device=await v8ChatEnsureDevice();
  for(var i=0;i<(wrapped||[]).length;i++){
    var x=wrapped[i],row=await v8ChatGetKeyRow(cid,x.key_version),hash=await v8ChatEnvelopeHash(x.wrapped_key);
    if(row&&row.raw&&row.envelopeHash===hash)continue;
    try{var raw=await crypto.subtle.decrypt({name:'RSA-OAEP'},device.privateKey,v8Unb64(x.wrapped_key));await v8ChatSaveRawKey(cid,x.key_version,new Uint8Array(raw),hash);}catch(e){}
  }
}
async function v8ChatWrapRawForDevices(raw,devices){
  var envelopes=[];
  for(var i=0;i<devices.length;i++){
    var d=devices[i],jwk=typeof d.public_key_jwk==='string'?JSON.parse(d.public_key_jwk):d.public_key_jwk,pub=await crypto.subtle.importKey('jwk',jwk,{name:'RSA-OAEP',hash:'SHA-256'},false,['encrypt']),wrapped=await crypto.subtle.encrypt({name:'RSA-OAEP'},pub,raw);
    envelopes.push({device_id:d.device_id,wrapped_key:v8B64(wrapped)});
  }
  return envelopes;
}
function v8ChatSetComposeEnabled(enabled){
  ['v8-chat-text','v8-chat-send','v8-chat-attach'].forEach(function(id){var el=g(id);if(el)el.disabled=!enabled;});
  var text=g('v8-chat-text');if(text)text.placeholder=enabled?'پیام بنویسید...':'در حال آماده‌سازی رمزگذاری...';
}
function v8ChatSleep(ms){return new Promise(function(resolve){setTimeout(resolve,ms);});}
async function v8ChatWaitForRotatedKey(cid,version){
  for(var attempt=0;attempt<16;attempt++){
    await v8ChatSleep(500);
    var r=await api('/v8/chat/messages',{conversation_id:cid,after_id:0,limit:1,device_id:V8.chat.device.id});
    if(!r.ok)throw new Error(r.error);
    await v8ChatUnwrapKeys(cid,r.wrapped_keys||[]);
    var raw=await v8ChatGetRawKey(cid,version);
    if(raw&&!r.conversation.needs_key_rotation){
      if(V8.chat.current&&Number(V8.chat.current.id)===Number(cid)){
        V8.chat.current.key_version=r.conversation.key_version;
        V8.chat.current.needs_key_rotation=false;
      }
      return true;
    }
  }
  throw new Error('آماده‌سازی کلید گفتگو بیش از حد طول کشید. دوباره تلاش کنید.');
}
async function v8ChatRotateKey(options){
  options=options||{};var c=V8.chat.current;if(!c)return false;
  var claim=await api('/v8/chat/key_rotation_claim',{conversation_id:c.id,device_id:V8.chat.device.id});
  if(!claim.ok)throw new Error(claim.error);
  c.key_version=claim.key_version;
  if(claim.ready)return true;
  if(!claim.claimed)return v8ChatWaitForRotatedKey(c.id,claim.key_version);
  var r=await api('/v8/chat/member_devices',{conversation_id:c.id});if(!r.ok)throw new Error(r.error);
  if(!(r.rows||[]).length)throw new Error('هیچ دستگاه فعالی برای اعضای این گفتگو ثبت نشده است');
  var key=await crypto.subtle.generateKey({name:'AES-GCM',length:256},true,['encrypt','decrypt']),raw=new Uint8Array(await crypto.subtle.exportKey('raw',key)),env=await v8ChatWrapRawForDevices(raw,r.rows),saved=await api('/v8/chat/keys_save',{conversation_id:c.id,key_version:r.key_version,device_id:V8.chat.device.id,claim_token:claim.claim_token,envelopes:env});
  if(!saved.ok)throw new Error(saved.error);
  await v8ChatSaveRawKey(c.id,r.key_version,raw);c.key_version=r.key_version;c.needs_key_rotation=!saved.rotation_complete;
  if(!options.silent)toast('رمزگذاری گفتگو آماده شد','ok');
  return saved.rotation_complete;
}
async function v8ChatEnsureConversationReady(){
  var c=V8.chat.current;if(!c||V8.chat.rotating)return;
  var raw=await v8ChatGetRawKey(c.id,c.key_version);
  if(raw&&!c.needs_key_rotation){V8.chat.lastError=null;v8ChatRenderKeyState();return;}
  V8.chat.rotating=true;V8.chat.lastError=null;v8ChatSetComposeEnabled(false);v8ChatRenderKeyState();
  try{
    if(!raw&&!c.needs_key_rotation){
      var begin=await api('/v8/chat/key_rotation_begin',{conversation_id:c.id,device_id:V8.chat.device.id,reason:'missing_local_key'});if(!begin.ok)throw new Error(begin.error);c.key_version=begin.key_version;c.needs_key_rotation=true;
    }
    await v8ChatRotateKey({silent:true});
    await v8ChatLoadMessages(true,true);
  }catch(e){V8.chat.lastError=e.message||String(e);}
  finally{V8.chat.rotating=false;v8ChatRenderKeyState();}
}
async function v8ChatRetrySecurity(){V8.chat.lastError=null;await v8ChatEnsureConversationReady();}
async function v8ChatInit(){
  if(!CU||!can('chat.use'))return;
  if(V8.chat.initializing)return;V8.chat.initializing=true;
  try{
    await v8ChatGetMode();
    if(v8ChatServerMode()){
      V8.chat.device={id:0,userId:CU.id,label:'شبکه داخلی',pending:false};v8ChatApplyModeUi();
      await v8ChatLoadConversations();
      if(!V8.chat.poll)V8.chat.poll=setInterval(function(){var p=document.querySelector('#pg24.page.active');if(p)v8ChatPoll();},7000);
      return;
    }
    var device=await v8ChatEnsureDevice();
    if(device.pending){v8ChatRenderPendingDevice();if(!V8.chat.pendingPoll)V8.chat.pendingPoll=setInterval(async function(){var p=document.querySelector('#pg24.page.active');if(!p)return;try{var d=await v8ChatEnsureDevice(true);if(!d.pending){clearInterval(V8.chat.pendingPoll);V8.chat.pendingPoll=null;await v8ChatLoadConversations();await v8ChatRefreshDeviceApprovals();}}catch(e){}},5000);return;}
    await v8ChatLoadConversations();await v8ChatRefreshDeviceApprovals();
    if(!V8.chat.poll)V8.chat.poll=setInterval(function(){var p=document.querySelector('#pg24.page.active');if(p&&!V8.chat.rotating)v8ChatPoll();},7000);
  }catch(e){V8.chat.lastError=e.message||String(e);v8ChatSetDeviceState('error',V8.chat.lastError);var box=g('v8-conversations');if(box)box.innerHTML='<div class="v8-lock-alert">'+escHtml(V8.chat.lastError)+'</div>';}
  finally{V8.chat.initializing=false;}
}
// ── Unread badge + new-message alerts ───────────────────────────────────────
// The sidebar badge used to be written only by v8ChatLoadConversations, which
// runs only while the messenger page is open, so someone working on tasks
// never learned that a message had arrived. This watcher runs on its own
// interval regardless of the active page and reuses the app's existing alert
// layer (toast + blinking tab title + optional desktop notification).
function v8ChatSetBadge(total){
  total=Number(total||0);V8.chat.unreadTotal=total;
  var badge=g('v8-chat-badge');if(!badge)return;
  badge.textContent=toFaDigits(total>99?'99+':total);
  badge.style.display=total?'':'none';
}
async function v8ChatUnreadTick(){
  if(!CU||!can('chat.use')||V8.chat.unreadBusy)return;
  V8.chat.unreadBusy=true;
  try{
    var r=await api('/v8/chat/unread_summary',{});
    if(!r||!r.ok)return;
    var total=Number(r.total||0),latest=Number(r.latest_id||0);
    v8ChatSetBadge(total);
    // Alert once per new message id, and never for a conversation the user is
    // already reading - v8ChatPoll marks those read as they arrive.
    if(!latest||latest<=V8.chat.lastAlertId){if(!total)V8.chat.lastAlertId=0;return;}
    var first=!V8.chat.lastAlertId&&!V8.chat.unreadSeeded;
    V8.chat.lastAlertId=latest;V8.chat.unreadSeeded=true;
    if(first)return; // don't shout about the backlog that existed at login
    var who=r.latest_sender||'',where=r.latest_title||'',
        line=who?('پیام جدید از '+who+(where&&where!==who?(' در «'+where+'»'):'')):'پیام جدید در پیامرسان';
    if(!(document.querySelector('#pg24.page.active')&&!tabIsHiddenOrUnfocused()))toast('💬 '+line,'inf');
    if(tabIsHiddenOrUnfocused()){
      notifyDesktop(who||'پیام جدید',where&&where!==who?(where+' — پیام جدید دارید'):'پیام جدید دارید');
      startTitleAlert('💬 پیام جدید! - تسک هاب',1);
    }
  }catch(e){}
  finally{V8.chat.unreadBusy=false;}
}
function v8ChatStartUnreadWatch(){
  if(!CU||!can('chat.use')){v8ChatStopUnreadWatch();return;}
  // applyRole also runs after an account edit; restarting the timer there must
  // not reset the alert baseline, or the next arriving message goes unnoticed.
  if(V8.chat.unreadTimer)return;
  v8ChatUnreadTick();
  V8.chat.unreadTimer=setInterval(v8ChatUnreadTick,20000);
}
function v8ChatStopUnreadWatch(){
  if(V8.chat.unreadTimer){clearInterval(V8.chat.unreadTimer);V8.chat.unreadTimer=null;}
  V8.chat.lastAlertId=0;V8.chat.unreadSeeded=false;v8ChatSetBadge(0);
}
async function v8ChatLoadConversations(){
  try{
    await v8ChatGetMode();
    var payload={};
    if(!v8ChatServerMode()){
      await v8ChatEnsureDevice();if(V8.chat.device.pending){v8ChatRenderPendingDevice();return;}
      payload.device_id=V8.chat.device.id;
    }
    var r=await api('/v8/chat/conversations',payload);if(!r.ok)return toast(r.error,'err');
    if(r.server_device_id&&v8ChatServerMode())V8.chat.device.id=r.server_device_id;
    V8.chat.conversations=r.rows||[];var total=V8.chat.conversations.reduce(function(a,x){return a+Number(x.unread_count||0);},0);v8ChatSetBadge(total);if(V8.chat.current){var fresh=V8.chat.conversations.find(function(x){return Number(x.id)===Number(V8.chat.current.id);});if(fresh)V8.chat.current=fresh;}v8ChatRenderConversations();
  }catch(e){toast(e.message||String(e),'err');}
}
function v8ChatConversationTitle(c){if(c&&c.kind==='team')return 'گروه تیم';if(c&&c.title)return c.title;var other=(c&&c.members||[]).find(function(x){return Number(x.user_id)!==Number(CU.id);});return other?(other.display_name||other.username):'گفتگوی خصوصی';}
function v8ChatTodayKey(){var d=new Date();return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');}
function v8ChatConvStamp(v){
  if(!v)return '';
  var day=v8ChatDayKey(v);
  return day===v8ChatTodayKey()?v8ChatTime(v):v8ChatDayLabel(day);
}
function v8ChatRenderConversations(){
  var box=g('v8-conversations');if(!box)return;var q=((g('v8-chat-list-search')&&g('v8-chat-list-search').value)||'').trim().toLowerCase(),rows=(V8.chat.conversations||[]).filter(function(c){var names=(c.members||[]).map(function(x){return x.display_name||x.username||'';}).join(' ');return !q||(v8ChatConversationTitle(c)+' '+names).toLowerCase().indexOf(q)>=0;});
  box.innerHTML=rows.map(function(c){
    var title=v8ChatConversationTitle(c),
        active=V8.chat.current&&Number(V8.chat.current.id)===Number(c.id),
        unread=Number(c.unread_count||0),
        // A private chat shows the person, so an initials avatar identifies it
        // far faster than the same generic icon on every row.
        avatar=c.kind==='direct'
          ? '<span class="v8-conv-icon v8-avatar tone-'+v8ChatTone(title)+'">'+escHtml(v8ChatInitials(title))+'</span>'
          : '<span class="v8-conv-icon">'+({announcement:'📢',team:'👥',group:'💬'}[c.kind]||'💬')+'</span>',
        sub=c.kind==='direct'?'گفتگوی خصوصی':toFaDigits(c.member_count||0)+' عضو';
    if(!c.last_message_at)sub+=' · بدون پیام';
    return '<button type="button" class="v8-conv '+(active?'active':'')+(unread?' unread':'')+'" onclick="v8ChatOpen('+c.id+')">'+avatar+
      '<span class="v8-conv-info"><b>'+escHtml(title)+'</b><small>'+escHtml(sub)+'</small></span>'+
      '<span class="v8-conv-side"><em class="v8-conv-time">'+escHtml(v8ChatConvStamp(c.last_message_at))+'</em>'+
      (unread?'<span class="v8-unread">'+toFaDigits(unread>99?'99+':unread)+'</span>':'')+'</span></button>';
  }).join('')||'<div class="v7-empty">گفتگویی پیدا نشد.</div>';
}
function v8ChatBackToList(){var shell=g('v8-chat-shell');if(shell)shell.classList.remove('mobile-open');}
function v8ChatMemberSummary(c){var names=(c.members||[]).filter(function(x){return c.kind!=='direct'||Number(x.user_id)!==Number(CU.id);}).map(function(x){return x.display_name||x.username;});return names.join('، ');}
function v8ChatRenderMemberWarning(){
  var c=V8.chat.current,box=g('v8-chat-member-warning');if(!box||!c)return;
  if(v8ChatServerMode()){box.innerHTML='';return;}
  var missing=(c.members||[]).filter(function(x){return !Number(x.device_count||0);});
  box.innerHTML=missing.length?'<div class="v8-member-warning">'+toFaDigits(missing.length)+' عضو هنوز پیامرسان را روی هیچ دستگاهی فعال نکرده است: <b>'+missing.map(function(x){return escHtml(x.display_name||x.username);}).join('، ')+'</b>. پیام‌های قبل از اولین فعال‌سازی برای آن دستگاه‌ها قابل بازشدن نیست.</div>':'';
}
function v8ChatCanManageGroup(c){return !!(c&&c.kind==='group'&&['owner','admin'].indexOf(c.member_role)>=0&&can('chat.manage_groups'));}
function v8ChatUpdateActions(){var c=V8.chat.current,manage=v8ChatCanManageGroup(c),members=g('v8-chat-manage-members'),edit=g('v8-chat-edit'),del=g('v8-chat-delete');if(members)members.style.display=manage?'':'none';if(edit)edit.style.display=manage?'':'none';if(del){var removable=!!c&&['direct','group'].indexOf(c.kind)>=0;del.style.display=removable?'':'none';del.textContent=!c?'حذف':(c.kind==='direct'?'حذف گفتگو':(manage?'حذف گروه':'ترک گروه'));}}
async function v8ChatOpen(id){
  var c=(V8.chat.conversations||[]).find(function(x){return Number(x.id)===Number(id);});if(!c)return;V8.chat.current=c;V8.chat.messages=[];V8.chat.lastError=null;
  V8.chat.hasMore=false;V8.chat.loadingOlder=false;V8.chat.stickBottom=true;
  var shell=g('v8-chat-shell');if(shell)shell.classList.add('mobile-open');g('v8-chat-empty').style.display='none';g('v8-chat-active').style.display='flex';var headTitle=v8ChatConversationTitle(c);g('v8-chat-title').textContent=headTitle;g('v8-chat-members').textContent=v8ChatMemberSummary(c)||({announcement:'اطلاعیه‌های سازمان',team:'گروه تیمی'}[c.kind]||'');
  var headAvatar=g('v8-chat-avatar');
  if(headAvatar){
    headAvatar.className='v8-avatar v8-head-avatar tone-'+v8ChatTone(headTitle);
    headAvatar.textContent=c.kind==='direct'?v8ChatInitials(headTitle):({announcement:'📢',team:'👥'}[c.kind]||'💬');
  }
  g('v8-chat-search').value='';v8ChatUpdateActions();v8ChatRenderMemberWarning();v8ChatRenderConversations();v8ChatSetComposeEnabled(false);
  try{await v8ChatLoadMessages(true,false);}catch(e){V8.chat.lastError=e.message||String(e);v8ChatRenderKeyState();}
}
// Opening a conversation now asks for the newest page (after_id=0) and pages
// backwards on demand, instead of loading the oldest rows and stopping there.
async function v8ChatLoadMessages(reset,skipReady){
  var c=V8.chat.current;if(!c)return;var after=reset?0:(V8.chat.messages.length?V8.chat.messages[V8.chat.messages.length-1].id:0),payload={conversation_id:c.id,after_id:after,limit:reset?60:200};
  if(!v8ChatServerMode()){var device=await v8ChatEnsureDevice();payload.device_id=device.id;}
  var r=await api('/v8/chat/messages',payload);if(!r.ok)throw new Error(r.error);
  if(r.server_device_id&&v8ChatServerMode())V8.chat.device.id=r.server_device_id;
  c.key_version=r.conversation.key_version;c.needs_key_rotation=v8ChatServerMode()?false:!!r.conversation.needs_key_rotation;c.can_post=r.conversation.can_post;
  if(!v8ChatServerMode())await v8ChatUnwrapKeys(c.id,r.wrapped_keys||[]);
  var rows=r.rows||[];if(!v8ChatServerMode()){for(var i=0;i<rows.length;i++)rows[i].plain=await v8ChatDecryptMessage(rows[i]);}
  if(reset){V8.chat.messages=rows;V8.chat.hasMore=!!r.has_more;V8.chat.stickBottom=true;}
  else if(rows.length){V8.chat.messages=V8.chat.messages.concat(rows);}
  if(reset||rows.length)v8ChatRenderMessages();
  v8ChatRenderMemberWarning();
  if(V8.chat.messages.length){var last=V8.chat.messages[V8.chat.messages.length-1];api('/v8/chat/read',{conversation_id:c.id,message_id:last.id});}
  if(v8ChatServerMode())v8ChatRenderKeyState();else if(!skipReady)await v8ChatEnsureConversationReady();else v8ChatRenderKeyState();
}
async function v8ChatLoadOlder(){
  var c=V8.chat.current,box=g('v8-messages');
  if(!c||!V8.chat.hasMore||V8.chat.loadingOlder||!V8.chat.messages.length)return;
  V8.chat.loadingOlder=true;
  var anchorHeight=box?box.scrollHeight:0,anchorTop=box?box.scrollTop:0;
  try{
    var payload={conversation_id:c.id,before_id:V8.chat.messages[0].id,limit:60};
    if(!v8ChatServerMode())payload.device_id=(await v8ChatEnsureDevice()).id;
    var r=await api('/v8/chat/messages',payload);if(!r.ok)throw new Error(r.error);
    var rows=r.rows||[];
    if(!v8ChatServerMode()){for(var i=0;i<rows.length;i++)rows[i].plain=await v8ChatDecryptMessage(rows[i]);}
    V8.chat.hasMore=!!r.has_more;V8.chat.messages=rows.concat(V8.chat.messages);
    V8.chat.stickBottom=false;v8ChatRenderMessages();
    // Keep the message the user was reading under the cursor instead of
    // jumping to the top of the freshly prepended block.
    if(box)box.scrollTop=anchorTop+(box.scrollHeight-anchorHeight);
  }catch(e){toast(e.message||String(e),'err');}
  finally{V8.chat.loadingOlder=false;}
}
function v8ChatOnScroll(){
  var box=g('v8-messages');if(!box)return;
  var distance=box.scrollHeight-box.scrollTop-box.clientHeight;
  V8.chat.stickBottom=distance<70;
  var jump=g('v8-chat-jump');if(jump)jump.classList.toggle('show',distance>240);
  if(box.scrollTop<60&&V8.chat.hasMore&&!V8.chat.loadingOlder)v8ChatLoadOlder();
}
function v8ChatScrollToBottom(){var box=g('v8-messages');if(box){box.scrollTop=box.scrollHeight;V8.chat.stickBottom=true;}var jump=g('v8-chat-jump');if(jump)jump.classList.remove('show');}
async function v8ChatDecryptMessage(row){try{var raw=await v8ChatGetRawKey(row.conversation_id,row.key_version);if(!raw)return null;var key=await v8ChatImportAes(raw),aad=new TextEncoder().encode(row.aad||''),plain=await crypto.subtle.decrypt({name:'AES-GCM',iv:v8Unb64(row.iv),additionalData:aad},key,v8Unb64(row.ciphertext));return JSON.parse(new TextDecoder().decode(plain));}catch(e){return null;}}
async function v8ChatRenderKeyState(){
  var c=V8.chat.current,box=g('v8-chat-key-alert');if(!c||!box)return;
  if(v8ChatServerMode()){
    V8.chat.lastError=null;box.innerHTML='';v8ChatSetComposeEnabled(!!c.can_post);return;
  }
  if(V8.chat.lastError){v8ChatSetComposeEnabled(false);box.innerHTML='<div class="v8-lock-alert">آماده‌سازی رمزگذاری انجام نشد: '+escHtml(V8.chat.lastError)+' <button class="v7-mini primary" onclick="v8ChatRetrySecurity()">تلاش دوباره</button></div>';return;}
  if(V8.chat.rotating){v8ChatSetComposeEnabled(false);box.innerHTML='<div class="v8-key-progress"><span class="v8-spinner"></span> در حال ساخت و توزیع خودکار کلید گفتگو...</div>';return;}
  var raw=await v8ChatGetRawKey(c.id,c.key_version),ready=!!raw&&!c.needs_key_rotation;
  if(!ready){v8ChatSetComposeEnabled(false);box.innerHTML='<div class="v8-key-progress"><span class="v8-spinner"></span> در حال فعال‌سازی این دستگاه برای گفتگو...</div>';return;}
  if(!c.can_post){v8ChatSetComposeEnabled(false);box.innerHTML='<div class="v8-info-note">این گفتگو فقط برای مشاهده است.</div>';return;}
  v8ChatSetComposeEnabled(true);box.innerHTML='';
}
function v8ChatDayKey(v){return String(v||'').slice(0,10);}
function v8ChatDayLabel(key){
  var p=String(key||'').split('-').map(Number);
  if(p.length!==3||!p[0])return toFaDigits(key||'');
  var now=new Date(),today=new Date(now.getFullYear(),now.getMonth(),now.getDate()),
      day=new Date(p[0],p[1]-1,p[2]),diff=Math.round((today-day)/86400000);
  if(diff===0)return 'امروز';
  if(diff===1)return 'دیروز';
  var j=g2j(p[0],p[1],p[2]);
  return toFaDigits(j[0]+'/'+String(j[1]).padStart(2,'0')+'/'+String(j[2]).padStart(2,'0'));
}
function v8ChatTime(v){var m=String(v||'').match(/[T ](\d{2}):(\d{2})/);return m?toFaDigits(m[1]+':'+m[2]):'';}
function v8ChatInitials(name){
  var parts=String(name||'').trim().split(/\s+/).filter(Boolean);
  if(!parts.length)return '؟';
  return parts.length===1?parts[0].slice(0,1):(parts[0].slice(0,1)+parts[1].slice(0,1));
}
// Stable colour per person so the same face keeps the same avatar tone.
function v8ChatTone(seed){var n=0,s=String(seed||'');for(var i=0;i<s.length;i++)n=(n*31+s.charCodeAt(i))>>>0;return n%6;}
function v8ChatFileSize(bytes){
  var n=Number(bytes||0);
  if(n<1024)return toFaDigits(n)+' بایت';
  if(n<1048576)return toFaDigits((n/1024).toFixed(1))+' کیلوبایت';
  return toFaDigits((n/1048576).toFixed(1))+' مگابایت';
}
function v8ChatRenderMessages(){
  var box=g('v8-messages');if(!box)return;
  var q=((g('v8-chat-search')&&g('v8-chat-search').value)||'').trim().toLowerCase(),
      searching=!!q,all=V8.chat.messages||[],
      rows=searching?all.filter(function(x){return x.plain&&String(x.plain.text||x.plain.fileName||'').toLowerCase().indexOf(q)>=0;}):all;
  var html='';
  if(V8.chat.hasMore&&!searching)
    html+='<button type="button" class="v8-load-older" onclick="v8ChatLoadOlder()"'+(V8.chat.loadingOlder?' disabled':'')+'>'+(V8.chat.loadingOlder?'در حال بارگذاری...':'↑ پیام‌های قدیمی‌تر')+'</button>';
  var lastDay='',lastSender=null,lastAt=0;
  html+=rows.map(function(x){
    var out='',day=v8ChatDayKey(x.created_at);
    if(day&&day!==lastDay&&!searching){
      out+='<div class="v8-day-sep"><span>'+escHtml(v8ChatDayLabel(day))+'</span></div>';
      lastDay=day;lastSender=null;lastAt=0;
    }
    var mine=Number(x.sender_user_id)===Number(CU.id),
        sender=mine?'شما':(x.display_name||x.username||'کاربر'),
        at=Date.parse(x.created_at)||0,
        // Consecutive messages from one person within five minutes read as a
        // single turn, so the name and avatar are not repeated on every line.
        grouped=!searching&&lastSender===x.sender_user_id&&!!at&&!!lastAt&&(at-lastAt)<300000,
        body='';
    lastSender=x.sender_user_id;lastAt=at;
    if(x.plain&&x.message_kind==='file'){
      var fileAction=can('chat.file_download')?'<button type="button" class="v8-message-file" onclick="v8ChatDownloadFile('+x.id+')">📎 <span>'+escHtml(x.plain.fileName||'فایل')+'</span><small>'+escHtml(v8ChatFileSize(x.plain.originalSize))+'</small></button>':'<div class="v8-message-unavailable">📎 فایل پیوست — مجوز دانلود ندارید</div>';
      body=(x.plain.text?'<div class="v8-message-text" dir="auto">'+escHtml(x.plain.text)+'</div>':'')+fileAction;
    }else if(x.plain){body='<div class="v8-message-text" dir="auto">'+escHtml(x.plain.text||'').replace(/\n/g,'<br>')+'</div>';}
    else body='<div class="v8-message-unavailable">🔒 '+(v8ChatServerMode()?'این پیام مربوط به رمزگذاری نسخه قبلی است و در حالت شبکه داخلی قابل بازیابی نیست.':'این پیام قبل از فعال‌شدن کلید آن روی این دستگاه ارسال شده است.')+'</div>';
    // data-uid lets the shop's cosmetics (avatar frame, bubble colour, title)
    // decorate each sender's messages after rendering; see gameDecorateChat.
    var uid=escHtml(String(x.sender_user_id)),
        avatar=(mine||grouped)?'':'<span class="v8-avatar tone-'+v8ChatTone(x.sender_user_id)+'" data-uid="'+uid+'">'+escHtml(v8ChatInitials(sender))+'</span>',
        name=(mine||grouped)?'':'<b class="v8-message-sender" data-uid="'+uid+'">'+escHtml(sender)+'</b>';
    out+='<div class="v8-msg-row '+(mine?'mine':'other')+(grouped?' grouped':'')+'">'+avatar+
         '<article class="v8-message '+(mine?'mine':'')+(grouped?' grouped':'')+'" data-uid="'+uid+'">'+name+body+
         '<time class="v8-message-time">'+escHtml(v8ChatTime(x.created_at))+'</time></article></div>';
    return out;
  }).join('');
  if(!rows.length)html+='<div class="v8-chat-empty v8-chat-empty-small">'+(searching?'پیامی با این جستجو پیدا نشد.':'هنوز پیامی ثبت نشده است. اولین پیام را بنویسید.')+'</div>';
  var stick=V8.chat.stickBottom;
  box.innerHTML=html;
  if(typeof gameDecorateChat==='function')gameDecorateChat(box);
  // Only jump to the newest message when the reader is already at the bottom;
  // yanking them down while they scroll back through history is the reason
  // long conversations felt unusable.
  if(stick)box.scrollTop=box.scrollHeight;
}
async function v8ChatEncryptPayload(payload,kind,fileId){var c=V8.chat.current,raw=await v8ChatGetRawKey(c.id,c.key_version);if(!raw||c.needs_key_rotation)throw new Error('رمزگذاری گفتگو هنوز آماده نشده است');var key=await v8ChatImportAes(raw),iv=crypto.getRandomValues(new Uint8Array(12)),aad='taskhub:v8:conversation:'+c.id+':key:'+c.key_version,data=new TextEncoder().encode(JSON.stringify(payload)),cipher=await crypto.subtle.encrypt({name:'AES-GCM',iv:iv,additionalData:new TextEncoder().encode(aad)},key,data);return {conversation_id:c.id,device_id:V8.chat.device.id,key_version:c.key_version,message_kind:kind||'text',ciphertext:v8B64(cipher),iv:v8B64(iv),aad:aad,client_message_id:v8RandomId(),encrypted_file_id:fileId||null};}
function v8ChatKeydown(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();v8ChatSend();}}
async function v8ChatSend(){var text=(g('v8-chat-text').value||'').trim();if(!text||!V8.chat.current)return;try{v8ChatSetComposeEnabled(false);var body=v8ChatServerMode()?{conversation_id:V8.chat.current.id,message_kind:'text',plain:{text:text,ts:Date.now()},client_message_id:v8RandomId()}:await v8ChatEncryptPayload({text:text,ts:Date.now()},'text'),r=await api('/v8/chat/message_send',body);if(!r.ok)throw new Error(r.error);g('v8-chat-text').value='';v8ChatAutoGrow();V8.chat.stickBottom=true;await v8ChatLoadMessages(false,true);v8ChatScrollToBottom();}catch(e){toast(e.message,'err');}finally{v8ChatRenderKeyState();g('v8-chat-text').focus();}}
// The composer grows with the message instead of forcing a scrollbar inside a
// two-line box, and snaps back after sending.
function v8ChatAutoGrow(){var t=g('v8-chat-text');if(!t)return;t.style.height='auto';t.style.height=Math.min(t.scrollHeight,132)+'px';}
async function v8ChatSendFile(file){
  if(!can('chat.file_upload'))return toast('مجوز ارسال عکس یا فایل را ندارید','err');
  if(!file||!V8.chat.current)return;
  try{
    if(file.size>20*1024*1024)return toast('حجم فایل باید حداکثر ۲۰ مگابایت باشد','err');
    v8ChatSetComposeEnabled(false);
    if(v8ChatServerMode()){
      toast('در حال ارسال و رمزگذاری فایل روی سرور...','inf');
      var fd=new FormData();fd.append('conversation_id',V8.chat.current.id);fd.append('file_name',file.name);fd.append('file_type',file.type||'application/octet-stream');fd.append('file',file,file.name);var headers={};if(TOKEN)headers['X-Token']=TOKEN;var upload=await fetch('/api/v8/chat/file_upload',{method:'POST',headers:headers,body:fd}),ur=await upload.json();if(!ur.ok)throw new Error(ur.error);var body={conversation_id:V8.chat.current.id,message_kind:'file',plain:{text:'فایل پیوست',fileName:file.name,fileType:file.type||'application/octet-stream',originalSize:file.size,ts:Date.now()},client_message_id:v8RandomId(),encrypted_file_id:ur.id},mr=await api('/v8/chat/message_send',body);if(!mr.ok)throw new Error(mr.error);g('v8-chat-file').value='';await v8ChatLoadMessages(false,true);toast('فایل ارسال شد','ok');return;
    }
    toast('در حال رمزگذاری فایل...','inf');var source=await file.arrayBuffer(),compressed=false;if(window.CompressionStream&&source.byteLength>2048){try{source=await new Response(new Blob([source]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer();compressed=true;}catch(e){}}
    var c=V8.chat.current,raw=await v8ChatGetRawKey(c.id,c.key_version);if(!raw||c.needs_key_rotation)throw new Error('رمزگذاری گفتگو هنوز آماده نشده است');var key=await v8ChatImportAes(raw),iv=crypto.getRandomValues(new Uint8Array(12)),fileToken=v8RandomId(),aad='taskhub:v8:conversation:'+c.id+':key:'+c.key_version+':file:'+fileToken,cipher=await crypto.subtle.encrypt({name:'AES-GCM',iv:iv,additionalData:new TextEncoder().encode(aad)},key,source),fd2=new FormData();fd2.append('conversation_id',c.id);fd2.append('key_version',c.key_version);fd2.append('device_id',V8.chat.device.id);fd2.append('encrypted_meta','v8-aes-gcm');fd2.append('file',new Blob([cipher],{type:'application/octet-stream'}),'cipher.bin');var headers2={};if(TOKEN)headers2['X-Token']=TOKEN;var upload2=await fetch('/api/v8/chat/file_upload',{method:'POST',headers:headers2,body:fd2}),ur2=await upload2.json();if(!ur2.ok)throw new Error(ur2.error);var payload={text:'فایل پیوست',fileName:file.name,fileType:file.type||'application/octet-stream',originalSize:file.size,compressed:compressed,fileIv:v8B64(iv),fileAad:aad,fileToken:fileToken},body2=await v8ChatEncryptPayload(payload,'file',ur2.id),mr2=await api('/v8/chat/message_send',body2);if(!mr2.ok)throw new Error(mr2.error);g('v8-chat-file').value='';await v8ChatLoadMessages(false,true);toast('فایل رمز‌شده ارسال شد','ok');
  }catch(e){toast(e.message,'err');}finally{v8ChatRenderKeyState();}
}
async function v8ChatDownloadFile(messageId){if(!can('chat.file_download'))return toast('مجوز دانلود فایل را ندارید','err');try{var m=(V8.chat.messages||[]).find(function(x){return Number(x.id)===Number(messageId);});if(!m||!m.plain||!m.encrypted_file_id)return;var headers={};if(TOKEN)headers['X-Token']=TOKEN;var res=await fetch('/api/v8/chat/file_download/'+m.encrypted_file_id,{headers:headers});if(!res.ok)throw new Error('دریافت فایل ناموفق بود');if(v8ChatServerMode()){var blob0=await res.blob(),url0=URL.createObjectURL(blob0),a0=document.createElement('a');a0.href=url0;a0.download=m.plain.fileName||'file';a0.click();setTimeout(function(){URL.revokeObjectURL(url0);},1000);return;}var cipher=await res.arrayBuffer(),raw=await v8ChatGetRawKey(m.conversation_id,m.key_version);if(!raw)throw new Error('کلید این فایل روی دستگاه موجود نیست');var key=await v8ChatImportAes(raw),plain=await crypto.subtle.decrypt({name:'AES-GCM',iv:v8Unb64(m.plain.fileIv),additionalData:new TextEncoder().encode(m.plain.fileAad)},key,cipher);if(m.plain.compressed&&window.DecompressionStream)plain=await new Response(new Blob([plain]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();var blob=new Blob([plain],{type:m.plain.fileType||'application/octet-stream'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=m.plain.fileName||'file';a.click();setTimeout(function(){URL.revokeObjectURL(url);},1000);}catch(e){toast('بازکردن فایل ممکن نشد: '+e.message,'err');}}
async function v8ChatPoll(){if(!V8.chat.current||V8.chat.rotating||V8.chat.polling)return;V8.chat.polling=true;try{await v8ChatLoadMessages(false,true);await v8ChatLoadConversations();}catch(e){}finally{V8.chat.polling=false;}}
async function v8ChatOpenCreate(kind){
  try{await v8ChatGetMode();if(!v8ChatServerMode())await v8ChatEnsureDevice();V8.chat.createKind=kind;g('v8-chat-create-title').textContent=kind==='direct'?'پیام خصوصی جدید':'گروه جدید';g('v8-chat-group-title-wrap').style.display=kind==='group'?'':'none';g('v8-chat-group-title').value='';g('v8-chat-user-search').value='';var r=await api('/v8/chat/users',{});if(!r.ok)return toast(r.error,'err');V8.chat.users=r.rows||[];v8ChatRenderUserPicker();openM('v8-m-chat-create');}catch(e){toast(e.message,'err');}
}
function v8ChatUserDeviceText(u){if(v8ChatServerMode())return 'آماده در شبکه داخلی';return Number(u.device_count||0)?toFaDigits(u.device_count)+' دستگاه فعال':'هنوز وارد پیامرسان نشده';}
function v8ChatRenderUserPicker(){var q=(g('v8-chat-user-search').value||'').toLowerCase(),box=g('v8-chat-users'),kind=V8.chat.createKind;box.innerHTML=(V8.chat.users||[]).filter(function(u){return Number(u.id)!==Number(CU.id)&&(!q||[u.display_name,u.username,u.team_names].join(' ').toLowerCase().indexOf(q)>=0);}).map(function(u){return '<label class="v8-check-row v8-chat-person-row"><input type="'+(kind==='direct'?'radio':'checkbox')+'" name="v8-chat-member" value="'+u.id+'"><span><b>'+escHtml(u.display_name||u.username)+'</b><small>'+escHtml(u.team_names||'بدون تیم')+'</small><em class="'+(Number(u.device_count||0)?'ready':'waiting')+'">'+escHtml(v8ChatUserDeviceText(u))+'</em></span></label>';}).join('')||'<div class="v7-empty">کاربری یافت نشد.</div>';}
async function v8ChatCreate(){var ids=Array.from(document.querySelectorAll('#v8-chat-users input:checked')).map(function(x){return Number(x.value);}),kind=V8.chat.createKind;if(!ids.length)return toast('حداقل یک عضو انتخاب کنید','err');var r=await api('/v8/chat/conversation_create',{kind:kind,title:g('v8-chat-group-title').value,member_ids:ids});if(!r.ok)return toast(r.error,'err');closeM('v8-m-chat-create');await v8ChatLoadConversations();await v8ChatOpen(r.id);}
function v8ChatOpenEdit(){var c=V8.chat.current;if(!v8ChatCanManageGroup(c))return;g('v8-chat-edit-title').value=c.title||v8ChatConversationTitle(c);openM('v8-m-chat-edit');}
async function v8ChatSaveEdit(){var c=V8.chat.current,title=(g('v8-chat-edit-title').value||'').trim();if(!c||!title)return toast('نام گروه الزامی است','err');var r=await api('/v8/chat/conversation_update',{conversation_id:c.id,title:title});if(!r.ok)return toast(r.error,'err');closeM('v8-m-chat-edit');await v8ChatLoadConversations();await v8ChatOpen(c.id);toast('نام گروه ویرایش شد','ok');}
async function v8ChatDeleteConversation(){var c=V8.chat.current;if(!c||['direct','group'].indexOf(c.kind)<0)return;var manage=v8ChatCanManageGroup(c),verb=c.kind==='direct'?'این گفتگو را از فهرست خود حذف کنید؟':(manage?'این گروه برای همه اعضا حذف شود؟':'از این گروه خارج شوید؟');if(!confirm(verb))return;var r=await api('/v8/chat/conversation_delete',{conversation_id:c.id});if(!r.ok)return toast(r.error,'err');V8.chat.current=null;V8.chat.messages=[];g('v8-chat-active').style.display='none';g('v8-chat-empty').style.display='flex';var shell=g('v8-chat-shell');if(shell)shell.classList.remove('mobile-open');await v8ChatLoadConversations();toast(r.deleted_for_all?'گروه حذف شد':(c.kind==='group'?'از گروه خارج شدید':'گفتگو از فهرست شما حذف شد'),'ok');}

async function v8ChatOpenMembers(){var c=V8.chat.current;if(!c||c.kind!=='group'||['owner','admin'].indexOf(c.member_role)<0)return;var r=await api('/v8/chat/users',{});if(!r.ok)return toast(r.error,'err');V8.chat.users=r.rows||[];g('v8-chat-member-search').value='';v8ChatRenderMemberEditor();openM('v8-m-chat-members');}
function v8ChatRenderMemberEditor(){var c=V8.chat.current,q=(g('v8-chat-member-search').value||'').toLowerCase(),members=(c&&c.members||[]).map(function(x){return Number(x.user_id);}),box=g('v8-chat-member-editor');box.innerHTML=(V8.chat.users||[]).filter(function(u){return !q||[u.display_name,u.username,u.team_names].join(' ').toLowerCase().indexOf(q)>=0;}).map(function(u){var self=Number(u.id)===Number(CU.id);return '<label class="v8-check-row v8-chat-person-row"><input type="checkbox" data-v8-edit-member="'+u.id+'" '+(members.indexOf(Number(u.id))>=0?'checked':'')+' '+(self?'disabled':'')+'><span><b>'+escHtml(u.display_name||u.username)+'</b><small>'+escHtml(u.team_names||'بدون تیم')+'</small><em class="'+(Number(u.device_count||0)?'ready':'waiting')+'">'+escHtml(v8ChatUserDeviceText(u))+(self?' · شما':'')+'</em></span></label>';}).join('');}
async function v8ChatSaveMembers(){var c=V8.chat.current;if(!c)return;var ids=Array.from(document.querySelectorAll('[data-v8-edit-member]:checked')).map(function(x){return Number(x.dataset.v8EditMember);});if(ids.indexOf(Number(CU.id))<0)ids.push(Number(CU.id));if(ids.length<2)return toast('گروه باید حداقل دو عضو داشته باشد','err');var r=await api('/v8/chat/conversation_members_save',{conversation_id:c.id,member_ids:ids});if(!r.ok)return toast(r.error,'err');closeM('v8-m-chat-members');await v8ChatLoadConversations();await v8ChatOpen(c.id);}
