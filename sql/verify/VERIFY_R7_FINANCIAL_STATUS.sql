USE [TaskHub];
GO
SET NOCOUNT ON;

/* فقط کنترل؛ هیچ داده‌ای تغییر نمی‌کند. */
SELECT
    TotalLegacyStatements = COUNT_BIG(*),
    EmployerApproved = SUM(CASE WHEN business_status='employer_approved' THEN 1 ELSE 0 END),
    NotApproved = SUM(CASE WHEN business_status<>'employer_approved' THEN 1 ELSE 0 END),
    ApprovedWithoutPositiveAmount = SUM(CASE WHEN business_status='employer_approved'
        AND ISNULL(confirmed_without_vat,0)<=0 THEN 1 ELSE 0 END)
FROM dbo.ContractStatements
WHERE legacy_statement_id IS NOT NULL;

SELECT TOP (100)
    co.id,
    co.contract_number,
    co.title,
    EffectivePrice = ISNULL(co.base_price,0) + ISNULL((
        SELECT SUM(ISNULL(e.price_delta,0))
        FROM dbo.ContractExtensions e
        WHERE e.contract_id=co.id AND e.is_active=1
          AND e.internal_status='approved' AND e.extension_type_id IN (2,3)
    ),0),
    ApprovedStatements = ISNULL((
        SELECT SUM(ISNULL(s.confirmed_without_vat,0))
        FROM dbo.ContractStatements s
        WHERE s.contract_id=co.id AND s.is_active=1 AND s.is_current=1
          AND s.business_status='employer_approved'
    ),0),
    RemainingPrice =
        ISNULL(co.base_price,0) + ISNULL((
            SELECT SUM(ISNULL(e.price_delta,0))
            FROM dbo.ContractExtensions e
            WHERE e.contract_id=co.id AND e.is_active=1
              AND e.internal_status='approved' AND e.extension_type_id IN (2,3)
        ),0)
        - ISNULL((
            SELECT SUM(ISNULL(s.confirmed_without_vat,0))
            FROM dbo.ContractStatements s
            WHERE s.contract_id=co.id AND s.is_active=1 AND s.is_current=1
              AND s.business_status='employer_approved'
        ),0)
FROM dbo.Contracts co
WHERE co.is_active=1
ORDER BY co.id DESC;
