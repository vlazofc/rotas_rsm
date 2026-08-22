# Rotas Brasil RSM

Plataforma operacional de monitoramento de rotas (CD → entregas → devolução) para a filial do Brasil (Santo André - SP).
API-first, multilíngue (pt-BR / pt-PT), segura e pronta para evoluir para app Android/iOS.

## Stack

| Camada | Tecnologia |
|---|---|
| Frontend | React + Vite + i18next (pt-BR / pt-PT) |
| Backend | FastAPI (Python 3.12) |
| Banco | PostgreSQL + PostGIS |
| Fila / Workers | Redis + Celery |
| OCR | PaddleOCR (principal) + Tesseract (fallback) — **módulo isolado e trocável** |
| Storage | MinIO (S3 compatível) |
| Proxy interno | Caddy |
| Entrada pública | Cloudflare Tunnel (sem abrir portas na VPS) |
| Auth | JWT local + Microsoft Entra ID (OIDC) |
| Deploy | Docker Compose (VPS Hostinger) |

## Estrutura

```
admmendes-rotas-brasil/
├── apps/
│   ├── api/         FastAPI (config, security, RBAC, db, módulos, celery)
│   ├── web/         React + Vite (i18n, login, dashboard, rotas)
│   └── ocr-worker/  Celery + PaddleOCR/Tesseract (pipeline OCR)
├── infra/           Caddyfile + Cloudflare Tunnel
├── scripts/         deploy, backup, restore, firewall, init_server
├── docs/            arquitetura, banco, fluxo, segurança
├── docker-compose.yml
├── docker-compose.dev.yml
└── .env.example
```

## Subir em DESENVOLVIMENTO (local)

```bash
cp .env.example .env          # ajuste AUTH_MODE=local e senhas
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

- Frontend dev (Vite): rode `cd apps/web && npm install && npm run dev` → http://localhost:5173
- API: http://localhost:8000/docs
- MinIO console: http://localhost:9001
- Login inicial: `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` do `.env`

> Para imagem OCR leve só com Tesseract, defina `OCR_ENGINE=tesseract` e remova
> `paddleocr`/`paddlepaddle` de `apps/ocr-worker/requirements.txt`.

## Subir em PRODUÇÃO (VPS Hostinger + Cloudflare Tunnel)

```bash
# 1) Preparar servidor (root)
sh scripts/init_server.sh

# 2) Como usuário deploy
cp .env.example .env && nano .env       # senhas fortes + CLOUDFLARE_TUNNEL_TOKEN
sh scripts/firewall.sh                   # fecha tudo, libera só SSH + saída 7844
sh scripts/deploy.sh                     # docker compose up -d --build
```

No painel Cloudflare (ver `infra/cloudflare/README-tunnel.md`):
- Crie o Tunnel, copie o token para o `.env`.
- Public hostname `rotas.seudominio.pt` → service `http://proxy:80`.
- (Opcional) Cloudflare Access com Microsoft Entra ID.

## Como tudo conecta por `.env`

Um único `.env` na raiz alimenta **todos** os serviços (`env_file: .env` no compose):
`DATABASE_URL`, `REDIS_URL`/`CELERY_*`, `MINIO_*`, `JWT_SECRET`, `MICROSOFT_*`,
`OCR_*`, `CLOUDFLARE_TUNNEL_TOKEN`. Trocar de motor OCR, de storage ou de modo de
auth é só mudar variável — sem tocar no código.

## Fluxo operacional (resumo)

`Chegada CD → Entrada doca → Início/fim carregamento → Liberação → Manifesto (OCR) →
Conferência humana → Geração da rota → Saída CD → Check-in/entrega por ponto → Fechamento`.

Cada transição grava um `RouteEvent` auditável e recalcula os tempos da doca.
Detalhes em [docs/fluxo-operacional.md](docs/fluxo-operacional.md).

## Documentação completa

- [Documentação completa do sistema](docs/sistema-completo.md)
- [Visão e evolução (gap-analysis e roadmap consolidado)](docs/visao-evolucao.md)
- [Arquitetura](docs/arquitetura.md)
- [Banco de dados](docs/banco-dados.md)
- [Fluxo operacional](docs/fluxo-operacional.md)
- [Segurança](docs/seguranca.md)

## Roadmap
- **Fase 1 — Fundação:** ✅ login, perfis, filial, motoristas, veículos, rotas manuais, doca, check-in, dashboard, auditoria.
- **Fase 2 — Manifesto com IA:** ✅ upload, OCR assíncrono, conferência, geração automática da rota, histórico.
- **Fase 3 — Multiempresa SaaS:** 🚧 `tenant_id` (paralelo a `branch_id`), módulo de gestão de empresas (tenants).
- **Fase 4 — Mapas e geolocalização:** PostGIS + OSRM, mapa em tempo real, ETA, geofencing.
- **Fase 5 — PWA motorista:** rota do dia, check-in, foto, hodómetro, portagem, offline.
- **Fase 6 — Comprovante eletrônico (POD):** assinatura digital, fotos de entrega, recibo em PDF.
- **Fase 7 — WhatsApp / notificações:** alertas de atraso, confirmação de entrega, ocorrências.
- **Fase 8 — Observabilidade:** Grafana + Prometheus + Loki.
- **Fase 9 — IA preditiva:** revisão de OCR via Ollama/Llama local, previsão de atrasos.
- **Fase 10 — Comercialização SaaS:** onboarding self-service de novos tenants, planos, branding.

Detalhes, decisões de arquitetura e gap-analysis completo em
[docs/visao-evolucao.md](docs/visao-evolucao.md).
