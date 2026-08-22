#!/bin/bash
# Firewall da VPS (ufw). A aplicação NÃO expõe portas: só o Cloudflare Tunnel sai.
# Rode como root na VPS Hostinger.
set -e

ufw --force reset

# Política padrão
ufw default deny incoming
ufw default allow outgoing

# Entrada: apenas SSH (de preferência restrinja ao seu IP):
# ufw allow from SEU.IP.AQUI to any port 22 proto tcp
ufw allow 22/tcp

# Saída necessária para o Cloudflare Tunnel (cloudflared)
ufw allow out 7844/tcp
ufw allow out 7844/udp
ufw allow out 443/tcp
ufw allow out 53/udp

ufw --force enable
ufw status verbose

echo "Firewall aplicado. Portas 80/443/5432/6379/9000/9001/8000 permanecem fechadas para a internet."
