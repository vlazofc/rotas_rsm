# Documento Técnico Completo — Rotas Brasil RSM (Rotas Admmendes)

> Documento gerado a partir de análise direta do código-fonte (backend, frontend,
> worker de OCR, infraestrutura) em 2026-08-22, e **revisado em 2026-08-22** após o
> rebranding de "JM" para "Admmendes" (ver seção 0). Complementa e atualiza os
> documentos em `docs/` (que descrevem principalmente o estado da "Fase 1/Fase 2"
> do roadmap). O código atual já está bem além do que `README.md` e
> `docs/sistema-completo.md` descrevem — este documento reflete o estado real.

## 0. Rebranding "JM" → "Admmendes" (2026-08-22)

O produto foi originalmente construído sob a marca **"JM"** (JM Rotas, JM
Distribuição, JM Brasil/Portugal — nome do operador SaaS original). Nesta revisão,
todas as referências de marca no código, configuração e documentação foram
substituídas por **"Admmendes"**. Resumo do que mudou e do que foi mantido de
propósito:

**Alterado** (identificadores internos, nomes de exibição, templates):
- Nome do tenant/filial padrão criados no bootstrap: `Admmendes Brasil` /
  `Admmendes Distribuição - Brasil (Santo André)` (slug `admmendes-brasil`).
- `bootstrap.py` migra automaticamente instalações antigas: procura tenants com
  slug `jm-portugal` **ou** `jm-brasil` e renomeia para `admmendes-brasil` em vez
  de criar um tenant duplicado — importante para bancos já em produção.
- Nomes internos dos apps Celery (`admmendes` no `apps/api`, `admmendes_ocr` no
  `apps/ocr-worker`), logger raiz (`admmendes`), usuário padrão do MinIO
  (`admmendes`), modelo Ollama de treino (`admmendes-manifesto`).
- Domínio interno de contas de pré-visualização (`preview@{slug}.admmendes.internal`);
  o filtro que as esconde da listagem de usuários (`users/router.py`) passou a
  reconhecer **os dois domínios** (novo e `*.jm.internal` legado), para não vazar
  contas de preview já existentes em bancos antigos.
- `package.json` do frontend (`admmendes-rotas-web`), título/branding padrão em
  `pt-PT.json` e no fallback de iniciais em `Layout.tsx`.
- Valores de exemplo em `.env.example` (`POSTGRES_DB`, `POSTGRES_USER`,
  `MINIO_ROOT_USER`, `SEED_ADMIN_EMAIL`) e nomes de arquivo de backup
  (`admmendes_rotas_*.sql.gz` — a rotina de retenção em `backup_postgres.sh`
  continua limpando também o padrão antigo `jm_rotas_*.sql.gz`).
- README, todos os `docs/*.md` e `infra/cloudflare/README-tunnel.md`.

**Mantido intencionalmente** (não são branding nosso — são integrações externas
reais ou segredos ativos; renomear quebraria a conexão):
- A chave de provedor `jmhelpdesk` em `AI_OCR_PROVIDER`/`ai_client.py`/`settings.py`
  — identifica um serviço externo de OCR real (domínio `jmhelpdask.com.br`).
- `SHAREPOINT_FILE_URL` no `.env` — aponta para o tenant SharePoint real de um
  cliente (`jmtransportesdistribuicao-my.sharepoint.com`).
- `JWT_SECRET` no `.env` (prefixo `jmpt_`) — segredo de assinatura já em uso;
  trocá-lo invalidaria todas as sessões ativas sem necessidade.
- O nome de arquivo de exemplo `TORRE DE CONTROLE ADESTE - JM_MRD.xlsx` em
  comentários/docstrings — descreve a convenção real de nomeação usada pelo
  cliente externo, não muda com o rebranding do operador.
- `apps/web/dist/` (build gerado — será regenerado no próximo `npm run build`),
  `package-lock.json` (será resincronizado no próximo `npm install`),
  `apps/ocr-worker/knowledge_base_legacy_pt/**` (dataset/prompts de treino do
  piloto Portugal/Salvesen, conteúdo de dados, não branding de código) e
  `.tmp_audit/**` (artefatos históricos de auditoria, não código ativo).

---

## 1. Visão geral do produto

**Rotas Brasil RSM** (nome interno do repositório: `rotas-admmendes` / título da API:
"Rotas Brasil RSM") é uma plataforma **SaaS multiempresa (multi-tenant)** de gestão
operacional de logística e transporte: controla o ciclo completo de uma rota de
entrega — desde a chegada do veículo ao centro de distribuição (CD), passando pela
doca, carregamento, liberação, manifesto (com leitura automática por IA/OCR),
saída, entregas ponto a ponto, ocorrências e devoluções, até o fechamento e
auditoria — além de um módulo financeiro (receitas/despesas por rota) e
relatórios operacionais e financeiros.

Diferente do que a documentação anterior descreve (uma plataforma apenas para a
filial Brasil de uma empresa), o código implementa hoje um modelo **SaaS real**:
- `Tenant` = empresa cliente da plataforma (ex.: Admmendes Brasil, e outros clientes).
- `Branch` = filial/armazém, sempre associada a um `Tenant`.
- Cada tenant tem **feature flags** próprias (`feature_ocr`, `feature_financeiro`,
  `feature_rastreamento`, `feature_route_optimization`, `feature_km_calculation`,
  `feature_sharepoint_sync`) e dados de faturação SaaS (`billing_plan`,
  `billing_amount`, `billing_due_day`, `billing_last_payment_date`).
- Um perfil `admin_global` administra todos os tenants; um botão de
  **"sessão de pré-visualização"** (`POST /tenants/{id}/preview-session`) permite ao
  admin logar temporariamente como um tenant específico para suporte.

## 2. Stack tecnológica (confirmada no código)

| Camada | Tecnologia | Versão observada |
|---|---|---|
| Frontend | React 18.3 + Vite 6 + TypeScript 5.7 + i18next/react-i18next | `apps/web/package.json` |
| Mapas (frontend) | Leaflet 1.9 (+ `@types/leaflet`), tiles locais em `map-tiles/` | `RouteMap.tsx` |
| Roteamento SPA | react-router-dom 7.1 | — |
| HTTP client | axios 1.7 | `services/api.ts` |
| Backend | FastAPI 0.115 + Uvicorn/Gunicorn 4 workers | `apps/api/requirements.txt` |
| ORM | SQLAlchemy 2.0 (Mapped/typed models) + Alembic 1.14 (instalado, não usado ainda — schema via `create_all`) | `db/models.py` |
| Banco | PostgreSQL 16 + PostGIS 3.4 (`postgis/postgis:16-3.4`) | `docker-compose.yml` |
| Geo | GeoAlchemy2 (instalado, colunas lat/lng simples ainda são `Float`, não `geometry`) | — |
| Fila / Workers | Redis 7 + Celery 5.4 (broker/back-end separados por DB Redis 1/2) | — |
| Rate limiting | SlowAPI (`240/minute` por IP, global) | `main.py` |
| Auth | JWT local (python-jose + passlib/bcrypt) + Microsoft Entra ID (MSAL, OIDC) | `modules/auth` |
| OCR/IA | Motor plugável: EasyOCR, Tesseract, API externa genérica (`ai`), IA visual local via Ollama (`vision_llm`), Google Gemini (`gemini`) | `apps/ocr-worker/pipeline` |
| Extração estruturada | Regras (regex + base de conhecimento) **ou** LLM local via Ollama (endpoint OpenAI-compatível) | `EXTRACTOR=rules\|llm` |
| Roteirização/KM | Serviço externo "maestro" (`router_run`, GraphHopper) via HTTP, com geocodificação (ViaCEP/Photon/Nominatim) | `services/routing.py` |
| Storage | MinIO (S3-compatível) — 3 buckets: manifestos, comprovantes, branding | `services/storage.py` |
| Integração externa | Microsoft Graph / SharePoint (sync automática de planilha "Torre de Controle") | `services/sharepoint.py` |
| Proxy interno | Caddy 2 | `infra/Caddyfile` |
| Entrada pública | Cloudflare Tunnel (`cloudflared`, perfil docker `cloudflare`) | — |
| Deploy | Docker Compose (dev e produção), VPS Hostinger | `docker-compose*.yml` |
| E-mail/planilhas | openpyxl (exportação `.xlsx`) | `expenses/router.py`, `routes_import` |

## 3. Estrutura de pastas (real, não apenas a do README)

```text
apps/
  api/                    Backend FastAPI
    app/core/             config, security (JWT), permissions (RBAC), logging
    app/db/               models.py (ORM), session.py
    app/services/         audit, bootstrap, events, storage, routing, sharepoint,
                           generic_route_import, torre_controle_import
    app/workers/          celery_app.py (worker genérico + beat/scheduler)
    app/modules/          20 módulos de domínio (ver seção 5)
  web/                    Frontend React/Vite (13 páginas, 4 componentes-base)
  ocr-worker/             Worker Celery isolado (fila "ocr")
    pipeline/             preprocess, readers (EasyOCR/Tesseract), ai_client,
                           vision_extractor, gemini_extractor, llm_extractor, mapper
    knowledge_base_legacy_pt/  base de exemplos/prompts + export de dataset de treino
docs/                     Documentação (parcialmente desatualizada — ver seção 12)
infra/                    Caddyfile + Cloudflare Tunnel
scripts/                  deploy, backup/restore Postgres, firewall, init_server,
                           import_torre_controle.py, train.sh
map-tiles/                Tiles de mapa hospedados localmente (zoom 6–9)
backups/                  Dumps diários do Postgres (retenção)
test-artifacts/, .tmp_audit/   artefatos de testes/auditoria (não versionados no core)
```

## 4. Arquitetura de infraestrutura

```
Usuário (web) ──HTTPS──> Cloudflare (DNS+WAF+Access) ──túnel (saída 7844)──> cloudflared
                                                                                  │
                                                                                  ▼
                                                                        Caddy (proxy :80)
                                                        ┌─────────────────────┴─────────────────────┐
                                                        ▼                                             ▼
                                              web (SPA, build nginx)                     api (FastAPI, gunicorn+uvicorn, 4 workers)
                                                                                                        │
                                              ┌──────────────────────┬───────────────┬────────────────┼───────────────────┐
                                              ▼                      ▼               ▼                ▼                   ▼
                                        PostgreSQL+PostGIS         Redis          MinIO        worker (Celery genérico)  scheduler (Celery beat)
                                                                     │
                                                                     ▼ fila "ocr"
                                                              ocr-worker (Celery, concurrency=1)
                                                                     │
                                                          Local (EasyOCR/Tesseract) | AI OCR externo | Ollama (vision_llm) | Gemini
```

Serviços adicionais no `docker-compose.yml`:
- **`training-export`**: roda diariamente, exporta conferências humanas confirmadas
  para uma base de conhecimento/dataset versionável em Git — usada para melhorar
  extração por regras/LLM ao longo do tempo (aprendizado incremental "manual").
- **`ollama`** (perfil `llm`, opcional): motor de IA local para extração estruturada
  (`EXTRACTOR=llm`) ou leitura visual direta do manifesto (`OCR_ENGINE=vision_llm`,
  modelo sugerido `qwen2.5vl:7b`).
- **`backup`**: roda `scripts/backup_postgres.sh` a cada 24h, grava em `backups/`.

Mapeamento de portas em desenvolvimento local (`docker-compose.yml`):
| Serviço | Porta local | Descrição |
|---|---|---|
| proxy (Caddy) | 8089 | Ponto de entrada único |
| api | 8001 | `/docs`, `/health` |
| postgres | 5434 | evita conflito com Postgres local |
| redis | 6380 | — |
| minio | 9002 / 9003 | API S3 / console |

Redes: um único bridge `internal`; nenhum serviço além de `proxy`/`cloudflared`
expõe porta pública em produção real (as portas do compose acima são só para dev
local — no compose de produção completo, ver `infra/`).

## 5. Backend — módulos de domínio (`apps/api/app/modules`)

O backend tem **20 módulos**, bem mais do que os ~9 descritos em `docs/sistema-completo.md`:

| Módulo | Responsabilidade | Endpoints principais |
|---|---|---|
| `auth` | Login local JWT, refresh, troca de senha, login/callback Entra ID (OIDC) | `POST /auth/login`, `/refresh`, `GET /auth/me`, `POST /auth/change-password`, `GET /auth/entra/login`, `GET /auth/callback` |
| `users` | CRUD de usuários, perfis (`role_profiles`) configuráveis, reset de senha | `GET/POST/PUT /users`, `GET /users/roles`, CRUD `/users/role-profiles` |
| `tenants` | Gestão de empresas SaaS (só `admin_global`), marcação de pagamento, sessão de pré-visualização | `GET/POST/PUT /tenants`, `GET /tenants/me`, `POST /tenants/{id}/mark-paid`, `POST /tenants/{id}/preview-session` |
| `branches` | CRUD de filiais | `GET/POST/PUT/DELETE /branches` |
| `drivers` | CRUD de motoristas, vínculo opcional a `carrier` (transportadora) e a `user` | `GET/POST/PUT/DELETE /drivers` |
| `vehicles` | CRUD de veículos, tipo (`vehicle_types`), flag de câmara fria | `GET/POST/PUT/DELETE /vehicles` |
| `vehicle_types` | Tipologias de veículo configuráveis (Config) | CRUD |
| `carriers` | Transportadoras/fornecedores por tenant | CRUD |
| `customers` | Clientes finais atendidos pelo tenant | CRUD |
| `routes` | Núcleo operacional: rotas, paradas, eventos de doca/entrega, pedágios, correções administrativas | ver seção 6 (28 endpoints) |
| `routes_import` | Importação em massa de rotas via planilha (Fieldeas / Torre de Controle) | `GET /routes_import/template.xlsx`, `POST /routes_import/upload` |
| `manifests` | Upload de manifesto, sugestões, conferência humana, geração de rota | `GET/POST /manifests`, `/upload`, `/{id}/confirm`, `/{id}/generate-route` |
| `sync` | Sincronização automática com SharePoint (planilha "Torre de Controle" do cliente) | `GET /sync/torre-controle/status`, `POST /sync/torre-controle` |
| `dashboard` | KPIs operacionais + endpoint de mapa (posições/rotas ativas) | `GET /dashboard/summary`, `GET /dashboard/map` |
| `expenses` | Despesas por motorista/rota (combustível, pedágio, etc.), exportação Excel, lote mensal zipado | `GET/POST/PUT/DELETE /expenses`, `/export.xlsx`, `/batch/{ano}/{mes}.zip` |
| `revenues` | Receitas lançadas por rota (contraparte financeira das despesas) | CRUD, restrito a `gestor_financeiro`/financeiro |
| `reports` | 10 relatórios operacionais/financeiros (tempos de doca, produtividade, ocorrências, balancete) | 10 endpoints `GET`, incl. `GET /reports/balancete` |
| `failure_reasons` | Motivos de falha de entrega configuráveis | CRUD |
| `operational_settings` | Parâmetros operacionais gerais (por tenant) | `GET/PUT` |
| `branding` | Personalização visual por tenant (nome do app, cores, logo, favicon, fundo de login) | `GET/PUT /branding` |
| `audit` | Consulta de auditoria (somente leitura) | `GET /audit` |

**Total observado: ~90 endpoints REST**, todos sob o prefixo `/api` (`API_V1_PREFIX`).
Documentação interativa automática via OpenAPI em `/docs` e `/openapi.json`.

### 5.1 `core/` — infraestrutura transversal

- `core/config.py`: `Settings` (Pydantic Settings) carrega tudo de `.env`; nenhuma
  configuração fica hardcoded fora de defaults de desenvolvimento.
- `core/security.py`: geração/validação de JWT, hashing de senha (bcrypt).
- `core/permissions.py`: RBAC completo — ver seção 7.
- `core/logging.py`: logging estruturado (`python-json-logger`).

### 5.2 `services/` — lógica de domínio compartilhada

- `bootstrap.py`: roda no `lifespan` do FastAPI — cria tabelas (`create_all`,
  **sem Alembic** apesar de instalado), o tenant/filial padrão, o admin semente
  (`SEED_ADMIN_*`), e aplica `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` para colunas
  novas em bancos de dev já existentes (estratégia de migração "leve" documentada
  em `visao-evolucao.md`).
- `audit.py`: grava `audit_logs` (ação, entidade, ip, detalhe) de forma centralizada.
- `events.py`: helper para inserir `route_events` de forma consistente.
- `storage.py`: abstração sobre MinIO (upload, URL assinada, buckets).
- `routing.py`: cliente HTTP para o serviço externo de roteirização "maestro"
  (`ROUTER_BASE_URL`, GraphHopper) — calcula KM ida/volta entre filial e destino,
  mapeando texto livre de tipo de veículo para o enum aceito pelo router.
- `sharepoint.py`: cliente Microsoft Graph para baixar a planilha "Torre de
  Controle" de um SharePoint do cliente (client credentials / MSAL).
- `torre_controle_import.py` / `generic_route_import.py`: parsers de planilhas
  Excel (formato "Torre de Controle" e formato genérico/Fieldeas) que alimentam
  `routes_import` e a sincronização automática.

### 5.3 `workers/` — Celery

- `celery_app.py`: app Celery genérico (fila default) para tarefas de notificação
  e cálculo (worker "genérico" do compose), mais o `scheduler` (Celery beat) —
  provavelmente dispara a sincronização periódica do SharePoint e o backup.

## 6. Módulo `routes` — núcleo operacional (detalhado)

É o módulo mais extenso (28 rotas em `routes/router.py`, ~940 linhas). Cobre:

**CRUD e composição**
`GET/POST /routes`, `GET /routes/{id}`, `PUT /routes/{id}`, `DELETE /routes/{id}/exclude`
(soft-delete via `excluded=true`, não remove fisicamente), `POST/PUT/DELETE .../stops`,
`POST /routes/{id}/optimize-sequence` (reordenação de paradas, provavelmente usando o
serviço de roteirização).

**Fluxo de doca/CD (eventos auditáveis, ver `dock_sessions`)**
```
POST /routes/{id}/arrive-cd        → ARRIVED_CD
POST /routes/{id}/enter-dock       → ENTERED_DOCK
POST /routes/{id}/loading-start    → LOADING_STARTED
POST /routes/{id}/loading-finish   → LOADING_FINISHED
POST /routes/{id}/release          → OPERATOR_RELEASED
POST /routes/{id}/depart           → DEPARTED_CD
POST /routes/{id}/force-start      → início forçado (bypass de sequência, provavelmente restrito)
```
Cada transição calcula automaticamente os campos de `dock_sessions`
(`waiting_before_dock_minutes`, `loading_minutes`, `waiting_release_minutes`,
`total_cd_minutes`).

**Entrega / ocorrências**
```
POST /routes/{id}/stops/{stop}/checkin               → ARRIVED_STOP
POST /routes/{id}/stops/{stop}/deliver                → DELIVERED | FAILED_DELIVERY
POST /routes/{id}/stops/{stop}/deliver-with-proof     → entrega + upload de comprovante (Attachment)
POST /routes/{id}/stops/{stop}/warehouse-return-proof → comprovante de devolução ao armazém
```
`RouteStop` suporta devolução **total ou parcial** (`return_type`, `returned_quantity`)
e vínculo a `delivery_failure_reasons` configuráveis.

**Fechamento e correções administrativas**
```
POST /routes/{id}/close             → ROUTE_CLOSED
POST /routes/{id}/reopen            → reabertura (auditada, papel restrito)
POST /routes/{id}/admin-correction  → correção pós-fechamento no nível da rota
POST /routes/{id}/stops/{stop}/admin-correction → idem por parada
```

**Financeiro/operacional por rota**
```
POST/DELETE /routes/{id}/tolls   → lançamento individual de pedágio (ida/volta), tabela route_tolls
PUT /routes/{id}/km              → KM informado ou calculado (km_source: informado | calculado)
```

**Origem da rota (`Route.source`)**: `manual` | `automatico` (gerada por OCR) |
`fieldeas` (importada de planilha) — o mesmo modelo `Route` atende os três fluxos,
com campos específicos para integração Fieldeas (`fieldeas_description`,
`fieldeas_sync_at`) e para dados importados da planilha "Torre de Controle"
(`vehicle_requested`, `vehicle_sent`, `helper_assigned`, `tracked`, `raw_import_json`).

**Estados da rota**: `planejada → em_carregamento → liberada → em_rota → finalizada`
(ou `cancelada`), como documentado; **estados da parada** (`RouteStop.status`):
`pendente → em_rota → entregue | falha | devolvido`.

## 7. Segurança e RBAC

O RBAC é **inteiramente aplicado no backend** (`core/permissions.py`); a UI apenas
esconde ações. Confirma-se que o modelo evoluiu de 6 para **7 perfis**:

| Perfil (`Role`) | Ordem | Descrição |
|---|---|---|
| `admin_global` | 10 | Acesso total, atravessa tenants, gerencia usuários/filiais/integrações |
| `auditor` | 20 | Só leitura — auditoria, histórico, relatórios |
| `gestor_brasil` | 30 | Gestão operacional da filial (usuários, motoristas, veículos, manifesto, rotas) |
| `gestor_financeiro` | 35 | **Novo** — lança receitas/despesas, vê balancete e dashboard financeiro |
| `motorista` | 40 | Só as próprias rotas — check-in, entrega |
| `operador_logistico` | 50 | Doca, manifesto, liberação de carregamento |
| `torre_controle` | 60 | Monitoramento/dashboard em tempo real |

Camadas de controle:
1. `require_roles(*roles)` — dependência FastAPI que bloqueia por perfil (admin
   global sempre passa).
2. `require_same_branch` / `require_branch_access` — isola por `branch_id`,
   valida que a filial existe, está ativa e pertence ao mesmo tenant do usuário
   antes de qualquer gravação.
3. `require_same_tenant` — isola por `tenant_id` (bloqueia cross-tenant mesmo que
   o ID seja adivinhado na URL/payload).
4. `require_feature(feature)` — bloqueia módulos desativados no plano do tenant
   (`feature_ocr`, `feature_sharepoint_sync`, `feature_financeiro`,
   `feature_rastreamento`).

Outras proteções confirmadas no código:
- Rate limit global 240 req/min por IP (SlowAPI), configurado em `main.py`.
- CORS restrito a `ALLOWED_ORIGINS` (lista explícita, não wildcard).
- Upload validado por tipo/tamanho (`MAX_UPLOAD_MB`), arquivos ficam no MinIO
  (fora do container da API).
- Senhas com bcrypt (`passlib`); JWT assinado (`HS256` por padrão) com expiração
  de access token (60 min) e refresh token (7 dias) configuráveis.
- Auth corporativa opcional via Microsoft Entra ID (`AUTH_MODE=entra`, MSAL) —
  login/callback implementados em `auth/router.py`.
- Nenhum segredo hardcoded: tudo lido de `.env` via `pydantic-settings`; `.env`
  está no `.gitignore`.
- **Sessão de pré-visualização** (`tenants/{id}/preview-session`) é um ponto de
  atenção de segurança: permite ao `admin_global` emitir um token que atua como
  outro tenant — deve ser auditada e ter escopo/tempo de vida restritos (revisar
  se está implementada com logging obrigatório em `audit_logs`).

## 8. Modelo de dados (schema completo confirmado)

24 tabelas em `apps/api/app/db/models.py` (vs. ~18 documentadas anteriormente):

```
tenants, branches, users, role_profiles, carriers, customers,
drivers, vehicles, vehicle_types,
routes, route_tolls, route_stops, route_stop_operations,
delivery_failure_reasons, dock_sessions, route_events,
manifests, ocr_results, checkins, delivery_proofs,
tolls, odometer_readings, attachments,
branding_settings, expenses, revenues,
audit_logs, notifications
```

Destaques não documentados anteriormente:
- **`route_tolls`** — substitui/complementa `tolls` com lançamentos individuais
  por direção (`ida`/`volta`), quem lançou (`recorded_by`).
- **`route_stop_operations`** — suporta múltiplas operações (pedidos/volumes)
  dentro de uma mesma parada, modelo específico para integração Fieldeas
  (`fieldeas_code`, `order_id`, `pallets_provided`, `weight_provided`).
- **`expenses`** e **`revenues`** — módulo financeiro completo por rota/motorista/
  veículo, com anexo de comprovante e leitura de hodômetro; suporta lançamento
  manual e importação em lote (`source: manual | import`).
- **`branding_settings`** — personalização por tenant (nome do app, subtítulo,
  cor primária, locales habilitados, logo/logo do rail/fundo/favicon via
  `Attachment`); `tenant_id` nulo = branding padrão da plataforma.
- **`role_profiles`** — perfis deixaram de ser só o `Enum` fixo: existe uma tabela
  editável (label, descrição, permissões em JSON, ordem, ativo/inativo, flag
  `system` para os perfis nativos) — a Configuração no frontend permite gerenciar
  perfis sem deploy.
- **Preenchimento automático de `tenant_id`**: um listener SQLAlchemy
  (`before_insert`) copia `tenant_id` de `Branch` (para `User, Driver, Vehicle,
  Route, Manifest, Expense, Revenue`) ou de `User` (para `AuditLog, Notification`)
  — garante que nenhum registro operacional fique "órfão" de tenant mesmo que o
  módulo não informe o campo explicitamente. É uma decisão de design elegante
  para isolar dados por empresa sem exigir disciplina manual em cada endpoint.

Migrações: **Alembic está instalado mas não inicializado** (`bootstrap.py` usa
`create_all` + `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` manual). Isso é uma
dívida técnica conhecida e documentada (`visao-evolucao.md`), aceitável em fase
de MVP mas arriscado à medida que o schema cresce — mudanças destrutivas (rename/
drop de coluna) não são cobertas pela estratégia atual.

## 9. Pipeline de OCR/IA (worker isolado)

Fluxo (`apps/ocr-worker/worker.py`, tarefa Celery `ocr.process_manifest`, fila `ocr`):

1. Baixa o arquivo do MinIO (`manifestos/...`).
2. Escolhe o motor de leitura, **em ordem de prioridade**:
   `gemini` → `vision_llm` (Ollama) → `ai` (API externa genérica) → OCR local
   (EasyOCR/Tesseract). Cada motor externo tem **fallback automático para OCR
   local** em caso de exceção (não derruba o processamento do manifesto).
3. Extrai campos estruturados (`codigo_ut`, `data_carga`, `origem`, `destinos[]`
   com nome/endereço/data-hora limite/peso/paletes/pedido) via regras (regex +
   base de conhecimento) ou LLM.
4. Grava `ocr_results` (texto bruto, JSON extraído, confiança, `needs_review`).
5. **Conferência automática condicional**: se a confiança ≥ `OCR_MIN_CONFIDENCE`
   (padrão 0.82–0.88 conforme o `.env`) **e** os campos obrigatórios (`codigo_ut`,
   `data_carga`) foram extraídos, a rota é **criada ou atualizada automaticamente**
   (`_auto_generate_route`) e o manifesto vai direto para `ROTA_GERADA` — isto é
   uma evolução importante em relação ao que os docs descrevem ("a rota nunca é
   criada automaticamente pelo OCR"): **hoje ela pode ser**, quando a confiança é
   alta. Quando a confiança é baixa, o manifesto cai em `AGUARDANDO_CONFERENCIA`
   para revisão humana, como antes.
6. Se o manifesto já estava vinculado a uma rota criada manualmente, o worker
   **atualiza** essa rota (preserva datas/horários já registrados de doca) em vez
   de duplicar.
7. Toda geração automática grava eventos (`route_events` → `MANIFEST_VALIDATED`)
   e auditoria (`audit_logs` → `auto_generate_route`).
8. Em qualquer falha, o manifesto vai para `ERRO_OCR` com a mensagem de erro
   truncada, sem derrubar o worker (try/except amplo + rollback).

Motores de OCR/IA suportados (`OCR_ENGINE`): `easyocr` (padrão), `tesseract`,
`ai` (`ocrspace` | `custom` | `jmhelpdesk`, com `AI_OCR_AUTH_TYPE` header/bearer/
basic/none), `vision_llm` (imagem direto para modelo multimodal local via Ollama,
ex. `qwen2.5vl:7b`), `gemini` (Google Gemini 2.5 Flash, API gratuita).
Extrator estruturado (`EXTRACTOR`): `rules` (offline, sem custo) ou `llm` (Ollama,
ex. `llama3.1:8b`, endpoint OpenAI-compatível).

Isso confirma o princípio de arquitetura "OCR isolado e trocável" (README/
`arquitetura.md`) — e mostra que já foi bem além de Paddle/Tesseract: o sistema
suporta **cinco motores diferentes de leitura**, selecionáveis só por variável de
ambiente, sem alterar código do restante da plataforma.

**Aprendizado incremental**: o serviço `training-export` (compose) roda
diariamente e exporta as conferências humanas confirmadas para
`apps/ocr-worker/knowledge_base_legacy_pt/` — uma base de exemplos/prompts/dataset
versionável em Git que alimenta o extrator por regras/LLM. A base atual é
herdada de um piloto anterior (Portugal/Salvesen) e precisa ser substituída por
exemplos do Brasil (comentário explícito no `docker-compose.yml`).

## 10. Roteirização e cálculo de KM

`services/routing.py` chama um serviço externo chamado **"maestro" (`router_run`,
baseado em GraphHopper)**, não documentado anteriormente:
- `ROUTER_BASE_URL` (padrão `http://localhost:3005` em dev).
- Geocodifica endereços internamente (ViaCEP, Photon, Nominatim) — a API não
  precisa resolver coordenadas antes de chamar.
- `calculate_round_trip_km` calcula ida e volta **separadamente** (a distância
  pode ser assimétrica por vias de mão única/restrições para caminhões).
- Mapeia texto livre do campo "veículo solicitado/enviado" (planilha Torre de
  Controle) para os enums aceitos pelo router (`truck_articulated`,
  `truck_large`, `truck_medium`, fallback `car`).
- Falhas do router não quebram o fluxo — apenas loga aviso e retorna `None`
  (KM permanece "informado" manualmente em vez de "calculado").

Isto é um serviço externo ao repositório (não está em `apps/`) — provavelmente
outro projeto/container que precisa estar acessível na mesma rede Docker
(comentário no `.env.example` menciona trocar para `http://maestro:3000` quando
entrar na rede interna).

## 11. Integrações externas confirmadas

| Integração | Uso | Configuração |
|---|---|---|
| Microsoft Entra ID (OIDC) | Login corporativo alternativo ao JWT local | `AUTH_MODE=entra`, `MICROSOFT_*` |
| Microsoft Graph / SharePoint | Sincronização automática da planilha "Torre de Controle" do cliente (arquivo Excel compartilhado) | `SHAREPOINT_*`, módulo `sync` |
| Google Gemini | Leitura visual de manifesto (IA generativa multimodal) | `GEMINI_API_KEY`, `OCR_ENGINE=gemini` |
| Ollama (self-host) | LLM local para extração estruturada ou leitura visual (sem dados saindo do servidor) | perfil docker `llm`, `OCR_LLM_*` / `VISION_LLM_*` |
| OCR.space / provedor de IA genérico | OCR externo via API HTTP configurável (header/bearer/basic auth) | `AI_OCR_*` |
| Serviço "maestro" (router_run/GraphHopper) | Cálculo de distância/KM e (futuramente) otimização de sequência de paradas | `ROUTER_BASE_URL` |
| Cloudflare Tunnel | Única porta pública de entrada, sem abrir portas na VPS | `CLOUDFLARE_TUNNEL_TOKEN` |

## 12. Divergências entre a documentação existente (`docs/`) e o código atual

Esta análise encontrou lacunas relevantes entre `docs/sistema-completo.md` /
`docs/visao-evolucao.md` (a versão mais recente) e o código real:

| Item | Documentado | Código real |
|---|---|---|
| Perfis RBAC | 6 perfis | **7 perfis** — `gestor_financeiro` adicionado |
| Módulos de API | ~9 (`auth, dashboard, routes, manifests, users, branches, drivers, vehicles, failure-reasons, audit`) | **20 módulos**, incl. `tenants, carriers, customers, vehicle_types, expenses, revenues, reports, branding, operational_settings, sync, routes_import` |
| Tabelas | ~18 | **28 tabelas**, incl. `route_tolls, route_stop_operations, expenses, revenues, branding_settings, role_profiles` como tabela editável |
| Criação automática de rota por OCR | "a rota nunca é criada automaticamente pelo OCR" | **é criada automaticamente quando a confiança do OCR é alta** (`_auto_generate_route`) |
| Motores de OCR | Paddle/Tesseract/EasyOCR | **EasyOCR/Tesseract + AI externa + IA visual local (Ollama) + Gemini**, com fallback em cascata |
| Módulo financeiro | Não mencionado | Completo: despesas, receitas, balancete, exportação Excel |
| Multiempresa SaaS | "em andamento" (Fase 3, roadmap) | **Já implementado**: `tenants`, feature flags, billing, preview-session, isolamento cross-tenant no RBAC |
| Roteirização/mapas | "Fase 4, não iniciado" | **Parcialmente implementado**: cálculo de KM via serviço externo "maestro", endpoint `dashboard/map`, componente `RouteMap.tsx` (Leaflet) já existem |
| Integração SharePoint | Não mencionada | Sincronização automática implementada (`services/sharepoint.py`, módulo `sync`) |
| Importação de planilhas | Não mencionada | Módulo `routes_import` (upload de planilha, template `.xlsx`) + import "Torre de Controle" (script `scripts/import_torre_controle.py`) |

**Recomendação**: os documentos em `docs/` (especialmente `sistema-completo.md` e
o README) deveriam ser atualizados ou substituídos por este documento, para
evitar decisões de arquitetura futuras baseadas em informação desatualizada.

## 13. Pontos de atenção / dívida técnica identificados

1. **Sem migrações versionadas (Alembic instalado, não usado).** `create_all` +
   `ALTER TABLE ADD COLUMN IF NOT EXISTS` manual no `bootstrap.py` não cobre
   renomeações, drops, mudanças de tipo ou constraints — risco crescente à medida
   que o schema (já com 28 tabelas) evolui. Prioridade alta para produção séria.
2. **Coordenadas como `Float` simples, não `geometry` PostGIS.** `PostGIS` está
   instalado no banco mas os campos `latitude`/`longitude` em `route_stops`,
   `route_events`, `checkins` são pares de `Float`, não tipo `geometry(Point)` —
   limita o uso de índices espaciais e consultas geoespaciais nativas (distância,
   dentro-do-raio, geofencing) que o roadmap (Fase 4) prevê.
3. **Sessão de "preview" cross-tenant** (`tenants/{id}/preview-session`) é um
   vetor sensível — deve ter tempo de vida curto, escopo restrito e auditoria
   obrigatória; vale uma revisão de segurança dedicada.
4. **Fallback silencioso entre motores de OCR/IA** (Gemini → vision_llm → ai →
   local) é bom para disponibilidade, mas pode mascarar custos inesperados
   (chamadas a API paga) ou degradação de qualidade sem alertar operação — vale
   emitir métricas/alertas por motor usado.
5. **Dependência de serviço externo "maestro"** para KM/roteirização não está no
   monorepo nem documentada em `docs/` — comportamento de fallback (`None` em
   caso de erro) é seguro, mas a operação e o deploy desse serviço não estão
   descritos em nenhum lugar do repositório atual.
6. **Base de conhecimento de OCR herdada de outro piloto** (Portugal/Salvesen) —
   comentário explícito no compose indica que precisa ser substituída por dados
   reais do Brasil; enquanto isso, a extração por regras/LLM pode ter viés/baixa
   precisão para o domínio brasileiro.
7. **Rate limit único global (240/min por IP)** — não diferencia endpoints
   pesados (upload de manifesto, exportação Excel/zip) de leitura simples; pode
   valer limites por rota no futuro.

## 14. Ambientes e operação

**Desenvolvimento local**
```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```
- Web (Vite dev): `cd apps/web && npm install && npm run dev` → `http://localhost:5173`
- API/OpenAPI: `http://localhost:8001/docs` (via compose) ou `:8000` (execução direta)
- MinIO console: `http://localhost:9003`
- Login inicial: `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD`

**Produção (VPS Hostinger + Cloudflare Tunnel)**
```bash
sh scripts/init_server.sh        # provisiona o servidor (root)
cp .env.example .env && nano .env
sh scripts/firewall.sh           # fecha tudo, libera SSH + saída 7844
sh scripts/deploy.sh             # docker compose up -d --build
docker compose --profile cloudflare up -d --build   # inclui o túnel
```

**Backup**: serviço `backup` roda `scripts/backup_postgres.sh` a cada 24h,
grava em `backups/` (retenção 14 dias conforme `docs/seguranca.md`). Restore:
`sh scripts/restore_postgres.sh backups/arquivo.sql.gz`. **Não há backup
automatizado do volume MinIO** documentado — recomendação já presente no
`README.md`, ainda pendente.

**Critérios de release** (de `docs/sistema-completo.md`, ainda válidos):
`npm run build` sem erros; `py -3.13 -m compileall apps/api/app apps/ocr-worker`
sem erros; login admin semente funcional; upload → fila OCR → conferência →
rota; fluxo de doca respeita sequência; entrega/falha gera evento; auditoria
lista ações recentes; backup diário presente; `.env` sem valores `trocar_*`.

## 15. Roadmap — estado real vs. planejado

Com base no código, o roadmap do README (Fases 1–10) deveria ser reclassificado:

| Fase | Descrição | Status real |
|---|---|---|
| 1 — Fundação | login, RBAC, filiais, motoristas, veículos, rotas, doca, dashboard, auditoria | ✅ completo |
| 2 — Manifesto com IA | upload, OCR (multi-motor), conferência, geração de rota | ✅ completo — e mais avançado que o planejado (5 motores, geração automática) |
| 3 — Multiempresa SaaS | `tenant_id`, gestão de tenants | ✅ **completo** (não "🚧 em andamento" como no README) |
| 3.5 — Financeiro | não estava no roadmap original | ✅ **completo e não planejado**: expenses, revenues, balancete, relatórios |
| 4 — Mapas e geolocalização | PostGIS + OSRM, tempo real, ETA, geofencing | 🟡 **parcial**: cálculo de KM via serviço externo, mapa básico (`dashboard/map`, `RouteMap.tsx`); faltam geometry PostGIS, ETA, geofencing, tempo real |
| 5 — PWA motorista | app do motorista, offline | ❌ não iniciado |
| 6 — POD (comprovante eletrônico) | assinatura digital, fotos, PDF | 🟡 **parcial**: `deliver-with-proof`, `delivery_proofs`, `Attachment` já existem; assinatura digital/PDF não confirmados |
| 7 — WhatsApp/notificações | alertas, confirmações | ❌ não iniciado (tabela `notifications` existe, canal `whatsapp` previsto no enum, sem envio ativo) |
| 8 — Observabilidade | Grafana/Prometheus/Loki | ❌ não iniciado |
| 9 — IA preditiva | previsão de atrasos | ❌ não iniciado (mas infraestrutura de LLM local já existe via Ollama, reaproveitável) |
| 10 — Comercialização SaaS | onboarding self-service, planos, branding | 🟡 **parcial**: `branding_settings` e `billing_*` já existem no modelo; onboarding self-service não confirmado |

**Conclusão geral**: o sistema está significativamente mais maduro do que a
documentação em `docs/` sugere — a base SaaS multiempresa, o módulo financeiro e
o pipeline de OCR multi-motor (incluindo IA generativa) já estão em produção
funcional, o que muda a priorização recomendada do roadmap: o próximo maior
ganho está em **observabilidade** (para operar com confiança um sistema já
complexo) e em **fechar a Fase 4 (mapas/geo)**, não em "iniciar" a Fase 3 como o
README ainda sugere.

---

*Gerado por análise estática do código-fonte. Para validar comportamento em
runtime (ex.: confirmar se a sessão de preview-session grava auditoria, ou se o
rate limit realmente bloqueia em produção), recomenda-se testes manuais/E2E.*
