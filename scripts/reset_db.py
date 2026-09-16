"""
TaskHub - Database Reset (run ONCE before switching to the new version)

This wipes the OLD schema entirely (Cities, Projects, Contacts, Staff,
TaskCategories, Tasks, Users) and rebuilds the NEW schema where employer
and support are just roles on the Users table (no more separate
Contacts/Staff tables). After running this, the database will contain
ONLY the default admin user with the password you choose.

This is intentionally a manual, one-time script rather than something
taskhub.py runs automatically on every launch - an app that silently wipes
its own database on every startup would be too dangerous to ship.

NOTE: console messages here are English on purpose. cmd.exe does not
reliably render Persian text without a specific font/codepage setup,
so this script (like build.bat) sticks to English for safety.
"""
import os
import sys
import hashlib
import secrets
import pyodbc

# Application modules live in ../src.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
from config import connection_string
CONN_STR = connection_string()


def hash_pw(password):
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return salt + '$' + dk.hex()


def main():
    print('=== TaskHub - Database Reset ===')
    print('This will DELETE ALL current data (cities, projects, contacts,')
    print('staff, tasks, users) and leave only one admin user. You will choose its password.')
    confirm = input('Type YES to continue: ').strip()
    if confirm != 'YES':
        print('Cancelled.')
        return

    print('Connecting to ' + CONN_STR.split('SERVER=')[1].split(';')[0] + ' ...')
    conn = pyodbc.connect(CONN_STR, timeout=15)
    cur = conn.cursor()

    import getpass
    admin_password = getpass.getpass('New admin password (minimum 10 characters): ')
    if len(admin_password) < 10:
        print('Cancelled: password is too short.')
        return

    print('[1/3] Dropping old tables...')
    # Drop in dependency order (children before parents). IF EXISTS is safe
    # whether this is a fresh DB, the old schema, or a half-upgraded one.
    drop_order = ['Tasks', 'Users', 'Contacts', 'Staff', 'TaskCategories', 'Projects', 'Cities']
    for t in drop_order:
        try:
            cur.execute(f"IF EXISTS(SELECT * FROM sysobjects WHERE name='{t}' AND xtype='U') DROP TABLE {t}")
        except Exception as e:
            print(f'  warning: dropping {t} failed ({e})')
    conn.commit()

    print('[2/3] Creating new tables...')
    cur.execute("CREATE TABLE Cities(id INT IDENTITY PRIMARY KEY,name NVARCHAR(100) NOT NULL UNIQUE,created_at DATETIME DEFAULT GETDATE())")
    cur.execute("CREATE TABLE Projects(id INT IDENTITY PRIMARY KEY,city_id INT REFERENCES Cities(id) ON DELETE CASCADE,name NVARCHAR(200) NOT NULL,notes NVARCHAR(MAX) NULL,created_at DATETIME DEFAULT GETDATE())")
    cur.execute("CREATE TABLE TaskCategories(id INT IDENTITY PRIMARY KEY,name NVARCHAR(200) NOT NULL,description NVARCHAR(500),created_at DATETIME DEFAULT GETDATE())")
    cur.execute("CREATE TABLE Users(id INT IDENTITY PRIMARY KEY,username NVARCHAR(80) NOT NULL UNIQUE,password_hash NVARCHAR(200) NOT NULL,role NVARCHAR(20) NOT NULL,display_name NVARCHAR(200),phone NVARCHAR(30),phone2 NVARCHAR(30),position NVARCHAR(100),project_id INT NULL REFERENCES Projects(id),is_active BIT DEFAULT 1,created_at DATETIME DEFAULT GETDATE())")
    cur.execute("CREATE TABLE Tasks(id INT IDENTITY PRIMARY KEY,title NVARCHAR(300) NOT NULL,type NVARCHAR(20) DEFAULT 'bug',status NVARCHAR(20) DEFAULT 'registered',category_id INT REFERENCES TaskCategories(id) ON DELETE SET NULL,project_id INT REFERENCES Projects(id) ON DELETE NO ACTION,contact_id INT REFERENCES Users(id) ON DELETE NO ACTION,staff_id INT REFERENCES Users(id) ON DELETE NO ACTION,date_recv NVARCHAR(20),date_delivery NVARCHAR(20),description NVARCHAR(MAX),solution NVARCHAR(MAX),test_notes NVARCHAR(MAX),priority INT DEFAULT 2,created_by INT NULL,started_at DATETIME NULL,submitted_at DATETIME NULL,completed_at DATETIME NULL,work_seconds INT DEFAULT 0,reject_reason NVARCHAR(MAX) NULL,active_actor_id INT NULL,due_jalali NVARCHAR(10) NULL,created_at DATETIME DEFAULT GETDATE())")
    cur.execute("CREATE TABLE Sessions(token NVARCHAR(64) PRIMARY KEY,user_id INT NOT NULL REFERENCES Users(id) ON DELETE CASCADE,expires_at DATETIME NOT NULL,created_at DATETIME DEFAULT GETDATE())")
    cur.execute("CREATE TABLE TaskAssignees(task_id INT NOT NULL REFERENCES Tasks(id) ON DELETE CASCADE,user_id INT NOT NULL REFERENCES Users(id) ON DELETE NO ACTION,assigned_at DATETIME DEFAULT GETDATE(),PRIMARY KEY(task_id,user_id))")
    cur.execute("CREATE TABLE TaskTimeLog(id INT IDENTITY PRIMARY KEY,task_id INT NOT NULL REFERENCES Tasks(id) ON DELETE CASCADE,user_id INT NOT NULL,started_at DATETIME NOT NULL,ended_at DATETIME NULL,seconds INT NULL)")
    cur.execute("CREATE TABLE WeeklySchedule(id INT IDENTITY PRIMARY KEY,staff_id INT NOT NULL REFERENCES Users(id) ON DELETE NO ACTION,day_of_week INT NOT NULL,city_id INT NOT NULL REFERENCES Cities(id) ON DELETE NO ACTION,project_id INT NULL REFERENCES Projects(id) ON DELETE NO ACTION,sort_order INT DEFAULT 0,created_by INT NULL,created_at DATETIME DEFAULT GETDATE())")
    cur.execute("CREATE TABLE Holidays(id INT IDENTITY PRIMARY KEY,jalali_date NVARCHAR(10) NOT NULL UNIQUE,title NVARCHAR(200) NOT NULL,created_by INT NULL,created_at DATETIME DEFAULT GETDATE())")
    cur.execute("CREATE TABLE Missions(id INT IDENTITY PRIMARY KEY,staff_id INT NOT NULL REFERENCES Users(id) ON DELETE NO ACTION,city_id INT NOT NULL REFERENCES Cities(id) ON DELETE NO ACTION,project_id INT NULL REFERENCES Projects(id) ON DELETE NO ACTION,start_jalali NVARCHAR(10) NOT NULL,end_jalali NVARCHAR(10) NOT NULL,note NVARCHAR(500) NULL,created_by INT NULL,created_at DATETIME DEFAULT GETDATE())")
    cur.execute("CREATE TABLE Attendance(id INT IDENTITY PRIMARY KEY,user_id INT NOT NULL REFERENCES Users(id) ON DELETE NO ACTION,work_date NVARCHAR(10) NOT NULL,check_in DATETIME NOT NULL,check_out DATETIME NULL,last_heartbeat DATETIME NULL,checkout_source NVARCHAR(20) NULL,created_at DATETIME DEFAULT GETDATE())")
    cur.execute("CREATE INDEX IX_Attendance_user_date ON Attendance(user_id, work_date)")
    cur.execute("CREATE TABLE Leaves(id INT IDENTITY PRIMARY KEY,staff_id INT NOT NULL REFERENCES Users(id) ON DELETE NO ACTION,leave_date NVARCHAR(10) NOT NULL,end_date NVARCHAR(10) NULL,leave_type NVARCHAR(10) NOT NULL,start_time NVARCHAR(5) NULL,end_time NVARCHAR(5) NULL,reason NVARCHAR(300) NULL,status NVARCHAR(12) NOT NULL DEFAULT 'approved',reviewed_by INT NULL,reviewed_at DATETIME NULL,review_note NVARCHAR(300) NULL,created_by INT NULL,created_at DATETIME DEFAULT GETDATE())")
    cur.execute("CREATE INDEX IX_Leaves_staff_date ON Leaves(staff_id, leave_date)")
    conn.commit()

    # v6 tables
    cur.execute("CREATE TABLE AuditLog(id INT IDENTITY PRIMARY KEY,user_id INT NULL,username NVARCHAR(100) NULL,action NVARCHAR(60) NOT NULL,detail NVARCHAR(500) NULL,ip NVARCHAR(45) NULL,created_at DATETIME DEFAULT GETDATE())")
    cur.execute("CREATE INDEX IX_AuditLog_created ON AuditLog(created_at)")
    cur.execute("CREATE TABLE Notifications(id INT IDENTITY PRIMARY KEY,user_id INT NOT NULL,kind NVARCHAR(30) NOT NULL,title NVARCHAR(200) NOT NULL,link_task_id INT NULL,is_read BIT DEFAULT 0,created_at DATETIME DEFAULT GETDATE())")
    cur.execute("CREATE INDEX IX_Notif_user ON Notifications(user_id, is_read)")
    cur.execute("CREATE TABLE TaskComments(id INT IDENTITY PRIMARY KEY,task_id INT NOT NULL REFERENCES Tasks(id) ON DELETE CASCADE,user_id INT NOT NULL,author_name NVARCHAR(120) NULL,author_role NVARCHAR(20) NULL,body NVARCHAR(MAX) NOT NULL,created_at DATETIME DEFAULT GETDATE())")
    cur.execute("CREATE INDEX IX_TaskComments_task ON TaskComments(task_id)")
    cur.execute("CREATE TABLE TaskTemplates(id INT IDENTITY PRIMARY KEY,name NVARCHAR(150) NOT NULL,title NVARCHAR(300) NULL,type NVARCHAR(20) NULL,category_id INT NULL,description NVARCHAR(MAX) NULL,priority INT NULL,created_by INT NULL,created_at DATETIME DEFAULT GETDATE())")
    cur.execute("CREATE TABLE SavedFilters(id INT IDENTITY PRIMARY KEY,user_id INT NOT NULL,name NVARCHAR(120) NOT NULL,scope NVARCHAR(20) NOT NULL,filter_json NVARCHAR(MAX) NOT NULL,created_at DATETIME DEFAULT GETDATE())")
    cur.execute("CREATE TABLE TaskEvaluations(id INT IDENTITY PRIMARY KEY,task_id INT NOT NULL REFERENCES Tasks(id) ON DELETE CASCADE,user_id INT NOT NULL,score INT NOT NULL,note NVARCHAR(500) NULL,rated_by INT NULL,rated_at DATETIME DEFAULT GETDATE())")
    cur.execute("CREATE UNIQUE INDEX IX_TaskEval_task_user ON TaskEvaluations(task_id, user_id)")
    cur.execute("CREATE INDEX IX_TaskEval_user ON TaskEvaluations(user_id, rated_at)")
    conn.commit()

    print('[3/3] Creating default admin user...')
    cur.execute(
        "INSERT INTO Users(username,password_hash,role,display_name) VALUES(?,?,?,?)",
        'admin', hash_pw(admin_password), 'admin', 'Admin')
    conn.commit()

    print('[3/3] Seeding initial 1405 holiday list...')
    # Same starter list as taskhub.py's init_tables - kept in sync so a full
    # reset and an incremental upgrade both end up with the same calendar
    # data. Best-effort/not guaranteed complete (see note in taskhub.py).
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
        cur.execute("INSERT INTO Holidays(jalali_date,title) VALUES(?,?)", jd, title)
    conn.commit()
    conn.close()

    print('')
    print('[OK] Database reset successfully.')
    print('Login username: admin')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'ERROR: {e}')
    input('Press Enter to exit...')
