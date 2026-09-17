# Trans Adimax — Gestão de Rotas

Plataforma operacional da Trans Adimax para planejamento e monitoramento de rotas, entregas, falhas e evidências.
API-first, multilíngue (pt-BR / pt-PT), segura e pronta para evoluir para app Android/iOS.

## Stack

| Camada | Tecnologia |
|---|---|
| Frontend | React + Vite + i18next (pt-BR / pt-PT) |
| Backend | FastAPI (Python 3.12) |
| Banco | PostgreSQL + PostGIS |
| Fila / Workers | Redis + Celery |
| Storage | MinIO (S3 compatível) |
| Proxy interno | Caddy |
| Entrada pública | Cloudflare Tunnel (sem abrir portas na VPS) |
| Auth | JWT local com access e refresh token |
| Deploy | Docker Compose (VPS Hostinger) |

## Estrutura

```
trans-adimax-rotas/
├── apps/
│   ├── api/         FastAPI (config, security, RBAC, db, módulos, celery)
│   ├── web/         React + Vite (i18n, login, dashboard, rotas)
│   └── android-driver/ Aplicativo Android Studio para o motorista
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
- App do motorista: abra `apps/android-driver` no Android Studio.

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
- Public hostname `jmdistribuicao.com.br` → service `http://proxy:80`.
- (Opcional) proteja o hostname também com Cloudflare Access.

## Como tudo conecta por `.env`

Um único `.env` na raiz alimenta **todos** os serviços (`env_file: .env` no compose):
`DATABASE_URL`, `REDIS_URL`/`CELERY_*`, `MINIO_*`, `JWT_SECRET` e
`CLOUDFLARE_TUNNEL_TOKEN`. Em produção, o boot rejeita segredos padrão e CORS HTTP/local.

## Fluxo operacional (resumo)

`Criação/importação da rota → chegada CD → entrada doca → início/fim carregamento →
liberação → saída CD → check-in/entrega por ponto → fechamento`.

Cada transição grava um `RouteEvent` auditável e recalcula os tempos da doca.
Detalhes em [docs/fluxo-operacional.md](docs/fluxo-operacional.md).

## Documentação completa

- [Arquitetura](docs/arquitetura.md)
- [Banco de dados](docs/banco-dados.md)
- [Fluxo operacional](docs/fluxo-operacional.md)
- [Segurança](docs/seguranca.md)
