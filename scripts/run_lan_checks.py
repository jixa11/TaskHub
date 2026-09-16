# -*- coding: utf-8 -*-
"""Fast, dependency-light release checks for the TaskHub source."""
from __future__ import annotations

import ast
import json
import os
import pathlib
import py_compile
import shutil
import subprocess
import sys
import tempfile

from cryptography.fernet import Fernet

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
WEB = SRC / "web"
sys.path.insert(0, str(SRC))


def fail(message: str) -> None:
    raise SystemExit("LAN CHECK FAILED: " + message)


for path in sorted(list(SRC.glob("*.py")) + list((ROOT / "scripts").glob("*.py"))):
    try:
        py_compile.compile(str(path), doraise=True)
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except Exception as exc:
        fail(f"Python syntax: {path.name}: {exc}")

# Vazirmatn (SIL OFL) now ships inside this source package, so a clean machine
# can build without hunting for an older release archive. Both faces must be
# present and valid, and the build must bundle both, or the EXE silently falls
# back to Tahoma and every Persian screen looks wrong.
build_text = (ROOT / "build.bat").read_text(encoding="utf-8")
for font_name in ("Vazirmatn-Regular.ttf", "Vazirmatn-Bold.ttf"):
    font_path = WEB / font_name
    if not font_path.exists():
        fail("Bundled font is missing: " + font_name)
    if font_path.stat().st_size < 10000:
        fail("Bundled font is truncated or invalid: " + font_name)
    with font_path.open("rb") as handle:
        if handle.read(4) not in (b"\x00\x01\x00\x00", b"true", b"ttcf", b"OTTO"):
            fail("Bundled font is not a TrueType/OpenType file: " + font_name)
    if ('--add-data "src\\web\\%s;web"' % font_name) not in build_text:
        fail("Windows build does not bundle the font: " + font_name)
if not (WEB / "Vazirmatn-OFL.txt").exists():
    fail("Vazirmatn is redistributed without its SIL OFL license file")

ui_html = (WEB / "ui.html").read_text(encoding="utf-8")
for marker in ("/assets/Vazirmatn-Regular.ttf?v=1.0.0",
               "/assets/Vazirmatn-Bold.ttf?v=1.0.0"):
    if marker not in ui_html:
        fail("UI does not reference the Vazirmatn asset: " + marker)
# A static face declaring a 100-900 range suppresses synthetic bold, which is
# what made every bold heading render at regular weight.
if "font-weight:100 900" in ui_html:
    fail("A static Vazirmatn face must not declare a variable weight range")

cfg = json.loads((ROOT / "config" / "taskhub_config.LAN.example.json").read_text(encoding="utf-8"))
required = {
    "TASKHUB_HOST": "0.0.0.0",
    "TASKHUB_PUBLIC_HOST": "192.168.1.100",
    "TASKHUB_PORT": 19234,
    "TASKHUB_EXTERNAL_SCHEME": "http",
    "TASKHUB_CHAT_MODE": "server",
    "TASKHUB_AUTO_FIREWALL": True,
}
for key, expected in required.items():
    if cfg.get(key) != expected:
        fail(f"LAN config {key} must equal {expected!r}")
if cfg.get("TASKHUB_SSL_CERT_FILE") or cfg.get("TASKHUB_SSL_KEY_FILE"):
    fail("LAN config must not require client certificate setup")
if cfg.get("TASKHUB_DB_PASSWORD") != "CHANGE_ME":
    fail("example config must not contain a production password")

# Regression: stale HTTPS and browser-E2E settings from 8.0.2 must not make
# the R6 LAN release bind to localhost or create per-browser chat keys.
with tempfile.TemporaryDirectory() as temp:
    stale_path = pathlib.Path(temp) / "taskhub_config.json"
    stale_path.write_text(json.dumps({
        "TASKHUB_HOST": "127.0.0.1",
        "TASKHUB_SSL_CERT_FILE": "old-cert.pem",
        "TASKHUB_SSL_KEY_FILE": "old-key.pem",
        "TASKHUB_REVERSE_PROXY": True,
        "TASKHUB_EXTERNAL_SCHEME": "https",
        "TASKHUB_SERVER_ENGINE": "waitress",
        "TASKHUB_CHAT_MODE": "e2e",
    }), encoding="utf-8")
    probe = subprocess.run([
        sys.executable, "-c",
        "import config; print(config.HOST, config.URL_SCHEME, config.SSL_ENABLED, config.REVERSE_PROXY, config.SERVER_ENGINE, config.CHAT_MODE)",
    ], cwd=str(SRC), env={**os.environ, "TASKHUB_CONFIG": str(stale_path)},
       capture_output=True, text=True)
    if probe.returncode != 0:
        fail("stale configuration regression: " + (probe.stderr or probe.stdout).strip())
    if probe.stdout.strip() != "0.0.0.0 http False False waitress server":
        fail("stale LAN configuration was not overridden: " + probe.stdout.strip())

from lan_chat_crypto import ServerChatCrypto

# Functional restart test: ciphertext produced by one process remains readable
# by a new process that receives the same database-backed key, even without the
# compatibility mirror file.
with tempfile.TemporaryDirectory() as temp:
    durable_key = Fernet.generate_key()
    first = ServerChatCrypto(temp, key_provider=lambda: durable_key)
    token = first.encrypt_json({"text": "سلام", "n": 3})
    raw_token = first.encrypt_bytes(b"taskhub-lan-file\x00\xff")
    mirror = pathlib.Path(temp) / "taskhub_data" / "server_chat_fernet.key"
    if mirror.exists():
        mirror.unlink()
    second = ServerChatCrypto(temp, key_provider=lambda: durable_key)
    if second.decrypt_json(token) != {"text": "سلام", "n": 3}:
        fail("server chat JSON restart round-trip")
    if second.decrypt_bytes(raw_token) != b"taskhub-lan-file\x00\xff":
        fail("server chat file restart round-trip")

source = (SRC / "taskhub.py").read_text(encoding="utf-8")
features = (SRC / "v8_features.py").read_text(encoding="utf-8")
ui = (WEB / "v8_ui.js").read_text(encoding="utf-8")
rbac = (SRC / "rbac.py").read_text(encoding="utf-8")
v7_features = (SRC / "v7_features.py").read_text(encoding="utf-8")
for marker in (
    "threading.BoundedSemaphore(DB_MAX_CONCURRENCY)",
    "_acquire_single_instance",
    "_ensure_firewall_rule",
    "@flask_app.before_request",
    "permission_for_request(endpoint, data, user)",
):
    if marker not in source:
        fail("missing server/access hardening: " + marker)
for marker in (
    'CHAT_MODE == "server"',
    "ApplicationSecrets",
    "server_chat_fernet_v1",
    "legacy_key or Fernet.generate_key()",
    "WITH (UPDLOCK,HOLDLOCK)",
    "_LazyServerChat",
    "server_chat.encrypt_json",
    "server_chat.decrypt_json",
):
    if marker not in features:
        fail("missing durable LAN chat integration: " + marker)
for marker in (
    '"manager": set(ALL_PERMISSION_KEYS) - set(NON_DELEGABLE)',
    '"planner": set(ALL_PERMISSION_KEYS) - set(NON_DELEGABLE)',
    "r4_manager_planner_admin_parity_v1",
    "access_control.manage",
):
    if marker not in rbac:
        fail("missing permission matrix marker: " + marker)
for marker in (
    "Visibility is permission-driven",
    "user_has_permission(u, 'tasks.self_manage')",
    "user_has_permission(u, 'tasks.work')",
):
    if marker not in v7_features:
        fail("missing permission-driven task scope marker: " + marker)
for marker in (
    "v8AccessControlPageHtml",
    "v8AccessSave",
    'data-permission="access_control.manage"',
):
    if marker not in ui:
        fail("missing access-control UI: " + marker)
for marker in (
    "function defaultLandingPage()",
    "function canAny(value)",
    'data-permission-any="tasks.create,tasks.self_manage,tasks.create_for_group"',
    "Permission-based task scoping",
    "if(can('tasks.assign'))actionButtons.push",
    "v 1.0.0",
):
    if marker not in ui_html:
        fail("missing permission-driven UI marker: " + marker)

for marker in ("v8ChatServerMode", "plain:{text:text", "V8.chat.polling"):
    if marker not in ui:
        fail("missing LAN chat UI integration: " + marker)

v7_ui = (WEB / "v7_ui.js").read_text(encoding="utf-8")
v7_css = (WEB / "v7_ui.css").read_text(encoding="utf-8")
for marker in (
    "v7FinancialMonthChanged", "v7MonthOptions(selected,true)",
    "function v7PlanChartsHtml", "روند تجمعی تحقق هدف",
    "v71ComparisonChanged", "مقایسه پیشرفت تسک‌ها (شمسی)",
):
    if marker not in v7_ui:
        fail("missing R5 Jalali financial/chart UI: " + marker)
for marker in (
    "comparison_jalali_year", "comparison_jalali_month",
    "_jalali_month_window(comparison_year, comparison_month)",
    "FinancialPlanPeriods WHERE plan_id=? AND month_no=?",
    "s.period_month=?",
):
    if marker not in v7_features:
        fail("missing R5 Jalali financial backend: " + marker)
for marker in ("v7-plan-line-chart", "v71-month-chart"):
    if marker not in v7_css:
        fail("missing R5 chart styles: " + marker)
for marker in (
    "/api/v8/chat/conversation_update", "/api/v8/chat/conversation_delete",
    "Promote another active member first",
):
    if marker not in features:
        fail("missing R5 conversation lifecycle backend: " + marker)
for marker in (
    "v8ChatOpenEdit", "v8ChatDeleteConversation", "ترک گروه",
):
    if marker not in ui:
        fail("missing R5 conversation lifecycle UI: " + marker)
for marker in ("هدف مالی و نمودارهای شمسی", "ماه شمسی قبل"):
    if marker not in ui_html:
        fail("missing R5 help update: " + marker)

# R6 contract/finance/access-control release checks.
for marker in (
    "contracts.relink_project",
    "extensions.edit_any_status",
    "statements.edit_any_status",
):
    if marker not in rbac:
        fail("missing R6 permission: " + marker)
for marker in (
    "r6_legacy_finance_repair_v1",
    "$.ContractStatementPrice",
    "$.ContractStatementVat",
    "IN (3029,3030)",
    "confirm_project_relink",
    "project_relink",
    "UPDATE Tasks SET project_id=?,project_team_id=?",
):
    if marker not in v7_features:
        fail("missing R6 finance/relink backend: " + marker)
for marker in (
    "pendingContractFilter",
    "v7InstallTableSorting",
    "v7FormatMoneyInput",
    "data-money-input",
    "extensions.edit_any_status",
    "statements.edit_any_status",
):
    if marker not in v7_ui:
        fail("missing R6 UI workflow: " + marker)
for marker in (
    'table thead th:not([data-no-sort="1"])',
    "[data-money-input]",
):
    if marker not in v7_css:
        fail("missing R6 sortable/money styles: " + marker)
for marker in (
    "راهنما و آموزش نرم‌افزار",
    "تغییر پروژه قرارداد دارای سابقه",
    "ویرایش الحاقیه یا صورت‌وضعیت در همه وضعیت‌ها",
):
    if marker not in ui_html:
        fail("missing R6 help/training update: " + marker)

# R7 employer approval and financial-progress checks.
for marker in (
    "statements.edit_before_employer_decision",
    "r7_legacy_statement_status_repair_v1",
    "TaxPayerStatusId belongs to the tax workflow",
    "business_status = CASE",
    "financial_progress_percent",
    "confirmed_without_vat = requested_base",
):
    if marker not in (rbac + v7_features):
        fail("missing R7 approval/progress backend: " + marker)
for marker in (
    "تأییدیه کارفرما",
    "تأیید کامل",
    "v7-employer-summary",
    "v7-financial-progress",
    "پس از ثبت تأییدیه کارفرما",
):
    if marker not in (v7_ui + v7_css):
        fail("missing R7 approval/progress UI: " + marker)

# R8 task-report approval-date checks.
for marker in (
    "function taskApprovalJalaliDate(task)",
    "const approvalDate=taskApprovalJalaliDate(t)",
    "if((rfKey||rtoKey)&&!approvalDate)return false",
    "t.report_completed_date = taskApprovalJalaliDate(t)",
    "تاریخ تأیید تسک",
    "t.get('report_completed_date','')",
):
    if marker not in (ui_html + source):
        fail("missing R8 task-report approval-date marker: " + marker)

# R11 profile/phonebook/city/task-contract checks.
for marker in (
    "account.edit_identity", "account.change_password",
    "phonebook.view_all", "phonebook.edit", "tasks.link_contract",
    "r11_account_phonebook_contract_permissions_v1",
):
    if marker not in rbac:
        fail("missing R11 permission marker: " + marker)
for marker in (
    "def api_phonebook", "def api_account_update",
    "مجوز ویرایش نام کاربری یا نام نمایشی",
):
    if marker not in source:
        fail("missing R11 account/phonebook backend: " + marker)
for marker in (
    "Cities are shared master data across the company",
    "def api_v7_task_contract_options",
    "این شهر از قبل وجود دارد و همان رکورد مشترک استفاده شد",
):
    if marker not in v7_features:
        fail("missing R11 city/contract backend: " + marker)
for marker in (
    "v8-sensitive-access-card", "v8-sensitive-view", "v8-sensitive-manage",
):
    if marker not in ui:
        fail("missing R11 access shortcut UI: " + marker)
for marker in (
    "function loadPhonebook", "function openMyAccount",
    "12:'phonebook.view'",
):
    if marker not in ui_html:
        fail("missing R11 profile/phonebook UI: " + marker)
for marker in (
    "v7LoadTaskContractOptions", "v7TaskContractMatchesType",
    "else if(rows.length===1)",
):
    if marker not in v7_ui:
        fail("missing R11 task-contract UI: " + marker)

# R14 group lead and the client messenger rule.
for marker in ('("lead", "سرگروه")', '"tasks.create_for_group"', '"tasks.edit_group"',
               '"tasks.delete_group"', '"tasks.approve_group"',
               '"lead"] = set(_DEFAULTS["support"])'):
    if marker not in rbac:
        fail("missing R14 group-lead permission marker: " + marker)
if "CREATE TABLE LeadMembers(" not in source:
    fail("missing R14 sub-group table")
for marker in ("def client_contact_ids", "def chat_members_error", "CHAT_CLIENT_RULE"):
    if marker not in features:
        fail("missing R14 client messenger rule: " + marker)

# R16 groups with projects, the group report and the reorganised access screen.
team_scope_src = (SRC / "team_scope.py").read_text(encoding="utf-8")
v7_src = (SRC / "v7_features.py").read_text(encoding="utf-8")
for marker in ('"menu.groups"', '"groups.projects_manage"', '"reports.groups"', '"holidays.manage"',
               '"missions.manage"', '"leave.approve"', "GROUP_HINTS",
               "r16_holiday_mission_leave_split_v1", '"system.sql", "system.data_export"'):
    if marker not in rbac:
        fail("missing R16 access marker: " + marker)
for marker in ("CREATE TABLE WorkGroups(", "CREATE TABLE WorkGroupMembers(", "CREATE TABLE WorkGroupProjects(",
               "r16_lead_members_to_groups_v1", "def groups_report", '"/api/v8/group_save"',
               'elif kind == "groups":'):
    if marker not in features:
        fail("missing R16 group backend: " + marker)
if "def group_project_ids" not in team_scope_src or "FROM WorkGroupMembers gm" not in team_scope_src:
    fail("missing R16 group scope helpers")
if "group_project_ids(cur, u['id'])" not in v7_src:
    fail("missing R16 group project check on task save")
for marker in ('id="pg29"', "function v8RenderGroupsReport", 'data-v8-report="groups"', "v8-access-hint"):
    if marker not in ui:
        fail("missing R16 group UI: " + marker)
for marker in ('id="fgroup"', 'id="rgroup"', "function groupFilterOptions", "29:'menu.groups'"):
    if marker not in ui_html:
        fail("missing R16 group filter UI: " + marker)

node = shutil.which("node")
if node:
    for name in ("v7_ui.js", "v8_ui.js", "game_ui.js", "service-worker.js"):
        result = subprocess.run([node, "--check", str(WEB / name)], capture_output=True, text=True)
        if result.returncode:
            fail(f"JavaScript syntax: {name}: {result.stderr.strip()}")
else:
    print("INFO: Node.js not installed; JavaScript parser check skipped.")

print("TaskHub checks passed: Python, config, RBAC, profile, phonebook, shared cities, task-contract filtering, durable chat, build guards and JavaScript.")
