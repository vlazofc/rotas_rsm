# Cloudflare Tunnel — Rotas Admmendes

A VPS **não abre porta 80/443**. O `cloudflared` faz conexão de saída (porta 7844)
para a Cloudflare, e a Cloudflare publica o domínio.

## 1. Domínio
O domínio (`seudominio.pt`) precisa estar gerenciado pela Cloudflare (nameservers Cloudflare).

## 2. Criar o Tunnel
No painel: **Zero Trust → Networks → Tunnels → Create a tunnel**
- Conector: **Cloudflared**
- Nome: `rotas-admmendes`
- Ambiente: **Docker** → copie o **token**

Cole o token no `.env`:
```
CLOUDFLARE_TUNNEL_TOKEN=eyJ...token...
```

## 3. Publicar a aplicação (Public Hostname)
No tunnel, adicione um Public Hostname:
- **Subdomain/Domain:** `rotas.seudominio.pt`
- **Service:** `http://proxy:80`

> `cloudflared` e `proxy` estão na mesma rede Docker (`internal`),
> por isso o nome do serviço `proxy` resolve.

## 4. (Recomendado) Cloudflare Access
**Zero Trust → Access → Applications → Add an application (Self-hosted)**
- Domínio: `rotas.seudominio.pt`
- Identity provider: **Microsoft Entra ID**
- Policy: permitir apenas grupos `Admmendes_Rotas_Admin`, `Admmendes_Rotas_Operacao`

A Cloudflare decide **quem entra**; o backend decide **o que cada um pode fazer** (RBAC).

## 5. Firewall da VPS (ufw)
Veja `scripts/firewall.sh`. Resumo:
- **Entrada liberada:** só SSH (22), de preferência restrito ao seu IP.
- **Entrada bloqueada:** 80, 443, 5432, 6379, 9000, 9001, 8000.
- **Saída liberada:** 443, **7844** (Cloudflare Tunnel), DNS, updates.
