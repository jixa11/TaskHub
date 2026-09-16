"""
TaskHub - Flask + pywebview (native Windows window)
Flask server on localhost handles all DB calls. UI in native WebView2 window.
"""
import sys, os, json, base64, re, threading, traceback, secrets, hashlib, tempfile, time, datetime
import pyodbc
from flask import Flask, request, jsonify, send_file, g as flask_g
from config import (APP_VERSION, WEB_DIR, PORT, HOST, SESSION_HOURS, INITIAL_ADMIN_PASSWORD,
                    SSL_CERT_FILE, SSL_KEY_FILE, SSL_ENABLED, URL_SCHEME, INTERNAL_SCHEME,
                    PUBLIC_HOST, REVERSE_PROXY, SERVER_ENGINE, CHAT_MODE,
                    DB_MAX_CONCURRENCY, AUTO_FIREWALL, connection_string)
import fa_font
from v7_features import init_v7_tables, register_v7_routes
from v8_features import init_v8_tables, register_v8_routes
from v802_features import init_v802_tables, register_v802_routes
from r10_features import init_r10_tables
from gamification import init_gamification_tables, register_game_routes
from team_scope import (has_company_scope, requires_team, default_team_role, lead_group_ids,
                        group_project_ids)
from rbac import (init_rbac_tables, permissions_for_role, user_has_permission,
                  permission_for_request, catalog_payload, default_permissions,
                  ROLES, ALL_PERMISSION_KEYS, NON_DELEGABLE)



# ── Windows "start with Windows" toggle ─────────────────────────────────────
# Uses the per-user HKCU\...\Run registry key, which does NOT require
# Administrator/UAC (unlike HKLM or the Startup folder in some lockdown
# configs). This makes the toggle safe to flip from inside the running app
# itself - no elevation prompt, no separate installer step.
_AUTOSTART_KEY_NAME = 'TaskHub'
def _autostart_supported():
    return sys.platform == 'win32'

def _autostart_get():
    if not _autostart_supported():
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run', 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, _AUTOSTART_KEY_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False

def _autostart_set(enabled):
    if not _autostart_supported():
        return False, 'این قابلیت فقط روی ویندوز در دسترس است'
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run', 0, winreg.KEY_SET_VALUE)
        try:
            if enabled:
                exe_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(sys.argv[0])
                winreg.SetValueEx(key, _AUTOSTART_KEY_NAME, 0, winreg.REG_SZ, '"%s"' % exe_path)
            else:
                try:
                    winreg.DeleteValue(key, _AUTOSTART_KEY_NAME)
                except FileNotFoundError:
                    pass
            return True, None
        finally:
            winreg.CloseKey(key)
    except Exception as e:
        return False, str(e)

# Single source of truth for status labels, used by export_excel, export_pdf,
# export_template (the Excel dropdown), and import_excel. Previously each of
# these kept its own separate copy of this mapping, so adding a new status
# (like 'paused'/'approved'/'rejected') to the app meant remembering to
# update it in four different places - and inevitably some were missed. Now
# there's exactly one dict; everything else derives from it.
STATUS_LABELS = {
    'registered': 'ثبت شده',
    'approved': 'تایید شده',
    'rejected': 'رد شده',
    'assigned': 'منتظر شروع پشتیبان',
    'doing': 'در حال انجام',
    'paused': 'متوقف شده',
    'pending_approval': 'ارسال برای تایید',
    'returned': 'برگشت به ادمین',
    'done': 'پایان',
}
# Statuses with banked/live work time worth showing in reports.
WORK_TIME_STATUSES = ('doing', 'paused', 'pending_approval', 'returned', 'done')
# Subset offered in the Excel bulk-import dropdown: only "stable" states that
# make sense to set directly without going through the actual workflow
# (rejected needs a reason, pending_approval/returned are mid-workflow
# transients with no matching timestamps to set from a spreadsheet row).
IMPORTABLE_STATUSES = ('registered', 'approved', 'assigned', 'doing', 'done')

def get_html_path():
    return os.path.join(WEB_DIR, 'ui.html')

def get_icon_path():
    p = os.path.join(WEB_DIR, 'icon.ico')
    return p if os.path.exists(p) else None

# ── DB ────────────────────────────────────────────────────────────────────────
CONN_STR = connection_string()
# A single global pyodbc connection plus a global Lock serialized every API
# request in 8.0.2. With several browsers polling at once, requests queued
# behind one slow query and eventually timed out. The LAN build gives each
# Waitress worker thread its own connection and only limits the number of
# concurrent DB sections with a bounded semaphore.
_db_local = threading.local()
_db_lock = threading.BoundedSemaphore(DB_MAX_CONCURRENCY)


def get_conn():
    conn = getattr(_db_local, 'conn', None)
    if conn is not None:
        try:
            conn.cursor().execute("SELECT 1")
            return conn
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            _db_local.conn = None
    conn = pyodbc.connect(CONN_STR, timeout=15)
    try:
        conn.timeout = 60
    except Exception:
        pass
    _db_local.conn = conn
    return conn

def _hash_pw(password):
    """Hash a password with PBKDF2 + per-password salt. Returns 'salt$hash'."""
    import hashlib, secrets
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return salt + '$' + dk.hex()

def _verify_pw(password, stored):
    """Verify a password against 'salt$hash'."""
    import hashlib
    try:
        salt, h = stored.split('$', 1)
        dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
        return dk.hex() == h
    except Exception:
        return False

def init_tables():
    c = get_conn()
    cur = c.cursor()
    sqls = [
        "IF NOT EXISTS(SELECT * FROM sysobjects WHERE name='Cities' AND xtype='U') CREATE TABLE Cities(id INT IDENTITY PRIMARY KEY,name NVARCHAR(100) NOT NULL UNIQUE,created_at DATETIME DEFAULT GETDATE())",
        "IF NOT EXISTS(SELECT * FROM sysobjects WHERE name='Projects' AND xtype='U') CREATE TABLE Projects(id INT IDENTITY PRIMARY KEY,city_id INT REFERENCES Cities(id) ON DELETE CASCADE,name NVARCHAR(200) NOT NULL,created_at DATETIME DEFAULT GETDATE())",
        "IF NOT EXISTS(SELECT * FROM sys.columns WHERE object_id=OBJECT_ID('Projects') AND name='notes') ALTER TABLE Projects ADD notes NVARCHAR(MAX) NULL",
        "IF NOT EXISTS(SELECT * FROM sysobjects WHERE name='TaskCategories' AND xtype='U') CREATE TABLE TaskCategories(id INT IDENTITY PRIMARY KEY,name NVARCHAR(200) NOT NULL,description NVARCHAR(500),created_at DATETIME DEFAULT GETDATE())",
        # Users table: single source of truth for admin/employer/support identity.
        # Employers carry a project_id (their assigned project -> resolves to a city).
        # Support/employer can optionally carry phone/position. No more separate Contacts/Staff tables.
        "IF NOT EXISTS(SELECT * FROM sysobjects WHERE name='Users' AND xtype='U') CREATE TABLE Users(id INT IDENTITY PRIMARY KEY,username NVARCHAR(80) NOT NULL UNIQUE,password_hash NVARCHAR(200) NOT NULL,role NVARCHAR(20) NOT NULL,display_name NVARCHAR(200),phone NVARCHAR(30),position NVARCHAR(100),project_id INT NULL REFERENCES Projects(id),is_active BIT DEFAULT 1,created_at DATETIME DEFAULT GETDATE())",
        # Tasks.contact_id = the employer (Users.id) who requested it. Tasks.staff_id = the support (Users.id) assigned to it.
        "IF NOT EXISTS(SELECT * FROM sysobjects WHERE name='Tasks' AND xtype='U') CREATE TABLE Tasks(id INT IDENTITY PRIMARY KEY,title NVARCHAR(300) NOT NULL,type NVARCHAR(20) DEFAULT 'bug',status NVARCHAR(20) DEFAULT 'registered',category_id INT REFERENCES TaskCategories(id) ON DELETE SET NULL,project_id INT REFERENCES Projects(id) ON DELETE NO ACTION,contact_id INT REFERENCES Users(id) ON DELETE NO ACTION,staff_id INT REFERENCES Users(id) ON DELETE NO ACTION,date_recv NVARCHAR(20),date_delivery NVARCHAR(20),description NVARCHAR(MAX),solution NVARCHAR(MAX),priority INT DEFAULT 2,created_by INT NULL,started_at DATETIME NULL,submitted_at DATETIME NULL,completed_at DATETIME NULL,work_seconds INT DEFAULT 0,reject_reason NVARCHAR(MAX) NULL,created_at DATETIME DEFAULT GETDATE())",
        # Safe column additions for upgrades from older versions
        "IF NOT EXISTS(SELECT * FROM sys.columns WHERE object_id=OBJECT_ID('Users') AND name='project_id') ALTER TABLE Users ADD project_id INT NULL REFERENCES Projects(id)",
        "IF NOT EXISTS(SELECT * FROM sys.columns WHERE object_id=OBJECT_ID('Users') AND name='phone') ALTER TABLE Users ADD phone NVARCHAR(30) NULL",
        "IF NOT EXISTS(SELECT * FROM sys.columns WHERE object_id=OBJECT_ID('Users') AND name='phone2') ALTER TABLE Users ADD phone2 NVARCHAR(30) NULL",
        "IF NOT EXISTS(SELECT * FROM sys.columns WHERE object_id=OBJECT_ID('Users') AND name='position') ALTER TABLE Users ADD position NVARCHAR(100) NULL",
        "IF NOT EXISTS(SELECT * FROM sys.columns WHERE object_id=OBJECT_ID('Tasks') AND name='priority') ALTER TABLE Tasks ADD priority INT DEFAULT 2",
        "IF NOT EXISTS(SELECT * FROM sys.columns WHERE object_id=OBJECT_ID('Tasks') AND name='created_by') ALTER TABLE Tasks ADD created_by INT NULL",
        # Time tracking. started_at = last time support pressed Start.
        # work_seconds = accumulated active "doing" time across all start->submit cycles.
        # submitted_at / completed_at = last submit-for-approval / final approval.
        "IF NOT EXISTS(SELECT * FROM sys.columns WHERE object_id=OBJECT_ID('Tasks') AND name='started_at') ALTER TABLE Tasks ADD started_at DATETIME NULL",
        "IF NOT EXISTS(SELECT * FROM sys.columns WHERE object_id=OBJECT_ID('Tasks') AND name='submitted_at') ALTER TABLE Tasks ADD submitted_at DATETIME NULL",
        "IF NOT EXISTS(SELECT * FROM sys.columns WHERE object_id=OBJECT_ID('Tasks') AND name='completed_at') ALTER TABLE Tasks ADD completed_at DATETIME NULL",
        "IF NOT EXISTS(SELECT * FROM sys.columns WHERE object_id=OBJECT_ID('Tasks') AND name='work_seconds') ALTER TABLE Tasks ADD work_seconds INT DEFAULT 0",
        "IF NOT EXISTS(SELECT * FROM sys.columns WHERE object_id=OBJECT_ID('Tasks') AND name='reject_reason') ALTER TABLE Tasks ADD reject_reason NVARCHAR(MAX) NULL",
        # Persistent "remember me" web login tokens.
        "IF NOT EXISTS(SELECT * FROM sysobjects WHERE name='Sessions' AND xtype='U') CREATE TABLE Sessions(token NVARCHAR(64) PRIMARY KEY,user_id INT NOT NULL REFERENCES Users(id) ON DELETE CASCADE,expires_at DATETIME NOT NULL,created_at DATETIME DEFAULT GETDATE())",
        "IF COL_LENGTH('Sessions','last_seen') IS NULL ALTER TABLE Sessions ADD last_seen DATETIME NULL",
        "IF COL_LENGTH('Sessions','ip_address') IS NULL ALTER TABLE Sessions ADD ip_address NVARCHAR(45) NULL",
        "IF COL_LENGTH('Sessions','user_agent') IS NULL ALTER TABLE Sessions ADD user_agent NVARCHAR(300) NULL",
        "UPDATE Sessions SET last_seen=ISNULL(created_at,GETDATE()) WHERE last_seen IS NULL",
        """IF NOT EXISTS(SELECT 1 FROM sys.indexes
             WHERE name='IX_Sessions_user_activity'
               AND object_id=OBJECT_ID('Sessions'))
             CREATE INDEX IX_Sessions_user_activity
               ON Sessions(user_id,last_seen,expires_at)""",
        # Extra helpers on a task, alongside the primary assignee (Tasks.staff_id).
        # Some tasks need more than one pair of hands - this lets support/admin
        # add additional support users without disturbing who the "main" owner is.
        "IF NOT EXISTS(SELECT * FROM sysobjects WHERE name='TaskAssignees' AND xtype='U') CREATE TABLE TaskAssignees(task_id INT NOT NULL REFERENCES Tasks(id) ON DELETE CASCADE,user_id INT NOT NULL REFERENCES Users(id) ON DELETE NO ACTION,assigned_at DATETIME DEFAULT GETDATE(),PRIMARY KEY(task_id,user_id))",
        # R14: a group lead (سرگروه) may raise tasks for the people listed here
        # as their sub-group, and for themselves. A sub-group is not a team.
        # No foreign keys: two references to Users cannot both cascade in SQL
        # Server, so api_user_delete removes these rows explicitly instead.
        "IF OBJECT_ID('LeadMembers','U') IS NULL CREATE TABLE LeadMembers(lead_id INT NOT NULL,member_id INT NOT NULL,created_by INT NULL,created_at DATETIME DEFAULT GETDATE(),CONSTRAINT PK_LeadMembers PRIMARY KEY(lead_id,member_id))",
        "IF NOT EXISTS(SELECT * FROM sys.indexes WHERE name='IX_LeadMembers_member' AND object_id=OBJECT_ID('LeadMembers')) CREATE INDEX IX_LeadMembers_member ON LeadMembers(member_id)",
        # Tracks WHO actually has a task's (shared) clock running right now -
        # the primary assignee (staff_id) and "whoever is currently doing the
        # work" are NOT the same thing once helpers are involved. See the
        # 'start' action handler below for why this matters.
        "IF NOT EXISTS(SELECT * FROM sys.columns WHERE object_id=OBJECT_ID('Tasks') AND name='active_actor_id') ALTER TABLE Tasks ADD active_actor_id INT NULL",
        "IF NOT EXISTS(SELECT * FROM sys.columns WHERE object_id=OBJECT_ID('Tasks') AND name='test_notes') ALTER TABLE Tasks ADD test_notes NVARCHAR(MAX) NULL",
        # Per-person work sessions: every time someone starts a task's clock,
        # a new row opens here (ended_at NULL); when the clock stops for any
        # reason (pause/forward/back_admin/auto-paused by someone else
        # starting elsewhere), that row closes with the elapsed seconds.
        # This is what lets a shared task's time be correctly split between
        # whoever actually worked which portion of it, instead of the whole
        # task's total being attributed equally (and wrongly) to everyone
        # who ever touched it.
        "IF NOT EXISTS(SELECT * FROM sysobjects WHERE name='TaskTimeLog' AND xtype='U') CREATE TABLE TaskTimeLog(id INT IDENTITY PRIMARY KEY,task_id INT NOT NULL REFERENCES Tasks(id) ON DELETE CASCADE,user_id INT NOT NULL,started_at DATETIME NOT NULL,ended_at DATETIME NULL,seconds INT NULL)",
        # Weekly schedule: admin assigns which city (and optionally project) each
        # support/manager user should work on per weekday.
        # day_of_week: 0=شنبه 1=یک‌شنبه 2=دوشنبه 3=سه‌شنبه 4=چهارشنبه
        # sort_order: display order when a day has multiple city assignments.
        "IF NOT EXISTS(SELECT * FROM sysobjects WHERE name='WeeklySchedule' AND xtype='U') CREATE TABLE WeeklySchedule(id INT IDENTITY PRIMARY KEY,staff_id INT NOT NULL REFERENCES Users(id) ON DELETE NO ACTION,day_of_week INT NOT NULL,city_id INT NOT NULL REFERENCES Cities(id) ON DELETE NO ACTION,project_id INT NULL REFERENCES Projects(id) ON DELETE NO ACTION,sort_order INT DEFAULT 0,created_by INT NULL,created_at DATETIME DEFAULT GETDATE())",
        # Official holidays shown on the monthly calendar. jalali_date stored as
        # 'YYYY/MM/DD' text (Jalali) since that's what the calendar UI works in
        # natively - avoids a Gregorian<->Jalali conversion round-trip for a
        # simple lookup table. Admin/planner manage this list from inside the
        # app (no internet dependency for an offline LAN system).
        "IF NOT EXISTS(SELECT * FROM sysobjects WHERE name='Holidays' AND xtype='U') CREATE TABLE Holidays(id INT IDENTITY PRIMARY KEY,jalali_date NVARCHAR(10) NOT NULL UNIQUE,title NVARCHAR(200) NOT NULL,created_by INT NULL,created_at DATETIME DEFAULT GETDATE())",
        # Missions (ماموریت): admin/planner sends a staff member to a city/project
        # for a date range (single or multi-day). Shown on that person's monthly
        # calendar. Doesn't touch attendance/task data directly - purely informational
        # scheduling, same spirit as WeeklySchedule but for exceptional travel.
        "IF NOT EXISTS(SELECT * FROM sysobjects WHERE name='Missions' AND xtype='U') CREATE TABLE Missions(id INT IDENTITY PRIMARY KEY,staff_id INT NOT NULL REFERENCES Users(id) ON DELETE NO ACTION,city_id INT NOT NULL REFERENCES Cities(id) ON DELETE NO ACTION,project_id INT NULL REFERENCES Projects(id) ON DELETE NO ACTION,start_jalali NVARCHAR(10) NOT NULL,end_jalali NVARCHAR(10) NOT NULL,note NVARCHAR(500) NULL,created_by INT NULL,created_at DATETIME DEFAULT GETDATE())",
        # Attendance: one row per person per work-day. check_in is set the moment
        # a trackable-role user logs in (if no open row already exists for today).
        # check_out is set either explicitly (logout) or via the last heartbeat
        # timestamp if the tab/app just disappeared without a clean logout -
        # see the /api/attendance_heartbeat and /api/logout handlers.
        # source records how check_out was determined, for transparency.
        "IF NOT EXISTS(SELECT * FROM sysobjects WHERE name='Attendance' AND xtype='U') CREATE TABLE Attendance(id INT IDENTITY PRIMARY KEY,user_id INT NOT NULL REFERENCES Users(id) ON DELETE NO ACTION,work_date NVARCHAR(10) NOT NULL,check_in DATETIME NOT NULL,check_out DATETIME NULL,last_heartbeat DATETIME NULL,checkout_source NVARCHAR(20) NULL,created_at DATETIME DEFAULT GETDATE())",
        "IF NOT EXISTS(SELECT * FROM sys.indexes WHERE name='IX_Attendance_user_date' AND object_id=OBJECT_ID('Attendance')) CREATE INDEX IX_Attendance_user_date ON Attendance(user_id, work_date)",
        # Leave (مرخصی): either 'hourly' (start_time/end_time, 'HH:MM' text,
        # within leave_date) or 'daily' (the whole work day off - times NULL).
        # Used to subtract from the gross check_in->check_out span when
        # showing "hours worked" on the calendar, so a leave taken mid-day
        # doesn't get silently counted as work time.
        "IF NOT EXISTS(SELECT * FROM sysobjects WHERE name='Leaves' AND xtype='U') CREATE TABLE Leaves(id INT IDENTITY PRIMARY KEY,staff_id INT NOT NULL REFERENCES Users(id) ON DELETE NO ACTION,leave_date NVARCHAR(10) NOT NULL,leave_type NVARCHAR(10) NOT NULL,start_time NVARCHAR(5) NULL,end_time NVARCHAR(5) NULL,reason NVARCHAR(300) NULL,created_by INT NULL,created_at DATETIME DEFAULT GETDATE())",
        "IF NOT EXISTS(SELECT * FROM sys.columns WHERE object_id=OBJECT_ID('Leaves') AND name='status') ALTER TABLE Leaves ADD status NVARCHAR(12) NOT NULL DEFAULT 'approved'",
        "IF NOT EXISTS(SELECT * FROM sys.columns WHERE object_id=OBJECT_ID('Leaves') AND name='reviewed_by') ALTER TABLE Leaves ADD reviewed_by INT NULL",
        "IF NOT EXISTS(SELECT * FROM sys.columns WHERE object_id=OBJECT_ID('Leaves') AND name='reviewed_at') ALTER TABLE Leaves ADD reviewed_at DATETIME NULL",
        "IF NOT EXISTS(SELECT * FROM sys.columns WHERE object_id=OBJECT_ID('Leaves') AND name='review_note') ALTER TABLE Leaves ADD review_note NVARCHAR(300) NULL",
        "IF NOT EXISTS(SELECT * FROM sys.columns WHERE object_id=OBJECT_ID('Leaves') AND name='end_date') ALTER TABLE Leaves ADD end_date NVARCHAR(10) NULL",
        "IF NOT EXISTS(SELECT * FROM sys.indexes WHERE name='IX_Leaves_staff_date' AND object_id=OBJECT_ID('Leaves')) CREATE INDEX IX_Leaves_staff_date ON Leaves(staff_id, leave_date)",
        # ── v6 additions ────────────────────────────────────────────────
        # SLA deadline: optional Jalali due date on a task. When set and past,
        # the task is flagged as overdue in the UI and the overdue dashboard.
        "IF NOT EXISTS(SELECT * FROM sys.columns WHERE object_id=OBJECT_ID('Tasks') AND name='due_jalali') ALTER TABLE Tasks ADD due_jalali NVARCHAR(10) NULL",
        # Audit log: append-only record of who did what and when. Written by
        # _audit() from the sensitive endpoints (login, user/password changes,
        # task transitions, deletions). Makes 'why did X change' answerable.
        "IF NOT EXISTS(SELECT * FROM sysobjects WHERE name='AuditLog' AND xtype='U') CREATE TABLE AuditLog(id INT IDENTITY PRIMARY KEY,user_id INT NULL,username NVARCHAR(100) NULL,action NVARCHAR(60) NOT NULL,detail NVARCHAR(500) NULL,ip NVARCHAR(45) NULL,created_at DATETIME DEFAULT GETDATE())",
        "IF NOT EXISTS(SELECT * FROM sys.indexes WHERE name='IX_AuditLog_created' AND object_id=OBJECT_ID('AuditLog')) CREATE INDEX IX_AuditLog_created ON AuditLog(created_at)",
        # In-app notifications: one row per (recipient, event). is_read flips
        # when the user opens the bell. Kept small via lazy cleanup of old read ones.
        "IF NOT EXISTS(SELECT * FROM sysobjects WHERE name='Notifications' AND xtype='U') CREATE TABLE Notifications(id INT IDENTITY PRIMARY KEY,user_id INT NOT NULL,kind NVARCHAR(30) NOT NULL,title NVARCHAR(200) NOT NULL,link_task_id INT NULL,is_read BIT DEFAULT 0,created_at DATETIME DEFAULT GETDATE())",
        "IF NOT EXISTS(SELECT * FROM sys.indexes WHERE name='IX_Notif_user' AND object_id=OBJECT_ID('Notifications')) CREATE INDEX IX_Notif_user ON Notifications(user_id, is_read)",
        # Task comments: threaded discussion under a task. author_role lets the
        # UI style employer comments differently from staff comments.
        "IF NOT EXISTS(SELECT * FROM sysobjects WHERE name='TaskComments' AND xtype='U') CREATE TABLE TaskComments(id INT IDENTITY PRIMARY KEY,task_id INT NOT NULL REFERENCES Tasks(id) ON DELETE CASCADE,user_id INT NOT NULL,author_name NVARCHAR(120) NULL,author_role NVARCHAR(20) NULL,body NVARCHAR(MAX) NOT NULL,created_at DATETIME DEFAULT GETDATE())",
        "IF NOT EXISTS(SELECT * FROM sys.indexes WHERE name='IX_TaskComments_task' AND object_id=OBJECT_ID('TaskComments')) CREATE INDEX IX_TaskComments_task ON TaskComments(task_id)",
        # Task templates: reusable task presets (title/type/category/description)
        # so common repetitive tasks can be created in one click.
        "IF NOT EXISTS(SELECT * FROM sysobjects WHERE name='TaskTemplates' AND xtype='U') CREATE TABLE TaskTemplates(id INT IDENTITY PRIMARY KEY,name NVARCHAR(150) NOT NULL,title NVARCHAR(300) NULL,type NVARCHAR(20) NULL,category_id INT NULL,description NVARCHAR(MAX) NULL,priority INT NULL,created_by INT NULL,created_at DATETIME DEFAULT GETDATE())",
        # Saved report/kanban filters, per user. filter_json holds the UI state.
        "IF NOT EXISTS(SELECT * FROM sysobjects WHERE name='SavedFilters' AND xtype='U') CREATE TABLE SavedFilters(id INT IDENTITY PRIMARY KEY,user_id INT NOT NULL,name NVARCHAR(120) NOT NULL,scope NVARCHAR(20) NOT NULL,filter_json NVARCHAR(MAX) NOT NULL,created_at DATETIME DEFAULT GETDATE())",
        # Per-task, per-contributor performance score. One row per (task,
        # user) pair - a shared task gets a SEPARATE score for each person
        # who worked on it, not one shared number. score is a plain integer
        # with no enforced ceiling (a task that took a week can get a high
        # score). Only admin/planner/manager can write these.
        "IF NOT EXISTS(SELECT * FROM sysobjects WHERE name='TaskEvaluations' AND xtype='U') CREATE TABLE TaskEvaluations(id INT IDENTITY PRIMARY KEY,task_id INT NOT NULL REFERENCES Tasks(id) ON DELETE CASCADE,user_id INT NOT NULL,score INT NOT NULL,note NVARCHAR(500) NULL,rated_by INT NULL,rated_at DATETIME DEFAULT GETDATE())",
        "IF NOT EXISTS(SELECT * FROM sys.indexes WHERE name='IX_TaskEval_task_user' AND object_id=OBJECT_ID('TaskEvaluations')) CREATE UNIQUE INDEX IX_TaskEval_task_user ON TaskEvaluations(task_id, user_id)",
        "IF NOT EXISTS(SELECT * FROM sys.indexes WHERE name='IX_TaskEval_user' AND object_id=OBJECT_ID('TaskEvaluations')) CREATE INDEX IX_TaskEval_user ON TaskEvaluations(user_id, rated_at)",
    ]
    for s in sqls:
        cur.execute(s)
    c.commit()
    # v7 tables are an additive, idempotent upgrade.  The module receives the
    # already-open connection and never reads or changes the connection string.
    init_v7_tables(c)
    # Seed a starter set of 1405 official holidays (best-effort; admin/planner
    # can add/edit/remove any of these from inside the app - this is NOT a
    # complete or guaranteed-accurate list, especially for lunar-calendar
    # holidays whose exact date needs yearly verification).
    seed_holidays = [
        ('1405/01/01', 'جشن نوروز / عید سعید فطر'),
        ('1405/01/02', 'تعطیل به مناسبت عید سعید فطر'),
        ('1405/01/03', 'عید نوروز'),
        ('1405/01/04', 'عید نوروز'),
        ('1405/01/12', 'روز جمهوری اسلامی ایران'),
        ('1405/01/13', 'روز طبیعت (سیزده‌بدر)'),
        ('1405/03/06', 'عید سعید قربان'),
        ('1405/03/14', 'رحلت امام خمینی (ره) / عید سعید غدیر خم'),
        ('1405/03/15', 'قیام ۱۵ خرداد'),
        ('1405/04/03', 'تاسوعای حسینی'),
        ('1405/04/04', 'عاشورای حسینی'),
        ('1405/05/13', 'اربعین حسینی'),
        ('1405/06/08', 'میلاد رسول اکرم (ص) و امام جعفر صادق (ع)'),
        ('1405/08/22', 'شهادت حضرت فاطمه زهرا (س)'),
        ('1405/10/02', 'ولادت امام علی (ع) - روز پدر'),
        ('1405/10/16', 'مبعث حضرت رسول اکرم (ص)'),
        ('1405/11/04', 'ولادت حضرت قائم (عج) - نیمه شعبان'),
        ('1405/11/22', 'پیروزی انقلاب اسلامی ایران'),
        ('1405/12/09', 'شهادت حضرت علی (ع)'),
        ('1405/12/19', 'عید سعید فطر'),
        ('1405/12/20', 'تعطیل به مناسبت عید سعید فطر'),
        ('1405/12/29', 'روز ملی شدن صنعت نفت ایران'),
    ]
    for jd, title in seed_holidays:
        cur.execute("IF NOT EXISTS(SELECT * FROM Holidays WHERE jalali_date=?) INSERT INTO Holidays(jalali_date,title) VALUES(?,?)", jd, jd, title)
    c.commit()

    # Seed admin user if no users exist. Never use a fixed default password.
    cur.execute("SELECT COUNT(*) FROM Users")
    if cur.fetchone()[0] == 0:
        initial_pw = INITIAL_ADMIN_PASSWORD if len(INITIAL_ADMIN_PASSWORD) >= 10 else secrets.token_urlsafe(14)
        cur.execute(
            "INSERT INTO Users(username,password_hash,role,display_name) VALUES(?,?,?,?)",
            'admin', _hash_pw(initial_pw), 'admin', 'مدیر سیستم')
        c.commit()
        import logging
        try:
            base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
            pw_file = os.path.join(base_dir, 'initial_admin_password.txt')
            with open(pw_file, 'w', encoding='utf-8') as f:
                f.write('username=admin\npassword=' + initial_pw + '\n')
            logging.getLogger('taskhub').info('Initial admin account created; its password is in %s', pw_file)
        except Exception as exc:
            # A fresh database has no other way in, so a lost password file
            # must at least show up in the log instead of vanishing silently.
            logging.getLogger('taskhub').error('Could not write initial_admin_password.txt: %s', exc)

    # v8 is also an additive, idempotent upgrade.  It runs after the initial
    # administrator exists so the default team and encrypted announcement
    # channel can be seeded safely.  The existing connection object is passed
    # in; connection_string() is never read or modified here.
    # RBAC must exist before v8 startup code queries role permissions.
    init_rbac_tables(c)
    init_v8_tables(c)
    init_v802_tables(c)
    init_r10_tables(c)
    # R13 points, coins and item shop. Kept apart on purpose: if its tables
    # cannot be prepared the problem is logged, and login, tasks and finance
    # still start normally.
    try:
        init_gamification_tables(c)
    except Exception as exc:
        try:
            c.rollback()
        except Exception:
            pass
        import logging
        logging.getLogger('taskhub').error('Points and shop tables were not prepared: %s', exc)

def rows_to_list(cur):
    if not cur.description:
        return []
    cols = [c[0] for c in cur.description]
    result = []
    for row in cur.fetchall():
        d = {}
        for i, col in enumerate(cols):
            v = row[i]
            if hasattr(v, 'isoformat'):
                v = v.isoformat()
            d[col] = v
        result.append(d)
    return result

# ── Flask App ─────────────────────────────────────────────────────────────────
flask_app = Flask(__name__)
flask_app.config['JSON_AS_ASCII'] = False
flask_app.config['SESSION_COOKIE_HTTPONLY'] = True
flask_app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
flask_app.config['SESSION_COOKIE_SECURE'] = (URL_SCHEME == 'https')
if REVERSE_PROXY:
    from werkzeug.middleware.proxy_fix import ProxyFix
    # Trust exactly one local reverse proxy (IIS/ARR), never arbitrary client headers.
    flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

@flask_app.after_request
def _security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    if request.is_secure or (REVERSE_PROXY and URL_SCHEME == 'https'):
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Cache-Control'] = response.headers.get('Cache-Control', 'no-store')
    return response

@flask_app.route('/')
def index():
    resp = send_file(get_html_path())
    # This file changes with every new build/version - never let a browser
    # (or WebView2, which caches the same way) serve a stale cached copy
    # after an update. Freshness matters far more than the bandwidth saved.
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@flask_app.route('/assets/<path:filename>')
def app_asset(filename):
    """Serve versioned local UI assets without exposing arbitrary files."""
    if filename not in ('v7_ui.js', 'v7_ui.css', 'v8_ui.js', 'v8_ui.css',
                            'game_ui.js', 'game_ui.css',
                            'taskhub-icon-192.png', 'taskhub-icon-512.png',
                            'Vazirmatn-Regular.ttf', 'Vazirmatn-Bold.ttf'):
        return ('Not found', 404)
    base = os.path.dirname(get_html_path())
    asset_path = os.path.join(base, filename)
    if not os.path.isfile(asset_path):
        return ('Not found', 404)
    resp = send_file(asset_path)
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return resp

@flask_app.route('/manifest.webmanifest')
def app_manifest():
    base = os.path.dirname(get_html_path())
    resp = send_file(os.path.join(base, 'manifest.webmanifest'),
                     mimetype='application/manifest+json')
    resp.headers['Cache-Control'] = 'no-cache, max-age=0'
    return resp

@flask_app.route('/service-worker.js')
def app_service_worker():
    base = os.path.dirname(get_html_path())
    resp = send_file(os.path.join(base, 'service-worker.js'),
                     mimetype='application/javascript')
    # The service worker itself must be revalidated so releases are detected.
    resp.headers['Cache-Control'] = 'no-cache, max-age=0'
    resp.headers['Service-Worker-Allowed'] = '/'
    return resp

@flask_app.route('/api/ping', methods=['GET'])
def api_ping():
    return jsonify({'ok': True})

# Table creation used to run only when a browser reached /api/connect, so a
# server started with --server created nothing until someone opened the page,
# and several clients opening a first run at once could race on the same
# CREATE TABLE. It now also runs at startup, one caller at a time, and the log
# names the exact server, database and schema it wrote to: "it connects but I
# can't see the tables" is almost always a different instance or database
# than the one being inspected.
_init_lock = threading.Lock()
_SYSTEM_DATABASES = ('master', 'model', 'msdb', 'tempdb')


def _system_database_error(db_name):
    """Persian error when the connection landed in a SQL Server system DB.

    An empty TASKHUB_DB_NAME connects to the login's default database, which is
    usually master; creating the application tables there must be refused."""
    if str(db_name or '').strip().lower() in _SYSTEM_DATABASES:
        return ('برنامه به دیتابیس سیستمی «%s» وصل شده است، نه دیتابیس برنامه. '
                'مقدار TASKHUB_DB_NAME در taskhub_config.json خالی یا نادرست است؛ '
                'نام دیتابیس برنامه را وارد و برنامه را دوباره اجرا کنید.') % str(db_name).strip()
    return None


def _initialize_database(log):
    """Connect, report where we landed, then create/upgrade tables. Raises on failure."""
    with _init_lock:
        with _db_lock:
            cur = get_conn().cursor()
            cur.execute("SELECT @@SERVERNAME, DB_NAME(), SUSER_SNAME(), SCHEMA_NAME()")
            server, database, login, schema = cur.fetchone()
            log.info('DB connected OK: server=%s database=%s login=%s default_schema=%s',
                     server, database, login, schema)
            problem = _system_database_error(database)
            if problem:
                raise RuntimeError(problem)
            if schema and schema.lower() != 'dbo':
                log.warning('The default schema of %s is %s, so new tables are created as '
                            '%s.<name>, not dbo.<name>.', login, schema, schema)
            init_tables()
            cur = get_conn().cursor()
            cur.execute("SELECT COUNT(*) FROM sys.tables WHERE is_ms_shipped=0")
            log.info('Tables initialized OK: %s user tables in [%s] on %s',
                     cur.fetchone()[0], database, server)


@flask_app.route('/api/connect', methods=['POST'])
def api_connect():
    import logging; log = logging.getLogger('taskhub')
    try:
        log.info('Connecting to configured database...')
        _initialize_database(log)
        return jsonify({'ok': True})
    except Exception as e:
        log.error(f'DB connect failed: {e}')
        return jsonify({'ok': False, 'error': str(e)})

def _build_user_dict(row):
    """row: id,username,role,display_name,project_id,phone,position (in that order)."""
    user = {
        'id': row[0], 'username': row[1], 'role': row[2],
        'display_name': row[3], 'project_id': row[4],
        'phone': row[5], 'position': row[6],
    }
    try:
        with _db_lock:
            cur = get_conn().cursor()
            user['permissions'] = permissions_for_role(cur, row[2])
    except Exception:
        user['permissions'] = []
    with _db_lock:
        cur = get_conn().cursor()
        cur.execute("""SELECT TOP 1 tm.team_id,t.name,tm.team_role
            FROM TeamMembers tm JOIN Teams t ON t.id=tm.team_id
            WHERE tm.user_id=? AND tm.is_active=1 AND t.is_active=1
            ORDER BY tm.is_primary DESC,tm.team_id""", row[0])
        team = cur.fetchone()
        if team:
            user['team_id'], user['team_name'], user['team_role'] = team[0], team[1], team[2]
    user['company_scope'] = has_company_scope(user)
    # R16: groups hold support staff and leads only. A lead acts for the members
    # of the group they lead, and everybody in a group with projects sees only
    # those projects (the server enforces the same; this only shapes the lists).
    user['group_project_ids'] = []
    if row[2] in ('support', 'lead'):
        try:
            with _db_lock:
                cur = get_conn().cursor()
                if row[2] == 'lead':
                    user['group_member_ids'] = sorted(lead_group_ids(cur, row[0]) - {int(row[0])})
                user['group_project_ids'] = sorted(group_project_ids(cur, row[0]))
        except Exception:
            if row[2] == 'lead':
                user['group_member_ids'] = []
    if row[2] == 'employer' and row[4]:
        with _db_lock:
            cur = get_conn().cursor()
            cur.execute("SELECT city_id FROM Projects WHERE id=?", row[4])
            pr = cur.fetchone()
            if pr:
                user['city_id'] = pr[0]
    return user

def _create_session(user_id):
    token = secrets.token_hex(32)
    with _db_lock:
        c = get_conn(); cur = c.cursor()
        # Remove expired and abandoned sessions.  A live browser updates
        # last_seen on authenticated requests, so two legitimate devices stay
        # visible while zombie tabs disappear after two hours of inactivity.
        cur.execute("DELETE FROM Sessions WHERE expires_at < GETDATE() OR (last_seen IS NOT NULL AND last_seen < DATEADD(hour,-2,GETDATE()))")
        cur.execute("""INSERT INTO Sessions(token,user_id,expires_at,last_seen,ip_address,user_agent)
            VALUES(?,?,DATEADD(hour,?,GETDATE()),GETDATE(),?,?)""",
            token, user_id, SESSION_HOURS,
            (request.headers.get('X-Forwarded-For') or request.remote_addr or '')[:45],
            (request.headers.get('User-Agent') or '')[:300])
        c.commit()
    return token

def _token_from_request():
    """Pull the session token from header (preferred) or JSON body."""
    tok = request.headers.get('X-Token')
    if tok:
        return tok
    try:
        return (request.get_json(silent=True) or {}).get('token') or ''
    except Exception:
        return ''

def _user_from_token(token):
    """Resolve a session token to a live, active user row (or None).
    Returns a dict with id/username/role/display_name/etc. This is the
    single source of truth for 'who is calling' - endpoints must trust this
    over any role/id the client puts in the request body, which can be forged."""
    if not token:
        return None
    try:
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            cur.execute("""SELECT u.id,u.username,u.role,u.display_name,u.project_id,u.phone,u.position,u.is_active,s.expires_at
                FROM Sessions s JOIN Users u ON u.id=s.user_id WHERE s.token=?""", token)
            row = cur.fetchone()
            if not row or not row[7]:
                return None
            if row[8] < datetime.datetime.now():
                return None
            # Heartbeat without turning every API call into a write.
            cur.execute("UPDATE Sessions SET last_seen=GETDATE() WHERE token=? AND (last_seen IS NULL OR last_seen<DATEADD(minute,-1,GETDATE()))", token)
            if cur.rowcount:
                c.commit()
        user = {'id': row[0], 'username': row[1], 'role': row[2], 'display_name': row[3],
                'project_id': row[4], 'phone': row[5], 'position': row[6]}
        with _db_lock:
            cur = get_conn().cursor()
            user['permissions'] = permissions_for_role(cur, row[2])
            cur.execute("""SELECT TOP 1 tm.team_id,t.name,tm.team_role
                FROM TeamMembers tm JOIN Teams t ON t.id=tm.team_id
                WHERE tm.user_id=? AND tm.is_active=1 AND t.is_active=1
                ORDER BY tm.is_primary DESC,tm.team_id""", row[0])
            team = cur.fetchone()
            if team:
                user['team_id'], user['team_name'], user['team_role'] = team[0], team[1], team[2]
        user['company_scope'] = has_company_scope(user)
        return user
    except Exception:
        return None

def _current_user():
    """The authenticated user for THIS request, resolved from the token.
    Cached on flask.g so multiple checks in one request (e.g. require_auth
    plus _effective_actor) don't each run a DB lookup."""
    try:
        if getattr(flask_g, '_cached_user_set', False):
            return flask_g._cached_user
    except Exception:
        pass
    u = _user_from_token(_token_from_request())
    try:
        flask_g._cached_user = u
        flask_g._cached_user_set = True
    except Exception:
        pass
    return u

def _audit(action, detail=None, user=None):
    """Append-only audit trail. Never raises - a logging failure must not
    break the operation being logged."""
    try:
        u = user if user is not None else _current_user()
        uid = u['id'] if u else None
        uname = u['username'] if u else None
        ip = request.headers.get('X-Forwarded-For') or request.remote_addr or None
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            cur.execute("INSERT INTO AuditLog(user_id,username,action,detail,ip) VALUES(?,?,?,?,?)",
                        uid, uname, action, (detail or '')[:500], ip)
            c.commit()
    except Exception:
        pass

def _notify(user_id, kind, title, link_task_id=None):
    """Create an in-app notification for a user. Best-effort."""
    try:
        if not user_id:
            return
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            cur.execute("INSERT INTO Notifications(user_id,kind,title,link_task_id) VALUES(?,?,?,?)",
                        user_id, kind, title[:200], link_task_id)
            cur.execute("""DELETE FROM Notifications WHERE user_id=? AND is_read=1
                AND id NOT IN (SELECT TOP 50 id FROM Notifications WHERE user_id=? AND is_read=1 ORDER BY id DESC)""",
                user_id, user_id)
            c.commit()
    except Exception:
        pass

import functools

def require_auth(fn):
    """Endpoint guard: rejects the request unless it carries a valid session
    token. Stashes the authenticated user on flask.g for the handler to use.
    Role/permission checks inside handlers must read g.user.role - NOT any
    role the client sent in the body."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        u = _current_user()
        if not u:
            return jsonify({'ok': False, 'error': 'نیاز به ورود مجدد', 'auth': False}), 401
        flask_g.user = u
        return fn(*args, **kwargs)
    return wrapper

def require_roles(*roles):
    """Authentication plus database-backed permission enforcement.

    Routes mapped in rbac.permission_for_request use the configured permission
    instead of a hard-coded role list. Unmapped legacy routes retain the old
    role guard until they receive an explicit permission key.
    """
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            u = _current_user()
            if not u:
                return jsonify({'ok': False, 'error': 'نیاز به ورود مجدد', 'auth': False}), 401
            data = request.get_json(silent=True) or {}
            permission = permission_for_request(fn.__name__, data, u)
            allowed = user_has_permission(u, permission) if permission else u['role'] in roles
            if not allowed:
                _audit('denied', '%s tried %s (%s)' % (u['username'], fn.__name__, permission or 'role'), user=u)
                return jsonify({'ok': False, 'error': 'شما دسترسی لازم برای این عملیات را ندارید'}), 403
            flask_g.user = u
            return fn(*args, **kwargs)
        return wrapper
    return deco


@flask_app.before_request
def _enforce_configured_permission():
    """Protect require_auth routes that have a permission mapping.

    This runs before the handler, so hiding a button in the browser is never
    the security boundary. API calls made manually are checked as well.
    """
    endpoint = request.endpoint or ''
    data = request.get_json(silent=True) or {} if request.method in ('POST','PUT','PATCH','DELETE') else {}
    user = _current_user()
    permission = permission_for_request(endpoint, data, user)
    if not permission:
        return None
    if not user:
        return jsonify({'ok': False, 'error': 'نیاز به ورود مجدد', 'auth': False}), 401
    if not user_has_permission(user, permission):
        _audit('denied', '%s tried %s (%s)' % (user['username'], endpoint, permission), user=user)
        return jsonify({'ok': False, 'error': 'شما دسترسی لازم برای این عملیات را ندارید'}), 403
    flask_g.user = user
    return None

def _effective_actor(d):
    """Return (actor_id, actor_role) for an endpoint, derived ONLY from the
    session token. A client can no longer escalate by sending a fake
    actor_role in the body: without a valid token this returns (None, None),
    which every caller treats as 'no access'. The frontend always sends a
    token once logged in, so legitimate flows are unaffected."""
    u = _current_user()
    if u:
        return u['id'], u['role']
    return None, None


def _team_user_access(cur, actor, target_user_id, manage=False):
    """Return whether actor and target are inside the same authorized scope."""
    if not actor or not target_user_id:
        return False
    if int(actor['id']) == int(target_user_id):
        return True
    if has_company_scope(actor):
        return True
    cur.execute("""SELECT TOP 1 1 FROM TeamMembers mine JOIN TeamMembers target
        ON target.team_id=mine.team_id AND target.is_active=1
        WHERE mine.user_id=? AND target.user_id=? AND mine.is_active=1""",
                actor['id'], target_user_id)
    if cur.fetchone() is not None:
        return True
    # An account that belongs to no active team at all is nobody's teammate, so
    # the rule above locked it away from every team lead - and assigning it a
    # team was exactly what they were trying to do. A user who may manage a
    # team can therefore also reach an unassigned account.
    if manage and user_has_permission(actor, 'teams.members_manage'):
        cur.execute("""SELECT TOP 1 1 FROM Users u
            WHERE u.id=? AND NOT EXISTS(SELECT 1 FROM TeamMembers tm
                WHERE tm.user_id=u.id AND tm.is_active=1)""", target_user_id)
        return cur.fetchone() is not None
    return False


def _team_project_access(cur, actor, project_id, manage=False):
    """Team membership is the data boundary; permission is checked separately."""
    if not actor or not project_id:
        return False
    if has_company_scope(actor):
        return True
    cur.execute("""SELECT TOP 1 1 FROM ProjectTeams ptm JOIN TeamMembers tm
        ON tm.team_id=ptm.team_id
        WHERE ptm.project_id=? AND ptm.is_active=1 AND tm.user_id=?
          AND tm.is_active=1""", project_id, actor['id'])
    return cur.fetchone() is not None


def _task_team_scope(user, data, alias='t'):
    """SQL fragment for management/report task endpoints.

    Global roles can select any team. Other roles are always constrained to
    their memberships and an explicit selector may only narrow that set.
    """
    try:
        selected=int((data or {}).get('_team_scope'))
    except (TypeError,ValueError):
        selected=None
    conditions=[]; params=[]
    if not has_company_scope(user):
        conditions.append("""EXISTS(SELECT 1 FROM ProjectTeams scope_pt
            JOIN TeamMembers scope_tm ON scope_tm.team_id=scope_pt.team_id
            WHERE scope_pt.id=%s.project_team_id AND scope_pt.is_active=1
              AND scope_tm.user_id=? AND scope_tm.is_active=1)""" % alias)
        params.append(user['id'])
    if selected:
        conditions.append("""EXISTS(SELECT 1 FROM ProjectTeams chosen_pt
            WHERE chosen_pt.id=%s.project_team_id AND chosen_pt.is_active=1
              AND chosen_pt.team_id=?)""" % alias)
        params.append(selected)
    if not conditions:
        return None,[]
    return " AND ".join(conditions),params


def _team_task_management(cur, user, task_id):
    """Authorize the task's data scope after the operation permission passed."""
    if has_company_scope(user):
        return True
    cur.execute("""SELECT TOP 1 1 FROM Tasks t JOIN ProjectTeams ptm
        ON ptm.id=t.project_team_id JOIN TeamMembers tm
        ON tm.team_id=ptm.team_id
        WHERE t.id=? AND ptm.is_active=1 AND tm.user_id=?
          AND tm.is_active=1""", task_id,user['id'])
    return cur.fetchone() is not None


_login_fails = {}   # ip -> [fail_count, first_fail_ts]
_LOGIN_MAX_FAILS = 8
_LOGIN_WINDOW = 300   # 5 minutes
_LOGIN_LOCKOUT = 300  # lock for 5 minutes after too many fails

def _login_throttled(ip):
    rec = _login_fails.get(ip)
    if not rec:
        return False
    fails, first_ts = rec
    if fails >= _LOGIN_MAX_FAILS and (time.time() - first_ts) < _LOGIN_LOCKOUT:
        return True
    # window elapsed → reset
    if (time.time() - first_ts) > _LOGIN_WINDOW:
        _login_fails.pop(ip, None)
    return False

def _login_note_fail(ip):
    rec = _login_fails.get(ip)
    if not rec or (time.time() - rec[1]) > _LOGIN_WINDOW:
        _login_fails[ip] = [1, time.time()]
    else:
        rec[0] += 1

@flask_app.route('/api/login', methods=['POST'])
def api_login():
    try:
        data = request.get_json()
        username = (data.get('username') or '').strip()
        password = data.get('password') or ''
        _ip = request.headers.get('X-Forwarded-For') or request.remote_addr or 'unknown'
        if _login_throttled(_ip):
            _audit('login_locked', 'تلاش‌های ناموفق متعدد از %s' % _ip, user={'id': None, 'username': username})
            return jsonify({'ok': False, 'error': 'تلاش‌های ناموفق زیاد. لطفاً چند دقیقه صبر کنید.'})
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            cur.execute("SELECT id,username,password_hash,role,display_name,project_id,phone,position,is_active FROM Users WHERE username=?", username)
            row = cur.fetchone()
        if not row:
            _login_note_fail(_ip)
            return jsonify({'ok': False, 'error': 'نام کاربری یا رمز عبور اشتباه است'})
        if not row[8]:
            return jsonify({'ok': False, 'error': 'این حساب غیرفعال شده است'})
        if not _verify_pw(password, row[2]):
            _login_note_fail(_ip)
            return jsonify({'ok': False, 'error': 'نام کاربری یا رمز عبور اشتباه است'})
        _login_fails.pop(_ip, None)  # success clears the counter
        user = _build_user_dict([row[0], row[1], row[3], row[4], row[5], row[6], row[7]])
        token = _create_session(row[0])
        _audit('login', 'ورود موفق', user={'id': row[0], 'username': row[1]})
        # Attendance check-in for trackable roles. Also opportunistically
        # close out any attendance rows left open from a PREVIOUS day (the
        # "closed the browser/shut down the PC without logging out
        # yesterday" case) using their last heartbeat - cheap, request-driven,
        # no background scheduler needed.
        try:
            _close_stale_attendance()
            _attendance_check_in(row[0], row[3])
        except Exception:
            pass  # attendance is best-effort and must never block login
        return jsonify({'ok': True, 'user': user, 'token': token})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@flask_app.route('/api/session', methods=['POST'])
def api_session():
    """Auto-login from a previously-issued token (the 'remember me' on web)."""
    try:
        token = (request.get_json() or {}).get('token') or ''
        if not token:
            return jsonify({'ok': False, 'error': 'no token'})
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            cur.execute("""SELECT u.id,u.username,u.role,u.display_name,u.project_id,u.phone,u.position,u.is_active,s.expires_at
                FROM Sessions s JOIN Users u ON u.id=s.user_id WHERE s.token=?""", token)
            row = cur.fetchone()
            if not row or not row[7]:
                return jsonify({'ok': False, 'error': 'session invalid'})
            if row[8] < datetime.datetime.now():
                cur.execute("DELETE FROM Sessions WHERE token=?", token)
                c.commit()
                return jsonify({'ok': False, 'error': 'session expired'})
            cur.execute("UPDATE Sessions SET last_seen=GETDATE() WHERE token=?", token)
            c.commit()
            # No sliding renewal here on purpose - daily expiry means the
            # token's lifetime was fixed at creation time (see _create_session)
            # and is NOT extended just because the app checked in. The user
            # must log in again once a new day starts.
        user = _build_user_dict([row[0], row[1], row[2], row[3], row[4], row[5], row[6]])
        return jsonify({'ok': True, 'user': user})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@flask_app.route('/api/logout', methods=['POST'])
def api_logout():
    try:
        token = (request.get_json() or {}).get('token') or ''
        if token:
            with _db_lock:
                c = get_conn(); cur = c.cursor()
                # Look up the user before deleting the session, so we can
                # close their attendance with a clean, exact "logout" time -
                # the most reliable checkout path (vs. heartbeat-based guess).
                cur.execute("SELECT user_id FROM Sessions WHERE token=?", token)
                row = cur.fetchone()
                cur.execute("DELETE FROM Sessions WHERE token=?", token)
                c.commit()
            if row:
                try:
                    _attendance_check_out(row[0], source='logout')
                except Exception:
                    pass
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

def _sync_user_primary_team(cur, user_id, role, team_id, actor_id):
    """Set the selected primary team without deleting intentional secondary memberships."""
    if not requires_team(role):
        cur.execute("UPDATE TeamMembers SET is_primary=0 WHERE user_id=? AND is_primary=1", user_id)
        return
    cur.execute("SELECT id FROM Teams WHERE id=? AND is_active=1", team_id)
    if not cur.fetchone():
        raise ValueError('تیم انتخاب‌شده معتبر یا فعال نیست')
    cur.execute("UPDATE TeamMembers SET is_primary=0 WHERE user_id=? AND is_active=1", user_id)
    team_role = default_team_role(role)
    cur.execute("""IF EXISTS(SELECT 1 FROM TeamMembers WHERE team_id=? AND user_id=?)
        UPDATE TeamMembers SET team_role=?,is_primary=1,is_active=1,left_at=NULL,added_by=?
          WHERE team_id=? AND user_id=?
        ELSE INSERT INTO TeamMembers(team_id,user_id,team_role,is_primary,is_active,added_by)
          VALUES(?,?,?,1,1,?)""",
        team_id, user_id, team_role, actor_id, team_id, user_id,
        team_id, user_id, team_role, actor_id)


def _actor_can_select_team(cur, actor, team_id):
    if not team_id:
        return False
    if has_company_scope(actor):
        cur.execute("SELECT 1 FROM Teams WHERE id=? AND is_active=1", team_id)
    else:
        cur.execute("""SELECT 1 FROM TeamMembers tm JOIN Teams t ON t.id=tm.team_id
            WHERE tm.team_id=? AND tm.user_id=? AND tm.is_active=1 AND t.is_active=1""",
                    team_id, actor['id'])
    return cur.fetchone() is not None


@flask_app.route('/api/users', methods=['POST'])
@require_auth
def api_users_list():
    """Team-scoped user directory used by the user-management page."""
    try:
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            base_sql = """SELECT u.id,u.username,u.role,u.display_name,u.phone,u.phone2,u.position,
                u.project_id,u.is_active,p.name AS pname,ct.name AS cname,
                (SELECT TOP 1 wg.name FROM WorkGroups wg WHERE wg.is_active=1 AND (wg.lead_id=u.id
                    OR EXISTS(SELECT 1 FROM WorkGroupMembers gm WHERE gm.group_id=wg.id AND gm.user_id=u.id))
                    ORDER BY wg.id) AS group_name,
                primary_tm.team_id,primary_team.name AS team_name,primary_tm.team_role,
                STUFF((SELECT N'، '+tx.name FROM TeamMembers all_tm JOIN Teams tx
                    ON tx.id=all_tm.team_id WHERE all_tm.user_id=u.id
                    AND all_tm.is_active=1 AND tx.is_active=1 ORDER BY all_tm.is_primary DESC,tx.name
                    FOR XML PATH(''),TYPE).value('.','NVARCHAR(MAX)'),1,2,N'') AS team_names
                FROM Users u
                LEFT JOIN Projects p ON p.id=u.project_id
                LEFT JOIN Cities ct ON ct.id=p.city_id
                OUTER APPLY(SELECT TOP 1 tm.team_id,tm.team_role FROM TeamMembers tm
                    WHERE tm.user_id=u.id AND tm.is_active=1
                    ORDER BY tm.is_primary DESC,tm.team_id) primary_tm
                LEFT JOIN Teams primary_team ON primary_team.id=primary_tm.team_id """
            actor = flask_g.user
            if has_company_scope(actor):
                cur.execute(base_sql + " ORDER BY u.role,u.display_name,u.username")
            else:
                # Shared team membership is the normal rule, but an employer is
                # attached to a project rather than to a team, so a manager or
                # planner could not see the client of their own project - which
                # left the employer field of the task form empty for them.
                cur.execute(base_sql + """ WHERE u.id=? OR EXISTS(
                    SELECT 1 FROM TeamMembers target JOIN TeamMembers mine
                      ON mine.team_id=target.team_id AND mine.is_active=1
                    WHERE target.user_id=u.id AND target.is_active=1 AND mine.user_id=?)
                    OR EXISTS(
                    SELECT 1 FROM ProjectTeams client_pt JOIN TeamMembers mine
                      ON mine.team_id=client_pt.team_id AND mine.is_active=1
                    WHERE client_pt.project_id=u.project_id AND client_pt.is_active=1
                      AND mine.user_id=?)
                    OR (? = 1 AND NOT EXISTS(SELECT 1 FROM TeamMembers any_tm
                      WHERE any_tm.user_id=u.id AND any_tm.is_active=1))
                    ORDER BY u.role,u.display_name,u.username""",
                            actor['id'], actor['id'], actor['id'],
                            # An account with no team belongs to nobody, so it
                            # is shown to whoever may put it in a team -
                            # otherwise it can never be assigned one.
                            1 if user_has_permission(actor, 'teams.members_manage') else 0)
            rows = rows_to_list(cur)
        return jsonify({'ok': True, 'rows': rows, 'company_scope': has_company_scope(flask_g.user)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'rows': []})


@flask_app.route('/api/phonebook', methods=['POST'])
@require_auth
def api_phonebook():
    """Return employer contacts using the dedicated phonebook permissions.

    It used to return employers only, so on a normal installation the page
    showed two people and looked broken. A phone book is for reaching
    colleagues as much as clients, so every active account is listed.

    ``phonebook.view`` opens the page. ``phonebook.view_all`` is the explicit
    exception that allows a role such as support to see the whole company;
    without it the result stays limited to people who share an active team with
    the caller, or who are attached to one of the caller's projects.
    User-management data stays team-scoped separately.
    """
    try:
        actor = flask_g.user
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            sql = """SELECT u.id,u.username,u.role,u.display_name,u.phone,u.phone2,u.position,
                u.project_id,u.is_active,p.name AS pname,ct.name AS cname,
                primary_tm.team_id,primary_team.name AS team_name,primary_tm.team_role,
                STUFF((SELECT N'، '+tx.name FROM TeamMembers all_tm JOIN Teams tx
                    ON tx.id=all_tm.team_id WHERE all_tm.user_id=u.id
                    AND all_tm.is_active=1 AND tx.is_active=1 ORDER BY all_tm.is_primary DESC,tx.name
                    FOR XML PATH(''),TYPE).value('.','NVARCHAR(MAX)'),1,2,N'') AS team_names
                FROM Users u
                LEFT JOIN Projects p ON p.id=u.project_id
                LEFT JOIN Cities ct ON ct.id=p.city_id
                OUTER APPLY(SELECT TOP 1 tm.team_id,tm.team_role FROM TeamMembers tm
                    WHERE tm.user_id=u.id AND tm.is_active=1
                    ORDER BY tm.is_primary DESC,tm.team_id) primary_tm
                LEFT JOIN Teams primary_team ON primary_team.id=primary_tm.team_id
                WHERE u.is_active=1"""
            params = []
            if not user_has_permission(actor, 'phonebook.view_all'):
                sql += """ AND (
                    EXISTS(SELECT 1 FROM TeamMembers target_tm JOIN TeamMembers mine_tm
                        ON mine_tm.team_id=target_tm.team_id AND mine_tm.is_active=1
                        WHERE target_tm.user_id=u.id AND target_tm.is_active=1
                          AND mine_tm.user_id=?)
                    OR EXISTS(SELECT 1 FROM ProjectTeams project_team JOIN TeamMembers mine_tm
                        ON mine_tm.team_id=project_team.team_id AND mine_tm.is_active=1
                        WHERE project_team.project_id=u.project_id AND project_team.is_active=1
                          AND mine_tm.user_id=?))"""
                params.extend([actor['id'], actor['id']])
            sql += " ORDER BY ct.name,p.name,u.display_name,u.username"
            cur.execute(sql, params)
            rows = rows_to_list(cur)
        return jsonify({
            'ok': True,
            'rows': rows,
            'company_scope': user_has_permission(actor, 'phonebook.view_all'),
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'rows': []})


@flask_app.route('/api/user_save', methods=['POST'])
@require_auth
def api_user_save():
    try:
        d = request.get_json() or {}
        uid = d.get('id')
        username = (d.get('username') or '').strip()
        role = d.get('role')
        display_name = (d.get('display_name') or '').strip()
        project_id = d.get('project_id') or None
        team_id = d.get('team_id') or None
        phone = d.get('phone') or None
        phone2 = d.get('phone2') or None
        position = d.get('position') or None
        password = d.get('password') or ''
        allowed_roles = ('admin','manager','planner','finance','reporter','support','lead','supervisor','employer')
        if role not in allowed_roles:
            return jsonify({'ok': False, 'error': 'نقش الزامی است'})
        actor = flask_g.user
        actor_role = actor['role']
        protected_roles = ('manager','planner')
        company_roles = ('admin','finance','reporter')
        can_manage_privileged = user_has_permission(actor, 'users.manage_privileged')
        if role in company_roles and actor_role != 'admin':
            return jsonify({'ok': False, 'error': 'ساخت یا تغییر نقش‌های سراسری فقط برای مدیر سیستم مجاز است'}), 403
        if role in protected_roles and not can_manage_privileged:
            return jsonify({'ok': False, 'error': 'ساخت یا تغییر نقش‌های مدیر و پلنر برای این نقش مجاز نیست'}), 403
        if role == 'employer' and not project_id:
            return jsonify({'ok': False, 'error': 'برای کارفرما انتخاب پروژه الزامی است'})
        if requires_team(role) and not team_id:
            return jsonify({'ok': False, 'error': 'برای این نقش انتخاب تیم الزامی است'})
        needs_login = role in ('admin', 'supervisor', 'reporter', 'manager', 'planner', 'finance', 'lead')
        if needs_login and not username:
            return jsonify({'ok': False, 'error': 'برای این نقش نام کاربری الزامی است'})
        auto_username = username
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            if requires_team(role) and not _actor_can_select_team(cur, actor, team_id):
                return jsonify({'ok': False, 'error': 'به تیم انتخاب‌شده دسترسی ندارید'}), 403
            # A supervisor may be pinned to one project too (R14); the messenger
            # treats that project as the supervisor's company.
            if role == 'employer' or (role == 'supervisor' and project_id):
                cur.execute("""SELECT 1 FROM ProjectTeams WHERE project_id=? AND team_id=?
                    AND is_active=1""", project_id, team_id)
                if not cur.fetchone():
                    message = ('پروژه کارفرما باید به تیم انتخاب‌شده متصل باشد' if role == 'employer'
                               else 'پروژه راهبر باید به تیم انتخاب‌شده متصل باشد')
                    return jsonify({'ok': False, 'error': message}), 403
            if uid:
                cur.execute("SELECT role FROM Users WHERE id=?", uid)
                target = cur.fetchone()
                if not target:
                    return jsonify({'ok': False, 'error': 'کاربر یافت نشد'})
                if not _team_user_access(cur, actor, uid, manage=True):
                    return jsonify({'ok': False, 'error': 'این کاربر خارج از محدوده تیم شماست'}), 403
                if target[0] in company_roles and actor_role != 'admin':
                    return jsonify({'ok': False, 'error': 'ویرایش حساب سراسری فقط برای مدیر سیستم مجاز است'}), 403
                if target[0] in protected_roles and not can_manage_privileged:
                    return jsonify({'ok': False, 'error': 'ویرایش نقش مدیر یا پلنر برای این نقش مجاز نیست'}), 403
                if not auto_username:
                    auto_username = 'user_%d' % int(uid)
                if password:
                    cur.execute("""UPDATE Users SET username=?,role=?,display_name=?,project_id=?,phone=?,phone2=?,
                        position=?,password_hash=? WHERE id=?""",
                        auto_username, role, display_name, project_id, phone, phone2, position,
                        _hash_pw(password), uid)
                else:
                    cur.execute("""UPDATE Users SET username=?,role=?,display_name=?,project_id=?,phone=?,phone2=?,
                        position=? WHERE id=?""",
                        auto_username, role, display_name, project_id, phone, phone2, position, uid)
                saved_id = int(uid)
            else:
                if needs_login and not password:
                    return jsonify({'ok': False, 'error': 'رمز عبور برای این نقش الزامی است'})
                pw_hash = _hash_pw(password) if password else _hash_pw(secrets.token_hex(24))
                if not auto_username:
                    auto_username = 'u_' + secrets.token_hex(5)
                cur.execute("""INSERT INTO Users(username,password_hash,role,display_name,project_id,phone,phone2,
                    position,is_active) OUTPUT INSERTED.id VALUES(?,?,?,?,?,?,?,?,?)""",
                    auto_username, pw_hash, role, display_name, project_id, phone, phone2, position,
                    1 if (password or needs_login) else 0)
                saved_id = int(cur.fetchone()[0])
            _sync_user_primary_team(cur, saved_id, role, team_id, actor['id'])
            # R16: groups are managed on the «گروه‌ها» page. A changed role only
            # releases what the new role cannot hold: leading needs a سرگروه,
            # membership needs support staff or a lead.
            if role != 'lead':
                cur.execute("UPDATE WorkGroups SET lead_id=NULL,updated_at=GETDATE() WHERE lead_id=?", saved_id)
            if role not in ('support', 'lead'):
                cur.execute("DELETE FROM WorkGroupMembers WHERE user_id=?", saved_id)
            c.commit()
        _audit('user_edit' if uid else 'user_create',
               ('ویرایش کاربر #%s%s' % (saved_id, ' (+تغییر رمز)' if password else '')) if uid
               else ('ساخت کاربر %s نقش %s تیم %s' % (auto_username, role, team_id or 'سراسری')))
        return jsonify({'ok': True, 'id': saved_id})
    except Exception as e:
        msg = str(e)
        if 'UNIQUE' in msg or 'duplicate' in msg.lower():
            msg = 'این نام کاربری قبلاً ثبت شده است یا کاربر بیش از یک تیم اصلی دارد'
        return jsonify({'ok': False, 'error': msg})


def _can_manage_target_user(cur, actor, uid):
    cur.execute("SELECT role FROM Users WHERE id=?", uid)
    row = cur.fetchone()
    if not row:
        return False, 'کاربر یافت نشد'
    if not _team_user_access(cur, actor, uid, manage=True):
        return False, 'این کاربر خارج از محدوده تیم شماست'
    if row[0] in ('admin','finance','reporter') and actor.get('role') != 'admin':
        return False, 'تغییر حساب سراسری فقط برای مدیر سیستم مجاز است'
    if row[0] in ('manager','planner') and not user_has_permission(actor, 'users.manage_privileged'):
        return False, 'تغییر نقش مدیر یا پلنر برای این نقش مجاز نیست'
    return True, None

@flask_app.route('/api/user_reset_pw', methods=['POST'])
@require_auth
def api_user_reset_pw():
    try:
        d = request.get_json()
        uid = d.get('id'); newpw = d.get('password') or ''
        if not uid or not newpw:
            return jsonify({'ok': False, 'error': 'اطلاعات ناقص'})
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            allowed, message = _can_manage_target_user(cur, flask_g.user, uid)
            if not allowed:
                return jsonify({'ok': False, 'error': message}), 403
            cur.execute("UPDATE Users SET password_hash=? WHERE id=?", _hash_pw(newpw), uid)
            c.commit()
        _audit('reset_pw', 'بازنشانی رمز کاربر #%s' % uid)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@flask_app.route('/api/account_update', methods=['POST'])
@require_auth
def api_account_update():
    """Self-service account update with separate identity/password grants."""
    try:
        d = request.get_json() or {}
        uid = flask_g.user['id']
        current_password = d.get('current_password') or ''
        new_username = (d.get('username') or '').strip()
        new_display_name = (d.get('display_name') or '').strip()
        new_password = d.get('new_password') or ''
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            cur.execute("SELECT password_hash,username,display_name FROM Users WHERE id=?", uid)
            row = cur.fetchone()
            if not row:
                return jsonify({'ok': False, 'error': 'کاربر یافت نشد'})
            final_username = new_username or row[1]
            final_display_name = new_display_name or row[2]
            identity_changed = final_username != row[1] or final_display_name != row[2]
            password_changed = bool(new_password)
            if identity_changed and not user_has_permission(flask_g.user, 'account.edit_identity'):
                return jsonify({'ok': False, 'error': 'مجوز ویرایش نام کاربری یا نام نمایشی فعال نیست'}), 403
            if password_changed and not user_has_permission(flask_g.user, 'account.change_password'):
                return jsonify({'ok': False, 'error': 'مجوز تغییر رمز عبور فعال نیست'}), 403
            if not identity_changed and not password_changed:
                return jsonify({'ok': True, 'username': row[1], 'display_name': row[2]})
            if not current_password:
                return jsonify({'ok': False, 'error': 'رمز عبور فعلی را وارد کنید'})
            if not _verify_pw(current_password, row[0]):
                return jsonify({'ok': False, 'error': 'رمز عبور فعلی اشتباه است'})
            sets = []; params = []
            if identity_changed:
                sets.extend(["username=?", "display_name=?"])
                params.extend([final_username, final_display_name])
            if password_changed:
                sets.append("password_hash=?")
                params.append(_hash_pw(new_password))
            params.append(uid)
            cur.execute(f"UPDATE Users SET {','.join(sets)} WHERE id=?", *params)
            c.commit()
        _audit('account_update', 'ویرایش حساب شخصی%s%s' % (
            ' و مشخصات' if identity_changed else '', ' و رمز عبور' if password_changed else ''))
        return jsonify({'ok': True, 'username': final_username, 'display_name': final_display_name})
    except Exception as e:
        msg = str(e)
        if 'UNIQUE' in msg or 'duplicate' in msg.lower():
            msg = 'این نام کاربری قبلاً استفاده شده است'
        return jsonify({'ok': False, 'error': msg})

@flask_app.route('/api/autostart', methods=['POST'])
@require_auth
def api_autostart():
    """Get or set the 'launch automatically when Windows starts' setting.
    d.get('set') is None -> just report current state.
    d.get('set') is True/False -> change it."""
    try:
        d = request.get_json() or {}
        if 'set' in d and d['set'] is not None:
            if not user_has_permission(flask_g.user, 'system.autostart'):
                return jsonify({
                    'ok': False,
                    'error': 'برای تغییر اجرای خودکار دسترسی لازم را ندارید'
                }), 403
            ok, err = _autostart_set(bool(d['set']))
            if not ok:
                return jsonify({'ok': False, 'error': err, 'supported': _autostart_supported(), 'enabled': _autostart_get()})
        return jsonify({'ok': True, 'supported': _autostart_supported(), 'enabled': _autostart_get()})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@flask_app.route('/api/user_toggle', methods=['POST'])
@require_auth
def api_user_toggle():
    try:
        d = request.get_json()
        uid = d.get('id')
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            allowed, message = _can_manage_target_user(cur, flask_g.user, uid)
            if not allowed:
                return jsonify({'ok': False, 'error': message}), 403
            cur.execute("UPDATE Users SET is_active = CASE WHEN is_active=1 THEN 0 ELSE 1 END WHERE id=?", uid)
            c.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@flask_app.route('/api/update_phone', methods=['POST'])
@require_auth
def api_update_phone():
    """Update only employer phone fields using phonebook-specific grants."""
    try:
        d = request.get_json() or {}
        uid = d.get('user_id')
        phone = (d.get('phone') or '').strip() or None
        phone2 = (d.get('phone2') or '').strip() or None
        if not uid:
            return jsonify({'ok': False, 'error': 'پارامتر ناقص'})
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            actor = flask_g.user
            cur.execute("SELECT role FROM Users WHERE id=?", uid)
            target = cur.fetchone()
            if not target:
                return jsonify({'ok': False, 'error': 'کاربر یافت نشد'})
            if target[0] != 'employer':
                return jsonify({'ok': False, 'error': 'ویرایش سریع شماره فقط برای مخاطبان دفتر تلفن مجاز است'}), 403
            allowed = user_has_permission(actor, 'phonebook.view_all')
            if not allowed:
                cur.execute("""SELECT 1 FROM Users target WHERE target.id=? AND (
                    EXISTS(SELECT 1 FROM TeamMembers target_tm JOIN TeamMembers mine_tm
                        ON mine_tm.team_id=target_tm.team_id AND mine_tm.is_active=1
                        WHERE target_tm.user_id=target.id AND target_tm.is_active=1
                          AND mine_tm.user_id=?)
                    OR EXISTS(SELECT 1 FROM ProjectTeams project_team JOIN TeamMembers mine_tm
                        ON mine_tm.team_id=project_team.team_id AND mine_tm.is_active=1
                        WHERE project_team.project_id=target.project_id AND project_team.is_active=1
                          AND mine_tm.user_id=?))""", uid, actor['id'], actor['id'])
                allowed = cur.fetchone() is not None
            if not allowed:
                return jsonify({'ok': False, 'error': 'اجازه ویرایش شماره این کاربر را ندارید'}), 403
            cur.execute("UPDATE Users SET phone=?,phone2=? WHERE id=?", phone, phone2, uid)
            c.commit()
        _audit('phone_update', 'ویرایش شماره تماس کاربر #%s' % uid)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@flask_app.route('/api/schedule', methods=['POST'])
@require_auth
def api_schedule():
    """Return weekly schedules according to configured permissions."""
    try:
        d = request.get_json() or {}
        actor = flask_g.user
        staff_id = d.get('staff_id')
        try:
            selected_team = int(d.get('_team_scope'))
        except (TypeError, ValueError):
            selected_team = None
        global_view = has_company_scope(actor)
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            base = """SELECT ws.id,ws.staff_id,ws.day_of_week,ws.city_id,ws.project_id,
                ws.sort_order,ci.name AS city_name,p.name AS project_name,
                u.display_name AS staff_name
                FROM WeeklySchedule ws JOIN Cities ci ON ci.id=ws.city_id
                LEFT JOIN Projects p ON p.id=ws.project_id
                JOIN Users u ON u.id=ws.staff_id"""
            where = []; params = []
            if staff_id:
                allowed = global_view or _team_user_access(cur, actor, staff_id, manage=False)
                if selected_team:
                    cur.execute("SELECT 1 FROM TeamMembers WHERE team_id=? AND user_id=? AND is_active=1",
                                selected_team, staff_id)
                    allowed = allowed and cur.fetchone() is not None
                if not allowed:
                    return jsonify({'ok':False,'error':'به برنامه این همکار دسترسی ندارید'}),403
                where.append('ws.staff_id=?'); params.append(staff_id)
            elif selected_team:
                if not global_view:
                    cur.execute("SELECT 1 FROM TeamMembers WHERE team_id=? AND user_id=? AND is_active=1",
                                selected_team, actor['id'])
                    if not cur.fetchone():
                        return jsonify({'ok':False,'error':'به تیم انتخاب‌شده دسترسی ندارید'}),403
                where.append("EXISTS(SELECT 1 FROM TeamMembers tm WHERE tm.team_id=? AND tm.user_id=ws.staff_id AND tm.is_active=1)")
                params.append(selected_team)
            elif not global_view:
                where.append("(ws.staff_id=? OR EXISTS(SELECT 1 FROM TeamMembers target JOIN TeamMembers mine ON mine.team_id=target.team_id WHERE target.user_id=ws.staff_id AND target.is_active=1 AND mine.user_id=? AND mine.is_active=1))")
                params.extend([actor['id'], actor['id']])
            sql = base + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY u.display_name,ws.day_of_week,ws.sort_order"
            cur.execute(sql, params)
            rows = rows_to_list(cur)
        return jsonify({'ok': True, 'rows': rows})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'rows': []})

@flask_app.route('/api/schedule_save', methods=['POST'])
@require_auth
def api_schedule_save():
    """Replace a user's full weekly schedule when schedule.manage is granted."""
    try:
        d = request.get_json() or {}
        actor = flask_g.user
        if not user_has_permission(actor, 'schedule.manage'):
            return jsonify({'ok': False, 'error': 'مجوز ویرایش برنامه هفتگی را ندارید'}), 403
        staff_id = d.get('staff_id'); entries = d.get('entries') or []
        if not staff_id:
            return jsonify({'ok': False, 'error': 'staff_id الزامی است'})
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            cur.execute("SELECT 1 FROM Users WHERE id=? AND is_active=1", staff_id)
            if not cur.fetchone():
                return jsonify({'ok':False,'error':'کاربر فعال یافت نشد'})
            if not _team_user_access(cur,actor,staff_id,manage=True):
                return jsonify({'ok':False,'error':'این همکار خارج از محدوده تیم شماست'}),403
            for entry in entries:
                project_id=entry.get('project_id')
                if project_id and not _team_project_access(cur, actor, project_id, manage=True):
                    return jsonify({'ok':False,'error':'یکی از پروژه‌های برنامه خارج از محدوده تیم شماست'}),403
                cur.execute("SELECT 1 FROM Cities WHERE id=?",entry.get('city_id'))
                if not cur.fetchone():
                    return jsonify({'ok':False,'error':'یکی از شهرهای برنامه معتبر نیست'})
            cur.execute("DELETE FROM WeeklySchedule WHERE staff_id=?", staff_id)
            for entry in entries:
                cur.execute("""INSERT INTO WeeklySchedule(staff_id,day_of_week,city_id,project_id,sort_order,created_by)
                    VALUES(?,?,?,?,?,?)""", staff_id, entry['day_of_week'], entry['city_id'],
                            entry.get('project_id'), entry.get('sort_order',0), actor['id'])
            c.commit()
        _audit('schedule_save', 'برنامه هفتگی کاربر #%s ذخیره شد' % staff_id)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@flask_app.route('/api/ranking', methods=['POST'])
@require_auth
def api_ranking():
    """Return one of two completely separate staff rankings.

    mode='evaluation': sum of management evaluation scores; date range applies
    to rated_at.
    mode='legacy': actual logged work time on completed tasks, then completed
    task count as the tie-breaker; date range applies to completed_at.
    """
    try:
        d = request.get_json() or {}
        mode = (d.get('mode') or 'evaluation').strip().lower()
        self_only = d.get('scope') == 'self'
        if mode not in ('evaluation', 'legacy'):
            return jsonify({'ok': False, 'error': 'حالت رتبه‌بندی نامعتبر است', 'ranking': []})
        from_date = d.get('from_date')
        to_date = d.get('to_date')
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            actor=flask_g.user
            metric_scope,metric_scope_params=_task_team_scope(actor,d,'t')
            if not metric_scope and actor['role'] in ('support', 'lead'):
                metric_scope="""EXISTS(SELECT 1 FROM ProjectTeams rank_pt
                    JOIN TeamMembers rank_tm ON rank_tm.team_id=rank_pt.team_id
                    WHERE rank_pt.id=t.project_team_id AND rank_pt.is_active=1
                      AND rank_tm.user_id=? AND rank_tm.is_active=1)"""
                metric_scope_params=[actor['id']]
            try:selected_team=int(d.get('_team_scope'))
            except (TypeError,ValueError):selected_team=None
            user_scope="";user_scope_params=[]
            global_ranking = has_company_scope(actor)
            if selected_team:
                user_scope=""" AND EXISTS(SELECT 1 FROM TeamMembers rank_target
                    WHERE rank_target.team_id=? AND rank_target.user_id=u.id
                      AND rank_target.is_active=1)"""
                user_scope_params=[selected_team]
                if not global_ranking:
                    user_scope+=""" AND EXISTS(SELECT 1 FROM TeamMembers rank_mine
                        WHERE rank_mine.team_id=? AND rank_mine.user_id=?
                          AND rank_mine.is_active=1)"""
                    user_scope_params.extend([selected_team,actor['id']])
            elif not global_ranking and actor['role'] in ('manager','planner','support','lead'):
                user_scope=""" AND EXISTS(SELECT 1 FROM TeamMembers rank_target
                    JOIN TeamMembers rank_mine
                      ON rank_mine.team_id=rank_target.team_id
                    WHERE rank_target.user_id=u.id AND rank_target.is_active=1
                      AND rank_mine.user_id=? AND rank_mine.is_active=1)"""
                user_scope_params=[actor['id']]
            elif not global_ranking:
                user_scope=" AND u.id=?";user_scope_params=[actor['id']]
            if mode == 'evaluation':
                period = ''
                period_params=[]
                if from_date and to_date:
                    period = ' AND CAST(te.rated_at AS DATE) BETWEEN ? AND ?'
                    period_params = [from_date, to_date]
                eval_scope=(" AND EXISTS(SELECT 1 FROM Tasks t WHERE t.id=te.task_id AND "+
                            metric_scope+")") if metric_scope else ""
                first_params=period_params+metric_scope_params
                second_period=period.replace('te.','te2.')
                second_scope=eval_scope.replace('te.task_id','te2.task_id')
                query_params=first_params+period_params+metric_scope_params+user_scope_params
                cur.execute("""
                    SELECT u.id, u.display_name, u.username,
                        ISNULL((SELECT SUM(te.score) FROM TaskEvaluations te
                                WHERE te.user_id=u.id""" + period + eval_scope + """), 0) AS total_score,
                        (SELECT COUNT(*) FROM TaskEvaluations te2
                         WHERE te2.user_id=u.id""" + second_period + second_scope + """) AS scored_count
                    FROM Users u
                    WHERE u.role IN ('support','lead','manager') AND u.is_active=1""" + user_scope + """
                    ORDER BY total_score DESC, scored_count DESC, u.display_name
                """, *query_params)
            else:
                task_period = ''
                period_params=[]
                if from_date and to_date:
                    task_period = ' AND CAST(t.completed_at AS DATE) BETWEEN ? AND ?'
                    period_params = [from_date, to_date]
                task_scope=(" AND "+metric_scope) if metric_scope else ""
                query_params=(period_params+metric_scope_params+
                              period_params+metric_scope_params+user_scope_params)
                # Time is always taken from each person's own TaskTimeLog rows.
                # Task count is based on primary responsibility or membership in
                # TaskAssignees, so a completed task with zero logged time is still
                # counted once for that contributor.
                cur.execute("""
                    SELECT u.id, u.display_name, u.username,
                        ISNULL((
                            SELECT SUM(ISNULL(tl.seconds,0))
                            FROM TaskTimeLog tl
                            JOIN Tasks t ON t.id=tl.task_id
                            WHERE tl.user_id=u.id
                              AND tl.ended_at IS NOT NULL
                              AND t.status='done'
                              AND t.completed_at IS NOT NULL""" + task_period + task_scope + """
                        ),0) AS total_seconds,
                        ISNULL((
                            SELECT COUNT(DISTINCT t.id)
                            FROM Tasks t
                            WHERE t.status='done'
                              AND t.completed_at IS NOT NULL
                              AND (t.staff_id=u.id OR EXISTS(
                                  SELECT 1 FROM TaskAssignees ta
                                  WHERE ta.task_id=t.id AND ta.user_id=u.id
                              ))""" + task_period + task_scope + """
                        ),0) AS completed_count
                    FROM Users u
                    WHERE u.role IN ('support','lead','manager') AND u.is_active=1""" + user_scope + """
                    ORDER BY total_seconds DESC, completed_count DESC, u.display_name
                """, *query_params)
            ranking = rows_to_list(cur)
            import datetime as _dt
            wd = _dt.date.today().weekday()
            day_map = {5:0, 6:1, 0:2, 1:3, 2:4}
            today_idx = day_map.get(wd, -1)
            today_sched = []
            if today_idx >= 0:
                cur.execute("""
                    SELECT ws.staff_id, u.display_name as staff_name,
                        ws.city_id, ci.name as city_name,
                        ws.project_id, p.name as project_name, ws.sort_order
                    FROM WeeklySchedule ws
                    JOIN Users u ON u.id=ws.staff_id
                    JOIN Cities ci ON ci.id=ws.city_id
                    LEFT JOIN Projects p ON p.id=ws.project_id
                    WHERE ws.day_of_week=?""" + user_scope + """
                    ORDER BY u.display_name, ws.sort_order
                """, *([today_idx]+user_scope_params))
                today_sched = rows_to_list(cur)
        rank_position = None
        ranking_total = len(ranking)
        if self_only:
            for index, row in enumerate(ranking):
                if str(row.get('id')) == str(flask_g.user.get('id')):
                    rank_position = index + 1
                    ranking = [row]
                    break
            else:
                ranking = []
            # Personal-rank permission must not expose the rest of the team or
            # today's team-wide schedule.
            today_sched = []
        return jsonify({'ok': True, 'mode': mode, 'ranking': ranking,
                        'rank_position': rank_position, 'ranking_total': ranking_total,
                        'today_sched': today_sched, 'today_idx': today_idx})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'ranking': [],
                        'today_sched': [], 'today_idx': -1})

@flask_app.route('/api/holidays', methods=['POST'])
@require_auth
def api_holidays():
    """List all holidays (everyone can read - the monthly calendar is for
    all users). jalali_date stored/returned as 'YYYY/MM/DD' text."""
    try:
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            cur.execute("SELECT id,jalali_date,title FROM Holidays ORDER BY jalali_date")
            rows = rows_to_list(cur)
        return jsonify({'ok': True, 'rows': rows})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'rows': []})

@flask_app.route('/api/holiday_save', methods=['POST'])
@require_auth
def api_holiday_save():
    """Add or update the company-wide holiday calendar."""
    try:
        d = request.get_json() or {}
        if not user_has_permission(flask_g.user, 'holidays.manage'):
            return jsonify({'ok': False, 'error': 'برای ویرایش تقویم سراسری دسترسی لازم را ندارید'}), 403
        jalali_date = (d.get('jalali_date') or '').strip()
        title = (d.get('title') or '').strip()
        if not jalali_date or not title:
            return jsonify({'ok': False, 'error': 'تاریخ و عنوان الزامی است'})
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            cur.execute("SELECT id FROM Holidays WHERE jalali_date=?", jalali_date)
            row = cur.fetchone()
            if row:
                cur.execute("UPDATE Holidays SET title=? WHERE id=?", title, row[0])
            else:
                cur.execute("INSERT INTO Holidays(jalali_date,title,created_by) VALUES(?,?,?)",
                            jalali_date, title, flask_g.user['id'])
            c.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@flask_app.route('/api/holiday_delete', methods=['POST'])
@require_auth
def api_holiday_delete():
    try:
        d = request.get_json() or {}
        if not user_has_permission(flask_g.user, 'holidays.manage'):
            return jsonify({'ok': False, 'error': 'دسترسی حذف تعطیلی را ندارید'}), 403
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            cur.execute("DELETE FROM Holidays WHERE id=?", d.get('id'))
            c.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

# ── Missions (ماموریت) ──────────────────────────────────────────────────────
@flask_app.route('/api/missions', methods=['POST'])
@require_auth
def api_missions():
    """List missions according to leave.view/leave.manage scope."""
    try:
        d = request.get_json() or {}; actor = flask_g.user
        staff_id = d.get('staff_id')
        try: selected_team = int(d.get('_team_scope'))
        except (TypeError, ValueError): selected_team = None
        global_view = has_company_scope(actor)
        with _db_lock:
            c=get_conn(); cur=c.cursor()
            base="""SELECT m.id,m.staff_id,u.display_name AS staff_name,m.city_id,ci.name AS city_name,
                m.project_id,p.name AS project_name,m.start_jalali,m.end_jalali,m.note
                FROM Missions m JOIN Users u ON u.id=m.staff_id JOIN Cities ci ON ci.id=m.city_id
                LEFT JOIN Projects p ON p.id=m.project_id"""
            where=[]; params=[]
            if staff_id:
                if not (global_view or _team_user_access(cur,actor,staff_id,False)):
                    return jsonify({'ok':False,'error':'به ماموریت‌های این همکار دسترسی ندارید'}),403
                where.append('m.staff_id=?'); params.append(staff_id)
            elif selected_team:
                if not global_view:
                    cur.execute("SELECT 1 FROM TeamMembers WHERE team_id=? AND user_id=? AND is_active=1",selected_team,actor['id'])
                    if not cur.fetchone(): return jsonify({'ok':False,'error':'به تیم انتخاب‌شده دسترسی ندارید'}),403
                where.append("EXISTS(SELECT 1 FROM TeamMembers tm WHERE tm.team_id=? AND tm.user_id=m.staff_id AND tm.is_active=1)"); params.append(selected_team)
            elif not global_view:
                where.append("(m.staff_id=? OR EXISTS(SELECT 1 FROM TeamMembers target JOIN TeamMembers mine ON mine.team_id=target.team_id WHERE target.user_id=m.staff_id AND target.is_active=1 AND mine.user_id=? AND mine.is_active=1))")
                params.extend([actor['id'],actor['id']])
            cur.execute(base + (" WHERE "+" AND ".join(where) if where else "") + " ORDER BY m.start_jalali", params)
            rows=rows_to_list(cur)
        return jsonify({'ok':True,'rows':rows})
    except Exception as e:
        return jsonify({'ok':False,'error':str(e),'rows':[]})

@flask_app.route('/api/mission_save', methods=['POST'])
@require_auth
def api_mission_save():
    try:
        d=request.get_json() or {}; actor=flask_g.user
        if not user_has_permission(actor,'missions.manage'):
            return jsonify({'ok':False,'error':'دسترسی غیرمجاز'}),403
        staff_id=d.get('staff_id'); city_id=d.get('city_id')
        start_j=(d.get('start_jalali') or '').strip(); end_j=(d.get('end_jalali') or start_j).strip()
        if not staff_id or not city_id or not start_j:
            return jsonify({'ok':False,'error':'پارامتر ناقص'})
        with _db_lock:
            c=get_conn();cur=c.cursor()
            cur.execute("SELECT 1 FROM Users WHERE id=? AND is_active=1",staff_id)
            if not cur.fetchone(): return jsonify({'ok':False,'error':'کاربر فعال یافت نشد'})
            if not _team_user_access(cur, actor, staff_id, manage=True):
                return jsonify({'ok':False,'error':'این همکار خارج از محدوده تیم شماست'}),403
            project_id=d.get('project_id')
            if project_id and not _team_project_access(cur, actor, project_id, manage=True):
                return jsonify({'ok':False,'error':'این پروژه خارج از محدوده تیم شماست'}),403
            cur.execute("SELECT 1 FROM Cities WHERE id=?", city_id)
            if not cur.fetchone():
                return jsonify({'ok':False,'error':'شهر انتخاب‌شده معتبر نیست'})
            cur.execute("""INSERT INTO Missions(staff_id,city_id,project_id,start_jalali,end_jalali,note,created_by)
                VALUES(?,?,?,?,?,?,?)""",staff_id,city_id,project_id,start_j,end_j,d.get('note'),actor['id'])
            c.commit()
        return jsonify({'ok':True})
    except Exception as e:
        return jsonify({'ok':False,'error':str(e)})

@flask_app.route('/api/mission_delete', methods=['POST'])
@require_auth
def api_mission_delete():
    try:
        d=request.get_json() or {}
        if not user_has_permission(flask_g.user,'missions.manage'):
            return jsonify({'ok':False,'error':'دسترسی غیرمجاز'}),403
        with _db_lock:
            c=get_conn();cur=c.cursor()
            cur.execute("SELECT staff_id,project_id FROM Missions WHERE id=?",d.get('id'))
            row=cur.fetchone()
            if not row:return jsonify({'ok':False,'error':'ماموریت یافت نشد'})
            if not _team_user_access(cur, flask_g.user, row[0], manage=True):
                return jsonify({'ok':False,'error':'این ماموریت خارج از محدوده تیم شماست'}),403
            if row[1] and not _team_project_access(cur, flask_g.user, row[1], manage=True):
                return jsonify({'ok':False,'error':'پروژه ماموریت خارج از محدوده تیم شماست'}),403
            cur.execute("DELETE FROM Missions WHERE id=?",d.get('id'));c.commit()
        return jsonify({'ok':True})
    except Exception as e:
        return jsonify({'ok':False,'error':str(e)})

# ── Attendance (حضور و غیاب) ─────────────────────────────────────────────────
# Only these roles are actual timed employees for HR purposes. employer and
# supervisor are project-side/external users, not staff; admin is the
# untracked "owner" account - the new 'planner' role exists specifically for
# people who do admin-equivalent work but ARE staff and SHOULD be timed.
ATTENDANCE_ROLES = ('support', 'lead', 'manager', 'reporter', 'planner', 'finance')

def _today_jalali_str():
    """Best-effort Jalali YYYY/MM/DD for 'today', computed server-side so
    Attendance.work_date is consistent regardless of client clock/timezone
    quirks. Uses the same Jalali conversion algorithm as the frontend."""
    g = datetime.date.today()
    return _gregorian_to_jalali_str(g.year, g.month, g.day)

def _gregorian_to_jalali_str(gy, gm, gd):
    # Standard Jalali<->Gregorian conversion (no external deps).
    g_days_in_month = [31,28,31,30,31,30,31,31,30,31,30,31]
    j_days_in_month = [31,31,31,31,31,31,30,30,30,30,30,29]
    gy2 = gy - 1600; gm2 = gm - 1; gd2 = gd - 1
    g_day_no = 365*gy2 + (gy2+3)//4 - (gy2+99)//100 + (gy2+399)//400
    for i in range(gm2):
        g_day_no += g_days_in_month[i]
    if gm2 > 1 and ((gy%4==0 and gy%100!=0) or (gy%400==0)):
        g_day_no += 1
    g_day_no += gd2
    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053
    jy = 979 + 33*j_np + 4*(j_day_no//1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        jy += (j_day_no-1)//365
        j_day_no = (j_day_no-1)%365
    for i in range(11):
        if j_day_no < j_days_in_month[i]:
            jm = i+1; jd = j_day_no+1; break
        j_day_no -= j_days_in_month[i]
    else:
        jm = 12; jd = j_day_no+1
    return '%04d/%02d/%02d' % (jy, jm, jd)

def _close_stale_attendance():
    """Close any attendance rows left open from a PREVIOUS day (not today)
    using their last known heartbeat as the check_out time - this is the
    "browser was just closed/PC was shut down" case the heartbeat exists
    specifically to handle. Shared by the opportunistic call in api_login
    and the standalone /api/attendance_close_stale endpoint."""
    today = _today_jalali_str()
    with _db_lock:
        c = get_conn(); cur = c.cursor()
        cur.execute("""UPDATE Attendance
            SET check_out = ISNULL(last_heartbeat, check_in),
                checkout_source = 'auto_stale'
            WHERE check_out IS NULL AND work_date <> ?""", today)
        c.commit()

def _attendance_check_in(user_id, role):
    """Open today's attendance row for this user if not already open. Called
    on every successful login for trackable roles. Idempotent - if a row for
    today already exists (e.g. logged out and back in same day), it's reused
    rather than creating a duplicate."""
    if role not in ATTENDANCE_ROLES:
        return
    today = _today_jalali_str()
    with _db_lock:
        c = get_conn(); cur = c.cursor()
        cur.execute("SELECT id, check_out FROM Attendance WHERE user_id=? AND work_date=?", user_id, today)
        row = cur.fetchone()
        if row and row[1] is None:
            return  # already checked in and still open today
        if row and row[1] is not None:
            return  # already completed a full in/out cycle today - don't reopen
        cur.execute("INSERT INTO Attendance(user_id,work_date,check_in) VALUES(?,?,GETDATE())", user_id, today)
        c.commit()

def _attendance_check_out(user_id, source='logout'):
    """Close today's OPEN attendance row (if any) for this user."""
    today = _today_jalali_str()
    with _db_lock:
        c = get_conn(); cur = c.cursor()
        cur.execute("UPDATE Attendance SET check_out=GETDATE(),checkout_source=? WHERE user_id=? AND work_date=? AND check_out IS NULL",
                    source, user_id, today)
        c.commit()

@flask_app.route('/api/attendance_heartbeat', methods=['POST'])
@require_auth
def api_attendance_heartbeat():
    """Called periodically by the browser tab while the user is present, so
    that if the tab disappears without a clean logout (browser closed,
    system shutdown, crash), the LAST heartbeat timestamp can be used as a
    best-effort check-out time the next time anyone looks. This is
    EXPERIMENTAL, as agreed - if it proves unreliable in practice it can be
    removed in a later version without affecting anything else (it only
    touches its own last_heartbeat column)."""
    try:
        d = request.get_json() or {}
        # Identity from the session token - NOT the body - so nobody can send
        # heartbeats (fake presence) on someone else's behalf.
        user_id, _hb_role = _effective_actor(d)
        if not user_id:
            return jsonify({'ok': False, 'error': 'no user'})
        today = _today_jalali_str()
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            cur.execute("UPDATE Attendance SET last_heartbeat=GETDATE() WHERE user_id=? AND work_date=? AND check_out IS NULL",
                        user_id, today)
            c.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@flask_app.route('/api/attendance_close_stale', methods=['POST'])
@require_auth
def api_attendance_close_stale():
    """Manually-triggerable version of the same opportunistic cleanup that
    already runs automatically on every login - exposed as its own endpoint
    in case it's ever useful to call directly (e.g. from an admin action)."""
    try:
        _close_stale_attendance()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@flask_app.route('/api/attendance', methods=['POST'])
@require_auth
def api_attendance():
    """Attendance rows according to attendance.view/manage permissions."""
    try:
        d=request.get_json() or {}; actor=flask_g.user; user_id=d.get('user_id')
        try: selected_team=int(d.get('_team_scope'))
        except (TypeError,ValueError): selected_team=None
        global_view=has_company_scope(actor)
        with _db_lock:
            c=get_conn();cur=c.cursor(); where=[];params=[]
            if user_id:
                if not (global_view or _team_user_access(cur,actor,user_id,False)):
                    return jsonify({'ok':False,'error':'به حضور و غیاب این همکار دسترسی ندارید'}),403
                where.append('a.user_id=?');params.append(user_id)
            elif selected_team:
                if not global_view:
                    cur.execute("SELECT 1 FROM TeamMembers WHERE team_id=? AND user_id=? AND is_active=1",selected_team,actor['id'])
                    if not cur.fetchone(): return jsonify({'ok':False,'error':'به تیم انتخاب‌شده دسترسی ندارید'}),403
                where.append("EXISTS(SELECT 1 FROM TeamMembers tm WHERE tm.team_id=? AND tm.user_id=a.user_id AND tm.is_active=1)");params.append(selected_team)
            elif not global_view:
                where.append("(a.user_id=? OR EXISTS(SELECT 1 FROM TeamMembers target JOIN TeamMembers mine ON mine.team_id=target.team_id WHERE target.user_id=a.user_id AND target.is_active=1 AND mine.user_id=? AND mine.is_active=1))")
                params.extend([actor['id'],actor['id']])
            cur.execute("SELECT a.user_id,a.work_date,a.check_in,a.check_out FROM Attendance a"+(" WHERE "+" AND ".join(where) if where else "")+" ORDER BY a.work_date",params)
            rows=rows_to_list(cur)
        return jsonify({'ok':True,'rows':rows})
    except Exception as e:
        return jsonify({'ok':False,'error':str(e),'rows':[]})

@flask_app.route('/api/attendance_save', methods=['POST'])
@require_auth
def api_attendance_save():
    """Create or correct attendance when attendance.manage is granted."""
    try:
        d=request.get_json() or {}; actor=flask_g.user
        if not user_has_permission(actor,'attendance.manage'):
            return jsonify({'ok':False,'error':'دسترسی غیرمجاز'}),403
        user_id=d.get('user_id'); work_date=(d.get('work_date') or '').strip()
        check_in_t=(d.get('check_in') or '').strip(); check_out_t=(d.get('check_out') or '').strip()
        if not user_id or not work_date or not check_in_t:
            return jsonify({'ok':False,'error':'کارمند، تاریخ و ساعت ورود الزامی است'})
        jy,jm,jd=map(int,work_date.split('/')); gy,gm,gd=_jalali_to_gregorian(jy,jm,jd)
        ci_h,ci_m=map(int,check_in_t.split(':'))
        import datetime as _dt4
        check_in_dt=_dt4.datetime(gy,gm,gd,ci_h,ci_m); check_out_dt=None
        if check_out_t:
            co_h,co_m=map(int,check_out_t.split(':')); check_out_dt=_dt4.datetime(gy,gm,gd,co_h,co_m)
            if check_out_dt<=check_in_dt: return jsonify({'ok':False,'error':'ساعت خروج باید بعد از ساعت ورود باشد'})
        with _db_lock:
            c=get_conn();cur=c.cursor()
            if not _team_user_access(cur, actor, user_id, manage=True):
                return jsonify({'ok':False,'error':'این همکار خارج از محدوده تیم شماست'}),403
            cur.execute("SELECT id FROM Attendance WHERE user_id=? AND work_date=?",user_id,work_date);row=cur.fetchone()
            if row: cur.execute("UPDATE Attendance SET check_in=?,check_out=?,checkout_source=? WHERE id=?",check_in_dt,check_out_dt,'admin_edit' if check_out_dt else None,row[0])
            else: cur.execute("INSERT INTO Attendance(user_id,work_date,check_in,check_out,checkout_source) VALUES(?,?,?,?,?)",user_id,work_date,check_in_dt,check_out_dt,'admin_edit' if check_out_dt else None)
            c.commit()
        return jsonify({'ok':True})
    except Exception as e:
        return jsonify({'ok':False,'error':str(e)})

def _can_access_project_notes(actor_id, actor_role, project_id, manage=False):
    """Permission + team boundary for VPN/remote/login information."""
    actor = _current_user() or {'id': actor_id, 'role': actor_role}
    permission = 'project_notes.manage' if manage else 'project_notes.view'
    if not user_has_permission(actor, permission):
        return False
    with _db_lock:
        c=get_conn();cur=c.cursor()
        return _team_project_access(cur, actor, project_id, manage=manage)

@flask_app.route('/api/project_notes_get', methods=['POST'])
@require_auth
def api_project_notes_get():
    """Return sensitive project notes only inside the caller's team scope.

    The access-control page grants view/edit independently. Assigning a support
    user to the project team and enabling the two permissions is sufficient.
    """
    try:
        d = request.get_json() or {}
        project_id = d.get('project_id')
        actor_id, actor_role = _effective_actor(d)
        if not _can_access_project_notes(actor_id, actor_role, project_id):
            return jsonify({'ok': False, 'error': 'مجوز اطلاعات حساس یا عضویت تیم این پروژه را ندارید'}), 403
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            cur.execute("SELECT notes FROM Projects WHERE id=?", project_id)
            row = cur.fetchone()
        return jsonify({'ok': True, 'notes': (row[0] if row else None) or ''})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@flask_app.route('/api/project_notes_save', methods=['POST'])
@require_auth
def api_project_notes_save():
    """Update sensitive notes only with project_notes.manage and team scope."""
    try:
        d = request.get_json() or {}
        project_id = d.get('project_id')
        actor_id, actor_role = _effective_actor(d)
        if not _can_access_project_notes(actor_id, actor_role, project_id, manage=True):
            return jsonify({'ok': False, 'error': 'مجوز ویرایش اطلاعات حساس یا عضویت تیم این پروژه را ندارید'}),403
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            cur.execute("UPDATE Projects SET notes=? WHERE id=?", d.get('notes'), project_id)
            c.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

def _can_view_time_report(actor_id, actor_role, staff_id):
    actor = _current_user() or {'id': actor_id, 'role': actor_role}
    if not user_has_permission(actor, 'reports.view'):
        return False
    if has_company_scope(actor):
        return True
    if str(actor_id) == str(staff_id):
        return True
    with _db_lock:
        c=get_conn();cur=c.cursor()
        return _team_user_access(cur,actor,staff_id,manage=False)

def _jalali_month_days(jy, jm):
    if jm <= 6: return 31
    if jm <= 11: return 30
    # Esfand: 29 or 30 depending on leap year. Computed empirically as the
    # real day-gap between Esfand 1 of this year and Farvardin 1 of next
    # year, using the already-verified (0 mismatches across 5 years)
    # continuous day-offset conversion below - this can't drift out of sync
    # with a separate leap-year formula because there isn't one; it just
    # measures the actual distance.
    import datetime as _dt3
    g_esfand1 = _dt3.date(*_jalali_to_gregorian(jy, 12, 1))
    g_next_farvardin1 = _dt3.date(*_jalali_to_gregorian(jy+1, 1, 1))
    return (g_next_farvardin1 - g_esfand1).days

def _expand_jalali_dates(start_j, end_j):
    """Yield every 'YYYY/MM/DD' Jalali date string from start_j to end_j inclusive."""
    if not start_j or not end_j or end_j < start_j:
        return
    y, m, d = map(int, start_j.split('/'))
    ey, em, ed = map(int, end_j.split('/'))
    guard = 0
    while guard < 400:
        guard += 1
        ds = '%04d/%02d/%02d' % (y, m, d)
        yield ds
        if (y, m, d) == (ey, em, ed):
            return
        dim = _jalali_month_days(y, m)
        d += 1
        if d > dim:
            d = 1; m += 1
            if m > 12:
                m = 1; y += 1

def _gather_time_report(staff_id, from_j, to_j):
    with _db_lock:
        c = get_conn(); cur = c.cursor()
        cur.execute("SELECT display_name FROM Users WHERE id=?", staff_id)
        row = cur.fetchone()
        staff_name = row[0] if row else ('کاربر %s' % staff_id)
        cur.execute("""SELECT work_date,check_in,check_out FROM Attendance
            WHERE user_id=? AND work_date BETWEEN ? AND ? ORDER BY work_date""", staff_id, from_j, to_j)
        attendance = rows_to_list(cur)
        cur.execute("""SELECT leave_date,ISNULL(end_date,leave_date) as end_date,leave_type,start_time,end_time,reason,status FROM Leaves
            WHERE staff_id=? AND leave_date<=? AND ISNULL(end_date,leave_date)>=? ORDER BY leave_date""", staff_id, to_j, from_j)
        leaves = rows_to_list(cur)
        cur.execute("""SELECT m.start_jalali,m.end_jalali,ci.name as city_name,p.name as project_name,m.note
            FROM Missions m JOIN Cities ci ON ci.id=m.city_id LEFT JOIN Projects p ON p.id=m.project_id
            WHERE m.staff_id=? AND m.start_jalali<=? AND m.end_jalali>=? ORDER BY m.start_jalali""",
            staff_id, to_j, from_j)
        missions = rows_to_list(cur)
    # Totals
    import datetime as _dt
    total_work_sec = 0
    leave_sec_by_date = {}
    daily_leave_dates = set()
    for lv in leaves:
        if lv['status'] != 'approved':
            continue
        if lv['leave_type'] == 'daily':
            # Expand the whole range, clipped to the report window, so a
            # multi-day leave correctly counts every day it covers - not
            # just its start date.
            clip_start = max(lv['leave_date'], from_j)
            clip_end = min(lv.get('end_date') or lv['leave_date'], to_j)
            for ds in _expand_jalali_dates(clip_start, clip_end):
                daily_leave_dates.add(ds)
        elif lv['leave_type'] == 'hourly' and lv['start_time'] and lv['end_time']:
            sh, sm = map(int, lv['start_time'].split(':'))
            eh, em = map(int, lv['end_time'].split(':'))
            secs = max(0, ((eh*60+em)-(sh*60+sm))*60)
            leave_sec_by_date[lv['leave_date']] = leave_sec_by_date.get(lv['leave_date'], 0) + secs
    for a in attendance:
        if a['work_date'] in daily_leave_dates:
            continue  # whole day is leave - matches the calendar's treatment, don't count any attendance that day
        if a['check_out']:
            ci = a['check_in'] if isinstance(a['check_in'], _dt.datetime) else _dt.datetime.fromisoformat(str(a['check_in']))
            co = a['check_out'] if isinstance(a['check_out'], _dt.datetime) else _dt.datetime.fromisoformat(str(a['check_out']))
            gross = max(0, (co-ci).total_seconds())
            net = max(0, gross - leave_sec_by_date.get(a['work_date'], 0))
            total_work_sec += net
    total_leave_sec = sum(leave_sec_by_date.values())
    daily_leave_count = len(daily_leave_dates)
    mission_days = 0
    for m in missions:
        try:
            sd = max(m['start_jalali'], from_j); ed = min(m['end_jalali'], to_j)
            gy1,gm1,gd1 = _jalali_to_gregorian(int(sd.split('/')[0]),int(sd.split('/')[1]),int(sd.split('/')[2]))
            gy2,gm2,gd2 = _jalali_to_gregorian(int(ed.split('/')[0]),int(ed.split('/')[1]),int(ed.split('/')[2]))
            mission_days += (_dt.date(gy2,gm2,gd2) - _dt.date(gy1,gm1,gd1)).days + 1
        except Exception:
            mission_days += 1
    return {
        'staff_name': staff_name, 'from_jalali': from_j, 'to_jalali': to_j,
        'attendance': attendance, 'leaves': leaves, 'missions': missions,
        'totals': {
            'work_seconds': total_work_sec, 'leave_seconds': total_leave_sec,
            'daily_leave_count': daily_leave_count, 'mission_days': mission_days,
        }
    }

def _jalali_to_gregorian(jy, jm, jd):
    """Standard Jalali -> Gregorian conversion. Inverse of _gregorian_to_jalali_str."""
    import datetime as _dt2
    jy += 1595
    days = -355668 + (365 * jy) + ((jy // 33) * 8) + (((jy % 33) + 3) // 4) + jd
    if jm < 7:
        days += (jm - 1) * 31
    else:
        days += ((jm - 7) * 30) + 186
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    g_days_in_month = [31, 29 if (gy % 4 == 0 and (gy % 100 != 0 or gy % 400 == 0)) else 28,
                        31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gm < 12 and gd > g_days_in_month[gm]:
        gd -= g_days_in_month[gm]
        gm += 1
    return gy, gm + 1, gd

@flask_app.route('/api/time_report', methods=['POST'])
@require_auth
def api_time_report():
    try:
        d = request.get_json() or {}
        staff_id = d.get('staff_id')
        actor_id, actor_role = _effective_actor(d)
        from_j = (d.get('from_jalali') or '').strip()
        to_j = (d.get('to_jalali') or '').strip()
        if not _can_view_time_report(actor_id, actor_role, staff_id):
            return jsonify({'ok': False, 'error': 'دسترسی غیرمجاز'})
        if not staff_id or not from_j or not to_j:
            return jsonify({'ok': False, 'error': 'پارامتر ناقص'})
        data = _gather_time_report(staff_id, from_j, to_j)
        return jsonify({'ok': True, **data})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@flask_app.route('/api/export_time_report', methods=['POST'])
@require_auth
def api_export_time_report():
    try:
        d = request.get_json() or {}
        staff_id = d.get('staff_id')
        actor_id, actor_role = _effective_actor(d)
        from_j = (d.get('from_jalali') or '').strip()
        to_j = (d.get('to_jalali') or '').strip()
        etype = d.get('etype', 'excel')
        if not _can_view_time_report(actor_id, actor_role, staff_id):
            return jsonify({'ok': False, 'error': 'دسترسی غیرمجاز'})
        data = _gather_time_report(staff_id, from_j, to_j)
        ext = '.xlsx' if etype == 'excel' else '.pdf'
        tmp_dir = tempfile.gettempdir()
        path = os.path.join(tmp_dir, f'taskhub_timereport_{os.getpid()}_{int(time.time())}{ext}')
        if etype == 'excel':
            export_time_report_excel(data, path)
        else:
            export_time_report_pdf(data, path)
        return send_file(path, as_attachment=True, download_name='TaskHubTimeReport' + ext)
    except Exception as e:
        return jsonify({'ok': False, 'error': traceback.format_exc()})

@flask_app.route('/api/leaves', methods=['POST'])
@require_auth
def api_leaves():
    """List leave records according to leave.view/manage permissions."""
    try:
        d=request.get_json() or {};actor=flask_g.user;staff_id=d.get('staff_id')
        try:selected_team=int(d.get('_team_scope'))
        except (TypeError,ValueError):selected_team=None
        global_view=has_company_scope(actor)
        with _db_lock:
            c=get_conn();cur=c.cursor()
            base="""SELECT l.id,l.staff_id,u.display_name AS staff_name,l.leave_date,l.end_date,l.leave_type,
                l.start_time,l.end_time,l.reason,l.status,l.review_note,l.created_at,l.reviewed_at
                FROM Leaves l JOIN Users u ON u.id=l.staff_id"""
            where=[];params=[]
            if staff_id:
                if not (global_view or _team_user_access(cur,actor,staff_id,False)):
                    return jsonify({'ok':False,'error':'به مرخصی‌های این همکار دسترسی ندارید'}),403
                where.append('l.staff_id=?');params.append(staff_id)
            elif selected_team:
                if not global_view:
                    cur.execute("SELECT 1 FROM TeamMembers WHERE team_id=? AND user_id=? AND is_active=1",selected_team,actor['id'])
                    if not cur.fetchone():return jsonify({'ok':False,'error':'به تیم انتخاب‌شده دسترسی ندارید'}),403
                where.append("EXISTS(SELECT 1 FROM TeamMembers tm WHERE tm.team_id=? AND tm.user_id=l.staff_id AND tm.is_active=1)");params.append(selected_team)
            elif not global_view:
                where.append("(l.staff_id=? OR EXISTS(SELECT 1 FROM TeamMembers target JOIN TeamMembers mine ON mine.team_id=target.team_id WHERE target.user_id=l.staff_id AND target.is_active=1 AND mine.user_id=? AND mine.is_active=1))")
                params.extend([actor['id'],actor['id']])
            cur.execute(base+(" WHERE "+" AND ".join(where) if where else "")+" ORDER BY l.leave_date DESC,l.id DESC",params)
            rows=rows_to_list(cur)
        return jsonify({'ok':True,'rows':rows})
    except Exception as e:
        return jsonify({'ok':False,'error':str(e),'rows':[]})

@flask_app.route('/api/leave_save', methods=['POST'])
@require_auth
def api_leave_save():
    """Create an approved leave with leave.manage or an own pending request with leave.request."""
    try:
        d=request.get_json() or {};actor=flask_g.user;actor_id=actor['id'];staff_id=d.get('staff_id') or actor_id
        can_manage=user_has_permission(actor,'leave.manage');can_request=user_has_permission(actor,'leave.request')
        if not can_manage and not (can_request and str(staff_id)==str(actor_id)):
            return jsonify({'ok':False,'error':'دسترسی غیرمجاز'}),403
        leave_date=(d.get('leave_date') or '').strip();end_date=(d.get('end_date') or '').strip() or leave_date;leave_type=d.get('leave_type')
        if leave_type not in ('hourly','daily') or not leave_date:return jsonify({'ok':False,'error':'پارامتر ناقص'})
        start_time=d.get('start_time') if leave_type=='hourly' else None;end_time=d.get('end_time') if leave_type=='hourly' else None
        if leave_type=='hourly':
            end_date=leave_date
            if not start_time or not end_time:return jsonify({'ok':False,'error':'برای مرخصی ساعتی، ساعت شروع و پایان الزامی است'})
        elif end_date<leave_date:return jsonify({'ok':False,'error':'تاریخ پایان نمی‌تواند قبل از تاریخ شروع باشد'})
        status='approved' if can_manage else 'pending'
        with _db_lock:
            c=get_conn();cur=c.cursor()
            if can_manage and not _team_user_access(cur, actor, staff_id, manage=True):
                return jsonify({'ok':False,'error':'این همکار خارج از محدوده تیم شماست'}),403
            if can_manage:
                cur.execute("""INSERT INTO Leaves(staff_id,leave_date,end_date,leave_type,start_time,end_time,reason,created_by,status,reviewed_by,reviewed_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,GETDATE())""",staff_id,leave_date,end_date,leave_type,start_time,end_time,d.get('reason'),actor_id,status,actor_id)
            else:
                cur.execute("""INSERT INTO Leaves(staff_id,leave_date,end_date,leave_type,start_time,end_time,reason,created_by,status)
                    VALUES(?,?,?,?,?,?,?,?,?)""",staff_id,leave_date,end_date,leave_type,start_time,end_time,d.get('reason'),actor_id,status)
            c.commit()
        if not can_manage:
            try:
                with _db_lock:
                    c2=get_conn();cur2=c2.cursor()
                    cur2.execute("""SELECT DISTINCT u.id FROM Users u WHERE u.is_active=1 AND
                        (u.role=N'admin' OR EXISTS(SELECT 1 FROM RolePermissions rp WHERE rp.role=u.role AND rp.permission_key=N'leave.approve' AND rp.is_allowed=1))""")
                    approvers=[r[0] for r in cur2.fetchall()]
                for uid in approvers:_notify(uid,'leave_request','درخواست مرخصی جدید (%s)'%leave_date)
            except Exception:pass
        return jsonify({'ok':True,'status':status})
    except Exception as e:
        return jsonify({'ok':False,'error':str(e)})

_REWARD_LEAVE_MSG = 'این مرخصی تشویقی است؛ روز آن را از «امتیاز و فروشگاه» ← «خریدهای من» تغییر دهید یا خرید را لغو کنید تا سکه برگردد'

def _is_reward_leave(cur, leave_id):
    """True for a leave bought in the R13 shop. Changing it here would leave
    the purchase and its coins out of step, so it is managed from the shop.
    Returns False if the column does not exist yet (an older database)."""
    try:
        cur.execute("SELECT 1 FROM Leaves WHERE id=? AND is_reward=1", leave_id)
        return cur.fetchone() is not None
    except Exception:
        return False

@flask_app.route('/api/leave_update', methods=['POST'])
@require_auth
def api_leave_update():
    try:
        d=request.get_json() or {};actor=flask_g.user;lid=d.get('id')
        if not lid:return jsonify({'ok':False,'error':'شناسه مرخصی الزامی است'})
        with _db_lock:
            c=get_conn();cur=c.cursor();cur.execute("SELECT staff_id,status FROM Leaves WHERE id=?",lid);row=cur.fetchone()
            if not row:return jsonify({'ok':False,'error':'یافت نشد'})
            if _is_reward_leave(cur,lid):return jsonify({'ok':False,'error':_REWARD_LEAVE_MSG})
            owner_id,current_status=row
            can_manage=user_has_permission(actor,'leave.manage')
            can_own=user_has_permission(actor,'leave.request') and str(owner_id)==str(actor['id']) and current_status=='pending'
            if can_manage and not _team_user_access(cur, actor, owner_id, manage=True):can_manage=False
            if not (can_manage or can_own):return jsonify({'ok':False,'error':'دسترسی غیرمجاز یا خارج از محدوده تیم'}),403
            leave_date=(d.get('leave_date') or '').strip();leave_type=d.get('leave_type');end_date=(d.get('end_date') or '').strip() or leave_date
            if leave_type not in ('hourly','daily') or not leave_date:return jsonify({'ok':False,'error':'پارامتر ناقص'})
            if leave_type=='hourly':
                end_date=leave_date;start_time=d.get('start_time');end_time=d.get('end_time')
                if not start_time or not end_time:return jsonify({'ok':False,'error':'برای مرخصی ساعتی، ساعت شروع و پایان الزامی است'})
            else:
                if end_date<leave_date:return jsonify({'ok':False,'error':'تاریخ پایان نمی‌تواند قبل از تاریخ شروع باشد'})
                start_time=end_time=None
            cur.execute("UPDATE Leaves SET leave_date=?,end_date=?,leave_type=?,start_time=?,end_time=?,reason=? WHERE id=?",leave_date,end_date,leave_type,start_time,end_time,d.get('reason'),lid);c.commit()
        _audit('leave_update','مرخصی #%s ویرایش شد'%lid);return jsonify({'ok':True})
    except Exception as e:return jsonify({'ok':False,'error':str(e)})

@flask_app.route('/api/leave_review', methods=['POST'])
@require_auth
def api_leave_review():
    try:
        d=request.get_json() or {};actor=flask_g.user
        if not user_has_permission(actor,'leave.approve'):return jsonify({'ok':False,'error':'دسترسی غیرمجاز'}),403
        decision=d.get('decision')
        if decision not in ('approved','rejected'):return jsonify({'ok':False,'error':'مقدار نامعتبر'})
        with _db_lock:
            c=get_conn();cur=c.cursor()
            cur.execute("SELECT staff_id,leave_date,status FROM Leaves WHERE id=?",d.get('id'));row=cur.fetchone()
            if not row:return jsonify({'ok':False,'error':'درخواست مرخصی یافت نشد'})
            if not _team_user_access(cur, actor, row[0], manage=True):
                return jsonify({'ok':False,'error':'این درخواست خارج از محدوده تیم شماست'}),403
            cur.execute("UPDATE Leaves SET status=?,reviewed_by=?,reviewed_at=GETDATE(),review_note=? WHERE id=? AND status='pending'",decision,actor['id'],d.get('review_note'),d.get('id'));affected=cur.rowcount
            c.commit()
        if affected==0:return jsonify({'ok':False,'error':'این درخواست قبلاً بررسی شده یا یافت نشد'})
        if row:_notify(row[0],'leave_'+decision,('مرخصی شما تایید شد: ' if decision=='approved' else 'مرخصی شما رد شد: ')+(row[1] or ''))
        _audit('leave_review','درخواست #%s -> %s'%(d.get('id'),decision));return jsonify({'ok':True})
    except Exception as e:return jsonify({'ok':False,'error':str(e)})

@flask_app.route('/api/leave_delete', methods=['POST'])
@require_auth
def api_leave_delete():
    try:
        d=request.get_json() or {};actor=flask_g.user;leave_id=d.get('id')
        with _db_lock:
            c=get_conn();cur=c.cursor();cur.execute("SELECT staff_id,status FROM Leaves WHERE id=?",leave_id);row=cur.fetchone()
            if not row:return jsonify({'ok':False,'error':'مرخصی یافت نشد'})
            if _is_reward_leave(cur,leave_id):return jsonify({'ok':False,'error':_REWARD_LEAVE_MSG})
            can_manage=user_has_permission(actor,'leave.manage')
            can_own=user_has_permission(actor,'leave.request') and str(row[0])==str(actor['id']) and row[1]=='pending'
            if can_manage and not _team_user_access(cur, actor, row[0], manage=True):can_manage=False
            if not (can_manage or can_own):return jsonify({'ok':False,'error':'دسترسی غیرمجاز یا خارج از محدوده تیم'}),403
            cur.execute("DELETE FROM Leaves WHERE id=?",leave_id);c.commit()
        return jsonify({'ok':True})
    except Exception as e:return jsonify({'ok':False,'error':str(e)})

@flask_app.route('/api/user_delete', methods=['POST'])
@require_auth
def api_user_delete():
    try:
        d = request.get_json()
        uid = d.get('id')
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            allowed, message = _can_manage_target_user(cur, flask_g.user, uid)
            if not allowed:
                return jsonify({'ok': False, 'error': message}), 403
            if int(uid or 0) == int(flask_g.user['id']):
                return jsonify({'ok': False, 'error': 'حذف حساب کاربری فعلی مجاز نیست'}), 403
            cur.execute("DELETE FROM LeadMembers WHERE lead_id=? OR member_id=?", uid, uid)
            cur.execute("DELETE FROM WorkGroupMembers WHERE user_id=?", uid)
            cur.execute("UPDATE WorkGroups SET lead_id=NULL,updated_at=GETDATE() WHERE lead_id=?", uid)
            cur.execute("DELETE FROM Users WHERE id=?", uid)
            c.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@flask_app.route('/api/role_permissions', methods=['POST'])
@require_roles('admin')
def api_role_permissions():
    try:
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            rows = []
            for role, label in ROLES:
                rows.append({'role': role, 'label': label,
                             'permissions': permissions_for_role(cur, role)})
        # Shipping the per-role defaults lets the screen mark what an
        # administrator has customised and offer a real "back to default"
        # instead of making them remember the release's baseline.
        defaults = {role: sorted(default_permissions(role)) for role, _ in ROLES}
        return jsonify({'ok': True, 'roles': rows, 'groups': catalog_payload(),
                        'defaults': defaults,
                        'non_delegable': sorted(NON_DELEGABLE)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@flask_app.route('/api/role_permissions_save', methods=['POST'])
@require_roles('admin')
def api_role_permissions_save():
    try:
        data = request.get_json() or {}
        role = str(data.get('role') or '').strip()
        valid_roles = {x[0] for x in ROLES}
        if role not in valid_roles:
            return jsonify({'ok': False, 'error': 'نقش انتخاب‌شده معتبر نیست'})
        requested = data.get('permissions') or []
        if not isinstance(requested, list):
            return jsonify({'ok': False, 'error': 'فهرست دسترسی معتبر نیست'})
        selected = {str(x) for x in requested if str(x) in ALL_PERMISSION_KEYS}
        selected.difference_update(NON_DELEGABLE)
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            for key in ALL_PERMISSION_KEYS:
                allowed = 1 if key in selected else 0
                cur.execute("""IF EXISTS(SELECT 1 FROM RolePermissions WHERE role=? AND permission_key=?)
                    UPDATE RolePermissions SET is_allowed=?,updated_by=?,updated_at=GETDATE()
                      WHERE role=? AND permission_key=?
                    ELSE INSERT INTO RolePermissions(role,permission_key,is_allowed,updated_by)
                      VALUES(?,?,?,?)""",
                            role, key, allowed, flask_g.user['id'], role, key,
                            role, key, allowed, flask_g.user['id'])
            c.commit()
        _audit('role_permissions_save', 'نقش %s: %s دسترسی فعال' % (role, len(selected)))
        return jsonify({'ok': True, 'permissions': sorted(selected)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

_QUERY_FORBIDDEN = ('users', 'sessions')

def _sql_is_safe_read(sql):
    """Guard for the generic /api/query endpoint: only allow a single
    read-only SELECT, and never let it expose password hashes or session
    tokens. JOINing Users purely for display names is fine and common; what
    must never come back through this generic path is the credential columns
    themselves."""
    s = (sql or '').strip().lower().rstrip(';')
    if not s.startswith('select'):
        return False, 'فقط عملیات خواندن (SELECT) مجاز است'
    # Block stacked statements / write keywords hidden after the SELECT.
    for bad in (';', ' insert ', ' update ', ' delete ', ' drop ', ' alter ',
                ' truncate ', ' exec ', ' merge ', ' into '):
        if bad in s:
            return False, 'دستور غیرمجاز'
    # Never expose credentials or session tokens through the generic reader.
    if 'password' in s:
        return False, 'دسترسی به رمز عبور مجاز نیست'
    import re as _re
    if _re.search(r'\bsessions\b', s):
        return False, 'دسترسی به این جدول از این مسیر مجاز نیست'
    return True, None

@flask_app.route('/api/query', methods=['POST'])
@require_roles('admin')
def api_query():
    try:
        data = request.get_json()
        sql = data.get('sql', '')
        params = data.get('params', [])
        safe, err = _sql_is_safe_read(sql)
        if not safe:
            return jsonify({'ok': False, 'error': err, 'rows': []})
        with _db_lock:
            c = get_conn()
            cur = c.cursor()
            cur.execute(sql, params)
            rows = rows_to_list(cur)
        return jsonify({'ok': True, 'rows': rows})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'rows': []})

@flask_app.route('/api/run', methods=['POST'])
@require_roles('admin')
def api_run():
    try:
        data = request.get_json()
        sql = data.get('sql', '')
        params = data.get('params', [])
        # The generic write endpoint must never be used to mutate the
        # auth-critical tables - all user/password/session changes have
        # dedicated, validated endpoints. This is the guard that prevents a
        # crafted request (or a buggy client) from doing something like
        # "UPDATE Users SET password_hash=..." with no WHERE, which would
        # rewrite EVERYONE's password at once.
        low = (sql or '').lower()
        import re as _re
        for tbl in _QUERY_FORBIDDEN:
            if _re.search(r'\b' + tbl + r'\b', low):
                return jsonify({'ok': False, 'error': 'تغییر این جدول از این مسیر مجاز نیست؛ از عملیات مخصوص کاربران استفاده کنید'})
        # Extra belt-and-suspenders: any UPDATE/DELETE must be row-scoped
        # (have a WHERE clause), so a missing-WHERE accident can't wipe or
        # rewrite an entire table.
        stripped = low.strip()
        if (stripped.startswith('update ') or stripped.startswith('delete ')) and ' where ' not in low:
            return jsonify({'ok': False, 'error': 'عملیات UPDATE/DELETE بدون شرط WHERE مجاز نیست'})
        with _db_lock:
            c = get_conn()
            cur = c.cursor()
            cur.execute(sql, params)
            c.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

# ══════════════════════════════════════════════════════════════════
#  v6 endpoints: notifications, comments, templates, saved filters,
#  audit log, system health, overdue tasks, data export/import
# ══════════════════════════════════════════════════════════════════

def _can_access_task(cur, user, task_id):
    """Permission plus immutable company/team data boundary for task resources."""
    cur.execute("SELECT project_id,staff_id,status,created_by,project_team_id FROM Tasks WHERE id=?", task_id)
    row = cur.fetchone()
    if not row or not user_has_permission(user, 'tasks.view'):
        return False
    if has_company_scope(user):
        return True
    if _team_task_management(cur,user,task_id):
        return True
    # Legacy fallback for an old task not migrated to ProjectTeams yet. This
    # does not grant team-wide visibility; only an explicit assignee/creator.
    if str(row[1]) == str(user.get('id')) or str(row[3]) == str(user.get('id')):
        return True
    cur.execute("SELECT 1 FROM TaskAssignees WHERE task_id=? AND user_id=?", task_id, user.get('id'))
    return cur.fetchone() is not None

@flask_app.route('/api/notifications', methods=['POST'])
@require_auth
def api_notifications():
    """List this user's notifications (newest first) + unread count."""
    try:
        uid = flask_g.user['id']
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            cur.execute("""SELECT TOP 30 id,kind,title,link_task_id,is_read,created_at
                FROM Notifications WHERE user_id=? ORDER BY id DESC""", uid)
            rows = rows_to_list(cur)
            cur.execute("SELECT COUNT(*) FROM Notifications WHERE user_id=? AND is_read=0", uid)
            unread = cur.fetchone()[0]
        return jsonify({'ok': True, 'rows': rows, 'unread': unread})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'rows': [], 'unread': 0})

@flask_app.route('/api/notifications_read', methods=['POST'])
@require_auth
def api_notifications_read():
    """Mark all (or one) of this user's notifications as read."""
    try:
        uid = flask_g.user['id']
        nid = (request.get_json() or {}).get('id')
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            if nid:
                cur.execute("UPDATE Notifications SET is_read=1 WHERE user_id=? AND id=?", uid, nid)
            else:
                cur.execute("UPDATE Notifications SET is_read=1 WHERE user_id=?", uid)
            c.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@flask_app.route('/api/task_comments', methods=['POST'])
@require_auth
def api_task_comments():
    """List comments for a task (oldest first)."""
    try:
        tid = (request.get_json() or {}).get('task_id')
        if not tid:
            return jsonify({'ok': False, 'error': 'task_id لازم است', 'rows': []})
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            if not _can_access_task(cur, flask_g.user, tid):
                return jsonify({'ok': False, 'error': 'دسترسی به این تسک مجاز نیست', 'rows': []}), 403
            cur.execute("""SELECT id,user_id,author_name,author_role,body,created_at
                FROM TaskComments WHERE task_id=? ORDER BY id ASC""", tid)
            rows = rows_to_list(cur)
        return jsonify({'ok': True, 'rows': rows})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'rows': []})

@flask_app.route('/api/task_comment_add', methods=['POST'])
@require_auth
def api_task_comment_add():
    """Add a comment to a task. Notifies the assigned support + task creator
    (whoever isn't the author) so a back-and-forth is visible."""
    try:
        u = flask_g.user
        d = request.get_json() or {}
        tid = d.get('task_id')
        body = (d.get('body') or '').strip()
        if not tid or not body:
            return jsonify({'ok': False, 'error': 'متن نظر خالی است'})
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            if not _can_access_task(cur, u, tid):
                return jsonify({'ok': False, 'error': 'دسترسی به این تسک مجاز نیست'}), 403
            cur.execute("INSERT INTO TaskComments(task_id,user_id,author_name,author_role,body) VALUES(?,?,?,?,?)",
                        tid, u['id'], u['display_name'] or u['username'], u['role'], body[:4000])
            cur.execute("SELECT title,staff_id,created_by,contact_id FROM Tasks WHERE id=?", tid)
            trow = cur.fetchone()
            c.commit()
        if trow:
            title, staff_id, created_by, contact_id = trow
            short = (title or '')[:40]
            for target in {staff_id, created_by, contact_id}:
                if target and target != u['id']:
                    _notify(target, 'comment', 'نظر جدید روی تسک: ' + short, tid)
        _audit('comment_add', 'تسک #%s' % tid, user=u)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@flask_app.route('/api/templates', methods=['POST'])
@require_auth
def api_templates():
    try:
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            cur.execute("""SELECT tt.id,tt.name,tt.title,tt.type,tt.category_id,tt.description,tt.priority,cat.name as cat_name
                FROM TaskTemplates tt LEFT JOIN TaskCategories cat ON cat.id=tt.category_id ORDER BY tt.name""")
            rows = rows_to_list(cur)
        return jsonify({'ok': True, 'rows': rows})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'rows': []})

@flask_app.route('/api/template_save', methods=['POST'])
@require_auth
def api_template_save():
    try:
        d = request.get_json() or {}
        tid = d.get('id')
        name = (d.get('name') or '').strip()
        if not name:
            return jsonify({'ok': False, 'error': 'نام قالب الزامی است'})
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            if tid:
                cur.execute("UPDATE TaskTemplates SET name=?,title=?,type=?,category_id=?,description=?,priority=? WHERE id=?",
                    name, d.get('title'), d.get('type'), d.get('category_id') or None, d.get('description'), d.get('priority') or None, tid)
            else:
                cur.execute("INSERT INTO TaskTemplates(name,title,type,category_id,description,priority,created_by) VALUES(?,?,?,?,?,?,?)",
                    name, d.get('title'), d.get('type'), d.get('category_id') or None, d.get('description'), d.get('priority') or None, flask_g.user['id'])
            c.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@flask_app.route('/api/template_delete', methods=['POST'])
@require_auth
def api_template_delete():
    try:
        tid = (request.get_json() or {}).get('id')
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            cur.execute("DELETE FROM TaskTemplates WHERE id=?", tid)
            c.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@flask_app.route('/api/saved_filters', methods=['POST'])
@require_auth
def api_saved_filters():
    try:
        uid = flask_g.user['id']
        scope = (request.get_json() or {}).get('scope')
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            if scope:
                cur.execute("SELECT id,name,scope,filter_json FROM SavedFilters WHERE user_id=? AND scope=? ORDER BY name", uid, scope)
            else:
                cur.execute("SELECT id,name,scope,filter_json FROM SavedFilters WHERE user_id=? ORDER BY name", uid)
            rows = rows_to_list(cur)
        return jsonify({'ok': True, 'rows': rows})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'rows': []})

@flask_app.route('/api/saved_filter_save', methods=['POST'])
@require_auth
def api_saved_filter_save():
    try:
        u = flask_g.user
        d = request.get_json() or {}
        name = (d.get('name') or '').strip()
        scope = d.get('scope') or 'report'
        fj = d.get('filter_json') or '{}'
        if not name:
            return jsonify({'ok': False, 'error': 'نام فیلتر الزامی است'})
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            cur.execute("INSERT INTO SavedFilters(user_id,name,scope,filter_json) VALUES(?,?,?,?)",
                        u['id'], name, scope, fj)
            c.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@flask_app.route('/api/saved_filter_delete', methods=['POST'])
@require_auth
def api_saved_filter_delete():
    try:
        uid = flask_g.user['id']
        fid = (request.get_json() or {}).get('id')
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            cur.execute("DELETE FROM SavedFilters WHERE id=? AND user_id=?", fid, uid)
            c.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@flask_app.route('/api/audit_log', methods=['POST'])
@require_auth
def api_audit_log():
    try:
        d = request.get_json() or {}
        limit = min(int(d.get('limit') or 100), 500)
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            cur.execute("SELECT TOP (%d) id,user_id,username,action,detail,ip,created_at FROM AuditLog ORDER BY id DESC" % limit)
            rows = rows_to_list(cur)
        return jsonify({'ok': True, 'rows': rows})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'rows': []})

@flask_app.route('/api/active_sessions', methods=['POST'])
@require_roles('admin')
def api_active_sessions():
    try:
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            cur.execute("DELETE FROM Sessions WHERE expires_at < GETDATE() OR (last_seen IS NOT NULL AND last_seen < DATEADD(hour,-2,GETDATE()))")
            c.commit()
            cur.execute("""SELECT s.token,u.id AS user_id,u.username,u.display_name,u.role,s.created_at,s.last_seen,s.expires_at,s.ip_address,s.user_agent
                FROM Sessions s JOIN Users u ON u.id=s.user_id
                WHERE s.expires_at >= GETDATE() ORDER BY u.display_name,s.last_seen DESC,s.created_at DESC""")
            raw = rows_to_list(cur)
        grouped = {}
        for row in raw:
            uid = row['user_id']
            item = grouped.setdefault(uid, {
                'user_id': uid, 'username': row.get('username'),
                'display_name': row.get('display_name'), 'role': row.get('role'),
                'session_count': 0, 'last_seen': row.get('last_seen'), 'sessions': []})
            item['session_count'] += 1
            if row.get('last_seen') and (not item.get('last_seen') or row['last_seen'] > item['last_seen']):
                item['last_seen'] = row['last_seen']
            token = row.pop('token', '') or ''
            item['sessions'].append({
                'session_key': hashlib.sha256(token.encode('utf-8')).hexdigest()[:20],
                'created_at': row.get('created_at'), 'last_seen': row.get('last_seen'),
                'expires_at': row.get('expires_at'), 'ip_address': row.get('ip_address'),
                'device': (row.get('user_agent') or '')[:120]})
        rows = sorted(grouped.values(), key=lambda x: str(x.get('last_seen') or ''), reverse=True)
        return jsonify({'ok': True, 'rows': rows, 'total_sessions': len(raw)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'rows': []})

@flask_app.route('/api/session_revoke', methods=['POST'])
@require_roles('admin')
def api_session_revoke():
    try:
        d = request.get_json() or {}
        user_id = d.get('user_id')
        if not user_id:
            return jsonify({'ok': False, 'error': 'کاربر مشخص نشده است'})
        session_key = (d.get('session_key') or '').strip()
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            if session_key:
                cur.execute("SELECT token FROM Sessions WHERE user_id=?", user_id)
                tokens = [r[0] for r in cur.fetchall()]
                exact = next((t for t in tokens if hashlib.sha256(t.encode('utf-8')).hexdigest()[:20] == session_key), None)
                if exact:
                    cur.execute("DELETE FROM Sessions WHERE token=? AND user_id=?", exact, user_id)
                    count = cur.rowcount
                else:
                    count = 0
            else:
                cur.execute("DELETE FROM Sessions WHERE user_id=?", user_id)
                count = cur.rowcount
            c.commit()
        _audit('session_revoke', 'خروج اجباری کاربر #%s (%s نشست%s)' % (user_id, count, ' مشخص' if session_key else ''))
        return jsonify({'ok': True, 'count': count})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@flask_app.route('/api/system_health', methods=['POST'])
@require_auth
def api_system_health():
    """Quick operational snapshot for admins: DB connectivity, row counts,
    active sessions, last backup, recent errors from the audit log."""
    try:
        health = {'db_ok': True, 'version': APP_VERSION, 'session_hours': SESSION_HOURS}
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            def one(sql):
                cur.execute(sql); return cur.fetchone()[0]
            health['users'] = one("SELECT COUNT(*) FROM Users")
            health['active_sessions'] = one("SELECT COUNT(*) FROM Sessions WHERE expires_at >= GETDATE()")
            health['tasks'] = one("SELECT COUNT(*) FROM Tasks")
            health['open_tasks'] = one("SELECT COUNT(*) FROM Tasks WHERE status NOT IN ('done','rejected')")
            health['cities'] = one("SELECT COUNT(*) FROM Cities")
            health['projects'] = one("SELECT COUNT(*) FROM Projects")
            health['notifications'] = one("SELECT COUNT(*) FROM Notifications")
            health['audit_rows'] = one("SELECT COUNT(*) FROM AuditLog")
        # Last backup marker (written by the differential backup script)
        last_backup = None
        try:
            bdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backups')
            if os.path.isdir(bdir):
                files = [f for f in os.listdir(bdir) if f.lower().endswith('.taskhubbackup')]
                if files:
                    files.sort()
                    last_backup = files[-1]
        except Exception:
            pass
        health['last_backup'] = last_backup
        return jsonify({'ok': True, 'health': health})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'health': {'db_ok': False}})

@flask_app.route('/api/data_export', methods=['POST'])
@require_roles('admin')
def api_data_export():
    """Logical JSON export.  File bytes and live session tokens are excluded;
    use the verified .taskhubbackup checkpoints for a restorable backup."""
    try:
        import json as _json
        tables = ['Cities','Projects','TaskCategories','Users','Tasks','TaskAssignees',
                  'TaskTimeLog','WeeklySchedule','Holidays','Missions','Attendance','Leaves',
                  'TaskComments','TaskTemplates','Contracts','ContractExtensions',
                  'ContractStatements','ContractStatementItems','ContractStatementTaxEvents',
                  'FinancialPlans','FinancialPlanPeriods','FinancialPlanRevisions',
                  'PlannedStatements','PlannedStatementTasks','FileBlobs','Attachments',
                  'MigrationQuarantine','EntityAudit']
        dump = {'_meta': {'app': 'TaskHub', 'version': APP_VERSION,
                          'exported_at': datetime.datetime.now().isoformat()}}
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            for t in tables:
                try:
                    cur.execute("SELECT * FROM %s" % t)
                    dump[t] = rows_to_list(cur)
                except Exception:
                    dump[t] = []
        _audit('data_export', 'خروجی کامل داده')
        fd, path = tempfile.mkstemp(suffix='.json', prefix='taskhub_export_')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            _json.dump(dump, f, ensure_ascii=False, default=str, indent=1)
        fname = 'taskhub_backup_%s.json' % datetime.datetime.now().strftime('%Y%m%d_%H%M')
        return send_file(path, as_attachment=True, download_name=fname, mimetype='application/json')
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@flask_app.route('/api/analytics', methods=['POST'])
@require_auth
def api_analytics():
    """Managerial analytics: average resolution time (from started to
    completed, using work_seconds) grouped by city/project/staff, plus a
    this-month vs last-month task-count comparison for a trend indicator."""
    try:
        d=request.get_json() or {}
        scope_clause,scope_params=_task_team_scope(flask_g.user,d,'t')
        scope_sql=(" AND "+scope_clause) if scope_clause else ""
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            # Average work_seconds on DONE tasks, by city
            cur.execute("""SELECT ISNULL(ci.name,N'بدون شهر') as city, AVG(CAST(t.work_seconds AS FLOAT)) as avg_s, COUNT(*) as cnt
                FROM Tasks t LEFT JOIN Projects p ON p.id=t.project_id LEFT JOIN Cities ci ON ci.id=p.city_id
                WHERE t.status='done' AND t.work_seconds > 0""" + scope_sql + """
                GROUP BY ci.name ORDER BY avg_s DESC""",scope_params)
            by_city = [{'label': r[0], 'avg_seconds': int(r[1] or 0), 'count': r[2]} for r in cur.fetchall()]
            # By staff
            cur.execute("""SELECT ISNULL(u.display_name,N'—') as name, AVG(CAST(t.work_seconds AS FLOAT)) as avg_s, COUNT(*) as cnt
                FROM Tasks t LEFT JOIN Users u ON u.id=t.staff_id
                WHERE t.status='done' AND t.work_seconds > 0 AND t.staff_id IS NOT NULL""" +
                scope_sql + """
                GROUP BY u.display_name ORDER BY avg_s ASC""",scope_params)
            by_staff = [{'label': r[0], 'avg_seconds': int(r[1] or 0), 'count': r[2]} for r in cur.fetchall()]
            # This month vs last month (by completed_at)
            cur.execute("""SELECT
                    SUM(CASE WHEN completed_at >= DATEADD(month, DATEDIFF(month,0,GETDATE()), 0) THEN 1 ELSE 0 END) as this_m,
                    SUM(CASE WHEN completed_at >= DATEADD(month, DATEDIFF(month,0,GETDATE())-1, 0)
                             AND completed_at <  DATEADD(month, DATEDIFF(month,0,GETDATE()), 0) THEN 1 ELSE 0 END) as last_m
                FROM Tasks t WHERE t.status='done' AND t.completed_at IS NOT NULL""" +
                scope_sql,scope_params)
            row = cur.fetchone()
            this_m, last_m = int(row[0] or 0), int(row[1] or 0)
        return jsonify({'ok': True, 'by_city': by_city, 'by_staff': by_staff,
                        'this_month': this_m, 'last_month': last_m})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@flask_app.route('/api/overdue_tasks', methods=['POST'])
@require_auth
def api_overdue_tasks():
    """Tasks whose delivery (due) date is before today and still open.
    date_delivery is the 'موعد نهایی تحویل' (final delivery deadline) field, stored Jalali.
    Scoped by the caller's real role (from the session token) - management
    sees everything, a support worker sees only their own overdue work, an
    employer sees only their own project's, and a supervisor (who doesn't
    own tasks or a project) sees none."""
    try:
        u = flask_g.user
        d=request.get_json() or {}
        today = _today_jalali_str()
        where = ["t.date_delivery IS NOT NULL", "t.date_delivery <> ''",
                 "LEN(t.date_delivery)=10", "t.date_delivery < ?", "t.status NOT IN ('done','rejected')"]
        params = [today]
        if user_has_permission(u, 'tasks.view_all'):
            scope_clause,scope_params=_task_team_scope(u,d,'t')
            if scope_clause:
                where.append(scope_clause);params.extend(scope_params)
        elif user_has_permission(u, 'tasks.self_manage'):
            where.append("t.project_id = ?")
            params.append(u.get('project_id'))
        elif user_has_permission(u, 'tasks.work'):
            where.append("(t.staff_id = ? OR EXISTS(SELECT 1 FROM TaskAssignees ta WHERE ta.task_id=t.id AND ta.user_id=?))")
            params.extend([u['id'], u['id']])
        else:
            return jsonify({'ok': True, 'rows': [], 'today': today})
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            cur.execute("""SELECT t.id,t.title,t.date_delivery,t.status,u.display_name as staff_name,
                    p.name as pname
                FROM Tasks t LEFT JOIN Users u ON u.id=t.staff_id
                LEFT JOIN Projects p ON p.id=t.project_id
                WHERE """ + " AND ".join(where) + """
                ORDER BY t.date_delivery ASC""", params)
            rows = rows_to_list(cur)
        return jsonify({'ok': True, 'rows': rows, 'today': today})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'rows': []})

@flask_app.route('/api/presence', methods=['POST'])
@require_auth
def api_presence():
    """Who's currently checked in (present) right now, and what task - if
    any - they're actively timing at this exact moment. 'Present' means an
    open Attendance row for today (checked in, not checked out yet).
    'Working on' comes from Tasks.active_actor_id + status='doing', which is
    the same signal the timer/lock logic already uses elsewhere, so it's
    always in sync with the real single-active-timer-per-person rule."""
    try:
        today = _today_jalali_str()
        d=request.get_json() or {};actor=flask_g.user
        try:selected_team=int(d.get('_team_scope'))
        except (TypeError,ValueError):selected_team=None
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            conditions=["a.work_date=?","a.check_out IS NULL","u.is_active=1"]
            params=[today]
            global_presence = has_company_scope(actor)
            if selected_team:
                conditions.append("""EXISTS(SELECT 1 FROM TeamMembers target
                    WHERE target.team_id=? AND target.user_id=u.id
                      AND target.is_active=1)""")
                params.append(selected_team)
                if not global_presence:
                    conditions.append("""EXISTS(SELECT 1 FROM TeamMembers mine
                        WHERE mine.team_id=? AND mine.user_id=?
                          AND mine.is_active=1)""")
                    params.extend([selected_team,actor['id']])
            elif not global_presence and actor['role'] in ('manager','planner','support','lead'):
                conditions.append("""EXISTS(SELECT 1 FROM TeamMembers target
                    JOIN TeamMembers mine ON mine.team_id=target.team_id
                    WHERE target.user_id=u.id AND target.is_active=1
                      AND mine.user_id=? AND mine.is_active=1)""")
                params.append(actor['id'])
            elif not global_presence:
                conditions.append("u.id=?");params.append(actor['id'])
            cur.execute("""SELECT u.id,u.display_name,u.role,a.check_in,a.last_heartbeat
                FROM Attendance a JOIN Users u ON u.id=a.user_id
                WHERE """+" AND ".join(conditions)+
                        " ORDER BY a.check_in ASC",params)
            present = rows_to_list(cur)
            if present:
                ids = [p['id'] for p in present]
                placeholders = ','.join('?' * len(ids))
                cur.execute("""SELECT t.active_actor_id, t.id, t.title, p.name as pname
                    FROM Tasks t LEFT JOIN Projects p ON p.id=t.project_id
                    WHERE t.status='doing' AND t.active_actor_id IN (%s)""" % placeholders, ids)
                working = {r[0]: {'task_id': r[1], 'title': r[2], 'project': r[3]} for r in cur.fetchall()}
            else:
                working = {}
        for p in present:
            p['current_task'] = working.get(p['id'])
        return jsonify({'ok': True, 'rows': present})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'rows': []})

@flask_app.route('/api/dashboard_stats', methods=['POST'])
@require_auth
def api_dashboard_stats():
    """Aggregate analytics for the dashboard charts. Returns several small
    datasets the frontend renders as bar/donut charts: task counts by city,
    by project, by status, and per-support workload (open vs done)."""
    try:
        d=request.get_json() or {}
        scope_clause,scope_params=_task_team_scope(flask_g.user,d,'t')
        scope_where=(" WHERE "+scope_clause) if scope_clause else ""
        scope_and=(" AND "+scope_clause) if scope_clause else ""
        with _db_lock:
            c = get_conn(); cur = c.cursor()

            # Tasks per city (via project -> city)
            cur.execute("""SELECT ISNULL(ci.name, N'بدون شهر') as city, COUNT(t.id) as cnt
                FROM Tasks t
                LEFT JOIN Projects p ON p.id=t.project_id
                LEFT JOIN Cities ci ON ci.id=p.city_id
                """+scope_where+"""
                GROUP BY ci.name ORDER BY cnt DESC""",scope_params)
            by_city = [{'label': r[0], 'value': r[1]} for r in cur.fetchall()]

            # Tasks per project (top 8)
            cur.execute("""SELECT TOP 8 ISNULL(p.name, N'بدون پروژه') as proj, COUNT(t.id) as cnt
                FROM Tasks t LEFT JOIN Projects p ON p.id=t.project_id
                """+scope_where+"""
                GROUP BY p.name ORDER BY cnt DESC""",scope_params)
            by_project = [{'label': r[0], 'value': r[1]} for r in cur.fetchall()]

            # Tasks per status
            cur.execute("SELECT t.status, COUNT(*) FROM Tasks t"+scope_where+
                        " GROUP BY t.status",scope_params)
            status_map = {r[0]: r[1] for r in cur.fetchall()}

            # Per-support workload: open (not done/rejected) vs done
            cur.execute("""SELECT ISNULL(u.display_name, N'بدون پشتیبان') as name,
                    SUM(CASE WHEN t.status='done' THEN 1 ELSE 0 END) as done_cnt,
                    SUM(CASE WHEN t.status NOT IN ('done','rejected') THEN 1 ELSE 0 END) as open_cnt
                FROM Tasks t LEFT JOIN Users u ON u.id=t.staff_id
                WHERE t.staff_id IS NOT NULL"""+scope_and+"""
                GROUP BY u.display_name ORDER BY (SUM(CASE WHEN t.status NOT IN ('done','rejected') THEN 1 ELSE 0 END)) DESC""",scope_params)
            by_staff = [{'label': r[0], 'done': r[1] or 0, 'open': r[2] or 0} for r in cur.fetchall()]

            # Totals
            cur.execute("SELECT COUNT(*) FROM Tasks t"+scope_where,scope_params)
            total_tasks = cur.fetchone()[0]
            if scope_clause:
                cur.execute("""SELECT COUNT(DISTINCT p.city_id),
                    COUNT(DISTINCT t.project_id) FROM Tasks t
                    LEFT JOIN Projects p ON p.id=t.project_id WHERE """+
                            scope_clause,scope_params)
                totals_row=cur.fetchone()
                total_cities=int((totals_row[0] if totals_row else 0) or 0)
                total_projects=int((totals_row[1] if totals_row else 0) or 0)
            else:
                cur.execute("SELECT COUNT(*) FROM Cities")
                total_cities = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM Projects")
                total_projects = cur.fetchone()[0]

        return jsonify({'ok': True,
            'by_city': by_city,
            'by_project': by_project,
            'by_status': status_map,
            'by_staff': by_staff,
            'totals': {'tasks': total_tasks, 'cities': total_cities, 'projects': total_projects}})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@flask_app.route('/api/task_evaluation_get', methods=['POST'])
@require_auth
def api_task_evaluation_get():
    """List every contributor (primary support + helpers) of a task along
    with their existing score/note if one has been given yet (null if not).
    Available in any task status - evaluation isn't tied to 'done'."""
    try:
        tid = (request.get_json() or {}).get('task_id')
        if not tid:
            return jsonify({'ok': False, 'error': 'task_id لازم است', 'rows': []})
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            if not _team_task_management(cur,flask_g.user,tid):
                return jsonify({'ok':False,'error':'به ارزیابی تسک این تیم دسترسی ندارید','rows':[]}),403
            # Everyone who touched this task: the primary assignee plus any
            # helpers, de-duplicated.
            cur.execute("""SELECT u.id, u.display_name
                FROM Users u WHERE u.id IN (
                    SELECT staff_id FROM Tasks WHERE id=? AND staff_id IS NOT NULL
                    UNION
                    SELECT user_id FROM TaskAssignees WHERE task_id=?
                )""", tid, tid)
            people = rows_to_list(cur)
            cur.execute("""SELECT te.user_id, te.score, te.note, te.rated_at, ru.display_name as rated_by_name
                FROM TaskEvaluations te LEFT JOIN Users ru ON ru.id=te.rated_by
                WHERE te.task_id=?""", tid)
            existing = {r['user_id']: r for r in rows_to_list(cur)}
        for p in people:
            e = existing.get(p['id'])
            p['score'] = e['score'] if e else None
            p['note'] = e['note'] if e else None
            p['rated_at'] = e['rated_at'] if e else None
            p['rated_by_name'] = e['rated_by_name'] if e else None
        return jsonify({'ok': True, 'rows': people})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'rows': []})

@flask_app.route('/api/task_evaluation_save', methods=['POST'])
@require_auth
def api_task_evaluation_save():
    """Upsert one or more per-contributor star ratings for a task.

    From R13 an evaluation is 1 to 5 stars, and it scales the points that
    person earns on this task by 0.8 to 1.2. Scores saved before R13 keep
    their old open-ended numbers in the history and count as neutral."""
    try:
        u = flask_g.user
        d = request.get_json() or {}
        tid = d.get('task_id')
        scores = d.get('scores') or []
        if not tid or not scores:
            return jsonify({'ok': False, 'error': 'اطلاعات ناقص'})
        # Checked before anything is written, so a bad row never leaves the
        # task half-rated.
        for s in scores:
            try:
                stars = int(s.get('score'))
            except (TypeError, ValueError):
                continue
            if not 1 <= stars <= 5:
                return jsonify({'ok': False, 'error': 'ارزیابی هر نفر باید بین ۱ تا ۵ ستاره باشد'})
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            if not _team_task_management(cur,u,tid):
                return jsonify({'ok':False,'error':'به ارزیابی تسک این تیم دسترسی ندارید'}),403
            for s in scores:
                uid = s.get('user_id')
                score = s.get('score')
                if uid is None or score is None:
                    continue
                try:
                    score = int(score)
                except (TypeError, ValueError):
                    continue
                note = (s.get('note') or '').strip()[:500] or None
                cur.execute("SELECT id FROM TaskEvaluations WHERE task_id=? AND user_id=?", tid, uid)
                row = cur.fetchone()
                if row:
                    cur.execute("UPDATE TaskEvaluations SET score=?,note=?,rated_by=?,rated_at=GETDATE() WHERE id=?",
                                score, note, u['id'], row[0])
                else:
                    cur.execute("INSERT INTO TaskEvaluations(task_id,user_id,score,note,rated_by) VALUES(?,?,?,?,?)",
                                tid, uid, score, note, u['id'])
            c.commit()
        _audit('task_evaluate', 'تسک #%s' % tid)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@flask_app.route('/api/task_time_daily', methods=['POST'])
@require_auth
def api_task_time_daily():
    """Per-day, per-person work-time breakdown for one task, built from
    TaskTimeLog segments. A segment that crosses midnight is split so each
    calendar day is credited with exactly the seconds worked within it.
    Open segments (still running) are counted up to 'now'."""
    try:
        import datetime as _dt
        d = request.get_json()
        tid = d.get('task_id')
        if not tid:
            return jsonify({'ok': False, 'error': 'task_id لازم است'})
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            cur.execute("""SELECT tl.user_id, u.display_name, tl.started_at, tl.ended_at
                FROM TaskTimeLog tl LEFT JOIN Users u ON u.id=tl.user_id
                WHERE tl.task_id=? ORDER BY tl.started_at""", tid)
            segs = cur.fetchall()
        now = _dt.datetime.now()
        agg = {}  # (jalali_date, user_id) -> [name, seconds]
        for user_id, name, start, end in segs:
            if start is None:
                continue
            end = end or now
            if end <= start:
                continue
            cursor = start
            while cursor < end:
                day_end = _dt.datetime(cursor.year, cursor.month, cursor.day) + _dt.timedelta(days=1)
                chunk_end = min(end, day_end)
                secs = int((chunk_end - cursor).total_seconds())
                if secs > 0:
                    jdate = _gregorian_to_jalali_str(cursor.year, cursor.month, cursor.day)
                    key = (jdate, user_id)
                    if key not in agg:
                        agg[key] = [name or ('کاربر #%s' % user_id), 0]
                    agg[key][1] += secs
                cursor = chunk_end
        rows = [{'date_jalali': k[0], 'user_id': k[1], 'user_name': v[0], 'seconds': v[1]}
                for k, v in sorted(agg.items())]
        return jsonify({'ok': True, 'rows': rows})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@flask_app.route('/api/task_transition', methods=['POST'])
@require_auth
def api_task_transition():
    """Server-authoritative status changes with time tracking.

    State machine:
      registered --triage_approve(admin/supervisor)--> approved
      registered --triage_reject(admin/supervisor, needs reason)--> rejected
      registered --assign(admin)--> assigned   [admin can shortcut triage by assigning directly]
      approved --assign(admin)--> assigned
      assigned --start(support)--> doing
      assigned --back_admin(support)--> returned
      doing --back_admin(support)--> returned
      doing --pause(support)--> paused   [explicit "pause my own work" - time banked,
                                          task stays theirs, NOT sent back to admin]
      paused --start(support)--> doing   [resume - new time adds to what was banked]
      paused --back_admin(support)--> returned
      doing --forward(support, can include solution text)--> pending_approval
      pending_approval --approve(admin)--> done
      pending_approval --send_back(admin)--> assigned   [support must click "start" again;
                                                          work_seconds already banked from the
                                                          previous cycle is kept and the next
                                                          "forward" simply adds to it]
      returned --assign(admin)--> assigned

      add_helper/remove_helper(admin or anyone already on the task) - some
      tasks need more than one pair of hands; this adds/removes an extra
      support user alongside the primary assignee (Tasks.staff_id), who then
      has the exact same start/forward/back_admin rights as the primary.

    Note: assigning a support user does NOT start the work clock - that only
    happens when support actively clicks "start". This also means support can
    decline/return a task immediately without being forced to start it first.

    One-active-timer rule: a person can only really work on one thing at a
    time. So whenever "start" is called, any OTHER task where this same
    person is the PRIMARY assignee and which is currently "doing" gets
    auto-paused first (its elapsed time properly banked) - this is what makes
    "an urgent task came in" safe: starting the urgent one can't silently
    leave two timers running and double-count time. Tasks where they're only
    a helper (not primary) are left alone, since the task's shared clock may
    still need to keep running for the primary or other helpers.

    Uses server clock (GETDATE) so timing can't be spoofed by the client,
    and verifies the support user owns the task before start/forward/back.
    """
    try:
        d = request.get_json()
        tid = d.get('task_id')
        action = d.get('action')
        actor_id, actor_role = _effective_actor(d)
        new_staff_id = d.get('staff_id')
        helper_id = d.get('helper_id')
        solution_text = d.get('solution')
        test_notes_text = d.get('test_notes')
        reject_reason = d.get('reason')
        if not tid or not action:
            return jsonify({'ok': False, 'error': 'پارامتر ناقص'})
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            cur.execute("SELECT status,staff_id,started_at,work_seconds,active_actor_id,project_team_id FROM Tasks WHERE id=?", tid)
            row = cur.fetchone()
            if not row:
                return jsonify({'ok': False, 'error': 'تسک یافت نشد'})
            cur_status, staff_id, started_at, work_seconds, cur_active_actor_id, project_team_id = row[0], row[1], row[2], (row[3] or 0), row[4], row[5]
            if not _team_task_management(cur,flask_g.user,tid):
                return jsonify({'ok':False,'error':'این تسک خارج از محدوده تیم شماست'}),403

            def _is_on_task(uid):
                if uid is not None and staff_id is not None and str(staff_id) == str(uid):
                    return True
                cur.execute("SELECT 1 FROM TaskAssignees WHERE task_id=? AND user_id=?", tid, uid)
                return cur.fetchone() is not None

            worker_actions = ('start', 'forward', 'back_admin', 'pause')
            assignment_actions = ('assign', 'add_helper', 'remove_helper', 'set_work_time')
            triage_actions = ('triage_approve', 'triage_reject')
            approval_actions = ('approve', 'send_back')

            if action in worker_actions:
                if not user_has_permission(flask_g.user, 'tasks.work') and not user_has_permission(flask_g.user, 'tasks.edit'):
                    return jsonify({'ok': False, 'error': 'دسترسی انجام کار روی تسک را ندارید'}), 403
                if not user_has_permission(flask_g.user, 'tasks.edit') and not _is_on_task(actor_id):
                    return jsonify({'ok': False, 'error': 'این تسک به شما واگذار نشده است'}), 403
            elif action in assignment_actions:
                has_assignment = user_has_permission(flask_g.user, 'tasks.assign')
                has_own_work = user_has_permission(flask_g.user, 'tasks.work') and _is_on_task(actor_id)
                if not has_assignment and not (action in ('add_helper','remove_helper','set_work_time') and has_own_work):
                    return jsonify({'ok': False, 'error': 'دسترسی ارجاع و مدیریت همکاران تسک را ندارید'}), 403
            elif action in triage_actions:
                if not user_has_permission(flask_g.user, 'tasks.triage'):
                    return jsonify({'ok': False, 'error': 'دسترسی بررسی اولیه تسک را ندارید'}), 403
            elif action in approval_actions:
                if not user_has_permission(flask_g.user, 'tasks.approve'):
                    # R15 group lead: approves or returns the tasks of themselves
                    # and their sub-group only. Approving your own task earns you
                    # no points (the gamification self-approval rule).
                    in_group = (user_has_permission(flask_g.user, 'tasks.approve_group')
                                and staff_id is not None
                                and int(staff_id) in lead_group_ids(cur, flask_g.user['id']))
                    if not in_group:
                        return jsonify({'ok': False, 'error': 'دسترسی تأیید یا برگشت تسک را ندارید'}), 403
            else:
                return jsonify({'ok': False, 'error': 'عملیات مجاز نیست'}), 403

            if action == 'start' and cur_status not in ('assigned', 'paused'):
                return jsonify({'ok': False, 'error': 'این تسک در وضعیت قابل شروع نیست'})
            if action == 'pause' and cur_status != 'doing':
                return jsonify({'ok': False, 'error': 'این تسک در وضعیت قابل توقف نیست'})
            if action == 'forward' and cur_status != 'doing':
                return jsonify({'ok': False, 'error': 'این تسک در وضعیت قابل ارسال نیست'})
            if action == 'back_admin' and cur_status not in ('assigned', 'doing', 'paused'):
                return jsonify({'ok': False, 'error': 'این تسک در وضعیت قابل برگشت نیست'})
            if action == 'assign' and cur_status not in ('registered', 'approved', 'returned', 'assigned'):
                return jsonify({'ok': False, 'error': 'این تسک در وضعیت قابل واگذاری نیست'})
            if action in ('triage_approve', 'triage_reject') and cur_status != 'registered':
                return jsonify({'ok': False, 'error': 'این تسک در وضعیت قابل بررسی نیست'})
            if action in ('approve', 'send_back') and cur_status != 'pending_approval':
                return jsonify({'ok': False, 'error': 'این تسک در وضعیت قابل تایید/برگشت نیست'})
            if action in ('add_helper', 'remove_helper') and cur_status not in ('assigned', 'doing', 'paused'):
                return jsonify({'ok': False, 'error': 'این تسک در وضعیت قابل افزودن همکار نیست'})

            auto_paused = []
            if action == 'triage_approve':
                cur.execute("UPDATE Tasks SET status='approved' WHERE id=?", tid)
            elif action == 'triage_reject':
                if not reject_reason or not str(reject_reason).strip():
                    return jsonify({'ok': False, 'error': 'نوشتن دلیل رد الزامی است'})
                cur.execute("UPDATE Tasks SET status='rejected',reject_reason=? WHERE id=?", reject_reason, tid)
            elif action == 'assign':
                if not new_staff_id:
                    return jsonify({'ok': False, 'error': 'پشتیبان انتخاب نشده است'})
                if project_team_id:
                    cur.execute("""SELECT 1 FROM ProjectTeams pt JOIN TeamMembers tm
                        ON tm.team_id=pt.team_id WHERE pt.id=? AND tm.user_id=?
                        AND pt.is_active=1 AND tm.is_active=1""",
                                project_team_id, new_staff_id)
                    if not cur.fetchone():
                        return jsonify({'ok': False, 'error': 'پشتیبان انتخاب‌شده عضو تیم این تسک نیست'})
                cur.execute("UPDATE Tasks SET staff_id=?,status='assigned' WHERE id=?", new_staff_id, tid)
            elif action == 'start':
                # One-active-timer rule: auto-pause any OTHER task that THIS
                # PERSON is actually, currently running the clock on -
                # checked via active_actor_id, NOT staff_id. This distinction
                # is the fix for a real multi-assignee bug: if task T's
                # primary is A and a helper B is the one who actually clicked
                # "start" on T (active_actor_id=B), then A starting a
                # different task of their own must NOT touch T - A isn't the
                # one running T's clock right now, B is. Checking staff_id
                # instead would wrongly auto-pause B's active work just
                # because A happens to be T's primary assignee.
                cur.execute("SELECT id,started_at,work_seconds FROM Tasks WHERE active_actor_id=? AND status='doing' AND id<>?", actor_id, tid)
                others = cur.fetchall() or []
                for orow in others:
                    other_id, other_started, other_work = orow[0], orow[1], (orow[2] or 0)
                    if other_started is not None:
                        cur.execute("UPDATE Tasks SET status='paused',"
                                    "work_seconds=ISNULL(work_seconds,0)+DATEDIFF(SECOND,started_at,GETDATE()),started_at=NULL,active_actor_id=NULL WHERE id=?", other_id)
                        cur.execute("UPDATE TaskTimeLog SET ended_at=GETDATE(),seconds=DATEDIFF(SECOND,started_at,GETDATE()) WHERE task_id=? AND ended_at IS NULL", other_id)
                    else:
                        cur.execute("UPDATE Tasks SET status='paused',active_actor_id=NULL WHERE id=?", other_id)
                    auto_paused.append(other_id)
                cur.execute("UPDATE Tasks SET status='doing',started_at=GETDATE(),active_actor_id=? WHERE id=?", actor_id, tid)
                # Open a fresh per-person work session. This (not Tasks.work_seconds,
                # which stays a simple combined total for the quick at-a-glance
                # badges) is the real source of truth for "who worked how much" -
                # see api_report_contributions / the loadAll() contributions query.
                cur.execute("INSERT INTO TaskTimeLog(task_id,user_id,started_at) VALUES(?,?,GETDATE())", tid, actor_id)
            elif action == 'pause':
                # Explicit "pause my own work" - stays assigned to this person
                # (unlike back_admin, which gives the task away). Banks
                # elapsed time so resuming later adds to it correctly instead
                # of restarting from zero. Clearing active_actor_id means
                # nobody is "occupying" this task's clock anymore, so it
                # correctly stops being a candidate for anyone's auto-pause.
                if started_at is not None:
                    cur.execute("UPDATE Tasks SET status='paused',"
                                "work_seconds=ISNULL(work_seconds,0)+DATEDIFF(SECOND,started_at,GETDATE()),started_at=NULL,active_actor_id=NULL WHERE id=?", tid)
                    cur.execute("UPDATE TaskTimeLog SET ended_at=GETDATE(),seconds=DATEDIFF(SECOND,started_at,GETDATE()) WHERE task_id=? AND ended_at IS NULL", tid)
                else:
                    cur.execute("UPDATE Tasks SET status='paused',active_actor_id=NULL WHERE id=?", tid)
            elif action == 'forward':
                # Submit for approval: add elapsed time since started_at into work_seconds,
                # and optionally persist "how it was done" + "how it was tested" text
                # in the same atomic update.
                set_parts = ["status='pending_approval'", "submitted_at=GETDATE()", "active_actor_id=NULL"]
                params = []
                if started_at is not None:
                    set_parts.append("work_seconds=ISNULL(work_seconds,0)+DATEDIFF(SECOND,started_at,GETDATE())")
                    set_parts.append("started_at=NULL")
                if solution_text is not None:
                    set_parts.append("solution=?")
                    params.append(solution_text)
                if test_notes_text is not None:
                    set_parts.append("test_notes=?")
                    params.append(test_notes_text)
                params.append(tid)
                cur.execute("UPDATE Tasks SET " + ",".join(set_parts) + " WHERE id=?", *params)
                if started_at is not None:
                    cur.execute("UPDATE TaskTimeLog SET ended_at=GETDATE(),seconds=DATEDIFF(SECOND,started_at,GETDATE()) WHERE task_id=? AND ended_at IS NULL", tid)
            elif action == 'back_admin':
                # Support returns task to admin (with or without having started,
                # or even from a paused state where time is already banked):
                # bank any elapsed time if the clock was actively running.
                if started_at is not None:
                    cur.execute("UPDATE Tasks SET status='returned',"
                                "work_seconds=ISNULL(work_seconds,0)+DATEDIFF(SECOND,started_at,GETDATE()),started_at=NULL,active_actor_id=NULL WHERE id=?", tid)
                    cur.execute("UPDATE TaskTimeLog SET ended_at=GETDATE(),seconds=DATEDIFF(SECOND,started_at,GETDATE()) WHERE task_id=? AND ended_at IS NULL", tid)
                else:
                    cur.execute("UPDATE Tasks SET status='returned',active_actor_id=NULL WHERE id=?", tid)
            elif action == 'set_work_time':
                # Correct a recorded work time that's clearly wrong - the
                # classic case being a timer left running overnight because
                # someone forgot to pause, producing a 21-hour task. Without
                # this, that bogus number would distort the "busiest staff"
                # ranking and reports forever.
                #
                # new_seconds is the corrected time for ONE specific person
                # (target_user_id) on this task. We rewrite that person's
                # TaskTimeLog history for this task into a single normalized,
                # already-closed segment of the new length, then recompute the
                # task's combined work_seconds as the sum across everyone -
                # keeping the per-person reports and the task total perfectly
                # consistent (the whole point of the v4.8 per-person system).
                #
                # Permission: admin may edit anyone's; a support user may edit
                # only their OWN contribution, and only on a task they're on.
                target_user_id = d.get('target_user_id')
                new_seconds = d.get('new_seconds')
                if target_user_id is None or new_seconds is None:
                    return jsonify({'ok': False, 'error': 'پارامتر ناقص'})
                try:
                    new_seconds = int(new_seconds)
                except Exception:
                    return jsonify({'ok': False, 'error': 'مقدار زمان نامعتبر است'})
                if new_seconds < 0:
                    return jsonify({'ok': False, 'error': 'زمان نمی‌تواند منفی باشد'})
                if not user_has_permission(flask_g.user, 'tasks.assign'):
                    # worker: only their own contribution, only if on the task
                    if str(actor_id) != str(target_user_id) or not _is_on_task(actor_id):
                        return jsonify({'ok': False, 'error': 'اجازه ویرایش این زمان را ندارید'})
                # Don't allow editing while that person's clock is actively
                # running on this task - they should pause/submit first, so we
                # aren't fighting a live segment.
                cur.execute("SELECT COUNT(*) FROM TaskTimeLog WHERE task_id=? AND user_id=? AND ended_at IS NULL", tid, target_user_id)
                openc = cur.fetchone()
                if openc and openc[0]:
                    return jsonify({'ok': False, 'error': 'برای ویرایش، ابتدا کار روی این تسک را متوقف کنید'})
                # Replace that person's segments with one normalized closed segment.
                cur.execute("DELETE FROM TaskTimeLog WHERE task_id=? AND user_id=?", tid, target_user_id)
                if new_seconds > 0:
                    cur.execute("INSERT INTO TaskTimeLog(task_id,user_id,started_at,ended_at,seconds) "
                                "VALUES(?,?,DATEADD(SECOND,-?,GETDATE()),GETDATE(),?)", tid, target_user_id, new_seconds, new_seconds)
                # Recompute the task's combined total from all contributors.
                cur.execute("UPDATE Tasks SET work_seconds=ISNULL((SELECT SUM(ISNULL(seconds,0)) FROM TaskTimeLog WHERE task_id=? AND ended_at IS NOT NULL),0) WHERE id=?", tid, tid)
            elif action == 'approve':
                cur.execute("UPDATE Tasks SET status='done',completed_at=GETDATE() WHERE id=?", tid)
            elif action == 'send_back':
                # Admin bounces pending-approval back to support: do NOT auto-resume
                # the clock. Support must explicitly click "start" again, exactly
                # like a fresh assignment. work_seconds already banked from the
                # previous round stays as-is; the next "forward" will add to it.
                cur.execute("UPDATE Tasks SET status='assigned' WHERE id=?", tid)
            elif action == 'add_helper':
                if not helper_id:
                    return jsonify({'ok': False, 'error': 'پشتیبان مورد نظر انتخاب نشده است'})
                if staff_id is not None and str(staff_id) == str(helper_id):
                    return jsonify({'ok': False, 'error': 'این فرد همان پشتیبان اصلی تسک است'})
                if project_team_id:
                    cur.execute("""SELECT 1 FROM ProjectTeams pt JOIN TeamMembers tm
                        ON tm.team_id=pt.team_id WHERE pt.id=? AND tm.user_id=?
                        AND pt.is_active=1 AND tm.is_active=1""",
                                project_team_id, helper_id)
                    if not cur.fetchone():
                        return jsonify({'ok': False, 'error': 'همکار انتخاب‌شده عضو تیم این تسک نیست'})
                cur.execute("IF NOT EXISTS(SELECT 1 FROM TaskAssignees WHERE task_id=? AND user_id=?) "
                            "INSERT INTO TaskAssignees(task_id,user_id) VALUES(?,?)", tid, helper_id, tid, helper_id)
            elif action == 'remove_helper':
                if not helper_id:
                    return jsonify({'ok': False, 'error': 'پشتیبان مورد نظر انتخاب نشده است'})
                cur.execute("DELETE FROM TaskAssignees WHERE task_id=? AND user_id=?", tid, helper_id)
            else:
                return jsonify({'ok': False, 'error': 'عملیات ناشناخته'})
            c.commit()
            # Post-commit: fetch fresh title + involved people for notifications.
            cur.execute("SELECT title,staff_id,created_by FROM Tasks WHERE id=?", tid)
            _trow = cur.fetchone()
        # Fire notifications outside the DB lock (each _notify takes the lock).
        if _trow:
            _ttitle = (_trow[0] or '')[:40]
            _staff = _trow[1]
            if action == 'assign' and new_staff_id:
                _notify(new_staff_id, 'assigned', 'تسک جدید به شما واگذار شد: ' + _ttitle, tid)
            elif action == 'send_back' and _staff:
                _notify(_staff, 'returned', 'تسک شما برای اصلاح برگشت خورد: ' + _ttitle, tid)
            elif action == 'approve' and _staff:
                _notify(_staff, 'approved', 'تسک شما تایید شد: ' + _ttitle, tid)
            elif action == 'forward':
                # notify admins/planners that something awaits approval
                try:
                    with _db_lock:
                        c2 = get_conn(); cur2 = c2.cursor()
                        cur2.execute("SELECT id FROM Users WHERE role IN ('admin','planner','manager') AND is_active=1")
                        _admins = [r[0] for r in cur2.fetchall()]
                        # R15/R16: the lead of the group whoever did the work belongs to.
                        if _staff:
                            cur2.execute("""SELECT wg.lead_id FROM WorkGroupMembers gm
                                JOIN WorkGroups wg ON wg.id=gm.group_id AND wg.is_active=1
                                JOIN Users u ON u.id=wg.lead_id
                                WHERE gm.user_id=? AND u.is_active=1 AND u.role='lead'""", _staff)
                            _admins += [r[0] for r in cur2.fetchall() if r[0] not in _admins]
                    for _aid in _admins:
                        _notify(_aid, 'pending', 'تسک در انتظار تایید: ' + _ttitle, tid)
                except Exception:
                    pass
        try:
            _audit('task_' + action, 'تسک #%s' % tid)
        except Exception:
            pass
        return jsonify({'ok': True, 'auto_paused': auto_paused})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@flask_app.route('/api/export', methods=['POST'])
@require_auth
def api_export():
    try:
        data = request.get_json()
        etype = data.get('etype', 'excel')
        rows = data.get('rows', [])
        ext = '.xlsx' if etype == 'excel' else '.pdf'
        fname = 'TaskHubReport' + ext

        tmp_dir = tempfile.gettempdir()
        path = os.path.join(tmp_dir, f'taskhub_export_{os.getpid()}_{int(time.time())}{ext}')

        if etype == 'excel':
            export_excel(rows, path)
        else:
            export_pdf(rows, path)

        # Normal HTTP download - works the same whether this is the native
        # desktop window or a remote user's browser over the LAN.
        return send_file(path, as_attachment=True, download_name=fname)
    except Exception as e:
        return jsonify({'ok': False, 'error': traceback.format_exc()})

@flask_app.route('/api/template', methods=['POST'])
@require_auth
def api_template():
    try:
        tmp_dir = tempfile.gettempdir()
        path = os.path.join(tmp_dir, f'taskhub_template_{os.getpid()}_{int(time.time())}.xlsx')
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            cur.execute("SELECT id,name FROM Cities ORDER BY name")
            cities = [{'id':r[0],'name':r[1]} for r in cur.fetchall()]
            cur.execute("SELECT p.id,p.name,c.name as cname FROM Projects p JOIN Cities c ON c.id=p.city_id ORDER BY c.name,p.name")
            projects = [{'id':r[0],'name':r[1],'cname':r[2]} for r in cur.fetchall()]
            cur.execute("SELECT id,display_name FROM Users WHERE role='employer' ORDER BY display_name")
            contacts = [{'id':r[0],'full_name':r[1]} for r in cur.fetchall()]
            cur.execute("SELECT id,display_name FROM Users WHERE role IN ('support','lead','manager') ORDER BY display_name")
            staff = [{'id':r[0],'name':r[1]} for r in cur.fetchall()]
            cur.execute("SELECT id,name FROM TaskCategories ORDER BY name")
            cats = [{'id':r[0],'name':r[1]} for r in cur.fetchall()]
        export_template(path, cities, projects, contacts, staff, cats)
        return send_file(path, as_attachment=True, download_name='TaskHubTasks_Template.xlsx')
    except Exception as e:
        return jsonify({'ok': False, 'error': traceback.format_exc()})

@flask_app.route('/api/import', methods=['POST'])
@require_auth
def api_import():
    try:
        # File comes from a normal HTML <input type="file"> upload now,
        # instead of a native open-dialog reading a path on the server's own
        # disk (which made no sense for a remote browser user - their file
        # lives on their own machine, not the server's).
        if 'file' not in request.files:
            return jsonify({'ok': False, 'error': 'فایلی ارسال نشده است'})
        upload = request.files['file']
        tmp_dir = tempfile.gettempdir()
        path = os.path.join(tmp_dir, f'taskhub_import_{os.getpid()}_{int(time.time())}.xlsx')
        upload.save(path)
        tasks = import_excel(path)
        if not tasks:
            return jsonify({'ok': False, 'error': 'هیچ تسکی در فایل یافت نشد'})

        # Resolve names to IDs and insert
        inserted = 0
        errors = []
        with _db_lock:
            c = get_conn(); cur = c.cursor()
            # Build lookup maps
            cur.execute("SELECT id,name FROM Cities")
            city_map = {r[1]: r[0] for r in cur.fetchall()}
            cur.execute("SELECT p.id,p.name,c.name FROM Projects p JOIN Cities c ON c.id=p.city_id")
            proj_map = {}
            for r in cur.fetchall():
                proj_map[r[1]] = r[0]
                proj_map[f"{r[1]} ({r[2]})"] = r[0]
            cur.execute("SELECT id,display_name FROM Users WHERE role='employer'")
            cont_map = {r[1]: r[0] for r in cur.fetchall()}
            cur.execute("SELECT id,display_name FROM Users WHERE role IN ('support','lead','manager')")
            staff_map = {r[1]: r[0] for r in cur.fetchall()}
            cur.execute("SELECT id,name FROM TaskCategories")
            cat_map = {r[1]: r[0] for r in cur.fetchall()}
            # R16: importing can be granted to any role now, so it stays inside
            # the importer's teams and, for a group with projects, those projects.
            actor = flask_g.user
            actor_teams = actor_projects = None
            if not has_company_scope(actor):
                cur.execute("SELECT team_id FROM TeamMembers WHERE user_id=? AND is_active=1", actor['id'])
                actor_teams = {int(r[0]) for r in cur.fetchall()}
                actor_projects = group_project_ids(cur, actor['id'])

            for t in tasks:
                pid = proj_map.get(t['proj_name'])
                if not pid:
                    errors.append(f"پروژه «{t['proj_name']}» برای تسک «{t['title']}» یافت نشد")
                    continue
                if actor_projects and pid not in actor_projects:
                    errors.append(f"پروژه «{t['proj_name']}» جزو پروژه‌های گروه شما نیست")
                    continue
                cat_id = cat_map.get(t['cat_name'])
                cont_id = cont_map.get(t['cont_name'])
                staff_id = staff_map.get(t['staff_name'])
                cur.execute("""SELECT pt.id,pt.team_id FROM ProjectTeams pt
                    WHERE pt.project_id=? AND pt.is_active=1
                    ORDER BY pt.is_primary DESC,pt.id""", pid)
                project_teams = [(int(r[0]), int(r[1])) for r in cur.fetchall()]
                if actor_teams is not None:
                    project_teams = [x for x in project_teams if x[1] in actor_teams]
                    if not project_teams:
                        errors.append(f"پروژه «{t['proj_name']}» در محدوده تیم‌های شما نیست")
                        continue
                if staff_id:
                    staff_teams = [x for x in project_teams if cur.execute(
                        """SELECT 1 FROM TeamMembers WHERE team_id=? AND user_id=?
                            AND is_active=1""", x[1], staff_id
                    ).fetchone()]
                    if len(staff_teams) == 1:
                        project_teams = staff_teams
                if len(project_teams) != 1:
                    errors.append(
                        f"برای تسک «{t['title']}» روی پروژه «{t['proj_name']}» "
                        "باید دقیقاً یک جریان کاری تیمی قابل تشخیص باشد"
                    )
                    continue
                project_team_id = project_teams[0][0]
                final_status = t['status']
                # Same rule as creating a single task by hand: picking a
                # پشتیبان means "assign this now", skipping the triage queue.
                # Conversely 'assigned' with no resolvable staff name is an
                # inconsistent state (assigned-to-nobody) - fall back safely.
                if staff_id and final_status == 'registered':
                    final_status = 'assigned'
                elif final_status == 'assigned' and not staff_id:
                    final_status = 'registered'
                    errors.append(f"تسک «{t['title']}» چون پشتیبان «{t['staff_name']}» یافت نشد، به‌صورت «ثبت شده» وارد شد")
                cur.execute(
                    """INSERT INTO Tasks(title,type,status,category_id,project_id,
                        contact_id,staff_id,date_recv,date_delivery,description,
                        solution,project_team_id,progress_weight,created_by)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    t['title'], t['type'], final_status, cat_id, pid, cont_id, staff_id,
                    t['date_recv'] or None, t['date_delivery'] or None,
                    t['description'] or None, t['solution'] or None,
                    project_team_id, 1, flask_g.user['id'])
                inserted += 1
            c.commit()

        msg = f'{inserted} تسک وارد شد'
        if errors:
            msg += f' — {len(errors)} خطا'
        return jsonify({'ok': True, 'inserted': inserted, 'errors': errors, 'message': msg})
    except Exception as e:
        return jsonify({'ok': False, 'error': traceback.format_exc()})

@flask_app.route('/api/winaction', methods=['POST'])
def api_winaction():
    try:
        # Window controls only make sense for the desktop (pywebview) shell
        # on the SAME machine. Reject remote callers so nobody on the LAN can
        # minimize/close the server's window out from under everyone.
        if request.remote_addr not in ('127.0.0.1', '::1', 'localhost'):
            return jsonify({'ok': False, 'error': 'فقط از خود دستگاه سرور مجاز است'})
        action = request.get_json().get('action', '')
        if action == 'minimize' and _window:
            _window.minimize()
        elif action == 'maximize' and _window:
            _window.toggle_fullscreen()
        elif action == 'close' and _window:
            import logging
            _hide_to_tray(logging.getLogger('taskhub'))
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

# ── Export Excel ──────────────────────────────────────────────────────────────
def _fa(text):
    """Reshape Persian text so PDF renders connected letters correctly."""
    if not text:
        return ''
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(str(text)))
    except Exception:
        return str(text)

def _fmt_dur(sec):
    """Human-friendly Persian duration from seconds (day/hour/minute)."""
    try:
        sec = int(sec or 0)
    except Exception:
        sec = 0
    if sec <= 0:
        return '—'
    if sec < 60:
        return '%d ثانیه' % sec
    m = sec // 60
    if m < 60:
        return '%d دقیقه' % m
    h, rm = m // 60, m % 60
    if h < 24:
        return ('%d ساعت' % h) + ((' و %d دقیقه' % rm) if rm else '')
    d, rh = h // 24, h % 24
    return ('%d روز' % d) + ((' و %d ساعت' % rh) if rh else '')

def export_excel(rows, path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    TF = {'bug':'رفع باگ','dev':'توسعه','devminor':'توسعه جزئی'}
    SF = STATUS_LABELS
    wb = Workbook(); ws = wb.active
    ws.title = "گزارش تسک‌ها"; ws.sheet_view.rightToLeft = True

    headers = ['ردیف','عنوان','نوع','وضعیت','دسته','پروژه','شهر','درخواست‌کننده','پشتیبان','زمان انجام','تاریخ تأیید تسک','موعد نهایی تحویل','توضیحات','نحوه انجام','توضیحات تست']
    # Light header for printing - white bg, dark blue text, bold
    hf = PatternFill("solid", fgColor="DCE6F5")
    hfont = Font(bold=True, color="1F3864", size=11, name="Tahoma")
    thin = Side(style="thin", color="B4C6E7")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for ci, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=ci, value=h)
        cell.fill = hf; cell.font = hfont
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border
    ws.row_dimensions[1].height = 30

    import datetime as _dt
    af = PatternFill("solid", fgColor="F5F8FC")
    body_font = Font(name="Tahoma", size=10, color="222222")
    for ri, t in enumerate(rows, 2):
        # report_seconds, when present, is the specific person's own
        # contributed time (set by runRep() when the report is filtered to
        # one support person) - takes priority over the task's combined
        # total so a shared task correctly shows each contributor's own
        # portion, not the same full number for everyone who touched it.
        if t.get('report_seconds') is not None:
            wsec = t.get('report_seconds') or 0
        else:
            wsec = t.get('work_seconds') or 0
            if t.get('status') == 'doing' and t.get('started_at'):
                try:
                    st = t.get('started_at')
                    if not isinstance(st, _dt.datetime):
                        st = _dt.datetime.fromisoformat(str(st).replace(' ', 'T').split('.')[0])
                    wsec += max(0, (_dt.datetime.now() - st).total_seconds())
                except Exception:
                    pass
        wtxt = _fmt_dur(wsec) if t.get('status') in WORK_TIME_STATUSES else ''
        row_data = [ri-1, t.get('title',''), TF.get(t.get('type',''),''), SF.get(t.get('status',''),''),
            t.get('cat_name',''), t.get('pname',''), t.get('cname',''), t.get('cont_name',''),
            t.get('staff_name',''), wtxt, t.get('report_completed_date',''), t.get('date_delivery',''),
            t.get('description',''), t.get('solution',''), t.get('test_notes','')]
        for ci, v in enumerate(row_data, 1):
            cell = ws.cell(row=ri, column=ci, value=v or '')
            cell.alignment = Alignment(horizontal="right", vertical="center", wrap_text=True)
            cell.font = body_font
            cell.border = border
            if ri % 2 == 0: cell.fill = af
        ws.row_dimensions[ri].height = 24
    for i, w in enumerate([6,30,12,14,14,18,12,16,16,14,14,14,40,40,40], 1):
        ws.column_dimensions[ws.cell(row=1,column=i).column_letter].width = w
    # Freeze header + enable print fit
    ws.freeze_panes = "A2"
    ws.print_options.horizontalCentered = True
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    wb.save(path)

# ── Export PDF (Persian-correct) ──────────────────────────────────────────────
def export_pdf(rows, path):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER
    TF = {'bug':'رفع باگ','dev':'توسعه','devminor':'توسعه جزئی'}
    SF = STATUS_LABELS
    fn = fa_font.register()
    cs = ParagraphStyle('c', fontName=fn, fontSize=8, alignment=TA_RIGHT)
    hs = ParagraphStyle('h', fontName=fn, fontSize=9, alignment=TA_CENTER, textColor=colors.HexColor('#1F3864'))
    ts = ParagraphStyle('t', fontName=fn, fontSize=16, alignment=TA_CENTER, textColor=colors.HexColor('#1F3864'), spaceAfter=10)
    ss = ParagraphStyle('s', fontName=fn, fontSize=10, alignment=TA_CENTER, textColor=colors.gray, spaceAfter=16)
    def P(t): return Paragraph(_fa(t) if t else '—', cs)
    def H(t): return Paragraph(_fa(t), hs)
    doc = SimpleDocTemplate(path, pagesize=landscape(A4), rightMargin=1.2*cm, leftMargin=1.2*cm, topMargin=1.8*cm, bottomMargin=1.5*cm)
    hdrs = ['ردیف','عنوان','نوع','وضعیت','پروژه','شهر','درخواست‌کننده','پشتیبان','زمان انجام','تاریخ تأیید تسک','توضیحات','نحوه انجام','توضیحات تست']
    td = [[H(h) for h in reversed(hdrs)]]  # RTL: reverse columns
    import datetime as _dt
    for i, t in enumerate(rows, 1):
        desc = (t.get('description','') or '')
        # work time: prefer the frontend-computed per-person contribution
        # (report_seconds) when present, same priority as export_excel above.
        if t.get('report_seconds') is not None:
            wsec = t.get('report_seconds') or 0
        else:
            wsec = t.get('work_seconds') or 0
            if t.get('status') == 'doing' and t.get('started_at'):
                try:
                    st = t.get('started_at')
                    if not isinstance(st, _dt.datetime):
                        st = _dt.datetime.fromisoformat(str(st).replace(' ', 'T').split('.')[0])
                    wsec += max(0, (_dt.datetime.now() - st).total_seconds())
                except Exception:
                    pass
        wtxt = _fmt_dur(wsec) if t.get('status') in WORK_TIME_STATUSES else '—'
        sol = (t.get('solution','') or '')
        tst = (t.get('test_notes','') or '')
        row = [P(i), P(t.get('title','')), P(TF.get(t.get('type',''),'')), P(SF.get(t.get('status',''),'')),
            P(t.get('pname','')), P(t.get('cname','')), P(t.get('cont_name','')), P(t.get('staff_name','')),
            P(wtxt), P(t.get('report_completed_date','')),
            P(desc[:60] + ('...' if len(desc)>60 else '')),
            P(sol[:60] + ('...' if len(sol)>60 else '') if sol else '—'),
            P(tst[:60] + ('...' if len(tst)>60 else '') if tst else '—')]
        td.append(list(reversed(row)))  # RTL: reverse columns
    cw = list(reversed([1.2*cm,3.2*cm,1.5*cm,1.8*cm,2.2*cm,1.7*cm,2.1*cm,2.1*cm,2.1*cm,1.8*cm,2.6*cm,2.6*cm,2.6*cm]))
    tbl = Table(td, colWidths=cw, repeatRows=1)
    tbl.setStyle(TableStyle([
        # Light header for printing
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DCE6F5')),
        ('TEXTCOLOR',(0,0),(-1,0),colors.HexColor('#1F3864')),
        ('LINEBELOW',(0,0),(-1,0),1.2,colors.HexColor('#1F3864')),
        ('FONTNAME',(0,0),(-1,-1),fn), ('FONTSIZE',(0,0),(-1,-1),8),
        ('ALIGN',(0,0),(-1,-1),'CENTER'), ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F5F8FC')]),
        ('GRID',(0,0),(-1,-1),0.5,colors.HexColor('#B4C6E7')),
        ('TOPPADDING',(0,0),(-1,-1),5), ('BOTTOMPADDING',(0,0),(-1,-1),5),
    ]))
    doc.build([Paragraph(_fa('تسک هاب'),ts),
               Paragraph(_fa(f'گزارش تسک‌ها — تعداد: {len(rows)}'),ss),
               Spacer(1,0.3*cm), tbl])

# ── Time Report Export (attendance/leave/mission) ──────────────────────────
LEAVE_TYPE_LABELS = {'hourly': 'ساعتی', 'daily': 'تمام روز'}
LEAVE_STATUS_LABELS = {'pending': 'در انتظار تایید', 'approved': 'تایید شده', 'rejected': 'رد شده'}

def export_time_report_excel(data, path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    import datetime as _dt
    wb = Workbook()
    hf = PatternFill("solid", fgColor="DCE6F5")
    hfont = Font(bold=True, color="1F3864", size=11, name="Tahoma")
    thin = Side(style="thin", color="B4C6E7")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    af = PatternFill("solid", fgColor="F5F8FC")
    body_font = Font(name="Tahoma", size=10, color="222222")

    def style_header_row(ws, headers):
        for ci, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=ci, value=h)
            cell.fill = hf; cell.font = hfont
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = border
        ws.row_dimensions[1].height = 28
        ws.sheet_view.rightToLeft = True
        ws.freeze_panes = "A2"

    def style_body_row(ws, ri, values):
        for ci, v in enumerate(values, 1):
            cell = ws.cell(row=ri, column=ci, value=v if v not in (None, '') else '—')
            cell.alignment = Alignment(horizontal="right", vertical="center", wrap_text=True)
            cell.font = body_font; cell.border = border
            if ri % 2 == 0: cell.fill = af

    # Summary sheet
    ws0 = wb.active; ws0.title = "خلاصه"
    ws0.sheet_view.rightToLeft = True
    t = data.get('totals', {})
    summary_rows = [
        ('کارمند', data.get('staff_name', '—')),
        ('از تاریخ', data.get('from_jalali', '—')),
        ('تا تاریخ', data.get('to_jalali', '—')),
        ('مجموع ساعت کاری خالص', _fmt_dur(t.get('work_seconds', 0))),
        ('مجموع ساعت مرخصی (ساعتی، تایید‌شده)', _fmt_dur(t.get('leave_seconds', 0))),
        ('تعداد مرخصی تمام‌روز (تایید‌شده)', t.get('daily_leave_count', 0)),
        ('تعداد روزهای ماموریت', t.get('mission_days', 0)),
    ]
    for ri, (k, v) in enumerate(summary_rows, 1):
        c1 = ws0.cell(row=ri, column=1, value=k); c1.font = hfont; c1.alignment = Alignment(horizontal="right")
        c2 = ws0.cell(row=ri, column=2, value=v); c2.font = body_font; c2.alignment = Alignment(horizontal="right")
    ws0.column_dimensions['A'].width = 34; ws0.column_dimensions['B'].width = 26

    # Attendance sheet
    ws1 = wb.create_sheet("حضور و غیاب")
    style_header_row(ws1, ['تاریخ', 'ساعت ورود', 'ساعت خروج', 'مدت حضور'])
    for ri, a in enumerate(data.get('attendance', []), 2):
        ci_s = a['check_in'].strftime('%H:%M') if isinstance(a.get('check_in'), _dt.datetime) else (str(a.get('check_in') or '')[11:16] or '—')
        co_s = a['check_out'].strftime('%H:%M') if isinstance(a.get('check_out'), _dt.datetime) else (str(a.get('check_out') or '')[11:16] or 'هنوز باز است')
        dur = '—'
        if a.get('check_in') and a.get('check_out'):
            ci_dt = a['check_in'] if isinstance(a['check_in'], _dt.datetime) else _dt.datetime.fromisoformat(str(a['check_in']))
            co_dt = a['check_out'] if isinstance(a['check_out'], _dt.datetime) else _dt.datetime.fromisoformat(str(a['check_out']))
            dur = _fmt_dur(max(0, (co_dt-ci_dt).total_seconds()))
        style_body_row(ws1, ri, [a.get('work_date'), ci_s, co_s, dur])
    for i, w in enumerate([14, 14, 16, 16], 1): ws1.column_dimensions[ws1.cell(row=1,column=i).column_letter].width = w

    # Leave sheet
    ws2 = wb.create_sheet("مرخصی")
    style_header_row(ws2, ['تاریخ', 'نوع', 'از ساعت', 'تا ساعت', 'وضعیت', 'دلیل'])
    for ri, lv in enumerate(data.get('leaves', []), 2):
        lv_date_disp = lv.get('leave_date')
        if lv.get('leave_type')=='daily' and lv.get('end_date') and lv.get('end_date')!=lv.get('leave_date'):
            lv_date_disp = lv.get('leave_date')+' تا '+lv.get('end_date')
        style_body_row(ws2, ri, [lv_date_disp, LEAVE_TYPE_LABELS.get(lv.get('leave_type'), lv.get('leave_type')),
            lv.get('start_time') or '—', lv.get('end_time') or '—', LEAVE_STATUS_LABELS.get(lv.get('status'), lv.get('status')), lv.get('reason') or '—'])
    for i, w in enumerate([14, 12, 12, 12, 16, 34], 1): ws2.column_dimensions[ws2.cell(row=1,column=i).column_letter].width = w

    # Mission sheet
    ws3 = wb.create_sheet("ماموریت")
    style_header_row(ws3, ['از تاریخ', 'تا تاریخ', 'شهر', 'پروژه', 'توضیح'])
    for ri, m in enumerate(data.get('missions', []), 2):
        style_body_row(ws3, ri, [m.get('start_jalali'), m.get('end_jalali'), m.get('city_name'), m.get('project_name') or '—', m.get('note') or '—'])
    for i, w in enumerate([14, 14, 16, 18, 34], 1): ws3.column_dimensions[ws3.cell(row=1,column=i).column_letter].width = w

    wb.save(path)

def export_time_report_pdf(data, path):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER
    import datetime as _dt
    fn = fa_font.register()
    cs = ParagraphStyle('c', fontName=fn, fontSize=9, alignment=TA_RIGHT)
    hs = ParagraphStyle('h', fontName=fn, fontSize=9, alignment=TA_CENTER, textColor=colors.HexColor('#1F3864'))
    ts = ParagraphStyle('t', fontName=fn, fontSize=16, alignment=TA_CENTER, textColor=colors.HexColor('#1F3864'), spaceAfter=6)
    ss = ParagraphStyle('s', fontName=fn, fontSize=10, alignment=TA_CENTER, textColor=colors.gray, spaceAfter=14)
    sh = ParagraphStyle('sh', fontName=fn, fontSize=12, alignment=TA_RIGHT, textColor=colors.HexColor('#1F3864'), spaceBefore=14, spaceAfter=8)
    def P(t): return Paragraph(_fa(t) if t not in (None,'') else '—', cs)
    def H(t): return Paragraph(_fa(t), hs)
    doc = SimpleDocTemplate(path, pagesize=landscape(A4), rightMargin=1.2*cm, leftMargin=1.2*cm, topMargin=1.6*cm, bottomMargin=1.4*cm)
    story = [Paragraph(_fa('تسک هاب'), ts),
             Paragraph(_fa('گزارش زمانی — %s (%s تا %s)' % (data.get('staff_name','—'), data.get('from_jalali','—'), data.get('to_jalali','—'))), ss)]

    t = data.get('totals', {})
    sumhdrs = ['ساعت کاری خالص', 'ساعت مرخصی', 'مرخصی تمام‌روز', 'روزهای ماموریت']
    sumrow = [_fmt_dur(t.get('work_seconds',0)), _fmt_dur(t.get('leave_seconds',0)), str(t.get('daily_leave_count',0)), str(t.get('mission_days',0))]
    sumtbl = Table([[H(h) for h in reversed(sumhdrs)], [P(v) for v in reversed(sumrow)]], colWidths=[5*cm]*4)
    sumtbl.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DCE6F5')), ('TEXTCOLOR',(0,0),(-1,0),colors.HexColor('#1F3864')),
        ('FONTNAME',(0,0),(-1,-1),fn), ('FONTSIZE',(0,0),(-1,-1),10), ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('GRID',(0,0),(-1,-1),0.5,colors.HexColor('#B4C6E7')), ('TOPPADDING',(0,0),(-1,-1),6), ('BOTTOMPADDING',(0,0),(-1,-1),6),
    ]))
    story += [sumtbl]

    def section(title, headers, rows, colw):
        story.append(Paragraph(_fa(title), sh))
        if not rows:
            story.append(Paragraph(_fa('موردی ثبت نشده'), cs)); return
        td = [[H(h) for h in reversed(headers)]]
        for r in rows: td.append([P(v) for v in reversed(r)])
        tbl = Table(td, colWidths=list(reversed(colw)), repeatRows=1)
        tbl.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DCE6F5')), ('TEXTCOLOR',(0,0),(-1,0),colors.HexColor('#1F3864')),
            ('LINEBELOW',(0,0),(-1,0),1.2,colors.HexColor('#1F3864')),
            ('FONTNAME',(0,0),(-1,-1),fn), ('FONTSIZE',(0,0),(-1,-1),8.5),
            ('ALIGN',(0,0),(-1,-1),'CENTER'), ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F5F8FC')]),
            ('GRID',(0,0),(-1,-1),0.5,colors.HexColor('#B4C6E7')),
            ('TOPPADDING',(0,0),(-1,-1),4), ('BOTTOMPADDING',(0,0),(-1,-1),4),
        ]))
        story.append(tbl)

    att_rows = []
    for a in data.get('attendance', []):
        ci_s = a['check_in'].strftime('%H:%M') if isinstance(a.get('check_in'), _dt.datetime) else (str(a.get('check_in') or '')[11:16] or '—')
        co_s = a['check_out'].strftime('%H:%M') if isinstance(a.get('check_out'), _dt.datetime) else (str(a.get('check_out') or '')[11:16] or 'باز')
        dur = '—'
        if a.get('check_in') and a.get('check_out'):
            ci_dt = a['check_in'] if isinstance(a['check_in'], _dt.datetime) else _dt.datetime.fromisoformat(str(a['check_in']))
            co_dt = a['check_out'] if isinstance(a['check_out'], _dt.datetime) else _dt.datetime.fromisoformat(str(a['check_out']))
            dur = _fmt_dur(max(0, (co_dt-ci_dt).total_seconds()))
        att_rows.append([a.get('work_date'), ci_s, co_s, dur])
    section('🟢 حضور و غیاب', ['تاریخ','ورود','خروج','مدت'], att_rows, [3*cm,2.5*cm,2.5*cm,3*cm])

    def _lv_date_disp(lv):
        if lv.get('leave_type')=='daily' and lv.get('end_date') and lv.get('end_date')!=lv.get('leave_date'):
            return lv.get('leave_date')+' تا '+lv.get('end_date')
        return lv.get('leave_date')
    lv_rows = [[_lv_date_disp(lv), LEAVE_TYPE_LABELS.get(lv.get('leave_type'),''), lv.get('start_time') or '—',
                lv.get('end_time') or '—', LEAVE_STATUS_LABELS.get(lv.get('status'),''), (lv.get('reason') or '—')[:40]]
               for lv in data.get('leaves', [])]
    section('🟡 مرخصی', ['تاریخ','نوع','از','تا','وضعیت','دلیل'], lv_rows, [2.6*cm,2.2*cm,2*cm,2*cm,3*cm,5*cm])

    ms_rows = [[m.get('start_jalali'), m.get('end_jalali'), m.get('city_name'), m.get('project_name') or '—', (m.get('note') or '—')[:40]]
               for m in data.get('missions', [])]
    section('✈ ماموریت', ['از تاریخ','تا تاریخ','شهر','پروژه','توضیح'], ms_rows, [2.6*cm,2.6*cm,3*cm,3.5*cm,5*cm])

    doc.build(story)

# ── Excel Template (for bulk import with dropdowns) ───────────────────────────
def export_template(path, cities, projects, contacts, staff, categories):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "تسک‌ها"
    ws.sheet_view.rightToLeft = True

    # Lookup sheet for dropdown sources
    lk = wb.create_sheet("لیست‌ها")
    lk.sheet_state = 'visible'

    def fill_col(col_letter, items, header):
        lk[f'{col_letter}1'] = header
        for i, name in enumerate(items, 2):
            lk[f'{col_letter}{i}'] = name

    city_names = [c['name'] for c in cities]
    proj_names = [f"{p['name']} ({p['cname']})" for p in projects]
    cont_names = [c['full_name'] for c in contacts]
    staff_names = [s['name'] for s in staff]
    cat_names = [c['name'] for c in categories]

    fill_col('A', city_names, 'شهرها')
    fill_col('B', proj_names, 'پروژه‌ها')
    fill_col('C', cont_names, 'مخاطبین')
    fill_col('D', staff_names, 'پشتیبان‌ها')
    fill_col('E', cat_names, 'دسته‌ها')

    headers = ['عنوان','نوع','وضعیت','دسته','شهر','پروژه','درخواست‌کننده','پشتیبان','تاریخ ثبت','موعد نهایی تحویل','توضیحات','نحوه انجام']
    hf = PatternFill("solid", fgColor="DCE6F5")
    hfont = Font(bold=True, color="1F3864", size=11, name="Tahoma")
    thin = Side(style="thin", color="B4C6E7")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for ci, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=ci, value=h)
        cell.fill = hf; cell.font = hfont
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border
    ws.row_dimensions[1].height = 30

    NROWS = 200

    def add_dv(col_letter, formula):
        dv = DataValidation(type="list", formula1=formula, allow_blank=True)
        dv.error = 'لطفاً از لیست انتخاب کنید'
        dv.errorTitle = 'مقدار نامعتبر'
        ws.add_data_validation(dv)
        dv.add(f'{col_letter}2:{col_letter}{NROWS}')

    # Type dropdown (fixed values)
    add_dv('B', '"رفع باگ,توسعه,توسعه جزئی"')
    # Status dropdown - only "stable" states that make sense to set directly
    # from a spreadsheet row (rejected needs a reason text, pending_approval/
    # returned are mid-workflow transients with no matching timestamps a bulk
    # import can sensibly fill in). Generated from IMPORTABLE_STATUSES so it
    # always reflects the actual current state machine.
    add_dv('C', '"' + ','.join(STATUS_LABELS[s] for s in IMPORTABLE_STATUSES) + '"')
    # Category from lookup
    if cat_names:
        add_dv('D', f"=لیست‌ها!$E$2:$E${len(cat_names)+1}")
    # City
    if city_names:
        add_dv('E', f"=لیست‌ها!$A$2:$A${len(city_names)+1}")
    # Project
    if proj_names:
        add_dv('F', f"=لیست‌ها!$B$2:$B${len(proj_names)+1}")
    # Contact
    if cont_names:
        add_dv('G', f"=لیست‌ها!$C$2:$C${len(cont_names)+1}")
    # Staff
    if staff_names:
        add_dv('H', f"=لیست‌ها!$D$2:$D${len(staff_names)+1}")

    # Column widths
    for i, w in enumerate([28,12,14,14,14,22,18,16,14,14,35,35], 1):
        ws.column_dimensions[ws.cell(row=1,column=i).column_letter].width = w

    # Style empty rows lightly
    for r in range(2, NROWS+1):
        for c in range(1, len(headers)+1):
            cell = ws.cell(row=r, column=c)
            cell.border = border
            cell.alignment = Alignment(horizontal="right", vertical="center")

    ws.freeze_panes = "A2"
    wb.save(path)

# ── Import from Excel ─────────────────────────────────────────────────────────
def import_excel(path):
    """Read template Excel and return list of task dicts to insert."""
    from openpyxl import load_workbook
    TF_REV = {'رفع باگ':'bug','توسعه':'dev','توسعه جزئی':'devminor'}
    SF_REV = {v: k for k, v in STATUS_LABELS.items()}
    wb = load_workbook(path, data_only=True)
    ws = wb['تسک‌ها'] if 'تسک‌ها' in wb.sheetnames else wb.active
    tasks = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:  # title empty = skip
            continue
        title = str(row[0]).strip() if row[0] else ''
        if not title:
            continue
        tasks.append({
            'title': title,
            'type': TF_REV.get(str(row[1]).strip() if row[1] else '', 'bug'),
            'status': SF_REV.get(str(row[2]).strip() if row[2] else '', 'registered'),
            'cat_name': str(row[3]).strip() if row[3] else '',
            'city_name': str(row[4]).strip() if row[4] else '',
            'proj_name': str(row[5]).strip() if row[5] else '',
            'cont_name': str(row[6]).strip() if row[6] else '',
            'staff_name': str(row[7]).strip() if row[7] else '',
            'date_recv': str(row[8]).strip() if row[8] else '',
            'date_delivery': str(row[9]).strip() if row[9] else '',
            'description': str(row[10]).strip() if row[10] else '',
            'solution': str(row[11]).strip() if row[11] else '',
        })
    return tasks

# Register the v7 financial/contracts API after all shared authentication and
# audit helpers exist.  Storage is beside the executable in production, so it
# is included in the same backup set and never disappears with PyInstaller's
# temporary extraction directory.
_V7_DATA_BASE = (os.path.dirname(sys.executable) if getattr(sys, 'frozen', False)
                 else os.path.dirname(os.path.abspath(__file__)))
register_v7_routes(flask_app, get_conn, _db_lock, require_auth, require_roles,
                   rows_to_list, _audit, _V7_DATA_BASE)
register_v8_routes(flask_app, get_conn, _db_lock, require_auth, require_roles,
                   rows_to_list, _audit, _V7_DATA_BASE)
register_v802_routes(flask_app, get_conn, _db_lock, require_auth, require_roles,
                     rows_to_list, _audit, _V7_DATA_BASE)
# R13 points, coins and item shop. It hooks task approval, evaluation, edit and
# deletion through after_request, so none of those handlers had to change.
register_game_routes(flask_app, get_conn, _db_lock, require_auth, rows_to_list,
                     _audit, _notify)

# ── Start Flask Thread ────────────────────────────────────────────────────────
def _resolve_client_host():
    """Return a browser-safe host. 0.0.0.0 is only valid for binding.

    For HTTPS the host must also match the certificate SAN. Administrators can
    force the exact value with TASKHUB_PUBLIC_HOST (recommended for production).
    """
    if PUBLIC_HOST:
        return PUBLIC_HOST
    try:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            # No packets are sent; connect only asks Windows which local
            # interface would be used for the LAN.
            sock.connect(('8.8.8.8', 80))
            return sock.getsockname()[0]
    except Exception:
        return '127.0.0.1'


def _build_ssl_context():
    if not SSL_ENABLED:
        return None
    import ssl
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile=SSL_CERT_FILE, keyfile=SSL_KEY_FILE)
    return context


def start_flask():
    import logging

    werkzeug_log = logging.getLogger('werkzeug')
    werkzeug_log.setLevel(logging.ERROR)
    app_log = logging.getLogger('taskhub')
    try:
        if REVERSE_PROXY or SERVER_ENGINE == 'waitress':
            if SSL_ENABLED:
                raise RuntimeError('Waitress does not terminate TLS; use IIS TLS and remove app SSL files.')
            from waitress import serve
            # In reverse-proxy mode the application port is deliberately local
            # only. This prevents accidental direct exposure of Waitress when a
            # broad TASKHUB_HOST value remains in an older configuration file.
            bind_host = '127.0.0.1' if REVERSE_PROXY else HOST
            app_log.info(
                'Starting production server: engine=waitress bind=%s:%s external=%s://%s',
                bind_host, PORT, URL_SCHEME, PUBLIC_HOST or '-'
            )
            serve(flask_app, host=bind_host, port=PORT, threads=16,
                  channel_timeout=90, cleanup_interval=30, backlog=100)
            return

        from werkzeug.serving import make_server
        ssl_context = _build_ssl_context()
        app_log.info(
            'Starting web server: scheme=%s bind=%s:%s cert=%s key=%s',
            INTERNAL_SCHEME, HOST, PORT, SSL_CERT_FILE or '-', SSL_KEY_FILE or '-'
        )
        server = make_server(
            HOST, PORT, flask_app, threaded=True, ssl_context=ssl_context
        )
        app_log.info('Web server listening on %s://%s:%s', INTERNAL_SCHEME, HOST, PORT)
        server.serve_forever()
    except Exception:
        app_log.exception('Web server failed to start')
        raise

# ── pywebview Window ──────────────────────────────────────────────────────────
_window = None
_tray_icon = None

# ── Main ──────────────────────────────────────────────────────────────────────
def wait_flask():
    import urllib.request, time
    for _ in range(50):
        try:
            health_host = '127.0.0.1'
            urllib.request.urlopen(f'{INTERNAL_SCHEME}://{health_host}:{PORT}/api/ping', timeout=0.3,
                                   context=(__import__('ssl')._create_unverified_context() if SSL_ENABLED else None))
            return True
        except:
            time.sleep(0.1)
    return False

# ── System tray (minimize-to-tray on close) ────────────────────────────────
def _build_tray_image(icon_path):
    from PIL import Image, ImageDraw
    ico_path = get_icon_path()
    if ico_path:
        try:
            return Image.open(ico_path).convert('RGBA')
        except Exception:
            pass
    try:
        if icon_path and os.path.exists(icon_path):
            return Image.open(icon_path).convert('RGBA')
    except Exception:
        pass
    img = Image.new('RGBA', (64, 64), (10, 10, 26, 255))
    d = ImageDraw.Draw(img)
    d.ellipse((6, 6, 58, 58), fill=(246, 169, 68, 255))
    return img

def _force_exit_later(log, delay=1.5):
    """Hard-kill watchdog: guarantees the process actually dies even if the
    normal GUI/Flask shutdown hangs (the root cause of the old 'stuck in
    Task Manager' bug). Runs in its own thread so a hung destroy() call
    elsewhere can't block it."""
    import time
    def _k():
        time.sleep(delay)
        try:
            log.info('Watchdog: forcing process exit.')
        except Exception:
            pass
        os._exit(0)
    threading.Thread(target=_k, daemon=True).start()

def _hide_to_tray(log):
    global _tray_icon
    try:
        if _tray_icon is not None:
            if _window:
                _window.hide()
            _tray_icon.visible = True
            log.info('Window hidden to tray.')
        else:
            # No tray available (pystray missing/failed) - fall back to a real,
            # but still guaranteed-clean, close.
            log.info('Tray unavailable - closing for real.')
            _force_exit_later(log, 1.5)
            try:
                if _window:
                    _window.destroy()
            except Exception:
                pass
            os._exit(0)
    except Exception as e:
        log.error(f'_hide_to_tray failed: {e}')

def _tray_open(icon_, item, log):
    try:
        if _window:
            _window.show()
            _window.restore()
        if _tray_icon is not None:
            _tray_icon.visible = False
    except Exception as e:
        log.error(f'_tray_open failed: {e}')

def _tray_exit(icon_, item, log):
    log.info('Exit requested from tray.')
    _force_exit_later(log, 1.5)  # guaranteed kill no matter what happens below
    try:
        if _tray_icon is not None:
            _tray_icon.visible = False
            _tray_icon.stop()
    except Exception:
        pass
    try:
        if _window:
            _window.destroy()
    except Exception:
        pass
    os._exit(0)

def _setup_tray(icon_path, log):
    global _tray_icon
    try:
        import pystray
        image = _build_tray_image(icon_path)
        menu = pystray.Menu(
            pystray.MenuItem('باز کردن برنامه', lambda icon_, item: _tray_open(icon_, item, log), default=True),
            pystray.MenuItem('خروج کامل از برنامه', lambda icon_, item: _tray_exit(icon_, item, log)),
        )
        _tray_icon = pystray.Icon('TaskHub', image, 'تسک هاب', menu)
        _tray_icon.visible = False  # only shown once the window is hidden/closed
        threading.Thread(target=_tray_icon.run, daemon=True).start()
        log.info('Tray icon ready.')
    except Exception as e:
        log.error(f'Tray setup failed (will fall back to normal close): {e}')
        _tray_icon = None

def _on_window_closing(log):
    """Fires on ANY close attempt (custom button via destroy(), Alt+F4, etc).
    Returning False cancels the actual close so we can hide to tray instead."""
    _hide_to_tray(log)
    return False

# ── LAN startup hardening ───────────────────────────────────────────────────
_single_instance_handle = None


def _listener_pids(port):
    """Return Windows PIDs currently listening on the configured TCP port."""
    if sys.platform != 'win32':
        return []
    try:
        import subprocess
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        result = subprocess.run(
            ['netstat', '-ano', '-p', 'tcp'], capture_output=True, text=True,
            timeout=15, creationflags=flags
        )
        pids = set()
        suffix = ':%s' % int(port)
        for raw in (result.stdout or '').splitlines():
            line = raw.strip()
            parts = line.split()
            if len(parts) < 5 or parts[0].upper() != 'TCP':
                continue
            if parts[3].upper() != 'LISTENING' or not parts[1].endswith(suffix):
                continue
            try:
                pids.add(int(parts[4]))
            except Exception:
                pass
        return sorted(pids)
    except Exception:
        return []


def _process_name(pid):
    if sys.platform != 'win32':
        return ''
    try:
        import subprocess
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        result = subprocess.run(
            ['tasklist', '/FI', 'PID eq %s' % int(pid), '/FO', 'CSV', '/NH'],
            capture_output=True, text=True, timeout=10, creationflags=flags
        )
        line = (result.stdout or '').strip().splitlines()
        if not line:
            return ''
        import csv, io
        row = next(csv.reader(io.StringIO(line[0])))
        return row[0].strip() if row else ''
    except Exception:
        return ''


def _show_startup_error(message):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, str(message), 'TaskHub', 0x10)
    except Exception:
        pass


def _replace_old_listener(log):
    """Stop an older TaskHub that owns the port; never kill unrelated apps."""
    if sys.platform != 'win32':
        return True
    import time, subprocess
    current_pid = os.getpid()
    pids = [pid for pid in _listener_pids(PORT) if pid != current_pid]
    if not pids:
        return True

    unrelated = []
    for pid in pids:
        name = _process_name(pid)
        if name.lower().startswith('taskhub'):
            log.warning('Stopping old TaskHub listener: pid=%s name=%s', pid, name)
            flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)],
                           capture_output=True, text=True, timeout=20,
                           creationflags=flags)
        else:
            unrelated.append((pid, name or 'unknown'))

    for _ in range(40):
        if not [pid for pid in _listener_pids(PORT) if pid != current_pid]:
            log.info('TCP port %s is free.', PORT)
            return True
        time.sleep(0.25)

    remaining = [(pid, _process_name(pid) or 'unknown')
                 for pid in _listener_pids(PORT) if pid != current_pid]
    details = ', '.join('%s (PID %s)' % (name, pid) for pid, name in remaining)
    msg = ('پورت %s توسط برنامه دیگری اشغال است: %s\n'
           'برنامه برای جلوگیری از صفحه صفر درصد بسته می‌شود.') % (PORT, details)
    log.error(msg)
    _show_startup_error(msg)
    return False


def _acquire_single_instance(log):
    """Prevent duplicate EXE launches from creating competing web servers."""
    global _single_instance_handle
    if sys.platform != 'win32':
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        name = 'Global\\TaskHub_LAN_%s' % PORT
        handle = kernel32.CreateMutexW(None, False, name)
        if not handle:
            return True
        _single_instance_handle = handle
        if kernel32.GetLastError() == 183:
            log.warning('Another TaskHub LAN instance is already running.')
            try:
                os.startfile('http://127.0.0.1:%s/' % PORT)
            except Exception:
                pass
            return False
        return True
    except Exception as exc:
        log.warning('Single-instance guard unavailable: %s', exc)
        return True


def _ensure_firewall_rule(log):
    """Best-effort inbound TCP rule creation on the server only."""
    if not AUTO_FIREWALL or sys.platform != 'win32':
        return
    try:
        import subprocess
        rule_name = 'TaskHub LAN %s' % PORT
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        # Keep one deterministic rule instead of accumulating duplicates after
        # every restart or port change.
        subprocess.run([
            'netsh', 'advfirewall', 'firewall', 'delete', 'rule',
            'name=%s' % rule_name
        ], capture_output=True, text=True, timeout=20, creationflags=flags)
        cmd = [
            'netsh', 'advfirewall', 'firewall', 'add', 'rule',
            'name=%s' % rule_name, 'dir=in', 'action=allow',
            'protocol=TCP', 'localport=%s' % PORT,
            'profile=any', 'enable=yes'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=20, creationflags=flags)
        if result.returncode == 0:
            log.info('Firewall rule is ready for TCP %s.', PORT)
        else:
            log.warning('Firewall rule could not be created: %s',
                        (result.stderr or result.stdout or '').strip())
    except Exception as exc:
        log.warning('Firewall setup failed: %s', exc)


def main():
    global _window
    import time

    # Setup log
    if getattr(sys, 'frozen', False):
        log_dir = os.path.dirname(sys.executable)
    else:
        log_dir = os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(log_dir, 'taskhub_log.txt')
    import logging
    logging.basicConfig(filename=log_path, level=logging.DEBUG,
        format='%(asctime)s %(levelname)s %(message)s', filemode='w', encoding='utf-8')
    log = logging.getLogger('taskhub')
    log.info('=== TaskHub Starting ===')
    log.info(f'Frozen: {getattr(sys, "frozen", False)}')
    log.info('Version=%s chat_mode=%s bind=%s:%s', APP_VERSION, CHAT_MODE, HOST, PORT)

    if not _replace_old_listener(log):
        return
    if not _acquire_single_instance(log):
        return
    _ensure_firewall_rule(log)

    # Create/upgrade the tables as soon as the server starts instead of waiting
    # for the first browser to open the page. A failure is logged here and is
    # shown again, with the exact SQL error, on the loading screen.
    def _startup_db_init():
        try:
            log.info('Preparing database at startup...')
            _initialize_database(log)
        except Exception as exc:
            log.error('Startup database preparation failed: %s', exc)
    threading.Thread(target=_startup_db_init, name='taskhub-db-init', daemon=True).start()

    server_only = '--server' in sys.argv

    if server_only:
        # Headless mode: no window, no tray - just the shared web server.
        # Meant for running on a dedicated always-on machine (e.g. via Task
        # Scheduler at boot, no one needs to be logged in). Other users just
        # open a browser to the configured http(s)://<this-machine-ip>:19234 - nothing to
        # install or update on their side, ever.
        log.info('Starting in --server (headless) mode...')
        print('=== TaskHub Server ===')
        print(f'Listening on {URL_SCHEME}://{_resolve_client_host()}:{PORT}/  (Ctrl+C to stop)')
        start_flask()
        return

    # Start Flask
    log.info('Starting Flask...')
    t = threading.Thread(target=start_flask, daemon=True)
    t.start()
    ok = wait_flask()
    log.info(f'Flask ready: {ok}')
    if not ok:
        msg = ('وب‌سرور روی پورت %s بالا نیامد. برنامه بسته شد تا روی صفر درصد نماند.\n'
               'فایل taskhub_log.txt را بررسی کنید.') % PORT
        log.error(msg)
        _show_startup_error(msg)
        os._exit(1)

    # Get window icon
    icon_path = None
    try:
        with open(get_html_path(), 'r', encoding='utf-8') as f:
            html = f.read()
        m = re.search(r'data:image/png;base64,([A-Za-z0-9+/=]+)', html)
        if m:
            icon_dir = log_dir
            icon_path = os.path.join(icon_dir, '_taskhub_icon.png')
            with open(icon_path, 'wb') as f:
                f.write(base64.b64decode(m.group(1)))
    except Exception as e:
        log.error(f'Icon extraction failed: {e}')

    # Create native window with pywebview. The import is intentionally
    # lazy so the dedicated IIS/Waitress server does not load GUI libraries.
    import webview
    log.info('Creating window...')
    _window = webview.create_window(
        'تسک هاب',
        url=f'{INTERNAL_SCHEME}://127.0.0.1:{PORT}/',
        width=1280, height=820,
        min_size=(1100, 700),
        background_color='#07071a',
        text_select=True,
    )
    # Minimize-to-tray on close instead of leaving an orphaned/zombie process.
    _setup_tray(icon_path, log)
    _window.events.closing += lambda: _on_window_closing(log)
    log.info('Starting webview...')
    webview.start()
    # When window closes, webview.start() returns — force full shutdown
    log.info('Window closed, shutting down...')
    try:
        conn = getattr(_db_local, 'conn', None)
        if conn:
            conn.close()
    except Exception:
        pass
    os._exit(0)

if __name__ == '__main__':
    main()
