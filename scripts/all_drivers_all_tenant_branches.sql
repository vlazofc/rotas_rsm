-- Execute uma vez na implantação em produção. Pode ser repetido sem duplicar vínculos.
-- Mantém bloqueios e reprovações existentes; filiais com aprovação exigida recebem vínculo pendente.
BEGIN;

INSERT INTO driver_branches (driver_id, branch_id, active, approval_status)
SELECT d.id, b.id, TRUE,
       CASE WHEN COALESCE(p.require_driver_approval, FALSE) THEN 'pending' ELSE 'approved' END
FROM drivers d
JOIN branches b ON b.tenant_id = d.tenant_id
LEFT JOIN branch_approval_policies p ON p.branch_id = b.id
WHERE d.carrier_id IS NULL OR EXISTS (
    SELECT 1 FROM carrier_branches cb
    WHERE cb.carrier_id = d.carrier_id AND cb.branch_id = b.id AND cb.active = TRUE
)
ON CONFLICT (driver_id, branch_id) DO NOTHING;

INSERT INTO vehicle_branches (vehicle_id, branch_id, active, approval_status)
SELECT v.id, b.id, TRUE,
       CASE WHEN COALESCE(p.require_vehicle_approval, FALSE) THEN 'pending' ELSE 'approved' END
FROM vehicles v
JOIN branches b ON b.tenant_id = v.tenant_id
LEFT JOIN branch_approval_policies p ON p.branch_id = b.id
WHERE v.carrier_id IS NULL OR EXISTS (
    SELECT 1 FROM carrier_branches cb
    WHERE cb.carrier_id = v.carrier_id AND cb.branch_id = b.id AND cb.active = TRUE
)
ON CONFLICT (vehicle_id, branch_id) DO NOTHING;

COMMIT;
