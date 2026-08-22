# Banco de dados

PostgreSQL 16 + PostGIS. Modelos em `apps/api/app/db/models.py`.
No primeiro boot, `services/bootstrap.py` cria as tabelas (`create_all`), a filial
Brasil e o admin semente. Para migrações versionadas use Alembic (já no requirements).

## Tabelas
`tenants, branches, users, customers, carriers, drivers, vehicles, routes, route_stops, dock_sessions,
route_events, manifests, ocr_results, checkins, delivery_proofs, tolls,
odometer_readings, attachments, audit_logs, notifications`

## Relações principais
- `routes` 1—N `route_stops`, 1—N `route_events`, 1—1 `dock_sessions`.
- `manifests` 1—1 `ocr_results`; `manifests.route_id` → rota gerada.
- `route_stops.proof_attachment_id` → `attachments` (comprovante).
- Entidades SaaS são escopadas por `tenant_id`; entidades operacionais também
  mantêm `branch_id`. O backend valida a cadeia `usuário → filial → tenant`.
- `customers` são os clientes finais; `tenants` são as empresas assinantes.
- `carriers` são fornecedores/transportadoras isolados por tenant.

## Migrações (quando necessário)
```bash
docker compose exec api alembic init app/db/migrations   # uma vez
docker compose exec api alembic revision --autogenerate -m "msg"
docker compose exec api alembic upgrade head
```
> Para produção séria, prefira Alembic ao `create_all`.
