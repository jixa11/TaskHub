-- TaskHub 8.3.0 LAN R13 - read-only checks for points, coins and the shop.
-- Run against the application database after the first start of R13.
-- Nothing here changes data. Each section is its own batch, so one missing
-- object does not stop the rest from running.
SET NOCOUNT ON;
GO

-- 1. Every R13 table exists.
SELECT t.name AS expected_table,
       CASE WHEN o.object_id IS NULL THEN 'MISSING' ELSE 'OK' END AS state
FROM (VALUES ('TaskEvents'),('GameWallets'),('GameXpLedger'),('GameCoinLedger'),('GameUserBadges'),
             ('GameTeamQuestResults'),('GameKudos'),('GameMonthlyRatings'),('GameCosmetics'),
             ('ShopItems'),('ShopFestivals'),('ShopFestivalItems'),('ShopOrders'),('ShopWishlist'),
             ('ShopGifts'),('GameTeamPots')) AS t(name)
LEFT JOIN sys.objects o ON o.name=t.name AND o.type='U'
ORDER BY state DESC, t.name;
GO

-- 2. New columns on existing tables.
SELECT 'Leaves.is_reward' AS column_name,
       CASE WHEN COL_LENGTH('Leaves','is_reward') IS NULL THEN 'MISSING' ELSE 'OK' END AS state
UNION ALL SELECT 'Leaves.reward_order_id',
       CASE WHEN COL_LENGTH('Leaves','reward_order_id') IS NULL THEN 'MISSING' ELSE 'OK' END
UNION ALL SELECT 'Tasks.due_at_assign',
       CASE WHEN COL_LENGTH('Tasks','due_at_assign') IS NULL THEN 'MISSING' ELSE 'OK' END;
GO

-- 3. Settings. game_installed_at is the moment from which approved tasks earn.
SELECT setting_key, setting_value, updated_at
FROM AppSettings WHERE setting_key LIKE 'game[_]%' ORDER BY setting_key;
GO

-- 4. The 17 new permission keys, per role.
SELECT role, COUNT(*) AS keys_present, SUM(CASE WHEN is_allowed=1 THEN 1 ELSE 0 END) AS allowed
FROM RolePermissions
WHERE permission_key IN ('menu.club','menu.club_admin','gamification.view_own','gamification.team_board',
    'gamification.full_ranking','gamification.kudos','shop.view','shop.buy','shop.manage_items',
    'shop.manage_festivals','shop.gift','shop.deliver','shop.pay_rewards','ratings.monthly',
    'wallet.adjust','economy.view','game.settings')
GROUP BY role ORDER BY role;
GO

-- 5. Wallet integrity. Both lists should be empty.
SELECT o.id AS paid_order_without_coin_entry, o.item_name, o.created_at
FROM ShopOrders o WHERE o.price_paid>0 AND o.coin_entry_id IS NULL;
SELECT r.id AS refund_without_its_purchase, r.user_id, r.amount, r.created_at
FROM GameCoinLedger r
WHERE r.kind='refund' AND NOT EXISTS(SELECT 1 FROM GameCoinLedger s WHERE s.id=r.reverses_id AND s.kind='spend');
GO

-- 6. Every reward leave belongs to a live order. Should be empty.
SELECT l.id AS reward_leave_without_order, l.staff_id, l.leave_date
FROM Leaves l
WHERE l.is_reward=1 AND NOT EXISTS(SELECT 1 FROM ShopOrders o WHERE o.id=l.reward_order_id AND o.status='scheduled');
GO

-- 7. Totals at a glance.
SELECT (SELECT COUNT(*) FROM TaskEvents) AS task_events,
       (SELECT COUNT(*) FROM GameXpLedger) AS point_rows,
       (SELECT ISNULL(SUM(points),0) FROM GameXpLedger) AS points_total,
       (SELECT ISNULL(SUM(CASE WHEN amount>0 AND kind<>'refund' THEN amount ELSE 0 END),0) FROM GameCoinLedger) AS coins_issued,
       (SELECT COUNT(*) FROM ShopItems WHERE is_archived=0) AS items_in_shop,
       (SELECT COUNT(*) FROM ShopOrders) AS orders,
       (SELECT COUNT(*) FROM ShopGifts) AS gifts;
GO
