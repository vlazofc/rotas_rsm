-- Modelo operacional atual: uma empresa prestadora (JM).
-- Adimax é cliente/contratante e não deve ser criada como tenant de acesso.
-- Este script é idempotente e serve apenas para instalações novas ou vazias.
-- A consolidação de uma base existente exige backup e auditoria prévia.
BEGIN;

DO $$
DECLARE copied_columns text;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM tenants WHERE slug = 'jm') THEN
    SELECT string_agg(quote_ident(column_name), ', ' ORDER BY ordinal_position)
      INTO copied_columns
      FROM information_schema.columns
     WHERE table_schema = 'public'
       AND table_name = 'tenants'
       AND column_name NOT IN ('id', 'name', 'slug', 'created_at', 'updated_at');

    IF EXISTS (SELECT 1 FROM tenants) AND copied_columns IS NOT NULL THEN
      EXECUTE format(
        'INSERT INTO tenants (%s,name,slug,created_at,updated_at) SELECT %s,%L,%L,now(),now() FROM tenants ORDER BY id LIMIT 1',
        copied_columns, copied_columns, 'JM', 'jm'
      );
    ELSE
      INSERT INTO tenants (name, slug, created_at, updated_at)
      VALUES ('JM', 'jm', now(), now());
    END IF;
  END IF;
END $$;

INSERT INTO branches (tenant_id, name, country, locale, active, created_at, updated_at)
SELECT id, 'Operação JM', 'BR', 'pt-BR', true, now(), now()
  FROM tenants t
 WHERE t.slug = 'jm'
   AND NOT EXISTS (SELECT 1 FROM branches b WHERE b.tenant_id = t.id);

COMMIT;
