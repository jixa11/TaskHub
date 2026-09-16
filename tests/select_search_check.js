// Exercises the real searchable-dropdown code from ui.html. The point of the
// design is that the native <select> stays the source of truth, so these
// assertions are mostly about NOT breaking existing readers and writers.
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = path.join(__dirname, '..', 'src', 'web');
const html = fs.readFileSync(path.join(ROOT, 'ui.html'), 'utf8');

const names = ['selSearchLabel', 'selSearchSync', 'selSearchWrap', 'selSearchClose',
               'selSearchOutside', 'selSearchReposition', 'selSearchOpen', 'applySelSearch'];
let code = '';
for (const n of names) {
  const m = html.match(new RegExp('^function ' + n + '\\([\\s\\S]*?^\\}', 'm'));
  if (!m) throw new Error('missing ' + n);
  code += m[0] + '\n';
}
const state = html.match(/^var _selPop=null,_selHost=null;/m)[0];
const escFn = html.match(/^function escHtml\([\s\S]*?^\}/m);

const dom = new JSDOM(`<!doctype html><body>
  <div class="fg">
    <select class="fi" id="single">
      <option value="">— انتخاب کنید —</option>
      <option value="1">تهران</option>
      <option value="2">اصفهان</option>
      <option value="3">شیراز</option>
    </select>
  </div>
  <div class="fg">
    <select class="fi" id="multi" multiple>
      <option value="a">علی</option>
      <option value="b">رضا</option>
      <option value="c">سارا</option>
    </select>
  </div>
  <script>
    ${state}
    function g(id){return document.getElementById(id);}
    function toFaDigits(v){return String(v);}
    ${escFn ? escFn[0] : 'function escHtml(s){return String(s==null?"":s);}'}
    ${code}
  <\/script></body>`, { runScripts: 'dangerously', pretendToBeVisual: true });

const { window } = dom;
const doc = window.document;
let fails = 0;
const check = (label, actual, expected) => {
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  if (a !== e) { fails++; console.log('FAIL ' + label + ': got ' + a + ' want ' + e); }
  else console.log('ok   ' + label + ' -> ' + a);
};

window.applySelSearch();
const single = doc.getElementById('single');
const multi = doc.getElementById('multi');

check('the native select survives', !!single, true);
check('select is wrapped once', doc.querySelectorAll('.sel-search').length, 2);
window.applySelSearch();
check('wrapping is idempotent', doc.querySelectorAll('.sel-search').length, 2);
check('placeholder shown when nothing is chosen',
      doc.querySelector('.sel-search .cap').textContent, '— انتخاب کنید —');

// Opening and filtering.
window.selSearchOpen(single.closest('.sel-search'));
const pop = doc.querySelector('.sel-pop');
check('popup opens on the body, clear of any clipping parent', pop.parentNode === doc.body, true);
check('all options listed initially', pop.querySelectorAll('.sel-opt').length, 4);
pop.querySelector('input').value = 'اصف';
pop.querySelector('input').dispatchEvent(new window.Event('input'));
check('typing filters the list', pop.querySelectorAll('.sel-opt').length, 1);
check('the surviving option is the match',
      pop.querySelector('.sel-opt').textContent, 'اصفهان');

// Choosing writes back to the real select and fires change.
let changes = 0;
single.addEventListener('change', () => changes++);
pop.querySelector('.sel-opt').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
check('value lands on the native select', single.value, '2');
check('change event fires so existing handlers still run', changes, 1);
check('single choice closes the popup', doc.querySelector('.sel-pop'), null);
check('button now shows the chosen label',
      single.closest('.sel-search').querySelector('.cap').textContent, 'اصفهان');

// Code that sets the value directly must still work.
single.value = '3';
window.applySelSearch();
check('programmatic value is reflected',
      single.closest('.sel-search').querySelector('.cap').textContent, 'شیراز');

// sOpts-style rebuild: options replaced, value preserved by the caller.
single.innerHTML = '<option value="">— انتخاب کنید —</option><option value="3">شیراز</option><option value="9">یزد</option>';
single.value = '9';
window.applySelSearch();
check('rebuilt options do not double-wrap', doc.querySelectorAll('.sel-search').length, 2);
check('label follows a rebuild',
      single.closest('.sel-search').querySelector('.cap').textContent, 'یزد');

// Multi-select keeps the popup open and accumulates choices.
window.selSearchOpen(multi.closest('.sel-search'));
const mpop = doc.querySelector('.sel-pop');
mpop.querySelectorAll('.sel-opt')[0].dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
check('multi keeps the popup open', !!doc.querySelector('.sel-pop'), true);
mpop.querySelectorAll('.sel-opt')[2].dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
check('both values selected on the native element',
      Array.from(multi.selectedOptions).map(o => o.value), ['a', 'c']);
check('multi label counts the picks',
      multi.closest('.sel-search').querySelector('.cap').textContent, 'علی، سارا');
// Clicking a chosen option again removes it.
doc.querySelector('.sel-pop').querySelectorAll('.sel-opt')[0]
  .dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
check('clicking again deselects', Array.from(multi.selectedOptions).map(o => o.value), ['c']);
window.selSearchClose();
check('close removes the popup', doc.querySelector('.sel-pop'), null);

// A disabled select must not open.
single.disabled = true;
window.applySelSearch();
check('disabled select disables the button',
      single.closest('.sel-search').querySelector('.sel-search-btn').disabled, true);
window.selSearchOpen(single.closest('.sel-search'));
check('disabled select does not open', doc.querySelector('.sel-pop'), null);

console.log(fails ? '\n' + fails + ' FAILURE(S)' : '\nall searchable-dropdown assertions passed');
process.exit(fails ? 1 : 0);
