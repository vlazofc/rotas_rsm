#!/bin/sh
set -eu

cd /home/admax/adimax-app

db_info=$(sudo docker compose run --rm --no-deps -T api python -c 'import os, urllib.parse; u=urllib.parse.urlsplit(os.environ["DATABASE_URL"]); print(f"{u.username}|{u.password}|{u.path.lstrip(chr(47))}")')
db_user=$(printf '%s' "$db_info" | cut -d '|' -f 1)
db_password=$(printf '%s' "$db_info" | cut -d '|' -f 2)
db_name=$(printf '%s' "$db_info" | cut -d '|' -f 3)

sudo docker compose stop api worker scheduler backup
escaped_password=$(printf '%s' "$db_password" | sed "s/'/''/g")
printf "ALTER ROLE \"%s\" PASSWORD '%s';\n" "$db_user" "$escaped_password" | sudo docker exec -i rotas_postgres psql -U "$db_user" -d postgres

if ! sudo docker exec rotas_postgres psql -U "$db_user" -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname='$db_name'" | grep -q 1; then
  sudo docker exec rotas_postgres createdb -U "$db_user" "$db_name"
fi

sudo docker cp /home/admax/adimax-local.dump rotas_postgres:/tmp/adimax-local.dump
sudo docker exec rotas_postgres pg_restore --clean --if-exists --no-owner -U "$db_user" -d "$db_name" /tmp/adimax-local.dump
sudo docker compose up -d api worker scheduler backup

tries=0
until curl -fsS http://127.0.0.1:8089/health >/dev/null 2>&1 || [ "$tries" -ge 20 ]; do
  tries=$((tries + 1))
  sleep 2
done

printf 'DATABASE=%s\n' "$db_name"
printf 'ROUTES='
sudo docker exec rotas_postgres psql -U "$db_user" -d "$db_name" -Atc 'select count(*) from routes'
printf 'USERS='
sudo docker exec rotas_postgres psql -U "$db_user" -d "$db_name" -Atc 'select count(*) from users'
printf 'ROOT_HTTP='
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8089/
printf 'API_HTTP='
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8089/health
