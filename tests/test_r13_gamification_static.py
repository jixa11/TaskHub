# -*- coding: utf-8 -*-
"""R13: how points, coins and the shop are wired into the application."""
import pathlib
import re
import sys
import unittest

from _paths import ROOT, SRC, project_file  # noqa: E402


def src(name):
    return project_file(name).read_text(encoding="utf-8")


TABLES = ("TaskEvents", "GameWallets", "GameXpLedger", "GameCoinLedger", "GameUserBadges",
          "GameTeamQuestResults", "GameKudos", "GameMonthlyRatings", "GameCosmetics", "ShopItems",
          "ShopFestivals", "ShopFestivalItems", "ShopOrders", "ShopWishlist", "ShopGifts", "GameTeamPots")
NEW_KEYS = ("menu.club", "menu.club_admin", "gamification.view_own", "gamification.team_board",
            "gamification.full_ranking", "gamification.kudos", "shop.view", "shop.buy",
            "shop.manage_items", "shop.manage_festivals", "shop.gift", "shop.deliver",
            "shop.pay_rewards", "ratings.monthly", "wallet.adjust", "economy.view", "game.settings")


class SchemaTests(unittest.TestCase):
    def test_every_table_is_created_idempotently(self):
        py = src("gamification.py")
        for table in TABLES:
            self.assertIn("IF OBJECT_ID('%s','U') IS NULL CREATE TABLE %s(" % (table, table), py, table)

    def test_new_columns_on_existing_tables(self):
        py = src("gamification.py")
        self.assertIn("IF COL_LENGTH('Leaves','is_reward') IS NULL", py)
        self.assertIn("IF COL_LENGTH('Leaves','reward_order_id') IS NULL", py)
        self.assertIn("IF COL_LENGTH('Tasks','due_at_assign') IS NULL", py)

    def test_startup_keeps_the_module_apart(self):
        body = src("taskhub.py")
        block = body[body.index("init_r10_tables(c)\n"):body.index("def rows_to_list")]
        self.assertIn("init_gamification_tables(c)", block)
        self.assertIn("except Exception", block)
        self.assertIn("register_game_routes(flask_app", body)


class HookTests(unittest.TestCase):
    def test_task_workflow_is_hooked_without_changing_it(self):
        py = src("gamification.py")
        self.assertIn("@app.after_request", py)
        for endpoint in ("api_task_transition", "api_task_evaluation_save",
                         "api_v7_task_delete", "api_v7_task_save"):
            self.assertIn('"%s"' % endpoint, py, endpoint)
        hook = py[py.index("def _game_task_hooks"):py.index("# ── monthly work")]
        # A failure is logged and the task response goes out unchanged.
        self.assertIn("except Exception as exc:", hook)
        self.assertIn("return response", hook)

    def test_points_only_for_approved_work_by_someone_else(self):
        py = src("gamification.py")
        block = py[py.index("def recompute_task"):py.index("def award_reason")]
        self.assertIn("action='approve'", block)
        self.assertIn("self_approved", block)
        self.assertIn("TASK_EARNING_ROLES", block)
        self.assertIn("softcap_applies", block)

    def test_on_time_uses_the_deadline_at_handover(self):
        py = src("gamification.py")
        self.assertIn("UPDATE Tasks SET due_at_assign=due_jalali", py)
        self.assertIn('row.get("due_at_assign") or row.get("due_jalali")', py)

    def test_evaluations_are_one_to_five_stars(self):
        body = src("taskhub.py")
        block = body[body.index("def api_task_evaluation_save"):body.index("@flask_app.route('/api/task_time_daily'")]
        self.assertIn("1 <= stars <= 5", block)


class ShopSafetyTests(unittest.TestCase):
    def test_purchase_locks_the_wallet_and_the_item(self):
        py = src("gamification.py")
        buy = py[py.index("def api_game_shop_buy"):py.index("def api_game_shop_my_orders")]
        self.assertIn("lock_wallet(cur, uid)", buy)
        self.assertIn("WITH (UPDLOCK,HOLDLOCK)", buy)
        self.assertIn("rollback(conn)", buy)
        self.assertIn("game_shop_open", buy)

    def test_cancelling_refunds_the_exact_purchase(self):
        py = src("gamification.py")
        cancel = py[py.index("def api_game_shop_order_cancel"):py.index("def api_game_shop_wishlist_toggle")]
        self.assertIn('"refund"', cancel)
        self.assertIn('reverses_id=order["coin_entry_id"]', cancel)
        self.assertIn("can_change_booking", cancel)

    def test_gifts_need_a_documented_reason(self):
        py = src("gamification.py")
        gift = py[py.index("def api_game_admin_gift"):py.index("def fulfilment_rows")]
        self.assertIn("len(reason) < 10", gift)
        self.assertIn('("task", "project", "contract")', gift)
        self.assertIn("game_gift_monthly_cap", gift)

    def test_bought_items_are_archived_not_deleted(self):
        py = src("gamification.py")
        block = py[py.index("def api_game_admin_item_delete"):py.index("def api_game_admin_item_toggle")]
        self.assertIn("is_archived=1", block)

    def test_activation_and_festivals_are_separate(self):
        py = src("gamification.py")
        fest = py[py.index("def api_game_admin_festival_save"):py.index("def api_game_admin_festival_delete")]
        self.assertNotIn("is_active", fest)

    def test_reward_leave_is_managed_from_the_shop(self):
        body = src("taskhub.py")
        for name in ("def api_leave_update", "def api_leave_delete"):
            block = body[body.index(name):body.index(name) + 1600]
            self.assertIn("_is_reward_leave(cur", block, name)

    def test_images_are_limited(self):
        py = src("gamification.py")
        self.assertIn("MAX_IMAGE_BYTES", py)
        self.assertIn('IMAGE_MIMES = ("image/png", "image/jpeg", "image/webp", "image/gif")', py)


class PermissionTests(unittest.TestCase):
    def test_new_keys_exist(self):
        from rbac import ALL_PERMISSION_KEYS
        for key in NEW_KEYS:
            self.assertIn(key, ALL_PERMISSION_KEYS, key)

    def test_wallet_roles_buy_and_controllers_do_not(self):
        from rbac import default_permissions
        for role in ("support", "planner", "finance", "reporter"):
            perms = default_permissions(role)
            self.assertIn("shop.buy", perms, role)
            self.assertIn("gamification.view_own", perms, role)
        manager = default_permissions("manager")
        self.assertNotIn("shop.buy", manager)
        self.assertNotIn("gamification.view_own", manager)
        self.assertIn("shop.manage_items", manager)
        self.assertIn("shop.gift", manager)

    def test_only_the_administrator_runs_the_economy(self):
        from rbac import default_permissions
        for role in ("manager", "planner", "finance", "reporter", "support", "supervisor", "employer"):
            perms = default_permissions(role)
            for key in ("wallet.adjust", "economy.view", "game.settings", "ratings.monthly",
                        "shop.manage_festivals", "shop.deliver"):
                self.assertNotIn(key, perms, "%s %s" % (role, key))
        self.assertIn("shop.pay_rewards", default_permissions("finance"))

    def test_clients_never_see_it(self):
        from rbac import default_permissions
        for role in ("supervisor", "employer"):
            leaked = {k for k in default_permissions(role)
                      if k.startswith(("shop.", "gamification.", "menu.club"))}
            self.assertFalse(leaked, role)

    def test_pages_and_endpoints_are_mapped(self):
        import rbac
        self.assertEqual(rbac.MENU_PERMISSION_BY_PAGE[27], "menu.club")
        self.assertEqual(rbac.MENU_PERMISSION_BY_PAGE[28], "menu.club_admin")
        # These check more than one permission, or none, inside the handler.
        inside = {"api_game_summary", "api_game_hall", "api_game_cosmetics", "api_game_admin_wallet_users"}
        for name in re.findall(r"def (api_game_\w+)\(", src("gamification.py")):
            if name not in inside:
                self.assertIn(name, rbac.ENDPOINT_PERMISSIONS, name)
                self.assertIn(rbac.ENDPOINT_PERMISSIONS[name], rbac.ALL_PERMISSION_KEYS, name)


class UiTests(unittest.TestCase):
    def test_assets_are_served_cached_and_bundled(self):
        self.assertIn("'game_ui.js', 'game_ui.css'", src("taskhub.py"))
        self.assertIn("'/assets/game_ui.css', '/assets/game_ui.js'", src("service-worker.js"))
        build = src("build.bat")
        for name in ("game_ui.js", "game_ui.css"):
            self.assertIn('--add-data "src\\web\\%s;web"' % name, build)
        for module in ("gamification", "gamification_domain"):
            self.assertIn("--hidden-import %s ^" % module, build)
        html = src("ui.html")
        self.assertIn('<script src="/assets/game_ui.js"></script>', html)
        self.assertIn("initGameUI();", html)

    def test_pages_and_tabs_follow_permissions(self):
        js = src("game_ui.js")
        self.assertIn("PERMISSION_PAGE_MAP[27]='menu.club'", js)
        self.assertIn("PERMISSION_PAGE_MAP[28]='menu.club_admin'", js)
        for perm in ("shop.manage_items", "shop.manage_festivals", "shop.gift", "shop.deliver",
                     "shop.pay_rewards", "ratings.monthly", "economy.view", "game.settings"):
            self.assertIn("perm:'%s'" % perm, js, perm)

    def test_help_is_tabbed_and_searchable(self):
        html = src("ui.html")
        for marker in ("var HELP_TABS=[", "var HELP_PROVIDERS=[]", "function _helpRender(", "hlp-search"):
            self.assertIn(marker, html, marker)
        for name in ("v7_ui.js", "v8_ui.js"):
            self.assertIn("HELP_PROVIDERS.push(", src(name), name)
            self.assertNotIn("renderHelp=function", src(name), name)
        self.assertIn("HELP_PROVIDERS.push(gmHelp)", src("game_ui.js"))

    def test_every_role_gets_a_club_guide(self):
        js = src("game_ui.js")
        guide = js[js.index("function gmHelp(add)"):]
        for marker in ("امتیاز تسک چطور حساب می‌شود", "ستاره ماهانه و کارنامه", "خرید از فروشگاه",
                       "ارزیابی ستاره‌ای تسک", "مدیریت آیتم‌های فروشگاه", "هدیه دادن", "جشنواره",
                       "لیست تحویل و پرداخت", "اقتصاد سکه و تنظیمات", "قدردانی از همکار"):
            self.assertIn(marker, guide, marker)

    def test_task_evaluation_uses_stars(self):
        html = src("ui.html")
        block = html[html.index("async function loadTaskEvaluation"):html.index("async function loadTaskComments")]
        self.assertIn("evalStars(", block)
        self.assertNotIn('type="number" class="fi" id="eval-score-', block)

    def test_chat_carries_sender_ids_for_cosmetics(self):
        js = src("v8_ui.js")
        self.assertIn("data-uid=\"'+uid+'\"", js)
        self.assertIn("gameDecorateChat(box)", js)


if __name__ == "__main__":
    unittest.main()
