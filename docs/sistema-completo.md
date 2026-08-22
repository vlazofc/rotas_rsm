# Rotas Admmendes Brasil — documentação completa do sistema

## 1. Visão geral

O Rotas Admmendes Brasil é uma plataforma operacional para controlar o ciclo logístico de rotas no Brasil: chegada ao armazém/CD, doca, carregamento, liberação, manifesto, saída, entregas, falhas, fechamento e auditoria.

O sistema atual é API-first e preparado para evoluir para PWA/app mobile. A implementação cobre a filial Brasil (Santo André - SP) com isolamento por `branch_id`; a arquitetura prevista no documento final permite evoluir para SaaS multiempresa com `tenant_id`, observabilidade, mapas, WhatsApp e IA preditiva.

## 2. Stack implementada

| Camada | Tecnologia |
|---|---|
| Frontend | React 18 + Vite + TypeScript + i18next |
| Backend | FastAPI + SQLAlchemy + Pydantic |
| Banco | PostgreSQL 16 + PostGIS |
| Fila | Redis + Celery |
| OCR/IA | Worker isolado com EasyOCR/Tesseract ou API externa (`OCR_ENGINE=ai`) |
| Storage | MinIO compatível com S3 |
| Proxy interno | Caddy |
| Entrada pública | Cloudflare Tunnel |
| Autenticação | JWT local; Entra ID preparado como evolução |
| Deploy | Docker Compose |

## 3. Estrutura de pastas

```text
apps/
  api/          Backend FastAPI, RBAC, módulos operacionais, Celery genérico
  web/          Portal React/Vite multilíngue
  ocr-worker/   Worker OCR isolado
docs/           Arquitetura, banco, fluxo, segurança e este guia
infra/          Caddy e Cloudflare Tunnel
scripts/        Deploy, firewall, backup, restore e bootstrap de servidor
docker-compose.yml
docker-compose.dev.yml
.env.example
```

## 4. Fluxo operacional

1. Operador cria rota manualmente ou envia manifesto.
2. Manifesto é salvo no MinIO e enviado para a fila `ocr`.
3. Worker OCR/IA extrai texto, mapeia JSON estruturado e marca o manifesto como `AGUARDANDO_CONFERENCIA`.
4. Operador confere/corrige os campos e confirma.
5. Sistema gera a rota com paragens/destinos.
6. Equipa registra chegada ao CD, entrada na doca, início/fim de carregamento, liberação e saída.
7. Motorista/operador registra check-in, entrega ou falha por motivo configurável.
8. Gestor fecha ou administrador reabre a rota para correção.
9. Ações sensíveis são gravadas em `audit_logs`.

Estados principais da rota:

```text
planejada -> em_carregamento -> liberada -> em_rota -> finalizada
```

Estados de manifesto:

```text
RECEBIDO -> PROCESSANDO_OCR -> AGUARDANDO_CONFERENCIA -> CONFERIDO -> ROTA_GERADA
```

## 5. Perfis e permissões

| Perfil | Uso |
|---|---|
| `admin_global` | Acesso total, reabertura de rotas, gestão global |
| `gestor_brasil` | Gestão operacional da filial, usuários, configurações e auditoria |
| `operador_logistico` | Rotas, doca, manifestos e liberação |
| `torre_controle` | Monitoramento e dashboards |
| `motorista` | Fluxo de rota, check-in e entrega |
| `auditor` | Consulta de auditoria e histórico |

O backend é a autoridade de permissão. A UI apenas esconde ações para melhorar a experiência.

## 6. Principais módulos

### Portal web

- Login JWT local.
- Dashboard operacional.
- Listagem e detalhe de rotas.
- Fluxo de doca e entrega.
- Manifestos com conferência humana.
- Configuração de filiais, perfis, motoristas, veículos e motivos de falha.
- Usuários e reset de palavra-passe/senha.
- Auditoria operacional.
- Idiomas `pt-BR` e `pt-PT`.

### API

Prefixo padrão: `/api`.

Endpoints principais:

| Área | Endpoint base |
|---|---|
| Autenticação | `/api/auth` |
| Dashboard | `/api/dashboard` |
| Rotas | `/api/routes` |
| Manifestos | `/api/manifests` |
| Usuários | `/api/users` |
| Filiais | `/api/branches` |
| Motoristas | `/api/drivers` |
| Veículos | `/api/vehicles` |
| Motivos de falha | `/api/failure-reasons` |
| Auditoria | `/api/audit` |

Documentação OpenAPI: `/docs`.

### OCR/IA worker

O OCR é isolado em `apps/ocr-worker`. Pode rodar localmente (`easyocr`/`tesseract`) ou enviar o arquivo para uma API externa (`OCR_ENGINE=ai`, `AI_OCR_PROVIDER=ocrspace`, `jmhelpdesk` ou `custom`). O contrato com o restante do sistema é o registro em `ocr_results.extracted_json`, que contém:

```json
{
  "codigo_ut": "123456",
  "data_carga": "2026-06-11",
  "hora_carga": "08:00",
  "origem": "Armazem",
  "destinos": [
    {
      "nome": "Cliente",
      "data_limite": "2026-06-12",
      "hora_limite": "10:00",
      "peso_kg": 1200,
      "paletes": 2,
      "pedido": "987654"
    }
  ]
}
```

A rota nunca é criada automaticamente pelo OCR. A conferência humana é obrigatória.

Exemplo para ligar um motor OCR/IA externo privado:

```env
OCR_ENGINE=ai
AI_OCR_PROVIDER=jmhelpdesk
AI_OCR_API_URL=https://api.jmhelpdask.com.br/ROTA_DE_LEITURA
AI_OCR_API_KEY=sua_chave_no_env
AI_OCR_AUTH_TYPE=header
AI_OCR_API_KEY_HEADER=x-api-key
```

Se a API usar Bearer token, use `AI_OCR_AUTH_TYPE=bearer`. Se usar Basic Auth,
use `AI_OCR_AUTH_TYPE=basic` e preencha `AI_OCR_BASIC_USERNAME` /
`AI_OCR_BASIC_PASSWORD`.

## 7. Modelo de dados

Tabelas principais:

```text
tenants, branches, users, role_profiles, drivers, vehicles,
routes, route_stops, dock_sessions, route_events,
manifests, ocr_results, checkins, delivery_proofs,
tolls, odometer_readings, attachments, audit_logs, notifications
```

`tenant_id` foi adicionado em paralelo a `branch_id` em `branches, users, drivers,
vehicles, routes, manifests, audit_logs, notifications` — preparação para
multiempresa SaaS sem alterar o isolamento atual por filial. Detalhes em
[visão e evolução](visao-evolucao.md).

Relações críticas:

- `routes` possui várias `route_stops` e `route_events`.
- `routes` possui uma `dock_session`.
- `manifests` possui um `ocr_result` e pode gerar uma `route`.
- `route_stops` pode apontar para comprovante em `attachments`.
- `audit_logs` registra ações administrativas e operacionais sensíveis.

Para produção, usar Alembic para migrações versionadas. O `create_all` atual facilita o bootstrap inicial.

## 8. Segurança

Controles implementados:

- JWT obrigatório nas rotas protegidas.
- RBAC no backend.
- Isolamento por filial via `branch_id`.
- Rate limit com SlowAPI.
- CORS configurável.
- Upload com validação de tipo e tamanho.
- MinIO/Postgres/Redis sem exposição pública no compose de produção.
- Auditoria de ações relevantes.
- Bloqueio de edição em rota finalizada/cancelada.
- Cloudflare Tunnel como única entrada pública.

Regras GDPR/LGPD:

- Monitorar localização apenas durante jornada operacional.
- Informar finalidade ao motorista.
- Restringir acesso por perfil.
- Configurar retenção e backups.
- Usar HTTPS e segredos fortes.

## 9. Variáveis de ambiente

Copie `.env.example` para `.env` e substitua todos os valores `trocar_*`.

Grupos relevantes:

- Aplicação: `APP_NAME`, `APP_ENV`, `APP_TIMEZONE`, `API_V1_PREFIX`.
- Domínio/CORS: `PUBLIC_DOMAIN`, `ALLOWED_ORIGINS`.
- Banco: `POSTGRES_*`, `DATABASE_URL`.
- Redis/Celery: `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`.
- MinIO: `MINIO_*`, `MINIO_BUCKET_MANIFESTS`, `MINIO_BUCKET_PROOFS`.
- JWT: `JWT_SECRET`, expiração e algoritmo.
- Auth corporativo: `AUTH_MODE`, `MICROSOFT_*`.
- OCR/IA: `OCR_ENGINE`, `OCR_LANG`, `OCR_MIN_CONFIDENCE`, `MAX_UPLOAD_MB`, `AI_OCR_PROVIDER`, `AI_OCR_API_URL`, `AI_OCR_API_KEY`, `AI_OCR_AUTH_TYPE`, `AI_OCR_API_KEY_HEADER`.
- Cloudflare: `CLOUDFLARE_TUNNEL_TOKEN`.
- Seed: `SEED_ADMIN_*`.

## 10. Execução local

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Serviços:

- Web: `http://localhost:5173`
- API/OpenAPI: `http://localhost:8000/docs`
- MinIO console: `http://localhost:9001`

Build frontend:

```bash
cd apps/web
npm install
npm run build
```

Validação Python local:

```bash
py -3.13 -m compileall apps/api/app apps/ocr-worker
```

## 11. Deploy produção

1. Preparar VPS:

```bash
sh scripts/init_server.sh
```

2. Configurar `.env` com segredos reais.

3. Configurar Cloudflare Tunnel e colar `CLOUDFLARE_TUNNEL_TOKEN`.

4. Aplicar firewall:

```bash
sh scripts/firewall.sh
```

5. Subir stack:

```bash
sh scripts/deploy.sh
```

6. Conferir saúde:

```bash
docker compose ps
docker compose logs -f api
docker compose logs -f ocr-worker
```

## 12. Backup e recuperação

O serviço `backup` executa `scripts/backup_postgres.sh` diariamente e grava arquivos em `backups/`.

Restore:

```bash
sh scripts/restore_postgres.sh backups/arquivo.sql.gz
```

Também é recomendável incluir rotina de backup do volume MinIO para preservar manifestos e comprovantes.

## 13. Roadmap alinhado à arquitetura final

### Curto prazo

- Ativar Alembic e versionar migrações.
- Finalizar callback Microsoft Entra ID.
- Adicionar testes automatizados de API e fluxo de manifesto.
- Adicionar comprovantes de entrega com foto/assinatura.
- Melhorar filtros de auditoria e exportação CSV.

### Médio prazo

- PWA/mobile para motorista.
- Mapa operacional com OpenStreetMap/OSRM.
- Geofencing e rastreamento em rota ativa.
- Observabilidade com Prometheus, Grafana e Loki.
- Backup MinIO automatizado.
- Relatórios executivos.

### Evolução SaaS corporativa

- Introduzir `tenant_id` em todas as entidades.
- Separar administração global, empresa e filial.
- PgBouncer e políticas de retenção por tenant.
- Integração WhatsApp Business/Evolution API.
- Worker de IA para interpretação documental avançada.
- Predição de atrasos, ETA e alertas proativos.

## 14. Critérios de pronto

Para considerar um release pronto:

- `npm run build` no frontend sem erros.
- `py -3.13 -m compileall apps/api/app apps/ocr-worker` sem erros.
- Login admin semente funcionando.
- Upload de manifesto cria registro e fila OCR.
- Conferência gera rota.
- Fluxo de doca respeita sequência.
- Entrega/falha registra evento.
- Auditoria lista ações recentes.
- Backup diário presente em `backups/`.
- `.env` sem valores `trocar_*` em produção.
