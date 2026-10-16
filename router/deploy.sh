#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
test -f .env || { echo 'Copy .env.example to .env and edit your settings first.'; exit 1; }
mkdir -p data
BIND_IP=$(sed -n 's/^LAN_BIND_IP=//p' .env | tail -n 1)
WEB_PORT=$(sed -n 's/^WEB_PORT=//p' .env | tail -n 1)
APK_MIRROR=$(sed -n 's/^APK_MIRROR=//p' .env | tail -n 1)
MEMORY_LIMIT=$(sed -n 's/^MEMORY_LIMIT=//p' .env | tail -n 1)
BIND_IP=${BIND_IP:-127.0.0.1};WEB_PORT=${WEB_PORT:-13335};MEMORY_LIMIT=${MEMORY_LIMIT:-256m}
NAME=cf-select
if docker inspect "$NAME" >/dev/null 2>&1; then
  LABEL=$(docker inspect "$NAME" --format '{{index .Config.Labels "cf-select.managed"}}')
  test "$LABEL" = 1 || { echo 'A different container uses this name; choose another name in this script.'; exit 1; }
fi
docker build --build-arg "APK_MIRROR=$APK_MIRROR" -t cf-select:local .
if docker inspect "$NAME" >/dev/null 2>&1; then docker stop "$NAME"; docker rm "$NAME"; fi
docker run -d --name "$NAME" --label cf-select.managed=1 \
  --restart unless-stopped --memory "$MEMORY_LIMIT" \
  --log-opt max-size=5m --log-opt max-file=2 \
  --env-file .env -p "$BIND_IP:$WEB_PORT:$WEB_PORT" \
  -v "$(pwd)/data:/data" cf-select:local
