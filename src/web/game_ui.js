/* global api,g,escHtml,toFaDigits,toEnDigits,D,CU,openM,closeM,toast,showPage,applyRole,can,PML,
   PERMISSION_PAGE_MAP,PAGE_DETAIL_PERMISSION_MAP,HELP_PROVIDERS,openDP,vTask,g2j,v8RenderTopbarUser,
   applySelSearch,loadCalendarData,V7 */
'use strict';

/* R13 points, coins and item shop.

   Everything here is additive: page 27 «امتیاز و فروشگاه», page 28
   «مدیریت فروشگاه», two dashboard cards, a help tab, the «ممنونم» buttons on a
   finished task and the cosmetic decorations. The server decides every rule
   (see gamification.py); this file only shows the result and sends choices. */

var GM={summary:null,shop:null,orders:null,feed:null,hall:null,board:null,history:null,
  cosmetics:{},images:{},tab:null,adminTab:null,filter:'all',boardTeam:null,boardSeason:null,
  admin:{items:null,festivals:null,festItems:null,users:null,giftItems:null,feed:null,monthly:null,
    monthKey:null,economy:null,settings:null,deliver:null,pay:null},
  buyId:null,editId:null,editImage:null,removeImage:false,festId:null,dateOrder:null,adjustUser:null,timer:null};

var GM_TYPES={leave:'مرخصی تشویقی',remote:'دورکاری یا ورود شناور',money:'پاداش مالی',
  goods:'کالا، کارت هدیه، کتاب یا دوره',cosmetic:'تزئینی',team_pot:'صندوق تیم',other:'سایر'};
var GM_TYPE_ICON={leave:'🌴',remote:'🏠',money:'💵',goods:'🎁',cosmetic:'🎨',team_pot:'🤝',other:'✨'};
var GM_FRAMES={gold:'طلایی',silver:'نقره‌ای',emerald:'زمردی',ruby:'یاقوتی',sapphire:'آبی',violet:'بنفش'};
var GM_CHATS={teal:'فیروزه‌ای',rose:'صورتی',amber:'کهربایی',violet:'بنفش',emerald:'سبز'};
var GM_ROLES={support:'پشتیبان',lead:'سرگروه',planner:'پلنر',finance:'کارشناس مالی',reporter:'کارشناس اجرایی',manager:'مدیر',admin:'مدیر سیستم'};
var GM_MEDALS=['🥇','🥈','🥉'];
var GM_TABS=[
  {key:'me',label:'👤 کارت من',perm:'gamification.view_own'},
  {key:'shop',label:'🛒 فروشگاه',perm:'shop.view'},
  {key:'orders',label:'🧾 خریدهای من',perm:'shop.buy'},
  {key:'feed',label:'📣 تاریخچه عمومی',perm:'shop.view'},
  {key:'hall',label:'🏆 تالار افتخارات',perm:'shop.view'},
  {key:'board',label:'📊 رتبه‌بندی',perm:'gamification.team_board'}
];
var GM_ADMIN_TABS=[
  {key:'items',label:'🎁 آیتم‌ها',perm:'shop.manage_items'},
  {key:'festivals',label:'🎉 جشنواره‌ها',perm:'shop.manage_festivals'},
  {key:'gift',label:'💝 هدیه',perm:'shop.gift'},
  {key:'deliver',label:'📦 لیست تحویل',perm:'shop.deliver'},
  {key:'pay',label:'💵 لیست پرداخت',perm:'shop.pay_rewards'},
  {key:'monthly',label:'⭐ ستاره ماهانه',perm:'ratings.monthly'},
  {key:'economy',label:'📊 اقتصاد سکه',perm:'economy.view'},
  {key:'settings',label:'⚙ تنظیمات',perm:'game.settings'}
];
var GM_SETTINGS=[
  ['game_shop_open','فروشگاه باز است','switch','وقتی خاموش است، امتیاز و سکه جمع می‌شود ولی خرید ممکن نیست.'],
  ['game_points_per_coin','امتیاز لازم برای هر سکه','number','پیش‌فرض ۱۰؛ هر ۱۰ امتیاز تسک یک سکه.'],
  ['game_coins_per_star','سکه هر ستاره ماهانه','number','یک ماه ۵ ستاره باید تقریباً برابر یک ماه خوب پشتیبان باشد.'],
  ['game_badge_coins','سکه جایزه هر نشان','number',''],
  ['game_quest_coins','سکه هر عضو برای مأموریت تیمی','number','به همه اعضای تیم (به‌جز مدیر) مساوی داده می‌شود.'],
  ['game_daily_softcap','تسک با امتیاز کامل در یک روز','number','از این تعداد به بعد در همان روز، امتیاز نصف می‌شود.'],
  ['game_gift_monthly_cap','سقف هدیه ماهانه هر مدیر','number','ادمین سقف ندارد.'],
  ['game_kudos_per_week','تعداد «ممنونم» هر نفر در هفته','number',''],
  ['game_kudos_coins','سکه هر «ممنونم»','number','از یک نفر به یک نفر ماهی یک‌بار سکه دارد.'],
  ['game_expiry_months','انقضای سکه (ماه)','number','هر سکه این تعداد ماه بعد از دریافت منقضی می‌شود.'],
  ['game_level_thresholds','امتیاز شروع هر سطح','text','به ترتیب تازه‌کار، کاردان، ماهر، خبره، استاد؛ با کاما جدا کنید.']
];
var GM_BADGES=[
  ['بی‌نقص','۱۰ تسک پشت‌سرهم بدون برگشت','support,lead'],
  ['سروقت','۲۰ تسک تحویل‌شده تا موعد','support,lead'],
  ['همیار','کمک در ۵ تسک مشترک','support,lead'],
  ['پرونده کامل','۲۰ تسک با اطلاعات کامل: دسته، تیم و شرح انجام کار','support,lead'],
  ['گره‌گشا','بستن تسکی که بیش از ۳۰ روز باز مانده بود','support,lead'],
  ['منظم','۴ هفته پیاپی بدون تسک معوق؛ مرخصی و تعطیلی زنجیره را قطع نمی‌کند','support,lead'],
  ['بدون صف','یک ماه بدون تسکی که بیش از یک روز کاری در صف تأیید مانده باشد','planner'],
  ['برنامه‌ریز دقیق','۹۰٪ تسک‌های تیم در ماه سر موعد','planner'],
  ['سر موعد','همه صورت‌وضعیت‌های برنامه ماه تا تاریخ برنامه ثبت شده‌اند','finance'],
  ['دفتر تمیز','صفر ایراد داده مالی در پایان ماه','finance'],
  ['سه ماه درخشان','سه ماه پیاپی ۴ ستاره یا بیشتر','planner,finance,reporter']
];

// ── small helpers ──────────────────────────────────────────────────────────
function gmFa(v){return toFaDigits(String(v==null?'':v));}
function gmNum(v){return toFaDigits(Number(v||0).toLocaleString('en-US'));}
function gmParseDate(v){
  if(!v)return null;
  var m=String(v).match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/);
  return m?new Date(+m[1],+m[2]-1,+m[3],+(m[4]||0),+(m[5]||0),+(m[6]||0)):null;
}
function gmDate(v){
  var d=gmParseDate(v);if(!d)return '—';
  var j=g2j(d.getFullYear(),d.getMonth()+1,d.getDate());
  return gmFa(j[0]+'/'+String(j[1]).padStart(2,'0')+'/'+String(j[2]).padStart(2,'0'));
}
function gmDateTime(v){
  var d=gmParseDate(v);if(!d)return '—';
  return gmDate(v)+' '+gmFa(String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0'));
}
function gmTodayIso(){var d=new Date();return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');}
function gmCoin(n){return '<span class="gm-coin"><i aria-hidden="true"></i>'+gmNum(n)+'</span>';}
function gmBar(p){p=Math.max(0,Math.min(100,Number(p)||0));return '<span class="gm-bar"><i style="width:'+p+'%"></i></span>';}
function gmEmpty(t){return '<div class="v7-empty">'+escHtml(t)+'</div>';}
function gmErr(r){return gmEmpty((r&&r.error)||'اطلاعات دریافت نشد');}
function gmUserName(id){var u=(D.u||[]).find(function(x){return Number(x.id)===Number(id);});return u?(u.display_name||u.username):('#'+id);}
function gmPeriodLabel(k){
  var p=String(k||'').split('-');if(p.length!==2)return gmFa(k||'');
  if(p[1].length===1)return (['بهار','تابستان','پاییز','زمستان'][Number(p[1])-1]||'')+' '+gmFa(p[0]);
  return (['فروردین','اردیبهشت','خرداد','تیر','مرداد','شهریور','مهر','آبان','آذر','دی','بهمن','اسفند'][Number(p[1])-1]||'')+' '+gmFa(p[0]);
}
function gmSelectOptions(rows,value,empty){
  return (empty?'<option value="">'+escHtml(empty)+'</option>':'')+rows.map(function(r){
    return '<option value="'+escHtml(String(r[0]))+'"'+(String(r[0])===String(value)?' selected':'')+'>'+escHtml(r[1])+'</option>';
  }).join('');
}
function gmSync(){if(typeof applySelSearch==='function')applySelSearch();}

// ── boot ───────────────────────────────────────────────────────────────────
function initGameUI(){
  if(typeof PERMISSION_PAGE_MAP==='object'){PERMISSION_PAGE_MAP[27]='menu.club';PERMISSION_PAGE_MAP[28]='menu.club_admin';}
  if(typeof PAGE_DETAIL_PERMISSION_MAP==='object')PAGE_DETAIL_PERMISSION_MAP[27]='shop.view';
  PML[27]=['امتیاز و فروشگاه','سطح، سکه، فروشگاه آیتم و تالار افتخارات'];
  PML[28]=['مدیریت فروشگاه','آیتم‌ها، جشنواره، هدیه، تحویل و ستاره ماهانه'];
  var nav=document.querySelector('.s-nav');
  if(nav){
    var sec=document.createElement('div');sec.className='nav-sec';sec.textContent='امتیاز و فروشگاه';
    var secs=Array.prototype.slice.call(nav.querySelectorAll('.nav-sec'));
    var anchor=secs.find(function(x){return x.textContent.trim()==='سیستم';})||secs.find(function(x){return x.textContent.trim()==='راهنما';});
    [sec,gmNavItem(27,'🏅','امتیاز و فروشگاه','menu.club'),gmNavItem(28,'🧰','مدیریت فروشگاه','menu.club_admin')]
      .forEach(function(el){if(anchor)nav.insertBefore(el,anchor);else nav.appendChild(el);});
  }
  var pages=g('pages');if(pages)pages.insertAdjacentHTML('beforeend',gmPagesHtml());
  var toasts=g('toast-c');if(toasts)toasts.insertAdjacentHTML('beforebegin',gmModalsHtml());
  gmInstallDashboardCards();
  gmInstallOverrides();
  if(typeof HELP_PROVIDERS!=='undefined')HELP_PROVIDERS.push(gmHelp);
  window.gameDecorateChat=gmDecorateChat;
  try{GM.tab=localStorage.getItem('taskhub_gm_tab')||null;GM.adminTab=localStorage.getItem('taskhub_gm_admin_tab')||null;}catch(e){}
}
function gmNavItem(pg,icon,label,perm){
  var el=document.createElement('div');el.className='nav-item';
  el.setAttribute('data-pg',String(pg));el.setAttribute('data-permission',perm);
  el.innerHTML='<span class="nav-ico">'+icon+'</span>'+label;
  el.addEventListener('click',function(){showPage(pg);var h=g('tbh'),s=g('tbs');if(h)h.textContent=PML[pg][0];if(s)s.textContent=PML[pg][1];});
  return el;
}
function gmInstallDashboardCards(){
  var pg0=g('pg0');if(!pg0)return;
  var anchor=pg0.querySelector('.dashboard-personal-grid');
  var html='<div data-dash-tab="me" class="dl-card gm-dash" id="gm-dash-me" data-permission="gamification.view_own" style="margin-top:20px;">'+
      '<div class="dl-card-t">🏅 باشگاه من<button type="button" class="v7-mini" style="margin-right:auto" onclick="showPage(27)">امتیاز و فروشگاه ›</button></div>'+
      '<div id="gm-dash-me-body">'+gmEmpty('در حال بارگذاری...')+'</div></div>'+
    '<div data-dash-tab="team" class="dl-card gm-dash" id="gm-dash-team" data-permission="gamification.team_board" style="margin-top:20px;">'+
      '<div class="dl-card-t">🎯 مأموریت‌های تیم این ماه</div><div id="gm-dash-team-body">'+gmEmpty('در حال بارگذاری...')+'</div></div>';
  if(anchor)anchor.insertAdjacentHTML('beforebegin',html);else pg0.insertAdjacentHTML('beforeend',html);
}
function gmInstallOverrides(){
  var baseShow=showPage;
  showPage=function(n){
    baseShow(n);var num=Number(n);
    if(num===27&&document.querySelector('#pg27.page.active'))gmOpenClub();
    if(num===28&&document.querySelector('#pg28.page.active'))gmOpenAdmin();
    if(num===0)gmLoadSummary(true);
  };
  var baseApply=applyRole;
  applyRole=function(){baseApply();gmAfterRole();};
  if(typeof v8RenderTopbarUser==='function'){var baseTop=v8RenderTopbarUser;v8RenderTopbarUser=function(){baseTop();gmDecorateTopbar();};}
  if(typeof vTask==='function'){var baseTask=vTask;vTask=function(id){baseTask(id);try{gmTaskKudos(id);}catch(e){}};}
  GM.timer=setInterval(function(){if(CU&&!document.hidden&&document.querySelector('#pg0.page.active'))gmLoadSummary(true);},120000);
}
function gmAfterRole(){if(!CU)return;gmLoadCosmetics();gmLoadSummary(true);}

// ── cosmetics ──────────────────────────────────────────────────────────────
async function gmLoadCosmetics(){
  var r=await api('/game/cosmetics',{});
  if(!r||!r.ok)return;
  GM.cosmetics=r.map||{};gmDecorateTopbar();
  var box=g('v8-messages');if(box)gmDecorateChat(box);
}
function gmDecorateTopbar(){
  if(!CU)return;var c=GM.cosmetics[String(CU.id)]||{};
  var av=document.querySelector('#topbar-user .v8-user-avatar');
  if(av){av.className=av.className.replace(/\s*gm-frame-\w+/g,'');if(c.frame)av.classList.add('gm-frame-'+c.frame);}
  var small=document.querySelector('#topbar-user .v8-user-copy small');
  if(small){var old=small.querySelector('.gm-title');if(old)old.remove();if(c.title)small.insertAdjacentHTML('afterbegin','<span class="gm-title">'+escHtml(c.title)+' · </span>');}
}
function gmDecorateChat(box){
  if(!box)return;
  box.querySelectorAll('[data-uid]').forEach(function(el){
    var c=GM.cosmetics[el.getAttribute('data-uid')];if(!c)return;
    if(el.classList.contains('v8-avatar')){if(c.frame)el.classList.add('gm-frame-'+c.frame);}
    else if(el.classList.contains('v8-message')){if(c.chat)el.classList.add('gm-chat-'+c.chat);}
    else if(el.classList.contains('v8-message-sender')&&c.title&&!el.querySelector('.gm-title'))
      el.insertAdjacentHTML('beforeend',' <small class="gm-title">'+escHtml(c.title)+'</small>');
  });
}

// ── summary and dashboard ──────────────────────────────────────────────────
async function gmLoadSummary(silent){
  if(!CU||!(can('gamification.view_own')||can('gamification.team_board')))return null;
  var r=await api('/game/summary',{});
  if(r&&r.ok){GM.summary=r;gmRenderDash();gmRenderWalletChip();}
  else if(!silent&&r&&!r.forbidden)toast(r.error||'بخش امتیاز در دسترس نیست','err');
  return r;
}
function gmLevelHtml(s){
  var lv=s&&s.level;if(!lv)return '';
  var next=lv.next!=null?'<small>'+gmNum(lv.to_next)+' امتیاز تا سطح بعد</small>':'<small>بالاترین سطح</small>';
  return '<div class="gm-level"><div class="gm-level-badge">'+escHtml(lv.title)+'</div><div class="gm-level-main"><b>'+gmNum(lv.points)+' امتیاز</b>'+gmBar(lv.progress)+next+'</div></div>';
}
function gmStatsHtml(s){
  var coins=s.coins||{},season=s.season||{},rank=s.rank,items=[];
  items.push('<div class="gm-stat"><span>موجودی سکه</span>'+gmCoin(coins.balance||0)+
    (coins.expiring_soon?'<small class="gm-warn">'+gmNum(coins.expiring_soon)+' سکه تا یک ماه دیگر منقضی می‌شود</small>':'')+'</div>');
  items.push('<div class="gm-stat"><span>'+escHtml(season.label||'فصل جاری')+'</span><b>'+gmNum(season.points||0)+' امتیاز</b></div>');
  if(rank&&rank.me)items.push('<div class="gm-stat"><span>جایگاه در تیم</span><b>'+gmFa(rank.me.position)+' از '+gmFa(rank.total)+'</b>'+
    (rank.gap?'<small>'+gmNum(rank.gap)+' امتیاز تا نفر بالاتر</small>':'')+'</div>');
  return '<div class="gm-stats">'+items.join('')+'</div>';
}
function gmBadgesHtml(list){
  if(!list||!list.length)return '';
  return '<div class="gm-badges">'+list.map(function(b){return '<span class="gm-badge">🎖 '+escHtml(b.title||b.badge_key)+'</span>';}).join('')+'</div>';
}
function gmQuestsHtml(s){
  var q=(s&&s.quests)||[];
  if(!q.length)return gmEmpty(s&&s.team?'مأموریتی برای این ماه تعریف نشده است.':'برای دیدن مأموریت‌ها باید عضو یک تیم باشید.');
  return '<div class="gm-quests">'+(s.team?'<div class="gm-quest-team">تیم '+escHtml(s.team.name)+'</div>':'')+q.map(function(x){
    var last=x.last===true?'<span class="gm-pill ok">ماه قبل انجام شد</span>':(x.last===false?'<span class="gm-pill">ماه قبل انجام نشد</span>':'');
    return '<div class="gm-quest'+(x.ok?' ok':'')+'"><div class="gm-quest-head"><b>'+escHtml(x.title)+'</b>'+
      (x.ok?'<span class="gm-pill ok">در مسیر</span>':'')+last+'</div>'+gmBar(x.progress)+'<small>'+escHtml(x.value)+'</small></div>';
  }).join('')+'</div>';
}
function gmTop3Html(s){
  var r=s&&s.rank;if(!r||!r.top||!r.top.length)return '';
  return '<div class="gm-top3">'+r.top.map(function(p,i){
    return '<div class="gm-top3-row'+(r.me&&r.me.user_id===p.user_id?' me':'')+'"><span>'+GM_MEDALS[i]+'</span><span>'+escHtml(p.name)+'</span><b>'+gmNum(p.points)+'</b></div>';
  }).join('')+'</div>';
}
function gmRenderDash(){
  var s=GM.summary;if(!s)return;
  var me=g('gm-dash-me-body');
  if(me)me.innerHTML=!s.has_wallet?gmEmpty('این نقش کیف پول سکه ندارد.'):
    gmLevelHtml(s)+gmStatsHtml(s)+gmBadgesHtml(s.badges)+(s.shop_open?'':'<div class="gm-note">🔒 فروشگاه هنوز باز نشده است؛ امتیاز و سکه از همین حالا جمع می‌شود.</div>');
  var team=g('gm-dash-team-body');if(team)team.innerHTML=gmQuestsHtml(s)+gmTop3Html(s);
}
function gmRenderWalletChip(){
  var el=g('gm-wallet-chip');if(!el)return;
  var bal=GM.summary&&GM.summary.coins?GM.summary.coins.balance:(GM.shop&&GM.shop.balance);
  el.innerHTML=bal==null?'':'<span class="gm-wallet">موجودی '+gmCoin(bal)+'</span>';
}

// ── page 27: club ──────────────────────────────────────────────────────────
function gmPagesHtml(){
  return '<div class="page" id="pg27"><div class="ph"><h2><span>🏅</span>امتیاز و فروشگاه</h2><div class="bg"><span id="gm-wallet-chip"></span>'+
      '<button class="btn btn-ghost" onclick="gmRefreshClub()">↺ به‌روزرسانی</button></div></div>'+
      '<div id="gm-closed-note"></div><div class="gm-tabs" id="gm-tabs" role="tablist"></div><div id="gm-club-body"></div></div>'+
    '<div class="page" id="pg28"><div class="ph"><h2><span>🧰</span>مدیریت فروشگاه</h2><div class="bg">'+
      '<button class="btn btn-ghost" onclick="gmOpenAdmin()">↺ به‌روزرسانی</button></div></div>'+
      '<div class="gm-tabs" id="gm-admin-tabs" role="tablist"></div><div id="gm-admin-body"></div></div>';
}
function gmOpenClub(){
  var tabs=GM_TABS.filter(function(t){return can(t.perm);}),bar=g('gm-tabs'),body=g('gm-club-body');
  if(!bar||!body)return;
  if(!tabs.length){bar.innerHTML='';body.innerHTML=gmEmpty('دسترسی به این بخش برای نقش شما فعال نیست.');return;}
  if(!tabs.some(function(t){return t.key===GM.tab;}))GM.tab=tabs[0].key;
  bar.innerHTML=tabs.map(function(t){return '<button type="button" role="tab" class="gm-tab'+(t.key===GM.tab?' active':'')+'" onclick="gmClubTab(\''+t.key+'\')">'+t.label+'</button>';}).join('');
  gmLoadClubTab();
}
function gmClubTab(key){GM.tab=key;try{localStorage.setItem('taskhub_gm_tab',key);}catch(e){}gmOpenClub();}
function gmRefreshClub(){GM.images={};gmOpenClub();}
async function gmLoadClubTab(){
  var key=GM.tab,body=g('gm-club-body');body.innerHTML=gmEmpty('در حال بارگذاری...');
  if(key==='me'){await gmLoadSummary(true);var h=await api('/game/history',{});if(GM.tab!==key)return;GM.history=h;gmRenderMe();}
  else if(key==='shop'){var r=await api('/game/shop/items',{});if(GM.tab!==key)return;GM.shop=r;gmRenderShop();}
  else if(key==='orders'){var o=await api('/game/shop/my_orders',{});if(GM.tab!==key)return;GM.orders=o;gmRenderOrders();}
  else if(key==='feed'){var f=await api('/game/shop/feed',{});if(GM.tab!==key)return;GM.feed=f;gmRenderFeed(body,f,true);}
  else if(key==='hall'){var hl=await api('/game/hall',{});if(GM.tab!==key)return;GM.hall=hl;gmRenderHall();}
  else if(key==='board'){await gmLoadBoard();}
  if(!GM.summary)await gmLoadSummary(true);
  gmRenderClosedNote();gmRenderWalletChip();
}
function gmRenderClosedNote(){
  var box=g('gm-closed-note');if(!box)return;
  var open=GM.summary?GM.summary.shop_open:(GM.shop?GM.shop.shop_open:true);
  box.innerHTML=open?'':'<div class="gm-note">🔒 فروشگاه هنوز باز نشده است. امتیاز و سکه از همین حالا جمع می‌شود و بعد از باز شدن فروشگاه قابل خرج است.'+
    (can('game.settings')?' <button type="button" class="v7-mini" onclick="gmGoSettings()">باز کردن فروشگاه</button>':'')+'</div>';
}
function gmGoSettings(){GM.adminTab='settings';showPage(28);}

function gmRenderMe(){
  var s=GM.summary||{},h=GM.history||{},body=g('gm-club-body');if(!body)return;
  if(!s.has_wallet){
    body.innerHTML='<div class="gm-note">نقش شما کیف پول سکه ندارد؛ امتیاز و سکه برای پشتیبان، پلنر، کارشناس مالی و کارشناس اجرایی است.</div>'+
      '<section class="gm-card"><h4>🎯 مأموریت‌های تیم</h4>'+gmQuestsHtml(s)+gmTop3Html(s)+'</section>';
    return;
  }
  var html='<div class="gm-grid2"><section class="gm-card"><h4>🏅 سطح و موجودی</h4>'+gmLevelHtml(s)+gmStatsHtml(s)+'</section>'+
    '<section class="gm-card"><h4>🎯 مأموریت‌های تیم</h4>'+gmQuestsHtml(s)+'</section></div>';
  var badges=h.badges||[];
  html+='<section class="gm-card"><h4>🎖 نشان‌های من</h4>'+(badges.length?'<div class="gm-badges">'+badges.map(function(b){
    return '<span class="gm-badge" title="'+escHtml(b.desc||'')+'">🎖 '+escHtml(b.title||b.badge_key)+' <small>'+escHtml(gmPeriodLabel(b.period_key))+'</small></span>';
  }).join('')+'</div>':gmEmpty('هنوز نشانی نگرفته‌اید؛ شرط هر نشان در «تالار افتخارات» آمده است.'))+'</section>';
  var wishes=s.wishlist||[];
  if(wishes.length)html+='<section class="gm-card"><h4>♥ لیست آرزو</h4>'+wishes.map(function(w){
    return '<div class="gm-wish"><b>'+escHtml(w.name)+'</b>'+gmBar(w.progress)+'<small>'+gmFa(w.progress)+'٪ از '+gmNum(w.price)+' سکه'+(w.is_active?'':' · فعلاً غیرفعال')+'</small></div>';
  }).join('')+'</section>';
  var coins=h.coins||[],points=h.points||[],expired=h.expired||[];
  html+='<section class="gm-card"><h4>🧾 تاریخچه سکه</h4>'+(coins.length?'<div class="gm-table-wrap"><table class="gm-table"><thead><tr><th>تاریخ</th><th>شرح</th><th>نوع</th><th>سکه</th><th>انقضا</th></tr></thead><tbody>'+
    coins.map(function(c){return '<tr><td>'+gmDateTime(c.created_at)+'</td><td>'+escHtml(c.note||'')+'</td><td>'+escHtml(c.kind_label||c.kind)+'</td>'+
      '<td class="'+(c.amount>0?'gm-plus':'gm-minus')+'">'+(c.amount>0?'+':'−')+gmNum(Math.abs(c.amount))+'</td><td>'+(c.expires_at?gmDate(c.expires_at):'—')+'</td></tr>';}).join('')+
    '</tbody></table></div>':gmEmpty('هنوز سکه‌ای ثبت نشده است.'))+
    (expired.length?'<small class="gm-muted">منقضی‌شده: '+expired.map(function(x){return gmNum(x.amount)+' سکه در '+gmDate(x.expired_at);}).join('، ')+'</small>':'')+'</section>';
  html+='<section class="gm-card"><h4>📈 تاریخچه امتیاز</h4>'+(points.length?'<div class="gm-table-wrap"><table class="gm-table"><thead><tr><th>تاریخ</th><th>شرح</th><th>فصل</th><th>امتیاز</th></tr></thead><tbody>'+
    points.map(function(p){return '<tr><td>'+gmDateTime(p.created_at)+'</td><td>'+escHtml(p.note||'')+'</td><td>'+escHtml(gmPeriodLabel(p.season_key))+'</td>'+
      '<td class="'+(p.points>0?'gm-plus':'gm-minus')+'">'+(p.points>0?'+':'−')+gmNum(Math.abs(p.points))+'</td></tr>';}).join('')+
    '</tbody></table></div>':gmEmpty('هنوز امتیازی ثبت نشده است.'))+'</section>';
  body.innerHTML=html;
}

function gmItemDetail(i){
  if(i.item_type==='leave')return i.leave_mode==='hours'?gmFa(i.leave_hours)+' ساعت':'یک روز';
  if(i.item_type==='money'&&i.reward_amount)return gmNum(i.reward_amount)+' ریال';
  if(i.item_type==='cosmetic'){
    if(i.cosmetic_slot==='frame')return 'قاب '+(GM_FRAMES[i.cosmetic_value]||'');
    if(i.cosmetic_slot==='chat')return 'حباب '+(GM_CHATS[i.cosmetic_value]||'');
    return 'لقب «'+(i.cosmetic_value||'')+'»';
  }
  return '';
}
function gmBuyBlock(i){
  var r=GM.shop||{},today=gmTodayIso();
  if(!r.shop_open)return 'فروشگاه هنوز باز نشده است';
  if(!i.is_active)return 'فعلاً غیرفعال';
  if(i.sale_from&&String(i.sale_from).slice(0,10)>today)return 'فروش هنوز شروع نشده';
  if(i.sale_to&&String(i.sale_to).slice(0,10)<today)return 'زمان فروش تمام شده';
  if(i.item_type==='team_pot')return r.balance!=null&&r.balance<1?'سکه کافی نیست':'';
  if(i.stock_total&&i.sold>=i.stock_total)return 'موجودی تمام شده';
  if(i.per_user_monthly_limit&&i.mine_this_month>=i.per_user_monthly_limit)return 'سقف خرید این ماه پر شده';
  if(r.balance!=null&&r.balance<i.final_price)return 'سکه کافی نیست';
  return '';
}
function gmItemCard(i){
  var r=GM.shop||{},tags=[];
  if(!i.is_active)tags.push('<span class="gm-tag off">غیرفعال</span>');
  if(i.stock_total)tags.push('<span class="gm-tag">'+gmFa(Math.max(0,i.stock_total-i.sold))+' از '+gmFa(i.stock_total)+' باقی‌مانده</span>');
  if(i.per_user_monthly_limit)tags.push('<span class="gm-tag">هر نفر '+gmFa(i.per_user_monthly_limit)+' بار در ماه</span>');
  if(i.sale_to_fa)tags.push('<span class="gm-tag">فروش تا '+gmFa(i.sale_to_fa)+'</span>');
  if(i.festival)tags.push('<span class="gm-tag fest">🎉 '+escHtml(i.festival.title)+' · '+gmFa(i.festival.percent)+'٪ تخفیف تا '+gmDate(i.festival.ends)+'</span>');
  var price=i.festival?'<s>'+gmNum(i.price)+'</s> '+gmCoin(i.final_price):gmCoin(i.price),action='';
  if(r.has_wallet){
    var reason=gmBuyBlock(i);
    action='<button type="button" class="btn btn-primary gm-buy"'+(reason?' disabled title="'+escHtml(reason)+'"':'')+' onclick="gmOpenBuy('+i.id+')">'+(i.item_type==='team_pot'?'مشارکت':'خرید')+'</button>';
    if(reason)action+='<small class="gm-muted">'+escHtml(reason)+'</small>';
  }
  if(i.item_type==='cosmetic'&&((r.owned_cosmetics||[]).indexOf(i.id)>=0||r.all_cosmetics)){
    var eq=r.equipped&&r.equipped[i.cosmetic_slot]&&Number(r.equipped[i.cosmetic_slot].item_id)===Number(i.id);
    action+='<button type="button" class="v7-mini" onclick="gmEquip(\''+i.cosmetic_slot+'\','+(eq?'null':i.id)+')">'+(eq?'برداشتن':'استفاده')+'</button>';
  }
  var pot='';
  if(i.pot)pot='<div class="gm-pot">'+gmBar(Math.round((i.pot.collected||0)*100/Math.max(1,i.pot.goal||1)))+
    '<small>صندوق تیم '+escHtml(i.pot.team||'')+': '+gmNum(i.pot.collected)+' از '+gmNum(i.pot.goal)+' سکه</small></div>';
  var detail=gmItemDetail(i);
  return '<article class="gm-item'+(i.is_active?'':' off')+'">'+
    '<div class="gm-item-img"'+(i.has_image?' data-gm-img="'+i.id+'" data-gm-ver="'+i.image_version+'"':'')+'>'+(i.has_image?'':'<span>'+(GM_TYPE_ICON[i.item_type]||'🎁')+'</span>')+'</div>'+
    '<div class="gm-item-body"><div class="gm-item-top"><b>'+escHtml(i.name)+'</b>'+
    (r.has_wallet?'<button type="button" class="gm-heart'+(i.wished?' on':'')+'" title="لیست آرزو" aria-pressed="'+(i.wished?'true':'false')+'" onclick="gmWish('+i.id+')">♥</button>':'')+'</div>'+
    '<div class="gm-item-type">'+escHtml(i.type_label||GM_TYPES[i.item_type]||'')+(detail?' · '+escHtml(detail):'')+'</div>'+
    (i.description?'<p>'+escHtml(i.description)+'</p>':'')+(tags.length?'<div class="gm-tags">'+tags.join('')+'</div>':'')+pot+
    '<div class="gm-item-foot"><span class="gm-price">'+price+'</span><span class="gm-item-act">'+action+'</span></div></div></article>';
}
function gmRenderShop(){
  var r=GM.shop||{},body=g('gm-club-body');if(!body)return;
  if(!r.ok){body.innerHTML=gmErr(r);return;}
  var items=r.items||[],types=[],f=GM.filter;
  items.forEach(function(i){if(types.indexOf(i.item_type)<0)types.push(i.item_type);});
  var chips=[['all','همه'],['afford','قابل خرید']];
  if(r.has_wallet)chips.push(['wished','♥ لیست آرزو']);
  chips=chips.concat(types.map(function(t){return [t,GM_TYPES[t]||t];}));
  var list=items.filter(function(i){
    if(f==='all')return true;
    if(f==='wished')return i.wished;
    if(f==='afford')return !gmBuyBlock(i);
    return i.item_type===f;
  });
  var html='<div class="gm-filters">'+chips.map(function(c){return '<button type="button" class="gm-chip'+(f===c[0]?' active':'')+'" onclick="gmShopFilter(\''+c[0]+'\')">'+escHtml(c[1])+'</button>';}).join('')+'</div>';
  if(!items.length)html+=gmEmpty('هنوز آیتمی در فروشگاه ثبت نشده است.'+(can('shop.manage_items')?' از «مدیریت فروشگاه» آیتم اضافه کنید.':''));
  else if(!list.length)html+=gmEmpty('آیتمی با این فیلتر نیست.');
  else html+='<div class="gm-items">'+list.map(gmItemCard).join('')+'</div>';
  body.innerHTML=html;gmLoadImages(body);
}
function gmShopFilter(f){GM.filter=f;gmRenderShop();}
async function gmLoadImages(root){
  var els=Array.prototype.slice.call((root||document).querySelectorAll('[data-gm-img]'));
  for(var k=0;k<els.length;k++){
    var el=els[k],key=el.getAttribute('data-gm-img')+':'+el.getAttribute('data-gm-ver');
    if(GM.images[key]===undefined){
      var r=await api('/game/shop/item_image',{id:Number(el.getAttribute('data-gm-img'))});
      GM.images[key]=(r&&r.ok&&r.data_url)||'';
    }
    if(GM.images[key]){el.style.backgroundImage='url("'+GM.images[key]+'")';el.classList.add('has');}
  }
}
async function gmReloadShop(){var r=await api('/game/shop/items',{});GM.shop=r;if(GM.tab==='shop'&&document.querySelector('#pg27.page.active'))gmRenderShop();gmRenderWalletChip();}
async function gmWish(id){
  var r=await api('/game/shop/wishlist_toggle',{item_id:id});if(!r.ok)return toast(r.error||'خطا','err');
  var it=((GM.shop||{}).items||[]).find(function(x){return x.id===id;});if(it)it.wished=r.wished;
  gmRenderShop();toast(r.wished?'به لیست آرزو اضافه شد':'از لیست آرزو برداشته شد','ok');gmLoadSummary(true);
}
async function gmEquip(slot,itemId){
  var r=await api('/game/shop/equip',{slot:slot,item_id:itemId});if(!r.ok)return toast(r.error||'خطا','err');
  toast(itemId?'روی پروفایل شما اعمال شد':'برداشته شد','ok');await gmLoadCosmetics();gmReloadShop();
}
function gmOpenBuy(id){
  var r=GM.shop||{},i=(r.items||[]).find(function(x){return x.id===id;});if(!i)return;
  GM.buyId=id;
  g('gm-buy-title').textContent=(i.item_type==='team_pot'?'مشارکت در ':'خرید ')+i.name;
  var detail=gmItemDetail(i);
  var html='<div class="gm-buy-sum"><div>'+escHtml(i.type_label||'')+(detail?' · '+escHtml(detail):'')+'</div>'+
    '<div>قیمت: '+(i.festival?'<s>'+gmNum(i.price)+'</s> ':'')+gmCoin(i.final_price)+'</div><div>موجودی شما: '+gmCoin(r.balance||0)+'</div></div>';
  if(i.item_type==='leave'||i.item_type==='remote'){
    html+='<div class="fg"><label class="fl">روز استفاده <span class="r">*</span></label><input class="fi" id="gm-buy-date" readonly placeholder="انتخاب روز" onclick="openDP(\'gm-buy-date\')">'+
      '<small class="gm-muted">از فردا به بعد و یک روز کاری. تا روز قبل از آن می‌توانید روز را عوض کنید یا خرید را لغو کنید.</small></div>';
    if(i.item_type==='leave'&&i.leave_mode==='hours')html+='<div class="fg"><label class="fl">ساعت شروع ('+gmFa(i.leave_hours)+' ساعت)</label><input class="fi" id="gm-buy-time" type="time" value="08:00"></div>';
    if(i.item_type==='leave')html+='<small class="gm-muted">مرخصی تشویقی جزو مرخصی رسمی نیست و خودکار در تقویم شما ثبت می‌شود.</small>';
  }else if(i.item_type==='team_pot'){
    var left=i.pot?Math.max(1,(i.pot.goal||0)-(i.pot.collected||0)):i.price;
    html+='<div class="fg"><label class="fl">مقدار مشارکت (سکه)</label><input class="fi" id="gm-buy-amount" type="number" min="1" max="'+left+'" value="'+Math.min(i.price,left)+'">'+
      '<small class="gm-muted">تا کامل شدن صندوق '+gmNum(left)+' سکه مانده است.</small></div>';
  }else if(i.item_type==='money')html+='<small class="gm-muted">بعد از خرید در لیست پرداخت کارشناس مالی قرار می‌گیرد و همراه حقوق بعدی پرداخت می‌شود.</small>';
  else if(i.item_type==='cosmetic')html+='<small class="gm-muted">همان لحظه روی پروفایل و پیام‌رسان شما اعمال می‌شود.</small>';
  else html+='<small class="gm-muted">بعد از خرید در لیست تحویل ادمین قرار می‌گیرد.</small>';
  g('gm-buy-body').innerHTML=html;openM('gm-m-buy');
}
async function gmConfirmBuy(){
  var i=((GM.shop||{}).items||[]).find(function(x){return x.id===GM.buyId;});if(!i)return;
  var payload={item_id:i.id};
  if(g('gm-buy-date'))payload.date=toEnDigits(g('gm-buy-date').value||'');
  if(g('gm-buy-time'))payload.start_time=g('gm-buy-time').value;
  if(g('gm-buy-amount'))payload.amount=Number(toEnDigits(g('gm-buy-amount').value||'0'));
  if((i.item_type==='leave'||i.item_type==='remote')&&!payload.date)return toast('روز استفاده را انتخاب کنید','err');
  var btn=g('gm-buy-go');if(btn)btn.disabled=true;
  var r=await api('/game/shop/buy',payload);
  if(btn)btn.disabled=false;
  if(!r.ok)return toast(r.error||'خرید انجام نشد','err');
  closeM('gm-m-buy');toast((i.item_type==='team_pot'?'مشارکت ثبت شد: ':'خرید انجام شد: ')+gmNum(r.price)+' سکه','ok');
  await gmLoadSummary(true);await gmReloadShop();
  if(i.item_type==='cosmetic')gmLoadCosmetics();
  if(i.item_type==='leave'&&typeof loadCalendarData==='function'){try{loadCalendarData();}catch(e){}}
}

function gmRenderOrders(){
  var r=GM.orders||{},body=g('gm-club-body');if(!body)return;
  if(!r.ok){body.innerHTML=gmErr(r);return;}
  var rows=r.rows||[];if(!rows.length){body.innerHTML=gmEmpty('هنوز خریدی ثبت نکرده‌اید.');return;}
  body.innerHTML='<div class="gm-table-wrap"><table class="gm-table"><thead><tr><th>آیتم</th><th>نوع</th><th>سکه</th><th>وضعیت</th><th>روز استفاده</th><th>تاریخ</th><th></th></tr></thead><tbody>'+rows.map(function(o){
    var acts='';
    if(o.can_change)acts+='<button type="button" class="v7-mini" onclick="gmOpenDate('+o.id+')">'+(o.status==='awaiting_date'?'انتخاب روز':'تغییر روز')+'</button>';
    if(o.can_cancel)acts+='<button type="button" class="v7-mini danger" onclick="gmCancelOrder('+o.id+')">لغو</button>';
    var when=o.scheduled_date?gmFa(o.scheduled_date)+(o.start_time?' · '+gmFa(o.start_time):''):'—';
    return '<tr><td><b>'+escHtml(o.item_name)+'</b>'+(o.gift_id?' <span class="gm-pill">🎁 هدیه</span>':'')+'</td><td>'+escHtml(o.type_label)+'</td>'+
      '<td>'+(o.price_paid?gmNum(o.price_paid):'—')+(o.discount_percent?' <small class="gm-muted">('+gmFa(o.discount_percent)+'٪ تخفیف)</small>':'')+'</td>'+
      '<td><span class="gm-status s-'+escHtml(o.status)+'">'+escHtml(o.status_label)+'</span></td><td>'+when+'</td><td>'+gmDateTime(o.created_at)+'</td><td class="gm-acts">'+acts+'</td></tr>';
  }).join('')+'</tbody></table></div>';
}
function gmOpenDate(orderId){
  var o=((GM.orders||{}).rows||[]).find(function(x){return x.id===orderId;});if(!o)return;
  GM.dateOrder=orderId;
  g('gm-dt-date').value=o.scheduled_date||'';
  var hourly=o.item_type==='leave'&&o.leave_mode==='hours';
  g('gm-dt-time-row').style.display=hourly?'':'none';
  if(hourly)g('gm-dt-time').value=o.start_time||'08:00';
  openM('gm-m-date');
}
async function gmSaveDate(){
  var payload={order_id:GM.dateOrder,date:toEnDigits(g('gm-dt-date').value||'')};
  if(g('gm-dt-time-row').style.display!=='none')payload.start_time=g('gm-dt-time').value;
  if(!payload.date)return toast('روز را انتخاب کنید','err');
  var r=await api('/game/shop/order_reschedule',payload);if(!r.ok)return toast(r.error||'خطا','err');
  closeM('gm-m-date');toast('روز استفاده ثبت شد','ok');
  GM.orders=await api('/game/shop/my_orders',{});gmRenderOrders();
  if(typeof loadCalendarData==='function'){try{loadCalendarData();}catch(e){}}
}
async function gmCancelOrder(orderId){
  if(!confirm('این خرید لغو شود؟ سکه آن کامل به کیف پول شما برمی‌گردد.'))return;
  var r=await api('/game/shop/order_cancel',{order_id:orderId});if(!r.ok)return toast(r.error||'خطا','err');
  toast(r.refunded?gmNum(r.refunded)+' سکه برگشت':'لغو شد','ok');
  GM.orders=await api('/game/shop/my_orders',{});gmRenderOrders();gmLoadSummary(true);
  if(typeof loadCalendarData==='function'){try{loadCalendarData();}catch(e){}}
}

function gmRenderFeed(box,f,withPurchases){
  if(!box)return;if(!f||!f.ok){box.innerHTML=gmErr(f);return;}
  var purchases=f.purchases||[],gifts=f.gifts||[],linkNames={task:'تسک',project:'پروژه',contract:'قرارداد'};
  var buys='<section class="gm-card"><h4>🛍 خریدهای اخیر همکاران</h4>'+(purchases.length?'<ul class="gm-feed">'+purchases.map(function(x){
    var what=x.status==='contributed'?'به صندوق «'+escHtml(x.item_name)+'» '+gmNum(x.price_paid)+' سکه ریخت':
      (x.item_type==='team_pot'&&x.note?escHtml(x.note):'«'+escHtml(x.item_name)+'» را خرید');
    return '<li><b>'+escHtml(x.name)+'</b> '+what+'<small>'+gmDateTime(x.created_at)+'</small></li>';
  }).join('')+'</ul>':gmEmpty('هنوز خریدی ثبت نشده است.'))+'</section>';
  var giftsHtml='<section class="gm-card"><h4>💝 دفتر هدیه‌ها</h4>'+(gifts.length?'<ul class="gm-feed">'+gifts.map(function(x){
    return '<li><b>'+escHtml(x.from_name||'')+'</b> به <b>'+escHtml(x.to_name||'')+'</b> «'+escHtml(x.item_name)+'» هدیه داد<small>'+gmDateTime(x.created_at)+'</small>'+
      '<div class="gm-reason">دلیل: '+escHtml(x.reason)+(x.link_label?' — '+escHtml(linkNames[x.link_type]||'')+' «'+escHtml(x.link_label)+'»':'')+'</div></li>';
  }).join('')+'</ul>':gmEmpty('هنوز هدیه‌ای ثبت نشده است.'))+'</section>';
  box.innerHTML=withPurchases?'<div class="gm-grid2">'+buys+giftsHtml+'</div>':giftsHtml;
}
function gmRenderHall(){
  var h=GM.hall||{},body=g('gm-club-body');if(!body)return;if(!h.ok){body.innerHTML=gmErr(h);return;}
  var html='<section class="gm-card"><h4>🎖 نشان‌ها و شرط هر کدام</h4><div class="gm-badge-grid">'+(h.badges||[]).map(function(b){
    return '<div class="gm-badge-card'+(b.mine?' mine':'')+'"><div class="gm-badge-icon">🎖</div><b>'+escHtml(b.title)+'</b><p>'+escHtml(b.desc)+'</p>'+
      '<small>'+(b.roles||[]).map(function(r){return GM_ROLES[r]||r;}).join('، ')+' · '+(b.period==='month'?'هر ماه':'هر فصل')+'</small>'+
      '<small>'+(b.mine?'شما '+gmFa(b.mine)+' بار گرفته‌اید · ':'')+gmFa(b.holders)+' نفر دارند</small></div>';
  }).join('')+'</div></section>';
  var hall=h.hall||[];
  html+='<section class="gm-card"><h4>🏆 برترین‌های هر فصل</h4>'+(hall.length?hall.map(function(season){
    return '<div class="gm-season"><b>'+escHtml(season.label)+'</b><div class="gm-season-teams">'+season.teams.map(function(t){
      return '<div class="gm-season-team"><small>'+escHtml(t.team)+'</small>'+t.top.map(function(p,i){return '<div>'+GM_MEDALS[i]+' '+escHtml(p.name)+' <b>'+gmNum(p.points)+'</b></div>';}).join('')+'</div>';
    }).join('')+'</div></div>';
  }).join(''):gmEmpty('هنوز هیچ فصلی تمام نشده است.'))+'</section>';
  body.innerHTML=html;
}
async function gmLoadBoard(){
  var r=await api('/game/board',{team_id:GM.boardTeam,season:GM.boardSeason});
  if(GM.tab!=='board')return;GM.board=r;gmRenderBoard();
}
function gmRenderBoard(){
  var r=GM.board||{},body=g('gm-club-body');if(!body)return;if(!r.ok){body.innerHTML=gmErr(r);return;}
  if(!r.board){body.innerHTML=gmEmpty('برای دیدن رتبه‌بندی باید عضو یک تیم باشید.');return;}
  var b=r.board,cmp=r.compare||[],max=Math.max.apply(null,[1].concat(cmp.map(function(c){return c.average;})));
  var html='<div class="gm-filters">'+((r.teams||[]).length>1?'<select class="gm-sel" id="gm-board-team" onchange="gmBoardChange()">'+
      gmSelectOptions((r.teams||[]).map(function(t){return [t.id,t.name];}),r.team_id)+'</select>':'')+
    '<select class="gm-sel" id="gm-board-season" onchange="gmBoardChange()">'+gmSelectOptions((r.seasons||[]).map(function(s){return [s.key,s.label];}),r.season)+'</select></div>';
  html+='<div class="gm-grid2"><section class="gm-card"><h4>🏅 سه نفر اول · '+escHtml(r.season_label)+'</h4>'+
    (b.top.length?'<div class="gm-podium">'+b.top.map(function(p,i){
      return '<div class="gm-podium-'+(i+1)+(b.me&&b.me.user_id===p.user_id?' me':'')+'"><span>'+GM_MEDALS[i]+'</span><b>'+escHtml(p.name)+'</b><small>'+gmNum(p.points)+' امتیاز</small></div>';
    }).join('')+'</div>':gmEmpty('هنوز امتیازی در این فصل ثبت نشده است.'))+
    (b.me?'<div class="gm-me-line">جایگاه شما: '+gmFa(b.me.position)+' از '+gmFa(b.total)+(b.gap?' · '+gmNum(b.gap)+' امتیاز تا نفر بالاتر':'')+'</div>':'')+'</section>'+
    '<section class="gm-card"><h4>👥 مقایسه تیم‌ها (میانگین هر عضو)</h4>'+(cmp.length?cmp.map(function(c){
      return '<div class="gm-cmp"><span>'+escHtml(c.name)+' <small>('+gmFa(c.members)+' نفر)</small></span>'+gmBar(Math.round(c.average*100/max))+'<b>'+gmNum(c.average)+'</b></div>';
    }).join(''):gmEmpty('داده‌ای برای مقایسه نیست.'))+'</section></div>';
  if(b.rows)html+='<section class="gm-card"><h4>📋 جدول کامل</h4><div class="gm-table-wrap"><table class="gm-table"><thead><tr><th>رتبه</th><th>نام</th><th>امتیاز فصل</th></tr></thead><tbody>'+
    b.rows.map(function(p){return '<tr><td>'+gmFa(p.position)+'</td><td>'+escHtml(p.name)+'</td><td>'+gmNum(p.points)+'</td></tr>';}).join('')+'</tbody></table></div></section>';
  body.innerHTML=html;
}
function gmBoardChange(){var t=g('gm-board-team'),s=g('gm-board-season');GM.boardTeam=t?Number(t.value):null;GM.boardSeason=s?s.value:null;gmLoadBoard();}

// ── kudos on a finished task ───────────────────────────────────────────────
function gmTaskKudos(id){
  if(!CU||!can('gamification.kudos'))return;
  var t=(D.t||[]).find(function(x){return Number(x.id)===Number(id);}),box=g('tvb');
  if(!t||!box||t.status!=='done')return;
  var people=[],seen={};
  if(t.staff_id)people.push({id:Number(t.staff_id),name:gmUserName(t.staff_id)});
  (t.helpers||[]).forEach(function(h){people.push({id:Number(h.id),name:h.name||gmUserName(h.id)});});
  people=people.filter(function(p){if(seen[p.id]||p.id===Number(CU.id))return false;seen[p.id]=1;return true;});
  if(!people.length)return;
  box.insertAdjacentHTML('beforeend','<div class="gm-kudos"><b>🙏 قدردانی از همکار</b><div>'+people.map(function(p){
    return '<button type="button" class="v7-mini" onclick="gmGiveKudos('+t.id+','+p.id+',this)">ممنونم، '+escHtml(p.name)+'</button>';
  }).join('')+'</div></div>');
}
async function gmGiveKudos(taskId,userId,btn){
  if(btn)btn.disabled=true;
  var r=await api('/game/kudos_give',{task_id:taskId,to_user:userId});
  if(!r.ok){if(btn)btn.disabled=false;return toast(r.error||'خطا','err');}
  toast('قدردانی ثبت شد'+(r.coins?' و '+gmFa(r.coins)+' سکه به همکارتان رسید':''),'ok');
  if(btn)btn.textContent='✓ ثبت شد';
}

// ── page 28: shop administration ───────────────────────────────────────────
function gmOpenAdmin(){
  var tabs=GM_ADMIN_TABS.filter(function(t){return can(t.perm);}),bar=g('gm-admin-tabs'),body=g('gm-admin-body');
  if(!bar||!body)return;
  if(!tabs.length){bar.innerHTML='';body.innerHTML=gmEmpty('دسترسی به این بخش برای نقش شما فعال نیست.');return;}
  if(!tabs.some(function(t){return t.key===GM.adminTab;}))GM.adminTab=tabs[0].key;
  bar.innerHTML=tabs.map(function(t){return '<button type="button" role="tab" class="gm-tab'+(t.key===GM.adminTab?' active':'')+'" onclick="gmAdminTab(\''+t.key+'\')">'+t.label+'</button>';}).join('');
  gmLoadAdminTab();
}
function gmAdminTab(key){GM.adminTab=key;try{localStorage.setItem('taskhub_gm_admin_tab',key);}catch(e){}gmOpenAdmin();}
async function gmLoadAdminTab(){
  var key=GM.adminTab,body=g('gm-admin-body'),r;body.innerHTML=gmEmpty('در حال بارگذاری...');
  if(key==='items'){r=await api('/game/admin/items',{});if(GM.adminTab!==key)return;GM.admin.items=r;gmRenderAdminItems();}
  else if(key==='festivals'){
    r=await api('/game/admin/festivals',{});var items=await api('/game/shop/items',{});
    if(GM.adminTab!==key)return;GM.admin.festivals=r;GM.admin.festItems=items;gmRenderFestivals();
  }else if(key==='gift'){
    var users=await api('/game/admin/wallet_users',{}),giftItems=await api('/game/shop/items',{}),feed=await api('/game/shop/feed',{});
    if(GM.adminTab!==key)return;GM.admin.users=users;GM.admin.giftItems=giftItems;GM.admin.feed=feed;gmRenderGift();
  }else if(key==='deliver'){r=await api('/game/admin/deliveries',{});if(GM.adminTab!==key)return;GM.admin.deliver=r;gmRenderFulfil(r,'deliver');}
  else if(key==='pay'){r=await api('/game/admin/payments',{});if(GM.adminTab!==key)return;GM.admin.pay=r;gmRenderFulfil(r,'pay');}
  else if(key==='monthly'){r=await api('/game/admin/monthly',{month:GM.admin.monthKey});if(GM.adminTab!==key)return;GM.admin.monthly=r;gmRenderMonthly();}
  else if(key==='economy'){r=await api('/game/admin/economy',{});if(GM.adminTab!==key)return;GM.admin.economy=r;gmRenderEconomy();}
  else if(key==='settings'){r=await api('/game/admin/settings',{});if(GM.adminTab!==key)return;GM.admin.settings=r;gmRenderSettings();}
}

function gmRenderAdminItems(){
  var r=GM.admin.items||{},body=g('gm-admin-body');if(!body)return;if(!r.ok){body.innerHTML=gmErr(r);return;}
  var items=r.items||[];
  var html='<div class="gm-toolbar"><button type="button" class="btn btn-add" onclick="gmOpenItem(null)">➕ افزودن آیتم</button>'+
    '<small class="gm-muted">فعال و غیرفعال کردن دستی و بدون تاریخ است و از جشنواره جداست؛ آیتم غیرفعال در فروشگاه کم‌رنگ دیده می‌شود و خریدنی نیست.</small></div>';
  if(!items.length)html+=gmEmpty('هنوز آیتمی ثبت نشده است.');
  else html+='<div class="gm-table-wrap"><table class="gm-table"><thead><tr><th></th><th>نام</th><th>نوع</th><th>قیمت</th><th>فروش</th><th>فعال</th><th></th></tr></thead><tbody>'+items.map(function(i){
    var detail=gmItemDetail(i);
    return '<tr class="'+(i.is_archived?'gm-archived':'')+'"><td><div class="gm-thumb"'+(i.has_image?' data-gm-img="'+i.id+'" data-gm-ver="'+i.image_version+'"':'')+'>'+(i.has_image?'':(GM_TYPE_ICON[i.item_type]||'🎁'))+'</div></td>'+
      '<td><b>'+escHtml(i.name)+'</b>'+(i.is_archived?' <span class="gm-pill">بایگانی</span>':'')+(i.festival?' <span class="gm-pill fest">🎉 '+gmFa(i.festival.percent)+'٪</span>':'')+'</td>'+
      '<td>'+escHtml(i.type_label)+(detail?'<br><small class="gm-muted">'+escHtml(detail)+'</small>':'')+'</td><td>'+gmNum(i.price)+'</td>'+
      '<td>'+gmFa(i.sold)+(i.stock_total?' از '+gmFa(i.stock_total):'')+'</td>'+
      '<td>'+(i.is_archived?'—':'<label class="sw" title="فعال یا غیرفعال"><input type="checkbox"'+(i.is_active?' checked':'')+' onchange="gmToggleItem('+i.id+',this.checked)"><span class="sw-slider"></span></label>')+'</td>'+
      '<td class="gm-acts">'+(i.is_archived?'':'<button type="button" class="v7-mini" onclick="gmOpenItem('+i.id+')">ویرایش</button><button type="button" class="v7-mini danger" onclick="gmDeleteItem('+i.id+')">حذف</button>')+'</td></tr>';
  }).join('')+'</tbody></table></div>';
  body.innerHTML=html;gmLoadImages(body);
}
function gmItemTypeChanged(){
  var type=g('gm-it-type').value;
  document.querySelectorAll('#gm-m-item .gm-type-row').forEach(function(row){
    row.style.display=(row.getAttribute('data-types')||'').split(',').indexOf(type)>=0?'':'none';
  });
  g('gm-it-hours-row').style.display=g('gm-it-leave-mode').value==='hours'?'':'none';
  var slot=g('gm-it-slot').value,choices=slot==='frame'?GM_FRAMES:(slot==='chat'?GM_CHATS:null),sel=g('gm-it-value-sel'),keep=sel.value;
  g('gm-it-value-sel-row').style.display=choices?'':'none';
  g('gm-it-value-text-row').style.display=choices?'none':'';
  if(choices){sel.innerHTML=gmSelectOptions(Object.keys(choices).map(function(k){return [k,choices[k]];}),keep);}
  var stock=g('gm-it-stock-row');if(stock)stock.style.display=type==='team_pot'?'none':'';
  gmPriceHint();gmSync();
}
function gmPriceHint(){
  var el=g('gm-it-hint');if(!el)return;
  var per=(GM.admin.items||{}).support_daily_coins,price=Number(toEnDigits(g('gm-it-price').value||'0'));
  if(!price){el.textContent='';return;}
  el.textContent=per?'حدوداً معادل '+gmFa(Math.max(1,Math.round(price/per)))+' روز کار یک پشتیبان':'برای تخمین «چند روز کار» هنوز داده کافی نیست؛ بعد از چند هفته استفاده نمایش داده می‌شود.';
}
function gmOpenItem(id){
  var i=id?((GM.admin.items||{}).items||[]).find(function(x){return x.id===id;}):null;
  GM.editId=id;GM.editImage=null;GM.removeImage=false;
  g('gm-item-title').textContent=i?'ویرایش آیتم':'آیتم جدید';
  g('gm-it-name').value=i?i.name:'';
  g('gm-it-type').value=i?i.item_type:'goods';
  g('gm-it-price').value=i?i.price:'';
  g('gm-it-stock').value=i&&i.stock_total?i.stock_total:'';
  g('gm-it-limit').value=i&&i.per_user_monthly_limit?i.per_user_monthly_limit:'';
  g('gm-it-from').value=i&&i.sale_from_fa?i.sale_from_fa:'';
  g('gm-it-to').value=i&&i.sale_to_fa?i.sale_to_fa:'';
  g('gm-it-desc').value=i&&i.description?i.description:'';
  g('gm-it-active').checked=i?!!i.is_active:true;
  g('gm-it-public').checked=i?!!i.show_in_public:true;
  g('gm-it-leave-mode').value=i&&i.leave_mode?i.leave_mode:'day';
  g('gm-it-hours').value=i&&i.leave_hours?i.leave_hours:'2';
  g('gm-it-reward').value=i&&i.reward_amount?i.reward_amount:'';
  g('gm-it-goal').value=i&&i.team_goal?i.team_goal:'';
  g('gm-it-slot').value=i&&i.cosmetic_slot?i.cosmetic_slot:'frame';
  g('gm-it-value-text').value=i&&i.cosmetic_slot==='title'?(i.cosmetic_value||''):'';
  g('gm-it-file').value='';
  gmItemTypeChanged();
  if(i&&i.cosmetic_slot&&i.cosmetic_slot!=='title')g('gm-it-value-sel').value=i.cosmetic_value;
  var preview=g('gm-it-preview');preview.style.backgroundImage='';preview.classList.remove('has');
  preview.innerHTML='<span>'+(GM_TYPE_ICON[i?i.item_type:'goods']||'🖼')+'</span>';
  if(i&&i.has_image){
    var key=i.id+':'+i.image_version;
    var show=function(url){if(url){preview.style.backgroundImage='url("'+url+'")';preview.classList.add('has');preview.innerHTML='';}};
    if(GM.images[key])show(GM.images[key]);
    else api('/game/shop/item_image',{id:i.id}).then(function(r){GM.images[key]=(r&&r.ok&&r.data_url)||'';show(GM.images[key]);});
  }
  openM('gm-m-item');
}
function gmResizeImage(file){
  return new Promise(function(resolve,reject){
    if(!/^image\/(png|jpeg|webp|gif)$/.test(file.type))return reject(new Error('فقط تصویر PNG، JPEG، WEBP یا GIF پذیرفته می‌شود'));
    var reader=new FileReader();
    reader.onerror=function(){reject(new Error('فایل خوانده نشد'));};
    reader.onload=function(){
      var url=reader.result;
      if(file.type==='image/gif'){if(file.size>650*1024)return reject(new Error('حجم GIF حداکثر ۶۵۰ کیلوبایت است'));return resolve(url);}
      var img=new Image();
      img.onerror=function(){reject(new Error('تصویر قابل خواندن نیست'));};
      img.onload=function(){
        var scale=Math.min(1,640/Math.max(img.width,img.height)),c=document.createElement('canvas');
        c.width=Math.max(1,Math.round(img.width*scale));c.height=Math.max(1,Math.round(img.height*scale));
        c.getContext('2d').drawImage(img,0,0,c.width,c.height);
        var out=file.type==='image/png'?c.toDataURL('image/png'):c.toDataURL('image/jpeg',0.86);
        if(out.length>900000)out=c.toDataURL('image/jpeg',0.72);
        resolve(out);
      };
      img.src=url;
    };
    reader.readAsDataURL(file);
  });
}
async function gmItemFile(input){
  var file=input.files&&input.files[0];if(!file)return;
  try{
    GM.editImage=await gmResizeImage(file);GM.removeImage=false;
    var preview=g('gm-it-preview');preview.style.backgroundImage='url("'+GM.editImage+'")';preview.classList.add('has');preview.innerHTML='';
  }catch(e){toast(e.message,'err');input.value='';}
}
function gmItemNoImage(){
  GM.editImage=null;GM.removeImage=true;g('gm-it-file').value='';
  var preview=g('gm-it-preview');preview.style.backgroundImage='';preview.classList.remove('has');preview.innerHTML='<span>🖼</span>';
}
async function gmSaveItem(){
  var type=g('gm-it-type').value,slot=g('gm-it-slot').value;
  var payload={id:GM.editId,name:g('gm-it-name').value.trim(),item_type:type,
    price:toEnDigits(g('gm-it-price').value||''),stock_total:toEnDigits(g('gm-it-stock').value||''),
    per_user_monthly_limit:toEnDigits(g('gm-it-limit').value||''),
    sale_from:toEnDigits(g('gm-it-from').value||''),sale_to:toEnDigits(g('gm-it-to').value||''),
    description:g('gm-it-desc').value.trim(),is_active:g('gm-it-active').checked,show_in_public:g('gm-it-public').checked,
    leave_mode:g('gm-it-leave-mode').value,leave_hours:toEnDigits(g('gm-it-hours').value||''),
    reward_amount:toEnDigits(String(g('gm-it-reward').value||'').replace(/[,٬]/g,'')),team_goal:toEnDigits(g('gm-it-goal').value||''),
    cosmetic_slot:slot,cosmetic_value:slot==='title'?g('gm-it-value-text').value.trim():g('gm-it-value-sel').value,
    remove_image:GM.removeImage};
  if(GM.editImage)payload.image=GM.editImage;
  var r=await api('/game/admin/item_save',payload);if(!r.ok)return toast(r.error||'خطا','err');
  closeM('gm-m-item');toast('آیتم ذخیره شد','ok');GM.admin.items=await api('/game/admin/items',{});gmRenderAdminItems();
}
async function gmToggleItem(id,active){
  var r=await api('/game/admin/item_toggle',{id:id,active:active});
  if(!r.ok){toast(r.error||'خطا','err');return gmLoadAdminTab();}
  toast(active?'آیتم فعال شد':'آیتم غیرفعال شد','ok');
}
async function gmDeleteItem(id){
  if(!confirm('این آیتم حذف شود؟ اگر قبلاً خریده یا هدیه داده شده باشد، بایگانی می‌شود تا تاریخچه خریدها سالم بماند.'))return;
  var r=await api('/game/admin/item_delete',{id:id});if(!r.ok)return toast(r.error||'خطا','err');
  toast(r.archived?'آیتم بایگانی شد':'آیتم حذف شد','ok');GM.admin.items=await api('/game/admin/items',{});gmRenderAdminItems();
}

function gmRenderFestivals(){
  var r=GM.admin.festivals||{},body=g('gm-admin-body');if(!body)return;if(!r.ok){body.innerHTML=gmErr(r);return;}
  var rows=r.rows||[],states={running:'در حال اجرا',upcoming:'آینده',finished:'تمام‌شده'};
  var html='<div class="gm-toolbar"><button type="button" class="btn btn-add" onclick="gmOpenFest(null)">➕ جشنواره جدید</button>'+
    '<small class="gm-muted">جشنواره فقط تخفیف درصدی زمان‌دار است و فعال‌سازی را تغییر نمی‌دهد؛ آیتم غیرفعال در جشنواره هم خریدنی نیست تا آن را دستی فعال کنید.</small></div>';
  if(!rows.length)html+=gmEmpty('هنوز جشنواره‌ای ساخته نشده است.');
  else html+='<div class="gm-table-wrap"><table class="gm-table"><thead><tr><th>عنوان</th><th>بازه</th><th>وضعیت</th><th>آیتم‌ها</th><th></th></tr></thead><tbody>'+rows.map(function(f){
    return '<tr><td><b>'+escHtml(f.title)+'</b></td><td>'+gmFa(f.start_fa)+' تا '+gmFa(f.end_fa)+'</td><td><span class="gm-status s-'+f.state+'">'+states[f.state]+'</span></td>'+
      '<td>'+f.items.map(function(x){return escHtml(x.name)+' <small class="gm-muted">'+gmFa(x.discount_percent)+'٪ ← '+gmNum(x.final_price)+'</small>';}).join('<br>')+'</td>'+
      '<td class="gm-acts"><button type="button" class="v7-mini" onclick="gmOpenFest('+f.id+')">ویرایش</button><button type="button" class="v7-mini danger" onclick="gmDeleteFest('+f.id+')">حذف</button></td></tr>';
  }).join('')+'</tbody></table></div>';
  body.innerHTML=html;
}
function gmOpenFest(id){
  var f=id?((GM.admin.festivals||{}).rows||[]).find(function(x){return x.id===id;}):null;
  var items=((GM.admin.festItems||{}).items||[]),chosen={};
  (f?f.items:[]).forEach(function(x){chosen[x.item_id]=x.discount_percent;});
  GM.festId=id;
  g('gm-fest-title').textContent=f?'ویرایش جشنواره':'جشنواره جدید';
  g('gm-fe-title').value=f?f.title:'';
  g('gm-fe-start').value=f?f.start_fa:'';
  g('gm-fe-end').value=f?f.end_fa:'';
  g('gm-fe-items').innerHTML=items.length?items.filter(function(i){return i.item_type!=='team_pot';}).map(function(i){
    var on=chosen[i.id]!==undefined;
    return '<label class="gm-fest-row"><input type="checkbox" data-item="'+i.id+'"'+(on?' checked':'')+'>'+
      '<span><b>'+escHtml(i.name)+'</b> <small class="gm-muted">'+gmNum(i.price)+' سکه'+(i.is_active?'':' · غیرفعال')+'</small></span>'+
      '<input class="fi gm-pct" type="number" min="1" max="90" placeholder="٪" value="'+(on?chosen[i.id]:'')+'" data-pct="'+i.id+'"></label>';
  }).join(''):gmEmpty('ابتدا آیتم بسازید.');
  openM('gm-m-fest');
}
async function gmSaveFest(){
  var items=[];
  document.querySelectorAll('#gm-fe-items input[data-item]').forEach(function(box){
    if(!box.checked)return;var id=box.getAttribute('data-item'),pct=document.querySelector('#gm-fe-items input[data-pct="'+id+'"]');
    items.push({item_id:Number(id),percent:Number(toEnDigits((pct&&pct.value)||'0'))});
  });
  var payload={id:GM.festId,title:g('gm-fe-title').value.trim(),start:toEnDigits(g('gm-fe-start').value||''),end:toEnDigits(g('gm-fe-end').value||''),items:items};
  var r=await api('/game/admin/festival_save',payload);if(!r.ok)return toast(r.error||'خطا','err');
  closeM('gm-m-fest');toast('جشنواره ذخیره شد','ok');gmLoadAdminTab();
}
async function gmDeleteFest(id){
  if(!confirm('این جشنواره حذف شود؟ قیمت آیتم‌ها به حالت عادی برمی‌گردد.'))return;
  var r=await api('/game/admin/festival_delete',{id:id});if(!r.ok)return toast(r.error||'خطا','err');toast('جشنواره حذف شد','ok');gmLoadAdminTab();
}

function gmRenderGift(){
  var body=g('gm-admin-body');if(!body)return;
  var users=(GM.admin.users||{}).rows||[],items=((GM.admin.giftItems||{}).items||[]);
  body.innerHTML='<div class="gm-grid2"><section class="gm-card"><h4>💝 هدیه دادن</h4>'+
    '<p class="gm-muted">برای کار خیلی مهم یا پروژه پول‌ساز. دلیل و مورد مرتبط برای همه کارکنان در دفتر هدیه‌ها نمایش داده می‌شود.</p>'+
    '<div class="fg"><label class="fl">گیرنده <span class="r">*</span></label><select class="fi" id="gm-gf-user">'+gmSelectOptions(users.map(function(u){return [u.id,(u.name||u.username)+' — '+(GM_ROLES[u.role]||u.role)];}),'','— انتخاب کنید —')+'</select></div>'+
    '<div class="fg"><label class="fl">آیتم <span class="r">*</span></label><select class="fi" id="gm-gf-item">'+gmSelectOptions(items.map(function(i){return [i.id,i.name+' ('+(GM_TYPES[i.item_type]||'')+')'];}),'','— انتخاب کنید —')+'</select></div>'+
    '<div class="fr"><div class="fg"><label class="fl">مورد مرتبط <span class="r">*</span></label><select class="fi" id="gm-gf-link-type" onchange="gmGiftLinks()">'+
      gmSelectOptions([['task','تسک'],['project','پروژه'],['contract','قرارداد']],'task')+'</select></div>'+
    '<div class="fg"><label class="fl">&nbsp;</label><select class="fi" id="gm-gf-link"></select></div></div>'+
    '<div class="fg"><label class="fl">دلیل هدیه <span class="r">*</span></label><textarea class="fi" id="gm-gf-reason" maxlength="1000" placeholder="مثلاً: تحویل زودتر از موعد پروژه ... که قرارداد جدید را ممکن کرد"></textarea></div>'+
    '<button type="button" class="btn btn-primary" onclick="gmSendGift()">ثبت هدیه</button></section>'+
    '<div id="gm-gift-log"></div></div>';
  gmRenderFeed(g('gm-gift-log'),GM.admin.feed,false);
  gmGiftLinks();
}
async function gmGiftLinks(){
  var type=g('gm-gf-link-type').value,sel=g('gm-gf-link'),rows=[];
  if(type==='task')rows=(D.t||[]).slice().sort(function(a,b){return ((b.status==='done')-(a.status==='done'))||(b.id-a.id);}).slice(0,500)
    .map(function(t){return [t.id,'#'+t.id+' '+(t.title||'')];});
  else if(type==='project')rows=(D.p||[]).map(function(p){return [p.id,(p.cname?p.cname+' / ':'')+p.name];});
  else{
    var list=(typeof V7!=='undefined'&&V7.contracts)||[];
    if(!list.length&&can('contracts.view')){var r=await api('/contracts',{});list=(r&&r.ok&&(r.rows||r.contracts))||[];}
    rows=list.map(function(c){return [c.id,(c.contract_number?c.contract_number+' — ':'')+(c.title||('#'+c.id))];});
  }
  sel.innerHTML=gmSelectOptions(rows,'',rows.length?'— انتخاب کنید —':'موردی در دسترس نیست');gmSync();
}
async function gmSendGift(){
  var payload={to_user:Number(g('gm-gf-user').value),item_id:Number(g('gm-gf-item').value),reason:g('gm-gf-reason').value.trim(),
    link_type:g('gm-gf-link-type').value,link_id:Number(g('gm-gf-link').value)};
  if(!payload.to_user||!payload.item_id)return toast('گیرنده و آیتم را انتخاب کنید','err');
  if(payload.reason.length<10)return toast('دلیل هدیه را کامل بنویسید (حداقل ۱۰ حرف)','err');
  if(!payload.link_id)return toast('تسک، پروژه یا قرارداد مرتبط را انتخاب کنید','err');
  var r=await api('/game/admin/gift',payload);if(!r.ok)return toast(r.error||'خطا','err');
  toast('هدیه ثبت شد و در دفتر هدیه‌ها نمایش داده می‌شود','ok');gmLoadAdminTab();
}

function gmRenderFulfil(r,kind){
  var body=g('gm-admin-body');if(!body)return;if(!r||!r.ok){body.innerHTML=gmErr(r);return;}
  var rows=r.rows||[],pending=kind==='pay'?'pending_payment':'pending_delivery';
  var note=kind==='pay'?'پاداش‌های مالی خریده‌شده؛ بعد از پرداخت همراه حقوق، «پرداخت شد» را بزنید.':
    'کالا، کارت هدیه، آیتم «سایر» و صندوق‌های کامل‌شده تیم؛ بعد از تحویل، «تحویل شد» را بزنید.';
  if(!rows.length){body.innerHTML='<p class="gm-muted">'+note+'</p>'+gmEmpty('موردی در این لیست نیست.');return;}
  body.innerHTML='<p class="gm-muted">'+note+' این لیست تأیید نیست؛ فقط برای این است که تحویل فراموش نشود.</p>'+
    '<div class="gm-table-wrap"><table class="gm-table"><thead><tr><th>نفر / تیم</th><th>آیتم</th>'+(kind==='pay'?'<th>مبلغ (ریال)</th>':'')+'<th>تاریخ</th><th>وضعیت</th><th></th></tr></thead><tbody>'+rows.map(function(o){
      var who=escHtml(o.name)+(o.team_name&&o.item_type==='team_pot'?'<br><small class="gm-muted">تیم '+escHtml(o.team_name)+'</small>':'');
      return '<tr><td>'+who+'</td><td>'+escHtml(o.item_name)+(o.gift_id?' <span class="gm-pill">🎁 هدیه</span>':'')+(o.note?'<br><small class="gm-muted">'+escHtml(o.note)+'</small>':'')+'</td>'+
        (kind==='pay'?'<td>'+gmNum(o.reward_amount)+'</td>':'')+'<td>'+gmDateTime(o.created_at)+'</td>'+
        '<td><span class="gm-status s-'+escHtml(o.status)+'">'+escHtml(o.status_label)+'</span>'+(o.fulfilled_at?'<br><small class="gm-muted">'+gmDate(o.fulfilled_at)+' · '+escHtml(o.fulfilled_by_name||'')+'</small>':'')+'</td>'+
        '<td class="gm-acts">'+(o.status===pending?'<button type="button" class="v7-mini primary" onclick="gmMark(\''+kind+'\','+o.id+')">'+(kind==='pay'?'پرداخت شد':'تحویل شد')+'</button>':'')+'</td></tr>';
    }).join('')+'</tbody></table></div>';
}
async function gmMark(kind,id){
  var r=await api(kind==='pay'?'/game/admin/payment_mark':'/game/admin/deliver_mark',{id:id});if(!r.ok)return toast(r.error||'خطا','err');
  toast(kind==='pay'?'پرداخت ثبت شد':'تحویل ثبت شد','ok');gmLoadAdminTab();
}

function gmStars(id,value){
  var v=Number(value||0),h='<span class="gm-stars" id="'+id+'" data-value="'+v+'" role="radiogroup" aria-label="ستاره">';
  for(var i=1;i<=5;i++)h+='<button type="button" class="gm-star'+(i<=v?' on':'')+'" data-v="'+i+'" aria-label="'+gmFa(i)+' ستاره" onclick="gmStarPick(\''+id+'\','+i+')">★</button>';
  return h+'</span>';
}
function gmStarPick(id,v){
  var el=g(id);if(!el)return;el.setAttribute('data-value',String(v));
  el.querySelectorAll('.gm-star').forEach(function(b){b.classList.toggle('on',Number(b.getAttribute('data-v'))<=v);});
  var preview=g(id+'-coins'),per=(GM.admin.monthly||{}).coins_per_star||0;if(preview)preview.textContent=gmNum(v*per)+' سکه';
}
function gmStarValue(id){var el=g(id);return el?Number(el.getAttribute('data-value')||0):0;}
function gmRenderMonthly(){
  var r=GM.admin.monthly||{},body=g('gm-admin-body');if(!body)return;if(!r.ok){body.innerHTML=gmErr(r);return;}
  GM.admin.monthKey=r.month;
  var html='<div class="gm-toolbar"><select class="gm-sel" id="gm-mo-month" onchange="gmMonthChange()">'+gmSelectOptions((r.months||[]).map(function(m){return [m.key,m.label];}),r.month)+'</select>'+
    '<small class="gm-muted">هر ستاره '+gmNum(r.coins_per_star)+' سکه است. ستاره را می‌توانید بعداً عوض کنید؛ فقط تفاوت سکه ثبت می‌شود. کارنامه از داده‌های ثبت‌شده در سیستم ساخته شده است.</small></div>';
  var rows=r.rows||[];
  if(!rows.length)html+=gmEmpty('پلنر، کارشناس مالی یا کارشناس اجرایی فعالی وجود ندارد.');
  html+=rows.map(function(p){
    var rt=p.rating,sid='gm-st-'+p.id;
    return '<section class="gm-card gm-month-row"><div class="gm-month-head"><b>'+escHtml(p.name)+'</b><span class="gm-pill">'+escHtml(GM_ROLES[p.role]||p.role)+'</span>'+
      (rt?'<small class="gm-muted">ثبت‌شده: '+gmFa(rt.stars)+' ستاره · '+gmNum(rt.coins)+' سکه</small>':'<small class="gm-warn">هنوز ستاره نگرفته است</small>')+'</div>'+
      '<ul class="gm-card-list">'+(p.card||[]).map(function(c){return '<li><span>'+escHtml(c.label)+'</span><b>'+escHtml(c.value)+'</b></li>';}).join('')+'</ul>'+
      '<div class="gm-month-form">'+gmStars(sid,rt?rt.stars:0)+'<span class="gm-muted" id="'+sid+'-coins">'+(rt?gmNum(rt.coins)+' سکه':'')+'</span>'+
      '<input class="fi" id="'+sid+'-note" maxlength="500" placeholder="یادداشت برای خود فرد (اختیاری)" value="'+escHtml(rt&&rt.note?rt.note:'')+'">'+
      '<button type="button" class="btn btn-primary" onclick="gmSaveMonthly('+p.id+')">ثبت ستاره</button></div></section>';
  }).join('');
  body.innerHTML=html;
}
function gmMonthChange(){GM.admin.monthKey=g('gm-mo-month').value;gmLoadAdminTab();}
async function gmSaveMonthly(uid){
  var sid='gm-st-'+uid,stars=gmStarValue(sid);if(!stars)return toast('ستاره را انتخاب کنید','err');
  var r=await api('/game/admin/monthly_save',{user_id:uid,month:GM.admin.monthKey,stars:stars,note:(g(sid+'-note')||{}).value||''});
  if(!r.ok)return toast(r.error||'خطا','err');toast('ستاره ثبت شد: '+gmNum(r.coins)+' سکه','ok');gmLoadAdminTab();
}

function gmRenderEconomy(){
  var r=GM.admin.economy||{},body=g('gm-admin-body');if(!body)return;if(!r.ok){body.innerHTML=gmErr(r);return;}
  var t=r.totals||{},rows=r.rows||[],adjust=can('wallet.adjust');
  var tiles=[['سکه صادرشده',t.issued],['سکه خرج‌شده',t.spent],['موجودی کل (تعهد شرکت)',t.outstanding],['منقضی تا یک ماه دیگر',t.expiring_soon],['منقضی‌شده',t.expired]];
  var html='<div class="gm-tiles">'+tiles.map(function(x){return '<div class="gm-tile"><span>'+x[0]+'</span>'+gmCoin(x[1]||0)+'</div>';}).join('')+'</div>';
  html+=rows.length?'<div class="gm-table-wrap"><table class="gm-table"><thead><tr><th>نام</th><th>نقش</th><th>موجودی</th><th>منقضی تا یک ماه</th><th>کل دریافت</th><th>کل خرج</th>'+(adjust?'<th></th>':'')+'</tr></thead><tbody>'+rows.map(function(p){
    return '<tr><td>'+escHtml(p.name)+'</td><td>'+escHtml(GM_ROLES[p.role]||p.role)+'</td><td class="'+(p.balance<0?'gm-minus':'')+'">'+gmNum(p.balance)+'</td><td>'+gmNum(p.expiring_soon)+'</td><td>'+gmNum(p.earned)+'</td><td>'+gmNum(p.spent)+'</td>'+
      (adjust?'<td><button type="button" class="v7-mini" onclick="gmOpenAdjust('+p.id+')">اصلاح موجودی</button></td>':'')+'</tr>';
  }).join('')+'</tbody></table></div>':gmEmpty('کاربری با کیف پول وجود ندارد.');
  body.innerHTML=html;
}
function gmOpenAdjust(uid){
  var p=((GM.admin.economy||{}).rows||[]).find(function(x){return x.id===uid;});if(!p)return;
  GM.adjustUser=uid;g('gm-adj-who').textContent=p.name+' — موجودی فعلی '+gmNum(p.balance)+' سکه';
  g('gm-adj-amount').value='';g('gm-adj-reason').value='';openM('gm-m-adjust');
}
async function gmSaveAdjust(){
  var amount=Number(toEnDigits(g('gm-adj-amount').value||'0')),reason=g('gm-adj-reason').value.trim();
  if(!amount)return toast('مقدار را وارد کنید؛ برای کم کردن، عدد منفی بنویسید','err');
  if(reason.length<5)return toast('دلیل اصلاح را بنویسید؛ خود کاربر آن را می‌بیند','err');
  var r=await api('/game/admin/wallet_adjust',{user_id:GM.adjustUser,amount:amount,reason:reason});if(!r.ok)return toast(r.error||'خطا','err');
  closeM('gm-m-adjust');toast('موجودی اصلاح شد','ok');gmLoadAdminTab();
}

function gmRenderSettings(){
  var r=GM.admin.settings||{},body=g('gm-admin-body');if(!body)return;if(!r.ok){body.innerHTML=gmErr(r);return;}
  var s=r.settings||{};
  body.innerHTML='<section class="gm-card gm-settings">'+GM_SETTINGS.map(function(row){
    var key=row[0],label=row[1],kind=row[2],hint=row[3],value=s[key]==null?'':s[key],input;
    if(kind==='switch')input='<label class="sw"><input type="checkbox" id="gm-set-'+key+'"'+(String(value)==='1'?' checked':'')+'><span class="sw-slider"></span></label>';
    else input='<input class="fi" id="gm-set-'+key+'" '+(kind==='number'?'type="number" min="0" dir="ltr"':'dir="ltr"')+' value="'+escHtml(String(value))+'">';
    return '<div class="gm-setting"><div><b>'+escHtml(label)+'</b>'+(hint?'<small class="gm-muted">'+escHtml(hint)+'</small>':'')+'</div>'+input+'</div>';
  }).join('')+'<div class="gm-toolbar"><button type="button" class="btn btn-primary" onclick="gmSaveSettings()">ذخیره تنظیمات</button></div></section>';
}
async function gmSaveSettings(){
  var out={};
  GM_SETTINGS.forEach(function(row){var el=g('gm-set-'+row[0]);if(!el)return;out[row[0]]=row[2]==='switch'?(el.checked?'1':'0'):toEnDigits(el.value||'');});
  var r=await api('/game/admin/settings_save',{settings:out});if(!r.ok)return toast(r.error||'خطا','err');
  toast('تنظیمات ذخیره شد','ok');gmLoadSummary(true);gmLoadAdminTab();
}

// ── modals ─────────────────────────────────────────────────────────────────
function gmModalsHtml(){
  var typeOptions=Object.keys(GM_TYPES).map(function(k){return '<option value="'+k+'">'+GM_TYPES[k]+'</option>';}).join('');
  return ''+
  '<div class="mo" id="gm-m-buy"><div class="md"><div class="mh"><span class="mi">🛒</span><h3 id="gm-buy-title">خرید</h3><button class="mx" onclick="closeM(\'gm-m-buy\')">✕</button></div>'+
    '<div class="mb" id="gm-buy-body"></div><div class="mf"><button class="btn btn-ghost" onclick="closeM(\'gm-m-buy\')">انصراف</button><button class="btn btn-primary" id="gm-buy-go" onclick="gmConfirmBuy()">تأیید خرید</button></div></div></div>'+
  '<div class="mo" id="gm-m-date"><div class="md"><div class="mh"><span class="mi">📅</span><h3>روز استفاده</h3><button class="mx" onclick="closeM(\'gm-m-date\')">✕</button></div><div class="mb">'+
    '<div class="fg"><label class="fl">روز <span class="r">*</span></label><input class="fi" id="gm-dt-date" readonly placeholder="انتخاب روز" onclick="openDP(\'gm-dt-date\')"><small class="gm-muted">از فردا به بعد و یک روز کاری.</small></div>'+
    '<div class="fg" id="gm-dt-time-row"><label class="fl">ساعت شروع</label><input class="fi" id="gm-dt-time" type="time" value="08:00"></div>'+
    '</div><div class="mf"><button class="btn btn-ghost" onclick="closeM(\'gm-m-date\')">انصراف</button><button class="btn btn-primary" onclick="gmSaveDate()">ثبت</button></div></div></div>'+
  '<div class="mo" id="gm-m-item"><div class="md wide"><div class="mh"><span class="mi">🎁</span><h3 id="gm-item-title">آیتم</h3><button class="mx" onclick="closeM(\'gm-m-item\')">✕</button></div><div class="mb"><div class="gm-item-form">'+
    '<div class="gm-img-edit"><div class="gm-img-preview" id="gm-it-preview"><span>🖼</span></div>'+
      '<label class="btn btn-ghost gm-file-btn">انتخاب عکس<input type="file" id="gm-it-file" accept="image/png,image/jpeg,image/webp,image/gif" onchange="gmItemFile(this)"></label>'+
      '<button type="button" class="v7-mini" onclick="gmItemNoImage()">بدون عکس</button><small class="gm-muted">عکس خودکار تا ۶۴۰ پیکسل کوچک می‌شود.</small></div>'+
    '<div class="gm-form-main">'+
      '<div class="fr"><div class="fg"><label class="fl">نام <span class="r">*</span></label><input class="fi" id="gm-it-name" maxlength="150"></div>'+
        '<div class="fg"><label class="fl">نوع <span class="r">*</span></label><select class="fi" id="gm-it-type" onchange="gmItemTypeChanged()">'+typeOptions+'</select></div></div>'+
      '<div class="fr"><div class="fg"><label class="fl">قیمت (سکه) <span class="r">*</span></label><input class="fi" id="gm-it-price" type="number" min="1" dir="ltr" oninput="gmPriceHint()"><small class="gm-muted" id="gm-it-hint"></small></div>'+
        '<div class="fg" id="gm-it-stock-row"><label class="fl">موجودی کل (آیتم محدود)</label><input class="fi" id="gm-it-stock" type="number" min="1" dir="ltr" placeholder="نامحدود"></div>'+
        '<div class="fg"><label class="fl">سقف خرید هر نفر در ماه</label><input class="fi" id="gm-it-limit" type="number" min="1" dir="ltr" placeholder="بدون سقف"></div></div>'+
      '<div class="fr"><div class="fg"><label class="fl">شروع فروش</label><input class="fi" id="gm-it-from" readonly onclick="openDP(\'gm-it-from\')" placeholder="از همین حالا"></div>'+
        '<div class="fg"><label class="fl">پایان فروش</label><input class="fi" id="gm-it-to" readonly onclick="openDP(\'gm-it-to\')" placeholder="بدون پایان"></div></div>'+
      '<div class="fr gm-type-row" data-types="leave"><div class="fg"><label class="fl">مدت مرخصی</label><select class="fi" id="gm-it-leave-mode" onchange="gmItemTypeChanged()"><option value="day">یک روز</option><option value="hours">چند ساعت</option></select></div>'+
        '<div class="fg" id="gm-it-hours-row"><label class="fl">تعداد ساعت</label><input class="fi" id="gm-it-hours" type="number" min="0.5" max="8" step="0.5" dir="ltr" value="2"></div></div>'+
      '<div class="fr gm-type-row" data-types="money"><div class="fg"><label class="fl">مبلغ پاداش (ریال) <span class="r">*</span></label><input class="fi" id="gm-it-reward" dir="ltr" inputmode="numeric"></div></div>'+
      '<div class="fr gm-type-row" data-types="team_pot"><div class="fg"><label class="fl">هدف صندوق تیم (سکه) <span class="r">*</span></label><input class="fi" id="gm-it-goal" type="number" min="1" dir="ltr"><small class="gm-muted">قیمت، مقدار پیشنهادی هر مشارکت است.</small></div></div>'+
      '<div class="fr gm-type-row" data-types="cosmetic"><div class="fg"><label class="fl">نوع تزئین</label><select class="fi" id="gm-it-slot" onchange="gmItemTypeChanged()"><option value="frame">قاب آواتار</option><option value="chat">رنگ حباب چت</option><option value="title">لقب زیر نام</option></select></div>'+
        '<div class="fg" id="gm-it-value-sel-row"><label class="fl">رنگ</label><select class="fi" id="gm-it-value-sel"></select></div>'+
        '<div class="fg" id="gm-it-value-text-row"><label class="fl">لقب</label><input class="fi" id="gm-it-value-text" maxlength="30"></div></div>'+
      '<div class="fg"><label class="fl">توضیح</label><textarea class="fi" id="gm-it-desc" maxlength="1000"></textarea></div>'+
      '<div class="gm-checks"><label><input type="checkbox" id="gm-it-active" checked> فعال در فروشگاه</label><label><input type="checkbox" id="gm-it-public" checked> نمایش در تاریخچه عمومی خرید</label></div>'+
    '</div></div></div><div class="mf"><button class="btn btn-ghost" onclick="closeM(\'gm-m-item\')">انصراف</button><button class="btn btn-primary" onclick="gmSaveItem()">ذخیره</button></div></div></div>'+
  '<div class="mo" id="gm-m-fest"><div class="md wide"><div class="mh"><span class="mi">🎉</span><h3 id="gm-fest-title">جشنواره</h3><button class="mx" onclick="closeM(\'gm-m-fest\')">✕</button></div><div class="mb">'+
    '<div class="fr"><div class="fg"><label class="fl">عنوان <span class="r">*</span></label><input class="fi" id="gm-fe-title" maxlength="150" placeholder="مثلاً جشنواره نوروز"></div>'+
      '<div class="fg"><label class="fl">شروع <span class="r">*</span></label><input class="fi" id="gm-fe-start" readonly onclick="openDP(\'gm-fe-start\')"></div>'+
      '<div class="fg"><label class="fl">پایان <span class="r">*</span></label><input class="fi" id="gm-fe-end" readonly onclick="openDP(\'gm-fe-end\')"></div></div>'+
    '<label class="fl">آیتم‌ها و درصد تخفیف (۱ تا ۹۰)</label><div class="gm-fest-list" id="gm-fe-items"></div>'+
    '</div><div class="mf"><button class="btn btn-ghost" onclick="closeM(\'gm-m-fest\')">انصراف</button><button class="btn btn-primary" onclick="gmSaveFest()">ذخیره</button></div></div></div>'+
  '<div class="mo" id="gm-m-adjust"><div class="md"><div class="mh"><span class="mi">🪙</span><h3>اصلاح موجودی سکه</h3><button class="mx" onclick="closeM(\'gm-m-adjust\')">✕</button></div><div class="mb">'+
    '<p id="gm-adj-who" class="gm-muted"></p>'+
    '<div class="fg"><label class="fl">مقدار (برای کم کردن، عدد منفی) <span class="r">*</span></label><input class="fi" id="gm-adj-amount" type="number" dir="ltr"></div>'+
    '<div class="fg"><label class="fl">دلیل <span class="r">*</span></label><textarea class="fi" id="gm-adj-reason" maxlength="300" placeholder="این دلیل برای خود کاربر نمایش داده می‌شود"></textarea></div>'+
    '</div><div class="mf"><button class="btn btn-ghost" onclick="closeM(\'gm-m-adjust\')">انصراف</button><button class="btn btn-primary" onclick="gmSaveAdjust()">ثبت</button></div></div></div>';
}

// ── help ───────────────────────────────────────────────────────────────────
function gmHelp(add){
  if(!CU)return;
  var role=CU.role,wallet=['support','lead','planner','finance','reporter'].indexOf(role)>=0;
  if(can('menu.club')||can('tasks.evaluate')||can('shop.manage_items'))add('club','<div class="hlp-card"><h3>🏅 امتیاز و سکه در یک نگاه</h3><ul>'+
    '<li><b>دو واحد:</b> امتیاز، سطح و رتبه شما را می‌سازد و خرج نمی‌شود. سکه در کیف پول جمع می‌شود و با آن از فروشگاه خرید می‌کنید.</li>'+
    '<li><b>چه کسی سکه می‌گیرد:</b> پشتیبان از تسک تأییدشده؛ پلنر، کارشناس مالی و کارشناس اجرایی ماهانه با ستاره ادمین. مدیر و ادمین کنترل‌گرند و کیف پول ندارند.</li>'+
    '<li><b>سطح:</b> تازه‌کار، کاردان، ماهر، خبره و استاد. از جمع امتیاز همه دوران ساخته می‌شود و هیچ‌وقت کم نمی‌شود.</li>'+
    '<li><b>فصل:</b> هر سه ماه (بهار، تابستان، پاییز، زمستان) امتیاز فصل از صفر شروع می‌شود؛ سکه صفر نمی‌شود. برترین‌های هر فصل در «تالار افتخارات» می‌مانند.</li>'+
    '<li><b>انقضا:</b> هر سکه ۱۲ ماه بعد از دریافت منقضی می‌شود و در خرید، اول قدیمی‌ترها خرج می‌شوند. یک ماه قبل از انقضا اعلان می‌گیرید.</li>'+
    '<li><b>هرگز امتیاز ندارد:</b> حضور و غیاب، ساعت کار، ورود به برنامه و پیام.</li>'+
    '<li><i>اعداد این راهنما مقدارهای پیش‌فرض‌اند و مدیر سیستم می‌تواند آن‌ها را از تنظیمات تغییر دهد.</i></li></ul></div>');
  if(wallet&&(role==='support'||role==='lead')&&can('gamification.view_own'))add('club','<div class="hlp-card"><h3>⚙ امتیاز تسک چطور حساب می‌شود</h3>'+
    '<p>فقط تسکی امتیاز دارد که بعد از نصب این نسخه تأیید نهایی شده باشد و تأییدکننده‌اش خود شما نباشید. امتیاز = ۱۰ × وزن پیشرفت × وزن دسته × ضریب کیفیت × ضریب سروقت × ضریب ستاره.</p><ul>'+
    '<li><b>ضریب کیفیت:</b> بدون برگشت ۱٫۲؛ هر برگشت ۰٫۱ کمتر؛ کمترین ۰٫۸.</li>'+
    '<li><b>ضریب سروقت:</b> تحویل تا موعدی که هنگام واگذاری ثبت بود ۱٫۲؛ تأخیر جریمه ندارد و ضریب ۱ است.</li>'+
    '<li><b>ضریب ستاره مدیر:</b> ۱ ستاره ۰٫۸، ۳ ستاره ۱ و ۵ ستاره ۱٫۲.</li>'+
    '<li><b>تسک مشترک:</b> بر اساس زمان واقعی کار هر نفر تقسیم می‌شود. اگر زمانی ثبت نشده باشد، کل امتیاز به پشتیبان اصلی می‌رسد.</li>'+
    '<li><b>سکه:</b> هر ۱۰ امتیاز یک سکه. لحظه تأیید، اعلان امتیاز و سکه همراه با دلیلش می‌آید.</li>'+
    '<li><b>سقف روزانه:</b> از پانزدهمین تسکِ تأییدشده در یک روز به بعد، امتیاز نصف می‌شود تا خرد کردن تسک‌ها سودی نداشته باشد.</li>'+
    '<li><b>برگشت امتیاز:</b> اگر تسک تأییدشده حذف یا دوباره باز شود، امتیاز و سکه‌اش پس گرفته می‌شود. اگر سکه را خرج کرده باشید، موجودی موقتاً منفی می‌شود و از درآمد بعدی جبران می‌شود.</li>'+
    '<li><b>مثال:</b> تسک وزن ۲، بدون برگشت، سروقت و ۴ ستاره: ۱۰ × ۲ × ۱٫۲ × ۱٫۲ × ۱٫۱ ≈ ۳۲ امتیاز و ۳ سکه.</li></ul></div>');
  if(wallet&&role!=='support'&&can('gamification.view_own')){
    var card={planner:'سرعت بررسی تسک‌های جدید، مدت ماندن تسک‌ها در صف تأیید، درصد سروقت بودن تیم و تسک‌هایی که کامل ساخته‌اید',
      finance:'صورت‌وضعیت‌های برنامه ماه که به‌موقع ثبت شده‌اند، صورت‌وضعیت‌هایی که بار اول تأیید شده‌اند، ارسال مالیاتی بی‌خطا و ایرادهای داده مالی',
      reporter:'کار این نقش کمتر در سیستم ثبت می‌شود و ستاره بیشتر به نظر ادمین بستگی دارد'}[role]||'';
    add('club','<div class="hlp-card"><h3>⭐ ستاره ماهانه و کارنامه</h3><ul>'+
      '<li>آخر هر ماه ادمین به شما ۱ تا ۵ ستاره می‌دهد. سکه آن ماه برابر است با تعداد ستاره × «سکه هر ستاره» (پیش‌فرض ۲۰).</li>'+
      '<li>ادمین هنگام ستاره‌دهی یک کارنامه خودکار از داده‌های سیستم کنار اسم شما می‌بیند: '+card+'.</li>'+
      '<li>ستاره و یادداشت ادمین با اعلان به شما می‌رسد و در «امتیاز و فروشگاه» ← «کارت من» ثبت می‌شود. اگر ادمین ستاره‌ای را عوض کند، فقط تفاوت سکه ثبت می‌شود.</li>'+
      (role==='planner'?'<li>از تسکی که خودتان تعریف یا تأیید می‌کنید سکه نمی‌گیرید، چون هم تعریف‌کننده‌اید و هم ذی‌نفع.</li>':'')+'</ul></div>');
  }
  if(can('gamification.view_own')||can('gamification.team_board')){
    var mine=GM_BADGES.filter(function(b){return !wallet||b[2].split(',').indexOf(role)>=0;});
    add('club','<div class="hlp-card"><h3>🎖 نشان‌ها و مأموریت تیمی</h3><p>هر نشان یک‌بار سکه جایزه دارد و هر فصل (یا هر ماه برای نشان‌های ماهانه) دوباره قابل گرفتن است.</p><ul>'+
      mine.map(function(b){return '<li><b>'+b[0]+':</b> '+b[1]+'.</li>';}).join('')+
      '<li><b>مأموریت تیمی ماهانه:</b> «صفر تسک معوق در پایان ماه»، «۹۰٪ تحویل سروقت» (با حداقل ۵ تسک) و «رسیدن به هدف مالی ماه تیم». اگر انجام شود، همه اعضای تیم به‌جز مدیر سکه مساوی می‌گیرند و اعلان می‌آید. پیشرفت ماه جاری روی داشبورد دیده می‌شود.</li>'+
      (can('gamification.team_board')?'<li><b>رتبه‌بندی:</b> فقط بین پشتیبان‌های هر تیم. هر کس جایگاه خودش، فاصله‌اش تا نفر بالاتر و سه نفر اول را می‌بیند؛ مقایسه تیم‌ها با میانگین امتیاز هر عضو است.</li>':'')+'</ul></div>');
  }
  if(can('shop.buy'))add('club','<div class="hlp-card"><h3>🛒 خرید از فروشگاه</h3><ul>'+
    '<li>در تب «فروشگاه» همه آیتم‌ها دیده می‌شوند؛ آیتم غیرفعال کم‌رنگ است و خریدنی نیست. خرید تأیید نمی‌خواهد و سکه همان لحظه کسر می‌شود.</li>'+
    '<li><b>مرخصی تشویقی و دورکاری:</b> روز را انتخاب می‌کنید (از فردا به بعد و روز کاری) و خودکار در تقویم ثبت می‌شود. مرخصی تشویقی جزو مرخصی رسمی نیست. تا روز قبل از آن تاریخ، از «خریدهای من» روز را عوض کنید یا خرید را لغو کنید تا سکه کامل برگردد.</li>'+
    '<li><b>پاداش مالی:</b> در لیست پرداخت کارشناس مالی قرار می‌گیرد و همراه حقوق بعدی پرداخت می‌شود. کالا، کارت هدیه و «سایر» را ادمین تحویل می‌دهد.</li>'+
    '<li><b>تزئینی:</b> قاب آواتار، لقب و رنگ حباب چت همان لحظه روی پروفایل و پیام‌رسان شما اعمال می‌شود؛ هر وقت خواستید از همان کارت آیتم «برداشتن» را بزنید.</li>'+
    '<li><b>صندوق تیم:</b> هر مقدار سکه که بخواهید به صندوق تیمتان می‌ریزید؛ وقتی به هدف رسید، برنامه تیمی آزاد می‌شود.</li>'+
    '<li><b>آیتم محدود و جشنواره:</b> بعضی آیتم‌ها موجودی کل یا سقف خرید ماهانه دارند. در جشنواره، قیمت قبلی خط می‌خورد و درصد تخفیف و زمان پایان نمایش داده می‌شود.</li>'+
    '<li><b>لیست آرزو:</b> با ♥ آیتم را نشان کنید تا ببینید چند درصد سکه‌اش را دارید و اگر تخفیف خورد اعلان بگیرید.</li>'+
    '<li><b>تاریخچه عمومی:</b> همه می‌بینند چه کسی چه چیزی خریده است، مگر آیتم‌هایی که ادمین از تاریخچه عمومی خارج کرده باشد.</li></ul></div>');
  if(can('gamification.kudos'))add('club','<div class="hlp-card"><h3>🙏 قدردانی از همکار</h3><ul>'+
    '<li>در صفحه یک تسکِ انجام‌شده، کنار نام همکارانی که روی آن کار کرده‌اند دکمه «ممنونم» هست.</li>'+
    '<li>هر نفر هفته‌ای ۳ «ممنونم» دارد و گیرنده ۲ سکه می‌گیرد. از یک نفر به یک نفر فقط ماهی یک‌بار سکه حساب می‌شود تا جلوی تبانی گرفته شود.</li></ul></div>');
  if(can('tasks.evaluate'))add('club','<div class="hlp-card"><h3>⭐ ارزیابی ستاره‌ای تسک</h3><ul>'+
    '<li>در صفحه تسک، به هر نفری که روی آن کار کرده ۱ تا ۵ ستاره بدهید. ۳ ستاره یعنی امتیاز عادی؛ ۵ ستاره ۲۰٪ بیشتر و ۱ ستاره ۲۰٪ کمتر.</li>'+
    '<li>اگر ستاره را بعداً عوض کنید، امتیاز همان تسک به‌روز می‌شود و فرد اعلان می‌گیرد. اثر ستاره عمداً کوچک است تا سلیقه‌ها مستقیم به سکه تبدیل نشوند.</li>'+
    '<li>ارزیابی‌های قبل از این نسخه، که عدد بدون سقف بودند، در تاریخچه می‌مانند ولی روی امتیاز اثری ندارند.</li></ul></div>');
  if(can('shop.manage_items'))add('club','<div class="hlp-card"><h3>🧰 مدیریت آیتم‌های فروشگاه</h3><ul>'+
    '<li>از «مدیریت فروشگاه» ← «آیتم‌ها» آیتم با نام، عکس، توضیح، نوع و قیمت ثبت، ویرایش یا حذف کنید. حذف آیتمی که قبلاً خریده شده، آن را بایگانی می‌کند تا تاریخچه سالم بماند.</li>'+
    '<li><b>انواع:</b> مرخصی تشویقی (یک روز یا چند ساعت)، دورکاری یا ورود شناور، پاداش مالی (با مبلغ ریالی)، کالا یا کارت هدیه، تزئینی (قاب، رنگ چت یا لقب)، صندوق تیم (با هدف سکه) و سایر.</li>'+
    '<li><b>فعال و غیرفعال:</b> با کلید کنار هر آیتم، دستی و بدون تاریخ؛ می‌تواند طولانی‌مدت بماند و ربطی به جشنواره ندارد.</li>'+
    '<li><b>آیتم محدود:</b> موجودی کل، سقف خرید هر نفر در ماه و بازه فروش را تعیین کنید.</li>'+
    '<li><b>راهنمای قیمت:</b> کنار قیمت نوشته می‌شود «حدوداً معادل چند روز کار یک پشتیبان» تا قیمت نه دست‌نیافتنی باشد و نه خیلی ارزان.</li>'+
    '<li>با تیک «نمایش در تاریخچه عمومی» می‌توانید آیتم‌های حساس، مثل پاداش مالی، را از تاریخچه عمومی خارج کنید.</li></ul></div>');
  if(can('shop.gift'))add('club','<div class="hlp-card"><h3>💝 هدیه دادن</h3><ul>'+
    '<li>برای کار خیلی مهم یا پروژه پول‌ساز، از «مدیریت فروشگاه» ← «هدیه» یک آیتم به همکار هدیه دهید؛ برای گیرنده رایگان است.</li>'+
    '<li>دلیل نوشتاری (حداقل ۱۰ حرف) و اتصال به یک تسک، پروژه یا قرارداد مشخص اجباری است. همه هدیه‌ها در «دفتر هدیه‌ها» برای همه کارکنان دیده می‌شوند تا جای پارتی‌بازی نماند.</li>'+
    '<li>هر مدیر سقف هدیه ماهانه دارد (پیش‌فرض ۵). مرخصی یا دورکاری هدیه را گیرنده خودش از «خریدهای من» تاریخ‌گذاری می‌کند.</li></ul></div>');
  if(can('shop.manage_festivals'))add('club','<div class="hlp-card"><h3>🎉 جشنواره</h3><ul>'+
    '<li>عنوان، تاریخ شروع و پایان را تعیین کنید، آیتم‌ها را انتخاب کنید و برای هر کدام درصد تخفیف (۱ تا ۹۰) بزنید؛ قیمت جدید خودکار حساب می‌شود.</li>'+
    '<li>جشنواره فقط تخفیف است و از فعال‌سازی جداست. آیتم غیرفعال در جشنواره هم خریدنی نیست تا دستی فعالش کنید.</li>'+
    '<li>هر آیتم در یک زمان فقط در یک جشنواره قرار می‌گیرد. کسانی که آیتم را در لیست آرزو دارند اعلان می‌گیرند. پایان جشنواره خودکار است.</li></ul></div>');
  if(can('ratings.monthly'))add('club','<div class="hlp-card"><h3>⭐ ستاره ماهانه</h3><ul>'+
    '<li>از «مدیریت فروشگاه» ← «ستاره ماهانه» ماه را انتخاب کنید؛ برای هر پلنر، کارشناس مالی و کارشناس اجرایی یک کارنامه خودکار نمایش داده می‌شود.</li>'+
    '<li>۱ تا ۵ ستاره و یادداشت اختیاری ثبت کنید. اگر برای ماهی ستاره ندهید، سکه‌ای برای آن ماه صادر نمی‌شود. تغییر بعدی ستاره فقط تفاوت سکه را ثبت می‌کند.</li></ul></div>');
  if(can('shop.deliver')||can('shop.pay_rewards'))add('club','<div class="hlp-card"><h3>📦 لیست تحویل و پرداخت</h3><ul>'+
    (can('shop.deliver')?'<li><b>لیست تحویل:</b> کالا، کارت هدیه، «سایر» و صندوق‌های کامل‌شده تیم. بعد از تحویل، «تحویل شد» را بزنید.</li>':'')+
    (can('shop.pay_rewards')?'<li><b>لیست پرداخت:</b> پاداش‌های مالی خریده‌شده با مبلغ ریالی. بعد از پرداخت همراه حقوق، «پرداخت شد» را بزنید.</li>':'')+
    '<li>این لیست‌ها تأیید نیستند؛ خرید قبلاً انجام شده و فقط برای این است که تحویل فراموش نشود.</li></ul></div>');
  if(can('economy.view')||can('wallet.adjust')||can('game.settings'))add('club','<div class="hlp-card"><h3>📊 اقتصاد سکه و تنظیمات</h3><ul>'+
    '<li><b>اقتصاد سکه:</b> سکه صادرشده، خرج‌شده، موجودی کل (تعهد شرکت) و سکه‌هایی که به‌زودی منقضی می‌شوند، به همراه موجودی هر نفر.</li>'+
    '<li><b>اصلاح موجودی:</b> فقط با دلیل؛ در لاگ ثبت می‌شود و خود کاربر هم آن را می‌بیند.</li>'+
    '<li><b>تنظیمات:</b> باز و بسته کردن فروشگاه، امتیاز لازم برای هر سکه، سکه هر ستاره، سکه نشان و مأموریت، سقف روزانه، سقف هدیه، «ممنونم» و انقضای سکه.</li>'+
    '<li>فروشگاه در ابتدا بسته است تا در ماه اول درآمد واقعی دیده و قیمت‌ها بر اساس آن تعیین شوند؛ امتیاز و سکه از همان روز اول جمع می‌شود.</li></ul></div>');
}
