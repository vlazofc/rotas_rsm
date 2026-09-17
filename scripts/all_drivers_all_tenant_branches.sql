-- Todo motorista deve pertencer a todas as filiais da própria empresa.
-- A operação é idempotente pela restrição única (driver_id, branch_id).
INSERT INTO driver_branches (driver_id, branch_id)
SELECT d.id, b.id
FROM drivers d
JOIN branches b ON b.tenant_id = d.tenant_id
ON CONFLICT (driver_id, branch_id) DO NOTHING;

-- Remove somente vínculos inconsistentes entre empresas.
DELETE FROM driver_branches db
USING drivers d, branches b
WHERE db.driver_id = d.id
  AND db.branch_id = b.id
  AND d.tenant_id IS DISTINCT FROM b.tenant_id;
