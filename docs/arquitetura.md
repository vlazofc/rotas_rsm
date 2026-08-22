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
                     ├── MinIO                  (privado)  → manifestos/comprovantes
                     ├── worker (Celery)        → notificações, cálculos
                     ├── ocr-worker (Celery, fila "ocr")  → PaddleOCR/Tesseract
                     └── scheduler (Celery beat)
```

## Princípios
- **API-first:** o mobile futuro consome a mesma API `/api`.
- **OCR isolado:** `apps/ocr-worker` é trocável (Paddle → Azure DI / Gemini / OpenAI Vision) sem mexer no resto.
- **Segurança em duas camadas:** Cloudflare Access (entrada) + RBAC no backend (regra de negócio).
- **Nada exposto:** Postgres/Redis/MinIO/API só na rede `internal` do Docker.
- **Segredos só no `.env`** do servidor; nunca no Git.
