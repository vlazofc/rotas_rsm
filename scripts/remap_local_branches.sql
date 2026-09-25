BEGIN;
SET LOCAL session_replication_role = replica;

DO $$
DECLARE
    ref record;
BEGIN
    -- Configurações exclusivas por filial não devem ser mescladas. Salto já
    -- possui sua própria política; descartamos somente a política da unidade
    -- fictícia antes de transferir os demais vínculos.
    DELETE FROM branch_approval_policies WHERE branch_id = 1;

    -- A antiga filial 1 era fictícia. Seus vínculos passam primeiro para a
    -- filial Salto (antigo ID 2).
    FOR ref IN
        SELECT kcu.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.constraint_schema = kcu.constraint_schema
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
         AND ccu.constraint_schema = tc.constraint_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND ccu.table_name = 'branches'
          AND ccu.column_name = 'id'
    LOOP
        EXECUTE format('UPDATE %I SET %I = 2 WHERE %I = 1', ref.table_name, ref.column_name, ref.column_name);
    END LOOP;
    DELETE FROM branches WHERE id = 1;

    -- Salto: 2 -> 1.
    FOR ref IN
        SELECT kcu.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.constraint_schema = kcu.constraint_schema
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
         AND ccu.constraint_schema = tc.constraint_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND ccu.table_name = 'branches'
          AND ccu.column_name = 'id'
    LOOP
        EXECUTE format('UPDATE %I SET %I = 1 WHERE %I = 2', ref.table_name, ref.column_name, ref.column_name);
    END LOOP;
    UPDATE branches SET id = 1 WHERE id = 2;

    -- Barueri: 3 -> 2.
    FOR ref IN
        SELECT kcu.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.constraint_schema = kcu.constraint_schema
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
         AND ccu.constraint_schema = tc.constraint_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND ccu.table_name = 'branches'
          AND ccu.column_name = 'id'
    LOOP
        EXECUTE format('UPDATE %I SET %I = 2 WHERE %I = 3', ref.table_name, ref.column_name, ref.column_name);
    END LOOP;
    UPDATE branches SET id = 2 WHERE id = 3;
    PERFORM setval(pg_get_serial_sequence('branches', 'id'), (SELECT max(id) FROM branches), true);
END $$;

COMMIT;
