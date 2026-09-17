\set ON_ERROR_STOP on
BEGIN;
WITH RECURSIVE keep(relid) AS (
  SELECT unnest(ARRAY[
    'users'::regclass, 'drivers'::regclass, 'vehicles'::regclass,
    'tenants'::regclass, 'branches'::regclass, 'role_profiles'::regclass,
    'operational_settings'::regclass, 'driver_settings'::regclass,
    'vehicle_types'::regclass, 'vehicle_owners'::regclass,
    'carriers'::regclass, 'carrier_vehicle_links'::regclass,
    'branding_settings'::regclass
  ])
  UNION
  SELECT constraint_row.confrelid
  FROM pg_constraint constraint_row
  JOIN keep ON keep.relid = constraint_row.conrelid
  WHERE constraint_row.contype = 'f'
), removable AS (
  SELECT format('%I.%I', namespace_row.nspname, class_row.relname) AS table_name
  FROM pg_class class_row
  JOIN pg_namespace namespace_row ON namespace_row.oid = class_row.relnamespace
  WHERE namespace_row.nspname = 'public' AND class_row.relkind = 'r'
    AND class_row.oid NOT IN (SELECT relid FROM keep)
)
SELECT 'TRUNCATE TABLE ' || string_agg(table_name, ', ') || ' RESTART IDENTITY CASCADE;'
FROM removable
\gexec
COMMIT;
