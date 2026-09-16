# -*- coding: utf-8 -*-
"""R13 points, coins and item shop: storage and routes.

The rules live in gamification_domain and are unit-tested there; this module
reads rows, asks the domain what they mean and writes the answer back. It is
additive like the v7/v8/r10 modules: it creates its own tables and registers
its own routes.

Everything that reacts to the rest of the application - a task approved or
sent back, a star given, a task edited or deleted - arrives through a single
after_request hook. The task workflow therefore never waits on the game layer
and can never fail because of it: a problem here is logged, and the task keeps
the status it was given.
"""
from __future__ import annotations

import base64
import binascii
import datetime as _dt
import logging
import threading
import time
from decimal import Decimal

from flask import g, jsonify, request
from api_errors import public_error

import gamification_domain as gd
from rbac import user_has_permission
from team_scope import has_company_scope

LOG = logging.getLogger("taskhub")

SETTING_DEFAULTS = {
    # The shop opens after the pilot month, once real earnings are known and
    # prices can be set from them; points and coins accrue from day one.
    "game_shop_open": "0",
    "game_points_per_coin": "10",
    "game_coins_per_star": "20",
    "game_badge_coins": "20",
    "game_quest_coins": "30",
    "game_daily_softcap": "15",
    "game_gift_monthly_cap": "5",
    "game_kudos_per_week": "3",
    "game_kudos_coins": "2",
    "game_expiry_months": "12",
    "game_level_thresholds": "0,300,1000,3000,8000",
}
SETTING_LIMITS = {
    "game_points_per_coin": (1, 1000),
    "game_coins_per_star": (0, 100000),
    "game_badge_coins": (0, 100000),
    "game_quest_coins": (0, 100000),
    "game_daily_softcap": (1, 500),
    "game_gift_monthly_cap": (0, 1000),
    "game_kudos_per_week": (0, 100),
    "game_kudos_coins": (0, 10000),
    "game_expiry_months": (1, 60),
}
MAX_IMAGE_BYTES = 700 * 1024
IMAGE_MIMES = ("image/png", "image/jpeg", "image/webp", "image/gif")
TRACKED_TASK_ACTIONS = ("triage_approve", "triage_reject", "assign", "start", "pause",
                        "forward", "back_admin", "approve", "send_back")
HOOKED_ENDPOINTS = ("api_task_transition", "api_task_evaluation_save",
                    "api_v7_task_delete", "api_v7_task_save")
# Same definition of an approved statement as the team goals page, so the
# financial team mission and the goals screen always agree.
APPROVED_STATEMENT = """(s.business_status='employer_approved' OR (s.employer_decision_at IS NOT NULL
    AND ISNULL(s.business_status,'') NOT IN ('employer_rejected','revised','void')
    AND COALESCE(s.confirmed_without_vat,s.confirmed_price,0)>0))"""
ORDER_LABELS = {
    "active": "فعال", "scheduled": "زمان‌بندی‌شده", "awaiting_date": "منتظر انتخاب روز",
    "pending_payment": "در انتظار پرداخت", "paid": "پرداخت شد",
    "pending_delivery": "در انتظار تحویل", "delivered": "تحویل شد",
    "cancelled": "لغو شد", "contributed": "مشارکت در صندوق",
}
COIN_KIND_LABELS = {
    "task": "تسک", "badge": "نشان", "quest": "مأموریت تیمی", "rating": "ستاره ماهانه",
    "kudos": "قدردانی همکار", "spend": "خرید", "refund": "برگشت خرید",
    "adjust": "اصلاح مدیر سیستم", "gift": "هدیه",
}

_SCHEMA = (
    """IF OBJECT_ID('TaskEvents','U') IS NULL CREATE TABLE TaskEvents(
        id INT IDENTITY PRIMARY KEY,task_id INT NOT NULL,action NVARCHAR(30) NOT NULL,
        actor_id INT NULL,due_jalali NVARCHAR(10) NULL,
        created_at DATETIME NOT NULL DEFAULT GETDATE())""",
    """IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_TaskEvents_task'
        AND object_id=OBJECT_ID('TaskEvents'))
        CREATE INDEX IX_TaskEvents_task ON TaskEvents(task_id,action,id)""",
    """IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_TaskEvents_created'
        AND object_id=OBJECT_ID('TaskEvents'))
        CREATE INDEX IX_TaskEvents_created ON TaskEvents(created_at,action) INCLUDE(task_id,actor_id)""",
    "IF COL_LENGTH('Tasks','due_at_assign') IS NULL ALTER TABLE Tasks ADD due_at_assign NVARCHAR(10) NULL",
    """IF COL_LENGTH('Leaves','is_reward') IS NULL
        ALTER TABLE Leaves ADD is_reward BIT NOT NULL CONSTRAINT DF_Leaves_is_reward DEFAULT 0""",
    "IF COL_LENGTH('Leaves','reward_order_id') IS NULL ALTER TABLE Leaves ADD reward_order_id INT NULL",
    """IF OBJECT_ID('GameWallets','U') IS NULL CREATE TABLE GameWallets(
        user_id INT NOT NULL PRIMARY KEY,updated_at DATETIME NOT NULL DEFAULT GETDATE())""",
    """IF OBJECT_ID('GameXpLedger','U') IS NULL CREATE TABLE GameXpLedger(
        id INT IDENTITY PRIMARY KEY,user_id INT NOT NULL,season_key NVARCHAR(10) NOT NULL,
        source_type NVARCHAR(20) NOT NULL,source_id INT NULL,points INT NOT NULL,
        note NVARCHAR(300) NULL,created_at DATETIME NOT NULL DEFAULT GETDATE())""",
    """IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_GameXp_user_season'
        AND object_id=OBJECT_ID('GameXpLedger'))
        CREATE INDEX IX_GameXp_user_season ON GameXpLedger(user_id,season_key) INCLUDE(points)""",
    """IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_GameXp_source'
        AND object_id=OBJECT_ID('GameXpLedger'))
        CREATE INDEX IX_GameXp_source ON GameXpLedger(source_type,source_id,user_id)""",
    """IF OBJECT_ID('GameCoinLedger','U') IS NULL CREATE TABLE GameCoinLedger(
        id INT IDENTITY PRIMARY KEY,user_id INT NOT NULL,amount INT NOT NULL,
        kind NVARCHAR(20) NOT NULL,source_type NVARCHAR(20) NULL,source_id INT NULL,
        reverses_id INT NULL,note NVARCHAR(300) NULL,created_by INT NULL,
        created_at DATETIME NOT NULL DEFAULT GETDATE(),expires_at DATETIME NULL)""",
    """IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_GameCoin_user'
        AND object_id=OBJECT_ID('GameCoinLedger'))
        CREATE INDEX IX_GameCoin_user ON GameCoinLedger(user_id,created_at)""",
    """IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_GameCoin_source'
        AND object_id=OBJECT_ID('GameCoinLedger'))
        CREATE INDEX IX_GameCoin_source ON GameCoinLedger(source_type,source_id,user_id)""",
    """IF OBJECT_ID('GameUserBadges','U') IS NULL CREATE TABLE GameUserBadges(
        id INT IDENTITY PRIMARY KEY,user_id INT NOT NULL,badge_key NVARCHAR(40) NOT NULL,
        period_key NVARCHAR(12) NOT NULL,coins INT NOT NULL DEFAULT 0,
        awarded_at DATETIME NOT NULL DEFAULT GETDATE(),
        CONSTRAINT UQ_GameUserBadges UNIQUE(user_id,badge_key,period_key))""",
    """IF OBJECT_ID('GameTeamQuestResults','U') IS NULL CREATE TABLE GameTeamQuestResults(
        id INT IDENTITY PRIMARY KEY,team_id INT NOT NULL,month_key NVARCHAR(7) NOT NULL,
        quest_key NVARCHAR(30) NOT NULL,achieved BIT NOT NULL DEFAULT 0,
        detail NVARCHAR(200) NULL,coins_per_member INT NOT NULL DEFAULT 0,
        evaluated_at DATETIME NOT NULL DEFAULT GETDATE(),
        CONSTRAINT UQ_GameTeamQuestResults UNIQUE(team_id,month_key,quest_key))""",
    """IF OBJECT_ID('GameKudos','U') IS NULL CREATE TABLE GameKudos(
        id INT IDENTITY PRIMARY KEY,from_user INT NOT NULL,to_user INT NOT NULL,
        task_id INT NULL,note NVARCHAR(200) NULL,coins INT NOT NULL DEFAULT 0,
        created_at DATETIME NOT NULL DEFAULT GETDATE())""",
    """IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_GameKudos_from'
        AND object_id=OBJECT_ID('GameKudos'))
        CREATE INDEX IX_GameKudos_from ON GameKudos(from_user,created_at)""",
    """IF OBJECT_ID('GameMonthlyRatings','U') IS NULL CREATE TABLE GameMonthlyRatings(
        id INT IDENTITY PRIMARY KEY,user_id INT NOT NULL,month_key NVARCHAR(7) NOT NULL,
        stars TINYINT NOT NULL,note NVARCHAR(500) NULL,rated_by INT NULL,
        rated_at DATETIME NOT NULL DEFAULT GETDATE(),coins INT NOT NULL DEFAULT 0,
        CONSTRAINT UQ_GameMonthlyRatings UNIQUE(user_id,month_key),
        CONSTRAINT CK_GameMonthlyRatings_stars CHECK(stars BETWEEN 1 AND 5))""",
    """IF OBJECT_ID('GameCosmetics','U') IS NULL CREATE TABLE GameCosmetics(
        user_id INT NOT NULL,slot NVARCHAR(20) NOT NULL,item_id INT NULL,
        value NVARCHAR(60) NOT NULL,updated_at DATETIME NOT NULL DEFAULT GETDATE(),
        CONSTRAINT PK_GameCosmetics PRIMARY KEY(user_id,slot))""",
    """IF OBJECT_ID('ShopItems','U') IS NULL CREATE TABLE ShopItems(
        id INT IDENTITY PRIMARY KEY,name NVARCHAR(150) NOT NULL,description NVARCHAR(1000) NULL,
        item_type NVARCHAR(20) NOT NULL,price INT NOT NULL,
        is_active BIT NOT NULL DEFAULT 1,is_archived BIT NOT NULL DEFAULT 0,
        stock_total INT NULL,per_user_monthly_limit INT NULL,
        sale_from DATE NULL,sale_to DATE NULL,show_in_public BIT NOT NULL DEFAULT 1,
        leave_mode NVARCHAR(10) NULL,leave_hours DECIMAL(4,1) NULL,
        reward_amount DECIMAL(18,0) NULL,team_goal INT NULL,
        cosmetic_slot NVARCHAR(20) NULL,cosmetic_value NVARCHAR(60) NULL,
        image_mime NVARCHAR(40) NULL,image_data VARBINARY(MAX) NULL,
        image_version INT NOT NULL DEFAULT 0,
        created_by INT NULL,created_at DATETIME NOT NULL DEFAULT GETDATE(),
        updated_by INT NULL,updated_at DATETIME NULL,
        CONSTRAINT CK_ShopItems_price CHECK(price>0))""",
    """IF OBJECT_ID('ShopFestivals','U') IS NULL CREATE TABLE ShopFestivals(
        id INT IDENTITY PRIMARY KEY,title NVARCHAR(150) NOT NULL,
        start_date DATE NOT NULL,end_date DATE NOT NULL,
        created_by INT NULL,created_at DATETIME NOT NULL DEFAULT GETDATE(),
        CONSTRAINT CK_ShopFestivals_range CHECK(end_date>=start_date))""",
    """IF OBJECT_ID('ShopFestivalItems','U') IS NULL CREATE TABLE ShopFestivalItems(
        festival_id INT NOT NULL REFERENCES ShopFestivals(id) ON DELETE CASCADE,
        item_id INT NOT NULL REFERENCES ShopItems(id) ON DELETE CASCADE,
        discount_percent INT NOT NULL,
        CONSTRAINT PK_ShopFestivalItems PRIMARY KEY(festival_id,item_id),
        CONSTRAINT CK_ShopFestivalItems_percent CHECK(discount_percent BETWEEN 1 AND 90))""",
    """IF OBJECT_ID('ShopOrders','U') IS NULL CREATE TABLE ShopOrders(
        id INT IDENTITY PRIMARY KEY,item_id INT NOT NULL REFERENCES ShopItems(id),
        user_id INT NOT NULL,item_type NVARCHAR(20) NOT NULL,item_name NVARCHAR(150) NOT NULL,
        base_price INT NOT NULL DEFAULT 0,price_paid INT NOT NULL DEFAULT 0,
        discount_percent INT NULL,festival_id INT NULL,status NVARCHAR(20) NOT NULL,
        scheduled_date NVARCHAR(10) NULL,start_time NVARCHAR(5) NULL,
        leave_id INT NULL,gift_id INT NULL,team_id INT NULL,pot_round INT NULL,
        coin_entry_id INT NULL,show_in_public BIT NOT NULL DEFAULT 1,note NVARCHAR(500) NULL,
        created_at DATETIME NOT NULL DEFAULT GETDATE(),
        fulfilled_by INT NULL,fulfilled_at DATETIME NULL)""",
    """IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_ShopOrders_user'
        AND object_id=OBJECT_ID('ShopOrders'))
        CREATE INDEX IX_ShopOrders_user ON ShopOrders(user_id,created_at)""",
    """IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_ShopOrders_item'
        AND object_id=OBJECT_ID('ShopOrders'))
        CREATE INDEX IX_ShopOrders_item ON ShopOrders(item_id,status)""",
    """IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_ShopOrders_status'
        AND object_id=OBJECT_ID('ShopOrders'))
        CREATE INDEX IX_ShopOrders_status ON ShopOrders(status,created_at)""",
    """IF OBJECT_ID('ShopWishlist','U') IS NULL CREATE TABLE ShopWishlist(
        user_id INT NOT NULL,item_id INT NOT NULL REFERENCES ShopItems(id) ON DELETE CASCADE,
        created_at DATETIME NOT NULL DEFAULT GETDATE(),
        CONSTRAINT PK_ShopWishlist PRIMARY KEY(user_id,item_id))""",
    """IF OBJECT_ID('ShopGifts','U') IS NULL CREATE TABLE ShopGifts(
        id INT IDENTITY PRIMARY KEY,order_id INT NULL,item_id INT NOT NULL,
        to_user INT NOT NULL,from_user INT NOT NULL,reason NVARCHAR(1000) NOT NULL,
        link_type NVARCHAR(12) NOT NULL,link_id INT NOT NULL,
        created_at DATETIME NOT NULL DEFAULT GETDATE())""",
    """IF OBJECT_ID('GameTeamPots','U') IS NULL CREATE TABLE GameTeamPots(
        item_id INT NOT NULL,team_id INT NOT NULL,round_no INT NOT NULL DEFAULT 1,
        CONSTRAINT PK_GameTeamPots PRIMARY KEY(item_id,team_id))""",
)


def _jsonable(value):
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (bytes, bytearray, memoryview)):
        return None
    return str(value)


def init_gamification_tables(conn):
    """Create the R13 tables and default settings; safe on every startup."""
    cur = conn.cursor()
    try:
        for sql in _SCHEMA:
            cur.execute(sql)
        for key, value in SETTING_DEFAULTS.items():
            cur.execute("""IF NOT EXISTS(SELECT 1 FROM AppSettings WHERE setting_key=?)
                INSERT INTO AppSettings(setting_key,setting_value,updated_at) VALUES(?,?,GETDATE())""",
                        key, key, value)
        # Points are only ever earned for work approved after this moment, so
        # nobody starts the first season with a head start from old tasks.
        cur.execute("""IF NOT EXISTS(SELECT 1 FROM AppSettings WHERE setting_key='game_installed_at')
            INSERT INTO AppSettings(setting_key,setting_value,updated_at)
            VALUES('game_installed_at',CONVERT(NVARCHAR(30),GETDATE(),126),GETDATE())""")
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


def register_game_routes(app, get_conn, db_lock, require_auth, rows_to_list, audit, notify):
    """Register /api/game/* and the task hooks."""

    # ── plumbing ────────────────────────────────────────────────────────────
    def ok(**kwargs):
        payload = {"ok": True}
        payload.update(kwargs)
        return jsonify(_jsonable(payload))

    def err(message, status=200, **kwargs):
        payload = {"ok": False, "error": message}
        payload.update(kwargs)
        return jsonify(_jsonable(payload)), status

    def body():
        return request.get_json(silent=True) or {}

    def fetch(cur, sql, *params):
        cur.execute(sql, *params)
        if not cur.description:
            return []
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def fetch_one(cur, sql, *params):
        cur.execute(sql, *params)
        row = cur.fetchone()
        if not row:
            return None
        return dict(zip([c[0] for c in cur.description], row))

    def scalar(cur, sql, *params):
        cur.execute(sql, *params)
        row = cur.fetchone()
        return row[0] if row else None

    def db_now(cur):
        return scalar(cur, "SELECT GETDATE()")

    def rollback(conn):
        try:
            conn.rollback()
        except Exception:
            pass

    def settings(cur):
        values = dict(SETTING_DEFAULTS)
        for row in fetch(cur, "SELECT setting_key,setting_value FROM AppSettings WHERE setting_key LIKE 'game[_]%'"):
            if row["setting_value"] is not None:
                values[str(row["setting_key"])] = str(row["setting_value"])
        return values

    def setting_int(values, key):
        return gd.to_int(values.get(key), gd.to_int(SETTING_DEFAULTS.get(key), 0))

    def save_setting(cur, key, value, uid=None):
        cur.execute("""IF EXISTS(SELECT 1 FROM AppSettings WHERE setting_key=?)
            UPDATE AppSettings SET setting_value=?,updated_by=?,updated_at=GETDATE() WHERE setting_key=?
            ELSE INSERT INTO AppSettings(setting_key,setting_value,updated_by,updated_at)
            VALUES(?,?,?,GETDATE())""", key, value, uid, key, key, value, uid)

    def installed_at(cur):
        raw = scalar(cur, "SELECT setting_value FROM AppSettings WHERE setting_key='game_installed_at'")
        try:
            return _dt.datetime.fromisoformat(str(raw)[:19])
        except (TypeError, ValueError):
            return None

    def user_info(cur, uid):
        return fetch_one(cur, "SELECT id,username,display_name,role,is_active FROM Users WHERE id=?", uid)

    def name_of(row):
        row = row or {}
        return row.get("display_name") or row.get("username") or ""

    def team_ids_of(cur, uid):
        return [int(r["team_id"]) for r in fetch(cur, """SELECT tm.team_id FROM TeamMembers tm
            JOIN Teams t ON t.id=tm.team_id
            WHERE tm.user_id=? AND tm.is_active=1 AND t.is_active=1""", uid)]

    def primary_team(cur, uid):
        return fetch_one(cur, """SELECT TOP 1 tm.team_id,t.name FROM TeamMembers tm
            JOIN Teams t ON t.id=tm.team_id
            WHERE tm.user_id=? AND tm.is_active=1 AND t.is_active=1
            ORDER BY tm.is_primary DESC,tm.team_id""", uid)

    def visible_team_ids(cur, user):
        if has_company_scope(user):
            return [int(r["id"]) for r in fetch(cur, "SELECT id FROM Teams WHERE is_active=1")]
        return team_ids_of(cur, user["id"])

    def shares_team(cur, actor, target_id):
        if has_company_scope(actor) or int(actor["id"]) == int(target_id):
            return True
        return scalar(cur, """SELECT TOP 1 1 FROM TeamMembers mine JOIN TeamMembers other
            ON other.team_id=mine.team_id AND other.is_active=1
            WHERE mine.user_id=? AND mine.is_active=1 AND other.user_id=?""",
                      actor["id"], target_id) is not None

    def holiday_days(cur):
        days = set()
        for row in fetch(cur, "SELECT jalali_date FROM Holidays"):
            day = gd.parse_jalali(row["jalali_date"])
            if day:
                days.add(day)
        return days

    def due_of(row):
        return gd.parse_jalali(row.get("due_at_assign") or row.get("due_jalali"))

    # ── wallet ──────────────────────────────────────────────────────────────
    def ensure_wallet(cur, uid):
        cur.execute("""IF NOT EXISTS(SELECT 1 FROM GameWallets WHERE user_id=?)
            INSERT INTO GameWallets(user_id) VALUES(?)""", uid, uid)

    def lock_wallet(cur, uid):
        # Two tabs or a double click must not spend the same coins twice: every
        # purchase takes this row lock first and holds it to commit.
        ensure_wallet(cur, uid)
        cur.execute("SELECT user_id FROM GameWallets WITH (UPDLOCK,HOLDLOCK) WHERE user_id=?", uid)
        cur.fetchall()

    def wallet(cur, uid, now):
        rows = fetch(cur, """SELECT id,amount,kind,created_at,expires_at,reverses_id
            FROM GameCoinLedger WHERE user_id=? ORDER BY created_at,id""", uid)
        return gd.wallet_state(rows, now)

    def add_coins(cur, uid, amount, kind, source_type, source_id, note, now, values,
                  created_by=None, reverses_id=None):
        amount = int(amount or 0)
        if not amount:
            return None
        ensure_wallet(cur, uid)
        expires = None
        if amount > 0 and kind != "refund":
            expires = gd.add_months(now, setting_int(values, "game_expiry_months"))
        cur.execute("""INSERT INTO GameCoinLedger(user_id,amount,kind,source_type,source_id,
                reverses_id,note,created_by,expires_at)
            OUTPUT INSERTED.id VALUES(?,?,?,?,?,?,?,?,?)""",
                    uid, amount, kind, source_type, source_id, reverses_id,
                    (note or "")[:300] or None, created_by, expires)
        return int(cur.fetchone()[0])

    def add_points(cur, uid, season, source_type, source_id, points, note):
        points = int(points or 0)
        if not points:
            return
        cur.execute("""INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note)
            VALUES(?,?,?,?,?,?)""", uid, season, source_type, source_id, points, (note or "")[:300] or None)

    # ── task points ─────────────────────────────────────────────────────────
    def record_task_event(cur, task_id, action, actor_id):
        due = scalar(cur, "SELECT due_jalali FROM Tasks WHERE id=?", task_id)
        cur.execute("INSERT INTO TaskEvents(task_id,action,actor_id,due_jalali) VALUES(?,?,?,?)",
                    task_id, action, actor_id, due)
        if action == "assign":
            # The on-time bonus is measured against the deadline the task had
            # when it was handed over, so moving a deadline later earns nothing.
            cur.execute("""UPDATE Tasks SET due_at_assign=due_jalali WHERE id=?
                AND due_at_assign IS NULL AND ISNULL(due_jalali,'')<>''""", task_id)

    def returns_count(cur, task_id, created_at, installed):
        count = int(scalar(cur, "SELECT COUNT(*) FROM TaskEvents WHERE task_id=? AND action='send_back'",
                           task_id) or 0)
        if installed is None or (created_at is not None and created_at < installed):
            # A task that already existed before this version may have been sent
            # back before TaskEvents did; the audit log still has those.
            legacy = int(scalar(cur, "SELECT COUNT(*) FROM AuditLog WHERE action=N'task_send_back' AND detail=?",
                                "تسک #%s" % task_id) or 0)
            count = max(count, legacy)
        return count

    def recompute_task(cur, task_id, values, now):
        """Bring one task's points and coins in line with its current state.

        Safe to repeat: it compares what the task should be worth today with
        what has already been written and records only the difference. An
        approval, a star, an edit, a reopening and a deletion all come through
        here, so there is exactly one way points can change."""
        task = fetch_one(cur, """SELECT t.id,t.title,t.status,t.staff_id,t.completed_at,t.created_at,
                t.due_jalali,t.due_at_assign,ISNULL(t.progress_weight,1) AS progress_weight,
                ISNULL(w.weight,1) AS category_weight
            FROM Tasks t
            LEFT JOIN Contracts co ON co.id=t.contract_id
            LEFT JOIN ContractTaskCategoryWeights w ON w.contract_type_id=ISNULL(co.contract_type_id,0)
              AND w.task_category_id=t.category_id AND w.is_active=1
            WHERE t.id=?""", task_id)
        targets, details, season = {}, {}, None
        if task and task.get("status") == "done" and task.get("completed_at"):
            approver = fetch_one(cur, """SELECT TOP 1 actor_id FROM TaskEvents
                WHERE task_id=? AND action='approve' ORDER BY id DESC""", task_id)
            # Only work approved since this version earns; older tasks stay out.
            if approver is not None:
                approver_id = approver.get("actor_id")
                returns = returns_count(cur, task_id, task.get("created_at"), installed_at(cur))
                flag = gd.on_time(task["completed_at"], due_of(task))
                helpers = [int(r["user_id"]) for r in fetch(cur,
                           "SELECT user_id FROM TaskAssignees WHERE task_id=?", task_id)]
                seconds = {int(r["user_id"]): int(r["seconds"] or 0) for r in fetch(cur,
                           """SELECT user_id,SUM(ISNULL(seconds,0)) AS seconds FROM TaskTimeLog
                              WHERE task_id=? AND ended_at IS NOT NULL GROUP BY user_id""", task_id)}
                shares = gd.split_shares(task.get("staff_id"), [task.get("staff_id")] + helpers, seconds)
                stars = {int(r["user_id"]): r["score"] for r in fetch(cur,
                         "SELECT user_id,score FROM TaskEvaluations WHERE task_id=?", task_id)}
                roles = {}
                if shares:
                    marks = ",".join("?" for _ in shares)
                    roles = {int(r["id"]): r["role"] for r in fetch(cur,
                             "SELECT id,role FROM Users WHERE id IN (%s)" % marks, *list(shares))}
                cap = setting_int(values, "game_daily_softcap")
                season = gd.season_key(task["completed_at"])
                completed = task["completed_at"]
                for uid, share in shares.items():
                    if roles.get(uid) not in gd.TASK_EARNING_ROLES:
                        continue
                    self_approved = approver_id is not None and int(approver_id) == uid
                    index = int(scalar(cur, """SELECT COUNT(*) FROM Tasks t2
                        WHERE t2.status='done' AND t2.id<>? AND t2.completed_at IS NOT NULL
                          AND CAST(t2.completed_at AS DATE)=CAST(? AS DATE)
                          AND (t2.completed_at<? OR (t2.completed_at=? AND t2.id<?))
                          AND (t2.staff_id=? OR EXISTS(SELECT 1 FROM TaskAssignees a
                                WHERE a.task_id=t2.id AND a.user_id=?))
                          AND EXISTS(SELECT 1 FROM TaskEvents e WHERE e.task_id=t2.id AND e.action='approve')""",
                                       task_id, completed, completed, completed, task_id, uid, uid) or 0)
                    halved = gd.softcap_applies(index, cap)
                    points = 0 if self_approved else gd.task_points(
                        task["progress_weight"], task["category_weight"], returns, flag,
                        stars.get(uid), share, halved)
                    targets[uid] = points
                    details[uid] = {"returns": returns, "on_time": flag, "stars": gd.to_int(stars.get(uid)),
                                    "halved": halved, "self_approved": self_approved, "share": float(share)}
        existing_points = {int(r["user_id"]): int(r["points"] or 0) for r in fetch(cur,
                           """SELECT user_id,SUM(points) AS points FROM GameXpLedger
                              WHERE source_type='task' AND source_id=? GROUP BY user_id""", task_id)}
        existing_coins = {int(r["user_id"]): int(r["amount"] or 0) for r in fetch(cur,
                          """SELECT user_id,SUM(amount) AS amount FROM GameCoinLedger
                             WHERE source_type='task' AND source_id=? GROUP BY user_id""", task_id)}
        per_coin = setting_int(values, "game_points_per_coin")
        title = ((task or {}).get("title") or ("#%s" % task_id))[:80]
        results = {}
        for uid in set(targets) | set(existing_points) | set(existing_coins):
            target = targets.get(uid, 0)
            delta_points = target - existing_points.get(uid, 0)
            if delta_points:
                row_season = season or scalar(cur, """SELECT TOP 1 season_key FROM GameXpLedger
                    WHERE source_type='task' AND source_id=? AND user_id=? ORDER BY id DESC""",
                                              task_id, uid) or gd.season_key(now)
                add_points(cur, uid, row_season, "task", task_id, delta_points, "تسک «%s»" % title)
            delta_coins = gd.coins_for_points(target, per_coin) - existing_coins.get(uid, 0)
            if delta_coins:
                add_coins(cur, uid, delta_coins, "task", "task", task_id, "تسک «%s»" % title, now, values)
            if delta_points or delta_coins:
                results[uid] = dict(details.get(uid, {}), points=delta_points, coins=delta_coins,
                                    total_points=target, title=title, season=season)
        return results

    def award_reason(result):
        if result.get("self_approved"):
            return "تأیید توسط خود شما امتیاز ندارد"
        parts = []
        if result.get("on_time") is True:
            parts.append("سروقت")
        elif result.get("on_time") is False:
            parts.append("با تأخیر")
        returns = result.get("returns") or 0
        parts.append("بدون برگشت" if returns == 0 else "%s برگشت" % gd.fa_digits(returns))
        if result.get("stars"):
            parts.append("%s ستاره" % gd.fa_digits(result["stars"]))
        if result.get("halved"):
            parts.append("بیش از سقف روزانه، نصف امتیاز")
        return "، ".join(parts)

    def signed(value):
        return ("+" if value > 0 else "−") + gd.fa_digits(abs(int(value)))

    def award_badge(cur, uid, key, period, values, now):
        if scalar(cur, "SELECT 1 FROM GameUserBadges WHERE user_id=? AND badge_key=? AND period_key=?",
                  uid, key, period):
            return None
        coins = setting_int(values, "game_badge_coins")
        cur.execute("""INSERT INTO GameUserBadges(user_id,badge_key,period_key,coins)
            OUTPUT INSERTED.id VALUES(?,?,?,?)""", uid, key, period, coins)
        badge_id = int(cur.fetchone()[0])
        title = gd.BADGE_BY_KEY[key]["title"]
        if coins:
            add_coins(cur, uid, coins, "badge", "badge", badge_id, "نشان «%s»" % title, now, values)
        return {"user_id": uid, "key": key, "title": title, "coins": coins}

    def badge_note(result):
        text = "نشان «%s» را گرفتید" % result["title"]
        if result.get("coins"):
            text += ": %s سکه" % gd.fa_digits(result["coins"])
        return text

    def check_task_badges(cur, uid, season, values, now):
        start, end = gd.season_bounds(season)
        rows = fetch(cur, """SELECT t.id,t.completed_at,t.created_at,t.due_jalali,t.due_at_assign,
                t.category_id,t.project_team_id,t.solution,
                CASE WHEN t.staff_id=? THEN 0 ELSE 1 END AS is_helper,
                (SELECT COUNT(*) FROM TaskEvents r WHERE r.task_id=t.id AND r.action='send_back') AS returns
            FROM Tasks t
            WHERE t.status='done' AND t.completed_at>=? AND t.completed_at<?
              AND (t.staff_id=? OR EXISTS(SELECT 1 FROM TaskAssignees a WHERE a.task_id=t.id AND a.user_id=?))
              AND EXISTS(SELECT 1 FROM TaskEvents e WHERE e.task_id=t.id AND e.action='approve')
            ORDER BY t.completed_at,t.id""", uid, start, end + _dt.timedelta(days=1), uid, uid)
        awarded = []

        def give(key):
            result = award_badge(cur, uid, key, season, values, now)
            if result:
                awarded.append(result)

        if gd.flawless_streak([r["returns"] for r in rows]):
            give("flawless")
        if sum(1 for r in rows if gd.on_time(r["completed_at"], due_of(r)) is True) >= 20:
            give("ontime")
        if sum(1 for r in rows if r["is_helper"]) >= 5:
            give("helper")
        if sum(1 for r in rows if r["category_id"] and r["project_team_id"]
               and str(r["solution"] or "").strip()) >= 20:
            give("complete")
        if any(r["created_at"] and (r["completed_at"] - r["created_at"]).days > 30 for r in rows):
            give("untangler")
        return awarded

    def check_steady(cur, uid, values, now):
        """«منظم»: four full weeks in a row without an overdue task."""
        season = gd.season_key(now)
        if scalar(cur, "SELECT 1 FROM GameUserBadges WHERE user_id=? AND badge_key='steady' AND period_key=?",
                  uid, season):
            return None
        today = now.date()
        week_start = today - _dt.timedelta(days=(today.weekday() - 5) % 7)   # Saturday
        window_start = week_start - _dt.timedelta(days=28)
        installed = installed_at(cur)
        if installed is None or window_start < installed.date():
            return None
        tasks = fetch(cur, """SELECT t.created_at,t.completed_at,t.due_jalali,t.due_at_assign
            FROM Tasks t WHERE t.staff_id=? AND t.created_at<? AND ISNULL(t.status,'')<>'rejected'
              AND (t.completed_at IS NULL OR t.completed_at>=?)""", uid, week_start, window_start)
        if not any(t["completed_at"] and t["completed_at"].date() >= window_start for t in tasks):
            return None
        for week in range(4):
            week_end = window_start + _dt.timedelta(days=7 * week + 6)
            for t in tasks:
                due = due_of(t)
                if not due or due > week_end or t["created_at"].date() > week_end:
                    continue
                if t["completed_at"] is None or t["completed_at"].date() > week_end:
                    return None
        return award_badge(cur, uid, "steady", season, values, now)

    # ── hooks from the task workflow ────────────────────────────────────────
    def after_points(conn, cur, results, values, now, kind):
        """Badges for everyone whose points moved, then the notifications."""
        notes = []
        for uid, result in results.items():
            if kind == "approve" and result["points"] > 0:
                notes.append((uid, "تسک «%s»: %s امتیاز و %s سکه — %s" % (
                    result["title"], gd.fa_digits(result["points"]), gd.fa_digits(max(0, result["coins"])),
                    award_reason(result)), None))
            elif kind == "approve" and result.get("self_approved"):
                notes.append((uid, "تسک «%s»: %s" % (result["title"], award_reason(result)), None))
            elif result["points"]:
                why = {"evaluation": "با ارزیابی مدیر", "edit": "با ویرایش تسک",
                       "delete": "با حذف تسک", "approve": "با تأیید دوباره"}.get(kind, "")
                notes.append((uid, "امتیاز تسک «%s» %s به‌روز شد: %s امتیاز" % (
                    result["title"], why, signed(result["points"])), None))
        for uid, result in results.items():
            if result["points"] > 0 and result.get("season"):
                try:
                    for badge in check_task_badges(cur, uid, result["season"], values, now):
                        notes.append((uid, badge_note(badge), None))
                    conn.commit()
                except Exception as exc:
                    rollback(conn)
                    LOG.warning("Badge check failed for user %s: %s", uid, exc)
        return notes

    def on_task_action(task_id, action, user):
        notes = []
        with db_lock:
            conn = get_conn()
            cur = conn.cursor()
            try:
                record_task_event(cur, task_id, action, (user or {}).get("id"))
                results = {}
                if action == "approve":
                    values = settings(cur)
                    now = db_now(cur)
                    results = recompute_task(cur, task_id, values, now)
                conn.commit()
            except Exception:
                rollback(conn)
                raise
            if results:
                notes = after_points(conn, cur, results, values, now, "approve")
        for uid, text, _ in notes:
            notify(uid, "game", text, task_id)

    def on_task_changed(task_id, kind):
        notes = []
        with db_lock:
            conn = get_conn()
            cur = conn.cursor()
            try:
                values = settings(cur)
                now = db_now(cur)
                results = recompute_task(cur, task_id, values, now)
                conn.commit()
            except Exception:
                rollback(conn)
                raise
            if results:
                notes = after_points(conn, cur, results, values, now, kind)
        for uid, text, _ in notes:
            notify(uid, "game", text, task_id if kind != "delete" else None)

    @app.after_request
    def _game_task_hooks(response):
        endpoint = request.endpoint or ""
        if endpoint not in HOOKED_ENDPOINTS:
            return response
        try:
            if response.status_code != 200 or response.mimetype != "application/json":
                return response
            payload = response.get_json(silent=True) or {}
            if not payload.get("ok"):
                return response
            data = request.get_json(silent=True) or {}
            user = getattr(g, "user", None)
            if endpoint == "api_task_transition":
                task_id = gd.to_int(data.get("task_id"))
                action = str(data.get("action") or "")
                if task_id and action in TRACKED_TASK_ACTIONS:
                    on_task_action(task_id, action, user)
            elif endpoint == "api_task_evaluation_save":
                task_id = gd.to_int(data.get("task_id"))
                if task_id:
                    on_task_changed(task_id, "evaluation")
            elif endpoint == "api_v7_task_delete":
                task_id = gd.to_int(data.get("id"))
                if task_id:
                    on_task_changed(task_id, "delete")
            elif endpoint == "api_v7_task_save":
                task_id = gd.to_int(data.get("id")) or gd.to_int(payload.get("id"))
                if task_id:
                    on_task_changed(task_id, "edit")
        except Exception as exc:
            LOG.exception("Gamification hook failed for %s: %s", endpoint, exc)
        return response

    # ── monthly work: team missions and monthly badges ─────────────────────
    def financial_issue_count(cur):
        return int(scalar(cur, """SELECT
            (SELECT COUNT(*) FROM ContractStatements s WHERE s.is_active=1 AND s.is_current=1
               AND NOT EXISTS(SELECT 1 FROM ContractStatementTeams cst
                 WHERE cst.statement_id=s.id AND cst.is_active=1))
          + (SELECT COUNT(*) FROM (SELECT s.id FROM ContractStatements s
               JOIN ContractStatementTeams cst ON cst.statement_id=s.id AND cst.is_active=1
               WHERE s.is_active=1 AND s.is_current=1 GROUP BY s.id
               HAVING ABS(SUM(cst.allocation_percent)-100)>0.01) q)
          + (SELECT COUNT(*) FROM Contracts co WHERE co.is_active=1 AND co.project_id IS NOT NULL
               AND NOT EXISTS(SELECT 1 FROM ContractProjectTeams x
                 WHERE x.contract_id=co.id AND x.is_active=1))""") or 0)

    def team_month_money(cur, team_id, month):
        jy, jm = (int(x) for x in month.split("-"))
        target = scalar(cur, """SELECT ISNULL(SUM(p.target_amount),0) FROM TeamFinancialTargetPeriods p
            JOIN TeamFinancialTargets tf ON tf.id=p.target_id
            JOIN FinancialPlans fp ON fp.id=tf.plan_id
            WHERE tf.team_id=? AND tf.is_current=1 AND fp.is_current=1
              AND fp.jalali_year=? AND p.month_no=?""", team_id, jy, jm) or 0
        approved = scalar(cur, """SELECT ISNULL(SUM(COALESCE(s.confirmed_without_vat,s.confirmed_price,
                s.requested_without_vat,s.requested_price,0)*cst.allocation_percent/100),0)
            FROM ContractStatementTeams cst
            JOIN ContractStatements s ON s.id=cst.statement_id
            JOIN ProjectTeams ptm ON ptm.id=cst.project_team_id
            WHERE cst.is_active=1 AND ptm.team_id=? AND s.is_active=1 AND s.is_current=1
              AND s.period_year=? AND s.period_month=? AND """ + APPROVED_STATEMENT,
                          team_id, jy, jm) or 0
        return Decimal(str(target)), Decimal(str(approved))

    def team_month_tasks(cur, team_id, start, end):
        after = end + _dt.timedelta(days=1)
        tasks = fetch(cur, """SELECT t.id,t.status,t.created_at,t.completed_at,t.due_jalali,t.due_at_assign,
                CASE WHEN EXISTS(SELECT 1 FROM TaskEvents e WHERE e.task_id=t.id AND e.action='approve')
                  THEN 1 ELSE 0 END AS game_era
            FROM Tasks t JOIN ProjectTeams pt ON pt.id=t.project_team_id
            WHERE pt.team_id=? AND t.created_at<? AND ISNULL(t.status,'')<>'rejected'
              AND (t.completed_at IS NULL OR t.completed_at>=?)""", team_id, after, start)
        overdue = 0
        for t in tasks:
            due = due_of(t)
            if due and due <= end and (t["completed_at"] is None or t["completed_at"].date() > end):
                overdue += 1
        done = [t for t in tasks if t["status"] == "done" and t["game_era"] and t["completed_at"]
                and start <= t["completed_at"].date() <= end]
        with_due = [t for t in done if due_of(t)]
        on_time = sum(1 for t in with_due if gd.on_time(t["completed_at"], due_of(t)))
        return {"active": len(tasks), "overdue": overdue, "with_due": len(with_due), "on_time": on_time}

    def planner_metrics(cur, uid, start, after, holidays):
        out = {"triage_count": 0, "triage_median_hours": None, "queue_decisions": 0, "queue_slow": 0,
               "queue_median_hours": None, "team_with_due": 0, "team_on_time": 0,
               "created": 0, "created_complete": 0}
        triage = fetch(cur, """SELECT e.created_at AS at_time,t.created_at AS task_created
            FROM TaskEvents e JOIN Tasks t ON t.id=e.task_id
            WHERE e.actor_id=? AND e.action IN ('triage_approve','triage_reject')
              AND e.created_at>=? AND e.created_at<?""", uid, start, after)
        out["triage_count"] = len(triage)
        out["triage_median_hours"] = gd.median([(r["at_time"] - r["task_created"]).total_seconds() / 3600
                                                for r in triage if r["task_created"]])
        teams = team_ids_of(cur, uid)
        if teams:
            marks = ",".join("?" for _ in teams)
            events = fetch(cur, """SELECT e.task_id,e.action,e.created_at FROM TaskEvents e
                JOIN Tasks t ON t.id=e.task_id JOIN ProjectTeams pt ON pt.id=t.project_team_id
                WHERE pt.team_id IN (%s) AND e.action IN ('forward','approve','send_back')
                  AND e.created_at>=? AND e.created_at<? ORDER BY e.task_id,e.id""" % marks,
                           *(teams + [start - _dt.timedelta(days=15), after]))
            pending, waits, slow = {}, [], 0
            for e in events:
                if e["action"] == "forward":
                    pending[e["task_id"]] = e["created_at"]
                    continue
                began = pending.pop(e["task_id"], None)
                if began is None or not (start <= e["created_at"].date() < after):
                    continue
                waits.append((e["created_at"] - began).total_seconds() / 3600)
                if not gd.within_one_working_day(began, e["created_at"], holidays):
                    slow += 1
            out.update(queue_decisions=len(waits), queue_slow=slow, queue_median_hours=gd.median(waits))
            done = fetch(cur, """SELECT t.completed_at,t.due_jalali,t.due_at_assign FROM Tasks t
                JOIN ProjectTeams pt ON pt.id=t.project_team_id
                WHERE pt.team_id IN (%s) AND t.status='done' AND t.completed_at>=? AND t.completed_at<?
                  AND EXISTS(SELECT 1 FROM TaskEvents a WHERE a.task_id=t.id AND a.action='approve')""" % marks,
                         *(teams + [start, after]))
            with_due = [r for r in done if due_of(r)]
            out["team_with_due"] = len(with_due)
            out["team_on_time"] = sum(1 for r in with_due if gd.on_time(r["completed_at"], due_of(r)))
        created = fetch_one(cur, """SELECT COUNT(*) AS total,
                SUM(CASE WHEN category_id IS NOT NULL AND project_team_id IS NOT NULL
                    AND ISNULL(due_jalali,'')<>'' THEN 1 ELSE 0 END) AS complete
            FROM Tasks WHERE created_by=? AND created_at>=? AND created_at<?""", uid, start, after) or {}
        out["created"] = int(created.get("total") or 0)
        out["created_complete"] = int(created.get("complete") or 0)
        return out

    def finance_metrics(cur, uid, month, start, after):
        jy, jm = (int(x) for x in month.split("-"))
        planned = fetch(cur, """SELECT ps.planned_date,ps.actual_statement_id,
                s.created_at AS actual_created,s.created_by AS actual_by
            FROM PlannedStatements ps JOIN FinancialPlans fp ON fp.id=ps.plan_id
            LEFT JOIN ContractStatements s ON s.id=ps.actual_statement_id
            WHERE ps.is_active=1 AND fp.is_current=1 AND fp.jalali_year=? AND ps.month_no=?""", jy, jm)

        def in_time(r):
            if not r["actual_statement_id"] or not r["actual_created"]:
                return False
            planned_day = gd.as_date(r["planned_date"])
            return planned_day is None or r["actual_created"].date() <= planned_day

        mine = [r for r in planned if r["actual_by"] is not None and int(r["actual_by"]) == int(uid)]
        decided = fetch(cur, """SELECT s.business_status,s.supersedes_statement_id FROM ContractStatements s
            WHERE s.is_active=1 AND s.employer_decision_at>=? AND s.employer_decision_at<?
              AND s.created_by=?""", start, after, uid)
        tax = fetch_one(cur, """SELECT COUNT(*) AS sent,
                SUM(CASE WHEN ISNULL(tax_error,'')='' THEN 1 ELSE 0 END) AS clean
            FROM ContractStatements WHERE tax_sent_at>=? AND tax_sent_at<? AND created_by=?""",
                        start, after, uid) or {}
        return {"planned": len(planned), "planned_on_time": sum(1 for r in planned if in_time(r)),
                "mine_planned": len(mine), "mine_on_time": sum(1 for r in mine if in_time(r)),
                "decided": len(decided),
                "first_time_ok": sum(1 for r in decided if r["business_status"] == "employer_approved"
                                     and r["supersedes_statement_id"] is None),
                "tax_sent": int(tax.get("sent") or 0), "tax_clean": int(tax.get("clean") or 0),
                "issues": financial_issue_count(cur)}

    def process_month(cur, month, values, now):
        notes = []
        start, end = gd.month_bounds(month)
        after = end + _dt.timedelta(days=1)
        quest_coins = setting_int(values, "game_quest_coins")
        for team in fetch(cur, "SELECT id,name FROM Teams WHERE is_active=1"):
            team_id = int(team["id"])
            stats = team_month_tasks(cur, team_id, start, end)
            target, approved = team_month_money(cur, team_id, month)
            outcomes = (
                ("zero_overdue", gd.quest_zero_overdue(stats["overdue"], stats["active"] > 0),
                 "%s تسک معوق در پایان ماه" % gd.fa_digits(stats["overdue"])),
                ("on_time", gd.quest_on_time(stats["on_time"], stats["with_due"]),
                 "%s از %s تسک سروقت" % (gd.fa_digits(stats["on_time"]), gd.fa_digits(stats["with_due"]))),
                ("finance_goal", gd.quest_finance(target, approved),
                 "%s٪ هدف مالی ماه" % gd.fa_digits(gd.percent(int(approved), int(target)) or 0)),
            )
            members = [m for m in fetch(cur, """SELECT u.id,u.role FROM TeamMembers tm
                JOIN Users u ON u.id=tm.user_id
                WHERE tm.team_id=? AND tm.is_active=1 AND u.is_active=1""", team_id)
                       if m["role"] in gd.WALLET_ROLES]
            for quest_key, achieved, detail in outcomes:
                if scalar(cur, """SELECT 1 FROM GameTeamQuestResults
                    WHERE team_id=? AND month_key=? AND quest_key=?""", team_id, month, quest_key):
                    continue
                coins = quest_coins if achieved else 0
                cur.execute("""INSERT INTO GameTeamQuestResults(team_id,month_key,quest_key,achieved,detail,
                        coins_per_member) OUTPUT INSERTED.id VALUES(?,?,?,?,?,?)""",
                            team_id, month, quest_key, 1 if achieved else 0, detail[:200], coins)
                result_id = int(cur.fetchone()[0])
                if not coins:
                    continue
                title = gd.QUEST_TITLES[quest_key]
                for member in members:
                    add_coins(cur, int(member["id"]), coins, "quest", "quest", result_id,
                              "مأموریت «%s» — %s" % (title, gd.month_label(month)), now, values)
                    notes.append((int(member["id"]), "مأموریت تیمی «%s» در %s انجام شد: %s سکه" % (
                        title, gd.month_label(month), gd.fa_digits(coins))))
        holidays = holiday_days(cur)
        for planner in fetch(cur, "SELECT id FROM Users WHERE role='planner' AND is_active=1"):
            uid = int(planner["id"])
            metrics = planner_metrics(cur, uid, start, after, holidays)
            for key, earned in (("no_queue", metrics["queue_decisions"] >= 3 and metrics["queue_slow"] == 0),
                                ("precise", gd.quest_on_time(metrics["team_on_time"], metrics["team_with_due"]))):
                if earned:
                    badge = award_badge(cur, uid, key, month, values, now)
                    if badge:
                        notes.append((uid, badge_note(badge)))
        issues = None
        for person in fetch(cur, "SELECT id FROM Users WHERE role='finance' AND is_active=1"):
            uid = int(person["id"])
            metrics = finance_metrics(cur, uid, month, start, after)
            issues = metrics["issues"] if issues is None else issues
            earned = [("on_schedule", metrics["mine_planned"] >= 1
                       and metrics["mine_on_time"] == metrics["mine_planned"]),
                      ("clean_books", issues == 0)]
            for key, ok_flag in earned:
                if ok_flag:
                    badge = award_badge(cur, uid, key, month, values, now)
                    if badge:
                        notes.append((uid, badge_note(badge)))
        return notes

    _periodic_lock = threading.Lock()
    _periodic_state = {"checked": 0.0}

    def maybe_periodic():
        """Close finished months lazily; the application has no scheduler."""
        if time.time() - _periodic_state["checked"] < 600:
            return
        if not _periodic_lock.acquire(blocking=False):
            return
        notes = []
        try:
            _periodic_state["checked"] = time.time()
            with db_lock:
                conn = get_conn()
                cur = conn.cursor()
                try:
                    values = settings(cur)
                    now = db_now(cur)
                    target = gd.previous_month_key(gd.month_key(now))
                    last = values.get("game_processed_month") or ""
                    installed = installed_at(cur)
                    cursor_key = gd.next_month_key(last) if last else (
                        gd.month_key(installed) if installed else target)
                    months = []
                    while cursor_key <= target and len(months) < 3:
                        months.append(cursor_key)
                        cursor_key = gd.next_month_key(cursor_key)
                    for month in months:
                        notes.extend(process_month(cur, month, values, now))
                    if months or not last:
                        save_setting(cur, "game_processed_month", max(target, last) if last else target)
                    conn.commit()
                except Exception:
                    rollback(conn)
                    raise
        except Exception as exc:
            LOG.exception("Gamification monthly processing failed: %s", exc)
        finally:
            _periodic_lock.release()
        for uid, text in notes:
            notify(uid, "game", text)

    # ── team missions shown live on the dashboard ──────────────────────────
    def quest_progress(cur, team_id, now):
        month = gd.month_key(now)
        start, end = gd.month_bounds(month)
        today = now.date()
        open_rows = fetch(cur, """SELECT t.due_jalali,t.due_at_assign FROM Tasks t
            JOIN ProjectTeams pt ON pt.id=t.project_team_id
            WHERE pt.team_id=? AND ISNULL(t.status,'') NOT IN ('done','rejected')""", team_id)
        overdue = sum(1 for t in open_rows if due_of(t) and due_of(t) < today)
        stats = team_month_tasks(cur, team_id, start, end)
        target, approved = team_month_money(cur, team_id, month)
        last = {r["quest_key"]: bool(r["achieved"]) for r in fetch(cur, """SELECT quest_key,achieved
            FROM GameTeamQuestResults WHERE team_id=? AND month_key=?""", team_id, gd.previous_month_key(month))}
        on_pct = gd.percent(stats["on_time"], stats["with_due"])
        money_pct = gd.percent(int(approved), int(target)) if target > 0 else None
        return [
            {"key": "zero_overdue", "title": gd.QUEST_TITLES["zero_overdue"],
             "value": "%s تسک معوق باز" % gd.fa_digits(overdue),
             "progress": 100 if overdue == 0 else 0, "ok": overdue == 0, "last": last.get("zero_overdue")},
            {"key": "on_time", "title": gd.QUEST_TITLES["on_time"],
             "value": "%s از %s تسک سروقت" % (gd.fa_digits(stats["on_time"]), gd.fa_digits(stats["with_due"])),
             "progress": on_pct or 0, "ok": gd.quest_on_time(stats["on_time"], stats["with_due"]),
             "last": last.get("on_time")},
            {"key": "finance_goal", "title": gd.QUEST_TITLES["finance_goal"],
             "value": ("%s٪ هدف این ماه" % gd.fa_digits(money_pct)) if money_pct is not None
             else "هدف این ماه تعریف نشده است",
             "progress": min(100, money_pct or 0), "ok": gd.quest_finance(target, approved),
             "last": last.get("finance_goal")},
        ]

    def season_ranking(cur, team_id, season):
        return fetch(cur, """SELECT u.id,u.display_name,u.username,ISNULL(SUM(x.points),0) AS points
            FROM TeamMembers tm JOIN Users u ON u.id=tm.user_id
            LEFT JOIN GameXpLedger x ON x.user_id=u.id AND x.season_key=?
            WHERE tm.team_id=? AND tm.is_active=1 AND u.is_active=1 AND u.role IN ('support','lead')
            GROUP BY u.id,u.display_name,u.username
            ORDER BY ISNULL(SUM(x.points),0) DESC,u.display_name""", season, team_id)

    def rank_payload(rows, uid, full):
        ranked = [{"user_id": int(r["id"]), "name": name_of(r), "points": int(r["points"] or 0),
                   "position": i + 1} for i, r in enumerate(rows)]
        mine = next((r for r in ranked if r["user_id"] == int(uid)), None)
        gap = None
        if mine and mine["position"] > 1:
            gap = ranked[mine["position"] - 2]["points"] - mine["points"]
        return {"top": ranked[:3], "me": mine, "gap": gap, "total": len(ranked),
                "rows": ranked if full else None}

    # ── routes: personal ────────────────────────────────────────────────────
    @app.route("/api/game/summary", methods=["POST"])
    @require_auth
    def api_game_summary():
        user = g.user
        maybe_periodic()
        notes = []
        try:
            with db_lock:
                conn = get_conn()
                cur = conn.cursor()
                try:
                    values = settings(cur)
                    now = db_now(cur)
                    uid, role = int(user["id"]), user.get("role")
                    out = {"role": role, "has_wallet": role in gd.WALLET_ROLES,
                           "earns_tasks": role in gd.TASK_EARNING_ROLES,
                           "monthly_stars": role in gd.MONTHLY_STAR_ROLES,
                           "shop_open": values.get("game_shop_open") == "1",
                           "points_per_coin": setting_int(values, "game_points_per_coin")}
                    season = gd.season_key(now)
                    out["season"] = {"key": season, "label": gd.season_label(season)}
                    if out["has_wallet"] and user_has_permission(user, "gamification.view_own"):
                        total = int(scalar(cur, "SELECT ISNULL(SUM(points),0) FROM GameXpLedger WHERE user_id=?",
                                           uid) or 0)
                        out["season"]["points"] = int(scalar(cur, """SELECT ISNULL(SUM(points),0)
                            FROM GameXpLedger WHERE user_id=? AND season_key=?""", uid, season) or 0)
                        out["level"] = gd.level_info(total, gd.parse_thresholds(values.get("game_level_thresholds")))
                        state = wallet(cur, uid, now)
                        out["coins"] = {"balance": state["balance"], "expiring_soon": state["expiring_soon"],
                                        "next_expiry": state["next_expiry"]}
                        out["badges"] = [dict(r, title=gd.BADGE_BY_KEY.get(r["badge_key"], {}).get("title"))
                                         for r in fetch(cur, """SELECT TOP 6 badge_key,period_key,awarded_at
                                             FROM GameUserBadges WHERE user_id=? ORDER BY awarded_at DESC""", uid)]
                        wished = fetch(cur, """SELECT i.id,i.name,i.price,i.is_active FROM ShopWishlist w
                            JOIN ShopItems i ON i.id=w.item_id WHERE w.user_id=? AND i.is_archived=0
                            ORDER BY w.created_at DESC""", uid)
                        festival = festival_prices(cur, now.date())
                        out["wishlist"] = [{"id": int(r["id"]), "name": r["name"], "is_active": bool(r["is_active"]),
                                            "price": festival.get(int(r["id"]), {}).get("price", int(r["price"])),
                                            "progress": min(100, int(max(0, state["balance"]) * 100
                                                                     // max(1, festival.get(int(r["id"]), {}).get("price", int(r["price"])))))}
                                           for r in wished]
                        if role in gd.TASK_EARNING_ROLES:
                            badge = check_steady(cur, uid, values, now)
                            if badge:
                                notes.append((uid, badge_note(badge)))
                        if state["expiring_soon"] > 0 and not scalar(cur, """SELECT TOP 1 1 FROM Notifications
                                WHERE user_id=? AND kind='game_expiry' AND created_at>=DATEADD(day,-7,GETDATE())""", uid):
                            notes.append((uid, "%s سکه شما تا یک ماه دیگر منقضی می‌شود" %
                                          gd.fa_digits(state["expiring_soon"]), "game_expiry"))
                    team = primary_team(cur, uid)
                    if team and (out["has_wallet"] or role in gd.CONTROLLER_ROLES):
                        out["team"] = {"id": int(team["team_id"]), "name": team["name"]}
                        out["quests"] = quest_progress(cur, int(team["team_id"]), now)
                        if user_has_permission(user, "gamification.team_board"):
                            out["rank"] = rank_payload(season_ranking(cur, int(team["team_id"]), season), uid, False)
                    conn.commit()
                except Exception:
                    rollback(conn)
                    raise
            for note in notes:
                notify(note[0], note[2] if len(note) > 2 else "game", note[1])
            return ok(**out)
        except Exception as exc:
            LOG.exception("game summary failed")
            return err("بخش امتیاز در دسترس نیست: %s" % exc)

    @app.route("/api/game/history", methods=["POST"])
    @require_auth
    def api_game_history():
        user = g.user
        try:
            with db_lock:
                cur = get_conn().cursor()
                now = db_now(cur)
                uid = int(user["id"])
                coins = fetch(cur, """SELECT TOP 200 id,amount,kind,note,created_at,expires_at
                    FROM GameCoinLedger WHERE user_id=? ORDER BY created_at DESC,id DESC""", uid)
                points = fetch(cur, """SELECT TOP 200 points,season_key,source_type,note,created_at
                    FROM GameXpLedger WHERE user_id=? ORDER BY created_at DESC,id DESC""", uid)
                badges = fetch(cur, """SELECT badge_key,period_key,coins,awarded_at FROM GameUserBadges
                    WHERE user_id=? ORDER BY awarded_at DESC""", uid)
                state = wallet(cur, uid, now)
            for row in coins:
                row["kind_label"] = COIN_KIND_LABELS.get(row["kind"], row["kind"])
            for row in badges:
                meta = gd.BADGE_BY_KEY.get(row["badge_key"], {})
                row["title"] = meta.get("title")
                row["desc"] = meta.get("desc")
            return ok(coins=coins, points=points, badges=badges, expired=state["expired_lots"],
                      balance=state["balance"])
        except Exception as exc:
            return err(public_error(exc))

    @app.route("/api/game/board", methods=["POST"])
    @require_auth
    def api_game_board():
        user = g.user
        data = body()
        try:
            with db_lock:
                cur = get_conn().cursor()
                now = db_now(cur)
                allowed = visible_team_ids(cur, user)
                team_id = gd.to_int(data.get("team_id"))
                if team_id is None:
                    team = primary_team(cur, user["id"])
                    team_id = int(team["team_id"]) if team else (allowed[0] if allowed else None)
                if team_id is None or team_id not in allowed:
                    return ok(teams=[], board=None, compare=[])
                season = str(data.get("season") or gd.season_key(now))
                full = user_has_permission(user, "gamification.full_ranking")
                board = rank_payload(season_ranking(cur, team_id, season), user["id"], full)
                teams = fetch(cur, "SELECT id,name FROM Teams WHERE is_active=1 AND id IN (%s) ORDER BY name"
                              % ",".join("?" for _ in allowed), *allowed) if allowed else []
                compare = []
                for team in teams:
                    rows = season_ranking(cur, int(team["id"]), season)
                    if rows:
                        compare.append({"team_id": int(team["id"]), "name": team["name"], "members": len(rows),
                                        "average": round(sum(int(r["points"] or 0) for r in rows) / len(rows))})
                compare.sort(key=lambda x: -x["average"])
                seasons = [r["season_key"] for r in fetch(cur, """SELECT DISTINCT season_key FROM GameXpLedger
                    ORDER BY season_key DESC""")]
            if season not in seasons:
                seasons.insert(0, season)
            return ok(team_id=team_id, season=season, season_label=gd.season_label(season),
                      seasons=[{"key": k, "label": gd.season_label(k)} for k in seasons],
                      teams=teams, board=board, compare=compare, full=full)
        except Exception as exc:
            return err(public_error(exc))

    @app.route("/api/game/hall", methods=["POST"])
    @require_auth
    def api_game_hall():
        user = g.user
        if not (user_has_permission(user, "shop.view") or user_has_permission(user, "gamification.view_own")):
            return err("شما دسترسی لازم برای این بخش را ندارید", 403)
        try:
            with db_lock:
                cur = get_conn().cursor()
                now = db_now(cur)
                current = gd.season_key(now)
                mine = {(r["badge_key"]) : int(r["n"]) for r in fetch(cur, """SELECT badge_key,COUNT(*) AS n
                    FROM GameUserBadges WHERE user_id=? GROUP BY badge_key""", user["id"])}
                holders = {r["badge_key"]: int(r["n"]) for r in fetch(cur, """SELECT badge_key,
                    COUNT(DISTINCT user_id) AS n FROM GameUserBadges GROUP BY badge_key""")}
                allowed = set(visible_team_ids(cur, user))
                rows = fetch(cur, """SELECT x.season_key,x.user_id,u.display_name,u.username,
                        SUM(x.points) AS points,
                        (SELECT TOP 1 tm.team_id FROM TeamMembers tm WHERE tm.user_id=x.user_id
                           AND tm.is_active=1 ORDER BY tm.is_primary DESC,tm.team_id) AS team_id
                    FROM GameXpLedger x JOIN Users u ON u.id=x.user_id
                    WHERE x.season_key<>?
                    GROUP BY x.season_key,x.user_id,u.display_name,u.username""", current)
                team_names = {int(r["id"]): r["name"] for r in fetch(cur, "SELECT id,name FROM Teams")}
            seasons = {}
            for row in rows:
                team_id = row["team_id"]
                if team_id is None or (allowed and int(team_id) not in allowed) or int(row["points"] or 0) <= 0:
                    continue
                seasons.setdefault(row["season_key"], {}).setdefault(int(team_id), []).append(
                    {"name": name_of(row), "points": int(row["points"] or 0), "user_id": int(row["user_id"])})
            hall = []
            for key in sorted(seasons, reverse=True):
                teams = []
                for team_id, people in seasons[key].items():
                    people.sort(key=lambda p: -p["points"])
                    teams.append({"team_id": team_id, "team": team_names.get(team_id, ""), "top": people[:3]})
                teams.sort(key=lambda t: t["team"])
                hall.append({"season": key, "label": gd.season_label(key), "teams": teams})
            badges = [dict(b, roles=list(b["roles"]), mine=mine.get(b["key"], 0), holders=holders.get(b["key"], 0))
                      for b in gd.BADGES]
            return ok(badges=badges, hall=hall)
        except Exception as exc:
            return err(public_error(exc))

    @app.route("/api/game/kudos_give", methods=["POST"])
    @require_auth
    def api_game_kudos_give():
        user = g.user
        data = body()
        task_id = gd.to_int(data.get("task_id"))
        to_user = gd.to_int(data.get("to_user"))
        note = str(data.get("note") or "").strip()[:200] or None
        if not task_id or not to_user:
            return err("تسک و همکار را انتخاب کنید")
        if int(to_user) == int(user["id"]):
            return err("نمی‌توانید از خودتان قدردانی کنید")
        text = None
        try:
            with db_lock:
                conn = get_conn()
                cur = conn.cursor()
                try:
                    values = settings(cur)
                    now = db_now(cur)
                    task = fetch_one(cur, "SELECT id,title,status,staff_id FROM Tasks WHERE id=?", task_id)
                    if not task:
                        return err("تسک یافت نشد")
                    on_task = (task["staff_id"] is not None and int(task["staff_id"]) == to_user) or scalar(
                        cur, "SELECT 1 FROM TaskAssignees WHERE task_id=? AND user_id=?", task_id, to_user)
                    if not on_task:
                        return err("این همکار روی این تسک کار نکرده است")
                    if not shares_team(cur, user, to_user):
                        return err("این همکار در تیم شما نیست", 403)
                    week_start = now - _dt.timedelta(days=(now.weekday() - 5) % 7)
                    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
                    used = int(scalar(cur, "SELECT COUNT(*) FROM GameKudos WHERE from_user=? AND created_at>=?",
                                      user["id"], week_start) or 0)
                    if used >= setting_int(values, "game_kudos_per_week"):
                        return err("سهم «ممنونم» این هفته شما تمام شده است")
                    if scalar(cur, "SELECT 1 FROM GameKudos WHERE from_user=? AND to_user=? AND task_id=?",
                              user["id"], to_user, task_id):
                        return err("برای این تسک قبلاً از این همکار قدردانی کرده‌اید")
                    month_start, _ = gd.month_bounds(gd.month_key(now))
                    repeat = scalar(cur, """SELECT 1 FROM GameKudos WHERE from_user=? AND to_user=?
                        AND coins>0 AND created_at>=?""", user["id"], to_user, month_start)
                    target = user_info(cur, to_user)
                    coins = 0
                    if not repeat and target and target["role"] in gd.WALLET_ROLES:
                        coins = setting_int(values, "game_kudos_coins")
                    cur.execute("""INSERT INTO GameKudos(from_user,to_user,task_id,note,coins)
                        OUTPUT INSERTED.id VALUES(?,?,?,?,?)""", user["id"], to_user, task_id, note, coins)
                    kudos_id = int(cur.fetchone()[0])
                    if coins:
                        add_coins(cur, to_user, coins, "kudos", "kudos", kudos_id,
                                  "قدردانی %s" % name_of(user), now, values)
                    conn.commit()
                    text = "%s بابت تسک «%s» از شما قدردانی کرد%s" % (
                        name_of(user), (task["title"] or "")[:60],
                        ": %s سکه" % gd.fa_digits(coins) if coins else "")
                except Exception:
                    rollback(conn)
                    raise
            notify(to_user, "game", text, task_id)
            return ok(coins=coins)
        except Exception as exc:
            return err(public_error(exc))

    # ── routes: shop ────────────────────────────────────────────────────────
    def festival_prices(cur, today):
        out = {}
        for row in fetch(cur, """SELECT fi.item_id,fi.discount_percent,f.id AS festival_id,f.title,f.end_date,
                i.price FROM ShopFestivalItems fi JOIN ShopFestivals f ON f.id=fi.festival_id
            JOIN ShopItems i ON i.id=fi.item_id
            WHERE ? BETWEEN f.start_date AND f.end_date""", today):
            out[int(row["item_id"])] = {"percent": int(row["discount_percent"]), "festival_id": int(row["festival_id"]),
                                        "title": row["title"], "ends": row["end_date"],
                                        "price": gd.discounted_price(row["price"], row["discount_percent"])}
        return out

    ITEM_COLUMNS = """i.id,i.name,i.description,i.item_type,i.price,i.is_active,i.is_archived,i.stock_total,
        i.per_user_monthly_limit,i.sale_from,i.sale_to,i.show_in_public,i.leave_mode,i.leave_hours,
        i.reward_amount,i.team_goal,i.cosmetic_slot,i.cosmetic_value,i.image_version,
        CASE WHEN i.image_data IS NULL THEN 0 ELSE 1 END AS has_image"""

    def decorate_items(cur, items, uid, now):
        today = now.date()
        festival = festival_prices(cur, today)
        sold = {int(r["item_id"]): int(r["n"]) for r in fetch(cur, """SELECT item_id,COUNT(*) AS n FROM ShopOrders
            WHERE status<>'cancelled' AND item_type<>'team_pot' GROUP BY item_id""")}
        month_start, month_end = gd.month_bounds(gd.month_key(now))
        mine = {int(r["item_id"]): int(r["n"]) for r in fetch(cur, """SELECT item_id,COUNT(*) AS n FROM ShopOrders
            WHERE user_id=? AND gift_id IS NULL AND status<>'cancelled' AND created_at>=? AND created_at<?
            GROUP BY item_id""", uid, month_start, month_end + _dt.timedelta(days=1))}
        wished = {int(r["item_id"]) for r in fetch(cur, "SELECT item_id FROM ShopWishlist WHERE user_id=?", uid)}
        team = primary_team(cur, uid)
        pots = {}
        if team:
            for r in fetch(cur, """SELECT o.item_id,SUM(o.price_paid) AS collected FROM ShopOrders o
                JOIN GameTeamPots p ON p.item_id=o.item_id AND p.team_id=o.team_id AND p.round_no=o.pot_round
                WHERE o.team_id=? AND o.status='contributed' GROUP BY o.item_id""", team["team_id"]):
                pots[int(r["item_id"])] = int(r["collected"] or 0)
        for item in items:
            ident = int(item["id"])
            item["type_label"] = dict(gd.ITEM_TYPES).get(item["item_type"], item["item_type"])
            item["sold"] = sold.get(ident, 0)
            item["mine_this_month"] = mine.get(ident, 0)
            item["wished"] = ident in wished
            item["festival"] = festival.get(ident)
            item["final_price"] = festival[ident]["price"] if ident in festival else int(item["price"])
            if item["item_type"] == "team_pot":
                item["pot"] = {"collected": pots.get(ident, 0), "goal": item["team_goal"],
                               "team": team["name"] if team else None}
            item["sale_from_fa"] = gd.jalali_text(item["sale_from"]) if item.get("sale_from") else None
            item["sale_to_fa"] = gd.jalali_text(item["sale_to"]) if item.get("sale_to") else None
        return items

    @app.route("/api/game/shop/items", methods=["POST"])
    @require_auth
    def api_game_shop_items():
        user = g.user
        maybe_periodic()
        try:
            with db_lock:
                cur = get_conn().cursor()
                values = settings(cur)
                now = db_now(cur)
                items = fetch(cur, "SELECT %s FROM ShopItems i WHERE i.is_archived=0 ORDER BY i.is_active DESC,i.price,i.id"
                              % ITEM_COLUMNS)
                items = decorate_items(cur, items, user["id"], now)
                balance = wallet(cur, user["id"], now)["balance"] if user.get("role") in gd.WALLET_ROLES else None
                owned = [int(r["item_id"]) for r in fetch(cur, """SELECT DISTINCT item_id FROM ShopOrders
                    WHERE user_id=? AND item_type='cosmetic' AND status='active'""", user["id"])]
                equipped = {r["slot"]: {"item_id": r["item_id"], "value": r["value"]} for r in fetch(cur,
                            "SELECT slot,item_id,value FROM GameCosmetics WHERE user_id=?", user["id"])}
            return ok(items=items, balance=balance, shop_open=values.get("game_shop_open") == "1",
                      has_wallet=user.get("role") in gd.WALLET_ROLES, owned_cosmetics=owned, equipped=equipped,
                      all_cosmetics=user.get("role") in gd.CONTROLLER_ROLES)
        except Exception as exc:
            return err("فروشگاه در دسترس نیست: %s" % exc, items=[])

    @app.route("/api/game/shop/item_image", methods=["POST"])
    @require_auth
    def api_game_shop_item_image():
        ident = gd.to_int(body().get("id"))
        try:
            with db_lock:
                cur = get_conn().cursor()
                row = fetch_one(cur, "SELECT image_mime,image_data,image_version FROM ShopItems WHERE id=?", ident)
            if not row or not row["image_data"]:
                return ok(data_url=None)
            encoded = base64.b64encode(bytes(row["image_data"])).decode("ascii")
            return ok(data_url="data:%s;base64,%s" % (row["image_mime"] or "image/jpeg", encoded),
                      version=row["image_version"])
        except Exception as exc:
            return err(public_error(exc))

    def create_leave(cur, uid, item, order_id, day, start_time):
        if item.get("leave_mode") == "hours":
            end_time = gd.hourly_end(start_time, item.get("leave_hours") or 1)
            if not end_time:
                raise ValueError("ساعت شروع مرخصی معتبر نیست یا مرخصی از نیمه‌شب می‌گذرد")
            leave_type, start_value = "hourly", start_time
        else:
            leave_type, start_value, end_time = "daily", None, None
        text = gd.jalali_text(day)
        cur.execute("""INSERT INTO Leaves(staff_id,leave_date,end_date,leave_type,start_time,end_time,reason,
                created_by,status,is_reward,reward_order_id)
            OUTPUT INSERTED.id VALUES(?,?,?,?,?,?,?,?,N'approved',1,?)""",
                    uid, text, text, leave_type, start_value, end_time,
                    "مرخصی تشویقی (فروشگاه): %s" % item["name"][:120], uid, order_id)
        return int(cur.fetchone()[0])

    def validate_booking(cur, item, day_text, start_time, today):
        day = gd.parse_jalali(day_text)
        if item["item_type"] not in gd.DATED_TYPES:
            return None, None, None
        if day is None:
            return None, None, "روز استفاده را انتخاب کنید"
        if day <= today:
            return None, None, "روز انتخابی باید از فردا به بعد باشد"
        if gd.is_day_off(day, holiday_days(cur)):
            return None, None, "روز انتخاب‌شده تعطیل است؛ یک روز کاری انتخاب کنید"
        if item["item_type"] == "leave" and item.get("leave_mode") == "hours":
            if not gd.hourly_end(start_time, item.get("leave_hours") or 1):
                return None, None, "ساعت شروع مرخصی را درست وارد کنید"
            return day, str(start_time), None
        return day, None, None

    def equip(cur, uid, item):
        cur.execute("""IF EXISTS(SELECT 1 FROM GameCosmetics WHERE user_id=? AND slot=?)
            UPDATE GameCosmetics SET item_id=?,value=?,updated_at=GETDATE() WHERE user_id=? AND slot=?
            ELSE INSERT INTO GameCosmetics(user_id,slot,item_id,value) VALUES(?,?,?,?)""",
                    uid, item["cosmetic_slot"], item["id"], item["cosmetic_value"], uid, item["cosmetic_slot"],
                    uid, item["cosmetic_slot"], item["id"], item["cosmetic_value"])

    def status_for(item_type, gifted=False):
        if item_type in gd.DATED_TYPES:
            return "awaiting_date" if gifted else "scheduled"
        return {"money": "pending_payment", "cosmetic": "active", "team_pot": "pending_delivery"}.get(
            item_type, "pending_delivery")

    @app.route("/api/game/shop/buy", methods=["POST"])
    @require_auth
    def api_game_shop_buy():
        user = g.user
        data = body()
        item_id = gd.to_int(data.get("item_id"))
        if user.get("role") not in gd.WALLET_ROLES:
            return err("این نقش کیف پول سکه ندارد", 403)
        notes = []
        try:
            with db_lock:
                conn = get_conn()
                cur = conn.cursor()
                try:
                    values = settings(cur)
                    now = db_now(cur)
                    today = now.date()
                    uid = int(user["id"])
                    if values.get("game_shop_open") != "1":
                        return err("فروشگاه هنوز باز نشده است")
                    lock_wallet(cur, uid)
                    item = fetch_one(cur, "SELECT %s FROM ShopItems i WITH (UPDLOCK,HOLDLOCK) WHERE i.id=?"
                                     % ITEM_COLUMNS, item_id)
                    if not item:
                        return err("این آیتم در فروشگاه نیست")
                    festival = festival_prices(cur, today).get(int(item["id"]))
                    price = festival["price"] if festival else int(item["price"])
                    team = None
                    if item["item_type"] == "team_pot":
                        team = primary_team(cur, uid)
                        if not team:
                            return err("برای مشارکت در صندوق تیم باید عضو یک تیم باشید")
                        cur.execute("""IF NOT EXISTS(SELECT 1 FROM GameTeamPots WHERE item_id=? AND team_id=?)
                            INSERT INTO GameTeamPots(item_id,team_id,round_no) VALUES(?,?,1)""",
                                    item_id, team["team_id"], item_id, team["team_id"])
                        round_no = int(scalar(cur, """SELECT round_no FROM GameTeamPots WITH (UPDLOCK,HOLDLOCK)
                            WHERE item_id=? AND team_id=?""", item_id, team["team_id"]))
                        collected = int(scalar(cur, """SELECT ISNULL(SUM(price_paid),0) FROM ShopOrders
                            WHERE item_id=? AND team_id=? AND pot_round=? AND status='contributed'""",
                                               item_id, team["team_id"], round_no) or 0)
                        remaining = max(1, int(item["team_goal"] or 1) - collected)
                        amount = gd.to_int(data.get("amount"), int(item["price"]))
                        if amount is None or amount < 1:
                            return err("مقدار مشارکت باید حداقل یک سکه باشد")
                        price = min(amount, remaining)
                        festival = None
                    month_start, month_end = gd.month_bounds(gd.month_key(now))
                    month_count = int(scalar(cur, """SELECT COUNT(*) FROM ShopOrders WHERE user_id=? AND item_id=?
                        AND gift_id IS NULL AND status<>'cancelled' AND created_at>=? AND created_at<?""",
                                             uid, item_id, month_start, month_end + _dt.timedelta(days=1)) or 0)
                    stock_used = int(scalar(cur, "SELECT COUNT(*) FROM ShopOrders WHERE item_id=? AND status<>'cancelled'",
                                            item_id) or 0)
                    day, start_time, problem = validate_booking(cur, item, data.get("date"), data.get("start_time"),
                                                                today)
                    if problem:
                        return err(problem)
                    balance = wallet(cur, uid, now)["balance"]
                    problem = gd.purchase_error(item, today, balance, price, month_count, stock_used,
                                                day if item["item_type"] in gd.DATED_TYPES else None)
                    if problem:
                        return err(problem)
                    status = "contributed" if item["item_type"] == "team_pot" else status_for(item["item_type"])
                    cur.execute("""INSERT INTO ShopOrders(item_id,user_id,item_type,item_name,base_price,price_paid,
                            discount_percent,festival_id,status,scheduled_date,start_time,team_id,pot_round,
                            show_in_public)
                        OUTPUT INSERTED.id VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                item_id, uid, item["item_type"], item["name"], int(item["price"]), price,
                                festival["percent"] if festival else None,
                                festival["festival_id"] if festival else None, status,
                                gd.jalali_text(day) if day else None, start_time,
                                team["team_id"] if team else None,
                                round_no if team else None, 1 if item["show_in_public"] else 0)
                    order_id = int(cur.fetchone()[0])
                    entry = add_coins(cur, uid, -price, "spend", "order", order_id, "خرید «%s»" % item["name"][:100],
                                      now, values)
                    cur.execute("UPDATE ShopOrders SET coin_entry_id=? WHERE id=?", entry, order_id)
                    if item["item_type"] == "leave":
                        leave_id = create_leave(cur, uid, item, order_id, day, start_time)
                        cur.execute("UPDATE ShopOrders SET leave_id=? WHERE id=?", leave_id, order_id)
                    elif item["item_type"] == "cosmetic":
                        equip(cur, uid, item)
                    elif item["item_type"] == "team_pot" and collected + price >= int(item["team_goal"] or 0):
                        cur.execute("""INSERT INTO ShopOrders(item_id,user_id,item_type,item_name,base_price,price_paid,
                                status,team_id,pot_round,show_in_public,note)
                            VALUES(?,?,?,?,0,0,'pending_delivery',?,?,?,?)""",
                                    item_id, uid, "team_pot", item["name"], team["team_id"], round_no,
                                    1 if item["show_in_public"] else 0,
                                    "صندوق تیم «%s» کامل شد" % team["name"])
                        cur.execute("UPDATE GameTeamPots SET round_no=round_no+1 WHERE item_id=? AND team_id=?",
                                    item_id, team["team_id"])
                        for member in fetch(cur, """SELECT user_id FROM TeamMembers
                            WHERE team_id=? AND is_active=1""", team["team_id"]):
                            notes.append((int(member["user_id"]), "صندوق تیم «%s» کامل شد: %s" % (
                                team["name"], item["name"])))
                    conn.commit()
                except Exception:
                    rollback(conn)
                    raise
            for uid_note, text in notes:
                notify(uid_note, "game", text)
            audit("game_buy", "خرید آیتم #%s (%s سکه)" % (item_id, price))
            return ok(order_id=order_id, price=price)
        except ValueError as exc:
            return err(public_error(exc))
        except Exception as exc:
            LOG.exception("purchase failed")
            return err("خرید انجام نشد: %s" % exc)

    @app.route("/api/game/shop/my_orders", methods=["POST"])
    @require_auth
    def api_game_shop_my_orders():
        user = g.user
        try:
            with db_lock:
                cur = get_conn().cursor()
                now = db_now(cur)
                rows = fetch(cur, """SELECT o.id,o.item_id,o.item_type,o.item_name,o.price_paid,o.base_price,
                        o.discount_percent,o.status,o.scheduled_date,o.start_time,o.gift_id,o.created_at,
                        o.fulfilled_at,o.note,i.leave_mode,i.leave_hours
                    FROM ShopOrders o LEFT JOIN ShopItems i ON i.id=o.item_id
                    WHERE o.user_id=? ORDER BY o.created_at DESC,o.id DESC""", user["id"])
            today = now.date()
            for row in rows:
                row["status_label"] = ORDER_LABELS.get(row["status"], row["status"])
                row["type_label"] = dict(gd.ITEM_TYPES).get(row["item_type"], row["item_type"])
                booked = gd.parse_jalali(row["scheduled_date"])
                row["can_change"] = (row["status"] == "awaiting_date" or
                                     (row["status"] == "scheduled" and gd.can_change_booking(booked, today)))
                row["can_cancel"] = row["status"] == "scheduled" and gd.can_change_booking(booked, today)
            return ok(rows=rows)
        except Exception as exc:
            return err(public_error(exc), rows=[])

    def owned_order(cur, uid, order_id):
        return fetch_one(cur, """SELECT o.*,i.leave_mode,i.leave_hours,i.name AS live_name
            FROM ShopOrders o LEFT JOIN ShopItems i ON i.id=o.item_id
            WHERE o.id=? AND o.user_id=?""", order_id, uid)

    @app.route("/api/game/shop/order_reschedule", methods=["POST"])
    @require_auth
    def api_game_shop_order_reschedule():
        user = g.user
        data = body()
        try:
            with db_lock:
                conn = get_conn()
                cur = conn.cursor()
                try:
                    now = db_now(cur)
                    today = now.date()
                    order = owned_order(cur, user["id"], gd.to_int(data.get("order_id")))
                    if not order or order["item_type"] not in gd.DATED_TYPES:
                        return err("این خرید روز استفاده ندارد")
                    booked = gd.parse_jalali(order["scheduled_date"])
                    if order["status"] == "scheduled" and not gd.can_change_booking(booked, today):
                        return err("روز استفاده را فقط تا روز قبل از آن می‌توانید تغییر دهید")
                    if order["status"] not in ("scheduled", "awaiting_date"):
                        return err("این خرید قابل تغییر نیست")
                    item = {"item_type": order["item_type"], "leave_mode": order["leave_mode"],
                            "leave_hours": order["leave_hours"], "name": order["live_name"] or order["item_name"]}
                    day, start_time, problem = validate_booking(cur, item, data.get("date"), data.get("start_time"),
                                                                today)
                    if problem:
                        return err(problem)
                    if order["item_type"] == "leave":
                        if order["leave_id"]:
                            cur.execute("DELETE FROM Leaves WHERE id=? AND is_reward=1", order["leave_id"])
                        leave_id = create_leave(cur, user["id"], item, order["id"], day, start_time)
                        cur.execute("UPDATE ShopOrders SET leave_id=? WHERE id=?", leave_id, order["id"])
                    cur.execute("""UPDATE ShopOrders SET scheduled_date=?,start_time=?,status='scheduled'
                        WHERE id=?""", gd.jalali_text(day), start_time, order["id"])
                    conn.commit()
                except Exception:
                    rollback(conn)
                    raise
            return ok()
        except ValueError as exc:
            return err(public_error(exc))
        except Exception as exc:
            return err(public_error(exc))

    @app.route("/api/game/shop/order_cancel", methods=["POST"])
    @require_auth
    def api_game_shop_order_cancel():
        user = g.user
        data = body()
        try:
            with db_lock:
                conn = get_conn()
                cur = conn.cursor()
                try:
                    values = settings(cur)
                    now = db_now(cur)
                    lock_wallet(cur, user["id"])
                    order = owned_order(cur, user["id"], gd.to_int(data.get("order_id")))
                    if not order or order["status"] != "scheduled":
                        return err("این خرید قابل لغو نیست")
                    if not gd.can_change_booking(gd.parse_jalali(order["scheduled_date"]), now.date()):
                        return err("خرید را فقط تا روز قبل از روز استفاده می‌توانید لغو کنید")
                    if order["leave_id"]:
                        cur.execute("DELETE FROM Leaves WHERE id=? AND is_reward=1", order["leave_id"])
                    cur.execute("UPDATE ShopOrders SET status='cancelled',leave_id=NULL WHERE id=?", order["id"])
                    refunded = 0
                    if order["price_paid"] and order["coin_entry_id"]:
                        add_coins(cur, user["id"], int(order["price_paid"]), "refund", "order", order["id"],
                                  "لغو «%s»" % order["item_name"][:100], now, values,
                                  reverses_id=order["coin_entry_id"])
                        refunded = int(order["price_paid"])
                    conn.commit()
                except Exception:
                    rollback(conn)
                    raise
            return ok(refunded=refunded)
        except Exception as exc:
            return err(public_error(exc))

    @app.route("/api/game/shop/wishlist_toggle", methods=["POST"])
    @require_auth
    def api_game_shop_wishlist_toggle():
        user = g.user
        item_id = gd.to_int(body().get("item_id"))
        try:
            with db_lock:
                conn = get_conn()
                cur = conn.cursor()
                try:
                    if scalar(cur, "SELECT 1 FROM ShopWishlist WHERE user_id=? AND item_id=?", user["id"], item_id):
                        cur.execute("DELETE FROM ShopWishlist WHERE user_id=? AND item_id=?", user["id"], item_id)
                        wished = False
                    else:
                        if not scalar(cur, "SELECT 1 FROM ShopItems WHERE id=? AND is_archived=0", item_id):
                            return err("این آیتم در فروشگاه نیست")
                        cur.execute("INSERT INTO ShopWishlist(user_id,item_id) VALUES(?,?)", user["id"], item_id)
                        wished = True
                    conn.commit()
                except Exception:
                    rollback(conn)
                    raise
            return ok(wished=wished)
        except Exception as exc:
            return err(public_error(exc))

    @app.route("/api/game/shop/feed", methods=["POST"])
    @require_auth
    def api_game_shop_feed():
        try:
            with db_lock:
                cur = get_conn().cursor()
                purchases = fetch(cur, """SELECT TOP 80 o.id,o.item_name,o.item_type,o.price_paid,o.status,
                        o.created_at,o.note,u.display_name,u.username,t.name AS team_name
                    FROM ShopOrders o JOIN Users u ON u.id=o.user_id LEFT JOIN Teams t ON t.id=o.team_id
                    WHERE o.show_in_public=1 AND o.gift_id IS NULL AND o.status<>'cancelled'
                    ORDER BY o.created_at DESC,o.id DESC""")
                gifts = fetch(cur, """SELECT TOP 100 s.id,s.reason,s.link_type,s.link_id,s.created_at,
                        i.name AS item_name,tu.display_name AS to_name,fu.display_name AS from_name
                    FROM ShopGifts s JOIN ShopItems i ON i.id=s.item_id
                    JOIN Users tu ON tu.id=s.to_user JOIN Users fu ON fu.id=s.from_user
                    ORDER BY s.created_at DESC,s.id DESC""")
                link_names = link_titles(cur, gifts)
            for row in purchases:
                row["name"] = name_of(row)
                row["type_label"] = dict(gd.ITEM_TYPES).get(row["item_type"], row["item_type"])
            for row in gifts:
                row["link_label"] = link_names.get((row["link_type"], row["link_id"]), "")
            return ok(purchases=purchases, gifts=gifts)
        except Exception as exc:
            return err(public_error(exc), purchases=[], gifts=[])

    def link_titles(cur, gifts):
        titles = {}
        sources = {"task": "SELECT id,title AS label FROM Tasks WHERE id IN (%s)",
                   "project": "SELECT id,name AS label FROM Projects WHERE id IN (%s)",
                   "contract": "SELECT id,COALESCE(title,contract_number,CAST(id AS NVARCHAR(20))) AS label FROM Contracts WHERE id IN (%s)"}
        for kind, sql in sources.items():
            ids = sorted({int(r["link_id"]) for r in gifts if r["link_type"] == kind})
            if not ids:
                continue
            try:
                for row in fetch(cur, sql % ",".join("?" for _ in ids), *ids):
                    titles[(kind, int(row["id"]))] = row["label"]
            except Exception as exc:
                LOG.warning("Could not name %s links: %s", kind, exc)
        return titles

    @app.route("/api/game/cosmetics", methods=["POST"])
    @require_auth
    def api_game_cosmetics():
        try:
            with db_lock:
                cur = get_conn().cursor()
                rows = fetch(cur, "SELECT user_id,slot,value FROM GameCosmetics")
            out = {}
            for row in rows:
                out.setdefault(str(row["user_id"]), {})[row["slot"]] = row["value"]
            return ok(map=out)
        except Exception as exc:
            return err(public_error(exc), map={})

    @app.route("/api/game/shop/equip", methods=["POST"])
    @require_auth
    def api_game_shop_equip():
        user = g.user
        data = body()
        slot = str(data.get("slot") or "")
        item_id = gd.to_int(data.get("item_id"))
        if slot not in gd.COSMETIC_SLOTS:
            return err("نوع آیتم تزئینی معتبر نیست")
        try:
            with db_lock:
                conn = get_conn()
                cur = conn.cursor()
                try:
                    if not item_id:
                        cur.execute("DELETE FROM GameCosmetics WHERE user_id=? AND slot=?", user["id"], slot)
                    else:
                        item = fetch_one(cur, """SELECT id,cosmetic_slot,cosmetic_value FROM ShopItems
                            WHERE id=? AND item_type='cosmetic' AND cosmetic_slot=?""", item_id, slot)
                        if not item:
                            return err("این آیتم تزئینی یافت نشد")
                        controller = user.get("role") in gd.CONTROLLER_ROLES
                        owns = scalar(cur, """SELECT 1 FROM ShopOrders WHERE user_id=? AND item_id=?
                            AND status='active'""", user["id"], item_id)
                        if not (controller or owns):
                            return err("این آیتم را هنوز نخریده‌اید")
                        equip(cur, user["id"], item)
                    conn.commit()
                except Exception:
                    rollback(conn)
                    raise
            return ok()
        except Exception as exc:
            return err(public_error(exc))

    # ── routes: administration ──────────────────────────────────────────────
    def decode_image(value):
        if not value:
            return None, None
        text = str(value)
        if not text.startswith("data:") or ";base64," not in text:
            raise ValueError("تصویر معتبر نیست")
        header, encoded = text.split(",", 1)
        mime = header[5:].split(";")[0].lower()
        if mime not in IMAGE_MIMES:
            raise ValueError("فقط تصویر PNG، JPEG، WEBP یا GIF پذیرفته می‌شود")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("تصویر خراب است")
        if len(raw) > MAX_IMAGE_BYTES:
            raise ValueError("حجم تصویر زیاد است؛ حداکثر ۷۰۰ کیلوبایت")
        return mime, raw

    @app.route("/api/game/admin/items", methods=["POST"])
    @require_auth
    def api_game_admin_items():
        user = g.user
        try:
            with db_lock:
                cur = get_conn().cursor()
                now = db_now(cur)
                items = fetch(cur, "SELECT %s FROM ShopItems i ORDER BY i.is_archived,i.is_active DESC,i.id DESC"
                              % ITEM_COLUMNS)
                items = decorate_items(cur, items, user["id"], now)
                daily = scalar(cur, """SELECT CAST(ISNULL(SUM(c.amount),0) AS FLOAT)
                    FROM GameCoinLedger c JOIN Users u ON u.id=c.user_id
                    WHERE u.role IN ('support','lead') AND c.amount>0 AND c.kind IN ('task','badge','quest','kudos')
                      AND c.created_at>=DATEADD(day,-30,GETDATE())""") or 0
                supports = int(scalar(cur, "SELECT COUNT(*) FROM Users WHERE role IN ('support','lead') AND is_active=1") or 0)
            per_day = (float(daily) / supports / 26.0) if supports and daily else None
            return ok(items=items, support_daily_coins=per_day, types=[{"key": k, "label": v} for k, v in gd.ITEM_TYPES])
        except Exception as exc:
            return err(public_error(exc), items=[])

    @app.route("/api/game/admin/item_save", methods=["POST"])
    @require_auth
    def api_game_admin_item_save():
        user = g.user
        data = body()
        clean, problem = gd.validate_item(data)
        if problem:
            return err(problem)
        try:
            mime, raw = decode_image(data.get("image"))
        except ValueError as exc:
            return err(public_error(exc))
        ident = gd.to_int(data.get("id"))
        try:
            with db_lock:
                conn = get_conn()
                cur = conn.cursor()
                try:
                    columns = ("name", "description", "item_type", "price", "is_active", "stock_total",
                               "per_user_monthly_limit", "sale_from", "sale_to", "show_in_public", "leave_mode",
                               "leave_hours", "reward_amount", "team_goal", "cosmetic_slot", "cosmetic_value")
                    params = [clean[c] if not isinstance(clean[c], bool) else (1 if clean[c] else 0) for c in columns]
                    if ident:
                        if not scalar(cur, "SELECT 1 FROM ShopItems WHERE id=?", ident):
                            return err("آیتم یافت نشد")
                        cur.execute("UPDATE ShopItems SET %s,updated_by=?,updated_at=GETDATE() WHERE id=?"
                                    % ",".join("%s=?" % c for c in columns), *(params + [user["id"], ident]))
                    else:
                        cur.execute("INSERT INTO ShopItems(%s,created_by) OUTPUT INSERTED.id VALUES(%s,?)"
                                    % (",".join(columns), ",".join("?" for _ in columns)), *(params + [user["id"]]))
                        ident = int(cur.fetchone()[0])
                    if raw is not None:
                        cur.execute("""UPDATE ShopItems SET image_mime=?,image_data=?,image_version=image_version+1
                            WHERE id=?""", mime, raw, ident)
                    elif data.get("remove_image"):
                        cur.execute("""UPDATE ShopItems SET image_mime=NULL,image_data=NULL,
                            image_version=image_version+1 WHERE id=?""", ident)
                    conn.commit()
                except Exception:
                    rollback(conn)
                    raise
            audit("game_item_save", "آیتم #%s: %s" % (ident, clean["name"]))
            return ok(id=ident)
        except Exception as exc:
            return err(public_error(exc))

    @app.route("/api/game/admin/item_delete", methods=["POST"])
    @require_auth
    def api_game_admin_item_delete():
        ident = gd.to_int(body().get("id"))
        try:
            with db_lock:
                conn = get_conn()
                cur = conn.cursor()
                try:
                    item = fetch_one(cur, "SELECT id,name FROM ShopItems WHERE id=?", ident)
                    if not item:
                        return err("آیتم یافت نشد")
                    used = scalar(cur, "SELECT TOP 1 1 FROM ShopOrders WHERE item_id=?", ident) or scalar(
                        cur, "SELECT TOP 1 1 FROM ShopGifts WHERE item_id=?", ident)
                    if used:
                        # Bought at least once: archived, so every purchase keeps its item.
                        cur.execute("UPDATE ShopItems SET is_archived=1,is_active=0,updated_at=GETDATE() WHERE id=?",
                                    ident)
                        cur.execute("DELETE FROM ShopWishlist WHERE item_id=?", ident)
                        archived = True
                    else:
                        cur.execute("DELETE FROM ShopItems WHERE id=?", ident)
                        archived = False
                    conn.commit()
                except Exception:
                    rollback(conn)
                    raise
            audit("game_item_delete", "آیتم #%s %s" % (ident, "بایگانی شد" if archived else "حذف شد"))
            return ok(archived=archived)
        except Exception as exc:
            return err(public_error(exc))

    @app.route("/api/game/admin/item_toggle", methods=["POST"])
    @require_auth
    def api_game_admin_item_toggle():
        data = body()
        ident = gd.to_int(data.get("id"))
        active = 1 if data.get("active") else 0
        try:
            with db_lock:
                conn = get_conn()
                cur = conn.cursor()
                try:
                    cur.execute("UPDATE ShopItems SET is_active=?,updated_at=GETDATE() WHERE id=? AND is_archived=0",
                                active, ident)
                    changed = cur.rowcount
                    conn.commit()
                except Exception:
                    rollback(conn)
                    raise
            if not changed:
                return err("آیتم یافت نشد")
            return ok(active=bool(active))
        except Exception as exc:
            return err(public_error(exc))

    @app.route("/api/game/admin/festivals", methods=["POST"])
    @require_auth
    def api_game_admin_festivals():
        try:
            with db_lock:
                cur = get_conn().cursor()
                today = db_now(cur).date()
                festivals = fetch(cur, "SELECT id,title,start_date,end_date,created_at FROM ShopFestivals ORDER BY start_date DESC,id DESC")
                links = fetch(cur, """SELECT fi.festival_id,fi.item_id,fi.discount_percent,i.name,i.price
                    FROM ShopFestivalItems fi JOIN ShopItems i ON i.id=fi.item_id""")
            for fest in festivals:
                fest["items"] = [dict(x, final_price=gd.discounted_price(x["price"], x["discount_percent"]))
                                 for x in links if x["festival_id"] == fest["id"]]
                fest["start_fa"] = gd.jalali_text(fest["start_date"])
                fest["end_fa"] = gd.jalali_text(fest["end_date"])
                fest["state"] = ("running" if fest["start_date"] <= today <= fest["end_date"]
                                 else ("upcoming" if fest["start_date"] > today else "finished"))
            return ok(rows=festivals)
        except Exception as exc:
            return err(public_error(exc), rows=[])

    @app.route("/api/game/admin/festival_save", methods=["POST"])
    @require_auth
    def api_game_admin_festival_save():
        user = g.user
        data = body()
        title = str(data.get("title") or "").strip()
        start = gd.parse_jalali(data.get("start"))
        end = gd.parse_jalali(data.get("end"))
        if not 2 <= len(title) <= 150:
            return err("عنوان جشنواره را وارد کنید")
        if not start or not end:
            return err("تاریخ شروع و پایان جشنواره را انتخاب کنید")
        if end < start:
            return err("پایان جشنواره نمی‌تواند قبل از شروع آن باشد")
        items = []
        for row in data.get("items") or []:
            item_id = gd.to_int(row.get("item_id"))
            percent_off = gd.to_int(row.get("percent"))
            if not item_id:
                continue
            if percent_off is None or not 1 <= percent_off <= 90:
                return err("درصد تخفیف هر آیتم باید بین ۱ تا ۹۰ باشد")
            items.append((item_id, percent_off))
        if not items:
            return err("حداقل یک آیتم با درصد تخفیف انتخاب کنید")
        ident = gd.to_int(data.get("id"))
        try:
            with db_lock:
                conn = get_conn()
                cur = conn.cursor()
                try:
                    for item_id, _ in items:
                        clash = fetch_one(cur, """SELECT TOP 1 f.title FROM ShopFestivalItems fi
                            JOIN ShopFestivals f ON f.id=fi.festival_id
                            WHERE fi.item_id=? AND f.id<>ISNULL(?,0) AND f.start_date<=? AND f.end_date>=?""",
                                          item_id, ident, end, start)
                        if clash:
                            name = scalar(cur, "SELECT name FROM ShopItems WHERE id=?", item_id) or item_id
                            return err("آیتم «%s» در همین بازه در جشنواره «%s» هم هست" % (name, clash["title"]))
                    if ident:
                        cur.execute("UPDATE ShopFestivals SET title=?,start_date=?,end_date=? WHERE id=?",
                                    title, start, end, ident)
                        cur.execute("DELETE FROM ShopFestivalItems WHERE festival_id=?", ident)
                    else:
                        cur.execute("""INSERT INTO ShopFestivals(title,start_date,end_date,created_by)
                            OUTPUT INSERTED.id VALUES(?,?,?,?)""", title, start, end, user["id"])
                        ident = int(cur.fetchone()[0])
                    for item_id, percent_off in items:
                        cur.execute("""INSERT INTO ShopFestivalItems(festival_id,item_id,discount_percent)
                            VALUES(?,?,?)""", ident, item_id, percent_off)
                    wished = fetch(cur, """SELECT DISTINCT w.user_id,i.name FROM ShopWishlist w
                        JOIN ShopItems i ON i.id=w.item_id WHERE w.item_id IN (%s)"""
                                   % ",".join("?" for _ in items), *[x[0] for x in items])
                    conn.commit()
                except Exception:
                    rollback(conn)
                    raise
            for row in wished:
                notify(int(row["user_id"]), "game", "«%s» از لیست آرزوی شما در جشنواره «%s» تخفیف دارد" % (
                    row["name"], title))
            audit("game_festival_save", "جشنواره #%s: %s" % (ident, title))
            return ok(id=ident)
        except Exception as exc:
            return err(public_error(exc))

    @app.route("/api/game/admin/festival_delete", methods=["POST"])
    @require_auth
    def api_game_admin_festival_delete():
        ident = gd.to_int(body().get("id"))
        try:
            with db_lock:
                conn = get_conn()
                cur = conn.cursor()
                try:
                    cur.execute("DELETE FROM ShopFestivalItems WHERE festival_id=?", ident)
                    cur.execute("DELETE FROM ShopFestivals WHERE id=?", ident)
                    conn.commit()
                except Exception:
                    rollback(conn)
                    raise
            audit("game_festival_delete", "جشنواره #%s" % ident)
            return ok()
        except Exception as exc:
            return err(public_error(exc))

    @app.route("/api/game/admin/wallet_users", methods=["POST"])
    @require_auth
    def api_game_admin_wallet_users():
        user = g.user
        if not any(user_has_permission(user, key) for key in
                   ("shop.gift", "wallet.adjust", "economy.view", "ratings.monthly")):
            return err("شما دسترسی لازم برای این بخش را ندارید", 403)
        try:
            with db_lock:
                cur = get_conn().cursor()
                now = db_now(cur)
                marks = ",".join("?" for _ in gd.WALLET_ROLES)
                rows = fetch(cur, "SELECT id,username,display_name,role FROM Users WHERE is_active=1 AND role IN (%s) ORDER BY display_name"
                             % marks, *gd.WALLET_ROLES)
                rows = [r for r in rows if shares_team(cur, user, r["id"])]
                with_balance = user_has_permission(user, "economy.view") or user_has_permission(user, "wallet.adjust")
                for row in rows:
                    row["name"] = name_of(row)
                    if with_balance:
                        state = wallet(cur, row["id"], now)
                        row["balance"] = state["balance"]
                        row["expiring_soon"] = state["expiring_soon"]
            return ok(rows=rows)
        except Exception as exc:
            return err(public_error(exc), rows=[])

    @app.route("/api/game/admin/gift", methods=["POST"])
    @require_auth
    def api_game_admin_gift():
        user = g.user
        data = body()
        to_user = gd.to_int(data.get("to_user"))
        item_id = gd.to_int(data.get("item_id"))
        reason = str(data.get("reason") or "").strip()
        link_type = str(data.get("link_type") or "")
        link_id = gd.to_int(data.get("link_id"))
        if len(reason) < 10:
            return err("دلیل هدیه را کامل بنویسید (حداقل ۱۰ حرف)؛ این دلیل برای همه نمایش داده می‌شود")
        if link_type not in ("task", "project", "contract") or not link_id:
            return err("هدیه باید به یک تسک، پروژه یا قرارداد مشخص وصل شود")
        try:
            with db_lock:
                conn = get_conn()
                cur = conn.cursor()
                try:
                    values = settings(cur)
                    now = db_now(cur)
                    target = user_info(cur, to_user)
                    if not target or not target["is_active"] or target["role"] not in gd.WALLET_ROLES:
                        return err("این کاربر کیف پول سکه ندارد")
                    if not shares_team(cur, user, to_user):
                        return err("این کاربر خارج از محدوده تیم شماست", 403)
                    item = fetch_one(cur, "SELECT %s FROM ShopItems i WHERE i.id=? AND i.is_archived=0"
                                     % ITEM_COLUMNS, item_id)
                    if not item:
                        return err("این آیتم در فروشگاه نیست")
                    table = {"task": "Tasks", "project": "Projects", "contract": "Contracts"}[link_type]
                    if not scalar(cur, "SELECT 1 FROM %s WHERE id=?" % table, link_id):
                        return err("مورد مرتبط یافت نشد")
                    month_start, month_end = gd.month_bounds(gd.month_key(now))
                    given = int(scalar(cur, "SELECT COUNT(*) FROM ShopGifts WHERE from_user=? AND created_at>=? AND created_at<?",
                                       user["id"], month_start, month_end + _dt.timedelta(days=1)) or 0)
                    cap = setting_int(values, "game_gift_monthly_cap")
                    if user.get("role") != "admin" and given >= cap:
                        return err("سقف هدیه ماهانه شما (%s) پر شده است" % gd.fa_digits(cap))
                    status = status_for(item["item_type"], gifted=True)
                    cur.execute("""INSERT INTO ShopOrders(item_id,user_id,item_type,item_name,base_price,price_paid,
                            status,show_in_public,note)
                        OUTPUT INSERTED.id VALUES(?,?,?,?,?,0,?,1,?)""",
                                item_id, to_user, item["item_type"], item["name"], int(item["price"]), status,
                                "هدیه از %s" % name_of(user))
                    order_id = int(cur.fetchone()[0])
                    cur.execute("""INSERT INTO ShopGifts(order_id,item_id,to_user,from_user,reason,link_type,link_id)
                        OUTPUT INSERTED.id VALUES(?,?,?,?,?,?,?)""",
                                order_id, item_id, to_user, user["id"], reason[:1000], link_type, link_id)
                    gift_id = int(cur.fetchone()[0])
                    cur.execute("UPDATE ShopOrders SET gift_id=? WHERE id=?", gift_id, order_id)
                    if item["item_type"] == "cosmetic":
                        equip(cur, to_user, item)
                    conn.commit()
                except Exception:
                    rollback(conn)
                    raise
            extra = " — روز استفاده را از «خریدهای من» انتخاب کنید" if item["item_type"] in gd.DATED_TYPES else ""
            notify(to_user, "game", "%s به شما «%s» هدیه داد%s" % (name_of(user), item["name"], extra))
            audit("game_gift", "هدیه «%s» به کاربر #%s — %s" % (item["name"], to_user, reason[:200]))
            return ok(order_id=order_id)
        except Exception as exc:
            return err(public_error(exc))

    def fulfilment_rows(cur, statuses):
        marks = ",".join("?" for _ in statuses)
        return fetch(cur, """SELECT TOP 300 o.id,o.item_name,o.item_type,o.price_paid,o.status,o.created_at,
                o.fulfilled_at,o.note,o.gift_id,u.display_name,u.username,t.name AS team_name,
                i.reward_amount,fu.display_name AS fulfilled_by_name
            FROM ShopOrders o JOIN Users u ON u.id=o.user_id
            LEFT JOIN ShopItems i ON i.id=o.item_id LEFT JOIN Teams t ON t.id=o.team_id
            LEFT JOIN Users fu ON fu.id=o.fulfilled_by
            WHERE o.status IN (%s) ORDER BY CASE WHEN o.fulfilled_at IS NULL THEN 0 ELSE 1 END,
              o.created_at DESC""" % marks, *statuses)

    def mark_fulfilled(from_status, to_status, label):
        user = g.user
        ident = gd.to_int(body().get("id"))
        with db_lock:
            conn = get_conn()
            cur = conn.cursor()
            try:
                cur.execute("""UPDATE ShopOrders SET status=?,fulfilled_by=?,fulfilled_at=GETDATE()
                    WHERE id=? AND status=?""", to_status, user["id"], ident, from_status)
                changed = cur.rowcount
                row = fetch_one(cur, "SELECT user_id,item_name FROM ShopOrders WHERE id=?", ident)
                conn.commit()
            except Exception:
                rollback(conn)
                raise
        if not changed:
            return err("این مورد قبلاً ثبت شده یا یافت نشد")
        if row:
            notify(int(row["user_id"]), "game", "«%s» %s" % (row["item_name"], label))
        audit("game_" + to_status, "سفارش #%s" % ident)
        return ok()

    @app.route("/api/game/admin/deliveries", methods=["POST"])
    @require_auth
    def api_game_admin_deliveries():
        try:
            with db_lock:
                cur = get_conn().cursor()
                rows = fulfilment_rows(cur, ("pending_delivery", "delivered"))
            for row in rows:
                row["name"] = name_of(row)
                row["status_label"] = ORDER_LABELS.get(row["status"], row["status"])
            return ok(rows=rows)
        except Exception as exc:
            return err(public_error(exc), rows=[])

    @app.route("/api/game/admin/deliver_mark", methods=["POST"])
    @require_auth
    def api_game_admin_deliver_mark():
        try:
            return mark_fulfilled("pending_delivery", "delivered", "تحویل داده شد")
        except Exception as exc:
            return err(public_error(exc))

    @app.route("/api/game/admin/payments", methods=["POST"])
    @require_auth
    def api_game_admin_payments():
        try:
            with db_lock:
                cur = get_conn().cursor()
                rows = fulfilment_rows(cur, ("pending_payment", "paid"))
            for row in rows:
                row["name"] = name_of(row)
                row["status_label"] = ORDER_LABELS.get(row["status"], row["status"])
            return ok(rows=rows)
        except Exception as exc:
            return err(public_error(exc), rows=[])

    @app.route("/api/game/admin/payment_mark", methods=["POST"])
    @require_auth
    def api_game_admin_payment_mark():
        try:
            return mark_fulfilled("pending_payment", "paid", "پرداخت شد")
        except Exception as exc:
            return err(public_error(exc))

    def hours_text(hours):
        if hours is None:
            return "—"
        if hours < 1:
            return "کمتر از یک ساعت"
        if hours < 24:
            return "%s ساعت" % gd.fa_digits(int(round(hours)))
        return "%s روز" % gd.fa_digits(round(hours / 24.0, 1))

    def ratio_text(part, whole):
        if not whole:
            return "موردی ثبت نشده"
        return "%s از %s (%s٪)" % (gd.fa_digits(part), gd.fa_digits(whole), gd.fa_digits(gd.percent(part, whole)))

    def report_card(cur, person, month, holidays):
        start, end = gd.month_bounds(month)
        after = end + _dt.timedelta(days=1)
        try:
            if person["role"] == "planner":
                m = planner_metrics(cur, int(person["id"]), start, after, holidays)
                return [
                    {"label": "میانه زمان بررسی تسک‌های جدید",
                     "value": "%s (%s مورد)" % (hours_text(m["triage_median_hours"]), gd.fa_digits(m["triage_count"]))},
                    {"label": "صف تأیید تیم", "value": "%s تصمیم، %s مورد دیرتر از یک روز کاری" % (
                        gd.fa_digits(m["queue_decisions"]), gd.fa_digits(m["queue_slow"]))},
                    {"label": "تسک‌های سروقت تیم", "value": ratio_text(m["team_on_time"], m["team_with_due"])},
                    {"label": "تسک‌هایی که کامل ساخته شده‌اند", "value": ratio_text(m["created_complete"], m["created"])},
                ]
            if person["role"] == "finance":
                m = finance_metrics(cur, int(person["id"]), month, start, after)
                return [
                    {"label": "صورت‌وضعیت‌های برنامه ماه که به‌موقع ثبت شده‌اند",
                     "value": ratio_text(m["planned_on_time"], m["planned"])},
                    {"label": "صورت‌وضعیت‌های او که بار اول تأیید شده‌اند",
                     "value": ratio_text(m["first_time_ok"], m["decided"])},
                    {"label": "ارسال مالیاتی بدون خطا", "value": ratio_text(m["tax_clean"], m["tax_sent"])},
                    {"label": "ایرادهای داده مالی (الان)", "value": gd.fa_digits(m["issues"])},
                ]
            return [{"label": "کارنامه عددی",
                     "value": "کار این نقش کمتر در سیستم ثبت می‌شود؛ ستاره بیشتر به نظر شما بستگی دارد."}]
        except Exception as exc:
            LOG.warning("Report card failed for user %s: %s", person.get("id"), exc)
            return [{"label": "کارنامه", "value": "محاسبه نشد: %s" % exc}]

    @app.route("/api/game/admin/monthly", methods=["POST"])
    @require_auth
    def api_game_admin_monthly():
        data = body()
        try:
            with db_lock:
                cur = get_conn().cursor()
                values = settings(cur)
                now = db_now(cur)
                current = gd.month_key(now)
                month = str(data.get("month") or gd.previous_month_key(current))
                months, cursor_key = [], current
                for _ in range(7):
                    months.append({"key": cursor_key, "label": gd.month_label(cursor_key)})
                    cursor_key = gd.previous_month_key(cursor_key)
                marks = ",".join("?" for _ in gd.MONTHLY_STAR_ROLES)
                people = fetch(cur, "SELECT id,username,display_name,role FROM Users WHERE is_active=1 AND role IN (%s) ORDER BY role,display_name"
                               % marks, *gd.MONTHLY_STAR_ROLES)
                ratings = {int(r["user_id"]): r for r in fetch(cur, """SELECT user_id,stars,note,coins,rated_at
                    FROM GameMonthlyRatings WHERE month_key=?""", month)}
                holidays = holiday_days(cur)
                for person in people:
                    person["name"] = name_of(person)
                    person["card"] = report_card(cur, person, month, holidays)
                    person["rating"] = ratings.get(int(person["id"]))
            return ok(month=month, month_label=gd.month_label(month), months=months, rows=people,
                      coins_per_star=setting_int(values, "game_coins_per_star"))
        except Exception as exc:
            return err(public_error(exc), rows=[])

    @app.route("/api/game/admin/monthly_save", methods=["POST"])
    @require_auth
    def api_game_admin_monthly_save():
        user = g.user
        data = body()
        uid = gd.to_int(data.get("user_id"))
        stars = gd.to_int(data.get("stars"))
        month = str(data.get("month") or "")
        note = str(data.get("note") or "").strip()[:500] or None
        if stars is None or not 1 <= stars <= 5:
            return err("ستاره باید بین ۱ تا ۵ باشد")
        notes = []
        try:
            gd.month_bounds(month)
        except Exception:
            return err("ماه انتخاب‌شده معتبر نیست")
        try:
            with db_lock:
                conn = get_conn()
                cur = conn.cursor()
                try:
                    values = settings(cur)
                    now = db_now(cur)
                    if month > gd.month_key(now):
                        return err("برای ماه‌های آینده نمی‌توان ستاره داد")
                    person = user_info(cur, uid)
                    if not person or person["role"] not in gd.MONTHLY_STAR_ROLES:
                        return err("ستاره ماهانه فقط برای پلنر، کارشناس مالی و کارشناس اجرایی است")
                    coins = stars * setting_int(values, "game_coins_per_star")
                    existing = fetch_one(cur, "SELECT id,coins FROM GameMonthlyRatings WHERE user_id=? AND month_key=?",
                                         uid, month)
                    if existing:
                        cur.execute("""UPDATE GameMonthlyRatings SET stars=?,note=?,rated_by=?,rated_at=GETDATE(),
                            coins=? WHERE id=?""", stars, note, user["id"], coins, existing["id"])
                        rating_id = int(existing["id"])
                    else:
                        cur.execute("""INSERT INTO GameMonthlyRatings(user_id,month_key,stars,note,rated_by,coins)
                            OUTPUT INSERTED.id VALUES(?,?,?,?,?,?)""", uid, month, stars, note, user["id"], coins)
                        rating_id = int(cur.fetchone()[0])
                    paid = int(scalar(cur, """SELECT ISNULL(SUM(amount),0) FROM GameCoinLedger
                        WHERE source_type='rating' AND source_id=? AND user_id=?""", rating_id, uid) or 0)
                    if coins - paid:
                        add_coins(cur, uid, coins - paid, "rating", "rating", rating_id,
                                  "ستاره ماهانه %s" % gd.month_label(month), now, values, created_by=user["id"])
                    history = [fetch_one(cur, "SELECT stars FROM GameMonthlyRatings WHERE user_id=? AND month_key=?",
                                         uid, key) for key in (gd.previous_month_key(gd.previous_month_key(month)),
                                                               gd.previous_month_key(month), month)]
                    if gd.bright_streak([(h or {}).get("stars") for h in history]):
                        badge = award_badge(cur, uid, "bright3", gd.season_of_month(month), values, now)
                        if badge:
                            notes.append(badge_note(badge))
                    conn.commit()
                except Exception:
                    rollback(conn)
                    raise
            notify(uid, "game", "ستاره ماهانه %s: %s ستاره و %s سکه" % (
                gd.month_label(month), gd.fa_digits(stars), gd.fa_digits(coins)))
            for text in notes:
                notify(uid, "game", text)
            audit("game_monthly_rating", "کاربر #%s، %s: %s ستاره" % (uid, month, stars))
            return ok(coins=coins)
        except Exception as exc:
            return err(public_error(exc))

    @app.route("/api/game/admin/economy", methods=["POST"])
    @require_auth
    def api_game_admin_economy():
        try:
            with db_lock:
                cur = get_conn().cursor()
                now = db_now(cur)
                marks = ",".join("?" for _ in gd.WALLET_ROLES)
                people = fetch(cur, "SELECT id,username,display_name,role FROM Users WHERE is_active=1 AND role IN (%s) ORDER BY display_name"
                               % marks, *gd.WALLET_ROLES)
                totals = fetch_one(cur, """SELECT
                    ISNULL(SUM(CASE WHEN amount>0 AND kind<>'refund' THEN amount ELSE 0 END),0) AS issued,
                    ISNULL(SUM(CASE WHEN kind='spend' THEN -amount ELSE 0 END),0) AS spent,
                    ISNULL(SUM(CASE WHEN kind='refund' THEN amount ELSE 0 END),0) AS refunded
                    FROM GameCoinLedger""") or {}
                earned = {int(r["user_id"]): r for r in fetch(cur, """SELECT user_id,
                        ISNULL(SUM(CASE WHEN amount>0 AND kind<>'refund' THEN amount ELSE 0 END),0) AS earned,
                        ISNULL(SUM(CASE WHEN kind='spend' THEN -amount ELSE 0 END),0) AS spent
                    FROM GameCoinLedger GROUP BY user_id""")}
                outstanding = soon = expired = 0
                for person in people:
                    state = wallet(cur, person["id"], now)
                    person["name"] = name_of(person)
                    person["balance"] = state["balance"]
                    person["expiring_soon"] = state["expiring_soon"]
                    person["expired"] = state["expired"]
                    person["earned"] = int((earned.get(int(person["id"])) or {}).get("earned") or 0)
                    person["spent"] = int((earned.get(int(person["id"])) or {}).get("spent") or 0)
                    outstanding += max(0, state["balance"])
                    soon += state["expiring_soon"]
                    expired += state["expired"]
            spent = int(totals.get("spent") or 0) - int(totals.get("refunded") or 0)
            return ok(rows=people, totals={"issued": int(totals.get("issued") or 0), "spent": spent,
                                           "outstanding": outstanding, "expiring_soon": soon, "expired": expired})
        except Exception as exc:
            return err(public_error(exc), rows=[])

    @app.route("/api/game/admin/wallet_adjust", methods=["POST"])
    @require_auth
    def api_game_admin_wallet_adjust():
        user = g.user
        data = body()
        uid = gd.to_int(data.get("user_id"))
        amount = gd.to_int(data.get("amount"))
        reason = str(data.get("reason") or "").strip()
        if not amount:
            return err("مقدار سکه را وارد کنید؛ برای کم کردن، عدد منفی بنویسید")
        if abs(amount) > 100000:
            return err("مقدار اصلاح بیش از حد است")
        if len(reason) < 5:
            return err("دلیل اصلاح را بنویسید؛ خود کاربر آن را می‌بیند")
        try:
            with db_lock:
                conn = get_conn()
                cur = conn.cursor()
                try:
                    values = settings(cur)
                    now = db_now(cur)
                    person = user_info(cur, uid)
                    if not person or person["role"] not in gd.WALLET_ROLES:
                        return err("این کاربر کیف پول سکه ندارد")
                    lock_wallet(cur, uid)
                    add_coins(cur, uid, amount, "adjust", "adjust", None, reason, now, values, created_by=user["id"])
                    conn.commit()
                except Exception:
                    rollback(conn)
                    raise
            notify(uid, "game", "موجودی سکه شما %s شد: %s" % (
                "%s سکه افزایش" % gd.fa_digits(amount) if amount > 0 else "%s سکه کاهش" % gd.fa_digits(-amount),
                reason[:120]))
            audit("game_wallet_adjust", "کاربر #%s: %s سکه — %s" % (uid, amount, reason[:200]))
            return ok()
        except Exception as exc:
            return err(public_error(exc))

    @app.route("/api/game/admin/settings", methods=["POST"])
    @require_auth
    def api_game_admin_settings():
        try:
            with db_lock:
                cur = get_conn().cursor()
                values = settings(cur)
            return ok(settings={k: values.get(k) for k in SETTING_DEFAULTS})
        except Exception as exc:
            return err(public_error(exc))

    @app.route("/api/game/admin/settings_save", methods=["POST"])
    @require_auth
    def api_game_admin_settings_save():
        user = g.user
        data = body().get("settings") or {}
        clean = {}
        for key, value in data.items():
            if key not in SETTING_DEFAULTS:
                continue
            if key == "game_shop_open":
                clean[key] = "1" if str(value) in ("1", "true", "True") or value is True else "0"
            elif key == "game_level_thresholds":
                clean[key] = ",".join(str(x) for x in gd.parse_thresholds(value))
            else:
                number = gd.to_int(value)
                low, high = SETTING_LIMITS[key]
                if number is None or not low <= number <= high:
                    return err("مقدار «%s» باید بین %s و %s باشد" % (key, gd.fa_digits(low), gd.fa_digits(high)))
                clean[key] = str(number)
        try:
            with db_lock:
                conn = get_conn()
                cur = conn.cursor()
                try:
                    for key, value in clean.items():
                        save_setting(cur, key, value, user["id"])
                    conn.commit()
                except Exception:
                    rollback(conn)
                    raise
            audit("game_settings", ", ".join("%s=%s" % kv for kv in sorted(clean.items()))[:500])
            return ok()
        except Exception as exc:
            return err(public_error(exc))

    return {"recompute_task": recompute_task}
