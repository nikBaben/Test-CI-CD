#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

BASE_DIR=/opt/account-service
RELEASE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
RELEASE_SHA="$(basename "$RELEASE_DIR")"

# Скрипт запускается только из каталога конкретного релиза.
if [[ ! "$RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]] ||
   [[ "$RELEASE_DIR" != "$BASE_DIR/releases/$RELEASE_SHA" ]]; then
  echo "Неверный каталог релиза." >&2
  exit 1
fi

test -r "$BASE_DIR/.env.production"

# Одновременно может выполняться только одно развёртывание.
exec 9>"$BASE_DIR/deploy.lock"
flock -w 600 9

APP_IMAGE="ghcr.io/nikbaben/test-ci-cd:$RELEASE_SHA"
MINIO_IMAGE="ghcr.io/nikbaben/test-ci-cd-minio:$RELEASE_SHA"

printf 'APP_IMAGE=%s\nMINIO_IMAGE=%s\n' \
  "$APP_IMAGE" "$MINIO_IMAGE" > "$RELEASE_DIR/release.env"

export DOCKER_CONFIG="$RELEASE_DIR/.docker"

compose=(
  docker compose
  --project-name account-service
  --env-file "$BASE_DIR/.env.production"
  --env-file "$RELEASE_DIR/release.env"
  -f "$RELEASE_DIR/compose.production.yaml"
)

cleanup() {
  status=$?
  rm -f "$DOCKER_CONFIG/config.json" || true

  if [[ "$status" -ne 0 ]]; then
    "${compose[@]}" start minio || true
    echo "Развёртывание завершилось ошибкой. Нужна проверка логов." >&2
  fi

  exit "$status"
}
trap cleanup EXIT
# Шаблон realm должен быть доступен пользователю внутри Keycloak.
chmod 0644 "$RELEASE_DIR/docker/keycloak/product-service-realm.json"
"${compose[@]}" config --quiet
"${compose[@]}" pull

# Подготавливаем инфраструктуру.
"${compose[@]}" up -d --no-build \
  --wait --wait-timeout 180 \
  app-db keycloak-db rabbitmq minio

# При обновлении останавливаем API перед копированием данных и миграциями.
"${compose[@]}" stop api

mkdir -p "$BASE_DIR/backups"
BACKUP_DIR="$(mktemp -d \
  "$BASE_DIR/backups/$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"

"${compose[@]}" exec -T app-db \
  sh -ec 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "$BACKUP_DIR/account.dump"

"${compose[@]}" exec -T keycloak-db \
  sh -ec 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "$BACKUP_DIR/keycloak.dump"

# Останавливаем MinIO для копирования его файлов.
"${compose[@]}" stop minio

docker run --rm \
  --network none \
  --user 0:0 \
  --entrypoint /bin/tar \
  --mount type=volume,src=account-service_minio_documents,dst=/data,readonly \
  --mount "type=bind,src=$BACKUP_DIR,dst=/backup" \
  "$MINIO_IMAGE" \
  -czf /backup/minio.tar.gz -C /data .

# Compose выполнит миграции, настройку Keycloak и запуск API.
"${compose[@]}" up -d --no-build \
  --wait --wait-timeout 600

curl --fail --silent --show-error --max-time 10 \
  http://127.0.0.1:18000/health > /dev/null

# Отмечаем успешно запущенный релиз.
ln -sfn "$RELEASE_DIR" "$BASE_DIR/current.next"
mv -Tf "$BASE_DIR/current.next" "$BASE_DIR/current"

echo "Релиз $RELEASE_SHA успешно запущен."