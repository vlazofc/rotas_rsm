# Visão e Evolução — Sistema Rotas Admmendes PT

Este documento consolida a visão de arquitetura recebida (PDF "Documento Final de
Arquitetura e Engenharia" + rascunho "Documento Oficial de Engenharia de Software",
47 seções, modelo SaaS multiempresa) com o **estado real do código** hoje, faz a
análise de lacunas (gap-analysis) e define o roadmap/backlog daqui para frente.

> Os documentos recebidos descrevem a **visão de produto** (onde queremos chegar).
> Este documento é o ponto de encontro entre essa visão e o scaffold já implementado
> (Fase 1 — Fundação), evitando retrabalho e divergência de arquitetura.

---

## 1. O que já existe (estado atual do código)

| Área | Status | Onde |
|---|---|---|
| Auth local (JWT) + Microsoft Entra ID (OIDC) | ✅ implementado | `apps/api/app/modules/auth` |
| RBAC (6 perfis) | ✅ implementado | `apps/api/app/core/permissions.py` |
| Multi-filial (`branch_id`) | ✅ implementado | em quase todas as tabelas |
| Multiempresa (`tenant_id`) | 🆕 nesta entrega | ver seção 4 |
| Motoristas / Veículos | ✅ CRUD completo | `modules/drivers`, `modules/vehicles` |
| Rotas + paragens + eventos auditáveis | ✅ implementado | `modules/routes` |
| Tempos de doca (`dock_sessions`) | ✅ implementado | `db/models.py` |
| Manifestos + OCR (Paddle/Tesseract/EasyOCR) + geração de rota | ✅ implementado | `modules/manifests`, `apps/ocr-worker` |
| Comprovantes de entrega (`delivery_proofs`, `attachments`) | ✅ modelo pronto, fluxo de upload existe | `db/models.py`, `services/storage.py` |
| Auditoria (backend) | ✅ implementado | `modules/audit` |
| Auditoria (frontend) | 🆕 nesta entrega — era placeholder | `pages/Audit.tsx` |
| Dashboard operacional | ✅ implementado (cards básicos) | `modules/dashboard`, `pages/Dashboard.tsx` |
| i18n pt-BR / pt-PT | ✅ implementado | `apps/web/src/i18n` |
| Notificações (modelo) | ✅ tabela existe, sem canal ativo | `db/models.py` |
| Backup PostgreSQL/MinIO | ✅ scripts existentes | `scripts/` |
| Observabilidade (Grafana/Prometheus/Loki) | ❌ não iniciado | — |
| Geolocalização (PostGIS/OSRM/mapas) | ❌ não iniciado (campos lat/lng já existem em `route_stops`/`route_events`/`checkins`) | — |
| WhatsApp / notificações externas | ❌ não iniciado | — |
| App mobile (React Native) | ❌ não iniciado | — |
| IA local (Ollama + Llama) | ❌ não iniciado — hoje OCR é determinístico (Paddle/Tesseract/EasyOCR) | — |
| Assinatura digital / geofencing / rastreamento automático | ❌ não iniciado | — |

**Conclusão:** a "Fase 1 — Fundação" do README já está praticamente completa e vai além
do previsto (manifesto + OCR já funcionam, o que estava previsto para a Fase 2).
O maior gap real está em: **multiempresa SaaS**, **mapas/geolocalização**,
**observabilidade**, **mobile** e **IA local**.

---

## 2. Decisões de arquitetura tomadas nesta rodada

### 2.1 Multiempresa SaaS (`tenant_id`)
O documento novo pede `tenant_id` em todas as entidades para isolar empresas
(Admmendes Brasil, clientes externos). O código atual já isola por
`branch_id` (filial/armazém).

**Decisão:** adicionar `tenant_id` **em paralelo** a `branch_id`, sem remover nada:

```
Tenant (empresa) 1—N Branch (filial/armazém) 1—N {users, drivers, vehicles, routes, ...}
```

- Nova tabela `tenants` (`id`, `name`, `slug`, `country`, `active`).
- `tenant_id` adicionado a: `branches`, `users`, `drivers`, `vehicles`, `routes`,
  `manifests`, `audit_logs`, `notifications`.
- No bootstrap, cria-se o tenant `Admmendes Brasil` e todas as filiais/registros
  existentes são associados a ele automaticamente.
- RBAC continua a isolar por `branch_id` (sem mudança de comportamento).
  `tenant_id` fica disponível para:
  - Relatórios/consultas cross-filial dentro da mesma empresa.
  - Onboarding de novas empresas (Fase 10 — comercialização SaaS) sem migração de schema.
  - Um futuro perfil `admin_saas` (acima de `admin_global`) com acesso cross-tenant.
- Como o projeto usa `create_all` (sem Alembic — ver [[schema-no-migrations]]),
  o `bootstrap.py` agora também roda um `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
  leve para as colunas novas, para não quebrar bancos de dev já existentes.

### 2.2 IA local (Ollama + Llama)
**Decisão:** manter o pipeline OCR atual (Paddle/Tesseract/EasyOCR + extração por
regras) como está — é determinístico, leve e já funciona. Ollama + Llama 3 entra
como **Fase futura (pós-MVP OCR)**, como uma etapa adicional opcional no
`ocr-worker`: depois da extração estruturada por regras, um modelo local
(Llama/Qwen/Mistral via Ollama) pode revisar/complementar campos de baixa
confiança antes da conferência humana. Sem dependência nova até lá.

### 2.3 Outras divergências do documento novo vs. código atual
| Documento novo | Código atual | Decisão |
|---|---|---|
| Nginx | Caddy | manter Caddy (mais simples, TLS automático, já configurado em `infra/`) |
| Tesseract apenas | Paddle/Tesseract/EasyOCR (motor trocável) | manter motor trocável via `OCR_ENGINE` |
| `users, roles, tenants, drivers, vehicles, trips, deliveries, checkpoints, occurrences, audit_logs` | `branches, users, drivers, vehicles, routes, route_stops, route_events, dock_sessions, manifests, ocr_results, checkins, delivery_proofs, tolls, odometer_readings, attachments, audit_logs, notifications, role_profiles, delivery_failure_reasons` | modelo atual é mais granular (tempos de doca, eventos, motivos de falha) — manter; `tenants` adicionado nesta entrega |

---

## 3. Roadmap consolidado (substitui a seção "Roadmap" do README)

- **Fase 1 — Fundação** ✅ concluída: login, RBAC, filiais, motoristas, veículos,
  rotas manuais, doca, check-in, dashboard, auditoria (backend + frontend).
- **Fase 2 — Manifesto com IA** ✅ concluída (OCR síncrono/assíncrono, conferência,
  geração automática de rota). Pendente apenas: revisão por LLM local (Ollama) — ver 2.2.
- **Fase 3 — Multiempresa SaaS** 🆕 em andamento (esta entrega): `tenant_id`,
  módulo de gestão de tenants, preparação para múltiplas empresas/clientes.
- **Fase 4 — Mapas e geolocalização**: PostGIS + OSRM, mapa em tempo real das
  rotas, cálculo de distância/ETA, geofencing dos pontos de entrega.
- **Fase 5 — PWA/App motorista (React Native)**: rota do dia, check-in com GPS,
  foto de entrega, hodómetro, portagem, modo offline — consumindo a mesma API.
- **Fase 6 — Comprovante eletrônico (POD)**: assinatura digital do cliente,
  fotos de entrega anexadas ao `delivery_proofs`, recibo em PDF.
- **Fase 7 — WhatsApp / notificações**: Evolution API ou WhatsApp Business para
  alertas de atraso, confirmação de entrega, ocorrências — usando a tabela
  `notifications` já existente (canal `whatsapp`).
- **Fase 8 — Observabilidade**: Grafana + Prometheus + Loki nos containers
  já listados no `docker-compose`.
- **Fase 9 — IA preditiva**: Ollama/Llama para revisão de OCR (ver 2.2),
  previsão de atrasos, sugestão de rotas com base em histórico.
- **Fase 10 — Comercialização SaaS**: onboarding self-service de novos tenants,
  faturação, planos, branding por tenant.

---

## 4. Backlog imediato (próximos itens, em ordem)

1. **`tenants` — modelo + migração leve + módulo CRUD (admin_global)** — base para
   todas as fases seguintes que dependem de multiempresa.
2. **Página de Auditoria (frontend)** — completa o requisito "auditoria completa"
   de segurança já citado no `docs/seguranca.md`, backend já pronto.
3. Tela de gestão de **filiais por tenant** (Config → aba Filiais já existe;
   adicionar coluna/seleção de tenant quando houver mais de um).
4. Endpoint `GET /tenants/me` para o frontend exibir o nome da empresa no layout.
5. (Fase 4) Spike de integração OSRM: endpoint `routes/{id}/eta` calculando
   distância/tempo entre paragens via PostGIS + OSRM.

Itens 1 e 2 são implementados nesta mesma entrega.
