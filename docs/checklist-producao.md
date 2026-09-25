# Checklist de liberação para produção

## Antes da janela

- Criar uma tag/commit imutável da versão aprovada.
- Gerar segredos exclusivos de produção; nunca reutilizar `.env.local.example`.
- Confirmar `APP_ENV=production`, `RUN_DB_BOOTSTRAP=false` e somente origens HTTPS em `ALLOWED_ORIGINS`.
- Gerar backup do PostgreSQL e do MinIO e copiar ambos para armazenamento externo.
- Restaurar os dois backups em homologação e executar o smoke test.

## Migração e implantação

```sh
docker compose --profile maintenance run --rm migrate
docker compose up -d --build
docker compose ps
```

A API de produção não altera o schema durante o startup. A migração explícita usa a tabela
`app_bootstrap_versions` e deve terminar com código zero antes da subida da aplicação.

## Smoke test

- Admin Adimax lista todas as transportadoras e filiais.
- Master Alfa não vê rotas, alertas, ocorrências, proprietários, veículos ou usuários da Beta.
- Master não consegue atribuir perfis financeiro, diretoria, auditoria, global ou master diretamente.
- Primeiro master consegue nomear somente mais dois masters.
- Segundo master não consegue promover outro master.
- Login exige troca da senha temporária e o reset invalida tokens anteriores.
- Upload e abertura de CRLV/evidência funcionam pelo domínio HTTPS.
- Worker, scheduler, PostgreSQL, Redis, MinIO, API e proxy permanecem saudáveis.

## Rollback

- Manter a imagem/tag anterior disponível.
- Interromper gravações antes de restaurar banco ou arquivos.
- Restaurar PostgreSQL com `scripts/restore_postgres.sh`.
- Restaurar documentos com `scripts/restore_minio.sh` usando um diretório que contenha `BACKUP_COMPLETE`.
- Subir a versão anterior e repetir o smoke test.
