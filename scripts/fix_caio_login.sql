DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM users WHERE lower(email)='caio.haddad@adimax.com.br') THEN
    RAISE EXCEPTION 'O e-mail correto já está cadastrado em outro usuário.';
  END IF;
  UPDATE users
  SET email='caio.haddad@adimax.com.br', auth_version=auth_version+1, updated_at=now()
  WHERE lower(email)='caiohaddad@adimax.com.br';
  IF NOT FOUND THEN RAISE EXCEPTION 'Usuário Caio Haddad não encontrado.'; END IF;
END $$;
