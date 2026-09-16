// Exercises the real dashboard tab functions from ui.html against fixtures
// that mimic what the permission pass leaves behind for different roles.
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = path.join(__dirname, '..', 'src', 'web');
const html = fs.readFileSync(path.join(ROOT, 'ui.html'), 'utf8');

const names = ['dashSections', 'dashTabHasContent', 'renderDashTabs', 'applyDashTab', 'showDashTab'];
let code = '';
for (const n of names) {
  const m = html.match(new RegExp('^function ' + n + '\\([\\s\\S]*?^\\}', 'm'));
  if (!m) throw new Error('missing ' + n);
  code += m[0] + '\n';
}
const tabsDecl = html.match(/^var DASH_TABS=\[[\s\S]*?\];/m)[0];

// spec: {tab: 'visible' | 'hidden' | 'emptyInside'}
function build(spec) {
  const sec = k => {
    const state = spec[k] || 'visible';
    if (state === 'hidden') return `<div data-dash-tab="${k}" style="display:none"></div>`;
    if (state === 'emptyInside') {
      // Wrapper itself is not gated, every card inside is hidden.
      return `<div data-dash-tab="${k}"><div data-permission="x" style="display:none"></div></div>`;
    }
    return `<div data-dash-tab="${k}"><div data-permission="x">card</div></div>`;
  };
  const dom = new JSDOM(`<!doctype html><body>
    <div id="pg0">
      <div class="dash-tabs" id="dash-tabs"></div>
      ${['overview', 'me', 'team', 'finance', 'org'].map(sec).join('')}
    </div>
    <script>
      ${tabsDecl}
      var _dashTab=null, CU={role:'x'};
      function g(id){return document.getElementById(id);}
      ${code}
    <\/script></body>`, { runScripts: 'dangerously' });
  return dom.window;
}

let fails = 0;
const check = (label, actual, expected) => {
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  if (a !== e) { fails++; console.log('FAIL ' + label + ': got ' + a + ' want ' + e); }
  else console.log('ok   ' + label + ' -> ' + a);
};
const labels = w => Array.from(w.document.querySelectorAll('.dash-tab')).map(b => b.textContent.trim());
const visible = w => Array.from(w.document.querySelectorAll('#pg0 [data-dash-tab]'))
  .filter(el => !el.classList.contains('dash-hidden') && el.style.display !== 'none')
  .map(el => el.getAttribute('data-dash-tab'));

// A manager-like user: everything visible.
let w = build({});
w.renderDashTabs();
check('all five tabs offered', labels(w).length, 5);
check('first tab selected by default', visible(w), ['overview']);
w.showDashTab('finance');
check('switching shows only that group', visible(w), ['finance']);
check('active button follows the selection',
      Array.from(w.document.querySelectorAll('.dash-tab.active')).length, 1);

// A wrapper that is visible but whose every card is permission-hidden must not
// be offered - this is what produced empty tabs for everyone.
w = build({ team: 'emptyInside', org: 'emptyInside' });
w.renderDashTabs();
check('a tab whose cards are all hidden is not offered', labels(w).length, 3);
check('an empty group is never the default', visible(w), ['overview']);

// A support-like user: only two groups have content, so no bar at all.
w = build({ team: 'emptyInside', org: 'hidden', overview: 'emptyInside' });
w.renderDashTabs();
check('fewer than three groups means one continuous page',
      w.document.getElementById('dash-tabs').style.display, 'none');
// With no bar every wrapper is un-hidden; the ones with no permitted cards are
// simply empty divs. What matters is that the groups holding content are shown
// and that no group is left hidden behind a bar that does not exist.
check('the groups with content are shown',
      ['finance', 'me'].every(k => visible(w).includes(k)), true);
check('nothing is left hidden by a tab class',
      Array.from(w.document.querySelectorAll('#pg0 .dash-hidden')).length, 0);
check('only two groups actually had content',
      ['overview', 'me', 'team', 'finance', 'org'].filter(k => w.dashTabHasContent(k)).sort(),
      ['finance', 'me']);

// Permission-hidden sections stay hidden even when their tab is active.
w = build({ overview: 'hidden' });
w.renderDashTabs();
check('a permission-hidden section is not resurrected by its tab',
      w.document.querySelector('[data-dash-tab="overview"]').style.display, 'none');
check('the first tab with content is chosen instead', visible(w), ['me']);

// Only one group at all.
w = build({ me: 'hidden', team: 'hidden', finance: 'hidden', org: 'hidden' });
w.renderDashTabs();
check('no tab bar for a single group', w.document.getElementById('dash-tabs').style.display, 'none');
check('sole group is shown without tabs', visible(w), ['overview']);

console.log(fails ? '\n' + fails + ' FAILURE(S)' : '\nall dashboard-tab assertions passed');
process.exit(fails ? 1 : 0);
