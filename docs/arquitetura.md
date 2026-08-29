# Arquitetura

```
Usuário / Motorista / Operador
        │  (Web / PWA / futuro app)
        ▼
Cloudflare DNS + WAF + Access        ← decide QUEM entra
        │
Cloudflare Tunnel (cloudflared)      ← única entrada; saída 7844, sem porta aberta
        ▼
Caddy (proxy interno)
   ├── /        → web (SPA nginx)
   └── /api     → api (FastAPI)      ← decide O QUE cada um faz (RBAC + auditoria)
                     ├── PostgreSQL + PostGIS   (privado)
                     ├── Redis                  (privado)  → fila Celery
                     ├── MinIO                  (privado)  → comprovantes/anexos
                     ├── worker (Celery)        → notificações, cálculos
                     └── scheduler (Celery beat)
```

## Princípios
- **API-first:** o mobile futuro consome a mesma API `/api`.
- **Segurança em duas camadas:** Cloudflare Access (entrada) + RBAC no backend (regra de negócio).
- **Nada exposto publicamente:** portas administrativas escutam somente em `127.0.0.1`; serviços comunicam pela rede `internal`.
- **Segredos só no `.env`** do servidor; nunca no Git.
