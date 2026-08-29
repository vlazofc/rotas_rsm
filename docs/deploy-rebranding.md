# Renomear o stack no servidor (jm-rotas-brasil → admmendes-rotas)

O painel da VPS mostra o **nome do projeto Docker Compose**, que hoje é
`jm-rotas-brasil` (derivado da pasta/como a stack foi criada originalmente no
servidor). Isso agora é controlado num único lugar: o campo `name:` no topo do
`docker-compose.yml` (já definido como `admmendes-rotas`).

**Importante:** só trocar esse nome e rodar `docker compose up` de novo **não
é seguro por si só** — por padrão, os volumes (Postgres, Redis, MinIO, Caddy)
são nomeados com o prefixo do projeto. Um projeto novo criaria volumes novos e
vazios, e os dados atuais (rotas, usuários e comprovantes) ficariam
"presos" nos volumes antigos, parecendo que sumiram.

Para evitar isso, o `docker-compose.yml` já foi ajustado para usar **nomes de
volume fixos** (`admmendes_postgres_data`, `admmendes_redis_data`,
`admmendes_minio_data`, `admmendes_caddy_data`, `admmendes_caddy_config`),
independentes do nome do projeto. Siga os passos
abaixo **na VPS** para migrar sem perder dados.

## 1. Descobrir os nomes atuais dos volumes

```bash
docker volume ls | grep -E "postgres_data|redis_data|minio_data|caddy"
```

Anote os nomes exatos (algo como `jm-rotas-brasil_postgres_data`,
`jm-rotas-brasil_minio_data`, etc.).

## 2. Backup antes de mexer (obrigatório)

```bash
# Postgres — já tem script pronto
sh scripts/backup_postgres.sh    # grava em ./backups/

# MinIO — cópia bruta do volume (não há script dedicado ainda)
docker run --rm -v <nome_do_volume_minio_atual>:/data -v "$PWD/backups":/backup \
  alpine tar czf /backup/minio_data_$(date +%Y%m%d_%H%M%S).tar.gz -C /data .
```

## 3. Parar a stack atual (sem apagar volumes)

```bash
docker compose down          # NÃO use -v — isso apagaria os volumes
```

## 4. Atualizar o código no servidor

```bash
git pull        # ou copie o docker-compose.yml/repositório atualizado
```

## 5. Migrar os dados dos volumes antigos para os novos nomes fixos

Repita para cada volume (Postgres, Redis, MinIO, Caddy data e Caddy config):

```bash
docker volume create admmendes_postgres_data
docker run --rm \
  -v <nome_antigo_postgres>:/from \
  -v admmendes_postgres_data:/to \
  alpine sh -c "cd /from && cp -av . /to"
```

Ajuste `<nome_antigo_*>` e o nome de destino (`admmendes_redis_data`,
`admmendes_minio_data`, `admmendes_caddy_data`, `admmendes_caddy_config`)
para os outros volumes.

## 6. Subir a stack com o novo nome de projeto

```bash
docker compose --profile cloudflare up -d --build
```

Confirme no painel que o projeto agora aparece como `admmendes-rotas`.

## 7. Validar antes de limpar o que sobrou

- Login funciona com o admin existente.
- Rotas e usuários anteriores aparecem normalmente.
- Upload/consulta de comprovantes (MinIO) funciona.

## 8. Só depois de validar: remover os containers/volumes antigos

```bash
docker ps -a | grep jm-rotas-brasil     # containers órfãos do projeto antigo, se sobrou algum
docker volume rm <nome_antigo_postgres> <nome_antigo_redis> <nome_antigo_minio> <nome_antigo_caddy_data> <nome_antigo_caddy_config>
```

Não apague os volumes antigos até ter certeza de que a stack nova subiu com
todos os dados corretos — eles são a única cópia "ao vivo" caso algo dê errado
na migração.
