// Runs the real access-matrix state functions out of v8_ui.js against a fake
// catalog, so the draft/dirty/bulk logic is exercised rather than eyeballed.
const fs = require('fs');
const path = require('path').join(__dirname, '..', 'src', 'web', 'v8_ui.js');
const src = fs.readFileSync(path, 'utf8');

const names = ['v8AccessRoleLabel', 'v8AccessLocked', 'v8AccessAllKeys', 'v8AccessSavedSet',
               'v8AccessChangedKeys', 'v8AccessToggle', 'v8AccessToggleGroup',
               'v8AccessSelectAll', 'v8AccessResetDefault', 'v8AccessCopyFrom', 'v8AccessRevert'];
let code = '';
for (const n of names) {
  const m = src.match(new RegExp('^function ' + n + '\\([\\s\\S]*?^\\}', 'm'));
  if (!m) throw new Error('could not extract ' + n);
  code += m[0] + '\n';
}

const prelude = `
var V8Access={roles:[],groups:[],current:null,nonDelegable:[],defaults:{},saved:new Set(),draft:new Set(),filter:'all'};
var CONFIRM=true;
function confirm(){return CONFIRM;}
function toFaDigits(v){return String(v);}
function toast(){}
function v8AccessRenderMatrix(){}   // rendering is not under test here
function v8AccessRenderRoles(){}
`;
const api = eval(prelude + code + '\n({V8Access:V8Access,setConfirm:function(v){CONFIRM=v;},'
  + names.map(n => n + ':' + n).join(',') + '})');

const A = api.V8Access;
A.groups = [
  {key: 'menus', label: 'منوها', permissions: [
    {key: 'menu.dashboard', label: 'داشبورد'},
    {key: 'menu.contracts', label: 'قراردادها'}]},
  {key: 'finance', label: 'مالی', permissions: [
    {key: 'contracts.view', label: 'مشاهده قرارداد'},
    {key: 'contracts.manage', label: 'ویرایش قرارداد'}]},
  {key: 'base', label: 'پایه', permissions: [
    {key: 'project_notes.view', label: 'مشاهده حساس'},
    {key: 'project_notes.manage', label: 'ویرایش حساس'}]},
  {key: 'system', label: 'سیستم', permissions: [
    {key: 'access_control.manage', label: 'مدیریت دسترسی'}]},
];
A.nonDelegable = ['access_control.manage'];
A.roles = [
  {role: 'finance', label: 'کارشناس مالی', permissions: ['menu.contracts', 'contracts.view']},
  {role: 'planner', label: 'پلنر', permissions: ['menu.dashboard']},
];
A.defaults = {finance: ['menu.contracts', 'contracts.view', 'contracts.manage'],
              planner: ['menu.dashboard']};
A.current = 'finance';
A.saved = api.v8AccessSavedSet('finance');
A.draft = new Set(A.saved);

let fails = 0;
function check(label, actual, expected) {
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  if (a !== e) { fails++; console.log('FAIL ' + label + ': got ' + a + ' want ' + e); }
  else console.log('ok   ' + label + ' -> ' + a);
}
const sorted = s => Array.from(s).sort();

// The locked permission must never appear in the editable universe.
check('all keys exclude non-delegable', api.v8AccessAllKeys().sort(),
      ['contracts.manage', 'contracts.view', 'menu.contracts', 'menu.dashboard',
       'project_notes.manage', 'project_notes.view']);
check('locked detects non-delegable', api.v8AccessLocked('access_control.manage'), true);
check('no changes at load', api.v8AccessChangedKeys(), []);

// Toggling tracks dirty state both ways.
api.v8AccessToggle('contracts.manage', true);
check('toggle on marks changed', api.v8AccessChangedKeys(), ['contracts.manage']);
api.v8AccessToggle('contracts.manage', false);
check('toggling back clears dirty', api.v8AccessChangedKeys(), []);

// A locked key cannot be granted through the toggle path.
api.v8AccessToggle('access_control.manage', true);
check('locked key cannot be toggled', A.draft.has('access_control.manage'), false);

// Sensitive-data pairing stays coherent in both directions.
api.v8AccessToggle('project_notes.manage', true);
check('edit implies view', sorted(A.draft).includes('project_notes.view'), true);
api.v8AccessToggle('project_notes.view', false);
check('removing view removes edit', A.draft.has('project_notes.manage'), false);

// Group bulk actions respect the lock.
api.v8AccessToggleGroup('finance', true);
check('group all grants the group', A.draft.has('contracts.view') && A.draft.has('contracts.manage'), true);
api.v8AccessToggleGroup('finance', false);
check('group none clears the group', A.draft.has('contracts.view') || A.draft.has('contracts.manage'), false);
api.v8AccessToggleGroup('system', true);
check('group all skips locked key', A.draft.has('access_control.manage'), false);

// Select-all / clear-all are confirmed and never include the locked key.
api.v8AccessSelectAll(true);
check('select all equals editable universe', sorted(A.draft), api.v8AccessAllKeys().sort());
check('select all still excludes locked', A.draft.has('access_control.manage'), false);
api.v8AccessSelectAll(false);
check('clear all empties draft', sorted(A.draft), []);

// A declined confirmation must change nothing.
A.draft = new Set(A.saved);
api.setConfirm(false);
api.v8AccessSelectAll(true);
check('declining confirm leaves draft untouched', sorted(A.draft), sorted(A.saved));
api.setConfirm(true);

// Reset to default and copy-from-role.
api.v8AccessResetDefault();
check('reset to default', sorted(A.draft), ['contracts.manage', 'contracts.view', 'menu.contracts']);
check('reset is dirty vs saved', api.v8AccessChangedKeys(), ['contracts.manage']);
api.v8AccessCopyFrom('planner');
check('copy from role', sorted(A.draft), ['menu.dashboard']);

// Revert restores the saved baseline exactly.
api.v8AccessRevert();
check('revert restores saved', sorted(A.draft), sorted(A.saved));
check('revert clears dirty', api.v8AccessChangedKeys(), []);

console.log(fails ? '\n' + fails + ' FAILURE(S)' : '\nall access-matrix assertions passed');
process.exit(fails ? 1 : 0);
