# Segurança e LGPD (Brasil)

## Proteções já no MVP
- Login obrigatório + JWT validado no backend.
- RBAC por perfil (`core/permissions.py`): admin_global, gestor_brasil, operador_logistico, torre_controle, motorista, auditor.
- Filtro por filial/branch em todas as consultas (exceto admin global).
- Rate limit por IP (slowapi).
- CORS restrito a `ALLOWED_ORIGINS`.
- Upload: tipo MIME validado + limite `MAX_UPLOAD_MB`; arquivos no MinIO (fora do container da API).
- Postgres/Redis/MinIO sem porta pública.
- Auditoria (`audit_logs`) de login e alterações.
- Bloqueio de edição em rota encerrada.
- Backup diário automático (retenção 14 dias).

## Isolamento multi-tenant

- Usuários comuns precisam ter `tenant_id` e `branch_id` válidos e ativos.
- A filial deve pertencer ao mesmo tenant do usuário.
- Auditoria, clientes e fornecedores são filtrados no backend.
- Rotas validam filial, motorista e veículo antes de persistir.
- OCR e Financeiro rejeitam chamadas quando desativados no plano.
- Apenas o administrador global atravessa tenants para operar o painel SaaS.

## GDPR — regras de produto
- Monitorar **só durante a jornada/rota ativa** (não em uso privado do veículo).
- Registrar finalidade operacional e informar o motorista sobre o tratamento.
- Acesso por necessidade: não expor localização a quem não tem permissão.
- Retenção configurável + criptografia em trânsito (HTTPS via Cloudflare) e em repouso.

Referências: EDPB (veículos conectados/mobilidade) e CNPD (geolocalização laboral).

## Cloudflare Access + Entra ID
Cloudflare valida identidade **antes** de chegar à VPS; o backend ainda valida
usuário/perfil/filial/ação e grava auditoria. Defesa em profundidade.
