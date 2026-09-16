/*
  TaskHub v7 - read-only post-migration checks
  این فایل هیچ INSERT/UPDATE/DELETE/ALTER اجرا نمی‌کند.
  آن را روی همان دیتابیسی اجرا کنید که TaskHub به آن متصل است.
*/
SET NOCOUNT ON;

SELECT N'Contracts' AS EntityName, COUNT_BIG(*) AS TotalRows
FROM Contracts
UNION ALL
SELECT N'ContractExtensions', COUNT_BIG(*) FROM ContractExtensions
UNION ALL
SELECT N'ContractStatements', COUNT_BIG(*) FROM ContractStatements
UNION ALL
SELECT N'MigrationQuarantine', COUNT_BIG(*) FROM MigrationQuarantine
UNION ALL
SELECT N'Attachments', COUNT_BIG(*) FROM Attachments;

SELECT
    SUM(CASE WHEN legacy_contract_id IS NOT NULL THEN 1 ELSE 0 END) AS LegacyContracts,
    SUM(CASE WHEN project_id IS NULL AND is_active = 1 THEN 1 ELSE 0 END) AS ContractsWithoutProject,
    SUM(CASE WHEN payer_rating NOT BETWEEN 0 AND 5 THEN 1 ELSE 0 END) AS InvalidPayerRatings,
    SUM(CASE WHEN base_price < 0 THEN 1 ELSE 0 END) AS NegativeContractPrices
FROM Contracts;

SELECT
    SUM(CASE WHEN c.id IS NULL THEN 1 ELSE 0 END) AS OrphanExtensions,
    SUM(CASE WHEN e.internal_status = 'approved' AND e.extension_type_id IN (1,2)
                  AND e.end_date IS NULL THEN 1 ELSE 0 END) AS ApprovedTimeExtensionsWithoutEndDate,
    SUM(CASE WHEN e.internal_status = 'approved' AND e.extension_type_id IN (2,3)
                  AND e.price_delta IS NULL THEN 1 ELSE 0 END) AS ApprovedMoneyExtensionsWithoutDelta,
    SUM(CASE WHEN e.price_delta < 0 OR e.resulting_price < 0 THEN 1 ELSE 0 END) AS NegativeExtensionAmounts
FROM ContractExtensions e
LEFT JOIN Contracts c ON c.id = e.contract_id;

SELECT
    SUM(CASE WHEN c.id IS NULL THEN 1 ELSE 0 END) AS OrphanStatements,
    SUM(CASE WHEN s.period_month IS NOT NULL AND s.period_month NOT BETWEEN 1 AND 12 THEN 1 ELSE 0 END) AS InvalidMonths,
    SUM(CASE WHEN s.progress_percentage IS NOT NULL AND s.progress_percentage NOT BETWEEN 0 AND 100 THEN 1 ELSE 0 END) AS InvalidProgress,
    SUM(CASE WHEN s.requested_price < 0 OR s.requested_without_vat < 0 OR s.requested_vat < 0
                  OR s.confirmed_price < 0 OR s.confirmed_without_vat < 0 OR s.confirmed_vat < 0
             THEN 1 ELSE 0 END) AS NegativeStatementAmounts,
    SUM(CASE WHEN s.business_status = 'employer_approved'
                  AND COALESCE(s.confirmed_without_vat,s.confirmed_price) IS NULL THEN 1 ELSE 0 END) AS ApprovedWithoutConfirmedAmount
FROM ContractStatements s
LEFT JOIN Contracts c ON c.id = s.contract_id;

;WITH EffectiveContracts AS
(
    SELECT
        c.id,
        ISNULL(c.base_price,0) + ISNULL(SUM(CASE
            WHEN e.is_active=1 AND e.internal_status='approved' AND e.extension_type_id IN (2,3)
            THEN ISNULL(e.price_delta,0) ELSE 0 END),0) AS EffectivePrice
    FROM Contracts c
    LEFT JOIN ContractExtensions e ON e.contract_id=c.id
    WHERE c.is_active=1
    GROUP BY c.id,c.base_price
), ApprovedStatements AS
(
    SELECT contract_id,
           SUM(COALESCE(confirmed_without_vat,confirmed_price,requested_without_vat,requested_price,0)) AS ApprovedAmount
    FROM ContractStatements
    WHERE is_active=1 AND is_current=1 AND business_status='employer_approved'
    GROUP BY contract_id
)
SELECT ec.id AS ContractId,ec.EffectivePrice,ISNULL(a.ApprovedAmount,0) AS ApprovedAmount,
       ec.EffectivePrice-ISNULL(a.ApprovedAmount,0) AS RemainingAmount
FROM EffectiveContracts ec
LEFT JOIN ApprovedStatements a ON a.contract_id=ec.id
WHERE ec.EffectivePrice-ISNULL(a.ApprovedAmount,0) < 0
ORDER BY RemainingAmount;

SELECT fp.id AS PlanId,fp.jalali_year,fp.annual_target,
       COUNT(pp.id) AS MonthCount,ISNULL(SUM(pp.target_amount),0) AS AllocatedAmount,
       ISNULL(SUM(pp.target_amount),0)-fp.annual_target AS AllocationDifference
FROM FinancialPlans fp
LEFT JOIN FinancialPlanPeriods pp ON pp.plan_id=fp.id
WHERE fp.is_current=1
GROUP BY fp.id,fp.jalali_year,fp.annual_target
HAVING COUNT(pp.id)<>12 OR ISNULL(SUM(pp.target_amount),0)>fp.annual_target;

SELECT source_table,reason,resolution_status,COUNT_BIG(*) AS TotalRows
FROM MigrationQuarantine
GROUP BY source_table,reason,resolution_status
ORDER BY source_table,reason,resolution_status;
