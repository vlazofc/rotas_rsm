BEGIN;
UPDATE users SET role='gerente', auth_version=auth_version+1 WHERE role='gestor_brasil';
UPDATE users SET role='monitoramento', auth_version=auth_version+1 WHERE role IN ('torre_controle','cliente');
DELETE FROM role_profiles WHERE value IN ('gestor_brasil','torre_controle','gestor_financeiro','cliente');
COMMIT;
